#!/usr/bin/env bash
# Atualiza o código a partir do GitHub e reinicia. Rodar como root em /opt/plastimanaus.
set -euo pipefail
cd /opt/plastimanaus
git pull --ff-only
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput -v0
chown -R plastimanaus:www-data /opt/plastimanaus
systemctl restart plastimanaus 2>/dev/null || true
