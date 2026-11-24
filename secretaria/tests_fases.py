"""Testes das fases 3 a 8 (Integrações, Lembretes, Agenda, Diário, Triagem, Angel, rotinas). Nada sai da máquina."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from . import config
from .models import Integracao, Lembrete, Notificacao, PerfilSecretaria, RegistroDiario
from .tests import FakeIMAP, FakeSMTP

CHAVE = "XG6F7DqkJJ3o5b6mdwYaugBAugGFojGldRwU8Dz7RTc="


@override_settings(SECRETARIA_PERMITIR_HTTP=True, ANTHROPIC_API_KEY="", ELEVENLABS_API_KEY="", SECRETARIA_CHAVE=CHAVE)
@mock.patch("imaplib.IMAP4_SSL", FakeIMAP)
@mock.patch("smtplib.SMTP_SSL", FakeSMTP)
class Base(TestCase):
    def setUp(self):
        cache.clear()
        FakeIMAP.servidor = None
        self.u = User.objects.create_user("ana", password="x", first_name="Ana", is_staff=True)
        self.u.groups.add(Group.objects.get(name="Secretaria"))
        self.client.force_login(self.u)


@mock.patch("imaplib.IMAP4_SSL", FakeIMAP)
class IntegracoesTest(Base):
    def test_salvar_mascarar_remover_e_token(self):
        r = self.client.post("/secretaria/integracoes/", {"nome": "ELEVENLABS_API_KEY", "acao": "salvar", "valor": "sk_abcdefghij1234"})
        self.assertEqual(r.status_code, 302)
        obj = Integracao.objects.get(nome="ELEVENLABS_API_KEY")
        self.assertNotIn("abcdefghij", obj.valor_cifrado)            # criptografada no banco
        self.assertEqual(config.obter("ELEVENLABS_API_KEY"), "sk_abcdefghij1234")
        pagina = self.client.get("/secretaria/integracoes/").content.decode()
        self.assertIn("1234", pagina)
        self.assertNotIn("abcdefghij", pagina)                        # nunca aparece inteira
        self.client.post("/secretaria/integracoes/", {"nome": "ELEVENLABS_API_KEY", "acao": "remover"})
        self.assertEqual(config.obter("ELEVENLABS_API_KEY"), "")
        self.client.post("/secretaria/integracoes/", {"nome": "ANGEL_TOKEN", "acao": "gerar"})
        t1 = config.obter("ANGEL_TOKEN")
        self.client.post("/secretaria/integracoes/", {"nome": "ANGEL_TOKEN", "acao": "gerar"})
        self.assertNotEqual(t1, config.obter("ANGEL_TOKEN"))          # revoga o antigo

    def test_so_administrador(self):
        self.u.is_staff = False
        self.u.save()
        self.assertEqual(self.client.get("/secretaria/integracoes/").status_code, 403)

    @override_settings(SECRETARIA_PERMITIR_HTTP=False)
    def test_exige_https(self):
        self.client.post("/secretaria/integracoes/", {"nome": "ANTHROPIC_API_KEY", "acao": "salvar", "valor": "sk-ant-x"})
        self.assertFalse(Integracao.objects.filter(nome="ANTHROPIC_API_KEY").exclude(valor_cifrado="").exists())

    def test_telas_abrem(self):
        for url in ["/secretaria/", "/secretaria/lembretes/", "/secretaria/agenda/", "/secretaria/diario/", "/secretaria/angel/",
                    "/secretaria/configuracoes/", "/secretaria/integracoes/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class PerfilTest(Base):
    def test_whatsapp_com_e_sem_nono_digito(self):
        p = PerfilSecretaria(usuario=self.u, whatsapp="(92) 99123-4567")
        self.assertEqual(p.whatsapp_variantes(), ["+559291234567", "+5592991234567"])
        p.whatsapp = "92 9123-4567"
        self.assertIn("+5592991234567", p.whatsapp_variantes())

    def test_salvar_preferencias(self):
        r = self.client.post("/secretaria/configuracoes/", {"whatsapp": "92991234567", "icloud_usuario": "", "briefing_hora": "07:30",
                                                           "briefing_ativo": "on", "triagem_ativa": "on"})
        self.assertEqual(r.status_code, 302)
        p = PerfilSecretaria.objects.get(usuario=self.u)
        self.assertEqual(p.whatsapp, "92991234567")
        self.assertFalse(p.avisos_whatsapp)


class LembretesTest(Base):
    def test_criar_concluir_repetir_adiar(self):
        quando = (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        self.client.post("/secretaria/lembretes/novo/", {"titulo": "Ligar pro contador", "quando": quando, "repeticao": "semanal"})
        l = Lembrete.objects.get()
        antes = l.quando
        self.client.post(f"/secretaria/lembretes/{l.pk}/concluir/")
        l.refresh_from_db()
        self.assertIsNone(l.concluido_em)
        self.assertEqual(l.quando - antes, timedelta(days=7))
        self.client.post(f"/secretaria/lembretes/{l.pk}/adiar/", {"minutos": "60", "voltar": "https://malicioso.example/"})
        l.refresh_from_db()
        self.assertEqual(l.quando - antes, timedelta(days=7, hours=1))
        outro = User.objects.create_user("bia")
        l2 = Lembrete.objects.create(usuario=outro, titulo="x", quando=timezone.now())
        self.assertEqual(self.client.post(f"/secretaria/lembretes/{l2.pk}/concluir/").status_code, 404)


class DiarioTest(Base):
    def test_registro_sem_ia_e_com_ia(self):
        self.client.post("/secretaria/diario/", {"texto": "A extrusora 2 parou."})
        r = RegistroDiario.objects.get()
        self.assertIsNone(r.classificado_em)
        self.assertIn("IA", r.erro_ia)
        with mock.patch("secretaria.ia.disponivel", return_value=True), \
                mock.patch("secretaria.ia.json_ia", return_value={"tipo": "problema", "empresa": "Plasti", "assunto": "Extrusora", "pontuacao": 4, "resumo": "Extrusora parou"}):
            self.client.post(f"/secretaria/diario/{r.pk}/", {"acao": "reclassificar"})
        r.refresh_from_db()
        self.assertEqual((r.tipo, r.pontuacao), ("problema", 4))
        pagina = self.client.get("/secretaria/diario/").content.decode()
        self.assertIn("Problemas e tarefas em aberto", pagina)
        self.client.post(f"/secretaria/diario/{r.pk}/", {"acao": "resolver"})
        r.refresh_from_db()
        self.assertTrue(r.resolvido)
        self.assertEqual(self.client.get("/secretaria/diario/?tipo=ideia").context["registros"], [])


class AngelApiTest(Base):
    def setUp(self):
        super().setUp()
        PerfilSecretaria.objects.create(usuario=self.u, whatsapp="92 99123-4567")
        config.salvar("ANGEL_TOKEN", "tok-secreto")

    def _post(self, dados, token="tok-secreto"):
        return self.client.post("/secretaria/api/angel/mensagem/", json.dumps(dados), content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_token_e_numero(self):
        self.assertEqual(self._post({"de": "+5592991234567", "texto": "oi"}, token="errado").status_code, 401)
        self.assertEqual(self._post({"de": "+5511988887777", "texto": "oi"}).status_code, 403)
        with mock.patch("secretaria.cerebro.conversar", return_value="Olá!") as c:
            r = self._post({"de": "+559291234567", "texto": "oi"})        # sem o nono dígito
        self.assertEqual(r.json()["resposta"], "Olá!")
        self.assertEqual(c.call_args.kwargs["canal"], "whatsapp")


class CerebroTest(Base):
    def test_cria_lembrete_por_ferramenta(self):
        from . import cerebro
        bloco = SimpleNamespace(type="tool_use", id="t1", name="lembrete_criar", input={"titulo": "Pagar DAS", "quando": "2026-12-20T09:00"},
                                model_dump=lambda **k: {"type": "tool_use", "id": "t1", "name": "lembrete_criar", "input": {}})
        r1 = SimpleNamespace(stop_reason="tool_use", content=[bloco])
        r2 = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Lembrete criado para 20/12 às 9h.")])
        with mock.patch("secretaria.ia.disponivel", return_value=True), \
                mock.patch("anthropic.resources.beta.messages.Messages.create", side_effect=[r1, r2]) as cr:
            resp = cerebro.conversar(self.u, "me lembra de pagar o DAS dia 20 às 9h", canal="whatsapp")
        self.assertIn("20/12", resp)
        l = Lembrete.objects.get()
        self.assertEqual(timezone.localtime(l.quando).hour, 9)
        self.assertEqual(l.origem, "whatsapp")
        nomes = {f["name"] for f in cr.call_args.kwargs["tools"]}
        self.assertFalse(any("apagar" in n or "enviar" in n or "excluir" in n for n in nomes))   # nada destrutivo


@mock.patch("imaplib.IMAP4_SSL", FakeIMAP)
@mock.patch("smtplib.SMTP_SSL", FakeSMTP)
class RotinasTest(Base):
    def test_lembrete_vira_aviso_e_expira(self):
        from . import rotinas
        PerfilSecretaria.objects.create(usuario=self.u, whatsapp="92991234567", briefing_ativo=False, triagem_ativa=False)
        agora = timezone.now()
        Lembrete.objects.create(usuario=self.u, titulo="Reunião", quando=agora - timedelta(minutes=1))
        Lembrete.objects.create(usuario=self.u, titulo="Antigo", quando=agora - timedelta(days=2))
        rotinas.rodar(agora)
        n = Notificacao.objects.get(tipo="lembrete")
        self.assertIn("Reunião", n.texto)
        self.assertEqual(n.situacao, "pendente")                       # sem WhatsApp: fica na fila
        self.assertFalse(Lembrete.objects.filter(avisado_em=None).exists())
        rotinas.rodar(agora + timedelta(hours=3))
        n.refresh_from_db()
        self.assertEqual(n.situacao, "expirada")

    def test_envia_quando_whatsapp_conectado_e_briefing(self):
        from . import rotinas
        p = PerfilSecretaria.objects.create(usuario=self.u, whatsapp="92991234567", triagem_ativa=False)
        local = timezone.localtime().replace(hour=7, minute=31)
        with mock.patch("secretaria.servicos.whatsapp_disponivel", return_value=True), \
                mock.patch("secretaria.servicos.enviar_whatsapp") as env, \
                mock.patch("secretaria.servicos.falar", return_value=(b"mp3", "edge")):
            rotinas.rodar(local)
        n = Notificacao.objects.get(tipo="briefing")
        self.assertEqual(n.situacao, "enviada")
        self.assertEqual(env.call_args.args[0], "+5592991234567")
        self.assertEqual(env.call_args.args[2], b"mp3")                # briefing vai em áudio

    def test_triagem_avisa_por_empresa(self):
        from . import rotinas
        from .models import ContaEmail
        PerfilSecretaria.objects.create(usuario=self.u, whatsapp="92991234567", briefing_ativo=False)
        c = ContaEmail(usuario=self.u, empresa="Plasti", email="a@plasti.com.br", login="a@plasti.com.br", imap_host="x", smtp_host="x")
        c.senha = "senha-certa"
        c.save()
        dez = timezone.localtime().replace(hour=10, minute=0)
        rotinas.rodar(dez)                                  # 1ª rodada: só marca o que já existia, não avisa
        self.assertFalse(Notificacao.objects.filter(tipo="triagem").exists())
        from email.message import EmailMessage
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = "Tribunal <intimacao@tj.jus.br>", "a@plasti.com.br", "Intimacao - prazo de 5 dias"
        m["Date"] = timezone.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
        m.set_content("Fica intimada a empresa.")
        FakeIMAP.servidor["INBOX"][3] = [set(), m.as_bytes()]
        from .models import EstadoTriagem
        EstadoTriagem.objects.update(executado_em=timezone.now() - timedelta(days=1))   # simula a rodada da hora anterior
        rotinas.rodar(dez + timedelta(hours=1))
        n = Notificacao.objects.get(tipo="triagem")
        self.assertIn("Plasti", n.texto)
        self.assertIn("Intimacao", n.texto)
        self.assertNotIn("Pedido de", n.texto)            # os antigos não são avisados
