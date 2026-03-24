import os
import json
from google import genai
from google.genai import types

def analisar_imagem(imagem_bytes, contexto_cliente=""):
    """
    Analisa os bytes da imagem vindos da Meta e extrai dados do produto.
    """
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # Se não houver contexto dinâmico do banco, usa o padrão de armazém
        instrucoes_dinamicas = contexto_cliente if contexto_cliente else """
        Foque em ler etiquetas de armazém, caixas, marcações a caneta ou embalagens industriais.
        - Se houver etiqueta impressa, extraia a referência exata (ex: F500056).
        - Se houver lista em papel com 'X' ou marcação, identifique o item assinalado.
        - Estime a quantidade de fardos ou leia os números escritos à mão.
        """

        prompt = f"""
        Você é um especialista em logística e gestão de inventário.
        Analise a imagem e extraia os dados.

        CONTEXTO DO CLIENTE:
        {instrucoes_dinamicas}

        REGRAS FIXAS DO JSON (Siga rigorosamente para todos os clientes):
        - "referencia": ID/Código do produto. Se não houver, crie um código curto baseado no nome.
        - "nome": Nome principal do produto. EXTREMAMENTE IMPORTANTE: Deve conter NO MÁXIMO 2 PALAVRAS (ex: "Saco Plástico", "Papel Kraft", "Oceano").
        - "quantidade": Número (inteiro ou decimal).
        - "especificacao": Detalhes técnicos, peso, marca ou localização. IMPORTANTE: NÃO repita nenhuma informação que já esteja no "nome" ou na "referencia". Use apenas para dados novos/complementares.

        Retorne APENAS um JSON válido no seguinte formato:
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