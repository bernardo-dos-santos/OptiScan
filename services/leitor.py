import os
import json
import requests
from google import genai
from google.genai import types

def analisar_imagem(url_imagem):
    """
    O Cérebro do Optilog: Baixa a imagem do WhatsApp e pede pro Gemini extrair os dados.
    """
    try:
      
        sid = os.getenv('TWILIO_ACCOUNT_SID')
        token = os.getenv('TWILIO_AUTH_TOKEN')
        resposta = requests.get(url_imagem, auth=(sid, token))
        
        if resposta.status_code != 200:
            print("Erro ao baixar imagem do Twilio")
            return None
        
        requests.delete(url_imagem, auth=(sid, token))

        # 2. Chamar o Gemini
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # O Prompt Universal (Depois dinamizar isso por cliente)
        prompt = """
        Você é um assistente de logística. Analise esta imagem e extraia os dados do produto.
        REGRAS:
        - "referencia": O código ou ID do produto.
        - "nome": NOME CURTO DO PRODUTO (MÁXIMO 2 PALAVRAS). Ex: 'Arroz Branco', 'Óleo Soya'.
        - "quantidade": Apenas a contagem de itens ou volumes lidos (número).
        - "especificacao": Detalhes técnicos e medidas (ex: '100% Algodão', '220V', '500g', '2 Litros'). OBS: Não repita a contagem de itens aqui. Peso e volume são especificações, mas a quantidade de fardos/caixas não.
        
        Retorne APENAS um JSON:
        {"referencia": "...", "nome": "...", "quantidade": ..., "especificacao": "..."}
        """
        
        # Chamada usando o padrão do SDK novo
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Pode usar o flash que é rápido e barato
            contents=[
                types.Part.from_bytes(data=resposta.content, mime_type='image/jpeg'),
                prompt
            ]
        )
        
        # 3. Limpar a resposta e converter para Dicionário
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        dados_json = json.loads(texto_limpo)
        
        # Garantir que a chave 'referencia' exista para o banco não quebrar
        if not dados_json.get('referencia'):
            dados_json['referencia'] = "ITEM_DESCONHECIDO"
            
        return dados_json

    except Exception as e:
        print(f"Erro na Visão/Gemini: {e}")
        return None