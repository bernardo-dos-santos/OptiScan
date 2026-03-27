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
    
def analisar_pdf_nf(pdf_bytes):
    """Lê um PDF de Nota Fiscal e retorna uma lista (Array) de produtos."""
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        prompt = prompt = """
        Você é um sistema de ERP inteligente. Extraia todos os produtos contidos nesta Nota Fiscal em PDF.
        IGNORE frete, impostos e dados das empresas. Foque na tabela de PRODUTOS.
        
        Siga estas regras de ouro de formatação:
        
        1. NOME CURTO: Crie um nome simples e curtíssimo para o produto, que seja fácil de ler e buscar. O campo "nome" NUNCA deve conter números de medidas, espessuras ou siglas técnicas (IMP, AA/CPG, etc).
        
        2. ESPECIFICAÇÃO COMPLETA: Pegue TODAS as informações técnicas — incluindo medidas completas (ex: 30X42+4), espessura (ex: 0,08), tipo de impressão, cores, ou qualquer sigla técnica — e jogue tudo no campo "especificacao".
        
        3. REGRA DE QUANTIDADE: Retorne o valor como NÚMERO PURO. Se na nota estiver escrito "30.500", retorne 30500. Use ponto apenas para casas decimais (ex: 10.5).
        
        ### EXEMPLO DO QUE FAZER:
        Nome na Nota: SACO PP IMP DADRI 30X42+4X0,08 AA/CPG
        Você retorna: {"nome": "SACO PP DADRI", "especificacao": "IMP 30X42+4X0,08 AA/CPG"}
        
        Retorne um ARRAY DE JSON válido com esta estrutura:
        [
          {"referencia": "codigo_na_nota", "nome": "nome do produto curtíssimo", "quantidade": 10.5, "especificacao": "detalhe e medidas completas (ex: 30X42+4X0,08, kg)"}
        ]
        
        Se não houver código, crie um curto (ex: PA-NOME).
        Retorne APENAS o JSON.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'),
                prompt
            ]
        )
        
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpo)
        
    except Exception as e:
        print(f"Erro no Gemini ao ler PDF: {e}")
        return []