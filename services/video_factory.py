"""
Фабрика для создания генераторов видео
Позволяет переключаться между разными версиями дизайна
"""

import logging
from typing import Union

logger = logging.getLogger("video_factory")


def create_video_generator(config: dict) -> Union['VideoComposer', 'VideoComposerV2']:
    """
    Создает генератор видео в зависимости от настройки generator_version
    
    Args:
        config: Конфигурация из config.ini
        
    Returns:
        VideoComposer (v1) или VideoComposerV2 (v2)
    """
    version = config['VIDEO'].get('generator_version', 'v1').lower()
    
    if version == 'v2':
        # Жесткая проверка на V2, без автоматического fallback
        try:
            from services.video_generator_v2 import VideoComposerV2
            logger.info("🎬 Используется генератор V2 (HTML+Selenium)")
            return VideoComposerV2(config)
        except ImportError as e:
            logger.error(f"❌ Не удалось загрузить V2 генератор: {e}", exc_info=True)
            logger.error("💡 Убедитесь, что установлены все зависимости для V2:")
            logger.error("   pip install selenium opencv-python")
            raise RuntimeError("Остановлено: отсутствуют зависимости для VideoComposerV2")
    
    # По умолчанию или если указан v1
    from services.video_generator import VideoComposer
    logger.info("📹 Используется генератор V1 (MoviePy)")
    return VideoComposer(config)


def create_llm_provider(config: dict, force_version: str = None, use_ollama: bool = False):
    """
    Создает LLM провайдер в зависимости от версии генератора
    
    Args:
        config: Конфигурация из config.ini
        force_version: Принудительный выбор версии ('v1' или 'v2')
        use_ollama: Использовать Ollama вместо Gemini
        
    Returns:
        LLM провайдер соответствующей версии
    """
    # Проверяем настройку из конфига
    llm_provider_config = config.get('LLM', {}).get('provider', 'gemini').lower()
    
    # Проверяем переменную окружения, которая имеет приоритет
    import os
    llm_provider_env = os.environ.get('LLM_PROVIDER', '').lower()
    
    # Определяем, какой провайдер использовать
    use_ollama_final = use_ollama or llm_provider_config == 'ollama'
    if llm_provider_env:
        use_ollama_final = (llm_provider_env == 'ollama')

    if use_ollama_final:
        try:
            from services.llm_provider_ollama import OllamaProvider
            ollama_model = config.get('LLM', {}).get('ollama_model', 'gpt-oss-20b-MXFP4')
            ollama_url = config.get('LLM', {}).get('ollama_url', 'http://localhost:11434')
            logger.info(f"🤖 Используется Ollama: {ollama_model}")
            return OllamaProvider(model=ollama_model, base_url=ollama_url)
        except ImportError as e:
            logger.error(f"❌ Не удалось загрузить Ollama провайдер: {e}")
            logger.info("🔄 Переключаемся на Gemini...")
    
    # Если Ollama не выбран или не загрузился, используем Gemini
    version = force_version or config['VIDEO'].get('generator_version', 'v1').lower()
    
    if version == 'v2':
        try:
            from services.llm_provider_v2 import create_llm_provider_v2
            logger.info("🤖 Используются промпты LLM V2 (Gemini)")
            return create_llm_provider_v2(config)
        except ImportError as e:
            logger.warning(f"⚠️ Не удалось загрузить LLM V2: {e}")
            logger.info("🤖 Переключаемся на LLM V1")
            from services.llm_provider import create_llm_provider as create_v1
            return create_v1(config)
    else:
        from services.llm_provider import create_llm_provider as create_v1
        logger.info("🤖 Используются промпты LLM V1")
        return create_v1(config)

