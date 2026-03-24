import os
import json
from google import genai
from google.genai import types

def analisar_imagem(imagem_bytes):
    """
    O Cérebro do OptiScan: Analisa os bytes da imagem vindos da Meta e identifica
    o nível de resina dental baseado no êmbolo.
    """
    try:
        # 1. Configurar Gemini
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # 2. Prompt com lógica de "Meia Resina"
        prompt = """
        Você é um especialista em logística e materiais odontológicos. 
        Analise a imagem e extraia os dados para o inventário.

        LÓGICA PARA RESINAS DENTAIS (Seringas):
        - Identifique a posição do ÊMBOLO (a haste que empurra o produto).
        - Êmbolo totalmente para trás = quantidade: 1.0 (Cheia).
        - Êmbolo no meio do tubo = quantidade: 0.5 (Metade).
        - Êmbolo quase no bico = quantidade: 0.1 (Vazia/Final).
        - Use valores decimais conforme a posição visual.

        REGRAS DO JSON:
        - "referencia": ID/Código ou crie um baseado no nome.
        - "nome": Nome comercial (ex: 'Resina Charisma A2').
        - "quantidade": Número (decimal para seringas, inteiro para caixas).
        - "especificacao": Cor, marca ou detalhes técnicos.

        Retorne APENAS o JSON:
        {"referencia": "...", "nome": "...", "quantidade": ..., "especificacao": "..."}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[
                types.Part.from_bytes(data=imagem_bytes, mime_type='image/jpeg'),
                prompt
            ]
        )
        
        # Limpa e converte
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpo)

    except Exception as e:
        print(f"Erro na Visão/Gemini: {e}")
        return None