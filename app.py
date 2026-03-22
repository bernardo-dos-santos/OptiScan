import os
import threading
from flask import Flask, request, abort
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from functools import wraps
from dotenv import load_dotenv


from services.banco import salvar_no_banco, executar_estorno_banco, buscar_cliente_por_whatsapp, atualizar_estoque_via_webhook
from services.leitor import analisar_imagem
from services.sheets import atualizar_sheets

load_dotenv()

app = Flask(__name__)
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
TWILIO_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', 'whatsapp:+14155238886')

def validate_twilio_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
        signature = request.headers.get('X-Twilio-Signature', '')
        url = request.url
        data = request.form.to_dict()

        if not validator.validate(url, data, signature):
            print("🚨 TENTATIVA DE INVASÃO: Assinatura do Twilio inválida!")
            abort(403) 
        return f(*args, **kwargs)
    return decorated_function

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("chave_nova.json")

@app.route("/whatsapp", methods=['POST'])
@validate_twilio_request
def whatsapp():
    # Pega os dados brutos e limpa
    numero_usuario = request.values.get('From', '').replace('whatsapp:', '')
    corpo_mensagem_original = request.values.get('Body', '').strip()
    corpo_mensagem = corpo_mensagem_original.lower() # Versão para checagem de comandos
    num_media = request.values.get('NumMedia', '0')

    # --- COMANDO DE ADMIN (SÓ VOCÊ) ---
    ADMIN_NUMBER = os.getenv('ADMIN_NUMBER') 
    
    if numero_usuario == ADMIN_NUMBER and corpo_mensagem.startswith('admin_add'):
        partes = corpo_mensagem_original.split() # Usa a original para não perder maiúsculas no Nome/ID
        if len(partes) >= 4:
            nome_empresa = partes[1].replace('_', ' ')
            zap_novo = partes[2]
            planilha_nova = partes[3]
            
            from services.banco import admin_cadastrar_cliente
            novo_id = admin_cadastrar_cliente(nome_empresa, zap_novo, planilha_nova)
            
            res = MessagingResponse()
            if novo_id:
                res.message(f"✅ *Cliente {nome_empresa} Cadastrado!*\nID: {novo_id}\nStatus: Ativo")
            else:
                res.message("❌ Erro ao cadastrar. Verifique se o número já existe.")
            return str(res)

    # --- IDENTIFICAÇÃO DINÂMICA DO CLIENTE ---
    numero_limpo = numero_usuario.replace('whatsapp:', '')
    cliente = buscar_cliente_por_whatsapp(numero_limpo)
    
    res = MessagingResponse()

    if not cliente:
        res.message("❌ Número não autorizado. Contate o suporte do Optilog para registrar a sua empresa.")
        return str(res)
    
    client_id = cliente['id']
    planilha_id = cliente['planilha_id']
    # -----------------------------------------

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
        res.message("📸 Imagem recebida. Analisando...")
        
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
        dados_extraidos = analisar_imagem(url_imagem)
        
        if not dados_extraidos or dados_extraidos.get('referencia') == 'N/A':
            enviar_whatsapp(numero_usuario, "❌ Não consegui ler os dados da etiqueta nesta foto. Tente mais de perto.")
            return

        log = salvar_no_banco(dados_extraidos, client_id, planilha_id)
        atualizar_sheets(dados_extraidos, log['total'], planilha_id)
        nome_prod = dados_extraidos.get('nome', 'Produto')
        espec = dados_extraidos.get('especificacao', 'N/A')
        
        msg = (f"✅ *Entrada Registrada!*\n\n"
               f"📦 *Produto:* {nome_prod}\n"
               f"🔧 *Spec:* {espec}\n"
               f"🔢 *Ref:* {log['product_id']}\n"
               f"📊 *Estoque Atual:* {log['total']}\n\n"
               f"Para reverter, digite 'Corrigir'")
               
        enviar_whatsapp(numero_usuario, msg)

    except Exception as e:
        enviar_whatsapp(numero_usuario, f"⚠️ Erro interno no sistema: {str(e)}")

def enviar_whatsapp(para, texto):
    """Função auxiliar para enviar mensagens ativas via Twilio"""
    # Garante que o número do remetente tenha o prefixo correto
    remetente = TWILIO_NUMBER if TWILIO_NUMBER.startswith('whatsapp:') else f"whatsapp:{TWILIO_NUMBER}"
    
    # Garante que o número do destinatário tenha o prefixo correto
    destinatario = para if para.startswith('whatsapp:') else f"whatsapp:{para}"
    
    twilio_client.messages.create(
        body=texto,
        from_=remetente,
        to=destinatario
    )

@app.route("/webhook_planilha", methods=['POST'])
def webhook_planilha():
    # --- VALIDAÇÃO DE SEGURANÇA ---
    token_recebido = request.headers.get('x-api-key')
    token_esperado = os.getenv('WEBHOOK_SECRET') 
    
    if token_recebido != token_esperado:
        print("🚨 TENTATIVA DE INVASÃO: Token do Webhook inválido!")
        return "Não autorizado", 403
    # ------------------------------

    dados = request.json
    if not dados:
        return "Sem dados", 400
        
    client_id = dados.get('client_id')
    ref = dados.get('referencia')
    nova_qtd = dados.get('quantidade')
    
    if not all([client_id, ref, nova_qtd is not None]):
        return "Dados incompletos", 400
        
    try:
        nova_qtd = float(nova_qtd)
        atualizar_estoque_via_webhook(client_id, str(ref), nova_qtd)
        return "Atualizado no banco", 200
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    app.run(port=5000, debug=True)