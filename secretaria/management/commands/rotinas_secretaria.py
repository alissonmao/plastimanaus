import fcntl
import os
import tempfile

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rotinas da Secretaria (lembretes, agenda, triagem, briefing, análise semanal, envio de avisos). Roda a cada minuto."

    def add_arguments(self, parser):
        parser.add_argument("--so", nargs="*", help="Só estes passos (lembretes agenda triagem briefing analise enviar)")

    def handle(self, *args, so=None, **kw):
        trava = open(os.path.join(tempfile.gettempdir(), "rotinas_secretaria.lock"), "w")
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # a rodada anterior ainda está trabalhando
        from secretaria.rotinas import rodar
        passos = rodar(so=set(so) if so else None)
        if kw.get("verbosity", 1) > 1:
            self.stdout.write(", ".join(passos))
