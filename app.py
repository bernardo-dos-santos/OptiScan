import os
import threading
import hmac
import hashlib
import requests
import pytz
from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Importações dos seus serviços
from services.banco import (
    get_conexao, salvar_no_banco, executar_estorno_banco, 
    buscar_cliente_por_whatsapp, atualizar_estoque_via_webhook, admin_cadastrar_cliente
)
from services.leitor import analisar_imagem
from services.analista import rodar_analise_preditiva
from services.sheets import (
    atualizar_sheets, verificar_alerta_minimo, 
    consultar_estoque_geral, buscar_produto_por_nome_ou_id
    
)

load_dotenv()
app = Flask(__name__)

# --- CONFIGURAÇÕES GERAIS ---
META_TOKEN = os.getenv('META_ACCESS_TOKEN')
META_PHONE_ID = os.getenv('META_PHONE_ID')
VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')
APP_SECRET = os.getenv('META_APP_SECRET')
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')

# --- FUNÇÕES DE COMUNICAÇÃO META ---

def enviar_mensagem_meta(para_numero, texto):
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": para_numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        resposta = requests.post(url, headers=headers, json=data)
        print(f"▶️ Status Meta: {resposta.status_code} | Resposta: {resposta.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro fatal ao conectar na Meta: {e}", flush=True)

def baixar_imagem_meta(media_id):
    url_info = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    try:
        res_info = requests.get(url_info, headers=headers)
        if res_info.status_code != 200: return None
        url_download = res_info.json().get('url')
        
        res_file = requests.get(url_download, headers=headers)
        return res_file.content if res_file.status_code == 200 else None
    except Exception as e:
        print(f"Erro no download da imagem: {e}", flush=True)
        return None

# --- SEGURANÇA ---

def validar_assinatura_meta(payload, signature):
    if not APP_SECRET or not signature: return True
    expected_sig = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected_sig}", signature)

# --- PROCESSAMENTO EM SEGUNDO PLANO ---

def processar_imagem_background(img_data, numero_usuario, client_id, planilha_id, contexto_ia=""):
    try:
        dados_extraidos = analisar_imagem(img_data, contexto_cliente=contexto_ia)
     
        
        if not dados_extraidos or dados_extraidos.get('referencia') == 'ITEM_DESCONHECIDO':
            enviar_mensagem_meta(numero_usuario, "❌ Não consegui ler os dados do produto nesta foto. Tente um ângulo melhor.")
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
               
        enviar_mensagem_meta(numero_usuario, msg)

    except Exception as e:
        enviar_mensagem_meta(numero_usuario, f"⚠️ Erro interno no sistema de IA: {str(e)}")

# --- WEBHOOK PRINCIPAL (WHATSAPP) ---

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_meta():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        return 'Token invalido', 403
            
    elif request.method == 'POST':
        signature = request.headers.get('X-Hub-Signature-256')
        if not validar_assinatura_meta(request.data, signature):
            abort(403)

        body = request.json
        if body and body.get('object') == 'whatsapp_business_account':
            for entry in body.get('entry', []):
                for change in entry.get('changes', []):
                    # CORREÇÃO CRÍTICA AQUI: Nome da variável alterado para evitar erro de alocação de memória (UnboundLocalError)
                    dados_meta = change.get('value', {})
                    
                    if 'messages' in dados_meta:
                        mensagem = dados_meta['messages'][0]
                        telefone_remetente = mensagem['from']
                        print(f"📩 Mensagem recebida de: {telefone_remetente}", flush=True)
                        
                        # --- TRATAMENTO DE IMAGEM ---
                        if mensagem['type'] == 'image':
                            cliente = buscar_cliente_por_whatsapp(telefone_remetente)
                            if not cliente:
                                enviar_mensagem_meta(telefone_remetente, "❌ Número não registrado no sistema OptiScan.")
                                return 'OK', 200
                                
                            media_id = mensagem['image']['id']
                            enviar_mensagem_meta(telefone_remetente, "📸 Imagem recebida. Analisando...")
                            img_data = baixar_imagem_meta(media_id)
                            
                            if img_data:
                                threading.Thread(
                                    target=processar_imagem_background,
                                    args=(img_data, telefone_remetente, cliente['id'], cliente['planilha_id'], cliente.get('contexto_ia', ''))
                                ).start()
                            else:
                                enviar_mensagem_meta(telefone_remetente, "❌ Falha ao baixar o arquivo da Meta.")
                            return 'OK', 200

                        # --- TRATAMENTO DE TEXTO ---
                        if mensagem['type'] == 'text':
                            corpo_mensagem = mensagem['text']['body'].lower().strip()
                            corpo_mensagem_original = mensagem['text']['body'].strip()
                            
                            # 1. Comando de Admin
                            if telefone_remetente == ADMIN_NUMBER and corpo_mensagem.startswith('admin_add'):
                                partes = corpo_mensagem_original.split()
                                if len(partes) >= 4:
                                    nome_empresa = partes[1].replace('_', ' ')
                                    zap_novo = partes[2]
                                    planilha_nova = partes[3]
                                    novo_id = admin_cadastrar_cliente(nome_empresa, zap_novo, planilha_nova)
                                    if novo_id:
                                        enviar_mensagem_meta(telefone_remetente, f"✅ *Cliente {nome_empresa} Cadastrado!*\nID: {novo_id}")
                                    else:
                                        enviar_mensagem_meta(telefone_remetente, "❌ Erro ao cadastrar. Verifique o banco de dados.")
                                return 'OK', 200
                            
                            # Validação de Cliente
                            cliente = buscar_cliente_por_whatsapp(telefone_remetente)
                            if not cliente:
                                enviar_mensagem_meta(telefone_remetente, "❌ Número não reconhecido. Contate o suporte da OptiScan.")
                                return 'OK', 200
                                
                            client_id = cliente['id']
                            planilha_id = cliente['planilha_id']

                            # 2. Comando de Correção
                            if corpo_mensagem == "corrigir":
                                resultado = executar_estorno_banco(client_id, planilha_id)
                                if resultado:
                                    acao = "Removidas" if resultado['acao_desfeita'] == 'ENTRADA' else "Adicionadas"
                                    enviar_mensagem_meta(telefone_remetente, f"🔄 *Estornado com sucesso!*\n\n📦 Ref: {resultado['product_id']}\n⚖️ {resultado['estornado']} unidades {acao}.\n📊 Novo Saldo: {resultado['total']}")
                                else:
                                    enviar_mensagem_meta(telefone_remetente, "❌ Nenhum registro recente para desfazer.")
                                return 'OK', 200

                            # 3. Comandos de Consulta
                            if corpo_mensagem in ["estoque", "estóque"]:
                                enviar_mensagem_meta(telefone_remetente, consultar_estoque_geral(planilha_id))
                                return 'OK', 200

                            # 4. Comandos Manuais (Entrada / Saída)
                            if corpo_mensagem.startswith(("entrada", "saida", "saída")):
                                partes = corpo_mensagem.split()
                                if len(partes) >= 3:
                                    comando = partes[0].replace('í', 'i').lower()
                                    try:
                                        qtd = float(partes[-1].replace(',', '.'))
                                    except ValueError:
                                        enviar_mensagem_meta(telefone_remetente, "❌ Erro: O *último* termo deve ser a quantidade.")
                                        return 'OK', 200
                                    
                                    termo_busca = " ".join(partes[1:-1]).upper()
                                    produtos_encontrados = buscar_produto_por_nome_ou_id(planilha_id, termo_busca)
                                    
                                    if not produtos_encontrados:
                                        enviar_mensagem_meta(telefone_remetente, f"❌ Produto não encontrado: *{termo_busca}*")
                                        return 'OK', 200
                                        
                                    elif len(produtos_encontrados) > 1:
                                        msg_ambigua = f"⚠️ Múltiplos produtos com *{termo_busca}*. Use o ID correto:\n\n"
                                        for p in produtos_encontrados:
                                            msg_ambigua += f"🔹 {p['nome']} -> ID: *{p['ref']}*\n"
                                        enviar_mensagem_meta(telefone_remetente, msg_ambigua)
                                        return 'OK', 200
                                    
                                    ref_exata = produtos_encontrados[0]['ref']
                                    dados_manuais = {'referencia': ref_exata, 'nome': produtos_encontrados[0]['nome'], 'quantidade': qtd, 'peso': 0}
                                    tipo_op = 'ENTRADA' if comando == "entrada" else 'SAIDA'
                                    
                                    log = salvar_no_banco(dados_manuais, client_id, planilha_id, tipo_operacao=tipo_op)
                                    if log.get('erro'):
                                        enviar_mensagem_meta(telefone_remetente, f"❌ *Negado:*\n{log['erro']}")
                                        return 'OK', 200
                                        
                                    atualizar_sheets(dados_manuais, log['total'], planilha_id)
                                                  
                                    acao = "Adicionadas" if tipo_op == 'ENTRADA' else "Removidas"
                                    enviar_mensagem_meta(telefone_remetente, f"✅ *{tipo_op.capitalize()} Manual Registrada!*\n\n📦 Ref: {log['product_id']}\n⚖️ {qtd} unidades {acao}.\n📊 Novo Saldo: {log['total']}")
                                else:
                                    enviar_mensagem_meta(telefone_remetente, "❌ Use: `entrada/saida [NOME OU ID] [QTD]`")
                                return 'OK', 200

                            # Fallback (Texto Livre)
                            enviar_mensagem_meta(telefone_remetente, "👋 OptiScan Online. Envie uma foto do produto, digite 'estoque' ou use comandos manuais.")

        return 'EVENT_RECEIVED', 200

# --- ROTAS DE PLANILHA E ALERTAS ---

@app.route("/webhook_planilha", methods=['POST'])
def webhook_planilha():
    if request.headers.get('x-api-key') != os.getenv('WEBHOOK_SECRET'):
        return "Não autorizado", 403
    dados = request.json
    if not dados: return "Sem dados", 400
    try:
        atualizar_estoque_via_webhook(dados.get('client_id'), str(dados.get('referencia')), float(dados.get('quantidade')))
        return "Atualizado no banco", 200
    except Exception as e:
        return str(e), 500
    
@app.route('/alerta-planilha', methods=['POST'])
def alerta_planilha():
    dados = request.json
    enviar_mensagem_meta(ADMIN_NUMBER, f"⚠️ *ALERTA DE ESTOQUE BAIXO*\n\nO produto *{dados.get('produto')}* atingiu {dados.get('quantidade')} unidades.")
    return jsonify({"status": "Alerta enviado"}), 200

def enviar_resumo_turno():
    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.whatsapp, e.product_id, e.nome, e.quantity, e.estoque_minimo
        FROM estoque e
        JOIN clientes c ON e.client_id = c.id
        WHERE e.quantity <= e.estoque_minimo AND e.estoque_minimo > 0
        ORDER BY c.whatsapp, e.nome;
    """)
    itens_criticos = cursor.fetchall()
    cursor.close()
    conn.close()

    if not itens_criticos: return 

    alertas_por_cliente = {}
    for whatsapp, product_id, nome, qtd, minimo in itens_criticos:
        if whatsapp not in alertas_por_cliente: alertas_por_cliente[whatsapp] = []
        alertas_por_cliente[whatsapp].append(f"🔹 *{nome}* (ID: {product_id})\n   Restam: {qtd} | Mín.: {minimo}")

    for whatsapp, itens in alertas_por_cliente.items():
        lista_itens = "\n\n".join(itens)
        enviar_mensagem_meta(whatsapp, f"⚠️ *OPTISCAN - RESUMO DE ESTOQUE DIÁRIO* ⚠️\n\nOs seguintes itens atingiram o nível crítico:\n\n{lista_itens}\n\nTotal a repor: {len(itens)}")

scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Sao_Paulo'))
scheduler.add_job(enviar_resumo_turno, 'cron', hour='18', minute='15')
scheduler.add_job(func=rodar_analise_preditiva, trigger="cron", hour=3, minute=0)
scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))