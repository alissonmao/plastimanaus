"""Modelos do ERP Plasti Manaus.

Espelham as tabelas do projeto Lovable (Supabase), com os mesmos UUIDs,
para permitir importar os dados existentes sem perder relacionamentos.
"""
import uuid

from django.conf import settings
from django.db import models

PROCESSO_EXTRUSAO = "extrusao"
PROCESSO_CORTE = "corte"
PROCESSOS = [(PROCESSO_EXTRUSAO, "Extrusão"), (PROCESSO_CORTE, "Corte")]
PRODUTO_BOBINA = "Bobina"


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        abstract = True


class Cadastro(Base):
    nome = models.CharField(max_length=200, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["nome"]

    def __str__(self):
        return self.nome


# ---------------------------------------------------------------- Cadastros
class Setor(Cadastro):
    processo = models.CharField(max_length=20, choices=PROCESSOS)

    class Meta(Cadastro.Meta):
        db_table = "setores"
        verbose_name_plural = "setores"


class Familia(Cadastro):
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name="familias")

    class Meta(Cadastro.Meta):
        db_table = "familias"
        verbose_name = "família"


class Maquina(Base):
    codigo = models.CharField("código", max_length=50, unique=True)
    descricao = models.CharField("descrição", max_length=200)
    familia = models.ForeignKey(Familia, on_delete=models.PROTECT, related_name="maquinas")
    capacidade_kg_h = models.DecimalField("capacidade kg/h", max_digits=12, decimal_places=3, null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "maquinas"
        ordering = ["codigo"]
        verbose_name = "máquina"

    def __str__(self):
        return self.descricao

    @property
    def setor(self):
        return self.familia.setor


class Turno(Base):
    codigo = models.CharField("código", max_length=20, unique=True)
    processo = models.CharField(max_length=20, choices=PROCESSOS)
    setor = models.ForeignKey(Setor, on_delete=models.SET_NULL, null=True, blank=True,
                              help_text="Obsoleto: mantido por compatibilidade; use o processo.")
    hora_inicio = models.TimeField("início", null=True, blank=True)
    hora_fim = models.TimeField("fim", null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "turnos"
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo

    @property
    def horas(self):
        """hora_fim − hora_inicio (+24 h quando passa da meia-noite); None sem horário."""
        if not self.hora_inicio or not self.hora_fim:
            return None
        ini = self.hora_inicio.hour * 60 + self.hora_inicio.minute
        fim = self.hora_fim.hour * 60 + self.hora_fim.minute
        d = fim - ini
        if d <= 0:
            d += 24 * 60
        return d / 60


class Produto(Cadastro):
    class Meta(Cadastro.Meta):
        db_table = "produtos"


class Cor(Cadastro):
    class Meta(Cadastro.Meta):
        db_table = "cores"
        verbose_name_plural = "cores"


class TipoSacola(Cadastro):
    class Meta(Cadastro.Meta):
        db_table = "tipos_sacola"
        ordering = ["created_at"]
        verbose_name = "tipo de sacola"
        verbose_name_plural = "tipos de sacola"


class Medida(Base):
    TIPOS = [("largura", "Largura"), ("comprimento", "Comprimento"), ("espessura", "Espessura")]
    tipo = models.CharField(max_length=20, choices=TIPOS)
    valor = models.DecimalField(max_digits=12, decimal_places=4)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "medidas"
        ordering = ["tipo", "valor"]
        constraints = [models.UniqueConstraint(fields=["tipo", "valor"], name="medida_unica")]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.valor.normalize()}"


class Cliente(Cadastro):
    class Meta(Cadastro.Meta):
        db_table = "clientes"


class OrdemProducao(Base):
    numero = models.CharField("número", max_length=50, unique=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="ordens")
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "ordens_producao"
        ordering = ["numero"]
        verbose_name = "ordem de produção"
        verbose_name_plural = "ordens de produção"

    def __str__(self):
        return self.numero


# ---------------------------------------------------------------- Produção
class Apontamento(Base):
    data = models.DateField(db_index=True)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT)
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, verbose_name="máquina")
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, null=True, blank=True)
    cor = models.ForeignKey(Cor, on_delete=models.PROTECT, null=True, blank=True)
    tipo_sacola = models.ForeignKey(TipoSacola, on_delete=models.PROTECT, null=True, blank=True, verbose_name="tipo de sacola")
    largura_mm = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    comprimento_mm = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    espessura_mm = models.DecimalField(max_digits=12, decimal_places=5, null=True, blank=True)
    op = models.CharField("OP", max_length=50, blank=True, null=True)
    ok_kg = models.DecimalField("produzido OK kg", max_digits=14, decimal_places=3, default=0)
    apara_kg = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    alca_kg = models.DecimalField("alça kg", max_digits=14, decimal_places=3, default=0)
    borra_kg = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    qtd_milheiro = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    observacao = models.TextField("observação", blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "apontamentos"
        ordering = ["data", "created_at"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} {self.turno} {self.maquina}"


# ---------------------------------------------------------------- Comercial
class Venda(Base):
    """Faturamento base Omie (aba "Base de Dados")."""
    data = models.DateField(db_index=True)
    cliente = models.CharField(max_length=300, db_index=True)
    produto = models.CharField(max_length=300)
    linha = models.CharField(max_length=100, db_index=True)
    quantidade = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    valor_unitario = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    kg = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    familia = models.CharField(max_length=200, blank=True, null=True)
    descricao = models.CharField(max_length=300, blank=True, null=True)
    grupo = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    cor = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    produto_simplificado = models.CharField(max_length=300, blank=True, null=True)
    nota_fiscal = models.CharField(max_length=100, blank=True, null=True)
    tipo_documento = models.CharField(max_length=100, blank=True, null=True)
    orcamento = models.CharField(max_length=100, blank=True, null=True)
    bairro = models.CharField(max_length=200, blank=True, null=True)
    cidade = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    estado = models.CharField(max_length=50, blank=True, null=True)
    vendedor = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    cnpj_cpf = models.CharField(max_length=30, blank=True, null=True)
    unidade = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        db_table = "vendas"
        ordering = ["data"]


class VendaPlasti(Base):
    """Pedidos base Plasti Manaus."""
    data_pedido = models.DateField(db_index=True)
    numero_pedido = models.CharField(max_length=100, blank=True, null=True)
    data_entrega = models.DateField(null=True, blank=True)
    cliente = models.CharField(max_length=300)
    vendedor = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=16, decimal_places=2)
    forma_pagamento = models.CharField(max_length=100)
    status = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "vendas_plasti"
        ordering = ["data_pedido"]
        verbose_name = "pedido Plasti"


class MetaVendedor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendedor = models.CharField(max_length=200)
    mes = models.DateField("mês", help_text="Use o primeiro dia do mês.")
    meta = models.DecimalField(max_digits=16, decimal_places=2)

    class Meta:
        db_table = "metas_vendedor"
        ordering = ["mes", "vendedor"]
        verbose_name = "meta de vendedor"
        verbose_name_plural = "metas de vendedor"

    def __str__(self):
        return f"{self.vendedor} {self.mes:%m/%Y}"


# ---------------------------------------------------------------- Financeiro
class FluxoCaixa(Base):
    """Entradas e saídas base Omie."""
    fornecedor = models.CharField(max_length=300)
    categoria = models.CharField(max_length=200)
    data_emissao = models.DateField(db_index=True)
    data_pagamento = models.DateField(null=True, blank=True)
    departamento = models.CharField(max_length=200, blank=True, null=True)
    cnpj_cpf = models.CharField(max_length=30, blank=True, null=True)
    grupo = models.CharField(max_length=200, db_index=True)
    forma_pagamento = models.CharField(max_length=100, blank=True, null=True)
    situacao = models.CharField(max_length=100)
    tipo = models.CharField(max_length=100)
    valor_conta = models.DecimalField(max_digits=16, decimal_places=2)
    valor_pago = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    conta_corrente = models.CharField(max_length=200, blank=True, null=True)
    # Campos vindos da API do Omie (vazios nos lançamentos importados de planilha)
    data_vencimento = models.DateField("vencimento", null=True, blank=True, db_index=True)
    data_previsao = models.DateField("previsão", null=True, blank=True)
    numero_documento = models.CharField("documento", max_length=100, blank=True, null=True)
    parcela = models.CharField(max_length=20, blank=True, null=True)
    omie_codigo = models.BigIntegerField("código Omie", null=True, blank=True, db_index=True)
    observacao = models.TextField("observação", blank=True, null=True)

    class Meta:
        db_table = "fluxo_caixa"
        ordering = ["data_emissao"]
        verbose_name = "lançamento"
        verbose_name_plural = "fluxo de caixa"

    @property
    def receber(self):
        return self.valor_conta > 0

    @property
    def quitado(self):
        return (self.situacao or "").strip() in ("Pago", "Recebido")

    @property
    def saldo_aberto(self):
        return max(abs(self.valor_conta) - abs(self.valor_pago or 0), 0) if not self.quitado else 0

    @property
    def vencimento(self):
        return self.data_vencimento or self.data_previsao or self.data_emissao


class SincronizacaoOmie(models.Model):
    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True, blank=True)
    de = models.DateField()
    ate = models.DateField()
    status = models.CharField(max_length=20, default="rodando")  # rodando | ok | erro
    mensagem = models.TextField(blank=True)
    usuario = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "sincronizacoes_omie"
        ordering = ["-inicio"]
        verbose_name = "sincronização Omie"
        verbose_name_plural = "sincronizações Omie"


class AuditoriaOmie(models.Model):
    """O que mudou no Omie entre uma leitura e outra (só cresce; não é apagado pelas telas)."""
    TIPOS = [("novo", "Novo"), ("alterado", "Alterado"), ("excluido", "Excluído/cancelado")]
    detectado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    sincronizacao = models.ForeignKey(SincronizacaoOmie, on_delete=models.SET_NULL, null=True, blank=True, related_name="auditoria")
    entidade = models.CharField(max_length=20, default="titulo")  # titulo | nf
    chave = models.CharField("código Omie", max_length=60, db_index=True)
    tipo = models.CharField(max_length=10, choices=TIPOS, db_index=True)
    natureza = models.CharField(max_length=10, blank=True)  # pagar | receber
    documento = models.CharField(max_length=120, blank=True)
    parte = models.CharField("fornecedor/cliente", max_length=300, blank=True, db_index=True)
    valor = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    campo = models.CharField(max_length=40, blank=True, db_index=True)
    antes = models.TextField(blank=True)
    depois = models.TextField(blank=True)
    sensivel = models.BooleanField(default=False, db_index=True)
    motivo = models.CharField(max_length=200, blank=True)
    usuario_omie = models.CharField(max_length=40, blank=True, db_index=True)
    alterado_no_omie = models.CharField(max_length=30, blank=True)

    class Meta:
        db_table = "auditoria_omie"
        ordering = ["-detectado_em", "id"]
        verbose_name = "auditoria Omie"
        verbose_name_plural = "auditoria Omie"


class UsuarioOmie(models.Model):
    """Nome de cada usuário do Omie (o Omie só informa o código, ex.: P001333838)."""
    codigo = models.CharField(max_length=40, unique=True)
    nome = models.CharField(max_length=150)

    class Meta:
        db_table = "usuarios_omie"


class SaldoContaOmie(models.Model):
    """Saldo atual de cada conta corrente no Omie (lido junto com a sincronização de hora em hora)."""
    codigo = models.BigIntegerField(unique=True)
    descricao = models.CharField(max_length=200)
    saldo = models.DecimalField(max_digits=16, decimal_places=2)
    fluxo_caixa = models.BooleanField("entra no fluxo de caixa", default=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saldo_conta_omie"
        verbose_name = "saldo de conta (Omie)"
        verbose_name_plural = "saldos de contas (Omie)"


class PerfilUsuario(models.Model):
    """Dados extras do usuário: vendedor ligado (vê só a própria carteira em Problemas para resolver)."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_erp")
    vendedor = models.CharField("vendedor (nome no Omie)", max_length=200, blank=True)

    class Meta:
        db_table = "perfil_usuario"


class DispensaProblema(models.Model):
    """Problema escondido até uma data. Depois dela, se o problema continuar, ele volta."""
    regra = models.CharField(max_length=60, db_index=True)
    volta_em = models.DateField("volta em")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dispensa_problema"
        ordering = ["-criado_em"]


class Favorito(models.Model):
    """Tela favoritada pelo usuário: aparece no menu Rotina."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favoritos")
    url = models.CharField(max_length=300)
    titulo = models.CharField(max_length=200)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorito"
        ordering = ["criado_em"]
        constraints = [models.UniqueConstraint(fields=["usuario", "url"], name="favorito_unico")]
