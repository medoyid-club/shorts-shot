"""
Генератор видео V2 (HTML + Selenium подход)
Использует HTML шаблоны и Selenium для создания видео с анимациями
"""

import asyncio
import logging
import os
import time
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
import io
import shutil
import subprocess
from typing import Optional, Union
import base64

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger("video_v2")


class VideoComposerV2:
    """Генератор видео через HTML + Selenium"""
    
    def __init__(self, config: dict):
        self.config = config
        v = config['VIDEO']
        
        # Основные параметры
        self.width = int(v.get('width', 1080))
        self.height = int(v.get('height', 1920))
        self.fps = int(v.get('v2_fps', 30))
        self.duration = int(v.get('v2_duration_seconds', 6)) # Убедимся, что по умолчанию 6 секунд
        
        # Пути
        self.template_path = v.get('v2_template_path', 'resources/templates/news_short_v2.html')
        self.temp_dir = config['PATHS'].get('tmp_dir', 'resources/tmp')
        self.outputs_dir = config['PATHS'].get('outputs_dir', 'outputs')
        
        # Настройки захвата
        self.headless = str(v.get('v2_headless', 'true')).lower() == 'true'
        
        # Selenium driver - отложенная инициализация
        self.driver = None
        logger.info(f"🎬 VideoComposerV2 инициализирован: headless={self.headless}")
    
    def _setup_selenium(self):
        """Настройка Selenium WebDriver (отложенная инициализация)"""
        # Проверяем, что браузер существует и сессия активна
        if self.driver:
            try:
                # Проверяем, что сессия еще активна
                _ = self.driver.current_url
                logger.info("✅ Браузер уже инициализирован и активен")
                return
            except Exception:
                # Сессия недействительна, нужно пересоздать
                logger.warning("⚠️ Браузер был закрыт, пересоздаем...")
                self.driver = None
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
                logger.info("🔒 Браузер запускается в фоновом режиме (headless)")
            else:
                logger.warning("⚠️ Браузер запускается в видимом режиме (не headless)")
            
            chrome_options.add_argument(f"--window-size={self.width},{self.height}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--hide-scrollbars")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ Selenium WebDriver инициализирован")
        except ImportError:
            logger.error("❌ Selenium не установлен. Выполните: pip install selenium")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Selenium: {e}")
            raise

    def _preprocess_media(self, media_path: str) -> Optional[str]:
        """Копирует медиафайл во временную папку, обрезает видео до нужной длительности и возвращает его file:// URI."""
        if not media_path or not Path(media_path).exists():
            return None
        
        try:
            temp_media_dir = Path(self.temp_dir)
            temp_media_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(time.time_ns() / 1000)
            ext = Path(media_path).suffix.lower()
            
            # Если это видео, обрезаем его до нужной длительности с перекодированием для точности
            if ext in ['.mp4', '.webm', '.mov']:
                trimmed_filename = f"media_{timestamp}_trimmed{ext}"
                trimmed_path = temp_media_dir / trimmed_filename
                
                # Принудительно перекодируем видео, чтобы гарантировать точную длительность.
                # Это решает проблему ускоренного воспроизведения из-за неточного `copy`.
                # -ss после -i для точного поиска кадра.
                command = [
                    'ffmpeg', '-y',
                    '-i', str(media_path),
                    '-ss', '0',
                    '-t', str(self.duration),
                    '-c:v', 'libx264',       # Перекодируем видео
                    '-preset', 'ultrafast',   # Максимально быстрое кодирование
                    '-c:a', 'aac',           # Перекодируем аудио для совместимости
                    '-avoid_negative_ts', 'make_zero',
                    '-loglevel', 'error',
                    str(trimmed_path)
                ]
                
                try:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                    logger.info(f"✂️ Видео обрезано до {self.duration} секунд (с перекодированием): {trimmed_path}")
                    return trimmed_path.resolve().as_uri()
                except subprocess.CalledProcessError as e:
                    logger.error(f"⚠️ Не удалось обрезать видео с перекодированием: {e.stderr}. Используем оригинал.")
                    # Fallback: если не получилось обрезать, используем оригинал
                    unique_filename = f"media_{timestamp}{ext}"
                    local_path = temp_media_dir / unique_filename
                    shutil.copy2(media_path, local_path)
                    logger.info(f"Медиа скопировано во временную папку: {local_path}")
                    return local_path.resolve().as_uri()
            else:
                # Для изображений просто копируем
                unique_filename = f"media_{timestamp}{ext}"
                local_path = temp_media_dir / unique_filename
                shutil.copy2(media_path, local_path)
                logger.info(f"Медиа скопировано во временную папку: {local_path}")
                return local_path.resolve().as_uri()
            
        except Exception as e:
            logger.error(f"Ошибка обработки медиа: {e}")
            return None

    def _create_html_from_template(self, video_data: dict) -> str:
        """Создает HTML файл из шаблона с подстановкой данных"""
        template_path = Path(self.template_path)
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон не найден: {self.template_path}")

        html_content = template_path.read_text('utf-8')
        
        # Подготовка данных
        title = video_data.get('title', 'Заголовок')
        summary = video_data.get('summary', 'Краткое содержание')
        source_text = video_data.get('source_text', 'Источник')
        
        # Обработка медиа
        media_path = video_data.get('media_path')
        media_uri = self._preprocess_media(media_path)
        
        news_image = ''
        news_video = ''
        if media_uri:
            # Определяем тип по расширению оригинального файла
            ext = Path(media_path).suffix.lower()
            if ext in ['.mp4', '.webm', '.mov']:
                news_video = media_uri
            elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                news_image = media_uri

        # Обработка QR кода
        qr_path = Path(self.config['PATHS'].get('resources_dir', 'resources')) / 'QR' / 'telegram.png'
        qr_uri = ''
        if qr_path.exists():
            qr_uri = qr_path.resolve().as_uri()
        else:
            logger.warning(f"⚠️ QR код не найден: {qr_path}")

        replacements = {
            '{{NEWS_TITLE}}': title,
            '{{NEWS_BRIEF}}': summary.replace('\n', '\\n'), # Экранируем переносы для JS
            '{{NEWS_IMAGE}}': news_image,
            '{{NEWS_VIDEO}}': news_video,
            '{{SOURCE_NAME}}': source_text,
            '{{QR_CODE_PATH}}': qr_uri,
        }

        for placeholder, value in replacements.items():
            html_content = html_content.replace(placeholder, str(value or ''))

        temp_html_path = Path(self.temp_dir) / f"temp_short_{int(time.time())}.html"
        temp_html_path.write_text(html_content, 'utf-8')
        logger.info(f"📄 HTML создан: {temp_html_path}")
        return str(temp_html_path)

    def _sync_media_state(self, frame_time: float) -> bool:
        """
        Синхронизирует видео и анимации на странице на конкретный момент времени.
        Использует execute_async_script для ожидания завершения seek.
        """
        try:
            return self.driver.execute_async_script(
                """
const frameTime = arguments[0];
const callback = arguments[arguments.length - 1];
const clampedTime = Math.max(0, frameTime);

function finalize(success) {
    try {
        let timeline = null;
        if (window.__cinematicTimeline) {
            timeline = window.__cinematicTimeline;
        } else if (window.gsap && window.gsap.globalTimeline) {
            timeline = window.gsap.globalTimeline;
        }

        if (timeline) {
            let total = null;
            const hint = window.__cinematicDuration;
            if (hint && isFinite(hint) && hint > 0) {
                total = hint;
            }

            if (!total && typeof timeline.totalDuration === 'function') {
                const computed = timeline.totalDuration();
                if (isFinite(computed) && computed > 0) {
                    total = computed;
                }
            }

            if (!total && typeof timeline.duration === 'function') {
                const simple = timeline.duration();
                if (isFinite(simple) && simple > 0) {
                    total = simple;
                }
            }

            const target = total && total > 0 ? clampedTime % total : clampedTime;

            if (typeof timeline.pause === 'function') {
                timeline.pause(target);
            } else if (typeof timeline.seek === 'function') {
                timeline.seek(target);
                if (typeof timeline.pause === 'function') {
                    timeline.pause();
                }
            }
        }
    } catch (err) {
        console.error('Timeline sync error', err);
    }
    callback(success);
}

const video = document.getElementById('mediaVideo');
if (!video) {
    finalize(true);
    return;
}

const videoDuration = isFinite(video.duration) && video.duration > 0
    ? Math.max(0, video.duration - 0.032)
    : clampedTime;
const targetTime = Math.min(clampedTime, videoDuration);

const cleanup = () => {
    video.onseeked = null;
    video.onloadeddata = null;
    video.ontimeupdate = null;
};

video.pause();

const seekTimeout = setTimeout(() => {
    cleanup();
    finalize(true);
}, 200);

video.onseeked = () => {
    clearTimeout(seekTimeout);
    cleanup();
    finalize(true);
};

try {
    video.currentTime = targetTime;
    // Принудительно останавливаем воспроизведение
    video.pause();
} catch (err) {
    console.error('Video seek error', err);
    clearTimeout(seekTimeout);
    cleanup();
    finalize(false);
}
                """,
                frame_time,
            )
        except Exception as e:
            logger.debug(f"Не удалось синхронизировать медиа: {e}")
            return False

    def _capture_animation_frames_precise(self) -> list:
        """
        Захватывает кадры с покадровой синхронизацией видео и анимаций.
        """
        num_frames = int(self.duration * self.fps)
        logger.info(f"📹 Захватываем {num_frames} кадров с покадровой синхронизацией...")

        frames = []

        for i in range(num_frames):
            frame_time = min(i / self.fps, self.duration - (1 / self.fps))

            sync_ok = self._sync_media_state(frame_time)
            if not sync_ok:
                logger.debug(f"Frame {i}: синхронизация вернула false, продолжаем.")

            # Небольшая пауза, чтобы страница успела перерисоваться
            time.sleep(0.01)

            try:
                screenshot_data = self.driver.execute_cdp_cmd(
                    "Page.captureScreenshot",
                    {
                        "format": "jpeg",
                        "quality": 95,
                    }
                )
            except Exception:
                # Fallback на обычный скриншот
                screenshot_png = self.driver.get_screenshot_as_png()
                image = Image.open(io.BytesIO(screenshot_png))
                if image.size != (self.width, self.height):
                    image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
                frames.append(np.array(image))
                continue

            jpeg_bytes = base64.b64decode(screenshot_data['data'])
            frame_bgr = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
            if frame_bgr is None:
                logger.error(f"Frame {i}: cv2.imdecode returned None.")
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            if (frame_rgb.shape[1], frame_rgb.shape[0]) != (self.width, self.height):
                frame_rgb = cv2.resize(
                    frame_rgb,
                    (self.width, self.height),
                    interpolation=cv2.INTER_AREA
                )

            frames.append(frame_rgb)

        logger.info(f"✅ Захвачено {len(frames)} кадров")
        return frames


    def _capture_animation_frames(self) -> list:
        """Захватывает кадры анимации из браузера (старый метод)."""
        num_frames = int(self.duration * self.fps)
        logger.info(f"📹 Захватываем {num_frames} кадров...")
        
        frames = []
        for i in range(num_frames):
            screenshot = self.driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            
            if image.size != (self.width, self.height):
                image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
            
            frame_array = np.array(image)
            frames.append(frame_array)
            # Задержка не нужна, т.к. анимации CSS-ные и идут сами по себе
        
        logger.info(f"✅ Захвачено {len(frames)} кадров")
        return frames

    def _export_frames_to_video(self, frames: list, output_path: str):
        """Экспорт кадров в видео файл через OpenCV и FFMPEG для аудио."""
        if not frames:
            logger.error("❌ Нет кадров для экспорта")
            return None
        
        temp_video_path = Path(self.temp_dir) / f"silent_{Path(output_path).name}"
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Более совместимый кодек
        video_writer = cv2.VideoWriter(str(temp_video_path), fourcc, self.fps, (self.width, self.height))
        
        for frame in frames:
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            video_writer.write(bgr_frame)
        video_writer.release()

        music_path = self._get_random_music()
        if music_path:
            logger.info(f"🎵 Добавляем аудио: {music_path}")
            final_video_path = Path(output_path)
            final_video_path.parent.mkdir(parents=True, exist_ok=True)
            
            command = [
                'ffmpeg', '-y',
                '-i', str(temp_video_path),
                '-i', music_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',
                '-loglevel', 'error',
                str(final_video_path)
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                logger.info(f"✅ Видео со звуком создано: {final_video_path}")
                os.remove(temp_video_path)
                return str(final_video_path)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.error(f"❌ Ошибка FFMPEG: {getattr(e, 'stderr', e)}")
                shutil.move(temp_video_path, final_video_path)
                return str(final_video_path)
        else:
            shutil.move(temp_video_path, output_path)
            return output_path

    def _get_random_music(self) -> Optional[str]:
        music_dir = Path(self.config['PATHS'].get('music_dir', 'resources/music'))
        if not music_dir.exists():
            return None
        
        music_files = list(music_dir.glob('*.mp3'))
        return str(np.random.choice(music_files)) if music_files else None

    async def compose(self, short_text: Union[str, dict], media_path: str, output_path: str, source_text: str) -> str:
        logger.info("🎬 Запуск генерации видео V2 (HTML+Selenium)...")
        
        # Инициализируем браузер только когда он действительно нужен
        self._setup_selenium()
        
        if isinstance(short_text, dict):
            title = short_text.get('title', 'Новость')
            summary = short_text.get('brief', title)
        else:
            title = summary = str(short_text)

        video_data = {
            'title': title,
            'summary': summary,
            'media_path': media_path,
            'source_text': source_text,
        }

        temp_html_path = self._create_html_from_template(video_data)
        
        try:
            # Диагностическое логирование для проверки URI
            html_uri = Path(os.path.abspath(temp_html_path)).as_uri()
            logger.info(f"🌐 Загружаем HTML в Selenium: {html_uri}")
            self.driver.get(html_uri)
            
            logger.info("Ожидаем загрузки и отображения медиа в браузере...")
            wait = WebDriverWait(self.driver, 15)  # Ждем до 15 секунд

            media_loaded_successfully = False
            if video_data.get('media_path'):
                ext = Path(video_data['media_path']).suffix.lower()
                element_id = None
                if ext in ['.mp4', '.webm', '.mov']:
                    element_id = "mediaVideo"
                elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    element_id = "mediaImage"

                if element_id:
                    try:
                        wait.until(EC.visibility_of_element_located((By.ID, element_id)))
                        logger.info(f"✅ Медиа-элемент '{element_id}' стал видимым.")
                        media_loaded_successfully = True
                    except Exception:
                        logger.warning(f"⚠️ Элемент '{element_id}' не стал видимым за 15 секунд.")
            
            if not media_loaded_successfully:
                logger.warning("Не удалось дождаться медиа. Захват может быть некорректным.")
            
            # Убираем все ожидания, так как виртуальное время само все синхронизирует.
            # logger.info("⏳ Ожидание загрузки GSAP и выполнения анимаций...")
            # await asyncio.sleep(3) 

            frames = await asyncio.to_thread(self._capture_animation_frames_precise)
            final_path = await asyncio.to_thread(self._export_frames_to_video, frames, output_path)
            
            logger.info(f"✅ Видео V2 создано: {final_path}")
            return final_path
        finally:
            os.remove(temp_html_path)
            # Очистка временных медиа файлов
            for item in Path(self.temp_dir).glob('media_*'):
                item.unlink()
    
    def close(self):
        """Закрывает браузер только если он еще активен"""
        if self.driver:
            try:
                # Проверяем, что сессия еще активна перед закрытием
                _ = self.driver.current_url
                self.driver.quit()
                logger.info("🔒 Selenium WebDriver закрыт")
            except Exception:
                # Браузер уже закрыт, просто очищаем ссылку
                logger.debug("Браузер уже был закрыт")
            finally:
                self.driver = None
    
    def __del__(self):
        """Деструктор - закрываем браузер только при удалении объекта"""
        # Не закрываем браузер в деструкторе, чтобы можно было переиспользовать
        # Браузер закроется автоматически при завершении программы
        pass

