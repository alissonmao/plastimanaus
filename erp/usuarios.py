"""Cadastros → Usuários: quem acessa o ERP e quem tem a Secretaria."""
from django import forms
from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from secretaria.acesso import GRUPO

from .models import PerfilUsuario

AREAS = ["Financeiro", "Vendas", "Produção", "Cadastro"]


class UsuarioForm(forms.ModelForm):
    secretaria = forms.BooleanField(label="Acesso à Secretaria", required=False,
                                    help_text="E-mail, agenda, lembretes, diário e Angel. Cada usuário vê só os próprios dados.")
    areas = forms.MultipleChoiceField(label="Áreas em Problemas para resolver", required=False, choices=[(a, a) for a in AREAS],
                                      widget=forms.CheckboxSelectMultiple,
                                      help_text="Quais avisos a pessoa vê. Administrador vê todos.")
    vendedor = forms.CharField(label="Vendedor (nome no Omie)", required=False, max_length=200,
                               help_text="Preencha só para vendedor: ele verá apenas os avisos da própria carteira.")
    senha1 = forms.CharField(label="Nova senha", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                             help_text="Deixe em branco para manter a atual.")
    senha2 = forms.CharField(label="Repita a nova senha", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]
        labels = {"username": "Usuário (login)", "first_name": "Nome", "last_name": "Sobrenome", "is_active": "Ativo",
                  "is_staff": "Administrador (gerencia usuários e cadastros)"}
        help_texts = {"username": "", "is_active": "Desmarque para bloquear o acesso sem apagar o usuário.", "is_staff": ""}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:
            self.fields["secretaria"].initial = self.instance.groups.filter(name=GRUPO).exists()
            self.fields["areas"].initial = list(self.instance.groups.filter(name__in=AREAS).values_list("name", flat=True))
            p = PerfilUsuario.objects.filter(usuario=self.instance).first()
            self.fields["vendedor"].initial = p.vendedor if p else ""
        else:
            self.fields["senha1"].required = True
            self.fields["senha1"].help_text = ""

    def clean(self):
        d = super().clean()
        s1, s2 = d.get("senha1"), d.get("senha2")
        if s1 or s2:
            if s1 != s2:
                self.add_error("senha2", "As senhas não conferem.")
            else:
                try:
                    validate_password(s1, self.instance)
                except forms.ValidationError as e:
                    self.add_error("senha1", e)
        return d


def _so_admin(request):
    if not request.user.is_staff:
        raise PermissionDenied


def lista(request):
    _so_admin(request)
    usuarios = User.objects.order_by("-is_active", "username").prefetch_related("groups")
    for u in usuarios:
        u.secretaria = any(g.name == GRUPO for g in u.groups.all())
    return render(request, "erp/usuarios.html", dict(titulo="Usuários", usuarios=usuarios))


def form(request, pk=None):
    _so_admin(request)
    obj = get_object_or_404(User, pk=pk) if pk else None
    if obj and obj.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    f = UsuarioForm(request.POST or None, instance=obj)
    if request.method == "POST" and f.is_valid():
        if obj and obj.pk == request.user.pk and not f.cleaned_data["is_active"]:
            f.add_error("is_active", "Você não pode desativar o seu próprio usuário.")
        else:
            u = f.save(commit=False)
            if f.cleaned_data.get("senha1"):
                u.set_password(f.cleaned_data["senha1"])
            u.save()
            grupo, _ = Group.objects.get_or_create(name=GRUPO)
            (u.groups.add if f.cleaned_data["secretaria"] else u.groups.remove)(grupo)
            for a in AREAS:
                g, _ = Group.objects.get_or_create(name=a)
                (u.groups.add if a in f.cleaned_data["areas"] else u.groups.remove)(g)
            PerfilUsuario.objects.update_or_create(usuario=u, defaults=dict(vendedor=f.cleaned_data["vendedor"].strip()))
            messages.success(request, f"Usuário {u.username} salvo.")
            return redirect("usuarios")
    return render(request, "erp/form.html", dict(titulo=f"Usuário {obj.username}" if obj else "Novo usuário",
                                                  form=f, voltar="/usuarios/"))
