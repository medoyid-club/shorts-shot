#!/bin/bash

# 🌐 Автоматическая настройка Cloudflare Tunnel
# Для Ubuntu сервера с доменом medoyid-club.com

set -e

echo "🌐 Настройка Cloudflare Tunnel для medoyid-club.com"
echo "=================================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Проверка прав sudo
if [[ $EUID -eq 0 ]]; then
   print_error "Не запускайте этот скрипт от root! Используйте обычного пользователя с sudo."
   exit 1
fi

# Проверка доступности sudo
if ! sudo -v; then
    print_error "Необходимы права sudo для установки"
    exit 1
fi

print_info "Шаг 1: Установка cloudflared"

# Проверяем, установлен ли cloudflared
if command -v cloudflared &> /dev/null; then
    print_status "cloudflared уже установлен ($(cloudflared --version))"
else
    print_info "Загружаем и устанавливаем cloudflared..."
    
    # Загружаем последнюю версию
    curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    
    # Устанавливаем
    sudo dpkg -i /tmp/cloudflared.deb
    
    # Очищаем временный файл
    rm /tmp/cloudflared.deb
    
    print_status "cloudflared установлен успешно"
fi

print_info "Шаг 2: Аутентификация с Cloudflare"

# Проверяем, есть ли уже сертификаты
if [ -f "$HOME/.cloudflared/cert.pem" ]; then
    print_status "Аутентификация уже выполнена"
else
    print_warning "На сервере без GUI необходимо выполнить аутентификацию вручную"
    print_info "Вариант 1: С другого компьютера с браузером:"
    echo "   1. Выполните на компьютере с браузером: cloudflared tunnel login"
    echo "   2. Выберите домен medoyid-club.com"
    echo "   3. Скопируйте файл ~/.cloudflared/cert.pem на этот сервер"
    echo ""
    print_info "Вариант 2: Через API токен Cloudflare:"
    echo "   1. Получите API Token в Cloudflare Dashboard:"
    echo "      https://dash.cloudflare.com/profile/api-tokens"
    echo "   2. Создайте Custom token с правами:"
    echo "      - Zone:Zone:Read"
    echo "      - Zone:DNS:Edit" 
    echo "      - Account:Cloudflare Tunnel:Edit"
    echo "   3. Экспортируйте токен: export CLOUDFLARE_API_TOKEN=your_token_here"
    echo ""
    print_info "Вариант 3: Скопировать cert.pem файл:"
    
    read -p "У вас уже есть cert.pem файл? (y/n): " HAS_CERT
    
    if [[ $HAS_CERT =~ ^[Yy]$ ]]; then
        echo ""
        print_info "Поместите файл cert.pem в $HOME/.cloudflared/cert.pem"
        echo "Например: scp user@other-computer:~/.cloudflared/cert.pem ~/.cloudflared/"
        echo ""
        read -p "Файл cert.pem размещен? Нажмите Enter для продолжения..."
        
        if [ -f "$HOME/.cloudflared/cert.pem" ]; then
            print_status "Файл cert.pem найден"
        else
            print_error "Файл cert.pem не найден в $HOME/.cloudflared/cert.pem"
            exit 1
        fi
    else
        print_error "Необходим файл cert.pem для продолжения"
        print_info "Получите его любым из способов выше и запустите скрипт снова"
        exit 1
    fi
fi

print_info "Шаг 3: Создание туннеля"

TUNNEL_NAME="medoyid-server"

# Проверяем, существует ли туннель
if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
    print_status "Туннель '$TUNNEL_NAME' уже существует"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
else
    print_info "Создаем новый туннель '$TUNNEL_NAME'..."
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
    print_status "Туннель создан с ID: $TUNNEL_ID"
fi

print_info "Шаг 4: Создание конфигурации"

# Создаем директорию для конфигурации
sudo mkdir -p /etc/cloudflared

# Находим путь к credentials файлу
CREDENTIALS_FILE="$HOME/.cloudflared/$TUNNEL_ID.json"

if [ ! -f "$CREDENTIALS_FILE" ]; then
    print_error "Файл credentials не найден: $CREDENTIALS_FILE"
    exit 1
fi

# Создаем конфигурационный файл
sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

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

print_status "Конфигурация создана в /etc/cloudflared/config.yml"

print_info "Шаг 5: Создание DNS записей"

# Создаем DNS записи
print_info "Создаем DNS записи в Cloudflare..."

for subdomain in ssh admin logs; do
    if cloudflared tunnel route dns "$TUNNEL_NAME" "$subdomain.medoyid-club.com"; then
        print_status "DNS запись для $subdomain.medoyid-club.com создана"
    else
        print_warning "Возможно DNS запись для $subdomain.medoyid-club.com уже существует"
    fi
done

print_info "Шаг 6: Настройка systemd сервиса"

# Устанавливаем сервис
if sudo cloudflared service install; then
    print_status "Systemd сервис установлен"
else
    print_warning "Сервис возможно уже установлен"
fi

# Запускаем и включаем автозапуск
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Проверяем статус
sleep 3
if sudo systemctl is-active --quiet cloudflared; then
    print_status "Cloudflare Tunnel запущен и работает"
else
    print_error "Проблема с запуском сервиса"
    print_info "Проверьте логи: sudo journalctl -u cloudflared -f"
    exit 1
fi

print_info "Шаг 7: Создание сервера для просмотра логов"

# Создаем простой HTTP сервер для логов
cat > "$HOME/log_server.py" << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os
from pathlib import Path

class LogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/home/dzianis/shorts-shot/logs", **kwargs)
    
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

# Создаем systemd сервис для сервера логов
sudo tee /etc/systemd/system/log-server.service > /dev/null << EOF
[Unit]
Description=Log Server for Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME
ExecStart=/usr/bin/python3 $HOME/log_server.py
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
    print_warning "Проблема с запуском сервера логов"
fi

print_info "Настройка завершена!"
echo ""
echo "🎉 Cloudflare Tunnel настроен успешно!"
echo ""
echo "📋 Доступные адреса:"
echo "   🔑 SSH: ssh.medoyid-club.com (порт 22)"
echo "   📊 Админ: admin.medoyid-club.com (порт 8080)"  
echo "   📝 Логи: logs.medoyid-club.com"
echo ""
echo "🔧 Полезные команды:"
echo "   📊 Статус туннеля: sudo systemctl status cloudflared"
echo "   📝 Логи туннеля: sudo journalctl -u cloudflared -f"
echo "   🔄 Перезапуск: sudo systemctl restart cloudflared"
echo ""
echo "📚 Полная документация: CLOUDFLARE_TUNNEL_SETUP.md"
echo ""

# Дополнительная информация для SSH клиента
print_info "Настройка SSH клиента"
echo ""
echo "Для подключения с локального компьютера, добавьте в ~/.ssh/config:"
echo ""
echo "Host medoyid-server"
echo "    HostName ssh.medoyid-club.com"
echo "    User $USER"
echo "    Port 22"
echo "    ProxyCommand cloudflared access ssh --hostname %h"
echo ""
echo "Затем подключайтесь: ssh medoyid-server"
echo ""

print_status "Готово! 🚀"
