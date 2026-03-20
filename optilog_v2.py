from flask import Flask, request
import requests
import os
import base64
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

UPLOAD_FOLDER = 'recebidos'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- MEMÓRIA: GRAVAÇÃO NO SQLITE ---
def salvar_no_banco(dados):
    """
    Insere os dados filtrados na tabela estoque do arquivo estoque.db
    """
    try:
        # Conecta ao arquivo de banco de dados
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()

        # Mapeamento para as colunas que você criou:
        # item_name -> Descrição do produto
        # hs_code   -> Referência Interna
        # price     -> Peso (usando a coluna price temporariamente)
        # quantity  -> Quantidade
        cursor.execute("""
            INSERT INTO estoque (item_name, hs_code, price, quantity)
            VALUES (?, ?, ?, ?)
        """, (
            f"Entrada Bioecco Ref: {dados['referencia']}", 
            dados['referencia'], 
            dados['peso'], 
            dados['quantidade']
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao salvar no banco de dados: {e}")
        return False

# --- FILTRO: EXTRAÇÃO COM REGEX ---
def filtrar_dados_etiqueta(texto_bruto):
    # Regex flexível para capturar Ref, Peso e Qtd (mesmo com erros de OCR)
    ref_match = re.search(r"REF\.?\s*INTERNA:?\s*(\w+)", texto_bruto, re.IGNORECASE)
    peso_match = re.search(r"PESO:?\s*([\d.,]+)", texto_bruto, re.IGNORECASE)
    qtd_match = re.search(r"(?:Q|O|G)TD:?\s*([\d.,]+)", texto_bruto, re.IGNORECASE)

    return {
        "referencia": ref_match.group(1) if ref_match else "N/A",
        "peso": peso_match.group(1) if peso_match else "0",
        "quantidade": qtd_match.group(1) if qtd_match else "0"
    }

# --- VISÃO: GOOGLE VISION API ---
def ler_imagem_google(caminho_imagem):
    api_key = os.getenv('GOOGLE_VISION_KEY')
    with open(caminho_imagem, "rb") as img:
        img_b64 = base64.b64encode(img.read()).decode('utf-8')

    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {"requests": [{"image": {"content": img_b64}, "features": [{"type": "TEXT_DETECTION"}]}]}
    
    res = requests.post(url, json=payload).json()
    try:
        return res['responses'][0]['fullTextAnnotation']['text']
    except:
        return ""

# --- RECEPTOR: WHATSAPP WEBHOOK ---
@app.route("/whatsapp", methods=['POST'])
def reply_whatsapp():
    if int(request.values.get('NumMedia', 0)) > 0:
        media_url = request.values.get('MediaUrl0')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{UPLOAD_FOLDER}/estoque_{timestamp}.jpg"
        
        response = requests.get(media_url, auth=(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
        
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            # Executa o fluxo completo: Ler -> Filtrar -> Salvar
            texto_bruto = ler_imagem_google(filename)
            dados_limpos = filtrar_dados_etiqueta(texto_bruto)
            
            if salvar_no_banco(dados_limpos):
                print(f"✅ SUCESSO: Ref {dados_limpos['referencia']} gravada no SQLite.")
            else:
                print(f"❌ ERRO: Falha ao gravar dados da Ref {dados_limpos['referencia']}.")

            print(f"Detalhes: {dados_limpos}")
            
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000)