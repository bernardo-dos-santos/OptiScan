import hashlib
import hmac

import pytest

from services import meta

SEGREDO = "segredo-de-teste"
CORPO = b'{"object": "whatsapp_business_account"}'


def assinar(corpo, segredo=SEGREDO):
    digest = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    monkeypatch.delenv("ALLOW_UNSIGNED_WEBHOOKS", raising=False)
    monkeypatch.setattr(meta, "APP_SECRET", SEGREDO)


def test_assinatura_valida_e_aceita():
    assert meta.validar_assinatura_meta(CORPO, assinar(CORPO)) is True


def test_assinatura_de_outro_segredo_e_recusada():
    assert meta.validar_assinatura_meta(CORPO, assinar(CORPO, "outro")) is False


def test_corpo_adulterado_e_recusado():
    assinatura = assinar(CORPO)
    assert meta.validar_assinatura_meta(CORPO + b" ", assinatura) is False


def test_sem_assinatura_e_recusado():
    assert meta.validar_assinatura_meta(CORPO, None) is False


def test_sem_app_secret_falha_fechada(monkeypatch):
    monkeypatch.setattr(meta, "APP_SECRET", None)
    assert meta.validar_assinatura_meta(CORPO, assinar(CORPO)) is False


def test_modo_dev_explicito_libera_sem_assinatura(monkeypatch):
    monkeypatch.setattr(meta, "APP_SECRET", None)
    monkeypatch.setenv("ALLOW_UNSIGNED_WEBHOOKS", "true")
    assert meta.validar_assinatura_meta(CORPO, None) is True
