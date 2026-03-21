from flask import Flask, request
from twilio.rest import Client
import requests
import os
import base64
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
import io

load_dotenv()
app = Flask(__name__)

# Configurações Twilio
client_twilio = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))

# AGORA O HISTÓRICO GUARDA UM DICIONÁRIO (Log da transação)
historico_usuarios = {}

UPLOAD_FOLDER = 'recebidos'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- FUNÇÕES DE APOIO ---

def responder_whatsapp(para, mensagem):
    client_twilio.messages.create(
        from_='whatsapp:+14155238886',
        body=mensagem,
        to=para
    )

def salvar_no_sheets(dados, total_banco):
    try:
        # 1. Autenticação segura usando o arquivo local
        caminho_absoluto = os.path.abspath('chave_nova.json')
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(caminho_absoluto, scope)
        client = gspread.authorize(creds)

        # 2. Puxando o ID da planilha do arquivo .env
        planilha_id = os.getenv('PLANILHA_ID')
        planilha = client.open_by_key(planilha_id)
        aba = planilha.sheet1 

        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # 3. Tenta achar a referência na planilha (tratando o erro do gspread)
        try:
            celula = aba.find(dados['referencia'])
        except gspread.exceptions.CellNotFound:
            celula = None

        # 4. Lógica de Dashboard (Atualiza ou Cria)
        if celula:
            # Se a referência já existe, ATUALIZA a mesma linha
            linha = celula.row
            aba.update_acell(f'A{linha}', data_hora)      # Atualiza a Coluna A (Última Data)
            aba.update_acell(f'D{linha}', total_banco)    # Atualiza a Coluna D (Quantidade Total Atualizada)
            
            print(f"✅ Sheets ATUALIZADO: Linha {linha} -> Ref {dados['referencia']} = {total_banco}")
            
        else:
            # Se a referência não existe, CRIA a primeira linha
            nova_linha = [data_hora, dados['referencia'], dados['peso'], total_banco, "Ativo"]
            aba.append_row(nova_linha)
            
            print(f"✅ Sheets NOVA LINHA: Ref {dados['referencia']} adicionada com {total_banco}")

        return True
    
    except Exception as e:
        print(f"❌ Erro no Sheets: {e}")
        return False

def salvar_no_banco(dados):
    """
    Retorna um log da operação para podermos desfazer depois.
    """
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()

        # 1. Verifica se a referência já existe
        cursor.execute("SELECT product_id, quantity FROM estoque WHERE hs_code = ?", (dados['referencia'],))
        resultado = cursor.fetchone()

        # Converte a nova quantidade para número (float)
        qtd_nova_vinda = float(dados['quantidade'].replace(',', '.'))

        if resultado:
            # --- CASO EXISTE: UPDATE (SOMA) ---
            id_existente, qtd_atual_texto = resultado
            qtd_total = float(str(qtd_atual_texto).replace(',', '.')) + qtd_nova_vinda
            
            cursor.execute("UPDATE estoque SET quantity = ?, price = ? WHERE product_id = ?", 
                           (str(qtd_total), dados['peso'], id_existente))
            conn.commit()
            conn.close()
            
            # ADICIONE O "total" AQUI
            return {"id": id_existente, "tipo": "update", "valor_estorno": qtd_nova_vinda, "total": qtd_total}

        else:
            # --- CASO NÃO EXISTE: INSERT (NOVO) ---
            cursor.execute("""
                INSERT INTO estoque (item_name, hs_code, price, quantity)
                VALUES (?, ?, ?, ?)
            """, (f"Entrada Bioecco Ref: {dados['referencia']}", dados['referencia'], dados['peso'], dados['quantidade']))
            
            last_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # ADICIONE O "total" AQUI
            return {"id": last_id, "tipo": "insert", "valor_estorno": qtd_nova_vinda, "total": qtd_nova_vinda}

    except Exception as e:
        print(f"Erro no banco: {e}")
        return None

def filtrar_dados_etiqueta(texto_bruto):
    ref_match = re.search(r"REF\.?\s*INTERNA:?\s*(\w+)", texto_bruto, re.IGNORECASE)
    peso_match = re.search(r"PESO:?\s*([\d.,]+)", texto_bruto, re.IGNORECASE)
    qtd_match = re.search(r"(?:Q|O|G)TD:?\s*([\d.,]+)", texto_bruto, re.IGNORECASE)

    return {
        "referencia": ref_match.group(1) if ref_match else "N/A",
        "peso": peso_match.group(1) if peso_match else "0",
        "quantidade": qtd_match.group(1) if qtd_match else "0"
    }

def ler_imagem_google(caminho_imagem):
    
    client = vision.ImageAnnotatorClient.from_service_account_json('chave_nova.json')

    with io.open(caminho_imagem, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    if texts:
        return texts[0].description
    return ""

# --- ROTA PRINCIPAL ---

@app.route("/whatsapp", methods=['POST'])
def reply_whatsapp():
    num_media = int(request.values.get('NumMedia', 0))
    corpo_mensagem = request.values.get('Body', '').strip().lower()
    numero_usuario = request.values.get('From')

    # --- 1. LÓGICA DE CORREÇÃO (O "DESFAZER") ---
    if corpo_mensagem == "corrigir":
        log_transacao = historico_usuarios.get(numero_usuario)
        
        if log_transacao:
            conn = sqlite3.connect('estoque.db')
            cursor = conn.cursor()
            
            # Preparamos os dados para registrar o "cancelamento" no Sheets
            dados_estorno = {
                "referencia": "ESTORNO/ERRO",
                "peso": "0",
                "quantidade": f"-{log_transacao['valor_estorno']}"
            }
            
            if log_transacao['tipo'] == "insert":
                # Se era um registro novo, DELETA a linha inteira
                cursor.execute("DELETE FROM estoque WHERE product_id = ?", (log_transacao['id'],))
                salvar_no_sheets(dados_estorno, "REGISTRO APAGADO")
                msg_feedback = "🗑️ Registro novo apagado do banco e da planilha."
            else:
                # Se era uma soma, SUBTRAI apenas o que foi adicionado
                cursor.execute("SELECT quantity FROM estoque WHERE product_id = ?", (log_transacao['id'],))
                qtd_no_banco = float(cursor.fetchone()[0].replace(',', '.'))
                nova_qtd_estornada = qtd_no_banco - log_transacao['valor_estorno']
                
                cursor.execute("UPDATE estoque SET quantity = ? WHERE product_id = ?", (str(nova_qtd_estornada), log_transacao['id']))
                salvar_no_sheets(dados_estorno, "ESTORNO DE SOMA")
                msg_feedback = f"⏪ Estorno realizado! Subtraí {log_transacao['valor_estorno']} do total na planilha."
            
            conn.commit()
            conn.close()
            historico_usuarios[numero_usuario] = None # Limpa histórico
            responder_whatsapp(numero_usuario, f"✅ *Correção feita!* {msg_feedback}")
        else:
            responder_whatsapp(numero_usuario, "❌ Não encontrei nada recente para corrigir.")
        return "OK", 200

    # --- 2. LÓGICA DE REGISTRO (QUANDO RECEBE FOTO) ---
    if num_media > 0:
        media_url = request.values.get('MediaUrl0')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{UPLOAD_FOLDER}/estoque_{timestamp}.jpg"
        
        response = requests.get(media_url, auth=(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
        
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            # Processa a imagem e salva
            texto_bruto = ler_imagem_google(filename)
            if os.path.exists(filename):
                    os.remove(filename)
            dados = filtrar_dados_etiqueta(texto_bruto)
            log_resultado = salvar_no_banco(dados)
            
            if log_resultado:
                historico_usuarios[numero_usuario] = log_resultado 
                
                # Pega o total atualizado direto do retorno do banco de dados
                total_atual = log_resultado.get('total', dados['quantidade'])
                
                # Chama a função enviando os dados e o total atual
                salvar_no_sheets(dados, total_atual)
                
                msg = (
                    f"✅ *Registrado!*\n"
                    f"📦 *Ref:* {dados['referencia']}\n"
                    f"🔢 *Qtd Adicionada:* {dados['quantidade']}\n\n"
                    f"_Para desfazer, digite_ *Corrigir*."
                )
                responder_whatsapp(numero_usuario, msg)
            
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000)