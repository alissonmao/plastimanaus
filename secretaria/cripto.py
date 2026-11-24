"""Criptografia das senhas guardadas no banco. A chave fica só no .env (SECRETARIA_CHAVE)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    chave = settings.SECRETARIA_CHAVE
    if not chave:
        if not settings.DEBUG:
            raise ImproperlyConfigured("Defina SECRETARIA_CHAVE no .env")
        chave = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(chave.encode())


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as e:
        raise ImproperlyConfigured("Não foi possível abrir a senha: a SECRETARIA_CHAVE mudou?") from e
