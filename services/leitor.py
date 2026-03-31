import os
import json
from google import genai
from google.genai import types

def analisar_imagem(imagem_bytes, contexto_cliente="", legenda=""):
    """
    Analisa os bytes da imagem vindos da Meta e extrai dados do produto.
    """
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        instrucoes_dinamicas = contexto_cliente if contexto_cliente else """
        Foque em ler etiquetas de armazém, caixas, marcações a caneta ou embalagens industriais.
        - Se houver etiqueta impressa, extraia a referência exata (ex: F500056).
        - Se houver lista em papel com 'X' ou marcação, identifique o item assinalado.
        """

        # Regra de ouro para a matemática da legenda
        bloco_legenda = f"""
        ATENÇÃO MÁXIMA - LEGENDA DO USUÁRIO: "{legenda}"
        Se a legenda contiver multiplicadores como "fardos", "caixas" ou "x" (ex: "30 fardos"):
        1. Encontre a quantidade unitária descrita na etiqueta ou embalagem na FOTO (ex: QTD 3000).
        2. Multiplique o número da legenda pela quantidade unitária encontrada na foto.
        3. A sua PRIORIDADE ABSOLUTA é colocar o RESULTADO TOTAL DESSA MULTIPLICAÇÃO no campo "quantidade".
        """ if legenda else ""

        prompt = f"""
        Você é um especialista em logística e gestão de inventário.
        Analise a imagem e extraia os dados.

        CONTEXTO DO CLIENTE:
        {instrucoes_dinamicas}

        {bloco_legenda}

        REGRAS FIXAS DO JSON (Siga rigorosamente):
        - "referencia": ID/Código do produto. Se não houver, crie um código curto baseado no nome.
        - "nome": Nome principal do produto (MÁXIMO 2 PALAVRAS).
        - "quantidade": Número (inteiro ou decimal).
        - "especificacao": Detalhes técnicos, peso ou marca. Seja extremamente conciso (MÁXIMO DE 4 PALAVRAS). NÃO repita informação do "nome" ou "referencia".

        Retorne APENAS um JSON válido no formato:
        {{"referencia": "...", "nome": "...", "quantidade": ..., "especificacao": "..."}}
        """
        
        
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[
                types.Part.from_bytes(data=imagem_bytes, mime_type='image/jpeg'),
                prompt
            ]
        )
        
        texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpo)

    except Exception as e:
        print(f"Erro no leitor Gemini: {e}")
        return None
    
def analisar_pdf_nf(pdf_bytes, cnpj_cliente):
    """Lê um PDF, identifica se é compra ou venda via CNPJ, e extrai os itens."""
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        prompt = f"""
        Você é um sistema de ERP inteligente processando uma Nota Fiscal brasileira em PDF.
        A empresa dona deste sistema tem o CNPJ: {cnpj_cliente}
        
        Sua primeira tarefa é descobrir a NATUREZA DA OPERAÇÃO usando APENAS esta regra lógica infalível:
        - Se o CNPJ {cnpj_cliente} estiver no campo DESTINATÁRIO, a empresa está comprando. Defina "tipo_operacao": "ENTRADA".
        - Se o CNPJ {cnpj_cliente} estiver no campo EMITENTE, a empresa está vendendo. Defina "tipo_operacao": "SAIDA".
        
        Sua segunda tarefa é extrair os produtos. Siga estas regras:
        1. NOME CURTO: Nome simples sem medidas.
        2. ESPECIFICACAO: Todas as medidas e detalhes técnicos.
        3. QUANTIDADE: Apenas número (use ponto para decimais).
        4. VALOR FINANCEIRO:
           - Se a operação for ENTRADA, extraia o valor unitário e chame de "custo_unitario".
           - Se a operação for SAIDA, extraia o valor unitário e chame de "preco_venda".
        # Adicionar esta regra no prompt do Gemini:
        5. UNIDADES DE MEDIDA E MATEMÁTICA: Preste muita atenção na coluna UNID. Se o produto for vendido em "MI" (Milheiro), "CX" (Caixa) ou "FD" (Fardo), a sua missão é retornar a quantidade física total (Ex: 3 MI = 3000 unidades) E o custo estritamente unitário de CADA PEÇA (Valor Total da Linha dividido pela Quantidade Física Total). A matemática de 'quantidade * custo_unitario' DEVE bater com o valor total da nota.

           
        Retorne APENAS um JSON válido nesta exata estrutura:
        {{
            "tipo_operacao": "ENTRADA",
            "produtos": [
                {{"referencia": "codigo", "nome": "SACO PP", "quantidade": 10.5, "especificacao": "30X42", "custo_unitario": 2.45}}
            ]
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'), prompt]
        )
        
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpo)
        
    except Exception as e:
        print(f"Erro no Gemini ao ler PDF: {e}")
        return None