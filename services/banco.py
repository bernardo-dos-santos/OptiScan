import sqlite3
from datetime import datetime
from services.sheets import buscar_saldo_na_planilha

def salvar_no_banco(dados, client_id, planilha_id, tipo_operacao='ENTRADA'):
    """
    Registra a transação, mas SEMPRE usando a planilha do Google como a fonte da verdade.
    """
    ref = str(dados.get('referencia', 'ITEM_DESCONHECIDO')).upper()
    
    # Extrai a quantidade vinda da IA (se não vier ou der erro, assume 1)
    try:
        qtd_movimento = float(dados.get('quantidade', 1))
    except (ValueError, TypeError):
        qtd_movimento = 1.0

    # 1. SINCRONIZAÇÃO DE MÃO DUPLA: Busca o saldo real na planilha primeiro
    saldo_atual_planilha = buscar_saldo_na_planilha(ref, planilha_id)

    # 2. Calcula o novo saldo com base no que está na planilha
    if tipo_operacao == 'ENTRADA':
        novo_total = saldo_atual_planilha + qtd_movimento
    elif tipo_operacao == 'SAIDA':
        novo_total = saldo_atual_planilha - qtd_movimento
        # Opcional: Trava para o estoque não ficar negativo
        if novo_total < 0: 
            novo_total = 0
    else:
        novo_total = saldo_atual_planilha

    # 3. Atualiza o banco local (Espelho e Histórico)
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM estoque WHERE product_id = ? AND client_id = ?", (ref, client_id))
    item_existe = cursor.fetchone()
    agora = datetime.now()

    if item_existe:
        cursor.execute("""
            UPDATE estoque SET quantity = ?, ultima_atualizacao = ?
            WHERE product_id = ? AND client_id = ?
        """, (novo_total, agora, ref, client_id))
    else:
        # Se for um item novo, pega o peso (se houver) e cadastra
        peso = dados.get('peso', 0)
        cursor.execute("""
            INSERT INTO estoque (client_id, product_id, quantity, peso, ultima_atualizacao)
            VALUES (?, ?, ?, ?, ?)
        """, (client_id, ref, novo_total, peso, agora))

    # Salva o log de auditoria
    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, ref, qtd_movimento, tipo_operacao, agora))

    conn.commit()
    conn.close()

    return {
        'product_id': ref,
        'total': novo_total,
        'qtd_movimentada': qtd_movimento
    }

def executar_estorno_banco(client_id, planilha_id):
    """
    Busca a última transação e reverte com base no SALDO REAL DA PLANILHA.
    """
    from services.sheets import buscar_saldo_na_planilha, atualizar_sheets
    import sqlite3
    from datetime import datetime
    
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()

    # 1. Acha o que a IA acabou de fazer
    cursor.execute("""
        SELECT product_id, quantidade, tipo 
        FROM historico 
        WHERE client_id = ? AND tipo IN ('ENTRADA', 'SAIDA')
        ORDER BY id DESC LIMIT 1
    """, (client_id,))
    
    ultima_transacao = cursor.fetchone()

    if not ultima_transacao:
        conn.close()
        return None

    ref, qtd_ia, tipo = ultima_transacao
    agora = datetime.now()

    # 2. A CHAVE DO SUCESSO: Olha para a planilha AGORA ANTES de desfazer
    saldo_atual_planilha = buscar_saldo_na_planilha(ref, planilha_id)

    # 3. Faz a matemática correta (Se o total é 4004 e a IA botou 4, tira só 4)
    if tipo == 'ENTRADA':
        novo_total = saldo_atual_planilha - qtd_ia
    else:
        novo_total = saldo_atual_planilha + qtd_ia

    # Trava para não ficar negativo
    if novo_total < 0:
        novo_total = 0

    # 4. Salva a correção no banco local
    cursor.execute("""
        UPDATE estoque SET quantity = ?, ultima_atualizacao = ?
        WHERE product_id = ? AND client_id = ?
    """, (novo_total, agora, ref, client_id))

    # 5. Registra que o estorno foi feito
    cursor.execute("""
        INSERT INTO historico (client_id, product_id, quantidade, tipo, data)
        VALUES (?, ?, ?, 'ESTORNO', ?)
    """, (client_id, ref, qtd_ia, agora))

    conn.commit()
    conn.close()

    # 6. Manda o valor corrigido (4000) de volta para a planilha
    atualizar_sheets({'referencia': ref}, novo_total, planilha_id)

    return {
        'product_id': ref,
        'total': novo_total,
        'estornado': qtd_ia,
        'acao_desfeita': tipo
    }