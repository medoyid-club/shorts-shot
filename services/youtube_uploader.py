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
        service = build('youtube', 'v3', credentials=creds)
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
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
        request = self.service.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
        logger.info("YouTube upload response: %s", response)
        return response

