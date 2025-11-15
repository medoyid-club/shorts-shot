# 🔧 Исправление проблемы с API токеном

## ❌ Проблема
API токен не имеет прав для получения Account ID. Ошибка: `{"result":[],"result_info":{"page":1,"per_page":20,"total_pages":0,"count":0,"total_count":0},"success":true,"errors":[],"messages":[]}`

## ✅ Решения

### Вариант 1: Создать новый токен с правильными правами (РЕКОМЕНДУЕТСЯ)

1. **Перейдите:** https://dash.cloudflare.com/profile/api-tokens
2. **Нажмите:** "Create Token" → "Custom token"
3. **Настройте права:**
   ```
   Permissions:
   - Account:Cloudflare Tunnel:Edit
   - Zone:Zone:Read  
   - Zone:DNS:Edit
   
   Account Resources:
   - Include:All accounts
   
   Zone Resources:
   - Include:Specific zone:medoyid-club.com
   ```
4. **Скопируйте новый токен** и замените в скрипте

### Вариант 2: Использовать исправленный скрипт (БЫСТРО)

Запустите исправленный скрипт, который обходит проблему:

```bash
chmod +x fix_tunnel_setup.sh
./fix_tunnel_setup.sh
```

### Вариант 3: Ручная настройка с cloudflared

```bash
# 1. Экспортируйте токен
export CLOUDFLARE_API_TOKEN="FC4E1zdC8UT-KSvyypVp10voIq_h_0O9RNL6RYkq"

# 2. Создайте туннель напрямую
cloudflared tunnel create medoyid-server

# 3. Получите ID туннеля
TUNNEL_ID=$(cloudflared tunnel list | grep medoyid-server | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# 4. Создайте конфигурацию
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml > /dev/null << EOF
tunnel: $TUNNEL_ID
credentials-file: /home/dzianis/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: ssh.medoyid-club.com
    service: ssh://localhost:22
  - hostname: logs.medoyid-club.com
    service: http://localhost:8081
  - service: http_status:404
EOF

# 5. Создайте DNS записи
cloudflared tunnel route dns medoyid-server ssh.medoyid-club.com
cloudflared tunnel route dns medoyid-server logs.medoyid-club.com

# 6. Запустите как сервис
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## 🔍 Проверка токена

Проверьте, какие права у вашего токена:

```bash
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer FC4E1zdC8UT-KSvyypVp10voIq_h_0O9RNL6RYkq" \
     -H "Content-Type:application/json" | jq '.result'
```

## 🎯 Рекомендация

**Запустите исправленный скрипт `fix_tunnel_setup.sh`** - он автоматически обойдет проблему с Account ID и настроит туннель альтернативным способом.

После запуска проверьте:
```bash
sudo systemctl status cloudflared
dig ssh.medoyid-club.com
```

Готово! 🚀
