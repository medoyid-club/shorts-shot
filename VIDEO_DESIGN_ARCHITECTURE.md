# Архитектура системы генерации видео

## Обзор

Проект поддерживает две независимые версии генераторов видео, которые можно переключать через конфигурацию:

- **V1 (MoviePy)** - текущий стабильный дизайн
- **V2 (HTML+Selenium)** - новый дизайн с анимациями

## Структура проекта

```
services/
├── video_factory.py           # Фабрика для выбора генератора
├── video_generator.py         # V1: MoviePy генератор
├── video_generator_v2.py      # V2: HTML+Selenium генератор
├── llm_provider.py            # V1: Промпты для текущего дизайна
└── llm_provider_v2.py         # V2: Промпты для нового дизайна

resources/
└── templates/
    └── news_short_v2.html     # HTML шаблон для V2
```

## Переключение между версиями

### В config.ini или config.dev.ini:

```ini
[VIDEO]
# Версия генератора: v1 (MoviePy) или v2 (HTML+Selenium)
generator_version = v1  # или v2
```

### Программно:

Фабрика автоматически выбирает генератор на основе конфига:

```python
from services.video_factory import create_video_generator, create_llm_provider

# Создание генератора (автоматически V1 или V2)
composer = create_video_generator(config)

# Создание LLM провайдера (автоматически V1 или V2)
llm = create_llm_provider(config)
```

## V1: MoviePy генератор (Текущий)

### Особенности:
- Использует библиотеку MoviePy для создания видео
- Три секции: header (видео), middle (текст), footer (источник)
- Эффект "сердцебиения" на тексте
- Zoom-анимация на header
- Стабильная, проверенная версия

### LLM промпты V1:
- `summarize_for_video()` - возвращает строку (до 180 символов)
- `generate_seo_package()` - возвращает title, description, tags
- Промпты оптимизированы под украинский язык

### Настройки (config.ini):
```ini
[VIDEO]
generator_version = v1
duration_seconds = 5
width = 1080
height = 1920
header_ratio = 0.4
middle_ratio = 0.5
footer_ratio = 0.1
heartbeat_enabled = true
```

## V2: HTML+Selenium генератор (Новый)

### Особенности:
- Использует HTML шаблоны + Selenium для захвата анимаций
- Полный контроль над дизайном через HTML/CSS
- Поддержка сложных CSS анимаций
- Гибкий формат: заголовок, медиа, описание
- Длительность до 59 секунд

### LLM промпты V2:
- `summarize_for_video()` - возвращает dict с ключами `title` и `brief`
- `generate_news_title()` - генерирует заголовок (15-25 слов)
- `generate_news_brief()` - генерирует краткое описание (2-3 предложения)
- `generate_seo_package()` - SEO для YouTube
- Промпты адаптированы под новостной формат

### Настройки (config.ini):
```ini
[VIDEO]
generator_version = v2
v2_template_path = resources/templates/news_short_v2.html
v2_fps = 30
v2_duration_seconds = 59
v2_capture_method = sync_video
v2_headless = true  # false для отладки
```

### HTML шаблон

Шаблон находится в `resources/templates/news_short_v2.html`

Плейсхолдеры:
- `{{NEWS_TITLE}}` - заголовок новости
- `{{NEWS_BRIEF}}` - краткое описание
- `{{NEWS_IMAGE}}` - путь к изображению
- `{{NEWS_VIDEO}}` - путь к видео
- `{{SOURCE_NAME}}` - название источника (t.me/channel)
- `{{PUBLISH_DATE}}` - дата публикации

### Требования для V2:

1. **Selenium WebDriver:**
```bash
pip install selenium
```

2. **ChromeDriver:**
Скачать с https://chromedriver.chromium.org/
Убедитесь что версия ChromeDriver соответствует версии Chrome

3. **ffmpeg (для добавления аудио):**
Установите ffmpeg и добавьте в PATH

## Разработка и тестирование

### Dev конфигурация (config.dev.ini)

```ini
[VIDEO]
generator_version = v2  # Используем новый дизайн в dev
v2_headless = false     # Видим браузер при отладке
```

### Запуск в песочнице:

```bash
# Активируем venv
.\venv\Scripts\Activate.ps1

# Запускаем с dev конфигом
python run_sandbox_test.py
```

### Тестирование обеих версий:

1. **Тестируем V1:**
```ini
# config.dev.ini
[VIDEO]
generator_version = v1
```

2. **Тестируем V2:**
```ini
# config.dev.ini
[VIDEO]
generator_version = v2
```

3. Отправляем сообщение в тестовый канал Telegram
4. Проверяем результат в `outputs/dev/`

## Миграция с V1 на V2

### Шаг 1: Тестирование

Сначала протестируйте V2 в dev среде:

```ini
# config.dev.ini
[VIDEO]
generator_version = v2
```

### Шаг 2: Установка зависимостей

```bash
pip install selenium
# Установите ChromeDriver
```

### Шаг 3: Настройка шаблона

Отредактируйте `resources/templates/news_short_v2.html` под ваш бренд:
- Цвета
- Шрифты
- Анимации
- Логотип/бейдж источника

### Шаг 4: Тестирование в production

```ini
# config.ini
[VIDEO]
generator_version = v2
```

### Шаг 5: Мониторинг

Следите за логами:
- Проверьте что Selenium правильно инициализируется
- Проверьте качество захваченных кадров
- Убедитесь что ffmpeg добавляет аудио

## Откат на V1

Если возникли проблемы с V2, просто измените конфиг:

```ini
[VIDEO]
generator_version = v1
```

Система автоматически переключится на стабильную версию V1.

## Troubleshooting

### V2 не запускается

1. **Ошибка "Selenium не установлен":**
```bash
pip install selenium
```

2. **Ошибка "ChromeDriver not found":**
- Скачайте ChromeDriver: https://chromedriver.chromium.org/
- Убедитесь что версия совпадает с Chrome
- Добавьте в PATH

3. **Видео без звука:**
- Установите ffmpeg
- Добавьте ffmpeg в PATH
- Перезапустите скрипт

4. **Браузер не открывается в headless режиме:**
```ini
[VIDEO]
v2_headless = false  # Отключите headless для отладки
```

### LLM генерирует неправильный формат

**V1:** Возвращает строку
```python
short_text = await llm.summarize_for_video(text)
# short_text - это str
```

**V2:** Возвращает словарь
```python
content = await llm.summarize_for_video(text)
# content = {'title': '...', 'brief': '...'}
```

Фабрика `create_llm_provider()` автоматически выбирает правильный провайдер.

## Производительность

| Характеристика | V1 (MoviePy) | V2 (HTML+Selenium) |
|---------------|--------------|-------------------|
| Скорость генерации | ~5-10 секунд | ~60-90 секунд (59s видео) |
| Использование CPU | Среднее | Высокое |
| Использование RAM | ~500MB | ~1-2GB |
| Качество анимаций | Базовые | Продвинутые |
| Гибкость дизайна | Ограниченная | Полная |

## Рекомендации

1. **Для production:** Используйте V1 если нужна скорость и стабильность
2. **Для качественного контента:** Используйте V2 с кастомным HTML шаблоном
3. **Для разработки:** Тестируйте V2 с `v2_headless = false`
4. **Для A/B тестирования:** Создайте два канала и сравните эффективность

## Дальнейшее развитие

### Идеи для улучшения V2:

1. **Множество шаблонов:**
   - Создайте несколько HTML шаблонов для разных типов новостей
   - Автоматический выбор шаблона на основе контента

2. **Оптимизация производительности:**
   - Кеширование рендера браузера
   - Использование headless Chrome вместо полного Chrome
   - GPU ускорение для захвата кадров

3. **Расширенные анимации:**
   - Интеграция с anime.js
   - Particle effects
   - 3D трансформации (CSS 3D)

4. **Интерактивные элементы:**
   - Счетчики (анимация цифр)
   - Графики и диаграммы
   - Бегущая строка (ticker)

---

**Вопросы или предложения?** Создайте issue в репозитории проекта.

