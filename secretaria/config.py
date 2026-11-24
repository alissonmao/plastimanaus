"""Chaves dos serviços externos: cadastradas na tela Sistema → Integrações (criptografadas no banco).
Se não houver nada no banco, usa o .env como reserva."""
import os
import secrets

from django.conf import settings
from django.core.cache import cache

# (nome, título, ajuda, secreto, opcional)
CHAVES = [
    ("ANTHROPIC_API_KEY", "Anthropic: chave da API", "console.anthropic.com → API Keys. Começa com sk-ant-. Usada na IA (rascunhos, triagem, diário, Angel).", True),
    ("ELEVENLABS_API_KEY", "ElevenLabs: chave da API", "elevenlabs.io → Profile → API Keys. Voz do Angel.", True),
    ("ELEVENLABS_VOICE_ID", "ElevenLabs: ID da voz feminina", "Na biblioteca de vozes, copie o Voice ID da voz escolhida para o Angel.", False),
    ("ANGEL_WHATSAPP", "WhatsApp do Angel (número dedicado)", "Número do chip do Angel, com DDD. O pareamento é por QR code.", False),
    ("ANGEL_TOKEN", "Token interno do Angel", "Gerado automaticamente. É a senha que o Angel usa para falar com o ERP. Gere outro para revogar.", True),
]
NOMES = [c[0] for c in CHAVES]
CACHE = 30


def obter(nome: str) -> str:
    chave = f"sec-cfg-{nome}"
    v = cache.get(chave)
    if v is None:
        from .models import Integracao
        obj = Integracao.objects.filter(nome=nome).first()
        v = obj.valor if obj and obj.valor_cifrado else (getattr(settings, nome, "") or os.getenv(nome, ""))
        cache.set(chave, v, CACHE)
    return v


def salvar(nome: str, valor: str, usuario=None):
    from .models import Integracao
    obj, _ = Integracao.objects.get_or_create(nome=nome)
    obj.valor = valor.strip()
    obj.atualizado_por = usuario
    obj.ultimo_erro = ""
    obj.testado_em = None
    obj.save()
    cache.delete(f"sec-cfg-{nome}")
    return obj


def token_angel() -> str:
    t = obter("ANGEL_TOKEN")
    if not t:
        t = secrets.token_urlsafe(32)
        salvar("ANGEL_TOKEN", t)
    return t


def mascarar(v: str) -> str:
    if not v:
        return ""
    return ("•" * 8) + v[-4:] if len(v) > 8 else "•" * len(v)
