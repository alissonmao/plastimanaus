#!/usr/bin/env bash
# Atualiza o código a partir do GitHub e reinicia. Rodar como root em /opt/plastimanaus.
set -euo pipefail
cd /opt/plastimanaus
git config --global --get-all safe.directory | grep -qx /opt/plastimanaus || git config --global --add safe.directory /opt/plastimanaus
git pull --ff-only
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
# Chave que criptografa as senhas da Secretaria: gerada uma única vez, fica só no .env
grep -q '^SECRETARIA_CHAVE=.\+' .env || echo "SECRETARIA_CHAVE=$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput -v0
chown -R plastimanaus:www-data /opt/plastimanaus
cp deploy/omie-sync.service deploy/omie-sync.timer deploy/secretaria-rotinas.service deploy/secretaria-rotinas.timer deploy/omie-auditoria.service deploy/omie-auditoria.timer /etc/systemd/system/
systemctl daemon-reload
# Rotinas da Secretaria (lembretes, agenda, triagem, briefing): sempre ligadas; sem WhatsApp os avisos só ficam registrados
systemctl enable --now secretaria-rotinas.timer >/dev/null 2>&1 || true
# Auditoria Omie: lê só Entradas e Saídas de hora em hora (7h–19h); o faturamento segue manual
systemctl enable --now omie-auditoria.timer >/dev/null 2>&1 || true
# Angel instalado? Reinstala a habilidade e a configuração a cada publicação
if id plastimanaus >/dev/null 2>&1 && sudo -u plastimanaus bash -lc 'command -v openclaw' >/dev/null 2>&1; then
  install -m 755 deploy/angel/angel-erp /usr/local/bin/angel-erp
  sudo -u plastimanaus HOME=/home/plastimanaus .venv/bin/python manage.py angel_config || true
  sudo -u plastimanaus XDG_RUNTIME_DIR=/run/user/$(id -u plastimanaus) systemctl --user restart openclaw-gateway >/dev/null 2>&1 || true
fi
# Sincronização diária só quando OMIE_SYNC_AUTO=1 no .env
if grep -q '^OMIE_SYNC_AUTO=1' .env; then systemctl enable --now omie-sync.timer >/dev/null 2>&1 || true
else systemctl disable --now omie-sync.timer >/dev/null 2>&1 || true; fi
systemctl restart plastimanaus 2>/dev/null || true
