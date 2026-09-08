# Faina Bot

Telegram-бот на Python с ответами Gemini, OCR изображений и созданием Word/Excel.

## Переменные окружения

- `BOT_TOKEN` - токен бота из BotFather.
- `GEMINI_KEY` - API-ключ Google Gemini.
- `RENDER_EXTERNAL_URL` или `BASE_URL` - публичный HTTPS-адрес Render для webhook. Если переменная не задана, бот автоматически использует polling.
- `WEBHOOK_SECRET` - необязательный секрет webhook, рекомендуется задать.
- `GEMINI_MODELS` - необязательно, список моделей через запятую. По умолчанию: `gemini-2.5-flash,gemini-2.0-flash`.

## Запуск

```powershell
python -m pip install -r requirements.txt
python main.py
```

На Render используйте Web Service с командой запуска `python main.py`, открытым портом из переменной `PORT` и переменными `BOT_TOKEN` и `GEMINI_KEY`. Render обычно сам предоставляет `RENDER_EXTERNAL_URL`; при его отсутствии бот перейдет на polling. После запуска проверьте `/health`.

Для локального запуска polling достаточно задать `BOT_TOKEN` и `GEMINI_KEY`. Никогда не публикуйте эти значения в GitHub.