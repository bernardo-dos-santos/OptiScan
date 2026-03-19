import requests
import base64
import os
from dotenv import load_dotenv


load_dotenv()


API_KEY = os.getenv('GOOGLE_VISION_KEY')

def ler_imagem_base64(caminho_imagem):
    with open(caminho_imagem, "rb") as arquivo_imagem:
        return base64.b64encode(arquivo_imagem.read()).decode('utf-8')

caminho_foto = 'teste.jpg' 

print("Enviando foto para a inteligência artificial do Google...")

url = f'https://vision.googleapis.com/v1/images:annotate?key={API_KEY}'
payload = {
    "requests": [
        {
            "image": {
                "content": ler_imagem_base64(caminho_foto)
            },
            "features": [
                {
                    "type": "TEXT_DETECTION" 
                }
            ]
        }
    ]
}


resposta = requests.post(url, json=payload)
dados = resposta.json()


try:
    
    texto_extraido = dados['responses'][0]['fullTextAnnotation']['text']
    print("\n--- SUCESSO! TEXTO ENCONTRADO NA IMAGEM ---\n")
    print(texto_extraido)
except KeyError:
    print("\nNenhum texto foi encontrado na imagem ou houve um erro.")
    print("Detalhes do erro:", dados)