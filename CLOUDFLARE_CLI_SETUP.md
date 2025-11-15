# 🖥️ Настройка Cloudflare Tunnel через CLI

Инструкция для Ubuntu сервера **БЕЗ графического интерфейса** (только командная строка).

## 🎯 Быстрый старт

```bash
# 1. Скопируйте и запустите скрипт
chmod +x setup_cloudflare_tunnel.sh
./setup_cloudflare_tunnel.sh
```

## 🔑 Аутентификация без браузера

### Вариант 1: С локального компьютера (РЕКОМЕНДУЕТСЯ)

На вашем **локальном компьютере** (Windows/Mac):

1. **Установите cloudflared:**
   ```bash
   # Windows (PowerShell as Admin)
   winget install --id Cloudflare.cloudflared
   
   # macOS
   brew install cloudflared
   
   # Linux
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```

2. **Аутентификация:**
   ```bash
   cloudflared tunnel login
   ```
   
3. **Скопируйте сертификат на сервер:**
   ```bash
   # Найдите файл cert.pem (обычно в ~/.cloudflared/)
   # Windows: %USERPROFILE%\.cloudflared\cert.pem
   # Linux/Mac: ~/.cloudflared/cert.pem
   
   # Скопируйте на сервер
   scp ~/.cloudflared/cert.pem dzianis@your-server-ip:~/.cloudflared/
   ```

### Вариант 2: Через API Token

1. **Получите API Token:**
   - Перейдите: https://dash.cloudflare.com/profile/api-tokens
   - Нажмите "Create Token" → "Custom token"
   - **Permissions:**
     - `Zone:Zone:Read`
     - `Zone:DNS:Edit`  
     - `Account:Cloudflare Tunnel:Edit`
   - **Zone Resources:** `Include - Specific zone - medoyid-club.com`

2. **Используйте токен на сервере:**
   ```bash
   export CLOUDFLARE_API_TOKEN=your_token_here
   
   # Проверьте токен
   curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        -H "Content-Type:application/json"
   ```

### Вариант 3: Ручное создание туннеля

Если у вас есть доступ к Cloudflare Dashboard:

1. **В Cloudflare Dashboard:**
   - Перейдите в `Zero Trust` → `Networks` → `Tunnels`
   - Создайте новый туннель `medoyid-server`
   - Скопируйте команду установки

2. **На сервере выполните:**
   ```bash
   # Команда будет примерно такой:
   cloudflared service install eyJhIjoiX...XYZ
   ```

## 🚀 Полная установка через CLI

```bash
#!/bin/bash

# 1. Установка cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# 2. Создание директории
mkdir -p ~/.cloudflared

# 3. Размещение cert.pem (если скопировали с другого компьютера)
# Файл должен быть в ~/.cloudflared/cert.pem

# 4. Создание туннеля
cloudflared tunnel create medoyid-server

# 5. Получение ID туннеля
TUNNEL_ID=$(cloudflared tunnel list | grep medoyid-server | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# 6. Создание конфигурации
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: /home/dzianis/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: ssh.medoyid-club.com
    service: ssh://localhost:22
  - hostname: admin.medoyid-club.com  
    service: http://localhost:8080
  - hostname: logs.medoyid-club.com
    service: http://localhost:8081
  - service: http_status:404
EOF

# 7. Создание DNS записей
cloudflared tunnel route dns medoyid-server ssh.medoyid-club.com
cloudflared tunnel route dns medoyid-server admin.medoyid-club.com  
cloudflared tunnel route dns medoyid-server logs.medoyid-club.com

# 8. Установка как сервис
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 9. Проверка
sudo systemctl status cloudflared
```

## 📊 Создание веб-сервера для логов

```bash
# Создание простого сервера логов
cat > ~/log_server.py << 'EOF'
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
        super().end_headers()

PORT = 8081
with socketserver.TCPServer(("", PORT), LogHandler) as httpd:
    print(f"Log server running on port {PORT}")
    httpd.serve_forever()
EOF

chmod +x ~/log_server.py

# Создание systemd сервиса
sudo tee /etc/systemd/system/log-server.service > /dev/null << 'EOF'
[Unit]
Description=Log Server for Bot
After=network.target

[Service]
Type=simple
User=dzianis
WorkingDirectory=/home/dzianis
ExecStart=/usr/bin/python3 /home/dzianis/log_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable log-server
sudo systemctl start log-server
```

## ✅ Проверка работы

```bash
# Статус туннеля
sudo systemctl status cloudflared

# Логи туннеля
sudo journalctl -u cloudflared -f

# Список туннелей
cloudflared tunnel list

# Информация о туннеле
cloudflared tunnel info medoyid-server

# Проверка DNS записей
dig ssh.medoyid-club.com
```

## 🔧 Подключение с локального компьютера

1. **Установите cloudflared на локальный компьютер**
2. **Добавьте в ~/.ssh/config:**
   ```
   Host medoyid-server
       HostName ssh.medoyid-club.com
       User dzianis
       Port 22
       ProxyCommand cloudflared access ssh --hostname %h
   ```
3. **Подключайтесь:**
   ```bash
   ssh medoyid-server
   ```

## 🌐 Доступные адреса после настройки

- **SSH:** `ssh.medoyid-club.com`
- **Логи бота:** `https://logs.medoyid-club.com`
- **Админка:** `https://admin.medoyid-club.com` (когда настроите)

## 🚨 Устранение проблем

1. **Ошибка аутентификации:**
   ```bash
   ls -la ~/.cloudflared/
   # Должен быть файл cert.pem
   ```

2. **Туннель не запускается:**
   ```bash
   sudo journalctl -u cloudflared -f
   # Проверить ошибки в логах
   ```

3. **DNS не резолвится:**
   ```bash
   cloudflared tunnel list
   # Проверить что туннель активен
   ```

4. **Проверка конфигурации:**
   ```bash
   sudo cat /etc/cloudflared/config.yml
   cloudflared tunnel ingress validate
   ```

Готово! Теперь у вас есть безопасный доступ к серверу через CLI. 🚀
