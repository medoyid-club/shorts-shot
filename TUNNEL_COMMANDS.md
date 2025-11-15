# 🚀 Команды для настройки Cloudflare Tunnel

Выполните эти команды **на вашем Ubuntu сервере** для настройки туннеля с доменом `medoyid-club.com`.

## ⚡ Быстрая установка (автоматически)

```bash
# 1. Скачайте скрипт настройки (с вашим токеном уже внутри)
curl -O https://raw.githubusercontent.com/your-repo/setup_tunnel_quick.sh

# Или если файл локально:
chmod +x setup_tunnel_quick.sh
./setup_tunnel_quick.sh
```

## 🔧 Ручная установка (пошагово)

### Шаг 1: Установка cloudflared
```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
cloudflared --version
```

### Шаг 2: Экспорт API токена
```bash
export CLOUDFLARE_API_TOKEN="FC4E1zdC8UT-KSvyypVp10voIq_h_0O9RNL6RYkq"

# Проверим токен
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json"
```

### Шаг 3: Получение Zone ID
```bash
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=medoyid-club.com" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | \
     python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'])")

echo "Zone ID: $ZONE_ID"
```

### Шаг 4: Получение Account ID
```bash
ACCOUNT_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" | \
     python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result'][0]['id'])")

echo "Account ID: $ACCOUNT_ID"
```

### Шаг 5: Создание туннеля
```bash
TUNNEL_NAME="medoyid-server"
TUNNEL_SECRET=$(openssl rand -base64 32)

TUNNEL_RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
     -H "Content-Type:application/json" \
     --data "{\"name\":\"$TUNNEL_NAME\",\"tunnel_secret\":\"$TUNNEL_SECRET\"}")

TUNNEL_ID=$(echo "$TUNNEL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['result']['id'])")

echo "Tunnel ID: $TUNNEL_ID"
```

### Шаг 6: Создание конфигурации
```bash
sudo mkdir -p /etc/cloudflared

# Credentials файл
sudo tee /etc/cloudflared/$TUNNEL_ID.json > /dev/null << EOF
{
    "AccountTag": "$ACCOUNT_ID",
    "TunnelID": "$TUNNEL_ID", 
    "TunnelName": "$TUNNEL_NAME",
    "TunnelSecret": "$TUNNEL_SECRET"
}
EOF

# Конфигурационный файл
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
```

### Шаг 7: DNS записи
```bash
# Создаем DNS записи для поддоменов
for subdomain in ssh admin logs; do
    curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
         -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
         -H "Content-Type:application/json" \
         --data "{\"type\":\"CNAME\",\"name\":\"$subdomain\",\"content\":\"$TUNNEL_ID.cfargotunnel.com\",\"ttl\":1}"
    echo "DNS для $subdomain.medoyid-club.com создан"
done
```

### Шаг 8: Systemd сервис
```bash
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << EOF
[Unit]
Description=cloudflared
After=network.target

[Service]
TimeoutStartSec=0
Type=notify
ExecStart=$(which cloudflared) --config /etc/cloudflared/config.yml tunnel run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### Шаг 9: Проверка
```bash
# Статус сервиса
sudo systemctl status cloudflared

# Логи
sudo journalctl -u cloudflared -f
```

### Шаг 10: Сервер логов (опционально)
```bash
# Создаем простой HTTP сервер для логов бота
cat > ~/log_server.py << 'EOF'
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

chmod +x ~/log_server.py

# Создаем сервис
sudo tee /etc/systemd/system/log-server.service > /dev/null << EOF
[Unit]
Description=Log Server
After=network.target

[Service]
Type=simple
User=dzianis
ExecStart=/usr/bin/python3 /home/dzianis/log_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable log-server
sudo systemctl start log-server
```

## ✅ Проверка работы

После выполнения команд проверьте:

```bash
# Статус сервисов
sudo systemctl status cloudflared
sudo systemctl status log-server

# Проверка DNS (может потребоваться время на распространение)
dig ssh.medoyid-club.com
dig logs.medoyid-club.com

# Логи туннеля
sudo journalctl -u cloudflared -f
```

## 🌐 Результат

После настройки будут доступны:

- **SSH**: `ssh.medoyid-club.com`
- **Логи бота**: `https://logs.medoyid-club.com`
- **Админ панель**: `https://admin.medoyid-club.com`

## 🔑 SSH подключение с локального компьютера

1. **Установите cloudflared на локальный компьютер**
2. **Добавьте в ~/.ssh/config:**
   ```
   Host medoyid-server
       HostName ssh.medoyid-club.com
       User dzianis
       Port 22
       ProxyCommand cloudflared access ssh --hostname %h
   ```
3. **Подключайтесь:** `ssh medoyid-server`

## 🚨 Решение проблем

- **Туннель не запускается**: `sudo journalctl -u cloudflared -f`
- **DNS не работает**: Подождите 5-10 минут для распространения
- **Нет доступа**: Проверьте что порт 22 открыт на сервере

Готово! 🚀
