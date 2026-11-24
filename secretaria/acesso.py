"""Quem pode usar a Secretaria: usuários marcados no cadastro (grupo "Secretaria")."""
from functools import wraps

from django.core.exceptions import PermissionDenied

GRUPO = "Secretaria"


def tem_secretaria(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.groups.filter(name=GRUPO).exists())


def secretaria_obrigatoria(view):
    @wraps(view)
    def interna(request, *args, **kwargs):
        if not tem_secretaria(request.user):
            raise PermissionDenied("Seu usuário não tem acesso à Secretaria.")
        return view(request, *args, **kwargs)
    return interna
