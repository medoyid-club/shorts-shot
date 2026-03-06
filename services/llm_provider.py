from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from google import genai
from google.api_core import retry

# Импортируем наши улучшения
import sys
import os
sys.path.append(r'D:\work\shorts_news\scripts')

try:
    from llm_processor import GeminiProvider as EnhancedGeminiProvider
    ENHANCED_LLM_AVAILABLE = True
    print("Улучшенный LLM провайдер доступен")
except ImportError as e:
    ENHANCED_LLM_AVAILABLE = False
    print(f"Улучшенный LLM провайдер недоступен: {e}")

logger = logging.getLogger("llm")

# Убираем настройки безопасности пока не разберемся с правильным синтаксисом
# SAFETY_SETTINGS = None

def _get_pacific_midnight_timestamp() -> float:
    """Возвращает timestamp последней полуночи по Тихоокеанскому времени"""
    # Тихоокеанское время: UTC-8 (PST) или UTC-7 (PDT)
    # Для простоты используем PST круглый год (UTC-8)
    pacific_tz = timezone(timedelta(hours=-8))
    
    # Получаем текущее время в тихоокеанском поясе
    now_pacific = datetime.now(pacific_tz)
    
    # Находим полночь сегодняшнего дня
    midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Возвращаем timestamp полуночи (если сейчас уже после полуночи)
    # Если сейчас до полуночи, то берем вчерашнюю полночь
    return midnight_pacific.timestamp()

def create_llm_provider(config: dict) -> "GeminiProvider":
    primary_key = os.getenv('GEMINI_API_KEY', '')
    backup_key = os.getenv('GEMINI_API_KEY_BACKUP', '')
    third_key = os.getenv('GEMINI_API_KEY_OTHER_BACKUP', '')
    fourth_key = os.getenv('GEMINI_API_KEY_BILLING', '')

    # Используем улучшенный провайдер если доступен
    if ENHANCED_LLM_AVAILABLE:
        logger.info("🚀 Используем улучшенный LLM провайдер с Google Search Grounding")
        llm_config = {
            'enable_fact_checking': True,
            'grounding_temperature': 0.3,
            'fact_check_threshold': 0.7,
            'temperature': 0.7,
            'max_tokens': 2000
        }
        return EnhancedGeminiProvider(
            api_key=primary_key,
            model=config['LLM'].get('gemini_model', 'gemini-2.5-flash'),
            config=llm_config
        )
    else:
        logger.info("📝 Используем стандартный LLM провайдер")
        return GeminiProvider(
            api_key=primary_key,
            backup_api_key=backup_key,
            third_api_key=third_key,
            fourth_api_key=fourth_key,
            model=config['LLM'].get('gemini_model', 'gemini-2.5-flash')
        )


@dataclass
class GeminiProvider:
    api_key: str
    backup_api_key: str = ''
    third_api_key: str = ''
    fourth_api_key: str = ''
    model: str = 'gemini-2.5-flash'
    current_api_key: str = ''  # Текущий используемый ключ
    used_keys: list = None  # Список уже использованных ключей
    exhausted_keys_timestamp: dict = None  # Время когда ключи были исчерпаны
    last_quota_reset_check: float = None  # Последняя проверка сброса квоты
    
    def __post_init__(self):
        self.current_api_key = self.api_key
        self.used_keys = []  # Инициализируем список использованных ключей
        self.exhausted_keys_timestamp = {}  # Инициализируем timestamps исчерпанных ключей
        self.last_quota_reset_check = time.time()
        # Настройка retry для Gemini API
        self._setup_retry()
    
    def _setup_retry(self):
        """Настройка автоматических повторов для Gemini API"""
        def is_retriable(exception):
            if hasattr(exception, 'code'):
                return exception.code in {429, 503}  # Quota exceeded, Service unavailable
            return False
        
        # Применяем retry к методу generate_content
        if hasattr(genai.models.Models, 'generate_content'):
            original_method = genai.models.Models.generate_content
            retried_method = retry.Retry(
                predicate=is_retriable,
                initial=1.0,    # начальная пауза 1 сек
                maximum=30.0,   # максимальная пауза 30 сек
                multiplier=2.0, # экспоненциальное увеличение
                deadline=60.0   # общий timeout 1 минута
            )(original_method)
            genai.models.Models.generate_content = retried_method
            logger.info("✅ Retry настроен для Gemini API (timeout: 60s)")

    def _get_client(self) -> genai.Client:
        if not self.current_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in the environment")
        
        return genai.Client(api_key=self.current_api_key)
    
    def _switch_to_next_key(self) -> bool:
        """Переключение на следующий доступный API ключ"""
        # Список всех доступных ключей
        available_keys = [
            (self.api_key, "основной"),
            (self.backup_api_key, "резервный"), 
            (self.third_api_key, "третий"),
            (self.fourth_api_key, "четвертый (с биллингом)")
        ]
        
        # Диагностика
        logger.info(f"🔍 Текущий ключ: {self.current_api_key[:10]}...")
        logger.info(f"🔍 Использованные ключи: {[k[:10] + '...' for k in self.used_keys]}")
        logger.info(f"🔍 Доступные ключи:")
        for key, name in available_keys:
            status = "✅" if key else "❌"
            logger.info(f"   {status} {name}: {key[:10] + '...' if key else 'отсутствует'}")
        
        # Помечаем текущий ключ как использованный ПЕРЕД поиском нового
        if self.current_api_key and self.current_api_key not in self.used_keys:
            self.used_keys.append(self.current_api_key)
            # Записываем время исчерпания для квотных ограничений (1 час)
            self.exhausted_keys_timestamp[self.current_api_key] = time.time()
            logger.info(f"🚫 Помечаем текущий ключ как использованный (квота исчерпана)")
        
        # Находим следующий неиспользованный ключ
        for key, name in available_keys:
            if key and key not in self.used_keys:
                if "биллингом" in name:
                    logger.warning(f"💳 ВНИМАНИЕ: Переключаемся на {name} - ПЛАТНЫЙ API!")
                else:
                    logger.warning(f"🔄 Переключаемся на {name} Gemini API ключ")
                self.current_api_key = key
                return True
        
        logger.error("❌ Все API ключи исчерпаны!")
        return False
    
    def _check_and_reset_quota(self):
        """Проверяет и сбрасывает квоту, если прошла полночь по Тихоокеанскому времени"""
        pacific_midnight = _get_pacific_midnight_timestamp()
        
        # Если последняя проверка была до полуночи, сбрасываем квоты
        if self.last_quota_reset_check < pacific_midnight:
            logger.info("🌅 Полночь по Тихоокеанскому времени прошла - сбрасываем квоты всех ключей!")
            
            # Очищаем все ограничения
            restored_count = len(self.exhausted_keys_timestamp)
            self.exhausted_keys_timestamp.clear()
            self.used_keys.clear()
            
            # Возвращаемся к основному ключу
            self.current_api_key = self.api_key
            self.last_quota_reset_check = time.time()
            
            if restored_count > 0:
                logger.info(f"✅ Восстановлено {restored_count} API ключей после сброса квоты")
                logger.info("🔄 Возвращаемся к основному ключу")
            
            return True
        return False
    
    def reset_for_new_message(self):
        """Сброс состояния для нового сообщения с учетом Тихоокеанского времени"""
        logger.info("🔄 Сбрасываем состояние API ключей для нового сообщения")
        
        # Сначала проверяем, не прошла ли полночь по Тихоокеанскому времени
        if self._check_and_reset_quota():
            # Если прошла полночь, все ключи уже восстановлены
            return
        
        # Если полночь не прошла, используем старую логику с часовыми интервалами
        current_time = time.time()
        quota_reset_hours = 1  # Дополнительная защита: час с момента исчерпания
        
        # Убираем ключи из черного списка, если прошел час с момента исчерпания
        keys_to_restore = []
        for key, timestamp in list(self.exhausted_keys_timestamp.items()):
            if current_time - timestamp > quota_reset_hours * 3600:  # 1 час в секундах
                keys_to_restore.append(key)
                
        for key in keys_to_restore:
            del self.exhausted_keys_timestamp[key]
            if key in self.used_keys:
                self.used_keys.remove(key)
            logger.info(f"✅ Восстанавливаем ключ {key[:10]}... (прошло >1 часа)")
        
        # Если основной ключ доступен, используем его
        if self.api_key and self.api_key not in self.used_keys:
            self.current_api_key = self.api_key
            logger.info("🔄 Возвращаемся к основному ключу")
        else:
            # Ищем первый доступный ключ
            available_keys = [
                (self.api_key, "основной"),
                (self.backup_api_key, "резервный"), 
                (self.third_api_key, "третий"),
                (self.fourth_api_key, "четвертый (с биллингом)")
            ]
            
            for key, name in available_keys:
                if key and key not in self.used_keys:
                    self.current_api_key = key
                    if "биллингом" in name:
                        logger.warning(f"💳 Остаемся на {name} ключе")
                    else:
                        logger.info(f"🔄 Используем {name} ключ")
                    break
    
    async def _generate_with_fallback(self, prompt: str) -> str:
        """Генерация с fallback на резервный API при ошибках квоты"""
        # Проверяем квоту перед началом генерации
        self._check_and_reset_quota()
        
        logger.info("🤖 Начинаем генерацию с Gemini API...")
        logger.info(f"🔑 Используем ключ: {self.current_api_key[:10]}... (попытка с текущим ключом)")
        
        for attempt in range(4):  # Максимум 4 попытки (для 4-х ключей)
            try:
                client = self._get_client()
                logger.info(f"📡 Отправляем запрос к Gemini (попытка {attempt + 1}/4)...")
                
                # Добавляем timeout для каждого отдельного запроса
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=self.model,
                        contents=prompt,
                    ),
                    timeout=45.0  # 45 секунд на один запрос
                )
                
                result = getattr(resp, 'text', str(resp))
                logger.info("✅ Получен ответ от Gemini API")
                return result
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ Timeout при запросе к Gemini API (попытка {attempt + 1})")
                if attempt < 3 and self._switch_to_next_key():
                    logger.info("💫 Повторяем запрос с другим API ключом...")
                    continue
                    
            except Exception as e:
                error_msg = str(e)
                is_quota_error = ('429' in error_msg or 'quota' in error_msg.lower() or 
                                'RESOURCE_EXHAUSTED' in error_msg)
                
                logger.error(f"❌ Ошибка генерации (попытка {attempt + 1}): {e}")
                
                if is_quota_error and attempt < 3:
                    if self._switch_to_next_key():
                        logger.info("💫 Повторяем запрос с другим API ключом...")
                        continue
                    else:
                        logger.error("❌ Нет больше доступных API ключей для fallback")
                
                if attempt == 3:  # Последняя попытка
                    raise
            
        return ""

    def _strip(self, text: str) -> str:
        return (text or "").strip()

    def _normalize_summary(self, text: str) -> str:
        t = (text or "").strip()
        # Replace unicode ellipsis with dots and remove trailing ellipses
        t = t.replace("…", "...")
        while t.endswith("..."):
            t = t[:-3].rstrip()
        # Ensure ending punctuation
        if t and t[-1] not in ".!?":
            t = t + "."
        return t

    async def _translate_to_uk(self, text: str) -> str:
        if not text:
            return ""
        prompt = (
            "TASK: Translate to Ukrainian (modern, natural Ukrainian).\n\n"
            "RULES:\n"
            "- Use modern Ukrainian vocabulary\n"
            "- Keep the same tone and energy\n"
            "- Preserve length as much as possible\n"
            "- For news: use journalism style\n"
            "- For titles: keep clickbait energy\n"
            "- NO Russian words or phrases\n"
            "- Return ONLY the translation\n\n"
            f"ENGLISH TEXT:\n{text}\n\n"
            "UKRAINIAN:"
        )
        response_text = await self._generate_with_fallback(prompt)
        return self._strip(response_text)

    async def _translate_tags_to_uk(self, tags: list[str]) -> list[str]:
        if not tags:
            return []
        prompt = (
            "TASK: Translate YouTube tags to Ukrainian.\n\n"
            "RULES:\n"
            "- Keep 1-2 words maximum per tag\n"
            "- Use common, searchable words\n"
            "- For names: keep original (Putin = Путін, Trump = Трамп)\n"
            "- For countries: use Ukrainian names (Russia = Росія, America = Америка)\n"
            "- For topics: use popular Ukrainian terms\n"
            "- Return JSON array only\n\n"
            f"ENGLISH TAGS: {json.dumps(tags, ensure_ascii=False)}\n\n"
            "UKRAINIAN JSON:"
        )
        raw = await self._generate_with_fallback(prompt)
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [self._strip(str(x)) for x in data if self._strip(str(x))]
        except Exception:
            pass
        # fallback: simple per-word translate in one go
        text = await self._translate_to_uk(
            ", ".join(tags)
        )
        return [self._strip(t) for t in re.split(r",|\n", text) if self._strip(t)]

    async def summarize_for_video(self, source_text: str) -> str:
        # Step 1: делаем чистое англ. резюме, чтобы улучшить структуру
        prompt_en = (
            "TASK: Create a video text summary for YouTube Shorts (Ukrainian news).\n"
            "RULES:\n"
            "- Maximum 180 characters total\n"
            "- Complete sentences only (no cut-offs, no ...)\n"
            "- Direct, engaging tone\n"
            "- Present tense where possible\n"
            "- No intro phrases like 'this is about' or 'the news says'\n"
            "- No hashtags, no links\n"
            "- Must end with proper punctuation (. ! ?)\n\n"
            "EXAMPLES:\n"
            "- 'Bitcoin hits new record above $95,000 as investors expect crypto-friendly policies.'\n"
            "- 'Ukrainian forces advance 3km near Bakhmut despite heavy resistance.'\n"
            "- 'Apple announces new iPhone with AI features launching next month.'\n\n"
            f"SOURCE TEXT:\n{source_text}\n\n"
            "SUMMARY:"
        )
        summary_en = await self._generate_with_fallback(prompt_en)
        summary_en = self._strip(summary_en)
        logger.info(f"🔍 LLM Summary EN: {summary_en}")
        # Step 2: переводим на украинский
        summary_uk = await self._translate_to_uk(summary_en)
        logger.info(f"🔍 LLM Summary UK: {summary_uk}")
        result = self._normalize_summary(summary_uk)
        logger.info(f"🔍 LLM Summary Final: {result}")
        return result

    async def generate_seo_package(self, source_text: str) -> Dict[str, Any]:
        # Генерация на английском для большей стабильности
        prompt_en = (
            "TASK: Create YouTube Shorts SEO package for Ukrainian news content.\n\n"
            "OUTPUT FORMAT: JSON only, no explanations\n"
            "{\n"
            '  "title": "...",\n'
            '  "description": "...",\n'
            '  "tags": ["...", "..."]\n'
            "}\n\n"
            "TITLE RULES:\n"
            "- Maximum 65 characters\n"
            "- Clickbait style but factual\n"
            "- Start with action words or shocking facts\n"
            "- NO generic words like 'news', 'update', 'breaking'\n"
            "- Examples: 'Putin meets Trump at Alaska hotel', 'Bitcoin crashes 40% in single day', 'Ukraine captures Russian general'\n\n"
            "DESCRIPTION RULES:\n"
            "- 1-2 SHORT sentences maximum\n"
            "- Add context or key details not in title\n"
            "- Can be empty if title says everything\n"
            "- Include 5 relevant hashtags at the end with # symbol\n\n"
            "TAGS RULES:\n"
            "- Exactly 12-15 tags\n"
            "- Mix of: specific names, general topics, emotions, locations\n"
            "- Single words or short phrases (max 3 words)\n"
            "- NO '#' symbols\n"
            "- Include: relevant people names, countries, topics, trending keywords\n"
            "- Examples: ['putin', 'trump', 'politics', 'russia', 'america', 'meeting', 'diplomacy', 'world news', 'leadership', 'international', 'alaska', 'summit']\n\n"
            f"SOURCE TEXT:\n{source_text}\n\n"
            "JSON:"
        )
        raw = await self._generate_with_fallback(prompt_en)
        logger.info(f"🔍 LLM SEO Raw Response: {raw}")
        data = _extract_json(raw)
        logger.info(f"🔍 LLM SEO Parsed JSON: {data}")
        if not isinstance(data, dict):
            raise ValueError("SEO JSON is not an object")
        data.setdefault('title', '')
        data.setdefault('description', '')
        tags = data.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        logger.info(f"🔍 LLM SEO EN - Title: {data.get('title')}, Tags: {tags}")
        # Переводим заголовок и описание на укр., теги — тоже на укр.
        title_uk = await self._translate_to_uk(str(data.get('title', '')))
        descr_uk = await self._translate_to_uk(str(data.get('description', '')))
        tags_uk = await self._translate_tags_to_uk([str(t) for t in tags])
        logger.info(f"🔍 LLM SEO UK - Title: {title_uk}, Description: {descr_uk}, Tags: {tags_uk}")
        return {'title': title_uk, 'description': descr_uk, 'tags': tags_uk}


def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("Failed to parse JSON from LLM response")

