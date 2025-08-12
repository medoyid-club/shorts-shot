#!/bin/bash
# Скрипт установки Telegram-to-YouTube Shorts на Ubuntu сервер

set -e

echo "🚀 Установка Telegram-to-YouTube Shorts Bot..."

# Обновление системы
echo "📦 Обновление пакетов системы..."
sudo apt update
sudo apt upgrade -y

# Установка зависимостей
echo "📦 Установка системных зависимостей..."
sudo apt install -y python3 python3-pip python3-venv git ffmpeg

# Создание пользователя (опционально)
if ! id "botuser" &>/dev/null; then
    echo "👤 Создание пользователя botuser..."
    sudo useradd -m -s /bin/bash botuser
    sudo usermod -aG sudo botuser
fi

# Переход в домашнюю директорию
cd /home/botuser

# Клонирование репозитория (замените URL на ваш)
echo "📁 Клонирование проекта..."
if [ -d "Telegram-to-YouTube-Shorts" ]; then
    echo "Директория уже существует, обновляем..."
    cd Telegram-to-YouTube-Shorts
    git pull
else
    git clone https://github.com/YOUR_USERNAME/Telegram-to-YouTube-Shorts.git
    cd Telegram-to-YouTube-Shorts
fi

# Создание виртуального окружения
echo "🐍 Создание виртуального окружения..."
python3 -m venv .venv
source .venv/bin/activate

# Установка Python зависимостей
echo "📦 Установка Python пакетов..."
pip install --upgrade pip
pip install -r requirements.txt

# Создание необходимых директорий
echo "📁 Создание рабочих директорий..."
mkdir -p resources/music
mkdir -p resources/fonts
mkdir -p resources/tmp
mkdir -p resources/default_backgrounds
mkdir -p outputs
mkdir -p state

# Копирование примера конфигурации
if [ ! -f ".env" ]; then
    echo "⚙️ Создание .env файла..."
    cp example.env .env
    echo "❗ ВНИМАНИЕ: Отредактируйте файл .env с вашими API ключами!"
    echo "nano .env"
fi

# Установка прав
sudo chown -R botuser:botuser /home/botuser/Telegram-to-YouTube-Shorts

# Создание systemd service
echo "🔧 Создание systemd сервиса..."
sudo tee /etc/systemd/system/telegram-shorts.service > /dev/null <<EOF
[Unit]
Description=Telegram to YouTube Shorts Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/Telegram-to-YouTube-Shorts
Environment=PATH=/home/botuser/Telegram-to-YouTube-Shorts/.venv/bin
ExecStart=/home/botuser/Telegram-to-YouTube-Shorts/.venv/bin/python main_script.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd
sudo systemctl daemon-reload

echo "✅ Установка завершена!"
echo ""
echo "🔧 Следующие шаги:"
echo "1. Отредактируйте .env файл: sudo -u botuser nano /home/botuser/Telegram-to-YouTube-Shorts/.env"
echo "2. Добавьте музыкальные файлы в: /home/botuser/Telegram-to-YouTube-Shorts/resources/music/"
echo "3. Добавьте шрифты в: /home/botuser/Telegram-to-YouTube-Shorts/resources/fonts/"
echo "4. Добавьте YouTube credentials JSON файл в корень проекта"
echo "5. Запустите сервис: sudo systemctl enable telegram-shorts && sudo systemctl start telegram-shorts"
echo "6. Проверьте статус: sudo systemctl status telegram-shorts"
echo "7. Просмотр логов: sudo journalctl -u telegram-shorts -f"
echo ""
echo "📚 Подробная документация в README.md"
