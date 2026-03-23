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

def verificar_alerta_minimo(planilha_id, referencia):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    
    try:
        celula = aba.find(referencia.upper(), in_column=3)
        linha = celula.row
        valores = aba.row_values(linha)
        
        
        qtd_atual = float(valores[3])
        qtd_minima = float(valores[5]) if len(valores) >= 6 and valores[5] else 0
        
        if qtd_atual <= qtd_minima:
            return True, valores[1], qtd_atual # Retorna True, Nome do Produto e Qtd
    except:
        pass
    return False, None, 0

def consultar_estoque_geral(planilha_id):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    dados = aba.get_all_values()
    
    if len(dados) <= 1:
        return "📦 O stock está vazio."

    msg = "*📋 OPTISCAN - RELATÓRIO*\n\n"
    # Pula a linha 1 (cabeçalhos)
    for linha in dados[1:]:
        try:
            # Índices: B=1 (Nome), C=2 (Ref), D=3 (Qtd), E=4 (Espec)
            qtd = float(linha[3])
            if qtd > 0:  # Lista apenas o que tem saldo
                msg += f"🔹 *{linha[1]}* ({linha[2]})\n   Qtd: {linha[3]} | {linha[4]}\n\n"
        except (ValueError, IndexError):
            continue
            
    return msg + f"_Gerado às: {datetime.now().strftime('%H:%M')}_"

        
    