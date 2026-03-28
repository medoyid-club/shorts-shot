# Получение нового `token.json` (Ubuntu headless + браузер на Windows)

Используй эту инструкцию, если YouTube OAuth-токен сломался, просрочился или отсутствует.

## 0) Останови бота (иначе он падает в цикле без `token.json`)

```bash
sudo systemctl stop telegram-shorts
```

Сервис **не может** сам открыть браузер на сервере — токен создаётся только этой ручной командой, потом снова `systemctl start`.

## 1) Сгенерировать токен одной командой

Выполни на сервере:

```bash
cd /home/dzianis/shorts-shot && source .venv/bin/activate && rm -f token.json && OAUTHLIB_INSECURE_TRANSPORT=1 python3 -c "import pickle; from pathlib import Path; from services.config_loader import load_config; from google_auth_oauthlib.flow import InstalledAppFlow; cfg=load_config(Path('.')); flow=InstalledAppFlow.from_client_secrets_file(cfg['YOUTUBE']['client_secret_file'], ['https://www.googleapis.com/auth/youtube.upload']); flow.redirect_uri='http://localhost:8090/'; auth_url,_=flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true'); print('\nOPEN URL:\n'+auth_url+'\n'); resp=input('PASTE FULL REDIRECT URL:\n').strip(); flow.fetch_token(authorization_response=resp); creds=flow.credentials; pickle.dump(creds, open('token.json','wb')); print('token.json created | refresh_token=', bool(creds.refresh_token))"
```

## 2) Что делать в браузере

1. Открой URL из строки `OPEN URL`.
2. Войди в Google и дай доступ.
3. После редиректа на `http://localhost:8090/?...` (страница может не открыться — это нормально) скопируй **весь URL** из адресной строки.
4. Вставь URL в терминал в поле `PASTE FULL REDIRECT URL:`.

## 3) Проверка токена

```bash
python3 -c "import pickle; c=pickle.load(open('token.json','rb')); print('valid=',c.valid,'expired=',c.expired,'refresh=',bool(c.refresh_token))"
```

Ожидаемо:
- `valid=True`
- `refresh=True`

## 4) Перезапуск сервиса

```bash
sudo systemctl restart telegram-shorts
sudo journalctl -u telegram-shorts -n 120 -f -o short-iso
```

## Если получаешь ошибки

- **«Ничего не происходит»** — подожди 5–15 секунд: сначала грузится конфиг, потом появится блок `OPEN URL:` и запрос `PASTE FULL REDIRECT URL:`. Команда должна выполняться в обычном SSH-терминале (не внутри скрипта без stdin).
- `InsecureTransportError` — убедись, что команда запущена с `OAUTHLIB_INSECURE_TRANSPORT=1`.
- `FileNotFoundError` для client secret — проверь `YOUTUBE_CLIENT_SECRET_FILE` в `.env`.
- `could not locate runnable browser` — если видишь это **в логах systemd**, значит бот стартовал **без** `token.json`: сначала создай токен по этой инструкции (шаг 0–1), **не** удаляй `token.json`, пока не готов новый.
- **Баннер «Your app requires verification» / непроверенное приложение** — для своего аккаунта на экране Google нажми **Advanced** → **Go to … (unsafe)** и разреши доступ. Полная верификация в Google Cloud нужна для публичных пользователей, не для твоего личного OAuth.

### Долгоживущий refresh-токен

Если OAuth app был в режиме **Testing**, refresh часто «сгорает» примерно раз в 7 дней. В **OAuth consent screen** переведи статус в **In production** (как у тебя на скрине) — так отзывы токена бывают реже; при смене настроек иногда нужно заново пройти шаги 0–1.
