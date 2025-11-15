"""
LLM Provider V2 - промпты для нового дизайна (HTML+Selenium)
Адаптирован под формат новостных шортсов с заголовком и кратким описанием
"""

import asyncio
import logging
import os
from typing import Any, Dict

import google.generativeai as genai

logger = logging.getLogger("llm_v2")


class GeminiProviderV2:
    """Gemini провайдер для генерации новостного контента (V2)"""
    
    def __init__(self, api_key: str, model: str = 'gemini-1.5-flash'):
        self.api_key = api_key
        self.model = model
        # Системная инструкция: украинский копирайтер с живым тоном
        self.system_instruction = (
            """
Ти — український креативний копірайтер та редактор новин для YouTube Shorts.
Пиши живо і розмовно, але відповідально: короткі фрази, активний стан, чітка логіка.
Стиль: динамічний, енергійний, без канцеляриту, без кліше, без емоційних ярликів.
Мова: лише українська (сучасна, природна). Уникай русизмів.
Факти — першочергово; жодної вигадки. Жодних емодзі/хештегів/посилань у заголовках або описах, якщо явно не вимагається.
Форматуй текст для ритму читання у шортсах: короткі речення, мікроабзаци, зрозумілі паузи.
            """
        ).strip()
        
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        
        # Настраиваем API ключ для google-generativeai
        genai.configure(api_key=self.api_key)
        
        logger.info(f"🤖 GeminiProviderV2 инициализирован: {model}")
    
    async def _generate(self, prompt: str) -> str:
        """Базовая генерация"""
        try:
            logger.info("📡 Отправляем запрос к Gemini API...")
            
            # Создаем модель и генерируем контент (с системной инструкцией)
            model_instance = genai.GenerativeModel(
                self.model,
                system_instruction=self.system_instruction
            )
            
            # Выполняем генерацию в отдельном потоке
            response = await asyncio.to_thread(
                model_instance.generate_content,
                prompt
            )
            
            # Получаем текст из ответа
            result = response.text if hasattr(response, 'text') else str(response)
            logger.info("✅ Получен ответ от Gemini API")
            return result.strip()
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            raise
    
    def _template_path(self) -> str:
        """Возвращает путь к общему шаблону промпта."""
        from pathlib import Path
        return str((Path(__file__).resolve().parent.parent / 'resources' / 'prompts' / 'news_package_en.prompt'))

    def _render_template(self, source_text: str, source_name: str = "Unknown", source_url: str = "") -> str:
        """Подставляет данные в шаблон {{PLACEHOLDER}} без конфликтов с фигурными скобками JSON."""
        path = self._template_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                template = f.read()
        except Exception as e:
            logger.error(f"Не удалось прочитать шаблон промпта: {path} ({e})")
            raise

        mapping = {
            '{{SOURCE_TEXT}}': source_text,
            '{{SOURCE_NAME}}': source_name,
            '{{SOURCE_URL}}': source_url,
        }
        for k, v in mapping.items():
            template = template.replace(k, v or '')
        return template

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Извлекает JSON-объект из произвольного текстового ответа."""
        import json
        import re
        # Убираем code fences, если есть
        fenced = re.search(r"```json\s*({[\s\S]*?})\s*```", text)
        if fenced:
            text = fenced.group(1)
        else:
            # Находим первое '{' и последнее '}'
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                text = text[start:end+1]
        try:
            return json.loads(text)
        except Exception as e:
            logger.error(f"❌ Не удалось распарсить JSON из ответа Gemini: {e}\nОтвет: {text[:500]}...")
            raise

    async def generate_video_package(self, source_text: str, source_name: str = "Unknown", source_url: str = "") -> Dict[str, Any]:
        """Генерирует полный пакет (контент+SEO) через общий промпт."""
        user_prompt = self._render_template(source_text=source_text, source_name=source_name, source_url=source_url)
        raw = await self._generate(user_prompt)
        data = self._extract_json(raw)
        return data

    async def summarize_for_video(self, source_text: str) -> Dict[str, str]:
        """Единая генерация через общий промпт (возврат title/brief)."""
        logger.info("🎯 Генерируем заголовок и описание через общий промпт V2...")
        pkg = await self.generate_video_package(source_text)
        vc = pkg.get('video_content', {}) if isinstance(pkg, dict) else {}
        return {'title': vc.get('title', 'Новина'), 'brief': vc.get('summary', '')}
    
    async def generate_seo_package(self, source_text: str) -> Dict[str, Any]:
        """Единая генерация SEO-пакета через общий промпт."""
        logger.info("🎯 Генерируем SEO пакет через общий промпт...")
        pkg = await self.generate_video_package(source_text)
        seo = pkg.get('seo_package', {}) if isinstance(pkg, dict) else {}
        title = pkg.get('video_content', {}).get('title', '')
        description = seo.get('youtube_description', '')
        tags = seo.get('tags', [])
        return {
            'title': title or seo.get('youtube_title', ''),
            'description': description,
            'tags': tags,
        }


def create_llm_provider_v2(config: dict) -> GeminiProviderV2:
    """
    Создает LLM провайдер V2 для нового дизайна
    
    Args:
        config: Конфигурация из config.ini
        
    Returns:
        GeminiProviderV2 instance
    """
    api_key = os.getenv('GEMINI_API_KEY', '')
    model = config['LLM'].get('gemini_model', 'gemini-1.5-flash')
    
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY не установлен в environment")
    
    logger.info("🚀 Создаем LLM провайдер V2 для нового дизайна")
    return GeminiProviderV2(api_key=api_key, model=model)

