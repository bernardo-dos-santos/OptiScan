import os
import requests
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

META_TOKEN = os.getenv('META_ACCESS_TOKEN')
META_PHONE_ID = os.getenv('META_PHONE_ID')
APP_SECRET = os.getenv('META_APP_SECRET')

def enviar_mensagem_meta(para_numero, texto):
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": para_numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        resposta = requests.post(url, headers=headers, json=data)
        print(f"▶️ Status Meta: {resposta.status_code} | Resposta: {resposta.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro fatal ao conectar na Meta: {e}", flush=True)

def enviar_template_meta(para_numero, nome_template, variavel_empresa):
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": para_numero,
        "type": "template",
        "template": {
            "name": nome_template,
            "language": {"code": "pt_BR"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(variavel_empresa)}]}]
        }
    }
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"Erro Template: {e}")

def baixar_imagem_meta(media_id):
    url_info = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    try:
        res_info = requests.get(url_info, headers=headers)
        if res_info.status_code != 200: return None
        
        url_download = res_info.json().get('url')
        res_file = requests.get(url_download, headers=headers)
        return res_file.content if res_file.status_code == 200 else None
    except Exception as e:
        print(f"Erro Download Imagem: {e}")
        return None

def validar_assinatura_meta(payload, signature):
    if not APP_SECRET or not signature: return True
    expected_sig = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected_sig}", signature)