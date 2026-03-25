def formatar_br(valor):
    """Formata número para o padrão brasileiro: 2.000.000 ou 2.000.000,50"""
    try:
        valor = float(valor)
        if valor % 1 == 0:
            return f"{int(valor):,}".replace(",", ".")
        else:
            return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)

def tratar_numero_brasileiro(texto):
    """
    Trata strings de números para o padrão Python.
    Regra OptiScan:
    - Se tem vírgula (80,000 ou 1,2): vira decimal (80.0 ou 1.2)
    - Se tem ponto e 3 casas (80.000): vira milhar (80000.0)
    - Se tem ponto e 1-2 casas (1.2): vira decimal (1.2)
    """
    if not texto: return 0.0
    texto = str(texto).strip().replace(' ', '')
    
    if ',' in texto:
        return float(texto.replace(',', '.'))
    
    if '.' in texto:
        partes = texto.split('.')
        if len(partes[-1]) == 3:
            return float(texto.replace('.', ''))
        return float(texto)
        
    return float(texto)