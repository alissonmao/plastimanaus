"""Serviços externos: testes das chaves, voz (ElevenLabs → Edge TTS) e envio pelo WhatsApp do Angel (OpenClaw)."""
import asyncio
import logging
import shutil
import subprocess
import tempfile

import requests

from . import config

log = logging.getLogger(__name__)
TESTAVEIS = {"ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ANGEL_WHATSAPP"}
VOZ_EDGE = "pt-BR-FranciscaNeural"


class ErroServico(Exception):
    pass


# ---------------------------------------------------------------- testes
def testar(nome):
    try:
        if nome == "ANTHROPIC_API_KEY":
            import anthropic
            k = config.obter(nome)
            if not k:
                return False, "Chave não cadastrada."
            anthropic.Anthropic(api_key=k, timeout=20.0, max_retries=0).models.list(limit=1)
            return True, "Anthropic respondeu: chave válida."
        if nome == "ELEVENLABS_API_KEY":
            r = requests.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": config.obter(nome)}, timeout=15)
            return (True, "ElevenLabs respondeu: chave válida.") if r.ok else (False, f"ElevenLabs recusou a chave (HTTP {r.status_code}).")
        if nome == "ELEVENLABS_VOICE_ID":
            r = requests.get(f"https://api.elevenlabs.io/v1/voices/{config.obter(nome)}",
                             headers={"xi-api-key": config.obter("ELEVENLABS_API_KEY")}, timeout=15)
            return (True, f"Voz encontrada: {r.json().get('name', '')}.") if r.ok else (False, f"Voz não encontrada (HTTP {r.status_code}).")
        if nome == "ANGEL_WHATSAPP":
            if not shutil.which("openclaw"):
                return False, "O Angel (OpenClaw) ainda não está instalado no servidor."
            r = subprocess.run(["openclaw", "channels", "status", "--channel", "whatsapp"], capture_output=True, text=True, timeout=30)
            return (r.returncode == 0, (r.stdout or r.stderr).strip()[:300] or "Sem resposta.")
    except Exception as e:  # rede, chave inválida etc.
        return False, f"Falhou: {type(e).__name__}: {str(e)[:200]}"
    return False, "Sem teste para este item."


# ---------------------------------------------------------------- voz
def falar(texto: str) -> tuple[bytes, str]:
    """Texto → áudio MP3 com a voz do Angel. ElevenLabs se houver chave; senão Microsoft Edge (Francisca). Nunca OpenAI."""
    texto = (texto or "").strip()[:4500]
    if not texto:
        raise ErroServico("Nada para falar.")
    chave, voz = config.obter("ELEVENLABS_API_KEY"), config.obter("ELEVENLABS_VOICE_ID")
    if chave and voz:
        try:
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voz}?output_format=mp3_44100_128",
                              headers={"xi-api-key": chave, "accept": "audio/mpeg"},
                              json={"text": texto, "model_id": "eleven_multilingual_v2"}, timeout=60)
            if r.ok and r.content:
                return r.content, "elevenlabs"
            log.warning("ElevenLabs falhou: HTTP %s", r.status_code)
        except requests.RequestException as e:
            log.warning("ElevenLabs falhou: %s", e)
    try:
        return asyncio.run(_edge(texto)), "edge"
    except Exception as e:
        log.warning("Edge TTS falhou: %s", e)
    try:
        return _piper(texto), "piper"
    except Exception as e:
        raise ErroServico(f"Não consegui gerar a voz ({e}).") from e


def _piper(texto):
    """Último recurso, local e grátis: Piper (se instalado com o Angel) + ffmpeg para MP3."""
    import os
    modelo = os.getenv("PIPER_MODELO", "/opt/piper/pt_BR-faber-medium.onnx")
    if not (shutil.which("piper") and shutil.which("ffmpeg") and os.path.exists(modelo)):
        raise ErroServico("Piper não instalado")
    with tempfile.TemporaryDirectory() as d:
        wav, mp3 = os.path.join(d, "a.wav"), os.path.join(d, "a.mp3")
        subprocess.run(["piper", "--model", modelo, "--output_file", wav], input=texto, text=True, check=True, timeout=120, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, mp3], check=True, timeout=60)
        return open(mp3, "rb").read()


async def _edge(texto):
    import edge_tts
    partes = []
    async for ch in edge_tts.Communicate(texto, VOZ_EDGE, rate="+5%").stream():
        if ch["type"] == "audio":
            partes.append(ch["data"])
    if not partes:
        raise ErroServico("Edge TTS não devolveu áudio.")
    return b"".join(partes)


# ---------------------------------------------------------------- WhatsApp (via OpenClaw)
def whatsapp_disponivel() -> bool:
    return bool(config.obter("ANGEL_WHATSAPP")) and bool(shutil.which("openclaw"))


def enviar_whatsapp(numero_e164: str, texto: str = "", audio_mp3: bytes | None = None):
    if not whatsapp_disponivel():
        raise ErroServico("WhatsApp do Angel ainda não configurado.")
    cmd = ["openclaw", "message", "send", "--channel", "whatsapp", "--target", numero_e164]
    arq = None
    try:
        if audio_mp3:
            arq = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            arq.write(audio_mp3)
            arq.close()
            cmd += ["--media", arq.name]
            if texto:
                cmd += ["--message", texto]
        else:
            cmd += ["--message", texto]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise ErroServico((r.stderr or r.stdout or "falha").strip()[:300])
    finally:
        if arq:
            import os
            os.unlink(arq.name)
