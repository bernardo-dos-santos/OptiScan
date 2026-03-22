import os
import threading
from flask import Flask, request, abort
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from functools import wraps
from dotenv import load_dotenv


from services.banco import salvar_no_banco, executar_estorno_banco
from services.leitor import analisar_imagem
from services.sheets import atualizar_sheets

load_dotenv()

app = Flask(__name__)
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
TWILIO_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', 'whatsapp:+14155238886') # Ajuste se necessário

def validate_twilio_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
        
        # O Twilio envia a assinatura no cabeçalho 'X-Twilio-Signature'
        signature = request.headers.get('X-Twilio-Signature', '')
        
        # Precisamos da URL completa que o Twilio está chamando
        # Se você estiver usando ngrok para testar, ele cuida disso
        url = request.url
        data = request.form.to_dict()

        if not validator.validate(url, data, signature):
            print("🚨 TENTATIVA DE INVASÃO: Assinatura do Twilio inválida!")
            abort(403) # Retorna "Proibido"
        return f(*args, **kwargs)
    return decorated_function

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("chave_nova.json")

@app.route("/whatsapp", methods=['POST'])
@validate_twilio_request
def whatsapp():
    numero_usuario = request.values.get('From', '')
    corpo_mensagem = request.values.get('Body', '').strip().lower()
    num_media = request.values.get('NumMedia', '0')

    
    client_id = 1 
    planilha_id = os.getenv('PLANILHA_ID')

    res = MessagingResponse()

 # --- COMANDO DE CORREÇÃO (ESTORNO) ---
    if corpo_mensagem == "corrigir":
        resultado = executar_estorno_banco(client_id, planilha_id)
        if resultado:
            acao = "Removidas" if resultado['acao_desfeita'] == 'ENTRADA' else "Adicionadas"
            res.message(f"🔄 *Estornado com sucesso!*\n\n📦 Ref: {resultado['product_id']}\n⚖️ {resultado['estornado']} unidades {acao}.\n📊 Novo Saldo: {resultado['total']}")
        else:
            res.message("❌ Nenhum registro recente para desfazer ou já estornado.")
        return str(res)
    
    # --- COMANDOS DE TEXTO MANUAL (ENTRADA / SAÍDA) ---
    if corpo_mensagem.startswith(("entrada", "saida", "saída")):
        partes = corpo_mensagem.split()
        
        if len(partes) >= 3:
            # Remove o acento caso o corretor do celular do funcionário coloque "saída"
            comando = partes[0].replace('í', 'i') 
            ref = partes[1].upper()
            
            try:
                qtd = float(partes[2].replace(',', '.'))
            except ValueError:
                res.message("❌ Quantidade inválida. Use apenas números.")
                return str(res)
            
            dados_manuais = {'referencia': ref, 'quantidade': qtd, 'peso': 0}
            tipo_op = 'ENTRADA' if comando == "entrada" else 'SAIDA'
            
            log = salvar_no_banco(dados_manuais, client_id, planilha_id, tipo_operacao=tipo_op)
            atualizar_sheets(dados_manuais, log['total'], planilha_id)
            
            acao = "Adicionadas" if tipo_op == 'ENTRADA' else "Removidas"
            res.message(f"✅ *{tipo_op.capitalize()} Manual Registrada!*\n\n📦 Ref: {log['product_id']}\n⚖️ {qtd} unidades {acao}.\n📊 Novo Saldo: {log['total']}")
        else:
            res.message("❌ Formato incorreto. Use: `entrada [CÓDIGO] [QTD]` ou `saida [CÓDIGO] [QTD]`")
        
        return str(res)

    # --- ENTRADA VIA FOTO (ASSÍNCRONA) ---
    if num_media != '0':
        url_imagem = request.values.get('MediaUrl0')
        
        # Responde HTTP 200 rápido para o Twilio não dar erro de Timeout
        res.message("📸 Imagem recebida. Analisando...")
        
        # Delega o trabalho pesado (OCR/Gemini, Banco e Planilha) para background
        threading.Thread(
            target=processar_imagem_background,
            args=(url_imagem, numero_usuario, client_id, planilha_id)
        ).start()
        
        return str(res)

    # --- TEXTO LIVRE ---
    res.message("👋 Envie a foto da etiqueta do fardo para registrar a entrada, ou digite 'saida [código] [qtd]'.")
    return str(res)

def processar_imagem_background(url_imagem, numero_usuario, client_id, planilha_id):
    """Função que roda nos bastidores sem prender o Webhook"""
    try:
        # 1. Visão Computacional
        dados_extraidos = analisar_imagem(url_imagem)
        
        if not dados_extraidos or dados_extraidos.get('referencia') == 'N/A':
            enviar_whatsapp(numero_usuario, "❌ Não consegui ler os dados da etiqueta nesta foto. Tente mais de perto.")
            return

        # 2. Lógica de Banco e Sincronização
        log = salvar_no_banco(dados_extraidos, client_id, planilha_id)
        
        # 3. Atualização Externa
        atualizar_sheets(dados_extraidos, log['total'], planilha_id)
        
        # 4. Feedback Final
        msg = f"✅ Entrada Registrada!\n\n📦 Ref: {log['product_id']}\n⚖️ Peso: {dados_extraidos.get('peso', 0)}\n📊 Total Estoque: {log['total']}\n\n Para reverter, digite 'Corrigir'"
        enviar_whatsapp(numero_usuario, msg)

    except Exception as e:
        enviar_whatsapp(numero_usuario, f"⚠️ Erro interno no sistema: {str(e)}")

def enviar_whatsapp(para, texto):
    """Função auxiliar para enviar mensagens ativas via Twilio"""
    twilio_client.messages.create(
        body=texto,
        from_=TWILIO_NUMBER,
        to=para
    )

if __name__ == "__main__":
    app.run(port=5000, debug=True)