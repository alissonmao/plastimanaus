"""Telas de configuração: Sistema → Integrações (chaves, só administradores) e Secretaria → Configurações (cada usuário)."""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from . import config, servicos
from .acesso import secretaria_obrigatoria
from .models import Integracao, PerfilSecretaria


def _https(request):
    from django.conf import settings
    return request.is_secure() or settings.SECRETARIA_PERMITIR_HTTP


def integracoes(request):
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == "POST":
        nome = request.POST.get("nome")
        if nome not in config.NOMES:
            raise PermissionDenied
        acao = request.POST.get("acao")
        if not _https(request):
            messages.error(request, "Ative o HTTPS para salvar chaves.")
        elif acao == "salvar":
            valor = request.POST.get("valor", "").strip()
            if not valor:
                messages.error(request, "Informe o valor.")
            else:
                config.salvar(nome, valor, request.user)
                messages.success(request, "Chave salva. Use Testar para conferir.")
        elif acao == "remover":
            config.salvar(nome, "", request.user)
            messages.success(request, "Chave removida do ERP. Lembre de revogar também no site do serviço.")
        elif acao == "gerar" and nome == "ANGEL_TOKEN":
            import secrets
            config.salvar(nome, secrets.token_urlsafe(32), request.user)
            messages.success(request, "Novo token gerado; o antigo deixou de valer. Publique de novo o Angel para ele usar o novo.")
        elif acao == "testar":
            ok, msg = servicos.testar(nome)
            Integracao.objects.filter(nome=nome).update(testado_em=timezone.now() if ok else None, ultimo_erro="" if ok else msg)
            (messages.success if ok else messages.error)(request, msg)
        return redirect("sec_integracoes")
    salvos = {i.nome: i for i in Integracao.objects.all()}
    linhas = []
    for nome, titulo, ajuda, secreto in config.CHAVES:
        obj = salvos.get(nome)
        v = config.obter(nome)
        linhas.append(dict(nome=nome, titulo=titulo, ajuda=ajuda, secreto=secreto, definido=bool(v),
                           mostra=config.mascarar(v) if secreto else v, origem="ERP" if obj and obj.valor_cifrado else (".env" if v else ""),
                           obj=obj, testavel=nome in servicos.TESTAVEIS))
    return render(request, "secretaria/integracoes.html", dict(
        titulo="Integrações", linhas=linhas, https=_https(request), ia=bool(config.obter("ANTHROPIC_API_KEY")),
        voz_eleven=bool(config.obter("ELEVENLABS_API_KEY")), whatsapp=servicos.whatsapp_disponivel()))


class PerfilForm(forms.ModelForm):
    icloud_senha = forms.CharField(label="Senha de app do iCloud", required=False, strip=True,
                                   widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
                                   help_text="Crie em appleid.apple.com → Iniciar sessão e segurança → Senhas de app. Deixe em branco para manter.")

    class Meta:
        model = PerfilSecretaria
        fields = ["whatsapp", "icloud_usuario", "briefing_ativo", "briefing_hora", "triagem_ativa", "avisos_whatsapp", "analise_semanal"]
        widgets = {"briefing_hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}


def perfil_de(usuario):
    p, _ = PerfilSecretaria.objects.get_or_create(usuario=usuario)
    return p


@secretaria_obrigatoria
def preferencias(request):
    perfil = perfil_de(request.user)
    form = PerfilForm(request.POST or None, instance=perfil)
    if request.method == "POST":
        if request.POST.get("remover_icloud"):
            perfil.icloud_usuario, perfil.icloud_senha, perfil.agenda_calendarios, perfil.agenda_padrao = "", "", [], ""
            perfil.save()
            messages.success(request, "Agenda do iCloud desconectada.")
            return redirect("sec_preferencias")
        if form.is_valid():
            p = form.save(commit=False)
            if form.cleaned_data.get("icloud_senha"):
                if not _https(request):
                    messages.error(request, "Ative o HTTPS para salvar a senha do iCloud.")
                    return redirect("sec_preferencias")
                p.icloud_senha = form.cleaned_data["icloud_senha"]
            p.save()
            msg = "Preferências salvas."
            if p.icloud_usuario and p.icloud_senha_cifrada and (form.cleaned_data.get("icloud_senha") or "icloud_usuario" in form.changed_data):
                from . import agenda
                try:
                    cals = agenda.calendarios(p)
                    if not p.agenda_calendarios:
                        p.agenda_calendarios = [c["url"] for c in cals]
                    if not p.agenda_padrao and cals:
                        p.agenda_padrao = cals[0]["url"]
                    p.save()
                    msg += f" iCloud conectado: {len(cals)} calendário(s)."
                except agenda.ErroAgenda as e:
                    messages.error(request, f"Não consegui conectar no iCloud: {e}")
            if request.POST.get("cal_form"):
                p.agenda_calendarios = request.POST.getlist("calendarios")
                p.agenda_padrao = request.POST.get("agenda_padrao", p.agenda_padrao)
                p.save()
            messages.success(request, msg)
            return redirect("sec_preferencias")
    cals = []
    if perfil.icloud_usuario and perfil.icloud_senha_cifrada:
        from . import agenda
        try:
            cals = agenda.calendarios(perfil)
        except agenda.ErroAgenda as e:
            messages.error(request, f"iCloud: {e}")
    return render(request, "secretaria/preferencias.html", dict(
        titulo="Configurações da Secretaria", form=form, perfil=perfil, cals=cals, https=_https(request),
        angel_numero=config.obter("ANGEL_WHATSAPP")))
