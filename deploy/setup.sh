#!/bin/bash
set -e

echo "========================================"
echo "  BaseLinker Monitor – instalacja VPS"
echo "========================================"

apt update && apt upgrade -y
apt install -y python3-pip python3-venv git nginx

# Klonowanie repozytorium
git clone https://github.com/Najdeq/baselinker-monitor.git /opt/baselinker-monitor
cd /opt/baselinker-monitor

# Środowisko Python
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Systemd service
cp deploy/baselinker-monitor.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable baselinker-monitor

# Nginx – proxy port 80 -> 5000
cat > /etc/nginx/sites-available/baselinker-monitor << 'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/baselinker-monitor /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "✅ Instalacja zakończona!"
echo ""
echo "Teraz utwórz plik z kluczami API:"
echo "  nano /opt/baselinker-monitor/.env"
echo ""
echo "Wklej i uzupełnij:"
echo "  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
echo "  EXPORT_URL=https://..."
echo "  OWELL_EXPORT_URL=https://..."
echo ""
echo "Następnie uruchom serwis:"
echo "  systemctl start baselinker-monitor"
echo "  systemctl status baselinker-monitor"
