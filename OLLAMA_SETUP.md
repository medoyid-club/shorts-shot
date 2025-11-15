# Установка Ollama для локальной LLM

## Что такое Ollama?

Ollama - это локальный сервер для запуска LLM моделей на вашем компьютере.
**Преимущества:**
- ✅ Работает оффлайн
- ✅ Нет ограничений по запросам
- ✅ Бесплатно
- ✅ Приватность (данные не уходят в интернет)

**Требования:**
- Windows 10/11
- 16GB RAM (минимум 8GB)
- ~10GB места на диске
- Желательно: видеокарта NVIDIA с 6GB+ VRAM

---

## Шаг 1: Установка Ollama

### Windows

1. **Скачайте Ollama:**
   - Перейдите на https://ollama.com/download
   - Нажмите "Download for Windows"
   - Запустите `OllamaSetup.exe`

2. **Установите:**
   - Следуйте инструкциям установщика
   - После установки Ollama автоматически запустится в фоне

3. **Проверьте установку:**
   ```powershell
   ollama --version
   ```

---

## Шаг 2: Скачивание модели

У вас уже есть файл `gpt-oss-20b-MXFP4.gguf`. Нужно импортировать его в Ollama.

### Вариант A: Импорт существующей модели (рекомендуется)

1. **Создайте Modelfile:**
   
   Создайте файл `Modelfile` (без расширения) со следующим содержимым:
   
   ```
   FROM D:/path/to/your/gpt-oss-20b-MXFP4.gguf
   
   PARAMETER temperature 0.7
   PARAMETER top_p 0.9
   PARAMETER stop "<|im_start|>"
   PARAMETER stop "<|im_end|>"
   
   TEMPLATE """{{ .Prompt }}"""
   ```
   
   **Замените путь** на актуальный путь к вашему файлу модели!

2. **Импортируйте модель:**
   ```powershell
   ollama create gpt-oss-20b-MXFP4 -f Modelfile
   ```

3. **Проверьте:**
   ```powershell
   ollama list
   ```
   
   Вы должны увидеть `gpt-oss-20b-MXFP4` в списке.

### Вариант B: Использовать готовую модель из библиотеки Ollama

Если импорт не работает, можно использовать одну из предустановленных моделей:

```powershell
# Скачать небольшую модель для тестов (3GB)
ollama pull llama3.2:3b

# Или более мощную модель (7GB)
ollama pull llama3.2:7b

# Или модель на украинском языке
ollama pull saiga-llama3
```

Затем в `config.ini` измените:
```ini
ollama_model = llama3.2:7b
```

---

## Шаг 3: Запуск Ollama сервера

Ollama запускается автоматически, но вы можете проверить:

```powershell
# Проверка статуса
ollama serve
```

По умолчанию сервер работает на `http://localhost:11434`

### Тест модели:

```powershell
ollama run gpt-oss-20b-MXFP4
```

Введите тестовый запрос:
```
Привіт! Розкажи коротко про себе українською мовою.
```

Для выхода: `/bye`

---

## Шаг 4: Настройка проекта

1. **Откройте `config.ini`:**
   ```ini
   [LLM]
   # Переключитесь на ollama
   provider = ollama
   gemini_model = gemini-2.0-flash-exp
   
   # Настройки Ollama
   ollama_model = gpt-oss-20b-MXFP4
   ollama_url = http://localhost:11434
   ```

2. **Установите зависимость:**
   ```powershell
   .\venv\Scripts\activate
   pip install httpx
   ```

---

## Шаг 5: Тестирование

### Тест 1: Только дизайн (без LLM)

Проверьте что дизайн работает корректно:

```powershell
cd "D:\work\Telegram-to-YouTube Shorts"
.\venv\Scripts\python.exe test_design_only.py
```

Это создаст видео с заранее подготовленным текстом.

### Тест 2: С локальной LLM

```powershell
python run_sandbox_test.py
```

Отправьте сообщение в тестовый канал - теперь будет использоваться Ollama вместо Gemini!

---

## Устранение проблем

### Ollama не запускается

```powershell
# Проверьте процессы
tasklist | findstr ollama

# Остановите и перезапустите
taskkill /F /IM ollama.exe
ollama serve
```

### Модель не найдена

```powershell
ollama list
```

Если модели нет - повторите импорт из Шага 2.

### Низкая скорость генерации

- Убедитесь что используется GPU: в Ollama логах должно быть "GPU acceleration enabled"
- Попробуйте меньшую модель (3b вместо 20b)
- Увеличьте VRAM лимит в настройках NVIDIA

### Ошибка "Connection refused"

```powershell
# Убедитесь что сервер запущен
ollama serve

# Проверьте порт
netstat -ano | findstr :11434
```

---

## Сравнение производительности

| Провайдер | Скорость | Квота | Оффлайн | Качество |
|-----------|----------|-------|---------|----------|
| **Gemini** | Быстро | 50/день | ❌ | Отлично |
| **Ollama 3B** | Средне | ∞ | ✅ | Хорошо |
| **Ollama 7B** | Медленно | ∞ | ✅ | Отлично |
| **Ollama 20B** | Очень медленно | ∞ | ✅ | Отлично+ |

---

## Рекомендации

1. **Для разработки:** Используйте Ollama
2. **Для продакшена:** Используйте Gemini (или платный API ключ)
3. **Компромисс:** Gemini как основной, Ollama как fallback

### Автоматический fallback

Проект уже настроен для автоматического переключения:
- Если Gemini дает ошибку квоты → автоматически переключится на Ollama
- Если Ollama недоступна → вернется к Gemini

---

## Полезные команды

```powershell
# Список моделей
ollama list

# Удалить модель
ollama rm model_name

# Информация о модели
ollama show model_name

# Логи
ollama logs

# Обновление Ollama
# Скачайте новый установщик с ollama.com
```

---

## Дополнительные ресурсы

- Официальная документация: https://ollama.com/docs
- Библиотека моделей: https://ollama.com/library
- GitHub: https://github.com/ollama/ollama
- Discord сообщество: https://discord.gg/ollama

