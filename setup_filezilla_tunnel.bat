@echo off
echo 🚀 Создание SSH туннеля для FileZilla
echo.
echo Этот скрипт создаст локальный туннель для FileZilla
echo Оставьте это окно открытым во время работы с FileZilla
echo.
echo Подключение через: ssh.medoyid-club.com
echo Локальный порт: 2222
echo.

REM Проверяем наличие cloudflared
where cloudflared >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ ОШИБКА: cloudflared не найден!
    echo.
    echo Установите cloudflared:
    echo 1. Скачайте с https://github.com/cloudflare/cloudflared/releases
    echo 2. Или используйте: winget install Cloudflare.cloudflared
    echo.
    pause
    exit /b 1
)

echo ✅ cloudflared найден
echo.
echo 🔗 Создаем SSH туннель...
echo ⚠️  Не закрывайте это окно пока используете FileZilla!
echo.

REM Создаем SSH туннель через ssh + cloudflared
echo 🔗 Попытка создания туннеля через SSH...
ssh -L 2222:localhost:22 -o "ProxyCommand=cloudflared access ssh --hostname ssh.medoyid-club.com" dzianis@ssh.medoyid-club.com -N

if %errorlevel% neq 0 (
    echo.
    echo ❌ SSH туннель не удался, пробуем альтернативный способ...
    echo.
    echo 🔗 Создаем прямой туннель через cloudflared...
    cloudflared access ssh --hostname ssh.medoyid-club.com --url localhost:2222
)

echo.
echo ❌ Туннель закрыт
pause
