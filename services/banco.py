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
    nome = str(dados.get('nome', 'Produto Sem Nome'))
    espec = str(dados.get('especificacao', 'N/A'))
    
    try:
        qtd_movimento = float(dados.get('quantidade', 1))
    except (ValueError, TypeError):
        qtd_movimento = 1.0
        
    peso_movimento = float(dados.get('peso', 0))

    conn = get_conexao()
    cursor = conn.cursor()

    # 1. Busca o saldo e dados atuais
    cursor.execute("SELECT quantity FROM estoque WHERE product_id = %s AND client_id = %s", (ref, client_id))
    resultado = cursor.fetchone()
    
    # --- TRAVA DE SEGURANÇA PARA SAÍDAS ---
    if tipo_operacao == 'SAIDA':
        if not resultado:
            cursor.close()
            conn.close()
            return {'erro': f"O código *{ref}* não está cadastrado no sistema."}
        
        saldo_atual_temp = float(resultado[0])
        if qtd_movimento > saldo_atual_temp:
            cursor.close()
            conn.close()
            return {'erro': f"Estoque insuficiente. Você tentou retirar {qtd_movimento}, mas só há {saldo_atual_temp} unidades de *{ref}*."}
    # --------------------------------------
     
    saldo_atual_banco = float(resultado[0]) if resultado else 0.0

    # 2. Calcula novo saldo
    if tipo_operacao == 'ENTRADA':
        novo_total = saldo_atual_banco + qtd_movimento
    else:
        novo_total = saldo_atual_banco - qtd_movimento
        if novo_total < 0: novo_total = 0

    agora = datetime.now()

    # 3. Update ou Insert incluindo NOME e ESPECIFICAÇÃO
    if resultado:
        cursor.execute("""
            UPDATE estoque 
            SET quantity = %s, peso = %s, nome = %s, especificacao = %s, ultima_atualizacao = %s
            WHERE product_id = %s AND client_id = %s
        """, (novo_total, peso_movimento, nome, espec, agora, ref, client_id))
    else:
        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, nome, especificacao, quantity, peso, ultima_atualizacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (client_id, ref, nome, espec, novo_total, peso_movimento, agora))

    # 4. Histórico (opcional: pode adicionar colunas aqui também se quiser log detalhado)
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

def admin_cadastrar_cliente(nome, whatsapp, planilha_id):
    conn = get_conexao()
    cursor = conn.cursor()
    try:
        # Garante o formato internacional
        if not whatsapp.startswith('+'):
            whatsapp = '+' + whatsapp
            
        cursor.execute("""
            INSERT INTO clientes (nome, whatsapp, planilha_id) 
            VALUES (%s, %s, %s)
            ON CONFLICT (whatsapp) DO UPDATE SET nome = EXCLUDED.nome, planilha_id = EXCLUDED.planilha_id
            RETURNING id;
        """, (nome, whatsapp, planilha_id))
        
        novo_id = cursor.fetchone()[0]
        conn.commit()
        return novo_id
    except Exception as e:
        print(f"Erro ao cadastrar cliente: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

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