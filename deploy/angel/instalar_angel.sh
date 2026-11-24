#!/usr/bin/env bash
# Instala o Angel (OpenClaw + Whisper + ffmpeg) para o usuário plastimanaus. Rodar como root, uma vez,
# depois de cadastrar em Sistema → Integrações: chave da Anthropic e número do Angel; e o seu WhatsApp em Secretaria → Configurações.
# O pareamento do WhatsApp é por QR code (último passo, feito junto com o usuário).
set -euo pipefail
cd /opt/plastimanaus
U=plastimanaus
H=/home/$U
apt-get install -y -q ffmpeg curl ca-certificates >/dev/null
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 24 ]; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash - >/dev/null
  apt-get install -y -q nodejs >/dev/null
fi
npm install -g openclaw@latest --allow-scripts=openclaw >/dev/null
.venv/bin/pip install -q faster-whisper
mkdir -p "$H" && chown $U "$H" && usermod -d "$H" $U || true
loginctl enable-linger $U
install -m 755 deploy/angel/angel-erp /usr/local/bin/angel-erp
sudo -u $U HOME=$H .venv/bin/python manage.py angel_config
# Baixa o modelo do Whisper (small) já na instalação
sudo -u $U HOME=$H .venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" >/dev/null
echo "Pronto. Próximo passo (com o usuário): sudo -iu $U openclaw onboard --install-daemon  e  openclaw channels login --channel whatsapp (QR code)."
