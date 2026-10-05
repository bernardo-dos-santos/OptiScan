import pytest

from services.uteis import formatar_br, tratar_numero_brasileiro


@pytest.mark.parametrize("entrada, esperado", [
    (2000000, "2.000.000"),
    (2000000.0, "2.000.000"),
    (1500.5, "1.500,50"),
    (0, "0"),
])
def test_formatar_br(entrada, esperado):
    assert formatar_br(entrada) == esperado


def test_formatar_br_valor_invalido_devolve_texto():
    assert formatar_br("abc") == "abc"


@pytest.mark.parametrize("entrada, esperado", [
    ("80,000", 80.0),        # vírgula = decimal
    ("1,2", 1.2),
    ("80.000", 80000.0),     # ponto + 3 casas = milhar
    ("1.2", 1.2),            # ponto + 1-2 casas = decimal
    ("1.234,56", 1234.56),   # milhar com ponto e decimal com vírgula
    ("  3000 ", 3000.0),
    (3000, 3000.0),
    ("", 0.0),
    (None, 0.0),
])
def test_tratar_numero_brasileiro(entrada, esperado):
    assert tratar_numero_brasileiro(entrada) == pytest.approx(esperado)
