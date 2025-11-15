# 🌐 Настройка Cloudflare Tunnel для Ubuntu сервера

Пошаговая инструкция для настройки безопасного доступа к серверу через домен `medoyid-club.com`.

## 📋 Что вы получите

- **SSH доступ**: `ssh.medoyid-club.com` 
- **Web интерфейс**: `admin.medoyid-club.com` (для мониторинга)
- **Логи бота**: `logs.medoyid-club.com` (просмотр логов)
- **Безопасность**: Все через HTTPS, без открытых портов

## 🔧 Шаг 1: Установка cloudflared

На вашем Ubuntu сервере выполните:

```bash
# Загружаем и устанавливаем cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Проверяем установку
cloudflared --version
```

## 🔑 Шаг 2: Аутентификация

```bash
# Аутентификация с Cloudflare аккаунтом
cloudflared tunnel login
```

Это откроет браузер для входа в Cloudflare. Выберите домен `medoyid-club.com`.

## 🚇 Шаг 3: Создание туннеля

```bash
# Создаем туннель
cloudflared tunnel create medoyid-server

# Получаем ID туннеля (сохраните его!)
cloudflared tunnel list
```

## 📝 Шаг 4: Конфигурация туннеля

Создайте файл конфигурации:

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Содержимое файла `config.yml`:

```yaml
tunnel: medoyid-server
credentials-file: /home/dzianis/.cloudflared/TUNNEL_ID.json

ingress:
  # SSH доступ
  - hostname: ssh.medoyid-club.com
    service: ssh://localhost:22
  
  # Веб-интерфейс для мониторинга (можно настроить позже)
  - hostname: admin.medoyid-club.com  
    service: http://localhost:8080
  
  # Просмотр логов бота
  - hostname: logs.medoyid-club.com
    service: http://localhost:8081
  
  # Fallback для всех остальных запросов
  - service: http_status:404
```

**Важно**: Замените `TUNNEL_ID` на реальный ID вашего туннеля из шага 3.

## 🌐 Шаг 5: DNS записи

Создайте DNS записи в Cloudflare Dashboard:

```bash
# Команды для создания DNS записей (выполните на сервере)
cloudflared tunnel route dns medoyid-server ssh.medoyid-club.com
cloudflared tunnel route dns medoyid-server admin.medoyid-club.com  
cloudflared tunnel route dns medoyid-server logs.medoyid-club.com
```

## 🔄 Шаг 6: Systemd сервис

Создайте сервис для автозапуска:

```bash
# Устанавливаем как сервис
sudo cloudflared service install

# Запускаем и включаем автозапуск
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Проверяем статус
sudo systemctl status cloudflared
```

## 🔒 Шаг 7: Настройка SSH клиента

На вашем локальном компьютере создайте файл `~/.ssh/config`:

```
Host medoyid-server
    HostName ssh.medoyid-club.com
    User dzianis
    Port 22
    ProxyCommand cloudflared access ssh --hostname %h
```

## 📊 Шаг 8: Веб-интерфейсы (опционально)

Для мониторинга и логов можете настроить простые веб-сервисы:

### Простой сервер для логов:
```bash
# Создаем простой HTTP сервер для логов
cat > /home/dzianis/log_server.py << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os
from pathlib import Path

class LogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/home/dzianis/shorts-shot/logs", **kwargs)

PORT = 8081
with socketserver.TCPServer(("", PORT), LogHandler) as httpd:
    print(f"Serving logs at port {PORT}")
    httpd.serve_forever()
EOF

chmod +x /home/dzianis/log_server.py

# Создаем сервис для сервера логов
sudo cat > /etc/systemd/system/log-server.service << 'EOF'
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

sudo systemctl enable log-server
sudo systemctl start log-server
```

## ✅ Проверка работы

1. **SSH**: `ssh medoyid-server` (с локального компьютера)
2. **Логи**: Откройте `https://logs.medoyid-club.com` в браузере
3. **Статус туннеля**: `sudo systemctl status cloudflared`

## 🔧 Полезные команды

```bash
# Просмотр логов туннеля
sudo journalctl -u cloudflared -f

# Перезапуск туннеля
sudo systemctl restart cloudflared

# Список активных туннелей
cloudflared tunnel list

# Информация о туннеле
cloudflared tunnel info medoyid-server
```

## 🚨 Устранение проблем

1. **Туннель не запускается**: Проверьте путь к credentials файлу в config.yml
2. **DNS не работает**: Убедитесь что записи созданы в Cloudflare Dashboard  
3. **SSH не подключается**: Проверьте что cloudflared установлен на локальном компьютере

## 🔐 Безопасность

- Все соединения проходят через HTTPS
- Никаких открытых портов на сервере
- Доступ только через Cloudflare аутентификацию
- Можно дополнительно настроить Access правила в Cloudflare

Готово! Теперь у вас есть безопасный доступ к серверу через интернет. 🚀
