#!/usr/bin/env bash
set -e

APP_DIR="/home/ribo/day-trader-dashboard"
cd "$APP_DIR"

echo "=== [1/3] Verifica Python 3 sul Raspberry Pi ==="
python3 --version

echo "=== [2/3] Verifica Cloudflared per il Tunnel ==="
CLOUDFLARED_BIN=$(command -v cloudflared || echo "/usr/local/bin/cloudflared")
if [ ! -x "$CLOUDFLARED_BIN" ]; then
  echo "Installazione cloudflared per ARM64/ARMhf..."
  ARCH=$(uname -m)
  if [ "$ARCH" = "aarch64" ]; then
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
  else
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
  fi
  sudo curl -fsSL "$CF_URL" -o /usr/local/bin/cloudflared
  sudo chmod +x /usr/local/bin/cloudflared
  CLOUDFLARED_BIN="/usr/local/bin/cloudflared"
fi

echo "=== [3/3] Creazione servizi systemd (daytrader + daytrader-tunnel) ==="
sudo tee /etc/systemd/system/daytrader.service >/dev/null <<EOF
[Unit]
Description=Day Trader AI Web Dashboard (Port 8080)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ribo
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/daytrader-bot.service >/dev/null <<EOF
[Unit]
Description=Day Trader Telegram Bot Service
After=network-online.target daytrader.service
Wants=network-online.target

[Service]
Type=simple
User=ribo
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/telegram_bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/daytrader-tunnel.service >/dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel for Day Trader Dashboard (port 8080)
After=network-online.target daytrader.service
Wants=network-online.target

[Service]
Type=simple
User=ribo
WorkingDirectory=$APP_DIR
ExecStart=/bin/sh -c '$CLOUDFLARED_BIN tunnel --no-autoupdate --url http://127.0.0.1:8080 > $APP_DIR/cloudflared.log 2>&1'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable daytrader.service daytrader-bot.service daytrader-tunnel.service
sudo systemctl restart daytrader.service
sudo systemctl restart daytrader-bot.service
sudo systemctl restart daytrader-tunnel.service

echo "Attesa generazione link pubblico Cloudflare (8s)..."
for i in $(seq 1 12); do
  sleep 1
  TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$APP_DIR/cloudflared.log" 2>/dev/null | tail -n 1 || true)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
done

echo ""
echo "=================================================================="
echo "✅ DAY TRADER DASHBOARD ATTIVA SUL RASPBERRY PI!"
echo "🏠 Rete Locale : http://192.168.1.130:8080"
echo "🌐 Link Remoto : ${TUNNEL_URL:-Generazione in corso in $APP_DIR/cloudflared.log}"
echo "=================================================================="
