# Cloudflare Tunnel Setup для Telegram-to-YouTube Shorts
Write-Host "🌐 Настройка Cloudflare Tunnel для удаленного доступа" -ForegroundColor Green

# Проверяем, установлен ли cloudflared
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    Write-Host "📥 Устанавливаем cloudflared..." -ForegroundColor Yellow
    
    # Создаем временную папку
    $tempDir = New-TemporaryFile | %{rm $_; mkdir $_}
    
    # Скачиваем cloudflared для Windows
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    $output = "$tempDir\cloudflared.exe"
    
    Write-Host "📥 Скачиваем cloudflared..."
    Invoke-WebRequest -Uri $url -OutFile $output
    
    # Копируем в системную папку
    $systemPath = "$env:ProgramFiles\Cloudflare"
    New-Item -ItemType Directory -Path $systemPath -Force | Out-Null
    Copy-Item $output "$systemPath\cloudflared.exe" -Force
    
    # Добавляем в PATH
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
    if ($currentPath -notlike "*$systemPath*") {
        [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$systemPath", "Machine")
        $env:PATH += ";$systemPath"
    }
    
    Write-Host "✅ cloudflared установлен!" -ForegroundColor Green
    Remove-Item $tempDir -Recurse -Force
}

Write-Host ""
Write-Host "🔐 Настройка аутентификации..." -ForegroundColor Cyan
Write-Host "1. Откройте браузер и перейдите по ссылке для авторизации"
Write-Host "2. Войдите в свой Cloudflare аккаунт"
Write-Host "3. Разрешите доступ для cloudflared"
Write-Host ""

# Запускаем аутентификацию
Start-Process "cloudflared" -ArgumentList "tunnel", "login" -Wait

Write-Host ""
Write-Host "🚇 Создание туннеля..." -ForegroundColor Cyan

# Создаем уникальное имя для туннеля
$tunnelName = "telegram-shorts-$(Get-Random -Minimum 1000 -Maximum 9999)"
Write-Host "📝 Имя туннеля: $tunnelName"

# Создаем туннель
$createResult = & cloudflared tunnel create $tunnelName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Туннель создан!" -ForegroundColor Green
    
    # Извлекаем UUID туннеля
    $tunnelId = ($createResult | Select-String "tunnel (\w{8}-\w{4}-\w{4}-\w{4}-\w{12})").Matches.Groups[1].Value
    Write-Host "🆔 ID туннеля: $tunnelId"
    
    # Создаем конфигурационный файл
    $configDir = "$env:USERPROFILE\.cloudflared"
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    
    $configContent = @"
tunnel: $tunnelId
credentials-file: $configDir\$tunnelId.json

ingress:
  # SSH доступ к серверу
  - hostname: ssh-$tunnelName.your-domain.com
    service: ssh://localhost:22
    
  # Web интерфейс логов (если будет)
  - hostname: logs-$tunnelName.your-domain.com  
    service: http://localhost:8080
    
  # Резерв для будущих сервисов
  - hostname: api-$tunnelName.your-domain.com
    service: http://localhost:3000
    
  # Catch-all (обязательно последний)
  - service: http_status:404
"@
    
    $configPath = "$configDir\config.yml"
    $configContent | Out-File -FilePath $configPath -Encoding UTF8
    
    Write-Host "✅ Конфигурация создана: $configPath" -ForegroundColor Green
    
    # Создаем DNS записи
    Write-Host ""
    Write-Host "🌐 Создание DNS записей..." -ForegroundColor Cyan
    
    & cloudflared tunnel route dns $tunnelId "ssh-$tunnelName.your-domain.com"
    & cloudflared tunnel route dns $tunnelId "logs-$tunnelName.your-domain.com"
    & cloudflared tunnel route dns $tunnelId "api-$tunnelName.your-domain.com"
    
    Write-Host "✅ DNS записи созданы!" -ForegroundColor Green
    
    # Создаем скрипт запуска
    $startScript = @"
# Запуск Cloudflare Tunnel
Write-Host "🚇 Запуск Cloudflare Tunnel..." -ForegroundColor Green
Write-Host "🌐 SSH доступ: ssh-$tunnelName.your-domain.com"
Write-Host "📊 Логи: https://logs-$tunnelName.your-domain.com"
Write-Host "🔌 API: https://api-$tunnelName.your-domain.com"
Write-Host ""
Write-Host "Для остановки нажмите Ctrl+C" -ForegroundColor Yellow
Write-Host ""

cloudflared tunnel run $tunnelName
"@
    
    $startScript | Out-File -FilePath "start_tunnel.ps1" -Encoding UTF8
    
    # Создаем скрипт установки службы Windows
    $serviceScript = @"
# Установка Cloudflare Tunnel как службы Windows
Write-Host "🔧 Установка службы Windows..." -ForegroundColor Green

cloudflared service install

Write-Host "✅ Служба установлена!" -ForegroundColor Green
Write-Host "Служба будет автоматически запускаться при загрузке Windows"
Write-Host ""
Write-Host "Управление службой:"
Write-Host "  Запуск: net start cloudflared"
Write-Host "  Остановка: net stop cloudflared"
Write-Host "  Статус: sc query cloudflared"
"@
    
    $serviceScript | Out-File -FilePath "install_tunnel_service.ps1" -Encoding UTF8
    
    Write-Host ""
    Write-Host "🎉 Cloudflare Tunnel настроен!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Следующие шаги:" -ForegroundColor Cyan
    Write-Host "1. Замените 'your-domain.com' на ваш домен в конфигурации"
    Write-Host "2. Запустите туннель: .\start_tunnel.ps1"
    Write-Host "3. Установите как службу: .\install_tunnel_service.ps1"
    Write-Host ""
    Write-Host "🔗 Ваши адреса:" -ForegroundColor Yellow
    Write-Host "  SSH: ssh-$tunnelName.your-domain.com"
    Write-Host "  Логи: https://logs-$tunnelName.your-domain.com"
    Write-Host "  API: https://api-$tunnelName.your-domain.com"
    Write-Host ""
    Write-Host "📁 Конфигурация: $configPath"
    
} else {
    Write-Host "❌ Ошибка создания туннеля!" -ForegroundColor Red
    Write-Host $createResult
}

Write-Host ""
Write-Host "💡 Документация: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/"
