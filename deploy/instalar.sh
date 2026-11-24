#!/usr/bin/env bash
# Instalação inicial em Ubuntu/Debian. Rodar como root no servidor:
#   bash deploy/instalar.sh
set -euo pipefail
APP=/opt/plastimanaus
REPO=https://github.com/alissonmao/plastimanaus.git

apt-get update
apt-get install -y python3 python3-venv python3-pip postgresql nginx git

id plastimanaus >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin plastimanaus
[ -d "$APP/.git" ] || git clone "$REPO" "$APP"
cd "$APP"

if [ ! -f .env ]; then
  DBPASS=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
  SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
  sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='plastimanaus'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER plastimanaus WITH PASSWORD '$DBPASS';"
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='plastimanaus'" | grep -q 1 || \
    sudo -u postgres createdb -O plastimanaus plastimanaus
  IP=$(hostname -I | awk '{print $1}')
  cat > .env <<ENV
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$SECRET
DJANGO_ALLOWED_HOSTS=$IP,localhost
DJANGO_HTTPS=0
DATABASE_URL=postgres://plastimanaus:$DBPASS@localhost:5432/plastimanaus
SUPABASE_URL=https://axwzrvqpfpiszjnbmhyl.supabase.co
SUPABASE_KEY=
ENV
  chmod 600 .env
fi

bash deploy/atualizar.sh
cp deploy/plastimanaus.service /etc/systemd/system/
cp deploy/nginx.conf /etc/nginx/sites-available/plastimanaus
ln -sf /etc/nginx/sites-available/plastimanaus /etc/nginx/sites-enabled/plastimanaus
rm -f /etc/nginx/sites-enabled/default
systemctl daemon-reload
systemctl enable --now plastimanaus
nginx -t && systemctl reload nginx
echo "Pronto. Crie o primeiro usuário: cd $APP && sudo -u plastimanaus .venv/bin/python manage.py createsuperuser"
