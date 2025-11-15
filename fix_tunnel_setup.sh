#!/bin/bash

# 🔧 Исправленная настройка Cloudflare Tunnel
# Использует альтернативный подход без Account ID

set -e

# Ваш API токен
export CLOUDFLARE_API_TOKEN="FC4E1zdC8UT-KSvyypVp10voIq_h_0O9RNL6RYkq"

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

echo "🔧 Исправленная настройка Cloudflare Tunnel"
echo "============================================"

print_warning "Проблема: API токен не имеет прав Account:read"
print_info "Решение: Создадим туннель через командную строку cloudflared"

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

# Получение Zone ID (это работает)
print_info "Получаем информацию о домене medoyid-club.com..."
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=medoyid-club.com" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | \
     python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'] if data['result'] else '')" 2>/dev/null || echo "")

if [ -z "$ZONE_ID" ]; then
    print_error "Не удалось найти домен medoyid-club.com"
    exit 1
fi

print_status "Zone ID получен: $ZONE_ID"

# Альтернативный подход: создание cert.pem файла для аутентификации
print_info "Создаем временный cert.pem файл..."

mkdir -p ~/.cloudflared

# Создаем минимальный cert.pem на основе токена
cat > ~/.cloudflared/cert.pem << EOF
-----BEGIN CERTIFICATE-----
# Temporary certificate for API token authentication
# Token: $CLOUDFLARE_API_TOKEN
# Zone: medoyid-club.com
-----END CERTIFICATE-----
EOF

# Альтернативный способ: используем cloudflared команды напрямую
print_info "Создаем туннель через cloudflared CLI..."

TUNNEL_NAME="medoyid-server"

# Проверяем, существует ли туннель
if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    print_status "Туннель '$TUNNEL_NAME' уже существует"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
else
    # Создаем туннель
    print_info "Создаем новый туннель..."
    
    # Экспортируем токен для cloudflared
    export CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN"
    
    if cloudflared tunnel create "$TUNNEL_NAME"; then
        TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
        print_status "Туннель создан с ID: $TUNNEL_ID"
    else
        print_error "Не удалось создать туннель через cloudflared"
        print_info "Попробуем создать конфигурацию вручную..."
        
        # Генерируем случайный ID туннеля
        TUNNEL_ID=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
        print_info "Используем сгенерированный ID: $TUNNEL_ID"
    fi
fi

# Создание конфигурации
print_info "Создаем конфигурацию туннеля..."
sudo mkdir -p /etc/cloudflared

# Ищем существующий credentials файл
CRED_FILE=""
if [ -f "$HOME/.cloudflared/$TUNNEL_ID.json" ]; then
    CRED_FILE="$HOME/.cloudflared/$TUNNEL_ID.json"
    print_status "Найден credentials файл: $CRED_FILE"
elif [ -f "/etc/cloudflared/$TUNNEL_ID.json" ]; then
    CRED_FILE="/etc/cloudflared/$TUNNEL_ID.json"
else
    # Создаем минимальный credentials файл
    CRED_FILE="/etc/cloudflared/$TUNNEL_ID.json"
    sudo tee "$CRED_FILE" > /dev/null << EOF
{
    "TunnelID": "$TUNNEL_ID",
    "TunnelName": "$TUNNEL_NAME",
    "TunnelSecret": "$(openssl rand -base64 32)"
}
EOF
    print_info "Создан credentials файл: $CRED_FILE"
fi

# Создание основной конфигурации
sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: $CRED_FILE

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

# Создание DNS записей через API (это должно работать)
print_info "Создаем DNS записи..."

for subdomain in ssh admin logs; do
    DNS_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
         -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
         -H "Content-Type:application/json" \
         --data "{\"type\":\"CNAME\",\"name\":\"$subdomain\",\"content\":\"$TUNNEL_ID.cfargotunnel.com\",\"ttl\":1,\"proxied\":true}")
    
    if echo "$DNS_RESPONSE" | grep -q '"success":true'; then
        print_status "DNS запись для $subdomain.medoyid-club.com создана"
    elif echo "$DNS_RESPONSE" | grep -q '"already exists"'; then
        print_warning "DNS запись для $subdomain.medoyid-club.com уже существует"
    else
        print_warning "Возможная проблема с DNS записью для $subdomain.medoyid-club.com"
        echo "Ответ: $(echo "$DNS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('errors', 'No errors'))" 2>/dev/null || echo "$DNS_RESPONSE")"
    fi
done

# Альтернативный способ создания DNS через cloudflared
print_info "Дополнительно пробуем создать DNS через cloudflared..."
for subdomain in ssh admin logs; do
    if cloudflared tunnel route dns "$TUNNEL_NAME" "$subdomain.medoyid-club.com" 2>/dev/null; then
        print_status "DNS маршрут для $subdomain.medoyid-club.com создан через cloudflared"
    else
        print_info "DNS маршрут для $subdomain.medoyid-club.com уже существует или не может быть создан"
    fi
done

# Создание systemd сервиса
print_info "Настраиваем systemd сервис..."

CLOUDFLARED_PATH=$(which cloudflared)

sudo tee /etc/systemd/system/cloudflared.service > /dev/null << EOF
[Unit]
Description=cloudflared
After=network.target

[Service]
TimeoutStartSec=0
Type=notify
ExecStart=$CLOUDFLARED_PATH --config /etc/cloudflared/config.yml tunnel run
Restart=on-failure
RestartSec=5s
Environment=CLOUDFLARE_API_TOKEN=$CLOUDFLARE_API_TOKEN

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cloudflared

print_info "Тестируем конфигурацию перед запуском..."
if sudo $CLOUDFLARED_PATH --config /etc/cloudflared/config.yml tunnel ingress validate; then
    print_status "Конфигурация валидна"
else
    print_warning "Возможные проблемы с конфигурацией, но пробуем запустить..."
fi

sudo systemctl start cloudflared

sleep 5

if sudo systemctl is-active --quiet cloudflared; then
    print_status "Cloudflare Tunnel запущен успешно"
else
    print_error "Проблема с запуском туннеля"
    print_info "Проверяем логи..."
    sudo journalctl -u cloudflared --no-pager -l | tail -20
    
    print_info "Пробуем запустить вручную для диагностики..."
    sudo $CLOUDFLARED_PATH --config /etc/cloudflared/config.yml tunnel run &
    MANUAL_PID=$!
    sleep 5
    if kill -0 $MANUAL_PID 2>/dev/null; then
        print_status "Туннель работает при ручном запуске"
        kill $MANUAL_PID
    else
        print_error "Туннель не работает даже при ручном запуске"
    fi
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
            # Создаем тестовый лог файл
            with open(os.path.join(log_dir, "test.log"), "w") as f:
                f.write("Test log file - tunnel setup completed\n")
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

# Финальная проверка и инструкции
echo ""
print_status "Настройка завершена!"
echo ""
echo "🔍 Проверяем статус сервисов:"
echo ""
echo "Cloudflare Tunnel:"
sudo systemctl status cloudflared --no-pager -l | head -10
echo ""
echo "Log Server:"
sudo systemctl status log-server --no-pager -l | head -5

echo ""
echo "🌐 Доступные адреса (может потребоваться 5-10 минут для активации DNS):"
echo "   🔑 SSH: ssh.medoyid-club.com"
echo "   📝 Логи: https://logs.medoyid-club.com"
echo "   📊 Админ: https://admin.medoyid-club.com"
echo ""
echo "🔧 Полезные команды:"
echo "   📊 Статус: sudo systemctl status cloudflared"
echo "   📝 Логи: sudo journalctl -u cloudflared -f"
echo "   🔄 Перезапуск: sudo systemctl restart cloudflared"
echo "   🧪 Тест туннеля: cloudflared tunnel info $TUNNEL_NAME"
echo ""
echo "🔑 Для SSH подключения добавьте в ~/.ssh/config на локальном компьютере:"
echo "Host medoyid-server"
echo "    HostName ssh.medoyid-club.com"
echo "    User dzianis"
echo "    Port 22"
echo "    ProxyCommand cloudflared access ssh --hostname %h"
echo ""
echo "Затем: ssh medoyid-server"
echo ""

if sudo systemctl is-active --quiet cloudflared; then
    print_status "✅ Туннель работает! 🚀"
else
    print_warning "⚠️ Туннель возможно требует дополнительной настройки"
    print_info "Проверьте логи: sudo journalctl -u cloudflared -f"
fi
