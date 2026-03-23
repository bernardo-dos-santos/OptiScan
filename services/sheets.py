import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

def _obter_cliente_gspread():
    caminho_absoluto = os.path.abspath('chave_nova.json')
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(caminho_absoluto, scope)
    return gspread.authorize(creds)
        
def atualizar_sheets(dados, total_banco, planilha_id):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    ref_limpa = str(dados.get('referencia', 'N/A')).upper()
    # Pega os dados sem forçar um valor padrão imediato
    nome_recebido = dados.get('nome')
    espec_recebida = dados.get('especificacao')

    try:
        celula = aba.find(ref_limpa, in_column=3)
    except gspread.exceptions.CellNotFound:
        celula = None

    if celula:
        linha = celula.row
        # Atualiza SEMPRE a Data e a Quantidade
        aba.update_acell(f'A{linha}', data_hora)
        aba.update_acell(f'D{linha}', str(total_banco))
        
        # Só atualiza Nome e Especificação se a IA os capturou (evita apagar no estorno/manual)
        if nome_recebido:
            aba.update_acell(f'B{linha}', str(nome_recebido))
        if espec_recebida:
            aba.update_acell(f'E{linha}', str(espec_recebida))
    else:
        # Se for uma linha nova, aplica o valor padrão caso algum campo venha vazio
        nome_final = str(nome_recebido if nome_recebido else 'Produto Sem Nome')
        espec_final = str(espec_recebida if espec_recebida else 'N/A')
        
        nova_linha = [data_hora, nome_final, ref_limpa, total_banco, espec_final]
        aba.append_row(nova_linha)

        
    