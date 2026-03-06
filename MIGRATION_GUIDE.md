# Руководство по миграции на новую архитектуру

## Что изменилось?

Проект теперь поддерживает две версии генераторов видео:

- **V1 (MoviePy)** - ваш текущий стабильный генератор (без изменений)
- **V2 (HTML+Selenium)** - новый генератор с продвинутыми анимациями

## Для текущих пользователей

### Хорошая новость 🎉

**Ничего не сломалось!** Ваш текущий генератор V1 продолжает работать как раньше.

### Что делать?

**Вариант 1: Продолжить использовать V1 (ничего не делать)**

Просто убедитесь что в `config.ini`:

```ini
[VIDEO]
generator_version = v1
```

Или вообще не указывайте эту опцию - по умолчанию используется V1.

**Вариант 2: Попробовать V2 (новый дизайн)**

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Установите ChromeDriver (см. QUICK_START_V2.md)

3. Протестируйте:
```bash
python test_video_versions.py
```

4. Если все работает, переключитесь в `config.ini`:
```ini
[VIDEO]
generator_version = v2
```

## Изменения в коде

### Изменен main_script.py

**Было:**
```python
from services.video_generator import VideoComposer
from services.llm_provider import create_llm_provider

composer = VideoComposer(config)
llm = create_llm_provider(config)
```

**Стало:**
```python
from services.video_factory import create_video_generator, create_llm_provider

composer = create_video_generator(config)  # Автоматически V1 или V2
llm = create_llm_provider(config)          # Автоматически V1 или V2
```

Фабрика автоматически выбирает нужную версию на основе `generator_version` в конфиге.

### Обратная совместимость

Старый способ все еще работает:

```python
from services.video_generator import VideoComposer
from services.llm_provider import create_llm_provider as create_v1_llm

composer = VideoComposer(config)  # Всегда V1
llm = create_v1_llm(config)        # Всегда V1
```

## Новые файлы в проекте

```
services/
├── video_factory.py           # НОВЫЙ: Фабрика генераторов
├── video_generator_v2.py      # НОВЫЙ: HTML+Selenium генератор
└── llm_provider_v2.py         # НОВЫЙ: Промпты для V2

resources/
└── templates/
    └── news_short_v2.html     # НОВЫЙ: HTML шаблон

# Документация
VIDEO_DESIGN_ARCHITECTURE.md   # НОВЫЙ: Архитектура
QUICK_START_V2.md              # НОВЫЙ: Быстрый старт V2
MIGRATION_GUIDE.md             # НОВЫЙ: Это руководство

# Скрипты
test_video_versions.py         # НОВЫЙ: Тест обеих версий
```

## Обновленные файлы

### config.ini
Добавлены настройки для V2:
```ini
[VIDEO]
generator_version = v1  # НОВАЯ опция

# === Настройки для V2 (HTML+Selenium) ===
v2_template_path = resources/templates/news_short_v2.html
v2_fps = 30
v2_duration_seconds = 59
v2_capture_method = sync_video
v2_headless = true
```

### config.dev.ini
Аналогично, добавлены настройки V2.

### requirements.txt
Добавлены зависимости для V2:
```
selenium>=4.15.0
opencv-python>=4.8.0
```

### main_script.py
Обновлены импорты для использования фабрики (см. выше).

## Миграция с сервера

### Если проект запущен на сервере (systemd)

1. **Подготовка на локальной машине:**
```bash
# Тестируйте локально
python test_video_versions.py

# Если V2 работает и вас устраивает
```

2. **Коммит и пуш изменений:**
```bash
git add .
git commit -m "Add V2 video generator with HTML+Selenium"
git push origin main
```

3. **На сервере:**
```bash
# Остановите сервис
sudo systemctl stop telegram-shorts

# Обновите код
git pull origin main

# Обновите зависимости
source venv/bin/activate
pip install -r requirements.txt

# Установите ChromeDriver (если хотите использовать V2)
# См. QUICK_START_V2.md

# Выберите версию в config.ini
nano config.ini
# [VIDEO]
# generator_version = v1  # или v2

# Запустите сервис
sudo systemctl start telegram-shorts

# Проверьте логи
sudo journalctl -u telegram-shorts -f
```

#### Быстрое восстановление YouTube OAuth токена

Если сервис падает с ошибками OAuth (`could not locate runnable browser`, проблемы с `token.json`), используйте отдельную инструкцию:

- `YOUTUBE_TOKEN_RUNBOOK.md`

Коротко:

1. Остановить сервис:
```bash
sudo systemctl stop telegram-shorts
```
2. Пройти процедуру получения нового `token.json` по runbook.
3. Проверить токен (`valid=True`, `refresh=True`).
4. Запустить сервис и проверить логи:
```bash
sudo systemctl start telegram-shorts
sudo journalctl -u telegram-shorts -n 120 -f -o short-iso
```

### Откат на V1 (если что-то пошло не так)

**На сервере:**
```bash
sudo systemctl stop telegram-shorts
nano config.ini
# Измените: generator_version = v1
sudo systemctl start telegram-shorts
```

**Или через git:**
```bash
git checkout HEAD~1  # Откат на предыдущий коммит
sudo systemctl restart telegram-shorts
```

## FAQ

### Нужно ли переходить на V2?

**Нет.** V1 полностью функционален и будет поддерживаться.

V2 - это **опция** для тех, кто хочет:
- Более красивые анимации
- Больше контроля над дизайном через HTML/CSS
- Более длинные видео (до 59 секунд)

### Можно ли использовать обе версии одновременно?

Нет, выбирается одна версия через `generator_version`.

Но вы можете:
- Использовать V1 в production
- Тестировать V2 в dev (через `config.dev.ini`)

### Что если я хочу остаться на V1 навсегда?

Отлично! Просто не меняйте `generator_version = v1` в конфиге.

### Будет ли V1 удален в будущем?

Нет планов удалять V1. Обе версии будут поддерживаться.

### У меня custom изменения в video_generator.py

Ваши изменения в `services/video_generator.py` не затронуты.

V2 - это полностью отдельный файл (`video_generator_v2.py`).

### Как вернуться к старой версии кода?

```bash
git log  # Найдите коммит до миграции
git checkout <commit_hash>
```

Или просто установите `generator_version = v1` и продолжайте работать.

## Поддержка

Если возникли проблемы:

1. **Проверьте логи:**
```bash
# Локально
ls -la logs/

# На сервере
sudo journalctl -u telegram-shorts -n 100
```

2. **Запустите диагностику:**
```bash
python test_video_versions.py
```

3. **Откройте issue** в репозитории с:
   - Версией Python
   - Содержимым `config.ini` (без секретов)
   - Логами ошибок

---

**Главное:** Миграция необязательна. V1 продолжает работать как раньше! 🚀

