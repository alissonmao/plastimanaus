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
