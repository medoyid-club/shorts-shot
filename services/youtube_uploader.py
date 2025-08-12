from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.exceptions
import os
import pickle
import ssl
import socket

logger = logging.getLogger("youtube")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(self, config: dict):
        self.config = config
        self.client_secret_file = config['YOUTUBE']['client_secret_file']
        self.token_path = Path('token.json')
        self.service = self._get_service()

    def _get_service(self):
        creds = None
        if self.token_path.exists():
            try:
                with open(self.token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        # Создаем YouTube service с улучшенными настройками для надежности
        try:
            service = build('youtube', 'v3', credentials=creds)
            logger.info("✅ YouTube API service создан успешно")
            return service
        except Exception as e:
            logger.warning(f"⚠️ Проблема создания YouTube service: {e}")
            # Попробуем создать с настройками для обхода SSL проблем
            import httplib2
            http = httplib2.Http(
                timeout=60,  # Увеличиваем timeout
                disable_ssl_certificate_validation=False  # Оставляем проверку SSL
            )
            http = creds.authorize(http)
            service = build('youtube', 'v3', http=http)
            logger.info("✅ YouTube API service создан с custom HTTP client")
            return service

    def upload_video(
        self,
        video_file: str,
        title: str,
        description: str,
        tags: List[str] | None,
        category_id: str = '25',
        privacy_status: str = 'public'
    ) -> dict:
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id,
            },
            'status': {
                'privacyStatus': privacy_status,
            }
        }
        # Используем chunked upload для больших файлов и надежности
        media = MediaFileUpload(video_file, chunksize=1024*1024, resumable=True)  # 1MB chunks
        request = self.service.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        response = None
        error_count = 0
        max_retries = 3
        
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"📤 Загружено {int(status.progress() * 100)}%")
            except Exception as e:
                error_count += 1
                logger.warning(f"⚠️ Ошибка загрузки (попытка {error_count}/{max_retries}): {e}")
                
                if error_count >= max_retries:
                    logger.error(f"❌ Превышено максимальное количество попыток загрузки")
                    raise
                
                # Ждем перед повторной попыткой
                import time
                wait_time = 2 ** error_count  # exponential backoff
                logger.info(f"⏳ Ожидание {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
                
        logger.info("YouTube upload response: %s", response)
        return response

