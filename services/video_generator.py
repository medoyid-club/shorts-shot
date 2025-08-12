from __future__ import annotations

import logging
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy import (
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    AudioFileClip,
    concatenate_audioclips,
)
from moviepy.video.fx import Resize

from .storage import random_file

logger = logging.getLogger("video")


class VideoComposer:
    def __init__(self, config: dict):
        self.config = config
        v = config['VIDEO']
        self.width = int(v.get('width', 1080))
        self.height = int(v.get('height', 1920))
        self.duration = int(v.get('duration_seconds', 8))
        self.header_ratio = float(v.get('header_ratio', 0.4))
        self.middle_ratio = float(v.get('middle_ratio', 0.5))
        self.footer_ratio = float(v.get('footer_ratio', 0.1))
        self.middle_bg = config._parsed['VIDEO']['middle_bg_rgb']  # type: ignore[attr-defined]
        self.footer_bg = config._parsed['VIDEO']['footer_bg_rgb']  # type: ignore[attr-defined]
        self.middle_red = config._parsed['VIDEO']['middle_red_rgb']  # type: ignore[attr-defined]
        self.header_zoom_start = float(v.get('header_zoom_start', 1.05))
        self.header_zoom_end = float(v.get('header_zoom_end', 1.00))
        self.heartbeat_enabled = v.get('heartbeat_enabled', 'true').lower() == 'true'
        self.heartbeat_cycle_seconds = float(v.get('heartbeat_cycle_seconds', 1.6))
        self.heartbeat_height_ratio = float(v.get('heartbeat_height_ratio', 0.10))
        self.heartbeat_opacity_main = int(v.get('heartbeat_opacity_main', 180))
        self.heartbeat_opacity_glow = int(v.get('heartbeat_opacity_glow', 80))
        self.heartbeat_opacity_glow2 = int(v.get('heartbeat_opacity_glow2', 40))
        self.font_path = v.get('font_path', 'resources/fonts/Inter_28pt-Bold.ttf')

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_path = Path(self.font_path)
        if font_path.exists():
            try:
                font = ImageFont.truetype(str(font_path), size=size)
                logger.info(f"✅ Шрифт '{font_path}' успешно загружен (размер {size})")
                return font
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки шрифта '{font_path}': {e}", exc_info=True)
        else:
            logger.warning(f"⚠️ Шрифт '{font_path}' не найден.")
        
        logger.warning("Используется стандартный шрифт.")
        return ImageFont.load_default()

    def _make_header_clip(self, media_path: str | None, header_size: Tuple[int, int]):
        w, h = header_size
        logger.info(f"🎬 Обрабатываем медиа: {media_path}, размер заголовка: {w}x{h}")
        
        if media_path and Path(media_path).exists():
            suffix = Path(media_path).suffix.lower()
            logger.info(f"📄 Тип файла: {suffix}")
            
            try:
                if suffix in {'.mp4', '.mov', '.mkv', '.avi', '.webm'}:
                    logger.info("🎥 Обрабатываем видеофайл...")
                    
                    # Загружаем видео без звука
                    video_clip = VideoFileClip(media_path)
                    logger.info(f"📏 Оригинальный размер видео: {video_clip.w}x{video_clip.h}, длительность: {video_clip.duration}")
                    
                    # Убираем звук
                    video_clip = video_clip.without_audio()
                    
                    # Обрезаем до нужной длительности сразу
                    if video_clip.duration > self.duration:
                        video_clip = video_clip.subclipped(0, self.duration)
                    
                    # Масштабируем по высоте
                    if video_clip.h != h:
                        scale_factor = h / video_clip.h
                        new_width = int(video_clip.w * scale_factor)
                        video_clip = video_clip.resized((new_width, h))
                        logger.info(f"🔄 Масштабировали до: {new_width}x{h}")
                    
                    # Обрезаем по ширине (центрируем)
                    if video_clip.w > w:
                        x_center = video_clip.w / 2
                        video_clip = video_clip.cropped(x1=x_center - w/2, x2=x_center + w/2)
                        logger.info(f"✂️ Обрезали до: {w}x{h}")
                    
                    # Устанавливаем нужную длительность
                    final_clip = video_clip.with_duration(self.duration)
                    logger.info("✅ Видео успешно обработано")
                    return self._add_header_effects(final_clip)
                    
                else:
                    logger.info("🖼️ Обрабатываем изображение...")
                    clip = ImageClip(media_path)
                    clip = clip.resized(height=h)
                    # crop center to width
                    x_center = clip.w/2
                    clip = clip.cropped(width=w, height=h, x_center=x_center, y_center=clip.h/2)
                    logger.info("✅ Изображение успешно обработано")
                    return self._add_header_effects(clip.with_duration(self.duration))
                    
            except Exception as e:
                logger.error("❌ Ошибка обработки медиа (%s): %s", media_path, e, exc_info=True)

        # Fallback to random background
        logger.warning("🔄 Используем запасной фон...")
        bg = random_file(self.config['PATHS']['backgrounds_dir'], ('.jpg', '.jpeg', '.png'))
        if bg:
            logger.info(f"🖼️ Используем случайный фон: {bg}")
            try:
                clip = ImageClip(bg).resized(height=h)
                clip = clip.cropped(width=w, height=h, x_center=clip.w/2, y_center=clip.h/2)
                return self._add_header_effects(clip.with_duration(self.duration))
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки фона {bg}: {e}")
        
        # Создаём градиентный fallback вместо чёрного прямоугольника
        logger.warning("🎨 Создаём градиентный фон...")
        try:
            from PIL import Image as PILImage
            # Создаём вертикальный градиент от тёмно-синего к тёмно-серому
            gradient_img = PILImage.new('RGB', (w, h))
            for y in range(h):
                # Интерполируем цвет от тёмно-синего (25, 25, 50) к тёмно-серому (50, 50, 50)
                ratio = y / h
                r = int(25 + (50 - 25) * ratio)
                g = int(25 + (50 - 25) * ratio) 
                b = int(50 + (50 - 50) * ratio)
                for x in range(w):
                    gradient_img.putpixel((x, y), (r, g, b))
            
            gradient_path = Path(self.config['PATHS']['tmp_dir']) / f"gradient_{w}x{h}.png"
            gradient_img.save(gradient_path)
            clip = ImageClip(str(gradient_path))
            logger.info("✅ Градиентный фон создан")
            return self._add_header_effects(clip.with_duration(self.duration))
        except Exception as e:
            logger.error(f"❌ Ошибка создания градиента: {e}")
            # Последний fallback - тёмно-синий вместо чёрного
            logger.warning("🔵 Используем синий фон как последний вариант")
            return self._add_header_effects(ColorClip(size=(w, h), color=(25, 25, 50)).with_duration(self.duration))

    def _render_text_image(self, text: str, size: Tuple[int, int], bg_rgb: tuple[int, int, int]) -> str:
        w, h = size
        # Закрашиваем всю среднюю зону насыщенным красным (как раньше)
        red_bg = tuple(self.middle_red)
        img = Image.new('RGB', (w, h), color=red_bg)
        draw = ImageDraw.Draw(img)

        # Adaptive text layout with readability-first strategy
        font_size = 80
        font = self._load_font(font_size)
        max_width = int(w * 0.86)
        max_height = int(h * 0.78)
        line_spacing = 12
        padding = 40

        def measure(ls: list[str], fnt: ImageFont.ImageFont, spacing: int) -> tuple[int, list[int]]:
            heights = [draw.textbbox((0, 0), L, font=fnt)[3] for L in ls]
            total = sum(heights) + (len(ls) - 1) * spacing
            return total, heights

        # Try to fit by decreasing font size, then spacing, then padding
        while True:
            lines = _wrap_text(draw, text, font, max_width)
            total_height, line_heights = measure(lines, font, line_spacing)
            if total_height <= max_height:
                break
            if font_size > 22:
                font_size -= 2
                font = self._load_font(font_size)
                continue
            if line_spacing > 8:
                line_spacing -= 1
                continue
            if padding > 24:
                padding -= 2
                max_height = int(h - padding * 2)
                continue
            # Если всё ещё не помещается, оставляем исходный текст (без обрезки) и продолжаем с текущими параметрами
            break

        # Рассчитываем размеры текстового блока
        line_heights = []
        max_line_width = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_heights.append(bbox[3])
            max_line_width = max(max_line_width, bbox[2])
        
        total_text_height = sum(line_heights) + (len(lines)-1)*line_spacing
        
        # Рассчитываем область под текст (подложку не рисуем, фон уже красный)
        overlay_width = min(max_line_width + padding*2, w - 40)
        overlay_height = total_text_height + padding*2
        overlay_x = (w - overlay_width) // 2
        overlay_y = (h - overlay_height) // 2
        # Подложку не накладываем, чтобы сохранить ровный красный фон всей зоны
        draw = ImageDraw.Draw(img)
        
        # Рисуем текст с двойной тенью для лучшей читаемости и иллюзии большей жирности
        y = overlay_y + padding
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2]
            x = (w - line_w) // 2
            
            # Двойная тень (2px и 1px) усиливает контраст и визуальную «жирность»
            draw.text((x+2, y+2), line, font=font, fill=(0, 0, 0))
            draw.text((x+1, y+1), line, font=font, fill=(0, 0, 0))
            # Основной текст
            draw.text((x, y), line, font=font, fill=(255, 255, 255))
            y += line_heights[i] + line_spacing

        out_path = Path(self.config['PATHS']['tmp_dir']) / f"middle_{os.getpid()}_{abs(hash(text))}.png"
        img.save(out_path)
        return str(out_path)

    async def _render_animated_text_html(self, text: str, size: Tuple[int, int], bg_rgb: tuple[int, int, int]) -> str:
        """Рендерит анимированный текст через HTML/CSS/JS в видео клип (async Playwright)."""
        w, h = size
        
        try:
            from playwright.async_api import async_playwright
            import numpy as np
            
            # Читаем HTML шаблон
            template_path = Path(self.config['PATHS']['resources_dir']) / 'text_animation_template.html'
            if not template_path.exists():
                logger.warning("HTML шаблон не найден, используем обычный рендеринг")
                return self._render_text_image(text, size, bg_rgb)
            
            html_content = template_path.read_text(encoding='utf-8')
            html_content = html_content.replace('{{TEXT_CONTENT}}', text)
            
            # Временный HTML файл
            temp_html = Path(self.config['PATHS']['tmp_dir']) / f"text_anim_{abs(hash(text))}.html"
            temp_html.write_text(html_content, encoding='utf-8')
            
            # Рендерим кадры анимации
            frames = []
            fps = 30
            animation_duration = 0.6  # длительность анимации в секундах
            total_frames = int(fps * animation_duration)
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={'width': w, 'height': h})
                await page.goto(f"file://{temp_html.absolute()}")

                logger.info(f"🎬 Рендерим {total_frames} кадров анимации...")

                for frame_num in range(total_frames):
                    # Время в миллисекундах для текущего кадра
                    time_ms = int((frame_num / fps) * 1000)

                    # Ждем до нужного момента анимации
                    await page.wait_for_timeout(time_ms if frame_num == 0 else int(1000 / fps))

                    # Делаем скриншот
                    screenshot_bytes = await page.screenshot(type='png')

                    # Конвертируем в numpy array
                    from PIL import Image as PILImage
                    import io
                    img = PILImage.open(io.BytesIO(screenshot_bytes))
                    frame = np.array(img)
                    frames.append(frame)

                await browser.close()
            
            # Удаляем временный HTML
            temp_html.unlink(missing_ok=True)
            
            # Создаем видео клип из кадров
            from moviepy import ImageSequenceClip
            clip = ImageSequenceClip(frames, fps=fps)

            # Сохраняем как видео (в отдельном потоке, чтобы не блокировать event loop)
            out_path = Path(self.config['PATHS']['tmp_dir']) / f"text_anim_{abs(hash(text))}.mp4"
            await asyncio.to_thread(
                clip.write_videofile,
                str(out_path),
                codec='libx264',
                audio=False,
            )
            
            logger.info("✅ HTML анимация отрендерена в видео")
            return str(out_path)
            
        except ImportError:
            logger.warning("Playwright не установлен, используем обычный рендеринг")
            return self._render_text_image(text, size, bg_rgb)
        except Exception as e:
            logger.error("❌ Ошибка HTML рендеринга: %s", e)
            return self._render_text_image(text, size, bg_rgb)

    def _render_footer_image(self, left_text: str, right_text: str, size: Tuple[int, int], bg_rgb: tuple[int, int, int]) -> str:
        w, h = size
        img = Image.new('RGB', (w, h), color=bg_rgb)
        draw = ImageDraw.Draw(img)
        font = self._load_font(36)

        # Left text
        draw.text((int(w*0.03), int(h*0.2)), left_text, font=font, fill=(255,255,255))
        # Right text
        right_bbox = draw.textbbox((0,0), right_text, font=font)
        rx = w - right_bbox[2] - int(w*0.03)
        draw.text((rx, int(h*0.2)), right_text, font=font, fill=(255,255,255))

        out_path = Path(self.config['PATHS']['tmp_dir']) / f"footer_{os.getpid()}_{abs(hash(left_text+right_text))}.png"
        img.save(out_path)
        return str(out_path)

    def _add_header_effects(self, clip):
        """Добавляет эффект зума (Ken Burns light) к шапке.

        Используем time-based resize: от 1.05 к 1.00 равномерно за всю длительность ролика.
        Это гарантированно видно, даже если позиционирование позже задаётся статически.
        """
        logger.info("🎬 Применяем эффект: zoom_in для header (time-based resize)")

        def zoom_resize(t: float) -> float:
            progress = 0.0 if self.duration <= 0 else min(max(t / self.duration, 0.0), 1.0)
            return self.header_zoom_start + (self.header_zoom_end - self.header_zoom_start) * progress

        return clip.resized(zoom_resize)

    def _add_text_effects(self, clip):
        """Добавляет эффект масштабирования к текстовому клипу."""
        logger.info("🎬 Применяем эффект: slide_in для текста")
        
        # Простой эффект въезда справа за первые 0.6 секунды
        def animate_text_position(t):
            if t < 0.6:
                # Движение справа к центру
                progress = t / 0.6
                offset_x = int(50 * (1 - progress))  # от 50 до 0 пикселей
                return (offset_x, 0)
            return (0, 0)
        
        return clip.with_position(animate_text_position)

    def _make_heartbeat_overlay(self, width: int, height: int):
        """Генерирует клип с имитацией диаграммы биения сердца поверх средней зоны.

        Рисуем весь слой кадр-за-кадром, чтобы легко управлять прозрачностью и формой
        без анимации opacity-функциями MoviePy.
        """
        baseline_y = height // 2
        amplitude = int(height * 0.35)
        period_px = max(20, int(width * 0.22))
        speed_px_per_s = width / max(0.2, self.heartbeat_cycle_seconds)

        def shape(u: float) -> float:
            # Форма удара: высокий пик + небольшой последующий импульс
            if u < 0.06:
                return u / 0.06
            if u < 0.12:
                return 1.0 - (u - 0.06) / 0.06
            if u < 0.20:
                return 0.4 * (1.0 - (u - 0.12) / 0.08)
            return 0.0

        # Готовим кадры на всю длительность
        fps = 30
        total_frames = max(1, int(self.duration * fps))
        frames: list[np.ndarray] = []

        for i in range(total_frames):
            t = i / fps
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img, 'RGBA')

            env = np.sin(np.pi * (t / max(self.duration, 0.001))) ** 2
            alpha_main = int(self.heartbeat_opacity_main * env)
            alpha_glow = int(self.heartbeat_opacity_glow * env)
            alpha_glow2 = int(self.heartbeat_opacity_glow2 * env)

            draw.line([(0, baseline_y), (width, baseline_y)], fill=(255, 255, 255, int(50 * env)), width=1)

            offset = int((t * speed_px_per_s) % period_px)
            pts = []
            step = 3
            for x in range(0, width, step):
                u = ((x + offset) % period_px) / period_px
                y = baseline_y - int(amplitude * shape(u))
                pts.append((x, y))

            if len(pts) >= 2:
                draw.line(pts, fill=(255, 255, 255, alpha_glow2), width=11)
                draw.line(pts, fill=(255, 255, 255, alpha_glow), width=7)
                draw.line(pts, fill=(255, 255, 255, alpha_main), width=3)

            frames.append(np.array(img))

        from moviepy import ImageSequenceClip
        return ImageSequenceClip(frames, fps=fps)

    async def compose(self, short_text: str, header_media_path: str | None, output_path: str, source_text: str) -> str:
        header_h = int(self.height * self.header_ratio)
        middle_h = int(self.height * self.middle_ratio)
        footer_h = self.height - header_h - middle_h

        header_clip = self._make_header_clip(header_media_path, (self.width, header_h))

        # Рендерим статическое изображение текста для максимальной читабельности
        # (HTML-анимацию можно включить позже флагом настройки)
        middle_path = self._render_text_image(short_text, (self.width, middle_h), self.middle_bg)

        # Используем статичное изображение без анимации для лучшей читабельности
        logger.info("🧩 Текст статичен (max readability)")
        middle_clip = ImageClip(middle_path).with_duration(self.duration)

        date_str = datetime.now().strftime('%d.%m.%Y')
        footer_img = self._render_footer_image(date_str, source_text, (self.width, footer_h), self.footer_bg)
        footer_clip = ImageClip(footer_img).with_duration(self.duration)

        base = ColorClip(size=(self.width, self.height), color=(0, 0, 0)).with_duration(self.duration)
        # Имитация диаграммы «сердечного удара» в верхней части красной зоны
        margin_x = int(self.width * 0.10)
        rail_width = self.width - 2 * margin_x
        rail_y = header_h + int(middle_h * 0.08)
        rail_clip = ColorClip(size=(rail_width, 2), color=(255, 255, 255)).with_duration(self.duration).with_opacity(0.22)
        rail_clip = rail_clip.with_position((margin_x, rail_y))

        # Кадровая анимация сердца (включается по конфигу)
        hb_height = max(20, int(middle_h * self.heartbeat_height_ratio))
        heartbeat_clip = None
        if self.heartbeat_enabled:
            heartbeat_clip = self._make_heartbeat_overlay(rail_width, hb_height)
            heartbeat_clip = heartbeat_clip.with_position((margin_x, rail_y - hb_height // 2 + 1))

        composed = CompositeVideoClip([
            base,
            header_clip.with_position((0, 0)),
            middle_clip.with_position((0, header_h)),
            rail_clip,
            *( [heartbeat_clip] if heartbeat_clip is not None else [] ),
            footer_clip.with_position((0, header_h + middle_h)),
        ], size=(self.width, self.height))

        # Audio
        music = random_file(self.config['PATHS']['music_dir'], ('.mp3', '.wav', '.m4a', '.aac'))
        if music:
            try:
                audio_clip = AudioFileClip(music)
                audio_duration = audio_clip.duration
                logger.info("🎵 Аудио файл: %s, длительность: %.2f сек, нужно: %.2f сек", 
                           Path(music).name, audio_duration, self.duration)
                
                if audio_duration >= self.duration:
                    # Аудио достаточно длинное - обрезаем
                    audio = audio_clip.subclipped(0, self.duration)
                    logger.info("✂️ Обрезали аудио до %.2f секунд", self.duration)
                else:
                    # Аудио короткое - зацикливаем
                    loops_needed = int(self.duration / audio_duration) + 1
                    audio_clips = [audio_clip] * loops_needed
                    audio = concatenate_audioclips(audio_clips).subclipped(0, self.duration)
                    logger.info("🔁 Зациклили аудио %d раз для %.2f секунд", loops_needed, self.duration)
                
                composed = composed.with_audio(audio)
            except Exception as e:
                logger.warning("Failed to attach audio: %s", e)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            composed.write_videofile,
            str(out),
            fps=30,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            threads=os.cpu_count() or 2,
        )
        return str(out)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.strip().split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = (" ".join(current + [word])).strip()
        w = draw.textbbox((0,0), trial, font=font)[2]
        if w <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines

