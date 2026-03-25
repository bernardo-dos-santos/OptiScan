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