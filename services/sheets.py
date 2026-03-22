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
    nome_limpo = str(dados.get('nome', 'Produto Sem Nome'))
    espec_limpa = str(dados.get('especificacao', 'N/A'))

    try:
        # Agora busca a referência especificamente na coluna C (3)
        celula = aba.find(ref_limpa, in_column=3)
    except gspread.exceptions.CellNotFound:
        celula = None

    if celula:
        linha = celula.row
        # Atualiza os dados mantendo a ordem
        aba.update_acell(f'A{linha}', data_hora)
        aba.update_acell(f'B{linha}', nome_limpo)
        aba.update_acell(f'D{linha}', str(total_banco))
        aba.update_acell(f'E{linha}', espec_limpa)
    else:
        # Cria linha nova na ordem exata: Data, Nome, Ref, Quant, Spec
        nova_linha = [data_hora, nome_limpo, ref_limpa, total_banco, espec_limpa]
        aba.append_row(nova_linha)

        
    