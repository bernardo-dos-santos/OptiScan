import os
import psycopg2
from datetime import datetime, timedelta
from services.sheets import atualizar_sheets
from services.uteis import tratar_numero_brasileiro

def get_conexao():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        port=os.getenv('DB_PORT', 5432)
    )

def salvar_no_banco(dados, client_id, planilha_id, tipo_operacao='ENTRADA'):
    ref = str(dados.get('referencia', 'ITEM_DESCONHECIDO')).upper()
    nome_recebido = dados.get('nome')
    espec_recebida = dados.get('especificacao')
    
    # ---> ESTA É A LINHA QUE FALTAVA <---
    custo_recebido = float(dados.get('custo_unitario', 0.0)) 
    
    try:
        from services.uteis import tratar_numero_brasileiro
        qtd_movimento = tratar_numero_brasileiro(dados.get('quantidade', 1))
    except Exception:
        qtd_movimento = 1.0

    conn = get_conexao()
    cursor = conn.cursor()
    agora = datetime.utcnow() - timedelta(hours=3)

    # 1. Busca o saldo E os dados financeiros (Custo e Preço)
    cursor.execute("SELECT quantity, nome, especificacao, custo_unitario, preco_venda FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    resultado = cursor.fetchone()

    if resultado:
        qtd_atual = float(resultado[0])
        nome_atual = resultado[1] if resultado[1] else nome_recebido
        espec_atual = resultado[2] if resultado[2] else espec_recebida
        
        # Se a nota fiscal trouxe um custo novo, atualiza. Se não, mantém o que já estava.
        custo_unitario = custo_recebido if custo_recebido > 0 else float(resultado[3])
        preco_venda = float(resultado[4]) if resultado[4] else 0.0
        
        if tipo_operacao == 'ENTRADA':
            nova_qtd = qtd_atual + qtd_movimento
            valor_movimento = qtd_movimento * custo_unitario # Registra Despesa
        else:
            if qtd_atual < qtd_movimento:
                return {'erro': f'Estoque insuficiente. Saldo atual: {qtd_atual}'}
            nova_qtd = qtd_atual - qtd_movimento
            valor_movimento = qtd_movimento * preco_venda # Registra Faturamento

        cursor.execute("""
            UPDATE estoque 
            SET quantity = %s, ultima_atualizacao = %s, nome = %s, especificacao = %s, custo_unitario = %s
            WHERE product_id = %s AND client_id = %s
        """, (nova_qtd, agora, nome_atual, espec_atual, custo_unitario, ref, client_id))

    else:
        if tipo_operacao == 'SAIDA':
            return {'erro': 'Produto não existe no estoque para saída.'}
        
        nova_qtd = qtd_movimento
        nome_atual = nome_recebido if nome_recebido else "Item Novo"
        espec_atual = espec_recebida if espec_recebida else ""
        custo_unitario = custo_recebido
        preco_venda = 0.0
        valor_movimento = qtd_movimento * custo_unitario

        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, nome, quantity, especificacao, ultima_atualizacao, custo_unitario, preco_venda) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (client_id, ref, nome_atual, nova_qtd, espec_atual, agora, custo_unitario, preco_venda))

    # 2. Inserção no histórico com a conversão financeira
    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data, valor_total) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (client_id, ref, qtd_movimento, tipo_operacao, agora, valor_movimento))

    conn.commit()
    cursor.close()
    conn.close()

    return {'status': 'sucesso', 'product_id': ref, 'total': nova_qtd}

def executar_estorno_banco(client_id, planilha_id):
    conn = get_conexao()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_id, quantidade, tipo FROM historico 
        WHERE client_id = %s AND tipo IN ('ENTRADA', 'SAIDA')
        ORDER BY id DESC LIMIT 1
    """, (client_id,))
    
    ultima_transacao = cursor.fetchone()
    if not ultima_transacao:
        conn.close()
        return None

    ref, qtd_ia, tipo = ultima_transacao
    
    # Ajuste Fuso
    agora = datetime.utcnow() - timedelta(hours=3)

    cursor.execute("SELECT quantity FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    resultado_estoque = cursor.fetchone()
    saldo_atual_banco = float(resultado_estoque[0]) if resultado_estoque else 0.0

    if tipo == 'ENTRADA':
        novo_total = saldo_atual_banco - float(qtd_ia)
    else:
        novo_total = saldo_atual_banco + float(qtd_ia)

    if novo_total < 0: novo_total = 0

    cursor.execute("""
        UPDATE estoque SET quantity = %s, ultima_atualizacao = %s
        WHERE product_id = %s AND client_id = %s
    """, (novo_total, agora, ref, client_id))

    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (%s, %s, %s, %s, %s)
    """, (client_id, ref, qtd_ia, 'ESTORNO', agora))

    conn.commit()
    cursor.close()
    conn.close()
    
    atualizar_sheets({'referencia': ref, 'peso': 0}, novo_total, planilha_id)

    return {'product_id': ref, 'estornado': float(qtd_ia), 'total': novo_total, 'acao_desfeita': tipo}

def buscar_cliente_por_whatsapp(telefone):
    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.nome, c.planilha_id, c.contexto_ia, c.cnpj 
        FROM clientes c
        JOIN numeros_autorizados n ON c.id = n.client_id
        WHERE n.telefone = %s
    """, (telefone,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()

    if resultado:
        return {
            'id': resultado[0],
            'nome_empresa': resultado[1], 
            'planilha_id': resultado[2],
            'contexto_ia': resultado[3],
            'cnpj': resultado[4] 
        }
    return None

def admin_cadastrar_cliente(nome, whatsapp, planilha_id, contexto_ia=""):
    conn = get_conexao()
    cursor = conn.cursor()
    try:           
        # 1. Cria a empresa
        cursor.execute("""
            INSERT INTO clientes (nome, planilha_id, contexto_ia) 
            VALUES (%s, %s, %s)
            RETURNING id;
        """, (nome, planilha_id, contexto_ia))
        novo_id = cursor.fetchone()[0]
        
        # 2. Associa o telefone principal a esta empresa
        cursor.execute("""
            INSERT INTO numeros_autorizados (telefone, client_id) 
            VALUES (%s, %s)
            ON CONFLICT (telefone) DO NOTHING;
        """, (whatsapp, novo_id))
        
        conn.commit()
        return novo_id
    except Exception as e:
        print(f"Erro ao cadastrar cliente: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def atualizar_estoque_via_webhook(client_id, ref, nome, nova_qtd, novo_minimo=0, especificacao='', custo=0.0, preco=0.0):
    conn = get_conexao()
    cursor = conn.cursor()
    agora = datetime.utcnow() - timedelta(hours=3)
    
    cursor.execute("SELECT id FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute("""
            UPDATE estoque 
            SET quantity = %s, estoque_minimo = %s, ultima_atualizacao = %s, nome = %s, especificacao = %s, custo_unitario = %s, preco_venda = %s
            WHERE product_id = %s AND client_id = %s
        """, (nova_qtd, novo_minimo, agora, nome, especificacao, custo, preco, ref, client_id))
    else:
        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, nome, quantity, estoque_minimo, especificacao, custo_unitario, preco_venda, ultima_atualizacao) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (client_id, ref, nome, nova_qtd, novo_minimo, especificacao, custo, preco, agora))
        
    conn.commit()
    cursor.close()
    conn.close()


# Adicione essa nova função no final do arquivo banco.py
def sincronizacao_geral_banco(client_id, produtos):
    conn = get_conexao()
    cursor = conn.cursor()
    agora = datetime.utcnow() - timedelta(hours=3)

    refs_planilha = tuple([p['referencia'] for p in produtos])

    # 1. Apaga tudo do banco que não está mais na planilha
    if refs_planilha:
        cursor.execute("DELETE FROM estoque WHERE client_id = %s AND product_id NOT IN %s", (client_id, refs_planilha))
    else:
        cursor.execute("DELETE FROM estoque WHERE client_id = %s", (client_id,))

    # 2. Atualiza ou insere (Upsert) cada linha da planilha no banco
    for p in produtos:
        custo = p.get('custo_unitario', 0.0)
        preco = p.get('preco_venda', 0.0)
        
        cursor.execute("SELECT id FROM estoque WHERE product_id = %s AND client_id = %s", (p['referencia'], client_id))
        existe = cursor.fetchone()
        
        if existe:
            cursor.execute("""
                UPDATE estoque
                SET quantity = %s, estoque_minimo = %s, ultima_atualizacao = %s, nome = %s, especificacao = %s, custo_unitario = %s, preco_venda = %s
                WHERE product_id = %s AND client_id = %s
            """, (p['quantidade'], p['estoque_minimo'], agora, p['nome'], p['especificacao'], custo, preco, p['referencia'], client_id))
        else:
            cursor.execute("""
                INSERT INTO estoque (client_id, product_id, nome, quantity, estoque_minimo, especificacao, custo_unitario, preco_venda, ultima_atualizacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (client_id, p['referencia'], p['nome'], p['quantidade'], p['estoque_minimo'], p['especificacao'], custo, preco, agora))
    conn.commit()
    cursor.close()
    conn.close()

def gerar_relatorio_financeiro(client_id):
    conn = get_conexao()
    cursor = conn.cursor()
    
    # Faturamento (Saídas) do mês atual
    cursor.execute("""
        SELECT COALESCE(SUM(valor_total), 0) FROM historico 
        WHERE client_id = %s AND tipo = 'SAIDA' 
        AND EXTRACT(MONTH FROM data) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM data) = EXTRACT(YEAR FROM CURRENT_DATE)
    """, (client_id,))
    faturamento = cursor.fetchone()[0]

    # Custos (Entradas) do mês atual
    cursor.execute("""
        SELECT COALESCE(SUM(valor_total), 0) FROM historico 
        WHERE client_id = %s AND tipo = 'ENTRADA' 
        AND EXTRACT(MONTH FROM data) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM data) = EXTRACT(YEAR FROM CURRENT_DATE)
    """, (client_id,))
    custos = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    return float(faturamento), float(custos)

def admin_listar_clientes():
    """Retorna uma lista de todos os clientes com seus IDs."""
    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM clientes ORDER BY id")
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()

    if not resultados:
        return "Nenhum cliente cadastrado no sistema."

    msg = "🏢 *Empresas Cadastradas:*\n\n"
    for row in resultados:
        msg += f"ID: *{row[0]}* - {row[1]}\n"
    return msg

def admin_adicionar_numero_por_id(novo_numero, client_id):
    """Vincula um novo número de WhatsApp direto ao ID da empresa."""
    conn = get_conexao()
    cursor = conn.cursor()
    try:
        # Verifica se o ID da empresa realmente existe
        cursor.execute("SELECT id FROM clientes WHERE id = %s", (client_id,))
        if not cursor.fetchone():
            return False

        # Adiciona o número
        cursor.execute("""
            INSERT INTO numeros_autorizados (telefone, client_id)
            VALUES (%s, %s)
            ON CONFLICT (telefone) DO NOTHING;
        """, (novo_numero, client_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao adicionar número via ID: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()