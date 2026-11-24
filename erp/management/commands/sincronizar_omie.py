"""Sincroniza fluxo de caixa e faturamento com a API do Omie.

Uso:
  python manage.py sincronizar_omie                     # mês anterior até hoje
  python manage.py sincronizar_omie --de 2026-01-01 --ate 2026-11-30
  python manage.py sincronizar_omie --so fluxo|vendas
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from erp import omie
from erp.models import SincronizacaoOmie


class Command(BaseCommand):
    help = "Busca dados do Omie (fluxo de caixa e faturamento)"

    def add_arguments(self, parser):
        parser.add_argument("--de", type=date.fromisoformat)
        parser.add_argument("--ate", type=date.fromisoformat)
        parser.add_argument("--so", choices=["fluxo", "vendas"])
        parser.add_argument("--usuario", default="agendado")
        parser.add_argument("--registro", type=int, help="id de SincronizacaoOmie já criado pela tela")
        parser.add_argument("--ano-corrente", action="store_true", help="de 1º de janeiro (do ano de 60 dias atrás) até hoje — usado pela auditoria")

    def handle(self, *a, de=None, ate=None, so=None, usuario="agendado", registro=None, ano_corrente=False, **kw):
        hoje = date.today()
        ate = ate or hoje
        if ano_corrente:
            de = date((hoje - timedelta(days=60)).year, 1, 1)
        de = de or (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
        if registro:
            reg = SincronizacaoOmie.objects.get(pk=registro)
        else:
            if SincronizacaoOmie.objects.filter(status="rodando", inicio__gte=timezone.now() - timedelta(hours=1)).exists():
                raise CommandError("Já existe uma sincronização em andamento")
            reg = SincronizacaoOmie.objects.create(de=de, ate=ate, usuario=usuario)
        try:
            msg = omie.sincronizar(de, ate, fluxo=so != "vendas", vendas=so != "fluxo", saida=self.stdout.write, registro=reg)
            reg.status, reg.mensagem = "ok", msg
        except Exception as e:  # registra o erro para aparecer na tela
            reg.status, reg.mensagem = "erro", str(e)[:2000]
            raise CommandError(str(e))
        finally:
            reg.fim = timezone.now()
            reg.save()
        self.stdout.write(self.style.SUCCESS(f"{de:%d/%m/%Y} a {ate:%d/%m/%Y}: {msg}"))
