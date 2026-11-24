from django import forms

from .models import ContaEmail


class ContaEmailForm(forms.ModelForm):
    senha = forms.CharField(label="senha do e-mail", required=False, strip=False,
                            widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
                            help_text="Guardada criptografada. Deixe em branco para manter a atual.")

    class Meta:
        model = ContaEmail
        fields = ["empresa", "email", "nome_exibicao", "login", "imap_host", "imap_porta",
                  "smtp_host", "smtp_porta", "smtp_seguranca", "assinatura", "ativa"]
        widgets = {"assinatura": forms.Textarea(attrs={"rows": 4})}
        help_texts = {"imap_host": "No HostGator normalmente mail.seudominio.com.br (veja no cPanel → Contas de e-mail → Configurar cliente).",
                      "smtp_host": "Normalmente o mesmo do IMAP."}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for nome in ("imap_host", "smtp_host"):
            self.fields[nome].required = False
        if not self.instance.pk:
            self.fields["senha"].required = True
            self.fields["senha"].help_text = "Guardada criptografada; nunca aparece de volta na tela."

    def clean(self):
        d = super().clean()
        email = d.get("email") or ""
        dominio = email.split("@")[-1] if "@" in email else ""
        if not d.get("imap_host") and dominio:
            d["imap_host"] = "mail." + dominio
        if not d.get("smtp_host"):
            d["smtp_host"] = d.get("imap_host")
        if d.get("smtp_seguranca") == "starttls" and d.get("smtp_porta") == 465:
            d["smtp_porta"] = 587
        return d


class VariosArquivos(forms.ClearableFileInput):
    allow_multiple_selected = True


class EscreverForm(forms.Form):
    conta = forms.ModelChoiceField(queryset=ContaEmail.objects.none(), label="De", empty_label=None)
    para = forms.CharField(label="Para", widget=forms.TextInput(attrs={"style": "width:100%"}))
    cc = forms.CharField(label="Cc", required=False, widget=forms.TextInput(attrs={"style": "width:100%"}))
    assunto = forms.CharField(widget=forms.TextInput(attrs={"style": "width:100%"}))
    corpo = forms.CharField(label="Mensagem", widget=forms.Textarea(attrs={"rows": 16, "style": "width:100%"}))
    anexos = forms.FileField(required=False, widget=VariosArquivos)
    em_resposta_a = forms.CharField(required=False, widget=forms.HiddenInput)
    referencias = forms.CharField(required=False, widget=forms.HiddenInput)
    origem_pasta = forms.CharField(required=False, widget=forms.HiddenInput)
    origem_uid = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, usuario, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["conta"].queryset = ContaEmail.objects.filter(usuario=usuario, ativa=True)
