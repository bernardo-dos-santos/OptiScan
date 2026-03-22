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
        # 1. Baixar a imagem enviada pelo Twilio
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
        Você é um assistente de logística. Analise esta imagem e extraia os dados do produto para o estoque.
        REGRAS CRÍTICAS DE MATEMÁTICA (PADRÃO BRASILEIRO):
        - Na etiqueta, o ponto indica milhar (Ex: 4.000 significa QUATRO MIL). Retorne como número inteiro sem ponto (ex: 4000).
        - Se houver vírgula, trate como decimal (Ex: 1,5 significa 1.5).
        
        Retorne APENAS um objeto JSON válido, sem formatação markdown (```json), com as seguintes chaves:
        - "referencia": O código ou ID do produto (se não houver, crie um curto).
        - "quantidade": A quantidade exata lida (número). Use 1 se não estiver visível.
        - "peso": O peso (número). Use 0 se não for aplicável.
        - "nome": O nome descritivo do produto.
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