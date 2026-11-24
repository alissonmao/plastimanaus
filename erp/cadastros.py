"""Configuração das telas de cadastro (equivalente às rotas /cadastros/* do Lovable)."""
from django import forms

from .models import Cliente, Cor, Familia, Maquina, Medida, OrdemProducao, Produto, Setor, TipoSacola, Turno

sim = lambda o: "Sim" if o.ativo else "Não"  # noqa: E731
hora = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")

CADASTROS = {
    "maquinas": dict(titulo="Máquinas", model=Maquina, select=["familia__setor"],
                     campos=["codigo", "descricao", "familia", "capacidade_kg_h", "ativo"],
                     colunas=[("Código", "codigo"), ("Descrição", "descricao"), ("Família", lambda o: o.familia.nome),
                              ("Setor", lambda o: o.familia.setor.nome), ("Cap. kg/h", "capacidade_kg_h"), ("Ativo", sim)]),
    "familias": dict(titulo="Famílias", model=Familia, select=["setor"], campos=["nome", "setor", "ativo"],
                     colunas=[("Nome", "nome"), ("Setor", lambda o: o.setor.nome), ("Ativo", sim)]),
    "setores": dict(titulo="Setores", model=Setor, campos=["nome", "processo", "ativo"],
                    colunas=[("Nome", "nome"), ("Processo", lambda o: o.get_processo_display()), ("Ativo", sim)]),
    "turnos": dict(titulo="Turnos", model=Turno, campos=["codigo", "processo", "hora_inicio", "hora_fim", "ativo"],
                   widgets={"hora_inicio": hora, "hora_fim": hora},
                   colunas=[("Código", "codigo"), ("Processo", lambda o: o.get_processo_display()),
                            ("Início", "hora_inicio"), ("Fim", "hora_fim"), ("Horas", lambda o: o.horas), ("Ativo", sim)]),
    "produtos": dict(titulo="Produtos (tipos)", model=Produto, campos=["nome", "ativo"], colunas=[("Nome", "nome"), ("Ativo", sim)]),
    "cores": dict(titulo="Cores", model=Cor, campos=["nome", "ativo"], colunas=[("Nome", "nome"), ("Ativo", sim)]),
    "tipos-sacola": dict(titulo="Tipos de Sacola", model=TipoSacola, campos=["nome", "ativo"], colunas=[("Nome", "nome"), ("Ativo", sim)]),
    "medidas": dict(titulo="Medidas", model=Medida, campos=["tipo", "valor", "ativo"],
                    colunas=[("Tipo", lambda o: o.get_tipo_display()), ("Valor", lambda o: o.valor.normalize()), ("Ativo", sim)]),
    "clientes": dict(titulo="Clientes", model=Cliente, campos=["nome", "ativo"], colunas=[("Nome", "nome"), ("Ativo", sim)]),
    "ordens-producao": dict(titulo="Ordens de Produção", model=OrdemProducao, select=["cliente"], campos=["numero", "cliente", "ativo"],
                            colunas=[("Número", "numero"), ("Cliente", lambda o: o.cliente.nome), ("Ativo", sim)]),
}
