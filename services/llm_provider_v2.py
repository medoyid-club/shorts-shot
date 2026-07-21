"""
LLM Provider V2 - промпты для нового дизайна (HTML+Selenium)
Адаптирован под формат новостных шортсов с заголовком и кратким описанием
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger("llm_v2")

# Gemini 2.5* для новых ключей часто отдаёт 404 «no longer available to new users».
# Актуальные замены: https://ai.google.dev/gemini-api/docs/deprecations
SUPPORTED_GEMINI_MODELS = (
    'gemini-3.1-flash-lite',
    'gemini-3.5-flash',
    'gemini-flash-lite-latest',
    # legacy — ещё могут работать на старых проектах
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
)
# Lite по умолчанию: как в Denis120→80 — быстрее для короткого JSON-пакета
DEFAULT_GEMINI_MODEL = 'gemini-3.1-flash-lite'
FALLBACK_MODELS = ['gemini-3.1-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.5-flash']

# Лимиты как у Denis: меньше thinking/болтовни, быстрее ответ
SOURCE_TEXT_MAX_CHARS = 8000
GENERATE_TIMEOUT_SEC = 45.0
MAX_OUTPUT_TOKENS = 1024


class GeminiProviderV2:
    """Gemini провайдер для генерации новостного контента (V2)"""
    
    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key
        normalized_model = (model or DEFAULT_GEMINI_MODEL).strip()
        if normalized_model not in SUPPORTED_GEMINI_MODELS:
            logger.warning(
                "⚠️ Модель '%s' не поддерживается. Разрешены только %s. "
                "Переключаемся на %s.",
                normalized_model,
                ', '.join(SUPPORTED_GEMINI_MODELS),
                DEFAULT_GEMINI_MODEL,
            )
            normalized_model = DEFAULT_GEMINI_MODEL

        self.original_model = normalized_model
        self.model = normalized_model
        self.fallback_models = [m for m in FALLBACK_MODELS if m != normalized_model]
        # Короткий system: детали уже в news_package_en.prompt (без дубля)
        self.system_instruction = (
            "Ти український редактор YouTube Shorts. Відповідай лише валідним JSON українською. "
            "Факти тільки з джерела. Трамп = Президент (з 2025), не екс-президент."
        )
        self._generation_config = genai.GenerationConfig(
            temperature=0.5,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type='application/json',
        )
        self._model_instance = None
        
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        
        genai.configure(api_key=self.api_key)
        self._model_instance = self._build_model()
        
        logger.info(f"🤖 GeminiProviderV2 инициализирован: {self.model}")

    def _build_model(self):
        return genai.GenerativeModel(
            self.model,
            system_instruction=self.system_instruction,
            generation_config=self._generation_config,
        )
    
    def _is_quota_error(self, error: Exception) -> Tuple[bool, Optional[float]]:
        """Проверяет, является ли ошибка ошибкой квоты (429) и извлекает retry_delay"""
        error_str = str(error)
        
        # Проверяем на ошибку 429 (квота)
        if '429' in error_str or 'quota' in error_str.lower() or 'Quota exceeded' in error_str:
            # Извлекаем retry_delay из сообщения об ошибке
            retry_match = re.search(r'Please retry in ([\d.]+)s', error_str)
            retry_delay = float(retry_match.group(1)) if retry_match else 60.0
            return True, retry_delay
        
        return False, None
    
    def _is_api_key_error(self, error: Exception) -> bool:
        """Проверяет, является ли ошибка проблемой с API ключом (403, 401, leaked)"""
        error_str = str(error)
        
        # Проверяем на ошибки авторизации и заблокированный ключ
        if ('403' in error_str or '401' in error_str or 
            'leaked' in error_str.lower() or 
            'invalid api key' in error_str.lower() or
            'api key was reported' in error_str.lower()):
            return True
        
        return False

    def _is_location_error(self, error: Exception) -> bool:
        """Проверяет, блокируется ли запрос по региону (гео-ограничение API)."""
        error_str = str(error).lower()
        return "user location is not supported" in error_str
    
    def _try_fallback_model(self) -> Optional[str]:
        """Пробует переключиться на fallback модель"""
        if self.fallback_models:
            fallback = self.fallback_models.pop(0)
            logger.warning(f"⚠️ Переключаемся на fallback модель: {fallback}")
            old_model = self.model
            self.model = fallback
            self._model_instance = self._build_model()
            return old_model
        return None
    
    async def _generate(self, prompt: str, retry_count: int = 0) -> str:
        """Базовая генерация с обработкой ошибок квот и fallback"""
        max_retries = 3
        
        try:
            logger.info(f"📡 Отправляем запрос к Gemini API (модель: {self.model})...")
            
            if self._model_instance is None:
                self._model_instance = self._build_model()

            response = await asyncio.wait_for(
                asyncio.to_thread(self._model_instance.generate_content, prompt),
                timeout=GENERATE_TIMEOUT_SEC,
            )
            
            result = response.text if hasattr(response, 'text') else str(response)
            logger.info("✅ Получен ответ от Gemini API")
            return result.strip()
            
        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут Gemini ({GENERATE_TIMEOUT_SEC:.0f}s) для {self.model}")
            if retry_count == 0 and self.fallback_models:
                old_model = self._try_fallback_model()
                if old_model:
                    logger.warning("🔄 Пробуем fallback модель после таймаута")
                    return await self._generate(prompt, retry_count=0)
            raise RuntimeError(f"Gemini timeout after {GENERATE_TIMEOUT_SEC:.0f}s ({self.model})")

        except Exception as e:
            error_str = str(e)

            if self._is_location_error(e):
                logger.error("❌ Gemini API недоступен из текущей локации: %s", error_str[:250])
                logger.error("💡 Проверьте, что VPN активен на сервере и трафик приложения идет через VPN.")
                raise RuntimeError(
                    "Gemini API blocked by region. "
                    "Проверьте ExpressVPN (подключение и маршрут по умолчанию)."
                )
            
            # Проверяем на проблему с API ключом (критичная ошибка, не retry)
            if self._is_api_key_error(e):
                logger.error(f"❌ Проблема с API ключом: {error_str[:200]}...")
                logger.error("💡 Создайте новый API ключ на https://aistudio.google.com/apikey")
                raise RuntimeError(f"API ключ заблокирован или неверный. Создайте новый ключ: {error_str[:100]}")
            
            # Проверяем на ошибку квоты
            is_quota, retry_delay = self._is_quota_error(e)
            
            if is_quota:
                logger.warning(f"⚠️ Превышена квота для модели {self.model}")
                logger.warning(f"ℹ️ {error_str[:200]}...")
                
                # Проверяем, является ли это ошибкой "limit: 0" (модель недоступна на тарифе)
                if 'limit: 0' in error_str:
                    logger.warning("⚠️ Модель недоступна на текущем тарифе (limit: 0). Переключаемся на fallback...")
                    old_model = self._try_fallback_model()
                    if old_model:
                        logger.info(f"🔄 Переключаемся с {old_model} на fallback модель: {self.model}")
                        return await self._generate(prompt, retry_count=0)
                    else:
                        logger.error("❌ Нет доступных fallback моделей. Включите биллинг в Google Cloud Console.")
                        raise RuntimeError(f"Модель {self.model} недоступна на free tier (limit: 0) и нет доступных fallback моделей. Включите биллинг или используйте другую модель.")
                
                # Пробуем fallback модель, если это была не первая попытка с текущей моделью
                if retry_count == 0:
                    old_model = self._try_fallback_model()
                    if old_model:
                        logger.info(f"🔄 Пробуем fallback модель вместо {old_model}")
                        return await self._generate(prompt, retry_count=0)
                
                # Если есть retry_delay и еще есть попытки, ждем и повторяем
                if retry_count < max_retries and retry_delay:
                    logger.info(f"⏳ Ждем {retry_delay:.1f} секунд перед повтором...")
                    await asyncio.sleep(min(retry_delay, 60))  # Максимум 60 секунд
                    return await self._generate(prompt, retry_count=retry_count + 1)
                
                # Если все попытки исчерпаны, пробуем fallback
                if self.fallback_models:
                    old_model = self._try_fallback_model()
                    if old_model:
                        logger.info(f"🔄 Исчерпаны попытки для {old_model}, пробуем fallback")
                        return await self._generate(prompt, retry_count=0)
            
            # Для всех остальных ошибок просто логируем и пробрасываем
            logger.error(f"❌ Ошибка генерации ({self.model}): {error_str[:300]}")
            
            # Последняя попытка с fallback моделью
            if retry_count == 0 and self.fallback_models:
                old_model = self._try_fallback_model()
                if old_model:
                    logger.warning(f"🔄 Пробуем fallback модель после ошибки")
                    return await self._generate(prompt, retry_count=0)
            
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

        # Как в Denis120→80: длинные форварды режем — меньше TTFT
        clipped = (source_text or '').strip()
        if len(clipped) > SOURCE_TEXT_MAX_CHARS:
            logger.info(
                "✂️ Обрезаем source_text: %s → %s символов",
                len(clipped),
                SOURCE_TEXT_MAX_CHARS,
            )
            clipped = clipped[:SOURCE_TEXT_MAX_CHARS]

        mapping = {
            '{{SOURCE_TEXT}}': clipped,
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
    model = config['LLM'].get('gemini_model', DEFAULT_GEMINI_MODEL)
    
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY не установлен в environment")
    
    logger.info("🚀 Создаем LLM провайдер V2 для нового дизайна")
    return GeminiProviderV2(api_key=api_key, model=model)

