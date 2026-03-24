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
        ATENÇÃO MÁXIMA - O UTILIZADOR ENVIOU ESTA LEGENDA JUNTO COM A FOTO: "{legenda}"
        Se a legenda contiver quantidades, fardos, caixas ou multiplicadores (ex: '30 fardos de 4000', 'entraram 5', 'x10'), a tua PRIORIDADE ABSOLUTA é fazer o cálculo matemático e colocar o RESULTADO TOTAL no campo "quantidade". A foto servirá apenas para extrair a Referência e o Nome.
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
        - "especificacao": Detalhes técnicos, peso, marca ou localização. NÃO repita informação do "nome" ou "referencia".

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