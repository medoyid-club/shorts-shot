"""
Ollama LLM Provider - локальный провайдер для работы без интернета
"""
import logging
import json
import asyncio
from typing import Dict, Optional
import httpx
import re
from pathlib import Path

logger = logging.getLogger(__name__)

class OllamaProvider:
    """Локальный LLM провайдер через Ollama"""
    
    def __init__(self, model: str = "gpt-oss-20b-MXFP4", base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        # Увеличиваем таймаут для больших моделей (до 10 минут)
        self.client = httpx.AsyncClient(timeout=600.0)
        logger.info(f"🤖 OllamaProvider инициализирован: {model} @ {base_url}")
    
    async def _check_ollama_available(self) -> bool:
        """Проверяет доступность Ollama сервера"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                logger.info(f"✅ Ollama доступен. Доступные модели: {', '.join(model_names[:5])}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Ollama недоступен: {e}")
            logger.error("💡 Убедитесь что Ollama запущен: ollama serve")
            return False
    
    async def _generate(self, prompt: str, max_retries: int = 2) -> str:
        """Отправляет запрос к Ollama API и возвращает текстовый ответ."""
        # Проверяем доступность Ollama
        if not await self._check_ollama_available():
            raise RuntimeError("Ollama сервер недоступен. Запустите: ollama serve")
        
        # Пробуем сначала новый API /api/chat
        endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }
        
        logger.info(f"Отправляем запрос к Ollama ({len(prompt)} символов) на {endpoint}...")

        for attempt in range(max_retries):
            try:
                # Используем клиент напрямую, без async with (он уже создан)
                # Увеличиваем таймаут до 10 минут для больших моделей
                response = await self.client.post(endpoint, json=payload, timeout=600.0)
                response.raise_for_status()
                
                # Обработка ответа для /api/chat
                data = response.json()
                content = data.get('message', {}).get('content', '')
                
                logger.info(f"Получен ответ от Ollama: {len(content)} символов")
                return content
                
            except httpx.ReadTimeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logger.warning(f"⏱️ Таймаут запроса (попытка {attempt + 1}/{max_retries}). Ждем {wait_time}с и повторяем...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Таймаут после {max_retries} попыток. Модель {self.model} слишком медленная.")
                    logger.info("💡 Попробуйте использовать более быструю модель (например, llama3.2:3b)")
                    raise RuntimeError(f"Ollama таймаут: модель {self.model} слишком медленная. Попробуйте более быструю модель.")
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Fallback на старый API /api/generate
                    logger.info("⚠️ /api/chat не найден, пробуем старый API /api/generate...")
                    return await self._generate_legacy(prompt)
                else:
                    logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise
            except Exception as e:
                logger.error(f"Неожиданная ошибка (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                else:
                    raise
        
        raise RuntimeError("Не удалось получить ответ от Ollama после всех попыток")
    
    async def _generate_legacy(self, prompt: str) -> str:
        """Fallback на старый API /api/generate для совместимости."""
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 1000,
            }
        }
        
        logger.info(f"Используем старый API: {endpoint}")
        
        # Используем клиент напрямую, без async with, с увеличенным таймаутом
        response = await self.client.post(endpoint, json=payload, timeout=600.0)
        response.raise_for_status()
        
        data = response.json()
        content = data.get('response', '').strip()
        
        logger.info(f"Получен ответ от Ollama (legacy): {len(content)} символов")
        return content
                
    async def generate_video_package(self, source_text: str, source_name: str = "Unknown", 
                                     source_url: str = "", author_type: str = "media") -> Dict:
        """
        Генерирует полный пакет данных для видео за один запрос
        
        Returns:
            {
                "video_content": {
                    "title": "...",
                    "summary": "..."
                },
                "seo_package": {
                    "youtube_title": "...",
                    "youtube_description": "...",
                    "tags": ["...", "..."]
                }
            }
        """
        # Загружаем общий шаблон промпта
        template_path = Path(__file__).resolve().parent.parent / 'resources' / 'prompts' / 'news_package_en.prompt'
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
        except Exception as e:
            logger.error(f"Не удалось прочитать шаблон промпта: {template_path} ({e})")
            raise

        # Рендерим плейсхолдеры {{...}}
        mapping = {
            '{{SOURCE_TEXT}}': source_text,
            '{{SOURCE_NAME}}': source_name,
            '{{SOURCE_URL}}': source_url,
        }
        prompt = template
        for k, v in mapping.items():
            prompt = prompt.replace(k, v or '')

        logger.info("🎯 Генерируем полный пакет данных через Ollama (общий промпт)...")
        raw_response = await self._generate(prompt)
        
        # Извлекаем JSON из ответа (метод из shorts_news)
        try:
            # Пытаемся извлечь JSON из ответа
            json_match = re.search(r'```json\n({.*?})\n```', raw_response, re.DOTALL)
            if not json_match:
                # Если не нашли ```json, ищем первый { и последний }
                start_brace = raw_response.find('{')
                end_brace = raw_response.rfind('}')
                if start_brace != -1 and end_brace != -1:
                    json_str = raw_response[start_brace : end_brace + 1]
                else:
                    logger.error("Не удалось найти JSON в ответе.")
                    return None
            else:
                json_str = json_match.group(1)

            logger.info(f"[DEBUG] Extracted JSON string: {json_str[:200]}...")
            
            try:
                # Убираем лишние символы и экранирование
                parsed_json = json.loads(json_str)
                logger.info("✅ JSON успешно распарсен")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Не удалось распарсить JSON: {e}")
                return None
            
            # Валидация структуры
            if not isinstance(parsed_json, dict):
                raise ValueError("Response is not a dictionary")
            
            video_content = parsed_json.get('video_content', {})
            
            # Проверяем наличие ключей
            if not video_content.get('title') or not video_content.get('summary'):
                logger.warning("Ответ не содержит 'title' или 'summary' в 'video_content'")
                # Пробуем извлечь из regex как fallback
                return self._parse_with_regex(raw_response)

            logger.info("✅ Пакет данных успешно сгенерирован")
            logger.info(f"   Title: {video_content.get('title', '')[:50]}...")
            logger.info(f"   Summary: {video_content.get('summary', '')[:50]}...")
            
            return parsed_json

        except Exception as e:
            logger.error(f"Критическая ошибка обработки ответа: {e}", exc_info=True)
            return None

    def _parse_with_regex(self, content: str) -> Optional[Dict]:
        """Резервный метод парсинга через регулярные выражения."""
        try:
            logger.info("✅ Используем резервный метод парсинга (regex)...")
            title_match = re.search(r'"title":\s*"(.*?)"', content, re.DOTALL)
            summary_match = re.search(r'"summary":\s*"(.*?)"', content, re.DOTALL)
            
            if title_match and summary_match:
                result = {
                    "video_content": {
                        "title": title_match.group(1).strip(),
                        "summary": summary_match.group(1).strip()
                    },
                    "seo_package": {} # SEO пакет теряется в этом случае
                }
                logger.info(f"✅ Извлечены данные через regex: title={result['video_content']['title'][:50]}...")
                return result
            else:
                logger.error("❌ Regex не смог извлечь 'title' и 'summary'")
                return None
        except Exception as e:
            logger.error(f"Ошибка regex парсинга: {e}")
            return None
			
    async def summarize_for_video(self, source_text: str) -> Dict:
        """
        Генерирует краткое содержание и заголовок для видео.
        Возвращает словарь: {'title': '...', 'brief': '...'}
        """
        package = await self.generate_video_package(source_text)
        
        if package and 'video_content' in package:
            video_content = package['video_content']
            return {
                'title': video_content.get('title', 'Без заголовка'),
                'brief': video_content.get('summary', '')
            }
        
        # Fallback на случай если полный пакет не сгенерировался
        return {
            'title': 'Новость дня',
            'brief': source_text[:150] # Просто обрезаем текст
        }

    async def generate_seo_package(self, source_text: str) -> Dict:
        """
        Генерирует SEO-пакет (заголовок, описание, теги) для YouTube.
        """
        package = await self.generate_video_package(source_text)
        
        if package and 'seo_package' in package:
            return package['seo_package']
            
        # Fallback
        return {
            'youtube_title': 'Свежие новости',
            'youtube_description': source_text[:200],
            'tags': ['новости']
        }
		
    def close(self):
        """Закрывает http-клиент."""
        # httpx.AsyncClient закрывается через async with, явное закрытие не нужно
        pass

    def __del__(self):
        self.close()

