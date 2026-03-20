from flask import Flask, request
import requests
import os
import base64
from datetime import datetime # Para nomes únicos
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configurações de pastas
UPLOAD_FOLDER = 'recebidos'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- FUNÇÃO QUE ENVIA PARA O GOOGLE (Puxada do seu teste_visao.py) ---
def ler_imagem_google(caminho_imagem):
    api_key = os.getenv('GOOGLE_VISION_KEY')
    
    # Transforma a imagem em base64
    with open(caminho_imagem, "rb") as arquivo_imagem:
        imagem_base64 = base64.b64encode(arquivo_imagem.read()).decode('utf-8')

    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {
        "requests": [{
            "image": {"content": imagem_base64},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    resposta = requests.post(url, json=payload)
    dados = resposta.json()

    try:
        return dados['responses'][0]['fullTextAnnotation']['text']
    except (KeyError, IndexError):
        return "Nenhum texto encontrado ou erro na API."

# --- ROTA DO WHATSAPP ---
@app.route("/whatsapp", methods=['POST'])
def reply_whatsapp():
    num_media = int(request.values.get('NumMedia', 0))
    
    if num_media > 0:
        media_url = request.values.get('MediaUrl0')
        
        # 1. GERA NOME ÚNICO (Para não dar duplicata!)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{UPLOAD_FOLDER}/estoque_{timestamp}.jpg"
        
        # 2. FAZ O DOWNLOAD DA FOTO
        response = requests.get(media_url, auth=(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
        
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"\n--- Foto recebida: {filename} ---")
            
            # 3. CHAMA A IA AUTOMATICAMENTE
            print("Iniciando leitura do Google Vision...")
            texto = ler_imagem_google(filename)
            
            print("\n--- RESULTADO DA LEITURA ---")
            print(texto)
            print("----------------------------\n")
            
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000)