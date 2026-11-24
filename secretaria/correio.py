"""Acesso às caixas de e-mail (IMAP para ler/mover, SMTP para enviar).

Nada fica guardado no banco além da configuração da conta: as mensagens são lidas
direto do servidor (HostGator) a cada tela.
"""
import base64
import imaplib
import re
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parseaddr, parsedate_to_datetime

TIMEOUT = 25
LIMITE_PAGINA = 50
LIMITE_IMAGEM_INLINE = 3 * 1024 * 1024

NOMES_PADRAO = {
    "\\Archive": ["INBOX.Archive", "Archive", "INBOX.Arquivo", "Arquivo", "INBOX.Arquivados", "Arquivados"],
    "\\Trash": ["INBOX.Trash", "Trash", "INBOX.Lixeira", "Lixeira", "Deleted Items", "INBOX.Deleted Items"],
    "\\Sent": ["INBOX.Sent", "Sent", "INBOX.Enviados", "Enviados", "Sent Items", "INBOX.Sent Items"],
}
NOMES_PT = {"INBOX": "Caixa de entrada", "Archive": "Arquivo", "Trash": "Lixeira", "Sent": "Enviados",
            "Drafts": "Rascunhos", "Junk": "Spam", "spam": "Spam"}


class ErroCorreio(Exception):
    pass


# ---------------------------------------------------------------- UTF-7 modificado (nomes de pasta IMAP)
def utf7_decode(s: str) -> str:
    def troca(m):
        txt = m.group(1)
        if not txt:
            return "&"
        txt = txt.replace(",", "/")
        txt += "=" * (-len(txt) % 4)
        return base64.b64decode(txt).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", troca, s)


def utf7_encode(s: str) -> str:
    out, buf = [], []

    def flush():
        if buf:
            b = base64.b64encode("".join(buf).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append("&" + b + "-")
            buf.clear()
    for ch in s:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def _q(pasta: str) -> str:
    return '"' + utf7_encode(pasta).replace("\\", "\\\\").replace('"', '\\"') + '"'


def nome_pasta(pasta: str) -> str:
    ult = re.split(r"[./]", pasta)[-1]
    return NOMES_PT.get(pasta, NOMES_PT.get(ult, ult))


# ---------------------------------------------------------------- cabeçalhos
def texto_cabecalho(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    try:
        return str(make_header(decode_header(v))).replace("\r", "").replace("\n", " ").strip()
    except Exception:
        return str(v)


def _data(v):
    try:
        d = parsedate_to_datetime(v)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@dataclass
class Resumo:
    conta: object
    pasta: str
    uid: str
    de_nome: str
    de_email: str
    assunto: str
    data: datetime | None
    lido: bool
    respondido: bool
    tamanho: int
    anexo: bool = False


@dataclass
class Anexo:
    n: int
    nome: str
    tipo: str
    tamanho: int


@dataclass
class Mensagem:
    uid: str
    pasta: str
    de: str
    de_email: str
    para: str
    cc: str
    responder_para: str
    assunto: str
    data: datetime | None
    message_id: str
    referencias: str
    texto: str
    html: str
    anexos: list = field(default_factory=list)
    tem_imagens_externas: bool = False


# ---------------------------------------------------------------- leitura da mensagem
def _partes(msg):
    """Todas as partes folha, na ordem do walk (o índice identifica o anexo)."""
    return [p for p in msg.walk() if not p.is_multipart()]


def _conteudo(p) -> str:
    try:
        return p.get_content()
    except Exception:
        carga = p.get_payload(decode=True) or b""
        return carga.decode(p.get_content_charset() or "latin-1", "replace")


def interpretar(bruto: bytes, uid: str, pasta: str, imagens_externas=False) -> Mensagem:
    msg = message_from_bytes(bruto, policy=policy.default)
    partes = _partes(msg)
    corpo_html = msg.get_body(preferencelist=("html",))
    corpo_txt = msg.get_body(preferencelist=("plain",))
    html = _conteudo(corpo_html) if corpo_html is not None else ""
    texto = _conteudo(corpo_txt) if corpo_txt is not None else ""
    anexos, cids = [], {}
    for i, p in enumerate(partes):
        if p is corpo_html or p is corpo_txt:
            continue
        carga = p.get_payload(decode=True) or b""
        cid = (p.get("Content-ID") or "").strip("<> ")
        if cid and p.get_content_maintype() == "image" and len(carga) <= LIMITE_IMAGEM_INLINE:
            cids[cid] = f"data:{p.get_content_type()};base64,{base64.b64encode(carga).decode()}"
            if not p.get_filename():
                continue
        nome = texto_cabecalho(p.get_filename()) or f"anexo-{i + 1}"
        anexos.append(Anexo(i, nome, p.get_content_type(), len(carga)))
    tem_ext = False
    if html:
        html = re.sub(r"cid:([^\"'\s)>]+)", lambda m: cids.get(m.group(1), "about:blank"), html, flags=re.I)
        tem_ext = bool(re.search(r"<img[^>]+src=[\"']?https?:", html, re.I))
        csp = ("default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:"
               + (" https: http:" if imagens_externas else ""))
        html = (f'<meta http-equiv="Content-Security-Policy" content="{csp}"><base target="_blank">'
                '<style>body{font-family:system-ui,sans-serif;font-size:14px;margin:8px;word-wrap:break-word}</style>' + html)
    de_nome, de_email = parseaddr(texto_cabecalho(msg.get("From")))
    return Mensagem(
        uid=uid, pasta=pasta, de=de_nome or de_email, de_email=de_email,
        para=texto_cabecalho(msg.get("To")), cc=texto_cabecalho(msg.get("Cc")),
        responder_para=texto_cabecalho(msg.get("Reply-To")) or texto_cabecalho(msg.get("From")),
        assunto=texto_cabecalho(msg.get("Subject")) or "(sem assunto)", data=_data(msg.get("Date")),
        message_id=(msg.get("Message-ID") or "").strip(), referencias=(msg.get("References") or "").strip(),
        texto=texto, html=html, anexos=anexos, tem_imagens_externas=tem_ext)


def extrair_anexo(bruto: bytes, n: int):
    msg = message_from_bytes(bruto, policy=policy.default)
    partes = _partes(msg)
    if n < 0 or n >= len(partes):
        raise ErroCorreio("Anexo não encontrado.")
    p = partes[n]
    return (texto_cabecalho(p.get_filename()) or f"anexo-{n + 1}", p.get_content_type(), p.get_payload(decode=True) or b"")


# ---------------------------------------------------------------- IMAP
_RE_LIST = re.compile(rb'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<nome>.+)')
_RE_FETCH = re.compile(rb"UID (\d+)")


class Caixa:
    """Uso: with Caixa(conta) as cx: cx.listar(...)"""

    def __init__(self, conta):
        self.conta = conta
        self.m = None
        self._pastas = None

    def __enter__(self):
        try:
            ctx = ssl.create_default_context()
            self.m = imaplib.IMAP4_SSL(self.conta.imap_host, self.conta.imap_porta, ssl_context=ctx, timeout=TIMEOUT)
            self.m.login(self.conta.usuario_login, self.conta.senha)
        except imaplib.IMAP4.error as e:
            raise ErroCorreio(f"Login recusado pelo servidor IMAP ({_msg(e)}). Confira usuário e senha.") from e
        except (OSError, ssl.SSLError) as e:
            raise ErroCorreio(f"Não consegui conectar em {self.conta.imap_host}:{self.conta.imap_porta} ({e}).") from e
        return self

    def __exit__(self, *exc):
        try:
            self.m.logout()
        except Exception:
            pass

    def _ok(self, r, oque):
        tipo, dados = r
        if tipo != "OK":
            raise ErroCorreio(f"Falha ao {oque}: {_msg(dados)}")
        return dados

    # ---- pastas
    def pastas(self):
        if self._pastas is None:
            out = []
            for linha in self._ok(self.m.list(), "listar pastas"):
                if not isinstance(linha, bytes):
                    continue
                m = _RE_LIST.match(linha)
                if not m:
                    continue
                nome = m.group("nome").strip()
                if nome.startswith(b'"'):
                    nome = nome[1:-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\")
                flags = m.group("flags").decode()
                if "\\Noselect" in flags or "\\NonExistent" in flags:
                    continue
                out.append(dict(nome=utf7_decode(nome.decode()), flags=flags, delim=m.group("delim").strip(b'"').decode()))
            out.sort(key=lambda p: (p["nome"] != "INBOX", p["nome"].lower()))
            self._pastas = out
        return self._pastas

    def pasta_especial(self, flag: str, criar=False):
        campo = {"\\Archive": "pasta_arquivo", "\\Trash": "pasta_lixeira", "\\Sent": "pasta_enviados"}[flag]
        salvo = getattr(self.conta, campo)
        nomes = [p["nome"] for p in self.pastas()]
        if salvo and salvo in nomes:
            return salvo
        achada = next((p["nome"] for p in self.pastas() if flag in p["flags"]), None)
        if not achada:
            achada = next((n for n in NOMES_PADRAO[flag] if n in nomes), None)
        if not achada and criar:
            delim = next((p["delim"] for p in self.pastas() if p["nome"] == "INBOX"), ".") or "."
            achada = "INBOX" + delim + NOMES_PADRAO[flag][1]
            self._ok(self.m.create(_q(achada)), "criar a pasta " + achada)
            self.m.subscribe(_q(achada))
            self._pastas = None
        if achada and achada != salvo and getattr(self.conta, "pk", None):
            setattr(self.conta, campo, achada)
            type(self.conta).objects.filter(pk=self.conta.pk).update(**{campo: achada})
        return achada

    def _selecionar(self, pasta, leitura=True):
        tipo, dados = self.m.select(_q(pasta), readonly=leitura)
        if tipo != "OK":
            raise ErroCorreio(f"Pasta {pasta} não encontrada.")
        return int(dados[0] or 0)

    # ---- lista
    def buscar_uids(self, pasta="INBOX", busca=None):
        self._selecionar(pasta)
        if busca:
            self.m.literal = busca.encode("utf-8")
            dados = self._ok(self.m.uid("SEARCH", "CHARSET", "UTF-8", "TEXT"), "buscar")
        else:
            dados = self._ok(self.m.uid("SEARCH", None, "ALL"), "listar")
        uids = [int(x) for x in (dados[0] or b"").split()]
        uids.sort(reverse=True)
        return uids

    def listar(self, pasta="INBOX", busca=None, pagina=0, limite=LIMITE_PAGINA):
        uids = self.buscar_uids(pasta, busca)
        fatia = uids[pagina * limite:(pagina + 1) * limite]
        itens = []
        if fatia:
            conjunto = ",".join(str(u) for u in fatia)
            dados = self._ok(self.m.uid("FETCH", conjunto,
                                        "(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"),
                             "ler a lista")
            for parte in dados:
                if not isinstance(parte, tuple):
                    continue
                meta, cab = parte
                m = _RE_FETCH.search(meta)
                if not m:
                    continue
                h = message_from_bytes(cab, policy=policy.compat32)
                nome, email = parseaddr(texto_cabecalho(h.get("From")))
                flags = re.search(rb"FLAGS \(([^)]*)\)", meta)
                flags = flags.group(1).decode() if flags else ""
                tam = re.search(rb"RFC822\.SIZE (\d+)", meta)
                itens.append(Resumo(
                    conta=self.conta, pasta=pasta, uid=m.group(1).decode(), de_nome=nome or email, de_email=email,
                    assunto=texto_cabecalho(h.get("Subject")) or "(sem assunto)", data=_data(h.get("Date")),
                    lido="\\Seen" in flags, respondido="\\Answered" in flags, tamanho=int(tam.group(1)) if tam else 0,
                    anexo=b'"attachment"' in meta.lower() or b'("name"' in meta.lower()))
        itens.sort(key=lambda r: r.data or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return itens, len(uids)

    def nao_lidos(self, pasta="INBOX"):
        dados = self._ok(self.m.status(_q(pasta), "(UNSEEN)"), "contar")
        m = re.search(rb"UNSEEN (\d+)", dados[0] or b"")
        return int(m.group(1)) if m else 0

    # ---- mensagem
    def bruto(self, pasta, uid, marcar_lido=False):
        self._selecionar(pasta, leitura=not marcar_lido)
        dados = self._ok(self.m.uid("FETCH", str(uid), "(BODY.PEEK[])"), "abrir a mensagem")
        for parte in dados:
            if isinstance(parte, tuple):
                if marcar_lido:
                    self.m.uid("STORE", str(uid), "+FLAGS", "(\\Seen)")
                return parte[1]
        raise ErroCorreio("Mensagem não encontrada (talvez já tenha sido movida ou apagada).")

    def marcar(self, pasta, uid, flag, ligar=True):
        self._selecionar(pasta, leitura=False)
        self._ok(self.m.uid("STORE", str(uid), "+FLAGS" if ligar else "-FLAGS", f"({flag})"), "marcar")

    def mover(self, pasta, uid, destino):
        if destino == pasta:
            return
        self._selecionar(pasta, leitura=False)
        caps = getattr(self.m, "capabilities", ())
        if "MOVE" in caps:
            self._ok(self.m.uid("MOVE", str(uid), _q(destino)), "mover")
            return
        self._ok(self.m.uid("COPY", str(uid), _q(destino)), "copiar")
        self._ok(self.m.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)"), "marcar para remoção")
        if "UIDPLUS" in caps:
            self.m.uid("EXPUNGE", str(uid))
        else:
            self.m.expunge()

    def guardar_enviado(self, bruto: bytes):
        pasta = self.pasta_especial("\\Sent", criar=True)
        self._ok(self.m.append(_q(pasta), "(\\Seen)", imaplib.Time2Internaldate(time.time()), bruto), "salvar em Enviados")


def _msg(e):
    a = e.args[0] if getattr(e, "args", None) else e
    if isinstance(a, list):
        a = a[0] if a else ""
    return a.decode("utf-8", "replace") if isinstance(a, bytes) else str(a)


# ---------------------------------------------------------------- SMTP
def enderecos(*textos: str):
    """E-mails de um ou mais campos (Para, Cc...). Ignora campos vazios, que fariam o parser descartar tudo."""
    return [e for _, e in getaddresses([t.strip(" ,;") for t in textos if t and t.strip(" ,;")]) if "@" in e]


def montar(conta, para, cc, assunto, corpo, em_resposta_a="", referencias="", anexos=()):
    msg = EmailMessage()
    msg["From"] = conta.remetente
    msg["To"] = para
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = assunto
    msg["Date"] = datetime.now(timezone.utc).astimezone()
    msg["Message-ID"] = make_msgid(domain=conta.email.split("@")[-1])
    if em_resposta_a:
        msg["In-Reply-To"] = em_resposta_a
        msg["References"] = (referencias + " " + em_resposta_a).strip()
    msg.set_content(corpo)
    for nome, tipo, dados in anexos:
        principal, _, sub = (tipo or "application/octet-stream").partition("/")
        msg.add_attachment(dados, maintype=principal, subtype=sub or "octet-stream", filename=nome)
    return msg


def enviar(conta, msg: EmailMessage):
    destinos = enderecos(msg.get("To", "")) + enderecos(msg.get("Cc", "")) + enderecos(msg.get("Bcc", ""))
    if not destinos:
        raise ErroCorreio("Informe pelo menos um destinatário.")
    ctx = ssl.create_default_context()
    try:
        if conta.smtp_seguranca == "ssl":
            s = smtplib.SMTP_SSL(conta.smtp_host, conta.smtp_porta, context=ctx, timeout=TIMEOUT)
        else:
            s = smtplib.SMTP(conta.smtp_host, conta.smtp_porta, timeout=TIMEOUT)
            s.starttls(context=ctx)
        with s:
            s.login(conta.usuario_login, conta.senha)
            s.send_message(msg, from_addr=conta.email, to_addrs=destinos)
    except smtplib.SMTPAuthenticationError as e:
        raise ErroCorreio("Login recusado pelo servidor SMTP. Confira usuário e senha.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise ErroCorreio(f"Falha ao enviar pelo SMTP ({e}).") from e


def testar_smtp(conta):
    ctx = ssl.create_default_context()
    try:
        if conta.smtp_seguranca == "ssl":
            s = smtplib.SMTP_SSL(conta.smtp_host, conta.smtp_porta, context=ctx, timeout=TIMEOUT)
        else:
            s = smtplib.SMTP(conta.smtp_host, conta.smtp_porta, timeout=TIMEOUT)
            s.starttls(context=ctx)
        with s:
            s.login(conta.usuario_login, conta.senha)
    except smtplib.SMTPAuthenticationError as e:
        raise ErroCorreio("Login recusado pelo servidor SMTP. Confira usuário e senha.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise ErroCorreio(f"Não consegui conectar no SMTP {conta.smtp_host}:{conta.smtp_porta} ({e}).") from e
