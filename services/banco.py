import os
import psycopg2
from datetime import datetime
from services.sheets import atualizar_sheets

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
    try:
        qtd_movimento = float(dados.get('quantidade', 1))
    except (ValueError, TypeError):
        qtd_movimento = 1.0
    peso_movimento = float(dados.get('peso', 0))

    conn = get_conexao()
    cursor = conn.cursor()

    cursor.execute("SELECT quantity FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    resultado = cursor.fetchone()
    saldo_atual_banco = float(resultado[0]) if resultado else 0.0

    if tipo_operacao == 'ENTRADA':
        novo_total = saldo_atual_banco + qtd_movimento
    elif tipo_operacao == 'SAIDA':
        novo_total = saldo_atual_banco - qtd_movimento
        if novo_total < 0: novo_total = 0

    agora = datetime.now()

    if resultado:
        cursor.execute("""
            UPDATE estoque SET quantity = %s, peso = %s, ultima_atualizacao = %s
            WHERE product_id = %s AND client_id = %s
        """, (novo_total, peso_movimento, agora, ref, client_id))
    else:
        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, quantity, peso, ultima_atualizacao)
            VALUES (%s, %s, %s, %s, %s)
        """, (client_id, ref, novo_total, peso_movimento, agora))

    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (%s, %s, %s, %s, %s)
    """, (client_id, ref, qtd_movimento, tipo_operacao, agora))

    conn.commit()
    cursor.close()
    conn.close()

    return {'product_id': ref, 'total': novo_total, 'qtd_movimentada': qtd_movimento}

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
    agora = datetime.now()

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

def buscar_cliente_por_whatsapp(numero_whatsapp):
    conn = get_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT id, planilha_id FROM clientes WHERE whatsapp = %s", (numero_whatsapp,))
    cliente = cursor.fetchone()
    conn.close()
    if cliente:
        return {'id': cliente[0], 'planilha_id': cliente[1]}
    return None

def atualizar_estoque_via_webhook(client_id, ref, nova_qtd):
    conn = get_conexao()
    cursor = conn.cursor()
    agora = datetime.now()
    
    cursor.execute("SELECT id FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute("UPDATE estoque SET quantity = %s, ultima_atualizacao = %s WHERE product_id = %s AND client_id = %s", (nova_qtd, agora, ref, client_id))
    else:
        cursor.execute("INSERT INTO estoque (client_id, product_id, quantity, peso, ultima_atualizacao) VALUES (%s, %s, %s, 0, %s)", (client_id, ref, nova_qtd, agora))
        
    cursor.execute("INSERT INTO historico (client_id, product_id, quantidade, tipo, data) VALUES (%s, %s, %s, 'AJUSTE_PLANILHA', %s)", (client_id, ref, nova_qtd, agora))
    
    conn.commit()
    cursor.close()
    conn.close()