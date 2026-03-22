import os
import psycopg2
from datetime import datetime
from services.sheets import buscar_saldo_na_planilha, atualizar_sheets

def get_conexao():
    """Cria a conexão com o banco de dados Supabase (PostgreSQL)"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        port=os.getenv('DB_PORT', 5432)
    )

def salvar_no_banco(dados, client_id, planilha_id, tipo_operacao='ENTRADA'):
    ref = str(dados.get('referencia', 'ITEM_DESCONHECIDO')).upper()
    
    try:
        qtd_movimento = float(dados.get('quantidade', 1))
    except (ValueError, TypeError):
        qtd_movimento = 1.0

    # 1. Busca o saldo real na planilha
    saldo_atual_planilha = buscar_saldo_na_planilha(ref, planilha_id)

    # 2. Calcula o novo saldo
    if tipo_operacao == 'ENTRADA':
        novo_total = saldo_atual_planilha + qtd_movimento
    elif tipo_operacao == 'SAIDA':
        novo_total = saldo_atual_planilha - qtd_movimento
        if novo_total < 0: 
            novo_total = 0
    else:
        novo_total = saldo_atual_planilha

    agora = datetime.now()
    conn = get_conexao()
    cursor = conn.cursor()

    # Verifica se o item já existe para esse cliente (Usando %s do Postgres)
    cursor.execute("SELECT id FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    item_existe = cursor.fetchone()

    if item_existe:
        cursor.execute("""
            UPDATE estoque SET quantity = %s, ultima_atualizacao = %s
            WHERE product_id = %s AND client_id = %s
        """, (novo_total, agora, ref, client_id))
    else:
        peso = dados.get('peso', 0)
        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, quantity, peso, ultima_atualizacao)
            VALUES (%s, %s, %s, %s, %s)
        """, (client_id, ref, novo_total, peso, agora))

    # Salva o log
    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (%s, %s, %s, %s, %s)
    """, (client_id, ref, qtd_movimento, tipo_operacao, agora))

    conn.commit()
    cursor.close()
    conn.close()

    return {
        'product_id': ref,
        'total': novo_total,
        'qtd_movimentada': qtd_movimento
    }

def executar_estorno_banco(client_id, planilha_id):
    conn = get_conexao()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_id, quantidade, tipo 
        FROM historico 
        WHERE client_id = %s AND tipo IN ('ENTRADA', 'SAIDA')
        ORDER BY id DESC LIMIT 1
    """, (client_id,))
    
    ultima_transacao = cursor.fetchone()

    if not ultima_transacao:
        conn.close()
        return None

    ref, qtd_ia, tipo = ultima_transacao
    agora = datetime.now()

    saldo_atual_planilha = buscar_saldo_na_planilha(ref, planilha_id)

    if tipo == 'ENTRADA':
        novo_total = saldo_atual_planilha - float(qtd_ia)
    else:
        novo_total = saldo_atual_planilha + float(qtd_ia)

    if novo_total < 0:
        novo_total = 0

    cursor.execute("""
        UPDATE estoque SET quantity = %s, ultima_atualizacao = %s
        WHERE product_id = %s AND client_id = %s
    """, (novo_total, agora, ref, client_id))

    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (%s, %s, %s, 'ESTORNO', %s)
    """, (client_id, ref, qtd_ia, agora))

    conn.commit()
    cursor.close()
    conn.close()

    atualizar_sheets({'referencia': ref}, novo_total, planilha_id)

    return {
        'product_id': ref,
        'total': novo_total,
        'estornado': qtd_ia,
        'acao_desfeita': tipo
    }