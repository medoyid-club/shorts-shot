# 🐦 Настройка Twitter/X интеграции

## 📋 Требования

- **Twitter Developer Account** (бесплатно)
- **Elevated access** для базовых функций
- **tweepy** библиотека

## 🚀 Пошаговая настройка

### 1. Создание Developer Account

1. Перейти на https://developer.twitter.com/
2. Войти в свой Twitter аккаунт
3. Подать заявку на Developer Account
4. Дождаться одобрения (обычно в течение дня)

### 2. Создание приложения

1. В Developer Portal нажать "Create App"
2. Заполнить форму:
   - **App name**: `telegram-shorts-bot`
   - **Description**: `Automated posting from Telegram to Twitter`
   - **Website URL**: `https://example.com` (можно любой)
   - **Terms of Service**: `https://example.com/terms`
   - **Privacy Policy**: `https://example.com/privacy`

### 3. Настройка разрешений

1. Перейти в "App Settings" → "Setup"
2. В разделе "User authentication settings" нажать "Set up"
3. Выбрать:
   - **App permissions**: "Read and write"
   - **Type of App**: "Web App, Automated App or Bot"
   - **Callback URI**: `https://example.com/callback`
   - **Website URL**: `https://example.com`

### 4. Получение ключей API

1. В разделе "Keys and tokens":
   - **API Key and Secret**: Нажать "Regenerate" и скопировать
   - **Access Token and Secret**: Нажать "Generate" и скопировать

### 5. Установка библиотеки

```bash
# В вашем виртуальном окружении
pip install tweepy
```

### 6. Настройка конфигурации

Добавить в `.env` файл:

```env
# Twitter/X API Keys
TWITTER_API_KEY=your_api_key_here
TWITTER_API_SECRET=your_api_secret_here
TWITTER_ACCESS_TOKEN=your_access_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here
```

### 7. Включение в config.ini

```ini
[TWITTER]
enabled = true
upload_mode = image  # image (бесплатно) или video ($100/мес)
```

## 💰 Тарифные планы 2024

### ✅ **Free Tier**
- ✅ Публикация текста
- ✅ Публикация изображений  
- ✅ 1,500 постов в месяц
- ✅ Read/Write API доступ
- ❌ Загрузка видео

### 💵 **Basic ($100/месяц)**
- ✅ Все из Free
- ✅ **Загрузка видео**
- ✅ 50,000 постов в месяц
- ✅ Расширенные метрики

### 💎 **Pro ($5,000/месяц)**
- ✅ Все из Basic
- ✅ Продвинутая аналитика
- ✅ Приоритетная поддержка

## 🎯 Рекомендуемая стратегия

### Этап 1: Бесплатный старт
```
Telegram → YouTube (видео) + Twitter (скриншот из видео)
```
- Полные шортсы на YouTube
- Превьюшки + текст на Twitter
- **Стоимость: $0/месяц**

### Этап 2: Масштабирование
```
Telegram → YouTube (видео) + Twitter (полное видео)
```
- Полные шортсы на обеих платформах
- **Стоимость: $100/месяц**

## 🔧 Режимы работы

### `upload_mode = image` (по умолчанию)
- Извлекает кадр из середины видео
- Публикует изображение + текст + хештеги
- **Бесплатно**

### `upload_mode = video`
- Публикует полное видео
- Требует Basic план ($100/мес)

### `upload_mode = auto`
- Пытается загрузить видео
- При ошибке переключается на изображение

## 📊 Тестирование

```python
# Проверка подключения
from services.twitter_uploader import TwitterUploader
twitter = TwitterUploader(config)
print(twitter.get_account_info())
```

## 🚨 Частые ошибки

1. **"Invalid credentials"**
   - Проверьте правильность API ключей
   - Убедитесь что включили Read and Write permissions

2. **"App only authentication"**
   - Создайте Access Token в Developer Portal
   - Убедитесь что используете User Access Token, не App-only

3. **"Video upload failed"**
   - Проверьте что у вас Basic план ($100/мес)
   - Попробуйте режим `upload_mode = image`

4. **"Rate limit exceeded"**
   - Подождите 15 минут
   - Уменьшите частоту постинга

## 📈 Статистика

Бот автоматически логирует:
- ✅ Успешные публикации
- ❌ Ошибки загрузки
- 📊 Ссылки на опубликованные посты
- 📈 Информацию об аккаунте

## 🔗 Полезные ссылки

- [Twitter Developer Portal](https://developer.twitter.com/)
- [Twitter API Documentation](https://developer.twitter.com/en/docs/twitter-api)
- [Tweepy Documentation](https://docs.tweepy.org/)
- [Rate Limits](https://developer.twitter.com/en/docs/twitter-api/rate-limits)
