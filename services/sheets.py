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
    
    data_hora = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y")

    ref_limpa = str(dados.get('referencia', 'N/A')).upper()
    nome_recebido = dados.get('nome')
    espec_recebida = dados.get('especificacao')
    
    # PEGANDO O DINHEIRO DO BANCO AQUI
    custo_unitario = dados.get('custo_unitario', 0.0)
    preco_venda = dados.get('preco_venda', 0.0)

    try:
        celula = aba.find(ref_limpa, in_column=3)
    except gspread.exceptions.CellNotFound:
        celula = None

    if celula:
        linha = celula.row
        valores_linha = aba.row_values(linha)
        
        # AGORA SÃO 9 COLUNAS (DE A ATÉ I)
        while len(valores_linha) < 9: 
            valores_linha.append("")
            
        valores_linha[0] = data_hora 
        if nome_recebido and nome_recebido != "PRODUTO DESCONHECIDO": 
            valores_linha[1] = nome_recebido 
        valores_linha[3] = total_banco 
        if espec_recebida: 
            valores_linha[5] = espec_recebida 
        valores_linha[6] = "✅ Atualizado  " 
        valores_linha[7] = custo_unitario # Escreve o Custo na Coluna H
        valores_linha[8] = preco_venda    # Escreve o Preço na Coluna I
        
        # UPDATE EXPANDIDO ATÉ A COLUNA I
        aba.update(f"A{linha}:I{linha}", [valores_linha], value_input_option="USER_ENTERED")
    else:
        # NOVA LINHA AGORA RECEBE OS 9 VALORES
        aba.append_row([data_hora, nome_recebido or "N/A", ref_limpa, total_banco, "", espec_recebida or "", "✅ Novo ", custo_unitario, preco_venda], value_input_option="USER_ENTERED")
        
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
            # Pega a string (ex: "2.000,50"), tira o ponto de milhar e troca vírgula por ponto
            qtd_str = str(linha[3]).strip().replace('.', '').replace(',', '.')
            if not qtd_str: 
                continue
                
            qtd = float(qtd_str)
            if qtd > 0:
                # Usa o formatar_br para exibir bonito no Zap
                msg += f"🔹 *{linha[1]}* ({linha[2]})\n   Qtd: {formatar_br(qtd)} | Mín: {linha[4]}\n\n"
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
        
    