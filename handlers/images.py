import threading
from services.meta import enviar_mensagem_meta, baixar_imagem_meta
from services.leitor import analisar_imagem, analisar_pdf_nf
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

def tratar_fluxo_pdf(media_id, telefone_remetente, cliente):
    enviar_mensagem_meta(telefone_remetente, "📄 PDF da Nota Fiscal recebido. A Inteligência Artificial está a analisar os emissores e produtos...")
    
    pdf_data = baixar_imagem_meta(media_id) 
    if not pdf_data:
        enviar_mensagem_meta(telefone_remetente, "❌ Falha ao descarregar o ficheiro PDF.")
        return

    client_id = cliente['id']
    planilha_id = cliente['planilha_id']
    cnpj_cliente = cliente.get('cnpj')

    if not cnpj_cliente:
        enviar_mensagem_meta(telefone_remetente, "⚠️ O CNPJ da sua empresa não está registado. Peça ao administrador para atualizar o seu registo para processar PDFs.")
        return

    try:
        resultado_ia = analisar_pdf_nf(pdf_data, cnpj_cliente)
        
        if not resultado_ia or 'produtos' not in resultado_ia or len(resultado_ia['produtos']) == 0:
            enviar_mensagem_meta(telefone_remetente, "❌ Não consegui encontrar produtos válidos nesta Nota Fiscal.")
            return

        tipo_op = resultado_ia['tipo_operacao']
        lista_produtos = resultado_ia['produtos']

        sucessos = 0
        produtos_sem_cadastro = [] # <-- 1. Criamos a lista para guardar os alertas

        for prod in lista_produtos:
            log = salvar_no_banco(prod, client_id, planilha_id, tipo_operacao=tipo_op)
            
            if 'erro' not in log:
                atualizar_sheets(prod, log['total'], planilha_id)
                sucessos += 1
                
                # 2. Se o banco sinalizou que o stock ficou negativo, guardamos o nome
                if log.get('aviso_venda'):
                    nome_item = log.get('nome') or prod.get('nome', 'Item Desconhecido')
                    produtos_sem_cadastro.append(nome_item)
        
        acao_texto = "adicionados ao" if tipo_op == 'ENTRADA' else "debitados do"
        msg_final = f"✅ *Operação Identificada: {tipo_op}*\n📦 {sucessos} itens da NF foram {acao_texto} stock com sucesso."

        # 3. Anexamos o alerta na mensagem final do WhatsApp se houver itens na lista
        if produtos_sem_cadastro:
            msg_final += "\n\n⚠️ *ALERTA DE STOCK:* \nOs itens abaixo foram vendidos, mas o stock ficou *negativo* (ou não existiam no sistema). Lembre-se de registar as notas de entrada deles:\n"
            # O set() remove itens duplicados caso a nota tenha o mesmo produto 2 vezes
            for p in set(produtos_sem_cadastro):
                msg_final += f" - {p}\n"

        enviar_mensagem_meta(telefone_remetente, msg_final)
        
    except Exception as e:
        print(f"Erro ao tratar PDF: {e}")
        enviar_mensagem_meta(telefone_remetente, "❌ Ocorreu um erro interno ao processar a Nota Fiscal.")