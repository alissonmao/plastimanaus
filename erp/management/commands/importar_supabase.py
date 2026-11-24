"""Copia todos os dados do Supabase do projeto Lovable para o banco do Django.

Uso:  python manage.py importar_supabase [--limpar]
Requer SUPABASE_URL e SUPABASE_KEY no .env. Mantém os mesmos UUIDs.
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from erp import models as m

# Ordem respeita as chaves estrangeiras.
TABELAS = [
    ("setores", m.Setor, {}), ("familias", m.Familia, {"setor_id": "setor_id"}),
    ("maquinas", m.Maquina, {"familia_id": "familia_id"}), ("turnos", m.Turno, {"setor_id": "setor_id"}),
    ("produtos", m.Produto, {}), ("cores", m.Cor, {}), ("tipos_sacola", m.TipoSacola, {}), ("medidas", m.Medida, {}),
    ("clientes", m.Cliente, {}), ("ordens_producao", m.OrdemProducao, {"cliente_id": "cliente_id"}),
    ("apontamentos", m.Apontamento, {}), ("vendas", m.Venda, {}), ("vendas_plasti", m.VendaPlasti, {}),
    ("metas_vendedor", m.MetaVendedor, {}), ("fluxo_caixa", m.FluxoCaixa, {}),
]


class Command(BaseCommand):
    help = "Importa os dados do Supabase (projeto Lovable ERP)"

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true", help="Apaga os dados atuais antes de importar")

    def buscar(self, tabela):
        url, key = settings.SUPABASE_URL.rstrip("/"), settings.SUPABASE_KEY
        out, ini = [], 0
        while True:
            r = requests.get(f"{url}/rest/v1/{tabela}", params={"select": "*", "order": "id"},
                             headers={"apikey": key, "Authorization": f"Bearer {key}", "Range": f"{ini}-{ini + 999}"}, timeout=60)
            if r.status_code >= 400:
                raise CommandError(f"{tabela}: HTTP {r.status_code} {r.text[:200]}")
            lote = r.json()
            out += lote
            if len(lote) < 1000:
                return out
            ini += 1000

    def handle(self, *args, limpar=False, **kw):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise CommandError("Defina SUPABASE_URL e SUPABASE_KEY no .env")
        dados = {t: self.buscar(t) for t, _, _ in TABELAS}
        with transaction.atomic():
            if limpar:
                for _, modelo, _ in reversed(TABELAS):
                    modelo.objects.all().delete()
            for tabela, modelo, _ in TABELAS:
                campos = {f.attname for f in modelo._meta.concrete_fields}
                objs = []
                for row in dados[tabela]:
                    row.pop("created_by", None)  # usuários do Supabase não existem aqui
                    objs.append(modelo(**{k: v for k, v in row.items() if k in campos}))
                modelo.objects.bulk_create(objs, batch_size=1000, ignore_conflicts=True)
                # created_at é auto_now_add: restaura o valor original
                if "created_at" in campos:
                    for row in dados[tabela]:
                        if row.get("created_at"):
                            modelo.objects.filter(pk=row["id"]).update(created_at=row["created_at"])
                self.stdout.write(f"{tabela}: {len(objs)} registros")
        self.stdout.write(self.style.SUCCESS("Importação concluída."))
