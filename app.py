import os
import threading
from flask import Flask, jsonify, request, abort
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from functools import wraps
from dotenv import load_dotenv


from services.banco import salvar_no_banco, executar_estorno_banco, buscar_cliente_por_whatsapp, atualizar_estoque_via_webhook, admin_cadastrar_cliente
from services.leitor import analisar_imagem
from services.sheets import atualizar_sheets, verificar_alerta_minimo

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
        res.message("❌ Número não reconhecido. Parece que seu número não está registrado, entre em contato com o suporte da OptiScan para mais informações.")
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
            comando = partes[0].replace('í', 'i').lower()
            
            # O último item digitado sempre deve ser a quantidade
            try:
                qtd = float(partes[-1].replace(',', '.'))
            except ValueError:
                res.message("❌ Erro de formato. Certifique-se de que o *último* termo seja a quantidade (número).")
                return str(res)
            
            # O que sobra entre o comando e a quantidade é o termo de busca (ID ou Nome)
            termo_busca = " ".join(partes[1:-1]).upper()
            
            # Busca na planilha
            from services.sheets import buscar_produto_por_nome_ou_id
            produtos_encontrados = buscar_produto_por_nome_ou_id(planilha_id, termo_busca)
            
            if len(produtos_encontrados) == 0:
                res.message(f"❌ Nenhum produto encontrado com o nome ou ID: *{termo_busca}*")
                return str(res)
                
            elif len(produtos_encontrados) > 1:
                # AMBIGUIDADE: Mostra as opções e pede para o usuário usar o ID
                msg_ambigua = f"⚠️ Encontramos mais de um produto contendo *{termo_busca}*.\nPara evitar erros, repita a operação usando o *ID* do produto correto:\n\n"
                for p in produtos_encontrados:
                    msg_ambigua += f"🔹 {p['nome']} -> ID: *{p['ref']}*\n"
                
                msg_ambigua += f"\nExemplo: `{comando} {produtos_encontrados[0]['ref']} {qtd}`"
                res.message(msg_ambigua)
                return str(res)
            
            # Se encontrou exatamente 1 produto, pega a referência exata e segue o fluxo normal
            ref_exata = produtos_encontrados[0]['ref']
            
            dados_manuais = {'referencia': ref_exata, 'quantidade': qtd, 'peso': 0}
            tipo_op = 'ENTRADA' if comando == "entrada" else 'SAIDA'
            
            log = salvar_no_banco(dados_manuais, client_id, planilha_id, tipo_operacao=tipo_op)

            if log.get('erro'):
                res.message(f"❌ *Operação Negada:*\n{log['erro']}")
                return str(res)
                
            atualizar_sheets(dados_manuais, log['total'], planilha_id)

            alerta, produto_alerta, qtd_atual = verificar_alerta_minimo(planilha_id, ref_exata)

            if alerta:
                msg_alerta = f"⚠️ *ALERTA DE ESTOQUE BAIXO*\n\nO produto *{produto_alerta}* atingiu {qtd_atual} unidades. Sugerimos reposição!"
                enviar_whatsapp(numero_usuario, msg_alerta)
            
            acao = "Adicionadas" if tipo_op == 'ENTRADA' else "Removidas"
            res.message(f"✅ *{tipo_op.capitalize()} Manual Registrada!*\n\n📦 Ref: {log['product_id']}\n⚖️ {qtd} unidades {acao}.\n📊 Novo Saldo: {log['total']}")
            
        else:
            comando_tentado = partes[0].lower() if len(partes) > 0 else "comando"
            res.message(f"❌ Formato incorreto. Use: `{comando_tentado} [NOME OU ID] [QTD]`")
        
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

    # --- COMANDO DE CONSULTA DE ESTOQUE ---
    comando_estoque = corpo_mensagem.lower().strip()
    
    if comando_estoque in ["estoque", "estóque"]:
        from services.sheets import consultar_estoque_geral
        relatorio = consultar_estoque_geral(planilha_id)
        res.message(relatorio)
        return str(res)
    
    
    res.message("👋 Olá, Bem vindo a OptiScan, para mais informações, digite 'ajuda'.")
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
    try:
        # Garante o prefixo
        remetente = TWILIO_NUMBER if TWILIO_NUMBER.startswith('whatsapp:') else f"whatsapp:{TWILIO_NUMBER}"
        destinatario = para if para.startswith('whatsapp:') else f"whatsapp:{para}"
        
        print(f"⏳ Tentando enviar mensagem de {remetente} para {destinatario}...")
        
        mensagem = twilio_client.messages.create(
            body=texto,
            from_=remetente,
            to=destinatario
        )
        print(f"✅ Mensagem enviada com sucesso! SID do Twilio: {mensagem.sid}")
        
    except Exception as e:
        print(f"🚨 ERRO CRÍTICO NO ENVIO TWILIO: {str(e)}")

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
    
@app.route('/alerta-planilha', methods=['POST'])
def alerta_planilha():
    dados = request.json
    produto = dados.get('produto')
    quantidade = dados.get('quantidade')
    
    msg_alerta = f"⚠️ *ALERTA DE ESTOQUE BAIXO*\n\nO produto *{produto}* atingiu {quantidade} unidades devido a uma movimentação na planilha. Sugerimos reposição!"
    
    # Chama sua função do Twilio/Meta para enviar a mensagem
    enviar_whatsapp(os.getenv('ADMIN_NUMBER') , msg_alerta)
    
    return jsonify({"status": "Alerta enviado"}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)