import uuid

from django.conf import settings
from django.db import models

from . import cripto


class ContaEmail(models.Model):
    SEGURANCA = [("ssl", "SSL (porta 465)"), ("starttls", "STARTTLS (porta 587)")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contas_email")
    empresa = models.CharField("empresa / apelido", max_length=100)
    email = models.EmailField("e-mail")
    nome_exibicao = models.CharField("nome do remetente", max_length=150, blank=True)
    login = models.CharField("usuário de login", max_length=200, blank=True, help_text="Normalmente o próprio e-mail.")
    imap_host = models.CharField("servidor IMAP", max_length=200)
    imap_porta = models.PositiveIntegerField("porta IMAP", default=993)
    smtp_host = models.CharField("servidor SMTP", max_length=200)
    smtp_porta = models.PositiveIntegerField("porta SMTP", default=465)
    smtp_seguranca = models.CharField("segurança SMTP", max_length=10, choices=SEGURANCA, default="ssl")
    senha_cifrada = models.TextField(editable=False)
    assinatura = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    pasta_arquivo = models.CharField(max_length=200, blank=True, editable=False)
    pasta_lixeira = models.CharField(max_length=200, blank=True, editable=False)
    pasta_enviados = models.CharField(max_length=200, blank=True, editable=False)
    ultimo_erro = models.TextField(blank=True, editable=False)
    verificada_em = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["empresa", "email"]
        unique_together = [("usuario", "email")]
        verbose_name = "conta de e-mail"
        verbose_name_plural = "contas de e-mail"

    def __str__(self):
        return f"{self.empresa} <{self.email}>"

    @property
    def senha(self) -> str:
        return cripto.decifrar(self.senha_cifrada)

    @senha.setter
    def senha(self, valor: str):
        self.senha_cifrada = cripto.cifrar(valor)

    @property
    def usuario_login(self):
        return self.login or self.email

    @property
    def remetente(self):
        from email.utils import formataddr
        return formataddr((self.nome_exibicao, self.email)) if self.nome_exibicao else self.email


# ===================================================================== Integrações (chaves de serviços externos)
class Integracao(models.Model):
    """Chaves de serviços (Anthropic, ElevenLabs...). Guardadas criptografadas; trocadas/revogadas pela tela."""
    nome = models.CharField(max_length=60, unique=True)
    valor_cifrado = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    testado_em = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)

    class Meta:
        verbose_name = "integração"
        verbose_name_plural = "integrações"

    def __str__(self):
        return self.nome

    @property
    def valor(self):
        return cripto.decifrar(self.valor_cifrado) if self.valor_cifrado else ""

    @valor.setter
    def valor(self, v):
        self.valor_cifrado = cripto.cifrar(v) if v else ""


# ===================================================================== Preferências de cada usuário
class PerfilSecretaria(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_secretaria")
    whatsapp = models.CharField("seu WhatsApp", max_length=20, blank=True, help_text="Com DDD, ex.: 92 99999-9999. O Angel só responde a este número.")
    icloud_usuario = models.CharField("Apple ID (e-mail do iCloud)", max_length=200, blank=True)
    icloud_senha_cifrada = models.TextField(blank=True, editable=False)
    agenda_calendarios = models.JSONField(default=list, blank=True, editable=False)
    agenda_padrao = models.CharField(max_length=500, blank=True, editable=False)
    briefing_ativo = models.BooleanField("briefing da manhã no WhatsApp", default=True)
    briefing_hora = models.TimeField("horário do briefing", default="07:30")
    triagem_ativa = models.BooleanField("triagem de e-mail (8h às 18h, de hora em hora)", default=True)
    avisos_whatsapp = models.BooleanField("avisos de agenda e lembretes no WhatsApp", default=True)
    analise_semanal = models.BooleanField("análise semanal do diário (segunda 8h)", default=True)

    class Meta:
        verbose_name = "preferências da Secretaria"

    def __str__(self):
        return f"Secretaria de {self.usuario}"

    @property
    def icloud_senha(self):
        return cripto.decifrar(self.icloud_senha_cifrada) if self.icloud_senha_cifrada else ""

    @icloud_senha.setter
    def icloud_senha(self, v):
        self.icloud_senha_cifrada = cripto.cifrar(v) if v else ""

    @property
    def whatsapp_e164(self):
        d = "".join(ch for ch in self.whatsapp if ch.isdigit())
        if not d:
            return ""
        if not d.startswith("55"):
            d = "55" + d
        return "+" + d

    def whatsapp_variantes(self):
        """No WhatsApp o celular brasileiro pode aparecer com ou sem o nono dígito: aceita as duas formas."""
        n = self.whatsapp_e164
        if not n:
            return []
        d = n[1:]
        out = {n}
        if len(d) == 13 and d[4] == "9":
            out.add("+" + d[:4] + d[5:])
        elif len(d) == 12:
            out.add("+" + d[:4] + "9" + d[4:])
        return sorted(out)


# ===================================================================== Lembretes
class Lembrete(models.Model):
    REPETICAO = [("", "Não repete"), ("diaria", "Todo dia"), ("dias_uteis", "Dias úteis (seg a sex)"),
                 ("semanal", "Toda semana"), ("mensal", "Todo mês")]
    ORIGEM = [("site", "Site"), ("whatsapp", "WhatsApp"), ("voz", "Voz")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lembretes")
    titulo = models.CharField("lembrete", max_length=300)
    notas = models.TextField(blank=True)
    quando = models.DateTimeField("data e hora", db_index=True)
    repeticao = models.CharField("repetição", max_length=12, choices=REPETICAO, blank=True, default="")
    concluido_em = models.DateTimeField(null=True, blank=True)
    avisado_em = models.DateTimeField(null=True, blank=True, editable=False)
    origem = models.CharField(max_length=10, choices=ORIGEM, default="site", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["concluido_em", "quando"]

    def __str__(self):
        return self.titulo

    def proxima_data(self):
        from datetime import timedelta
        q = self.quando
        if self.repeticao == "diaria":
            return q + timedelta(days=1)
        if self.repeticao == "dias_uteis":
            q = q + timedelta(days=1)
            while q.weekday() >= 5:
                q += timedelta(days=1)
            return q
        if self.repeticao == "semanal":
            return q + timedelta(days=7)
        if self.repeticao == "mensal":
            import calendar
            ano, mes = (q.year + 1, 1) if q.month == 12 else (q.year, q.month + 1)
            return q.replace(year=ano, month=mes, day=min(q.day, calendar.monthrange(ano, mes)[1]))
        return None

    def concluir(self):
        from django.utils import timezone
        prox = self.proxima_data()
        if prox:
            self.quando, self.avisado_em = prox, None
        else:
            self.concluido_em = timezone.now()
        self.save()


# ===================================================================== Diário
class RegistroDiario(models.Model):
    TIPOS = [("acontecimento", "Acontecimento"), ("ideia", "Ideia"), ("problema", "Problema"), ("decisao", "Decisão"), ("tarefa", "Tarefa")]
    ORIGEM = [("site", "Site"), ("voz", "Voz no site"), ("whatsapp", "WhatsApp"), ("audio", "Áudio no WhatsApp")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="diario")
    texto = models.TextField()
    criado_em = models.DateTimeField(db_index=True)
    origem = models.CharField(max_length=10, choices=ORIGEM, default="site")
    tipo = models.CharField(max_length=15, choices=TIPOS, blank=True)
    empresa = models.CharField(max_length=100, blank=True)
    assunto = models.CharField(max_length=150, blank=True)
    pontuacao = models.PositiveSmallIntegerField("importância (1 a 5)", null=True, blank=True)
    resumo = models.CharField(max_length=300, blank=True)
    resolvido = models.BooleanField(default=False)
    classificado_em = models.DateTimeField(null=True, blank=True)
    erro_ia = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-criado_em"]


class AnaliseSemanal(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analises_diario")
    inicio = models.DateField()
    fim = models.DateField()
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inicio"]
        unique_together = [("usuario", "inicio")]


# ===================================================================== Triagem de e-mail
class TriagemEmail(models.Model):
    CATEGORIAS = [("critico", "Crítico"), ("financeiro", "Financeiro"), ("responder", "Aguardando resposta"),
                  ("outros", "Outros"), ("propaganda", "Propaganda")]
    conta = models.ForeignKey(ContaEmail, on_delete=models.CASCADE, related_name="triagens")
    pasta = models.CharField(max_length=200, default="INBOX")
    uid = models.BigIntegerField()
    de = models.CharField(max_length=300, blank=True)
    assunto = models.CharField(max_length=500, blank=True)
    data = models.DateTimeField(null=True, blank=True)
    categoria = models.CharField(max_length=12, choices=CATEGORIAS)
    importancia = models.PositiveSmallIntegerField(default=1)
    resumo = models.CharField(max_length=500, blank=True)
    acao = models.CharField("ação sugerida", max_length=300, blank=True)
    por_ia = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    notificado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("conta", "pasta", "uid")]
        ordering = ["-data"]


class EstadoTriagem(models.Model):
    conta = models.OneToOneField(ContaEmail, on_delete=models.CASCADE, related_name="estado_triagem")
    ultimo_uid = models.BigIntegerField(default=0)
    executado_em = models.DateTimeField(null=True, blank=True)


# ===================================================================== Avisos (fila para o WhatsApp do Angel)
class Notificacao(models.Model):
    TIPOS = [("lembrete", "Lembrete"), ("agenda", "Agenda"), ("triagem", "Triagem de e-mail"), ("briefing", "Briefing"),
             ("analise", "Análise semanal"), ("teste", "Teste")]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificacoes")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    chave = models.CharField(max_length=200, help_text="Evita avisar duas vezes a mesma coisa.")
    texto = models.TextField()
    audio = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    situacao = models.CharField(max_length=12, default="pendente")  # pendente, enviada, erro, expirada, sem_canal
    erro = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = [("usuario", "chave")]
        ordering = ["-criada_em"]
