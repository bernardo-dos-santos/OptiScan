import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

def _obter_cliente_gspread():
    caminho_absoluto = os.path.abspath('chave_nova.json')
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(caminho_absoluto, scope)
    return gspread.authorize(creds)

def buscar_saldo_na_planilha(product_id, planilha_id):
    try:
        client = _obter_cliente_gspread()
        sheet = client.open_by_key(planilha_id).sheet1
        celula = sheet.find(product_id)
        if celula:
            valor_texto = sheet.cell(celula.row, 4).value
            return float(str(valor_texto).replace(',', '.')) if valor_texto else 0.0
        return 0.0
    except Exception as e:
        print(f"Erro Sheet: {e}")
        return 0.0

def atualizar_sheets(dados, total_banco, planilha_id):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    ref_limpa = dados.get('referencia', 'N/A')
    peso_limpo = dados.get('peso', 0)

    try:
        celula = aba.find(ref_limpa)
    except gspread.exceptions.CellNotFound:
        celula = None

    if celula:
        linha = celula.row
        aba.update_acell(f'A{linha}', data_hora)
        aba.update_acell(f'D{linha}', str(total_banco))
    else:
        nova_linha = [data_hora, ref_limpa, peso_limpo, str(total_banco), "Ativo"]
        aba.append_row(nova_linha)
    