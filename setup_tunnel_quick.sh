#!/bin/bash

# 🚀 Быстрая настройка Cloudflare Tunnel с готовым токеном
# Для сервера medoyid-club.com

set -e

# Ваш API токен
export CLOUDFLARE_API_TOKEN="30DKp4DnDjH-ezYvQEP3YzGHT8bH21EgrT6BcI7H"

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

echo "🌐 Быстрая настройка Cloudflare Tunnel"
echo "======================================"

# Проверка токена
print_info "Проверяем API токен..."
if curl -s -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | grep -q '"status":"active"'; then
    print_status "API токен действителен"
else
    print_error "API токен недействителен!"
    exit 1
fi

# Установка cloudflared
print_info "Установка cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    print_status "cloudflared установлен"
else
    print_status "cloudflared уже установлен ($(cloudflared --version))"
fi

# Получение Zone ID
print_info "Получаем информацию о домене medoyid-club.com..."
ZONE_RESPONSE=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=medoyid-club.com" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json")

ZONE_ID=$(echo "$ZONE_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')" 2>/dev/null || echo "")

if [ -z "$ZONE_ID" ]; then
    print_error "Не удалось найти домен medoyid-club.com в вашем аккаунте"
    echo "Ответ API: $ZONE_RESPONSE"
    exit 1
fi

print_status "Zone ID получен: $ZONE_ID"

# Получение Account ID
ACCOUNT_RESPONSE=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json")

ACCOUNT_ID=$(echo "$ACCOUNT_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')" 2>/dev/null || echo "")

if [ -z "$ACCOUNT_ID" ]; then
    print_error "Не удалось получить Account ID"
    echo "Ответ API: $ACCOUNT_RESPONSE"
    exit 1
fi

print_status "Account ID получен: $ACCOUNT_ID"

# Создание туннеля
TUNNEL_NAME="medoyid-server"
print_info "Создаем туннель $TUNNEL_NAME..."

# Генерируем случайный секрет для туннеля
TUNNEL_SECRET=$(openssl rand -base64 32)

TUNNEL_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" \
     --data "{\"name\":\"$TUNNEL_NAME\",\"tunnel_secret\":\"$TUNNEL_SECRET\"}")

# Проверяем успешность создания туннеля
if echo "$TUNNEL_RESPONSE" | grep -q '"success":true'; then
    TUNNEL_ID=$(echo "$TUNNEL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result']['id'])")
    print_status "Туннель создан с ID: $TUNNEL_ID"
elif echo "$TUNNEL_RESPONSE" | grep -q '"already exists"'; then
    print_warning "Туннель уже существует, получаем его данные..."
    
    # Получаем существующий туннель
    EXISTING_TUNNEL=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel?name=$TUNNEL_NAME" \
         -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
         -H "Content-Type:application/json")
    
    TUNNEL_ID=$(echo "$EXISTING_TUNNEL" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')")
    
    if [ -z "$TUNNEL_ID" ]; then
        print_error "Не удалось получить ID существующего туннеля"
        exit 1
    fi
    
    print_status "Используем существующий туннель: $TUNNEL_ID"
else
    print_error "Не удалось создать туннель"
    echo "Ответ API: $TUNNEL_RESPONSE"
    exit 1
fi

# Создание директорий
sudo mkdir -p /etc/cloudflared
mkdir -p ~/.cloudflared

# Создание credentials файла
print_info "Создаем credentials файл..."
sudo tee /etc/cloudflared/$TUNNEL_ID.json > /dev/null << EOF
{
    "AccountTag": "$ACCOUNT_ID",
    "TunnelID": "$TUNNEL_ID",
    "TunnelName": "$TUNNEL_NAME",
    "TunnelSecret": "$TUNNEL_SECRET"
}
EOF

# Создание конфигурационного файла
print_info "Создаем конфигурацию туннеля..."
sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json

ingress:
  # SSH доступ
  - hostname: ssh.medoyid-club.com
    service: ssh://localhost:22
  
  # Веб-интерфейс для мониторинга
  - hostname: admin.medoyid-club.com  
    service: http://localhost:8080
  
  # Просмотр логов бота
  - hostname: logs.medoyid-club.com
    service: http://localhost:8081
  
  # Fallback для всех остальных запросов
  - service: http_status:404
EOF

print_status "Конфигурация создана"

# Создание DNS записей
print_info "Создаем DNS записи..."

for subdomain in ssh admin logs; do
    DNS_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
         -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
         -H "Content-Type:application/json" \
         --data "{\"type\":\"CNAME\",\"name\":\"$subdomain\",\"content\":\"$TUNNEL_ID.cfargotunnel.com\",\"ttl\":1}")
    
    if echo "$DNS_RESPONSE" | grep -q '"success":true'; then
        print_status "DNS запись для $subdomain.medoyid-club.com создана"
    elif echo "$DNS_RESPONSE" | grep -q '"already exists"'; then
        print_warning "DNS запись для $subdomain.medoyid-club.com уже существует"
    else
        print_warning "Возможная проблема с DNS записью для $subdomain.medoyid-club.com"
    fi
done

# Создание systemd сервиса
print_info "Настраиваем systemd сервис..."

sudo tee /etc/systemd/system/cloudflared.service > /dev/null << EOF
[Unit]
Description=cloudflared
After=network.target

[Service]
TimeoutStartSec=0
Type=notify
ExecStart=/usr/local/bin/cloudflared --config /etc/cloudflared/config.yml tunnel run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# Проверяем где установлен cloudflared
CLOUDFLARED_PATH=$(which cloudflared)
sudo sed -i "s|/usr/local/bin/cloudflared|$CLOUDFLARED_PATH|g" /etc/systemd/system/cloudflared.service

sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

sleep 5

if sudo systemctl is-active --quiet cloudflared; then
    print_status "Cloudflare Tunnel запущен успешно"
else
    print_error "Проблема с запуском туннеля"
    print_info "Проверяем логи..."
    sudo journalctl -u cloudflared --no-pager -l
    exit 1
fi

# Создание сервера логов
print_info "Настраиваем сервер для просмотра логов..."

cat > "$HOME/log_server.py" << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os
from pathlib import Path

class LogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        log_dir = "/home/dzianis/shorts-shot/logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        super().__init__(*args, directory=log_dir, **kwargs)
    
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

PORT = 8081
print(f"🚀 Log server starting on port {PORT}")
print(f"📁 Serving logs from: /home/dzianis/shorts-shot/logs")

try:
    with socketserver.TCPServer(("", PORT), LogHandler) as httpd:
        print(f"✅ Server ready at http://localhost:{PORT}")
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\n🛑 Server stopped")
except Exception as e:
    print(f"❌ Error: {e}")
EOF

chmod +x "$HOME/log_server.py"

sudo tee /etc/systemd/system/log-server.service > /dev/null << EOF
[Unit]
Description=Log Server for Telegram Bot
After=network.target

[Service]
Type=simple
User=dzianis
WorkingDirectory=/home/dzianis
ExecStart=/usr/bin/python3 /home/dzianis/log_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable log-server
sudo systemctl start log-server

if sudo systemctl is-active --quiet log-server; then
    print_status "Сервер логов запущен на порту 8081"
else
    print_warning "Проблема с запуском сервера логов (не критично)"
fi

# Финальная проверка
print_info "Проверяем статус сервисов..."
echo ""
echo "🔍 Статус Cloudflare Tunnel:"
sudo systemctl status cloudflared --no-pager -l
echo ""
echo "🔍 Статус сервера логов:"
sudo systemctl status log-server --no-pager -l

print_status "Настройка завершена!"
echo ""
echo "🎉 Cloudflare Tunnel настроен для medoyid-club.com!"
echo ""
echo "📋 Доступные адреса:"
echo "   🔑 SSH: ssh.medoyid-club.com"
echo "   📝 Логи: https://logs.medoyid-club.com"
echo "   📊 Админ: https://admin.medoyid-club.com (когда настроите)"
echo ""
echo "🔧 Полезные команды:"
echo "   📊 Статус туннеля: sudo systemctl status cloudflared"
echo "   📝 Логи туннеля: sudo journalctl -u cloudflared -f"
echo "   🔄 Перезапуск: sudo systemctl restart cloudflared"
echo ""
echo "🔑 Для SSH с локального компьютера добавьте в ~/.ssh/config:"
echo "Host medoyid-server"
echo "    HostName ssh.medoyid-club.com"
echo "    User dzianis"
echo "    Port 22"
echo "    ProxyCommand cloudflared access ssh --hostname %h"
echo ""
echo "Затем: ssh medoyid-server"
echo ""
print_status "Готово! 🚀"
