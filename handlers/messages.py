import os
from datetime import datetime, timedelta
from services.meta import enviar_mensagem_meta, enviar_template_meta
from services.banco import admin_adicionar_numero_por_id, admin_listar_clientes, gerar_relatorio_financeiro, get_conexao, executar_estorno_banco, salvar_no_banco, admin_cadastrar_cliente
from services.sheets import consultar_estoque_geral, buscar_produto_por_nome_ou_id, atualizar_sheets
from services.uteis import formatar_br, tratar_numero_brasileiro

ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')

def tratar_comando_texto(telefone_remetente, corpo_mensagem_original, cliente):
    corpo_mensagem = corpo_mensagem_original.lower().strip()
    
    # 1. COMANDOS ADMIN
    if corpo_mensagem.startswith('!'):
        if telefone_remetente != ADMIN_NUMBER:
            enviar_mensagem_meta(telefone_remetente, "⛔ Comando restrito a administradores.")
            return

        if corpo_mensagem.startswith('!cadastrar'):
            partes = corpo_mensagem_original.split(" ", 4)
            if len(partes) < 4:
                enviar_mensagem_meta(telefone_remetente, "❌ Formato incorreto. Use: !cadastrar 554999999999 NomeEmpresa ID_PLANILHA [Contexto IA opcional]")
                return
            
            numero_novo, nome_empresa, planilha_nova = partes[1], partes[2], partes[3]
            contexto_ia = partes[4] if len(partes) == 5 else ""
            
            if admin_cadastrar_cliente(nome_empresa, numero_novo, planilha_nova, contexto_ia):
                enviar_mensagem_meta(telefone_remetente, f"✅ Cliente {nome_empresa} salvo com sucesso!")
                link_planilha = f"https://docs.google.com/spreadsheets/d/{planilha_nova}/edit"
                enviar_template_meta(numero_novo, "boas_vindas_optiscan", link_planilha)
            else:
                enviar_mensagem_meta(telefone_remetente, "❌ Falha ao gravar no banco.")
            return

        elif corpo_mensagem == '!status':
            msg_status = "🟢 *OPTISCAN STATUS* 🟢\n\n"
            try:
                conn = get_conexao()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                msg_status += "✅ Banco de Dados: Online\n"
                
                cursor.execute("SELECT COUNT(*) FROM clientes")
                msg_status += f"👥 Clientes Ativos: {cursor.fetchone()[0]}\n"
                
                cursor.execute("SELECT COUNT(*) FROM historico WHERE DATE(data) = CURRENT_DATE")
                msg_status += f"📊 Movimentações Hoje: {cursor.fetchone()[0]}\n"
                
                cursor.close()
                conn.close()
            except Exception as e:
                msg_status += f"❌ Banco de Dados: FALHA\n_{e}_\n"
            
            agora = (datetime.utcnow() - timedelta(hours=3)).strftime('%d/%m/%Y %H:%M:%S')
            msg_status += f"\n⏱️ Servidor: {agora}\n✅ Webhook Meta: Ativo\n"
            enviar_mensagem_meta(telefone_remetente, msg_status)
            return
        elif corpo_mensagem == '!lista':
            msg_lista = admin_listar_clientes()
            enviar_mensagem_meta(telefone_remetente, msg_lista)
            return
            
            # COMANDO: !add
        elif corpo_mensagem.startswith('!add '):
            partes = corpo_mensagem_original.split(" ")
            if len(partes) < 3:
                enviar_mensagem_meta(telefone_remetente, "❌ Formato: !add <NUMERO_NOVO> <ID_EMPRESA>")
                return
                
            novo_numero = partes[1]
            try:
                id_empresa = int(partes[2])
            except ValueError:
                enviar_mensagem_meta(telefone_remetente, "❌ O ID da empresa precisa ser um número.")
                return
                
            sucesso = admin_adicionar_numero_por_id(novo_numero, id_empresa)
            
            if sucesso:
                enviar_mensagem_meta(telefone_remetente, f"✅ Número {novo_numero} vinculado à empresa ID {id_empresa} com sucesso!")
            else:
                enviar_mensagem_meta(telefone_remetente, "❌ Erro: Empresa não encontrada no banco de dados.")
            return
        
    # 2. COMANDOS DO CLIENTE (Dono ou Estoquista acessam)

    if not cliente:
        enviar_mensagem_meta(telefone_remetente, "❌ Número não registrado no sistema OptiScan.")
        return

    if corpo_mensagem == "#financeiro":
        faturamento, custos = gerar_relatorio_financeiro(client_id)
        lucro_bruto = faturamento - custos
        
        msg_fin = (
            "📊 *Resumo Financeiro (Mês Atual)* 📊\n\n"
            f"📈 *Faturamento (Saídas):* R$ {faturamento:,.2f}\n"
            f"📉 *Custos de Reposição (Entradas):* R$ {custos:,.2f}\n"
            "------------------------\n"
            f"💰 *Resultado Operacional:* R$ {lucro_bruto:,.2f}"
        )
        msg_fin = msg_fin.replace(',', 'X').replace('.', ',').replace('X', '.') 
        enviar_mensagem_meta(telefone_remetente, msg_fin)
        return

    # 2. COMANDOS DE USUÁRIO
    client_id = cliente['id']
    planilha_id = cliente['planilha_id']

    if corpo_mensagem == "corrigir":
        resultado = executar_estorno_banco(client_id, planilha_id)
        if resultado:
            acao = "Removidas" if resultado['acao_desfeita'] == 'ENTRADA' else "Adicionadas"
            enviar_mensagem_meta(telefone_remetente, f"🔄 *Estornado com sucesso!*\n\n📦 Ref: {resultado['product_id']}\n⚖️ {formatar_br(resultado['estornado'])} unidades {acao}.\n📊 Novo Saldo: {formatar_br(resultado['total'])}")
        else:
            enviar_mensagem_meta(telefone_remetente, "❌ Nenhum registro recente para desfazer.")
        return
    
    if corpo_mensagem == "!financeiro":
        faturamento, custos = gerar_relatorio_financeiro(client_id)
        lucro_bruto = faturamento - custos
        
        msg_fin = (
            "📊 *Resumo Financeiro (Mês Atual)* 📊\n\n"
            f"📈 *Faturamento (Saídas):* R$ {faturamento:,.2f}\n"
            f"📉 *Custos de Reposição (Entradas):* R$ {custos:,.2f}\n"
            "------------------------\n"
            f"💰 *Resultado Operacional:* R$ {lucro_bruto:,.2f}"
        )
        msg_fin = msg_fin.replace(',', 'X').replace('.', ',').replace('X', '.') # Ajuste de pontuação BR
        enviar_mensagem_meta(telefone_remetente, msg_fin)
        return

    if corpo_mensagem in ["estoque", "estóque"]:
        enviar_mensagem_meta(telefone_remetente, consultar_estoque_geral(planilha_id))
        return

    # 3. ENTRADA / SAÍDA MANUAL (COM O TRATAMENTO BRASILEIRO)
    if corpo_mensagem.startswith(("entrada", "saida", "saída")):
        partes = corpo_mensagem_original.split()
        if len(partes) >= 3:
            comando = partes[0].replace('í', 'i').lower()
            try:
                qtd = tratar_numero_brasileiro(partes[-1])
            except ValueError:
                enviar_mensagem_meta(telefone_remetente, "❌ Erro: O *último* termo deve ser a quantidade.")
                return
            
            termo_busca = " ".join(partes[1:-1]).upper()
            produtos_encontrados = buscar_produto_por_nome_ou_id(planilha_id, termo_busca)
            
            if not produtos_encontrados:
                enviar_mensagem_meta(telefone_remetente, f"❌ Produto não encontrado: *{termo_busca}*")
                return
                
            elif len(produtos_encontrados) > 1:
                msg_ambigua = f"⚠️ Múltiplos produtos com *{termo_busca}*. Use o ID correto:\n\n"
                for p in produtos_encontrados:
                    msg_ambigua += f"🔹 {p['nome']} -> ID: *{p['ref']}*\n"
                enviar_mensagem_meta(telefone_remetente, msg_ambigua)
                return
            
            ref_exata = produtos_encontrados[0]['ref']
            dados_manuais = {'referencia': ref_exata, 'nome': produtos_encontrados[0]['nome'], 'quantidade': qtd, 'peso': 0}
            tipo_op = 'ENTRADA' if comando == "entrada" else 'SAIDA'
            
            log = salvar_no_banco(dados_manuais, client_id, planilha_id, tipo_operacao=tipo_op)
            
            if 'erro' in log:
                enviar_mensagem_meta(telefone_remetente, f"❌ *Negado:*\n{log['erro']}")
                return
                
            atualizar_sheets(dados_manuais, log['total'], planilha_id)
            acao = "Adicionadas" if tipo_op == 'ENTRADA' else "Removidas"
            enviar_mensagem_meta(telefone_remetente, f"✅ *{tipo_op.capitalize()} Manual Registrada!*\n\n📦 Ref: {log['product_id']}\n⚖️ {formatar_br(qtd)} unidades {acao}.\n📊 Novo Saldo: {formatar_br(log['total'])}")
            return
        else: 
            enviar_mensagem_meta(telefone_remetente, "❌ Use: `entrada/saida [NOME OU ID] [QTD]`")
            return

    # Fallback
    enviar_mensagem_meta(telefone_remetente, "👋 OptiScan Online. Envie uma foto da etiqueta, digite 'estoque' ou use comandos manuais.")
    