# Faina Bot

Telegram-бот на Python с ответами Gemini, OCR изображений и созданием Word/Excel.

## Переменные окружения

- `BOT_TOKEN` - токен бота из BotFather.
- `GEMINI_KEY` - API-ключ Google Gemini.
- `RENDER_EXTERNAL_URL` или `BASE_URL` - публичный HTTPS-адрес Render для webhook. Если переменная не задана, бот автоматически использует polling.
- `WEBHOOK_SECRET` - необязательный секрет webhook, рекомендуется задать.
- `GEMINI_MODELS` - необязательно, список моделей через запятую. По умолчанию: `gemini-2.5-flash,gemini-2.0-flash`.
- `GOOGLE_SERVICE_ACCOUNT_JSON` - JSON сервисного аккаунта Google с доступом только на чтение таблицы.
- `GOOGLE_SHEET_ID` - идентификатор Google Sheets.
- `GOOGLE_SHEET_RANGE` - диапазон с заголовками в первой строке, по умолчанию `Sheet1!A:Z`.
- `GOOGLE_SHEETS_CACHE_SECONDS` - срок кэша строк, по умолчанию `60`.

Для поиска прайса таблица должна содержать заголовки `model`, `model_aliases`, `service`,
`service_aliases`, `work_price`. Допустимы русские заголовки: `модель`, `синонимы модели`,
`услуга`, `синонимы услуги`, `цена работы`. Синонимы разделяются запятыми или точками с запятой.
Поиск нормализует варианты вроде `айфон 13 про макс` и `iPhone 13 Pro Max`, а также различает
результаты `found`, `not_found` и ошибку доступа к таблице. Цена не вычисляется и не изменяется.

## Запуск

```powershell
python -m pip install -r requirements.txt
python main.py
```

На Render используйте Web Service с командой запуска `python main.py`, открытым портом из переменной `PORT` и переменными `BOT_TOKEN` и `GEMINI_KEY`. Render обычно сам предоставляет `RENDER_EXTERNAL_URL`; при его отсутствии бот перейдет на polling. После запуска проверьте `/health`.

Для локального запуска polling достаточно задать `BOT_TOKEN` и `GEMINI_KEY`. Никогда не публикуйте эти значения в GitHub.