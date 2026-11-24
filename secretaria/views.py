"""Secretaria → E-mail: caixa de entrada, leitura, arquivar/apagar, responder e escrever."""
from datetime import datetime, timezone
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone as djtz
from django.views.decorators.http import require_POST

from . import correio as M
from . import ia
from .acesso import secretaria_obrigatoria
from .forms import ContaEmailForm, EscreverForm
from .models import ContaEmail

LIMITE_ANEXOS = 20 * 1024 * 1024


def _contas(request):
    return ContaEmail.objects.filter(usuario=request.user, ativa=True)


def _conta(request, pk):
    return get_object_or_404(ContaEmail, pk=pk, usuario=request.user)


def _https_ok(request):
    return request.is_secure() or settings.SECRETARIA_PERMITIR_HTTP


# ===================================================================== Tela única de e-mail
def _nao_lidos(conta, cx=None):
    """Não lidos da Caixa de entrada, com cache de 1 minuto para o painel não abrir todas as contas a cada clique."""
    chave = f"sec-naolidos-{conta.pk}"
    if cx is not None:
        n = cx.nao_lidos("INBOX")
        cache.set(chave, n, 60)
        return n
    n = cache.get(chave)
    if n is None:
        try:
            with M.Caixa(conta) as c2:
                n = c2.nao_lidos("INBOX")
        except M.ErroCorreio:
            n = -1
        cache.set(chave, n, 60)
    return n


def _painel(request, contas, sel="todas", pasta="INBOX", pastas=None, modo="caixa"):
    """Contexto da coluna da esquerda (contas, pastas, escrever), igual em todas as telas de e-mail."""
    for c in contas:
        if not hasattr(c, "nao_lidos"):
            c.nao_lidos = _nao_lidos(c)
    return dict(contas_nav=contas, sel=sel, pasta=pasta, pastas=pastas or [], modo=modo,
                total_nao_lidos=sum(max(c.nao_lidos or 0, 0) for c in contas))


def _qs(sel, pasta, q, pagina):
    return urlencode({k: v for k, v in dict(conta=sel, pasta=pasta, q=q, p=pagina or "").items() if v})


@secretaria_obrigatoria
def caixa(request, pk=None, uid=None):
    """Lista (e, se houver uid, a leitura) na mesma tela."""
    ver_conta = _conta(request, pk) if pk else None
    contas = list(_contas(request))
    if not contas:
        return redirect("sec_contas")
    sel = request.GET.get("conta") or (str(pk) if pk else "todas")
    pasta = request.GET.get("pasta", "INBOX")
    busca = request.GET.get("q", "").strip()
    pagina = max(int(request.GET.get("p", 0) or 0), 0)
    imagens = request.GET.get("imagens") == "1"
    alvo = contas if sel == "todas" else [c for c in contas if str(c.pk) == sel]
    if not alvo:
        raise Http404
    lista_pasta = "INBOX" if sel == "todas" else pasta
    ver_pasta = request.GET.get("ler_pasta") or lista_pasta
    itens, erros, total, pastas, msg = [], [], 0, [], None
    por_conta = M.LIMITE_PAGINA if len(alvo) == 1 else max(15, M.LIMITE_PAGINA // len(alvo))
    for c in alvo:
        try:
            with M.Caixa(c) as cx:
                if ver_conta and c.pk == ver_conta.pk:
                    try:
                        msg = M.interpretar(cx.bruto(ver_pasta, uid, marcar_lido=True), str(uid), ver_pasta, imagens)
                    except M.ErroCorreio as e:
                        messages.error(request, str(e))
                lst, n = cx.listar(lista_pasta, busca or None, pagina, por_conta)
                itens += lst
                total += n
                c.nao_lidos = _nao_lidos(c, cx)
                if len(alvo) == 1:
                    pastas = cx.pastas_organizadas()
        except M.ErroCorreio as e:
            erros.append(f"{c.empresa}: {e}")
    if ver_conta and msg is None and ver_conta not in alvo:
        try:
            with M.Caixa(ver_conta) as cx:
                msg = M.interpretar(cx.bruto(ver_pasta, uid, marcar_lido=True), str(uid), ver_pasta, imagens)
        except M.ErroCorreio as e:
            messages.error(request, str(e))
    itens.sort(key=lambda r: r.data or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    rotulo = next((p["rotulo"] for p in pastas if p["nome"] == lista_pasta), M.nome_pasta(lista_pasta))
    ctx = _painel(request, contas, sel, lista_pasta, pastas)
    ctx.update(titulo="E-mail", q=busca, itens=itens, erros=erros, total=total, pagina=pagina,
               pasta_rotulo="Todas as caixas" if sel == "todas" else rotulo,
               tem_mais=(pagina + 1) * por_conta < total, qs=_qs(sel, lista_pasta, busca, pagina),
               qs_sem_p=_qs(sel, lista_pasta, busca, 0), m=msg, conta=ver_conta, imagens=imagens,
               ver_uid=str(uid) if uid else "", ver_conta_id=str(pk) if pk else "")
    return render(request, "secretaria/caixa.html", ctx)


ler = caixa


@secretaria_obrigatoria
def anexo(request, pk, uid, n):
    conta = _conta(request, pk)
    pasta = request.GET.get("pasta", "INBOX")
    try:
        with M.Caixa(conta) as cx:
            nome, tipo, dados = M.extrair_anexo(cx.bruto(pasta, uid), n)
    except M.ErroCorreio as e:
        raise Http404(str(e))
    resp = HttpResponse(dados, content_type="application/octet-stream")
    resp["Content-Disposition"] = djtz_disposition(nome)
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def djtz_disposition(nome):
    from urllib.parse import quote
    seguro = "".join(ch if ch.isascii() and ch not in '"\\' and ch.isprintable() else "_" for ch in nome)
    return f"attachment; filename=\"{seguro}\"; filename*=UTF-8''{quote(nome)}"


@secretaria_obrigatoria
@require_POST
def acao(request, pk, uid):
    conta = _conta(request, pk)
    pasta = request.POST.get("pasta", "INBOX")
    oque = request.POST.get("acao")
    qs = request.POST.get("qs") or urlencode(dict(conta=conta.pk, pasta=pasta))
    voltar = f"{reverse('sec_caixa')}?{qs}"
    try:
        with M.Caixa(conta) as cx:
            cache.delete(f"sec-naolidos-{conta.pk}")
            if oque == "arquivar":
                cx.mover(pasta, uid, cx.pasta_especial("\\Archive", criar=True))
                messages.success(request, "E-mail arquivado.")
            elif oque == "apagar":
                lixeira = cx.pasta_especial("\\Trash", criar=True)
                if pasta == lixeira:
                    messages.error(request, "O e-mail já está na Lixeira.")
                else:
                    cx.mover(pasta, uid, lixeira)
                    messages.success(request, "E-mail enviado para a Lixeira.")
            elif oque == "nao_lido":
                cx.marcar(pasta, uid, "\\Seen", ligar=False)
                messages.success(request, "Marcado como não lido.")
            elif oque == "entrada":
                cx.mover(pasta, uid, "INBOX")
                messages.success(request, "E-mail devolvido para a Caixa de entrada.")
            else:
                raise Http404
    except M.ErroCorreio as e:
        messages.error(request, str(e))
    return redirect(voltar)


# ===================================================================== Escrever / responder
def _citar(msg):
    data = djtz.localtime(msg.data).strftime("%d/%m/%Y %H:%M") if msg.data else ""
    corpo = msg.texto or ia._sem_html(msg.html)
    citado = "\n".join("> " + l for l in corpo.strip().splitlines())
    return f"\n\n\nEm {data}, {msg.de} <{msg.de_email}> escreveu:\n{citado}\n"


@secretaria_obrigatoria
def escrever(request):
    contas = _contas(request)
    if not contas.exists():
        return redirect("sec_contas")
    original = None
    conta_id = request.GET.get("conta") or request.POST.get("conta")
    uid, pasta = request.GET.get("uid") or request.POST.get("origem_uid"), request.GET.get("pasta") or request.POST.get("origem_pasta") or "INBOX"
    modo = request.GET.get("modo", "")
    if uid and conta_id:
        conta = _conta(request, conta_id)
        try:
            with M.Caixa(conta) as cx:
                original = M.interpretar(cx.bruto(pasta, uid), str(uid), pasta)
        except M.ErroCorreio as e:
            messages.error(request, str(e))
    if request.method == "POST":
        form = EscreverForm(request.user, request.POST, request.FILES)
        arquivos = request.FILES.getlist("anexos")
        if sum(a.size for a in arquivos) > LIMITE_ANEXOS:
            form.add_error(None, "Os anexos passam de 20 MB.")
        if form.is_valid():
            d = form.cleaned_data
            conta = d["conta"]
            msg = M.montar(conta, d["para"], d["cc"], d["assunto"], d["corpo"], d["em_resposta_a"], d["referencias"],
                           [(a.name, a.content_type, a.read()) for a in arquivos])
            try:
                M.enviar(conta, msg)
            except M.ErroCorreio as e:
                form.add_error(None, str(e))
            else:
                aviso = ""
                try:
                    with M.Caixa(conta) as cx:
                        cx.guardar_enviado(msg.as_bytes())
                        if d["origem_uid"] and str(conta.pk) == str(conta_id):
                            cx.marcar(d["origem_pasta"] or "INBOX", d["origem_uid"], "\\Answered")
                except M.ErroCorreio as e:
                    aviso = f" (não consegui salvar a cópia em Enviados: {e})"
                messages.success(request, "E-mail enviado." + aviso)
                return redirect(f"{reverse('sec_caixa')}?conta={conta.pk}")
    else:
        inicial = {"conta": conta_id or contas.first().pk}
        if original:
            if modo == "encaminhar":
                inicial.update(assunto=_prefixo("Enc: ", original.assunto), corpo=_assinatura(conta) + _citar(original))
            else:
                para = original.responder_para
                cc = ""
                if modo == "todos":
                    eu = {e.lower() for e in contas.values_list("email", flat=True)}
                    outros = [e for e in M.enderecos(original.para, original.cc) if e.lower() not in eu]
                    cc = ", ".join(outros)
                inicial.update(para=para, cc=cc, assunto=_prefixo("Re: ", original.assunto),
                               corpo=_assinatura(conta) + _citar(original), em_resposta_a=original.message_id,
                               referencias=original.referencias, origem_pasta=pasta, origem_uid=uid)
        else:
            c = contas.filter(pk=inicial["conta"]).first()
            inicial["corpo"] = _assinatura(c)
        form = EscreverForm(request.user, initial=inicial)
    ctx = _painel(request, list(contas), conta_id or "todas", modo="escrever")
    ctx.update(titulo="E-mail", acao_titulo="Responder" if original and modo != "encaminhar" else ("Encaminhar" if original else "Novo e-mail"),
               form=form, original=original, ia=ia.disponivel(), conta_id=conta_id, uid=uid, pasta_orig=pasta)
    return render(request, "secretaria/escrever.html", ctx)


def _prefixo(p, assunto):
    return assunto if assunto.lower().startswith(p.lower().strip()) else p + assunto


def _assinatura(conta):
    return f"\n\n-- \n{conta.assinatura}" if conta and conta.assinatura else ""


@secretaria_obrigatoria
@require_POST
def sugerir(request):
    conta = _conta(request, request.POST.get("conta"))
    try:
        with M.Caixa(conta) as cx:
            original = M.interpretar(cx.bruto(request.POST.get("pasta", "INBOX"), request.POST.get("uid")),
                                     request.POST.get("uid"), request.POST.get("pasta", "INBOX"))
        texto = ia.sugerir_resposta(conta, request.user, original, request.POST.get("instrucao", ""),
                                    request.POST.get("rascunho", ""))
    except (M.ErroCorreio, ia.ErroIA) as e:
        return JsonResponse({"erro": str(e)}, status=400)
    return JsonResponse({"texto": texto + "\n" + _citar(original)})


# ===================================================================== Contas
@secretaria_obrigatoria
def contas(request):
    ctx = _painel(request, list(_contas(request)), modo="contas")
    ctx.update(titulo="E-mail", contas=ContaEmail.objects.filter(usuario=request.user), https=_https_ok(request))
    return render(request, "secretaria/contas.html", ctx)


@secretaria_obrigatoria
def conta_form(request, pk=None):
    obj = _conta(request, pk) if pk else None
    if request.method == "POST" and request.POST.get("excluir") and obj:
        obj.delete()
        messages.success(request, "Conta removida do ERP (os e-mails continuam no servidor).")
        return redirect("sec_contas")
    form = ContaEmailForm(request.POST or None, instance=obj)
    if request.method == "POST" and not _https_ok(request):
        messages.error(request, "Por segurança, só é possível salvar senhas com o ERP em HTTPS. Ative o domínio com HTTPS primeiro.")
    elif request.method == "POST" and form.is_valid():
        conta = form.save(commit=False)
        conta.usuario = request.user
        if form.cleaned_data.get("senha"):
            conta.senha = form.cleaned_data["senha"]
        for campo in ("imap_host", "smtp_host", "smtp_porta"):
            setattr(conta, campo, form.cleaned_data[campo])
        erro = ""
        try:
            with M.Caixa(conta) as cx:
                cx.pastas()
            M.testar_smtp(conta)
            conta.verificada_em = djtz.now()
        except M.ErroCorreio as e:
            erro = str(e)
        conta.ultimo_erro = erro
        conta.save()
        if erro:
            messages.error(request, f"Conta salva, mas o teste falhou: {erro}")
            return redirect("sec_conta_editar", pk=conta.pk)
        messages.success(request, "Conta salva e testada: IMAP e SMTP funcionando.")
        return redirect("sec_contas")
    ctx = _painel(request, list(_contas(request)), modo="contas")
    ctx.update(titulo="E-mail", acao_titulo="Editar conta" if obj else "Nova conta de e-mail", form=form, obj=obj,
               https=_https_ok(request))
    return render(request, "secretaria/conta_form.html", ctx)
