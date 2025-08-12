# Telegram-to-YouTube Shorts

Автоматический сервис для мониторинга Telegram канала и создания YouTube Shorts с загрузкой в YouTube.

## Возможности

- ✅ Мониторинг приватных Telegram каналов через bot API
- ✅ Обработка медиа (изображения и видео)
- ✅ LLM-генерация текста и SEO данных (Google Gemini)
- ✅ Создание вертикальных видео 1080x1920 с:
  - Динамическим заголовком (zoom-in эффект)
  - Адаптивным текстом с максимальной читаемостью
  - Анимированной диаграммой сердцебиения
  - Автоматическим аудио сопровождением
- ✅ Автоматическая загрузка в YouTube с метаданными
- ✅ Хештеги в заголовке (3 шт.) и описании (5 шт.)

## Требования

- Python 3.11+
- Google Gemini API key
- Telegram Bot API token
- YouTube Data API v3 credentials
- FFmpeg (для MoviePy)

## Быстрый запуск

### 1. Клонирование и установка

```bash
git clone <repository-url>
cd Telegram-to-YouTube-Shorts
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка API ключей

Создайте файл `.env`:

```env
# Telegram API (получить на https://my.telegram.org/apps)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL=-1001234567890  # ID канала

# Google Gemini API (получить на https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key

# YouTube API (создать в Google Cloud Console)
YOUTUBE_CLIENT_SECRET_FILE=client_secret_xxx.json
```

### 3. Настройка YouTube API

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включите YouTube Data API v3
3. Создайте OAuth 2.0 credentials (Desktop application)
4. Скачайте JSON файл и поместите в корень проекта
5. Обновите путь в `.env`

### 4. Подготовка ресурсов

```bash
# Создание директорий
mkdir -p resources/{music,fonts,tmp,default_backgrounds}
mkdir -p outputs
mkdir -p state

# Добавьте музыкальные файлы в resources/music/
# Добавьте шрифты в resources/fonts/ (например, Arsenal-Bold.ttf)
```

### 5. Настройка Telegram бота

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Добавьте бота в ваш канал как администратора
3. Дайте права на чтение сообщений

### 6. Запуск

```bash
python main_script.py
```

При первом запуске будет выполнена OAuth авторизация для YouTube.

## Конфигурация

Основные настройки в `config.ini`:

```ini
[VIDEO]
duration_seconds = 8
width = 1080
height = 1920
# Цвета и эффекты
middle_red_rgb = 180,30,30
header_zoom_start = 1.05
header_zoom_end = 1.00
# Анимация сердцебиения
heartbeat_enabled = true
heartbeat_cycle_seconds = 1.6

[LLM]
gemini_model = gemini-2.0-flash-exp

[YOUTUBE]
privacy_status = private
category_id = 25  # News & Politics
```

## Деплой на Ubuntu сервер

### Systemd service

Создайте `/etc/systemd/system/telegram-shorts.service`:

```ini
[Unit]
Description=Telegram to YouTube Shorts Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Telegram-to-YouTube-Shorts
Environment=PATH=/home/ubuntu/Telegram-to-YouTube-Shorts/.venv/bin
ExecStart=/home/ubuntu/Telegram-to-YouTube-Shorts/.venv/bin/python main_script.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Установка и запуск

```bash
# Установка зависимостей
sudo apt update
sudo apt install python3-pip python3-venv ffmpeg

# Деплой проекта
git clone <repository-url>
cd Telegram-to-YouTube-Shorts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Настройка .env файла
cp example.env .env
nano .env

# Запуск как сервис
sudo systemctl enable telegram-shorts.service
sudo systemctl start telegram-shorts.service
sudo systemctl status telegram-shorts.service

# Логи
sudo journalctl -u telegram-shorts.service -f
```

## Структура проекта

```
├── main_script.py              # Основной файл запуска
├── config.ini                  # Конфигурация
├── requirements.txt            # Python зависимости
├── services/                   # Модули сервиса
│   ├── config_loader.py        # Загрузка конфигурации
│   ├── llm_provider.py         # Интеграция с Gemini
│   ├── telegram_monitor.py     # Мониторинг Telegram
│   ├── video_generator.py      # Создание видео
│   └── youtube_uploader.py     # Загрузка в YouTube
├── resources/                  # Ресурсы
│   ├── music/                  # Аудиофайлы
│   ├── fonts/                  # Шрифты
│   └── tmp/                    # Временные файлы
├── outputs/                    # Готовые видео
└── state/                      # Сессии и состояние
```

## Устранение неполадок

### Проблемы с квотами Gemini
- Используйте `gemini-2.0-flash-exp` вместо `gemini-1.5-flash`
- Проверьте лимиты на [Google AI Studio](https://aistudio.google.com/)

### Проблемы с Telegram
- Убедитесь что бот добавлен как администратор канала
- Проверьте права на чтение сообщений
- Используйте правильный ID канала (начинается с -100)

### Проблемы с YouTube
- Проверьте статус OAuth приложения в Google Cloud Console
- Добавьте тестового пользователя при статусе "In testing"
- Удалите `token.json` для повторной авторизации

## Лицензия

MIT License - см. LICENSE файл для деталей.