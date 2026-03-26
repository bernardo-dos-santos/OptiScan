import os
import threading
from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from services.meta import validar_assinatura_meta, enviar_mensagem_meta
from services.banco import get_conexao, buscar_cliente_por_whatsapp, atualizar_estoque_via_webhook
from services.analista import rodar_analise_preditiva
from services.uteis import formatar_br
from handlers.messages import tratar_comando_texto
from handlers.images import tratar_fluxo_imagem

load_dotenv()
app = Flask(__name__)

VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')

# --- SCHEDULER / TAREFAS DE FUNDO ---
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
        alertas_por_cliente[whatsapp].append(f"🔹 *{nome}* (ID: {product_id})\n   Restam: {formatar_br(qtd)} | Mín.: {formatar_br(minimo)}")

    for whatsapp, itens in alertas_por_cliente.items():
        lista_itens = "\n\n".join(itens)
        enviar_mensagem_meta(whatsapp, f"⚠️ *OPTISCAN - RESUMO DE ESTOQUE* ⚠️\n\nOs seguintes itens atingiram o nível crítico hoje:\n\n{lista_itens}\n\nTotal a repor: {formatar_br(len(itens))}")

scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Sao_Paulo'))
scheduler.add_job(enviar_resumo_turno, 'cron', hour='18', minute='0')
scheduler.add_job(rodar_analise_preditiva, 'cron', day_of_week='mon', hour=9, minute=0)
scheduler.start()

# --- ROTAS ---
@app.route('/')
def home():
    return "OptiScan Online", 200

@app.route('/webhook_planilha', methods=['POST'])
def webhook_planilha():
    dados = request.json
    sheet_id = dados.get('sheet_id')
    ref = dados.get('referencia')
    nome = dados.get('nome', 'Sem Nome')
    especificacao = dados.get('especificacao', '') # <-- RECEBE A ESPECIFICAÇÃO
    qtd = dados.get('quantidade')
    estoque_minimo = dados.get('estoque_minimo', 0)

    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE planilha_id = %s", (sheet_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()

    if resultado:
        client_id = resultado[0]
        # Adicione o parâmetro especificacao aqui na chamada:
        atualizar_estoque_via_webhook(client_id, ref, nome, qtd, estoque_minimo, especificacao) 
        return jsonify({"status": "sucesso"}), 200
    return jsonify({"status": "cliente_nao_encontrado"}), 404


@app.route('/webhook_sincronizacao_geral', methods=['POST'])
def webhook_sincronizacao_geral():
    dados = request.json
    sheet_id = dados.get('sheet_id')
    produtos = dados.get('produtos', [])

    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM clientes WHERE planilha_id = %s", (sheet_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()

    if resultado:
        client_id = resultado[0]
        sincronizacao_geral_banco(client_id, produtos)
        return jsonify({"status": "sucesso"}), 200
    return jsonify({"status": "cliente_nao_encontrado"}), 404

@app.route('/webhook_excluir', methods=['POST'])
def webhook_excluir():
    dados = request.json
    sheet_id = dados.get('sheet_id')
    ref = dados.get('referencia')

    conn = get_conexao()
    cursor = conn.cursor()
    
    # Descobre quem é o cliente dono dessa planilha
    cursor.execute("SELECT id FROM clientes WHERE planilha_id = %s", (sheet_id,))
    resultado = cursor.fetchone()

    if resultado:
        client_id = resultado[0]
        # Deleta permanentemente o produto do banco de dados deste cliente
        cursor.execute("DELETE FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "sucesso"}), 200

    cursor.close()
    conn.close()
    return jsonify({"status": "cliente_nao_encontrado"}), 404
    
@app.route('/alerta-planilha', methods=['POST'])
def alerta_planilha():
    dados = request.json
    enviar_mensagem_meta(ADMIN_NUMBER, f"⚠️ *ALERTA DE ESTOQUE BAIXO*\n\nO produto *{dados.get('produto')}* atingiu {formatar_br(dados.get('quantidade'))} unidades.")
    return jsonify({"status": "Alerta enviado"}), 200

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
            try:
                for entry in body.get('entry', []):
                    for change in entry.get('changes', []):
                        dados_meta = change.get('value', {})
                        if 'messages' in dados_meta:
                            mensagem = dados_meta['messages'][0]
                            telefone_remetente = mensagem['from']
                            tipo = mensagem['type']

                            cliente = buscar_cliente_por_whatsapp(telefone_remetente)

                            if tipo == 'text':
                                tratar_comando_texto(telefone_remetente, mensagem['text']['body'], cliente)
                                
                            elif tipo == 'image':
                                if not cliente:
                                    enviar_mensagem_meta(telefone_remetente, "❌ Número não registrado no sistema OptiScan.")
                                    return 'OK', 200
                                
                                media_id = mensagem['image']['id']
                                legenda = mensagem['image'].get('caption', '').strip()
                                threading.Thread(
                                    target=tratar_fluxo_imagem, 
                                    args=(media_id, telefone_remetente, cliente, legenda)
                                ).start()
                                
                            elif tipo not in ['image', 'text']:
                                enviar_mensagem_meta(telefone_remetente, "🤖 Ops! Apenas texto ou fotos da etiqueta.")
            except Exception as e:
                print(f"Erro no parse do webhook: {e}", flush=True)
                
        return 'EVENT_RECEIVED', 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))