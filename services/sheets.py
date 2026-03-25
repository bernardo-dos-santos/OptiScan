import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

from services.uteis import formatar_br

def _obter_cliente_gspread():
    caminho_absoluto = os.path.abspath('chave_nova.json')
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(caminho_absoluto, scope)
    return gspread.authorize(creds)
        
def atualizar_sheets(dados, total_banco, planilha_id):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    
    # 1. DATA FORMATADA (Apenas dia/mês/ano)
    data_hora = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y")

    ref_limpa = str(dados.get('referencia', 'N/A')).upper()
    nome_recebido = dados.get('nome')
    espec_recebida = dados.get('especificacao')

    try:
        celula = aba.find(ref_limpa, in_column=3)
    except gspread.exceptions.CellNotFound:
        celula = None

    if celula:
        linha = celula.row
        # Lê a linha atual para não apagar o Estoque Mínimo (Coluna E)
        valores_linha = aba.row_values(linha)
        
        # Garante que a lista tenha 7 posições para evitar erros de índice
        while len(valores_linha) < 7: 
            valores_linha.append("")
            
        # Atualiza apenas o que importa:
        valores_linha[0] = data_hora # Coluna A (Data)
        if nome_recebido and nome_recebido != "PRODUTO DESCONHECIDO": 
            valores_linha[1] = nome_recebido # Coluna B (Nome)
        valores_linha[3] = total_banco # Coluna D (Quantidade)
        if espec_recebida: 
            valores_linha[5] = espec_recebida # Coluna F (Especificação)
        valores_linha[6] = "✅ Pelo Zap" # Coluna G (Status)
        
        aba.update(f"A{linha}:G{linha}", [valores_linha])
    else:
        # Nova linha: A(Data), B(Nome), C(Ref), D(Qtd), E(Minimo vazio), F(Espec), G(Status)
        aba.append_row([data_hora, nome_recebido or "N/A", ref_limpa, total_banco, "", espec_recebida or "", "✅ Novo via Zap"])
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
                msg += f"🔹 *{linha[1]}* ({linha[2]})\n   Qtd: {formatar_br(linha[3])} | {linha[4]}\n\n"
        except (ValueError, IndexError):
            continue
            
    # Ajuste Fuso
    hora_atual = (datetime.utcnow() - timedelta(hours=3)).strftime('%H:%M')
    return msg + f"_Gerado às: {hora_atual}_"

def buscar_produto_por_nome_ou_id(planilha_id, termo):
    client = _obter_cliente_gspread()
    aba = client.open_by_key(planilha_id).sheet1
    dados = aba.get_all_values()
    
    resultados = []
    termo = str(termo).upper().strip()
    
    # Pula cabeçalho
    for linha in dados[1:]:
        if len(linha) >= 3:
            nome = str(linha[1]).upper()
            ref = str(linha[2]).upper()
            
            # Se bater o ID exato, retorna direto (prioridade máxima)
            if termo == ref:
                return [{'nome': linha[1], 'ref': ref}]
            
            # Se o termo digitado fizer parte do nome do produto, adiciona na lista
            if termo in nome:
                resultados.append({'nome': linha[1], 'ref': ref})
                
    return resultados
        
    