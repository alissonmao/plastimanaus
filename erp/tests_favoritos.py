"""Menu Rotina: favoritar e desfavoritar telas."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Favorito


class FavoritosTest(TestCase):
    def setUp(self):
        self.u = User.objects.create_superuser("adm", "", "x")
        self.client.force_login(self.u)

    def test_favoritar_aparece_no_menu_e_desfazer(self):
        r = self.client.get("/fluxo-caixa/")
        self.assertContains(r, "Marque a ☆")
        self.assertContains(r, "Colocar na Rotina")
        r = self.client.post("/favoritos/alternar/", dict(url="/fluxo-caixa/", titulo="Entradas e Saídas base Omie"), follow=True)
        self.assertEqual(r.redirect_chain[-1][0], "/fluxo-caixa/")
        self.assertContains(r, "Tirar da Rotina")
        self.assertContains(r, '<a href="/fluxo-caixa/" class="on">Entradas e Saídas base Omie</a>', html=False)
        self.assertNotContains(r, "Marque a ☆")
        self.client.post("/favoritos/alternar/", dict(url="/fluxo-caixa/"))
        self.assertFalse(Favorito.objects.exists())

    def test_cada_usuario_tem_os_seus_e_url_externa_bloqueada(self):
        self.client.post("/favoritos/alternar/", dict(url="/problemas/", titulo="Problemas"))
        outro = User.objects.create_user("b", password="x")
        self.client.force_login(outro)
        self.assertContains(self.client.get("/problemas/"), "Marque a ☆")
        r = self.client.post("/favoritos/alternar/", dict(url="//site-mau.com/", titulo="x"))
        self.assertEqual(r["Location"], "/")
        self.assertEqual(Favorito.objects.filter(usuario=outro).count(), 0)
