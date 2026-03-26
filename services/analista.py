import os
from google import genai
from services.banco import get_conexao
from services.meta import enviar_mensagem_meta

def rodar_analise_preditiva():
    """Lê o histórico de 30 dias e define o estoque mínimo ideal usando IA (Agrupado por cliente)"""
    print("Iniciando cálculo preditivo de estoque...")
    conn = get_conexao()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT client_id, product_id, DATE(data) as dia, SUM(quantidade) as total_dia
        FROM historico
        WHERE tipo = 'SAIDA' AND data >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY client_id, product_id, DATE(data)
        ORDER BY client_id, product_id, dia;
    """)
    resultados = cursor.fetchall()
    
    historico_produtos = {}
    for client_id, product_id, dia, total_dia in resultados:
        chave = (client_id, product_id)
        if chave not in historico_produtos:
            historico_produtos[chave] = []
        historico_produtos[chave].append(f"Dia {dia}: {total_dia} unidades")

    if not historico_produtos:
        print("Sem dados suficientes de saída nos últimos 30 dias.")
        cursor.close()
        conn.close()
        return

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # DICIONÁRIO PARA AGRUPAR AS MENSAGENS ANTES DE ENVIAR
    mensagens_por_cliente = {}

    for (client_id, product_id), historico in historico_produtos.items():
        historico_str = "\n".join(historico)
        prompt = f"""
        Analise o histórico de saídas diárias deste produto nos últimos 30 dias:
        {historico_str}
        
        Calcule qual deve ser o estoque mínimo ideal para evitar rupturas, considerando
        um tempo de reposição de 7 dias. Retorne APENAS O NÚMERO INTEIRO, sem texto.
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            novo_minimo = int(response.text.strip().replace('.', '').replace(',', ''))
            
            # Buscamos também o estoque_minimo atual no banco (e.estoque_minimo)
            cursor.execute("""
                SELECT c.whatsapp, e.nome, e.estoque_minimo 
                FROM clientes c 
                JOIN estoque e ON c.id = e.client_id 
                WHERE c.id = %s AND e.product_id = %s
            """, (client_id, product_id))
            
            dados_cli = cursor.fetchone()
            
            if dados_cli:
                whatsapp_cliente, nome_produto, minimo_atual = dados_cli
                
                # CÁLCULO DA MARGEM DE TOLERÂNCIA (10%)
                if minimo_atual > 0:
                    diferenca_percentual = abs(novo_minimo - minimo_atual) / minimo_atual
                    # Se a variação for menor ou igual a 10%, ignoramos a dica.
                    if diferenca_percentual <= 0.10:
                        print(f"Ignorado: {nome_produto} (Variação irrelevante de {minimo_atual} para {novo_minimo})")
                        continue 
                elif minimo_atual == 0 and novo_minimo == 0:
                    continue # Se já era zero e a IA sugeriu zero, ignora.
                
                # Se passou pela tolerância, guarda na sacola do cliente
                if whatsapp_cliente not in mensagens_por_cliente:
                    mensagens_por_cliente[whatsapp_cliente] = []
                    
                mensagens_por_cliente[whatsapp_cliente].append(f"🔹 *{nome_produto}*: de {minimo_atual} para *{novo_minimo}*")
            
        except Exception as e:
            print(f"Erro na análise de {product_id}: {e}")

    # AGORA SIM, FORA DO LOOP, ENVIA UMA MENSAGEM ÚNICA POR CLIENTE
    for whatsapp, lista_dicas in mensagens_por_cliente.items():
        texto_final = "💡 *Dica do OptiScan (Análise dos últimos 30 dias):*\nSugiro que ajuste o Estoque Mínimo na planilha para os seguintes itens para evitar rupturas:\n\n"
        texto_final += "\n".join(lista_dicas)
        
        enviar_mensagem_meta(whatsapp, texto_final)
        print(f"Resumo preditivo enviado para {whatsapp}")

    conn.commit()
    cursor.close()
    conn.close()
    print("Cálculo preditivo finalizado.")