"""Áudio → texto com Whisper local (modelo small, português). Instalado junto com o Angel (faster-whisper)."""
import threading

from django.conf import settings

_modelo = None
_trava = threading.Lock()


class ErroTranscricao(Exception):
    pass


def disponivel():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcrever(caminho: str) -> str:
    global _modelo
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ErroTranscricao("Whisper ainda não instalado no servidor.") from e
    with _trava:
        if _modelo is None:
            _modelo = WhisperModel(getattr(settings, "WHISPER_MODELO", "small"), device="cpu", compute_type="int8", cpu_threads=1)
        partes, _ = _modelo.transcribe(caminho, language="pt", beam_size=1, vad_filter=True)
        return " ".join(p.text.strip() for p in partes).strip()
