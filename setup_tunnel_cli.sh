#!/bin/bash

# 🌐 Упрощенная настройка Cloudflare Tunnel для CLI сервера
# Использует API токен вместо браузерной аутентификации

set -e

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

echo "🌐 Настройка Cloudflare Tunnel (CLI версия)"
echo "============================================"

# Проверка API токена
if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    print_error "Необходим API токен Cloudflare!"
    echo ""
    print_info "Получите токен:"
    echo "1. Откройте: https://dash.cloudflare.com/profile/api-tokens"
    echo "2. Create Token → Custom token"
    echo "3. Права: Zone:Zone:Read, Zone:DNS:Edit, Account:Cloudflare Tunnel:Edit"
    echo "4. Zone: medoyid-club.com"
    echo ""
    echo "Затем экспортируйте:"
    echo "export CLOUDFLARE_API_TOKEN=your_token_here"
    echo ""
    read -p "Введите ваш API токен: " API_TOKEN
    export CLOUDFLARE_API_TOKEN="$API_TOKEN"
fi

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
    print_status "cloudflared уже установлен"
fi

# Получение Zone ID для домена
print_info "Получаем информацию о домене medoyid-club.com..."
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=medoyid-club.com" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | \
     python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')")

if [ -z "$ZONE_ID" ]; then
    print_error "Не удалось найти домен medoyid-club.com"
    exit 1
fi

print_status "Zone ID получен: $ZONE_ID"

# Создание туннеля через API
TUNNEL_NAME="medoyid-server"
print_info "Создаем туннель $TUNNEL_NAME..."

# Получение Account ID
ACCOUNT_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | \
     python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')")

if [ -z "$ACCOUNT_ID" ]; then
    print_error "Не удалось получить Account ID"
    exit 1
fi

# Создание туннеля
TUNNEL_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" \
     --data "{\"name\":\"$TUNNEL_NAME\",\"tunnel_secret\":\"$(openssl rand -base64 32)\"}")

TUNNEL_ID=$(echo "$TUNNEL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result']['id'] if 'result' in data and data['result'] else '')")

if [ -z "$TUNNEL_ID" ]; then
    print_error "Не удалось создать туннель"
    echo "Ответ API: $TUNNEL_RESPONSE"
    exit 1
fi

print_status "Туннель создан с ID: $TUNNEL_ID"

# Получение токена туннеля
TUNNEL_TOKEN=$(echo "$TUNNEL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result']['token'] if 'result' in data and data['result'] else '')")

# Создание конфигурации
print_info "Создаем конфигурацию туннеля..."
sudo mkdir -p /etc/cloudflared

sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: ssh.medoyid-club.com
    service: ssh://localhost:22
  - hostname: admin.medoyid-club.com  
    service: http://localhost:8080
  - hostname: logs.medoyid-club.com
    service: http://localhost:8081
  - service: http_status:404
EOF

# Создание credentials файла
echo "$TUNNEL_RESPONSE" | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
if 'result' in data:
    result = data['result']
    cred = {
        'AccountTag': result['account_tag'],
        'TunnelID': result['id'],
        'TunnelName': result['name'],
        'TunnelSecret': result['tunnel_secret']
    }
    print(json.dumps(cred))
" | sudo tee /etc/cloudflared/$TUNNEL_ID.json > /dev/null

print_status "Конфигурация создана"

# Создание DNS записей через API
print_info "Создаем DNS записи..."

for subdomain in ssh admin logs; do
    DNS_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
         -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
         -H "Content-Type:application/json" \
         --data "{\"type\":\"CNAME\",\"name\":\"$subdomain\",\"content\":\"$TUNNEL_ID.cfargotunnel.com\",\"ttl\":1}")
    
    if echo "$DNS_RESPONSE" | grep -q '"success":true'; then
        print_status "DNS запись для $subdomain.medoyid-club.com создана"
    else
        print_warning "Возможно DNS запись для $subdomain.medoyid-club.com уже существует"
    fi
done

# Установка как сервис
print_info "Настраиваем systemd сервис..."

# Создаем сервис вручную, так как у нас нет cert.pem для cloudflared service install
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

sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

sleep 3

if sudo systemctl is-active --quiet cloudflared; then
    print_status "Cloudflare Tunnel запущен"
else
    print_error "Проблема с запуском туннеля"
    print_info "Проверьте логи: sudo journalctl -u cloudflared -f"
    exit 1
fi

# Создание сервера логов
print_info "Настраиваем сервер логов..."

cat > "$HOME/log_server.py" << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os

class LogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/home/dzianis/shorts-shot/logs", **kwargs)

PORT = 8081
with socketserver.TCPServer(("", PORT), LogHandler) as httpd:
    httpd.serve_forever()
EOF

chmod +x "$HOME/log_server.py"

sudo tee /etc/systemd/system/log-server.service > /dev/null << EOF
[Unit]
Description=Log Server
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=/usr/bin/python3 $HOME/log_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable log-server
sudo systemctl start log-server

print_status "Настройка завершена!"
echo ""
echo "🎉 Cloudflare Tunnel настроен через API!"
echo ""
echo "📋 Доступные адреса:"
echo "   🔑 SSH: ssh.medoyid-club.com"
echo "   📝 Логи: https://logs.medoyid-club.com"
echo ""
echo "🔧 Статус сервисов:"
sudo systemctl status cloudflared --no-pager -l
echo ""
sudo systemctl status log-server --no-pager -l
echo ""
print_status "Готово! 🚀"
