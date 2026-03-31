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
        
        Sua primeira tarefa é descobrir a NATUREZA DA OPERAÇÃO:
        - Se o CNPJ {cnpj_cliente} estiver no campo DESTINATÁRIO, a empresa está comprando. Defina "tipo_operacao": "ENTRADA".
        - Se o CNPJ {cnpj_cliente} estiver no campo EMITENTE, a empresa está vendendo. Defina "tipo_operacao": "SAIDA".
        
        Sua segunda tarefa é extrair os produtos. Siga estas regras ESTRITAS:
        1. NOME CURTO: Nome simples sem medidas.
        2. ESPECIFICACAO: Medidas e detalhes técnicos.
        3. QUANTIDADE FÍSICA E MATEMÁTICA: 
           - Observe a UNID. Se for "MIL" ou "MI" (Milheiro), multiplique a quantidade da nota por 1000. (Exemplo: se diz 3 MI, retorne 3000). A prioridade é a quantidade física de peças.
        4. VALOR FINANCEIRO:
           - Se for MIL/MI, o custo unitário é o Valor Total da Linha dividido pela Quantidade Física de peças (Ex: 465 / 3000 = 0.155).
           - PROIBIDO ARREDONDAR: Se o cálculo der 0.155, retorne exatamente 0.155 (NÃO arredonde para 0.16).
           - Se a operação for ENTRADA, chame de "custo_unitario". Se for SAIDA, chame de "preco_venda".
           - Retorne com PONTO decimal. Sem aspas.
           
        Retorne APENAS um JSON válido nesta exata estrutura:
        {{
            "tipo_operacao": "ENTRADA",
            "produtos": [
                {{"referencia": "codigo", "nome": "SACO PP", "quantidade": 3000, "especificacao": "30X42", "custo_unitario": 0.155}}
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