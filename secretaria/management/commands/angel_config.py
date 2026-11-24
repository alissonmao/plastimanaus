"""Gera/atualiza a configuração do Angel (OpenClaw): só responde aos números cadastrados, usa a chave da API da Anthropic
(não o login da assinatura) e instala a habilidade erp-secretaria. Roda na instalação e a cada publicação."""
import json
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *a, **kw):
        from secretaria import config
        from secretaria.models import PerfilSecretaria
        base = Path(os.path.expanduser("~/.openclaw"))
        base.mkdir(mode=0o700, exist_ok=True)
        arq = base / "openclaw.json"
        cfg = json.loads(arq.read_text()) if arq.exists() else {}
        numeros = sorted({n for p in PerfilSecretaria.objects.exclude(whatsapp="") for n in p.whatsapp_variantes()})
        wa = cfg.setdefault("channels", {}).setdefault("whatsapp", {})
        wa["dmPolicy"] = "allowlist"
        wa["allowFrom"] = numeros or ["+0"]   # sem número cadastrado: não responde a ninguém
        wa["groupPolicy"] = "disabled"
        env = cfg.setdefault("env", {})
        chave = config.obter("ANTHROPIC_API_KEY")
        if chave:
            env["ANTHROPIC_API_KEY"] = chave
        # habilidade
        destino = base / "workspace" / "skills" / "erp-secretaria"
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(settings.BASE_DIR) / "deploy" / "angel" / "skills" / "erp-secretaria" / "SKILL.md", destino / "SKILL.md")
        (base / "erp-token").write_text(config.token_angel())
        os.chmod(base / "erp-token", 0o600)
        arq.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        os.chmod(arq, 0o600)
        self.stdout.write(f"Angel configurado: {len(numeros)} número(s) autorizado(s).")
