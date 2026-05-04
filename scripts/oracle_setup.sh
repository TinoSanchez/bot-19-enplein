#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Lance ce script avec sudo: sudo bash scripts/oracle_setup.sh"
  exit 1
fi

APP_DIR="/opt/bot19"
SERVICE_FILE="/etc/systemd/system/bot19.service"
RUN_USER="${SUDO_USER:-ubuntu}"
if ! id "${RUN_USER}" >/dev/null 2>&1; then
  RUN_USER="ubuntu"
fi

echo "==> Mise a jour systeme et installation dependances..."
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip

echo "==> URL du repo GitHub (ex: https://github.com/TinoSanchez/bot-19-enplein.git)"
read -r REPO_URL
if [[ -z "${REPO_URL}" ]]; then
  echo "Repo URL obligatoire."
  exit 1
fi

echo "==> ID du serveur Discord (optionnel, Enter pour ignorer)"
read -r GUILD_ID

echo "==> Token Discord (cache):"
read -r -s DISCORD_TOKEN
echo
if [[ -z "${DISCORD_TOKEN}" ]]; then
  echo "DISCORD_TOKEN obligatoire."
  exit 1
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  echo "==> Repo deja present, mise a jour..."
  sudo -u "${RUN_USER}" git -C "${APP_DIR}" pull --ff-only
else
  echo "==> Clone du repo..."
  rm -rf "${APP_DIR}"
  sudo -u "${RUN_USER}" git clone "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Preparation environnement Python..."
sudo -u "${RUN_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${RUN_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${RUN_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

mkdir -p "${APP_DIR}/data"
chown -R "${RUN_USER}:${RUN_USER}" "${APP_DIR}"

echo "==> Ecriture du fichier .env..."
ENV_FILE="${APP_DIR}/.env"
{
  echo "DISCORD_TOKEN=${DISCORD_TOKEN}"
  if [[ -n "${GUILD_ID}" ]]; then
    echo "GUILD_ID=${GUILD_ID}"
  fi
  echo "PLAYERS_DB_PATH=${APP_DIR}/data/players.db"
} > "${ENV_FILE}"
chown "${RUN_USER}:${RUN_USER}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

echo "==> Creation service systemd..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Bot Discord 19enplein
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bot19.service
systemctl restart bot19.service

echo "==> Installation terminee."
echo "Etat:  systemctl status bot19 --no-pager"
echo "Logs:  journalctl -u bot19 -f"
