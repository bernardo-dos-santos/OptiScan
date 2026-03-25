import threading
from services.meta import enviar_mensagem_meta, baixar_imagem_meta
from services.leitor import analisar_imagem
from services.banco import salvar_no_banco
from services.sheets import atualizar_sheets
from services.uteis import formatar_br

def tratar_fluxo_imagem(media_id, telefone_remetente, cliente, legenda):
    enviar_mensagem_meta(telefone_remetente, "📸 Imagem recebida. Analisando...")
    img_data = baixar_imagem_meta(media_id)
    
    if not img_data:
        enviar_mensagem_meta(telefone_remetente, "❌ Falha ao baixar o arquivo da Meta.")
        return

    client_id = cliente['id']
    planilha_id = cliente['planilha_id']
    contexto_ia = cliente.get('contexto_ia', '')

    try:
        dados_extraidos = analisar_imagem(img_data, contexto_cliente=contexto_ia, legenda=legenda)
        
        if not dados_extraidos or dados_extraidos.get('referencia') == 'ITEM_DESCONHECIDO':
            enviar_mensagem_meta(telefone_remetente, "❌ Não consegui ler os dados do produto nesta foto. Tente um ângulo melhor.")
            return

        legenda_lower = legenda.lower()
        tipo_op = 'SAIDA' if any(p in legenda_lower for p in ['saiu', 'saida', 'saída', 'menos', 'tirar']) else 'ENTRADA'

        log = salvar_no_banco(dados_extraidos, client_id, planilha_id, tipo_operacao=tipo_op)

        if 'erro' in log:
            enviar_mensagem_meta(telefone_remetente, f"⚠️ {log['erro']}")
            return
        
        atualizar_sheets(dados_extraidos, log['total'], planilha_id)
        
        nome_prod = dados_extraidos.get('nome', 'Produto')
        espec = dados_extraidos.get('especificacao', 'N/A')
        titulo_msg = "Entrada Registrada" if tipo_op == 'ENTRADA' else "Saída Registrada"
        
        msg = (f"✅ *{titulo_msg}!*\n\n"
               f"📦 *Produto:* {nome_prod}\n"
               f"🔧 *Spec:* {espec}\n"
               f"🔢 *Ref:* {log['product_id']}\n"
               f"📊 *Estoque Atual:* {formatar_br(log['total'])}\n\n"
               f"Para reverter, digite 'Corrigir'")
               
        enviar_mensagem_meta(telefone_remetente, msg)

    except Exception as e:
        enviar_mensagem_meta(telefone_remetente, f"⚠️ Erro interno no sistema de IA: {str(e)}")