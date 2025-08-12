from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict

from google import genai
from google.api_core import retry

logger = logging.getLogger("llm")

# Убираем настройки безопасности пока не разберемся с правильным синтаксисом
# SAFETY_SETTINGS = None

def create_llm_provider(config: dict) -> "GeminiProvider":
    primary_key = os.getenv('GEMINI_API_KEY', '')
    backup_key = os.getenv('GEMINI_API_KEY_BACKUP', '')
    return GeminiProvider(
        api_key=primary_key,
        backup_api_key=backup_key,
        model=config['LLM'].get('gemini_model', 'gemini-2.0-flash')
    )


@dataclass
class GeminiProvider:
    api_key: str
    backup_api_key: str = ''
    model: str = 'gemini-2.0-flash'
    current_api_key: str = ''  # Текущий используемый ключ
    
    def __post_init__(self):
        self.current_api_key = self.api_key
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
                initial=2.0,    # начальная пауза 2 сек
                maximum=60.0,   # максимальная пауза 60 сек
                multiplier=2.0, # экспоненциальное увеличение
                deadline=300.0  # общий timeout 5 минут
            )(original_method)
            genai.models.Models.generate_content = retried_method
            logger.info("✅ Retry настроен для Gemini API")

    def _get_client(self) -> genai.Client:
        if not self.current_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in the environment")
        
        return genai.Client(api_key=self.current_api_key)
    
    def _switch_to_backup(self) -> bool:
        """Переключение на резервный API ключ"""
        if self.backup_api_key and self.current_api_key != self.backup_api_key:
            logger.warning("🔄 Переключаемся на резервный Gemini API ключ")
            self.current_api_key = self.backup_api_key
            return True
        return False
    
    async def _generate_with_fallback(self, prompt: str) -> str:
        """Генерация с fallback на резервный API при ошибках квоты"""
        for attempt in range(2):  # Максимум 2 попытки
            try:
                client = self._get_client()
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                )
                return getattr(resp, 'text', str(resp))
            except Exception as e:
                error_msg = str(e)
                is_quota_error = ('429' in error_msg or 'quota' in error_msg.lower() or 
                                'RESOURCE_EXHAUSTED' in error_msg)
                
                if is_quota_error and attempt == 0:
                    if self._switch_to_backup():
                        logger.info("💫 Повторяем запрос с резервным API ключом...")
                        continue
                    else:
                        logger.error("❌ Нет резервного API ключа для fallback")
                
                logger.error(f"❌ Ошибка генерации (попытка {attempt + 1}): {e}")
                if attempt == 1:  # Последняя попытка
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

