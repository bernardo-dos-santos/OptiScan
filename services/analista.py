import os
from google import genai
from services.banco import get_conexao
from services.meta import enviar_mensagem_meta  # <-- Importação limpa e no topo do arquivo

def rodar_analise_preditiva():
    """Lê o histórico de 30 dias e define o estoque mínimo ideal usando IA"""
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

    for (client_id, product_id), registros in historico_produtos.items():
        dados_texto = "\n".join(registros)
        
        prompt = f"""
        Você é um analista de logística sênior.
        Abaixo está o histórico de SAÍDAS DIÁRIAS do produto '{product_id}' nos últimos 30 dias.
        
        {dados_texto}
        
        Analise a velocidade de consumo diário e possíveis picos.
        Calcule o 'Estoque Mínimo de Segurança' ideal para suprir os próximos 15 dias sem ruptura.
        
        Retorne APENAS um número inteiro. Nenhuma palavra adicional, símbolo ou explicação.
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            novo_minimo = int(response.text.strip().replace('.', '').replace(',', ''))
            
            # Busca WhatsApp do cliente e Nome do Produto
            cursor.execute("""
                SELECT c.whatsapp, e.nome 
                FROM clientes c 
                JOIN estoque e ON c.id = e.client_id 
                WHERE c.id = %s AND e.product_id = %s
            """, (client_id, product_id))
            
            dados_cli = cursor.fetchone()
            
            if dados_cli:
                whatsapp_cliente, nome_produto = dados_cli
                
                mensagem = (f"💡 *Dica do OptiScan:*\n"
                            f"Analisei o consumo dos últimos 30 dias de *{nome_produto}*.\n"
                            f"Sugiro que ajuste o Estoque Mínimo na sua planilha para *{novo_minimo}* para evitar rupturas.")
                
                # A chamada agora usa a função direto do services/meta
                enviar_mensagem_meta(whatsapp_cliente, mensagem)
                
            print(f"Produto {product_id} | Sugestão: {novo_minimo} enviada.")
            
        except Exception as e:
            print(f"Erro na análise de {product_id}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print("Análise preditiva concluída.")