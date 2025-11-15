# 🚀 Скрипт для создания SSH туннеля для FileZilla
# Запустите этот скрипт в отдельном окне PowerShell и оставьте открытым

Write-Host "🔗 Создание SSH туннеля для FileZilla..." -ForegroundColor Green
Write-Host ""
Write-Host "📋 Инструкция:" -ForegroundColor Yellow
Write-Host "1. Оставьте это окно ОТКРЫТЫМ во время работы с FileZilla"
Write-Host "2. В FileZilla подключайтесь к: localhost:2222"
Write-Host "3. Пользователь: dzianis"
Write-Host ""

# Проверяем cloudflared
try {
    $null = Get-Command cloudflared -ErrorAction Stop
    Write-Host "✅ cloudflared найден" -ForegroundColor Green
} catch {
    Write-Host "❌ ОШИБКА: cloudflared не найден!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Установите cloudflared:" -ForegroundColor Yellow
    Write-Host "winget install Cloudflare.cloudflared"
    Write-Host ""
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

Write-Host ""
Write-Host "🔗 Создаю туннель localhost:2222 -> ssh.medoyid-club.com:22" -ForegroundColor Cyan
Write-Host "⚠️  НЕ ЗАКРЫВАЙТЕ это окно пока используете FileZilla!" -ForegroundColor Red
Write-Host ""

# Создаем SSH туннель
try {
    # Используем ssh с ProxyCommand через cloudflared
    ssh -L 2222:localhost:22 -o "ProxyCommand=cloudflared access ssh --hostname ssh.medoyid-club.com" dzianis@ssh.medoyid-club.com -N
} catch {
    Write-Host "❌ Ошибка создания туннеля" -ForegroundColor Red
    Write-Host $_.Exception.Message
    Read-Host "Нажмите Enter для выхода"
}
