"""Testes do e-mail da Secretaria com um servidor IMAP/SMTP falso (nada sai da máquina)."""
import re
from email.message import EmailMessage
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings

from . import correio
from .models import ContaEmail


def _email(uid):
    m = EmailMessage()
    m["From"] = "João Cliente <joao@cliente.com.br>"
    m["To"] = "alisson@plasti.com.br, outro@plasti.com.br"
    m["Subject"] = "Pedido de orçamento ção"
    m["Date"] = "Tue, 24 Nov 2026 10:00:00 -0400"
    m["Message-ID"] = f"<msg{uid}@cliente.com.br>"
    m.set_content("Bom dia, preciso de 500 kg de sacola.")
    m.add_alternative('<p>Bom dia, preciso de <b>500 kg</b>.<script>alert(1)</script><img src="cid:logo1"><img src="https://rastreio.example/x.png"></p>', subtype="html")
    m.get_payload()[1].add_related(b"\x89PNG fake", maintype="image", subtype="png", cid="<logo1>")
    m.add_attachment(b"%PDF-1.4 teste", maintype="application", subtype="pdf", filename="orçamento.pdf")
    return m.as_bytes()


class FakeIMAP:
    servidor = None  # estado compartilhado entre conexões

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.capabilities = ("IMAP4REV1", "MOVE", "UIDPLUS")
        self.sel = None
        self.literal = None
        if FakeIMAP.servidor is None:
            FakeIMAP.servidor = {"INBOX": {1: [set(), _email(1)], 2: [{"\\Seen"}, _email(2)]},
                                 "INBOX.Trash": {}, "INBOX.Sent": {}}

    S = property(lambda self: FakeIMAP.servidor)

    def login(self, u, s):
        if s != "senha-certa":
            import imaplib
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication failed.")
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b""]

    def list(self):
        flags = {"INBOX": "\\HasNoChildren", "INBOX.Trash": "\\HasNoChildren \\Trash", "INBOX.Sent": "\\HasNoChildren \\Sent"}
        return "OK", [f'({flags.get(n, "")}) "." "{n}"'.encode() for n in self.S]

    def _n(self, q):
        return q.strip('"')

    def select(self, pasta, readonly=False):
        p = self._n(pasta)
        if p not in self.S:
            return "NO", [b"no such folder"]
        self.sel = p
        return "OK", [str(len(self.S[p])).encode()]

    def status(self, pasta, what):
        n = sum(1 for f, _ in self.S[self._n(pasta)].values() if "\\Seen" not in f)
        return "OK", [f"{pasta} (UNSEEN {n})".encode()]

    def create(self, pasta):
        self.S[self._n(pasta)] = {}
        return "OK", [b""]

    def subscribe(self, pasta):
        return "OK", [b""]

    def append(self, pasta, flags, data, msg):
        caixa = self.S[self._n(pasta)]
        caixa[max(caixa, default=0) + 1] = [{"\\Seen"}, msg]
        return "OK", [b""]

    def uid(self, cmd, *args):
        caixa = self.S[self.sel]
        if cmd == "SEARCH":
            if self.literal:
                termo = self.literal.decode().lower()
                self.literal = None
                uids = [u for u, (_, b) in caixa.items() if termo in b.decode("utf-8", "replace").lower()]
            else:
                uids = list(caixa)
            return "OK", [" ".join(map(str, uids)).encode()]
        if cmd == "FETCH":
            out = []
            for u in [int(x) for x in args[0].split(",")]:
                if u not in caixa:
                    continue
                f, b = caixa[u]
                if "HEADER.FIELDS" in args[1]:
                    cab = b.split(b"\n\n")[0]
                    meta = f'{u} (UID {u} FLAGS ({" ".join(f)}) RFC822.SIZE {len(b)} BODYSTRUCTURE (("text" "plain") "attachment") BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {{{len(cab)}}}'
                    out += [(meta.encode(), cab), b")"]
                else:
                    out += [(f"{u} (UID {u} BODY[] {{{len(b)}}}".encode(), b), b")"]
            return "OK", out
        if cmd == "STORE":
            u = int(args[0])
            flags = set(re.findall(r"\\\w+", args[2]))
            if args[1].startswith("+"):
                caixa[u][0] |= flags
            else:
                caixa[u][0] -= flags
            return "OK", [b""]
        if cmd == "MOVE":
            u, destino = int(args[0]), self._n(args[1])
            d = self.S[destino]
            d[max(d, default=0) + 1] = caixa.pop(u)
            return "OK", [b""]
        raise AssertionError(cmd)


class FakeSMTP:
    enviados = []

    def __init__(self, host, port, context=None, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def login(self, u, s):
        pass

    def send_message(self, msg, from_addr=None, to_addrs=None):
        FakeSMTP.enviados.append((msg, to_addrs))


@override_settings(SECRETARIA_PERMITIR_HTTP=True, ANTHROPIC_API_KEY="", SECRETARIA_CHAVE="XG6F7DqkJJ3o5b6mdwYaugBAugGFojGldRwU8Dz7RTc=")
@mock.patch("imaplib.IMAP4_SSL", FakeIMAP)
@mock.patch("smtplib.SMTP_SSL", FakeSMTP)
class EmailTest(TestCase):
    def setUp(self):
        FakeIMAP.servidor = None
        FakeSMTP.enviados = []
        self.u = User.objects.create_user("ana", password="x", first_name="Ana")
        self.u.groups.add(Group.objects.get(name="Secretaria"))
        self.c = self.client
        self.c.force_login(self.u)
        self.c.defaults["HTTP_HOST"] = "localhost"

    def _conta(self):
        r = self.c.post("/secretaria/email/contas/nova/", dict(
            empresa="Plasti", email="alisson@plasti.com.br", imap_porta=993, smtp_porta=465, smtp_seguranca="ssl",
            senha="senha-certa", ativa="on", assinatura="Ana\nPlasti Manaus"))
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        return ContaEmail.objects.get()

    def test_sem_acesso(self):
        outro = User.objects.create_user("beto", password="x")
        self.c.force_login(outro)
        self.assertEqual(self.c.get("/secretaria/email/").status_code, 403)
        self.assertNotContains(self.c.get("/"), "Secretaria")

    def test_senha_criptografada_e_teste_de_conexao(self):
        conta = self._conta()
        self.assertEqual(conta.imap_host, "mail.plasti.com.br")
        self.assertNotIn("senha-certa", conta.senha_cifrada)
        self.assertEqual(conta.senha, "senha-certa")
        self.assertIsNotNone(conta.verificada_em)
        self.assertEqual(conta.ultimo_erro, "")
        r = self.c.post(f"/secretaria/email/contas/{conta.pk}/", dict(
            empresa="Plasti", email="alisson@plasti.com.br", imap_porta=993, smtp_porta=465, smtp_seguranca="ssl", senha="errada", ativa="on"))
        conta.refresh_from_db()
        self.assertIn("Login recusado", conta.ultimo_erro)

    @override_settings(SECRETARIA_PERMITIR_HTTP=False)
    def test_bloqueia_senha_sem_https(self):
        self.c.post("/secretaria/email/contas/nova/", dict(empresa="P", email="a@b.com.br", imap_porta=993, smtp_porta=465,
                                                          smtp_seguranca="ssl", senha="senha-certa", ativa="on"))
        self.assertFalse(ContaEmail.objects.exists())

    def test_caixa_ler_anexo_busca(self):
        conta = self._conta()
        r = self.c.get("/secretaria/email/")
        self.assertContains(r, "Pedido de orçamento ção")
        self.assertContains(r, "João Cliente")
        self.assertContains(r, '<b class="cont">1</b>', html=False)
        r = self.c.get(f"/secretaria/email/{conta.pk}/1/")
        html = r.content.decode()
        self.assertIn('sandbox="allow-popups', html)
        self.assertNotIn("<script>alert", html)              # vai escapado dentro do srcdoc
        self.assertIn("data:image/png;base64", html)          # imagem cid embutida
        self.assertIn("Imagens externas bloqueadas", html)
        self.assertIn("orçamento.pdf", html)
        self.assertIn("\\Seen", FakeIMAP.servidor["INBOX"][1][0])
        n = r.context["m"].anexos[0].n
        r = self.c.get(f"/secretaria/email/{conta.pk}/1/anexo/{n}/")
        self.assertEqual(r["Content-Type"], "application/octet-stream")
        self.assertIn("attachment;", r["Content-Disposition"])
        self.assertEqual(r.content, b"%PDF-1.4 teste")
        self.assertContains(self.c.get("/secretaria/email/?conta=%s&q=sacola" % conta.pk), "Pedido de orçamento")
        self.assertContains(self.c.get("/secretaria/email/?conta=%s&q=inexistente" % conta.pk), "Nenhum e-mail")

    def test_apagar_e_arquivar(self):
        conta = self._conta()
        self.c.post(f"/secretaria/email/{conta.pk}/1/acao/", dict(acao="apagar", pasta="INBOX"))
        self.assertEqual(len(FakeIMAP.servidor["INBOX.Trash"]), 1)
        self.c.post(f"/secretaria/email/{conta.pk}/2/acao/", dict(acao="arquivar", pasta="INBOX"))
        self.assertEqual(len(FakeIMAP.servidor["INBOX.Archive"]), 1)   # criada automaticamente
        self.assertEqual(FakeIMAP.servidor["INBOX"], {})

    def test_responder(self):
        conta = self._conta()
        r = self.c.get(f"/secretaria/email/escrever/?conta={conta.pk}&uid=1&pasta=INBOX&modo=todos")
        f = r.context["form"]
        self.assertEqual(f.initial["assunto"], "Re: Pedido de orçamento ção")
        self.assertEqual(f.initial["cc"], "outro@plasti.com.br")
        self.assertIn("> Bom dia", f.initial["corpo"])
        self.assertContains(r, "Disponível quando a chave")
        dados = {k: v for k, v in f.initial.items()}
        dados.update(conta=str(conta.pk), para="joao@cliente.com.br", corpo="Olá João, segue." + f.initial["corpo"])
        r = self.c.post("/secretaria/email/escrever/", dados)
        self.assertEqual(r.status_code, 302)
        msg, dest = FakeSMTP.enviados[0]
        self.assertEqual(msg["In-Reply-To"], "<msg1@cliente.com.br>")
        self.assertEqual(sorted(dest), ["joao@cliente.com.br", "outro@plasti.com.br"])
        self.assertEqual(len(FakeIMAP.servidor["INBOX.Sent"]), 1)
        self.assertIn("\\Answered", FakeIMAP.servidor["INBOX"][1][0])

    def test_conta_de_outro_usuario(self):
        conta = self._conta()
        outro = User.objects.create_user("beto", password="x")
        outro.groups.add(Group.objects.get(name="Secretaria"))
        self.c.force_login(outro)
        self.assertEqual(self.c.get(f"/secretaria/email/{conta.pk}/1/").status_code, 404)
        self.assertEqual(self.c.get(f"/secretaria/email/contas/{conta.pk}/").status_code, 404)

    def test_sugerir(self):
        conta = self._conta()
        r = self.c.post("/secretaria/email/sugerir/", dict(conta=conta.pk, uid=1, pasta="INBOX"))
        self.assertEqual(r.status_code, 400)
        resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Olá João, envio hoje.")])
        with override_settings(ANTHROPIC_API_KEY="teste"), mock.patch("anthropic.resources.beta.messages.Messages.create", return_value=resp) as cr:
            r = self.c.post("/secretaria/email/sugerir/", dict(conta=conta.pk, uid=1, pasta="INBOX", instrucao="confirmar entrega"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["texto"].startswith("Olá João, envio hoje."))
        kw = cr.call_args.kwargs
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertIn("confirmar entrega", kw["messages"][0]["content"])


class UsuariosTest(TestCase):
    def test_marca_secretaria(self):
        adm = User.objects.create_user("adm", password="x", is_staff=True)
        u = User.objects.create_user("marcio", password="x")
        self.client.force_login(adm)
        r = self.client.post(f"/usuarios/{u.pk}/", dict(username="marcio", first_name="Márcio", is_active="on", secretaria="on"),
                             HTTP_HOST="localhost")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(u.groups.filter(name="Secretaria").exists())
        comum = User.objects.create_user("zé", password="x")
        self.client.force_login(comum)
        self.assertEqual(self.client.get("/usuarios/", HTTP_HOST="localhost").status_code, 403)


class Utf7Test(TestCase):
    def test_ida_e_volta(self):
        for s in ["INBOX.Lixeira", "INBOX.Itens Excluídos", "Ações & Co"]:
            self.assertEqual(correio.utf7_decode(correio.utf7_encode(s)), s)
        self.assertEqual(correio.utf7_encode("Excluídos"), "Exclu&AO0-dos")
