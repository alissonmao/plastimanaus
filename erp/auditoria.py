"""Auditoria do Omie: compara cada leitura com a anterior e registra o que foi criado, alterado ou excluído lá."""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect, render

from .models import AuditoriaOmie, FluxoCaixa, UsuarioOmie

log = logging.getLogger(__name__)

CAMPOS = {  # campo do ERP: rótulo
    "valor_conta": "Valor", "data_vencimento": "Vencimento", "data_previsao": "Previsão", "situacao": "Situação",
    "valor_pago": "Valor pago", "data_pagamento": "Data de pagamento", "data_emissao": "Emissão", "fornecedor": "Fornecedor/cliente",
    "cnpj_cpf": "CNPJ/CPF", "categoria": "Categoria", "departamento": "Departamento", "conta_corrente": "Conta corrente",
    "forma_pagamento": "Forma de pagamento", "numero_documento": "Documento", "parcela": "Parcela", "observacao": "Observação",
}
QUITADO = {"Pago", "Recebido"}
MAX_INFO = 60  # consultas extras ao Omie (quem alterou) por leitura


def _fmt(v):
    if v is None or v == "":
        return ""
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, Decimal):
        return f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v).strip()


def _norm(v):
    if isinstance(v, Decimal):
        return v.quantize(Decimal("0.01"))
    if isinstance(v, str):
        return v.strip() or None
    return v


def foto(de, ate):
    """Estado atual no ERP dos títulos do período (vindos do Omie)."""
    return {str(f["omie_codigo"]): f for f in FluxoCaixa.objects.filter(data_emissao__range=(de, ate)).exclude(omie_codigo=None)
            .values("omie_codigo", "tipo", *CAMPOS.keys())}


def _sensivel(campo, antes, depois):
    if campo == "valor_conta":
        return "Valor do título alterado"
    if campo == "data_vencimento" and antes and depois and depois > antes:
        return "Vencimento adiado"
    if campo == "situacao" and (antes or "").strip() in QUITADO and (depois or "").strip() not in QUITADO:
        return "Título quitado voltou a ficar em aberto (estorno?)"
    if campo == "valor_pago" and antes is not None and depois is not None and abs(depois) < abs(antes):
        return "Valor pago diminuiu"
    if campo in ("fornecedor", "cnpj_cpf", "conta_corrente"):
        return f"{CAMPOS[campo]} trocado"
    return ""


def comparar(antes: dict, rows: list[dict], sinc=None):
    """Gera os registros de auditoria (sem gravar)."""
    novos = {str(r["omie_codigo"]): r for r in rows if r.get("omie_codigo")}
    out = []

    def reg(codigo, r, tipo, **kw):
        out.append(AuditoriaOmie(sincronizacao=sinc, entidade="titulo", chave=codigo, tipo=tipo,
                                 natureza="receber" if (r.get("valor_conta") or 0) > 0 else "pagar",
                                 documento=(r.get("numero_documento") or "") + (f" parc. {r['parcela']}" if r.get("parcela") else ""),
                                 parte=(r.get("fornecedor") or "")[:300], valor=abs(r.get("valor_conta") or 0), **kw))

    hoje = date.today()
    for codigo, r in novos.items():
        a = antes.get(codigo)
        if a is None:
            retro = r.get("data_emissao") and r["data_emissao"] < hoje - timedelta(days=30)
            reg(codigo, r, "novo", depois=f"{_fmt(r.get('situacao'))} · venc. {_fmt(r.get('data_vencimento'))}",
                sensivel=bool(retro), motivo="Lançamento retroativo (emissão com mais de 30 dias)" if retro else "")
            continue
        for campo in CAMPOS:
            va, vn = _norm(a.get(campo)), _norm(r.get(campo))
            if va != vn:
                motivo = _sensivel(campo, va, vn)
                reg(codigo, r, "alterado", campo=campo, antes=_fmt(va), depois=_fmt(vn), sensivel=bool(motivo), motivo=motivo)
    for codigo, a in antes.items():
        if codigo not in novos:
            reg(codigo, a, "excluido", antes=f"{_fmt(a.get('situacao'))} · venc. {_fmt(a.get('data_vencimento'))}",
                sensivel=True, motivo="Título excluído ou cancelado no Omie")
    return out


def quem_alterou(registros):
    """Pergunta ao Omie quem incluiu/alterou cada título novo ou alterado (o Omie informa só o código do usuário)."""
    from . import omie
    feitos = {}
    for r in registros:
        if r.tipo == "excluido" or len(feitos) >= MAX_INFO:
            continue
        if r.chave not in feitos:
            ep, call = (("financas/contareceber/", "ConsultarContaReceber") if r.natureza == "receber"
                        else ("financas/contapagar/", "ConsultarContaPagar"))
            try:
                info = omie.chamar(ep, call, {"codigo_lancamento_omie": int(r.chave)}, tentativas=2).get("info") or {}
            except Exception as e:  # sem a informação, a auditoria continua valendo
                log.info("Omie: não consegui consultar %s: %s", r.chave, e)
                info = {}
            if r.tipo == "novo":
                feitos[r.chave] = (info.get("uInc") or "", f"{info.get('dInc', '')} {info.get('hInc', '')}".strip())
            else:
                feitos[r.chave] = (info.get("uAlt") or "", f"{info.get('dAlt', '')} {info.get('hAlt', '')}".strip())
        r.usuario_omie, r.alterado_no_omie = feitos[r.chave]


def gravar(registros):
    if not registros:
        return 0
    quem_alterou(registros)
    AuditoriaOmie.objects.bulk_create(registros, batch_size=500)
    sens = [r for r in registros if r.sensivel]
    if sens:
        _avisar(sens)
    return len(registros)


def _avisar(sens):
    """Avisa os administradores pela Angel (WhatsApp), quando ligada."""
    try:
        from django.contrib.auth import get_user_model

        from secretaria.acesso import tem_secretaria
        from secretaria.models import Notificacao
        nomes = dict(UsuarioOmie.objects.values_list("codigo", "nome"))
        linhas = [f"🔎 *Auditoria Omie*: {len(sens)} mudança{'s' if len(sens) > 1 else ''} sensíve{'is' if len(sens) > 1 else 'l'}"]
        for r in sens[:10]:
            quem = nomes.get(r.usuario_omie, r.usuario_omie)
            det = f"{CAMPOS.get(r.campo, '')}: {r.antes} → {r.depois}" if r.tipo == "alterado" else r.get_tipo_display()
            linhas.append(f"• {r.parte[:40]} ({_fmt(r.valor)}) — {r.motivo}. {det}" + (f" [por {quem}]" if quem else ""))
        if len(sens) > 10:
            linhas.append(f"… e mais {len(sens) - 10}. Veja em Sistema → Auditoria Omie.")
        for u in get_user_model().objects.filter(is_staff=True, is_active=True):
            if tem_secretaria(u):
                Notificacao.objects.create(usuario=u, tipo="auditoria", chave=f"aud-{sens[0].sincronizacao_id}-{sens[0].chave}-{len(sens)}",
                                           texto="\n".join(linhas))
    except Exception:
        log.exception("Aviso da auditoria falhou")


# ===================================================================== tela
def tela(request):
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == "POST" and request.POST.get("codigo"):
        cod = request.POST["codigo"].strip()[:40]
        nome = request.POST.get("nome", "").strip()[:150]
        if nome:
            UsuarioOmie.objects.update_or_create(codigo=cod, defaults={"nome": nome})
        else:
            UsuarioOmie.objects.filter(codigo=cod).delete()
        return redirect(request.get_full_path())
    g = request.GET
    qs = AuditoriaOmie.objects.all()
    hoje = date.today()
    de = g.get("de") or (hoje - timedelta(days=30)).isoformat()
    ate = g.get("ate") or hoje.isoformat()
    qs = qs.filter(detectado_em__date__gte=de, detectado_em__date__lte=ate)
    for k in ("tipo", "campo", "natureza", "usuario_omie"):
        if g.get(k):
            qs = qs.filter(**{k: g[k]})
    if g.get("sensivel"):
        qs = qs.filter(sensivel=True)
    if g.get("q"):
        qs = qs.filter(Q(parte__icontains=g["q"]) | Q(documento__icontains=g["q"]) | Q(chave=g["q"]))
    if g.get("valor_min"):
        try:
            qs = qs.filter(valor__gte=Decimal(g["valor_min"].replace(".", "").replace(",", ".")))
        except Exception:
            pass
    nomes = dict(UsuarioOmie.objects.values_list("codigo", "nome"))
    if g.get("exportar"):
        from .planilhas import xlsx_response
        return xlsx_response([{
            "Detectado em": r.detectado_em.astimezone().strftime("%d/%m/%Y %H:%M"), "Tipo": r.get_tipo_display(),
            "Natureza": r.natureza, "Fornecedor/cliente": r.parte, "Documento": r.documento, "Valor": r.valor,
            "Campo": CAMPOS.get(r.campo, r.campo), "Antes": r.antes, "Depois": r.depois, "Sensível": "sim" if r.sensivel else "",
            "Motivo": r.motivo, "Usuário Omie": nomes.get(r.usuario_omie, r.usuario_omie), "Alterado no Omie em": r.alterado_no_omie,
            "Código Omie": r.chave} for r in qs[:20000]], "auditoria-omie")
    total = qs.count()
    lista = list(qs[:500])
    for r in lista:
        r.campo_nome = CAMPOS.get(r.campo, r.campo)
        r.quem = nomes.get(r.usuario_omie, r.usuario_omie)
    codigos = sorted(set(AuditoriaOmie.objects.exclude(usuario_omie="").values_list("usuario_omie", flat=True)))
    ultima = None
    from .models import SincronizacaoOmie
    ultima = SincronizacaoOmie.objects.filter(status="ok").first()
    return render(request, "erp/auditoria_omie.html", dict(
        titulo="Auditoria Omie", lista=lista, total=total, f=g, de=de, ate=ate, campos=CAMPOS.items(), tipos=AuditoriaOmie.TIPOS,
        usuarios=[(c, nomes.get(c, "")) for c in codigos], sensiveis=qs.filter(sensivel=True).count(), ultima=ultima,
        qs_export=request.GET.urlencode()))
