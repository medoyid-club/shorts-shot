# 🎬 Гайд: Генерация видео шортов через HTML, JavaScript и Selenium

## 📋 Содержание
1. [Общая концепция](#общая-концепция)
2. [Архитектура системы](#архитектура-системы)
3. [HTML шаблон](#html-шаблон)
4. [Python: Подготовка данных](#python-подготовка-данных)
5. [Selenium: Рендеринг и захват кадров](#selenium-рендеринг-и-захват-кадров)
6. [Сборка видео](#сборка-видео)
7. [Полный пример кода](#полный-пример-кода)

---

## 🎯 Общая концепция

### Как это работает?

```
[Данные новости] → [HTML шаблон] → [Selenium WebDriver] → [Захват кадров] → [Видео файл]
```

**Процесс в деталях:**

1. **Создаем HTML-страницу** с анимациями, стилями и медиа-контентом
2. **Открываем в headless Chrome** через Selenium WebDriver
3. **Захватываем кадры** (скриншоты) с определенной частотой (FPS)
4. **Собираем кадры в видео** с помощью OpenCV
5. **Добавляем аудио** через ffmpeg

---

## 🏗️ Архитектура системы

```python
VideoExporter (класс)
├── HTML Template Generator    # Создает HTML из шаблона
├── Selenium WebDriver         # Рендерит HTML в браузере
├── Frame Capture Engine       # Захватывает кадры
└── Video Assembler           # Собирает кадры + аудио
```

---

## 📄 HTML шаблон

### Структура шаблона

HTML шаблон содержит:
- **Плейсхолдеры** для динамических данных: `{{NEWS_TITLE}}`, `{{NEWS_IMAGE}}` и т.д.
- **CSS стили** для визуального оформления (градиенты, тени, анимации)
- **JavaScript** для инициализации медиа, адаптации текста и анимаций
- **GSAP** (GreenSock Animation Platform) для плавных анимаций

### Пример базовой структуры

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>News Short</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@700&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
    <style>
        body {
            margin: 0;
            font-family: 'Roboto', sans-serif;
            background-color: #050a1a;
        }
        
        .container {
            width: 1080px;    /* Ширина shorts видео */
            height: 1920px;   /* Высота shorts видео (9:16) */
            position: relative;
            background: #050a1a;
            overflow: hidden;
        }
        
        /* Анимированный кибер-фон */
        .cyber-grid {
            position: absolute;
            width: 100%;
            height: 100%;
            background: repeating-linear-gradient(
                0deg,
                rgba(0, 255, 255, 0.05) 0px,
                rgba(0, 255, 255, 0.05) 1px,
                transparent 1px,
                transparent 20px
            );
            animation: grid-move 2s linear infinite;
        }
        
        @keyframes grid-move {
            0% { background-position: 0 0; }
            100% { background-position: 40px 40px; }
        }
        
        /* Карточка новости */
        .news-card {
            background: rgba(0, 255, 255, 0.05);
            border: 1px solid rgba(0, 255, 255, 0.2);
            padding: 80px;
            color: #00ffff;
            text-shadow: 0 0 15px rgba(0, 255, 255, 0.6);
        }
        
        .news-card-title {
            font-family: 'Oswald', sans-serif;
            font-size: 72px;
            font-weight: 700;
            color: #00ffff;
            line-height: 1.2;
        }
        
        .news-card-description {
            font-size: 36px;
            color: rgba(0, 255, 255, 0.9);
            line-height: 1.4;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="cyber-grid"></div>
        <div class="news-card">
            <!-- Футер с логотипом источника -->
            <div class="news-card-footer">
                <img src="{{TWITTER_AVATAR}}" alt="Avatar" class="source-logo">
                <div class="source-text">{{SOURCE_NAME}}</div>
                <div class="date-time">{{PUBLISH_DATE}}</div>
            </div>
            
            <!-- Заголовок -->
            <div id="newsText" class="news-card-title">{{NEWS_TITLE}}</div>
            
            <!-- Описание -->
            <div id="newsBrief" class="news-card-description">{{NEWS_BRIEF}}</div>
            
            <!-- Медиа (видео или изображение) -->
            <div class="news-card-media">
                <img id="newsCardImage" src="{{NEWS_IMAGE}}" style="display: none;">
                <video id="newsCardVideo" style="display: none;">
                    <source src="{{NEWS_VIDEO}}" type="video/mp4">
                </video>
            </div>
        </div>
    </div>
    
    <script>
        // Адаптация размера шрифта под длину текста
        function adjustFontSize() {
            const newsText = document.getElementById('newsText');
            const titleLength = newsText.textContent.length;
            
            let titleFontSize = 48;
            if (titleLength > 60) titleFontSize = 36;
            else if (titleLength > 40) titleFontSize = 42;
            
            newsText.style.fontSize = titleFontSize + 'px';
        }
        
        // Инициализация медиа (показываем видео или изображение)
        function initializeCardMedia() {
            const cardImage = document.getElementById('newsCardImage');
            const cardVideo = document.getElementById('newsCardVideo');
            const videoSource = cardVideo.querySelector('source');
            
            const hasVideo = videoSource && videoSource.src && 
                            !videoSource.src.includes('{{NEWS_VIDEO}}');
            const hasImage = cardImage && cardImage.src && 
                            !cardImage.src.includes('{{NEWS_IMAGE}}');
            
            if (hasVideo) {
                cardVideo.style.display = 'block';
                cardVideo.play().catch(e => {});
            } else if (hasImage) {
                cardImage.style.display = 'block';
            }
        }
        
        // Запускаем при загрузке страницы
        document.addEventListener('DOMContentLoaded', () => {
            adjustFontSize();
            initializeCardMedia();
        });
    </script>
</body>
</html>
```

### Ключевые особенности шаблона

1. **Фиксированные размеры контейнера**: 1080x1920px (формат 9:16 для вертикальных shorts)
2. **Плейсхолдеры**: `{{VARIABLE_NAME}}` - заменяются Python кодом
3. **CSS анимации**: `@keyframes` для фонового движения, `animation` для эффектов
4. **JavaScript адаптация**: динамическое изменение размера шрифта
5. **Медиа поддержка**: как `<img>`, так и `<video>` элементы

---

## 🐍 Python: Подготовка данных

### Класс VideoExporter

```python
import os
import time
import cv2
import numpy as np
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import io

class VideoExporter:
    def __init__(self, video_config: dict, paths_config: dict):
        self.video_config = video_config  # FPS, размеры, длительность
        self.paths_config = paths_config  # Пути к папкам
        self.driver = None
        self._setup_selenium()
    
    def _setup_selenium(self):
        """Настройка Selenium WebDriver для headless режима"""
        chrome_options = Options()
        
        # Headless режим (без видимого окна браузера)
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        # Устанавливаем размер окна = размеру видео
        width = self.video_config['width']   # 1080
        height = self.video_config['height'] # 1920
        chrome_options.add_argument(f"--window-size={width},{height}")
        
        # Отключаем лишние компоненты для ускорения
        chrome_options.add_argument("--hide-scrollbars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        print("✅ Selenium WebDriver инициализирован")
```

### Генерация HTML из шаблона

```python
def _create_news_short_html(self, video_package: dict) -> str:
    """Создает HTML файл с подстановкой данных"""
    
    # Читаем шаблон
    template_path = os.path.join(
        self.paths_config['templates_dir'], 
        'news_short_template.html'
    )
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    # Подготавливаем данные
    content = video_package.get('video_content', {})
    source_info = video_package.get('source_info', {})
    media = video_package.get('media', {})
    
    # Определяем пути к медиа файлам (относительные для HTML)
    def to_relative_path(path):
        if not path or not os.path.exists(path):
            return ''
        return '../' + path.replace('\\', '/')
    
    # Выбираем видео или изображение
    news_image_path = ''
    news_video_path = ''
    
    if media.get('has_video') and media.get('local_video_path'):
        news_video_path = to_relative_path(media.get('local_video_path'))
    elif media.get('has_images') and media.get('local_image_path'):
        news_image_path = to_relative_path(media.get('local_image_path'))
    
    # Словарь замен
    replacements = {
        '{{NEWS_IMAGE}}': news_image_path,
        '{{NEWS_VIDEO}}': news_video_path,
        '{{TWITTER_AVATAR}}': to_relative_path(source_info.get('avatar_path', '')),
        '{{SOURCE_NAME}}': source_info.get('name', 'News'),
        '{{NEWS_TITLE}}': content.get('title', 'News Title'),
        '{{NEWS_BRIEF}}': content.get('summary', 'News summary'),
        '{{PUBLISH_DATE}}': source_info.get('publish_date', 'Today'),
    }
    
    # Заменяем плейсхолдеры
    html_content = template_content
    for placeholder, value in replacements.items():
        html_content = html_content.replace(placeholder, str(value or ''))
    
    # Сохраняем временный HTML файл
    temp_html_path = os.path.join(
        self.paths_config.get('temp_dir', 'temp'), 
        f"news_short_{int(time.time())}.html"
    )
    with open(temp_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return temp_html_path
```

### Обработка видео с помощью ffmpeg

Если исходное видео слишком длинное, обрезаем его:

```python
def _trim_video_with_ffmpeg(self, video_path: str, offset: float, duration: float) -> str:
    """Обрезка видео с помощью ffmpeg"""
    import subprocess
    
    output_path = f"temp/trimmed_{Path(video_path).stem}_{int(time.time())}.mp4"
    
    command = [
        'ffmpeg',
        '-ss', str(offset),         # Начальная позиция
        '-i', video_path,            # Входной файл
        '-t', str(duration),         # Длительность
        '-c', 'copy',                # Копируем без перекодирования
        '-y',                        # Перезаписываем без запроса
        output_path
    ]
    
    subprocess.run(command, check=True, capture_output=True)
    print(f"✅ Видео обрезано: {output_path}")
    return output_path
```

---

## 🔍 Selenium: Рендеринг и захват кадров

### Открытие HTML в браузере

```python
def create_news_short_video(self, video_package: dict, output_path: str) -> str:
    """Создает видео из HTML шаблона"""
    
    # 1. Создаем HTML файл
    temp_html_path = self._create_news_short_html(video_package)
    
    # 2. Открываем в Selenium
    temp_html_uri = Path(os.path.abspath(temp_html_path)).as_uri()
    self.driver.get(temp_html_uri)
    
    # 3. Ждем загрузки всех ресурсов (шрифты, изображения, видео)
    time.sleep(3)
    
    # 4. Захватываем кадры
    frames = self._capture_animation_frames()
    
    # 5. Собираем видео
    music_path = self._get_background_music()
    self._export_frames_to_video(frames, output_path, music_path)
    
    # 6. Очистка
    os.remove(temp_html_path)
    
    return output_path
```

### Захват кадров

**Метод 1: Захват всех кадров последовательно**

```python
def _capture_animation_frames(self) -> list:
    """Захватывает кадры анимации"""
    
    fps = self.video_config.get('fps', 30)              # Кадров в секунду
    duration = self.video_config.get('duration_seconds', 59)  # Длительность видео
    num_frames = int(duration * fps)                    # Всего кадров
    
    print(f"📹 Захватываем {num_frames} кадров (FPS: {fps}, длительность: {duration}с)")
    
    frames = []
    
    for i in range(num_frames):
        # Делаем скриншот через Selenium
        screenshot = self.driver.get_screenshot_as_png()
        
        # Конвертируем в PIL Image
        image = Image.open(io.BytesIO(screenshot))
        
        # Проверяем/изменяем размер если нужно
        target_size = (self.video_config['width'], self.video_config['height'])
        if image.size != target_size:
            image = image.resize(target_size)
        
        # Конвертируем в numpy array для OpenCV
        frames.append(np.array(image))
        
        # Небольшая задержка между кадрами
        time.sleep(1 / fps)
    
    print(f"✅ Захвачено {len(frames)} кадров")
    return frames
```

**Метод 2: Синхронизация с видео внутри HTML**

Если внутри HTML есть `<video>` элемент, нужно синхронизировать захват кадров с видео:

```python
def _capture_animation_frames_with_video_sync(self) -> list:
    """Захват кадров с точной синхронизацией видео"""
    
    fps = self.video_config.get('fps', 30)
    duration = self.video_config.get('duration_seconds', 59)
    num_frames = int(duration * fps)
    
    # Ставим видео на паузу для ручного управления
    self.driver.execute_script(
        "document.getElementById('newsCardVideo').pause();"
    )
    
    frames = []
    
    for i in range(num_frames):
        # Вычисляем точное время для текущего кадра
        current_time = i / fps
        
        # Устанавливаем время видео через JavaScript
        self.driver.execute_script(f"""
            const video = document.getElementById('newsCardVideo');
            video.currentTime = {current_time};
        """)
        
        # Небольшая пауза для отрисовки кадра
        time.sleep(1 / (fps * 2))
        
        # Делаем скриншот
        screenshot = self.driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))
        
        # Проверяем размер
        if image.size != (self.video_config['width'], self.video_config['height']):
            image = image.resize((self.video_config['width'], self.video_config['height']))
        
        frames.append(np.array(image))
    
    print(f"✅ Захвачено {len(frames)} кадров с видео-синхронизацией")
    return frames
```

---

## 🎞️ Сборка видео

### Создание видео из кадров (OpenCV)

```python
def _export_frames_to_video(self, frames: list, output_path: str, music_path: str = None):
    """Экспорт кадров в видео файл"""
    
    if not frames:
        print("❌ Нет кадров для экспорта")
        return
    
    height, width, layers = frames[0].shape
    fps = self.video_config.get('fps', 30)
    
    # Кодек для MP4
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    # Если есть музыка, сначала создаем видео без звука
    silent_video_path = output_path
    if music_path and os.path.exists(music_path):
        silent_video_path = output_path.replace('.mp4', '_silent.mp4')
    
    # Создаем видео
    video_writer = cv2.VideoWriter(
        silent_video_path, 
        fourcc, 
        fps, 
        (width, height)
    )
    
    # Записываем кадры
    for i, frame in enumerate(frames):
        # Конвертируем из RGB в BGR (OpenCV использует BGR)
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video_writer.write(bgr_frame)
        
        if (i + 1) % 100 == 0:
            print(f"📝 Записано {i + 1}/{len(frames)} кадров")
    
    video_writer.release()
    print(f"✅ Видео создано: {silent_video_path}")
    
    # Добавляем аудио с помощью ffmpeg
    if music_path and os.path.exists(music_path):
        self._add_audio_to_video(silent_video_path, music_path, output_path)
        os.remove(silent_video_path)  # Удаляем видео без звука
```

### Добавление аудио (ffmpeg)

```python
def _add_audio_to_video(self, video_path: str, audio_path: str, output_path: str):
    """Добавляет аудиодорожку к видео"""
    import subprocess
    
    command = [
        'ffmpeg',
        '-y',                    # Перезаписываем без запроса
        '-i', video_path,        # Входное видео
        '-i', audio_path,        # Входное аудио
        '-c:v', 'copy',          # Копируем видео без перекодирования
        '-c:a', 'aac',           # Кодируем аудио в AAC
        '-shortest',             # Длительность = минимум из видео/аудио
        '-loglevel', 'error',    # Скрываем лишние логи
        output_path
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"✅ Аудиодорожка добавлена: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка ffmpeg: {e.stderr}")
        # Оставляем видео без звука
        if video_path != output_path:
            os.rename(video_path, output_path)
```

---

## 💻 Полный пример кода

### Минимальный рабочий пример

```python
#!/usr/bin/env python3
import os
import time
import cv2
import numpy as np
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import io

class SimpleVideoGenerator:
    """Простая генерация видео из HTML"""
    
    def __init__(self):
        self.width = 1080
        self.height = 1920
        self.fps = 30
        self.duration = 10  # секунд
        self.driver = None
        self._setup_browser()
    
    def _setup_browser(self):
        """Настройка headless браузера"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument(f"--window-size={self.width},{self.height}")
        self.driver = webdriver.Chrome(options=options)
    
    def create_video(self, html_content: str, output_path: str):
        """Создает видео из HTML контента"""
        
        # 1. Сохраняем HTML во временный файл
        temp_html = f"temp_{int(time.time())}.html"
        with open(temp_html, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # 2. Открываем в браузере
        html_uri = Path(os.path.abspath(temp_html)).as_uri()
        self.driver.get(html_uri)
        time.sleep(2)  # Ждем загрузки
        
        # 3. Захватываем кадры
        num_frames = self.duration * self.fps
        frames = []
        
        print(f"📹 Захватываю {num_frames} кадров...")
        for i in range(num_frames):
            screenshot = self.driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            frames.append(np.array(image))
            time.sleep(1 / self.fps)
        
        # 4. Создаем видео
        print(f"🎬 Создаю видео...")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(output_path, fourcc, self.fps, (self.width, self.height))
        
        for frame in frames:
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            video.write(bgr_frame)
        
        video.release()
        
        # 5. Очистка
        os.remove(temp_html)
        print(f"✅ Видео создано: {output_path}")
    
    def close(self):
        if self.driver:
            self.driver.quit()

# Использование
if __name__ == "__main__":
    # HTML контент с анимацией
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                height: 1920px;
                width: 1080px;
            }
            
            .title {
                font-family: Arial, sans-serif;
                font-size: 80px;
                color: white;
                text-align: center;
                animation: pulse 2s ease-in-out infinite;
            }
            
            @keyframes pulse {
                0%, 100% { transform: scale(1); opacity: 1; }
                50% { transform: scale(1.1); opacity: 0.8; }
            }
        </style>
    </head>
    <body>
        <div class="title">Hello World!</div>
    </body>
    </html>
    """
    
    generator = SimpleVideoGenerator()
    generator.create_video(html_content, "output.mp4")
    generator.close()
```

---

## 🎓 Ключевые концепции

### 1. Почему HTML + Selenium?

**Преимущества:**
- ✅ **Легко создавать визуальные эффекты** - используем CSS и JavaScript
- ✅ **WYSIWYG** - что видишь в браузере, то и будет в видео
- ✅ **Поддержка веб-технологий** - градиенты, тени, шрифты, анимации
- ✅ **Гибкость** - легко менять дизайн, не трогая Python код

**Недостатки:**
- ⚠️ Медленнее чем прямой рендеринг
- ⚠️ Требует headless браузер
- ⚠️ Больше зависимостей

### 2. Частота кадров (FPS)

```python
fps = 30  # Кадров в секунду

# Для плавного видео: 30-60 FPS
# Для экономии ресурсов: 24 FPS
# Для быстрой генерации: 15-20 FPS
```

### 3. Синхронизация времени

Для анимаций важно правильно управлять временем:

```javascript
// В HTML: CSS анимация длится 5 секунд
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.element { animation: pulse 5s infinite; }
```

```python
# В Python: захватываем видео 5 секунд
duration = 5
num_frames = duration * fps
```

### 4. Оптимизация производительности

```python
# Плохо: создаем новый driver для каждого видео
def create_video():
    driver = webdriver.Chrome()
    # ... создание видео
    driver.quit()

# Хорошо: переиспользуем driver
class VideoGenerator:
    def __init__(self):
        self.driver = webdriver.Chrome()  # Создаем один раз
    
    def create_video(self, data):
        # ... используем self.driver
    
    def __del__(self):
        self.driver.quit()  # Закрываем в конце
```

---

## 🛠️ Требования и установка

### Python библиотеки

```bash
pip install selenium opencv-python pillow numpy
```

### Дополнительное ПО

```bash
# Chrome WebDriver
# Скачайте версию под вашу версию Chrome:
# https://chromedriver.chromium.org/

# ffmpeg (для аудио)
# Windows: https://ffmpeg.org/download.html
# Linux: sudo apt install ffmpeg
# macOS: brew install ffmpeg
```

---

## 🎨 Советы по дизайну

### 1. Используйте контрастные цвета
```css
/* Хорошо читается */
.text {
    color: #ffffff;
    background: #000000;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
}
```

### 2. Адаптируйте размер текста
```javascript
function adjustFontSize(text, maxLength) {
    let fontSize = 72;
    if (text.length > 100) fontSize = 48;
    else if (text.length > 60) fontSize = 60;
    return fontSize;
}
```

### 3. Используйте безопасные шрифты
```html
<!-- Google Fonts - загружаются надежно -->
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
```

---

## 🐛 Типичные проблемы и решения

### Проблема 1: Белый экран вместо контента

**Причина:** Контент не успел загрузиться

**Решение:**
```python
self.driver.get(html_uri)
time.sleep(3)  # Увеличьте время ожидания

# Или используйте явное ожидание
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

wait = WebDriverWait(self.driver, 10)
wait.until(lambda d: d.find_element(By.CLASS_NAME, "container"))
```

### Проблема 2: Размер видео не совпадает с ожидаемым

**Решение:**
```python
# Проверяйте и изменяйте размер каждого кадра
screenshot = self.driver.get_screenshot_as_png()
image = Image.open(io.BytesIO(screenshot))

target_size = (1080, 1920)
if image.size != target_size:
    image = image.resize(target_size, Image.Resampling.LANCZOS)
```

### Проблема 3: Видео внутри HTML не синхронизировано

**Решение:** Управляйте временем видео через JavaScript
```python
for i in range(num_frames):
    current_time = i / fps
    self.driver.execute_script(f"document.getElementById('video').currentTime = {current_time};")
    time.sleep(0.05)  # Даем время на отрисовку
    # ... делаем скриншот
```

---

## 📊 Производительность

### Примерное время генерации

| Длительность видео | FPS | Количество кадров | Время генерации |
|-------------------|-----|-------------------|-----------------|
| 10 секунд         | 30  | 300               | ~30 секунд      |
| 30 секунд         | 30  | 900               | ~90 секунд      |
| 60 секунд         | 30  | 1800              | ~3 минуты       |

### Факторы, влияющие на скорость:

- ⚡ **FPS** - чем выше, тем дольше
- ⚡ **Разрешение** - 1080x1920 медленнее чем 720x1280
- ⚡ **Сложность HTML** - много анимаций = медленнее
- ⚡ **Загрузка медиа** - внешние изображения/видео

---

## 🚀 Расширенные возможности

### Добавление прогресс-бара

```python
from tqdm import tqdm

frames = []
for i in tqdm(range(num_frames), desc="Захват кадров"):
    screenshot = self.driver.get_screenshot_as_png()
    image = Image.open(io.BytesIO(screenshot))
    frames.append(np.array(image))
```

### Параллельная обработка

```python
from concurrent.futures import ThreadPoolExecutor

def capture_frame(driver, i, fps):
    time.sleep(i / fps)
    return driver.get_screenshot_as_png()

# Внимание: WebDriver не thread-safe, нужны отдельные экземпляры
```

### Динамические эффекты через GSAP

```javascript
// В HTML шаблоне
gsap.to(".title", {
    duration: 2,
    x: 100,
    rotation: 360,
    ease: "power2.inOut"
});
```

---

## 📝 Заключение

Генерация видео через HTML + Selenium - это мощный и гибкий подход, который позволяет:

1. ✅ Использовать веб-технологии для дизайна
2. ✅ Быстро итерировать и тестировать внешний вид
3. ✅ Создавать сложные анимации без глубоких знаний видео-рендеринга
4. ✅ Легко масштабировать и автоматизировать

**Ключевая идея:** Браузер становится вашим видео-рендером! 🎬

---

## 📚 Дополнительные ресурсы

- [Selenium Documentation](https://www.selenium.dev/documentation/)
- [OpenCV Video I/O](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html)
- [GSAP Animation](https://greensock.com/gsap/)
- [CSS Animations](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Animations)

---

*Документ создан на основе реального проекта генерации новостных shorts видео*

