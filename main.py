import asyncio
import io
import json
import os
import re
import time
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from google import genai
from google.genai import types as genai_types
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://faina-bot-new.onrender.com").rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
MAX_TEXT = 12000

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not GEMINI_KEY:
    raise RuntimeError("GEMINI_KEY is not set")

client = genai.Client(
    api_key=GEMINI_KEY,
    http_options=genai_types.HttpOptions(
        timeout=30000,
        retry_options=genai_types.HttpRetryOptions(attempts=1),
    ),
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
chat_locks: dict[int, asyncio.Lock] = {}
webhook_task = None
MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
)


def lock_for(chat_id: int) -> asyncio.Lock:
    return chat_locks.setdefault(chat_id, asyncio.Lock())


def clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def ask_gemini(contents: Any, system_prompt: str = "") -> str | None:
    payload = contents
    if system_prompt:
        payload = [system_prompt, contents] if not isinstance(contents, list) else [system_prompt, *contents]
    for model in MODELS:
        started = time.monotonic()
        try:
            response = await client.aio.models.generate_content(model=model, contents=payload)
            text = getattr(response, "text", None)
            if text:
                print(f"Gemini OK model={model} seconds={time.monotonic()-started:.2f}", flush=True)
                return text.strip()
            print(f"Gemini empty model={model}", flush=True)
        except Exception as e:
            print(f"Gemini failed model={model} seconds={time.monotonic()-started:.2f} error={type(e).__name__}: {e}", flush=True)
    return None


SYSTEM_PROMPT = (
    "Ты Фаина — полезный AI-помощник. Отвечай на языке пользователя. "
    "Поддерживай русский и таджикский, включая таджикские буквы Ғ Ӣ Қ Ӯ Ҳ Ҷ. "
    "Не выдумывай данные. Не упоминай внутренние API, модели или служебные ошибки."
)


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Привет! Я Фаина 👋\n\n"
        "Я умею отвечать на русском и таджикском, распознавать текст и таблицы с фото, "
        "а также создавать Word и Excel.\n\n"
        "Просто отправь сообщение или фотографию."
    )


@dp.message(commands={"help"})
async def help_cmd(message: types.Message):
    await message.answer(
        "Фаина умеет:\n"
        "• 💬 отвечать на русском и таджикском\n"
        "• 📷 распознавать текст и таблицы с фото\n"
        "• 📄 создавать Word (.docx)\n"
        "• 📊 создавать Excel (.xlsx)\n\n"
        "Для Word/Excel можно написать: «сделай Word» или «сделай Excel» и добавить данные/фото."
    )


async def extract_photo(photo_bytes: bytes, caption: str = "") -> dict[str, Any] | None:
    prompt = """
Ты выполняешь точное OCR и извлечение структуры документа с изображения.
Верни ТОЛЬКО валидный JSON без markdown:
{
  "title": "название документа или пусто",
  "language": "ru|tg|mixed|other",
  "document_text": "весь обычный текст в естественном порядке",
  "headers": ["название колонки 1", "название колонки 2"],
  "rows": [["значение", "значение"]]
}
Правила:
1. Сохраняй исходный текст максимально дословно.
2. Обязательно сохраняй таджикские буквы Ғ Ӣ Қ Ӯ Ҳ Ҷ и регистр.
3. Если на фото таблица, восстанови реальные названия колонок и все строки.
4. Не придумывай отсутствующие значения.
5. Если таблицы нет, headers и rows должны быть пустыми массивами.
6. document_text должен содержать весь распознанный текст, включая текст таблицы, если это необходимо для полноты.
""".strip()
    if caption:
        prompt += f"\nДополнительная инструкция пользователя: {caption[:2000]}"
    response = await ask_gemini(
        [genai_types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg"), prompt],
        "Ты специалист по OCR документов и таблиц."
    )
    if not response:
        return None
    try:
        data = json.loads(clean_json(response))
        if not isinstance(data, dict):
            return None
        data.setdefault("title", "Документ")
        data.setdefault("document_text", "")
        data.setdefault("headers", [])
        data.setdefault("rows", [])
        return data
    except Exception as e:
        print(f"OCR JSON parse failed: {type(e).__name__}", flush=True)
        return {
            "title": "Распознанный документ",
            "language": "mixed",
            "document_text": response,
            "headers": [],
            "rows": [],
        }


def make_docx(data: dict[str, Any]) -> bytes:
    doc = Document()
    title = str(data.get("title") or "Документ")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(16)

    text = str(data.get("document_text") or "").strip()
    if text:
        for block in re.split(r"\n\s*\n", text):
            if block.strip():
                doc.add_paragraph(block.strip())

    headers = data.get("headers") or []
    rows = data.get("rows") or []
    if headers:
        cols = len(headers)
        table = doc.add_table(rows=1, cols=cols)
        table.style = "Table Grid"
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = str(header)
            for run in cell.paragraphs[0].runs:
                run.bold = True
        for row in rows:
            cells = table.add_row().cells
            for i in range(cols):
                cells[i].text = str(row[i]) if i < len(row) else ""
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def make_xlsx(data: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"
    title = str(data.get("title") or "Документ")
    headers = [str(x) for x in (data.get("headers") or [])]
    rows = data.get("rows") or []
    text = str(data.get("document_text") or "").strip()

    if headers:
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in rows:
            ws.append([str(x) if x is not None else "" for x in row])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in range(1, len(headers) + 1):
            max_len = max([len(str(ws.cell(r, col).value or "")) for r in range(1, ws.max_row + 1)] + [10])
            ws.column_dimensions[get_column_letter(col)].width = min(max_len + 2, 45)
    else:
        ws.append([title])
        if text:
            for line in text.splitlines():
                if line.strip():
                    ws.append([line.strip()])
        ws.column_dimensions["A"].width = min(max([len(str(c.value or "")) for c in ws["A"]] + [20]) + 2, 80)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def send_file_pair(message: types.Message, data: dict[str, Any], word: bool = True, excel: bool = True):
    title = re.sub(r"[^\w\- ]+", "", str(data.get("title") or "Faina"), flags=re.UNICODE).strip()[:50] or "Faina"
    if word:
        content = make_docx(data)
        await message.answer_document(BufferedInputFile(content, filename=f"{title}.docx"), caption="📄 Word готов")
    if excel:
        content = make_xlsx(data)
        await message.answer_document(BufferedInputFile(content, filename=f"{title}.xlsx"), caption="📊 Excel готов")


@dp.message(F.photo)
async def photo_handler(message: types.Message):
    async with lock_for(message.chat.id):
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            stream = io.BytesIO()
            await bot.download_file(file.file_path, stream)
            data = await extract_photo(stream.getvalue(), message.caption or "")
            if not data:
                await message.answer("Не удалось распознать изображение. Попробуй отправить фото ещё раз.")
                return
            summary = str(data.get("document_text") or "").strip()
            if summary:
                preview = summary[:2500]
                await message.answer("📷 Распознано:\n\n" + preview)
            await send_file_pair(message, data, word=True, excel=True)
        except Exception as e:
            print(f"Photo handler failed: {type(e).__name__}: {e}", flush=True)
            await message.answer("Не удалось обработать фото. Попробуй ещё раз.")


@dp.message(F.document)
async def image_document_handler(message: types.Message):
    if not (message.document.mime_type or "").startswith("image/"):
        return
    async with lock_for(message.chat.id):
        try:
            file = await bot.get_file(message.document.file_id)
            stream = io.BytesIO()
            await bot.download_file(file.file_path, stream)
            data = await extract_photo(stream.getvalue(), message.caption or "")
            if not data:
                await message.answer("Не удалось распознать изображение.")
                return
            await send_file_pair(message, data, word=True, excel=True)
        except Exception as e:
            print(f"Image document handler failed: {type(e).__name__}: {e}", flush=True)
            await message.answer("Не удалось обработать изображение. Попробуй ещё раз.")


async def text_handler(message: types.Message):
    if not message.text:
        return
    text = message.text.strip()
    print(f"Telegram message received chat_id={message.chat.id} text_len={len(text)}", flush=True)
    lower = text.lower()
    wants_word = any(x in lower for x in ("сделай word", "создай word", "word документ", "/word"))
    wants_excel = any(x in lower for x in ("сделай excel", "создай excel", "excel таблиц", "/excel"))

    async with lock_for(message.chat.id):
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
        if wants_word or wants_excel:
            extraction_prompt = (
                "Преобразуй данные пользователя в JSON для документа. Верни только JSON: "
                '{"title":"...","language":"ru|tg|mixed","document_text":"...",'
                '"headers":["..."],"rows":[["..."]]}. '
                "Сохраняй таджикские буквы Ғ Ӣ Қ Ӯ Ҳ Ҷ. Если таблица не нужна, headers/rows пустые. "
                "Не выдумывай данные.\n\nДанные пользователя:\n" + text[:MAX_TEXT]
            )
            raw = await ask_gemini(extraction_prompt, "Ты специалист по структурированию документов.")
            if not raw:
                await message.answer("Сейчас не удалось создать документ. Попробуй ещё раз.")
                return
            try:
                data = json.loads(clean_json(raw))
            except Exception:
                data = {"title": "Документ", "document_text": raw, "headers": [], "rows": []}
            await send_file_pair(message, data, word=wants_word, excel=wants_excel)
            return

        prompt = SYSTEM_PROMPT + "\n\nСообщение пользователя:\n" + text[:MAX_TEXT]
        answer = await ask_gemini(prompt)
        if answer:
            for i in range(0, len(answer), 4000):
                await message.answer(answer[i:i + 4000])
        else:
            await message.answer("Сейчас AI временно занят. Попробуй ещё раз через несколько секунд.")


@dp.message(F.text)
async def text_message_handler(message: types.Message):
    await text_handler(message)


async def health_check(request: web.Request):
    return web.json_response({"status": "ok", "service": "faina-bot"})


async def configure_webhook():
    webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
    allowed_updates = dp.resolve_used_update_types()
    for attempt in range(1, 4):
        try:
            print(f"Setting Telegram webhook attempt={attempt} url={webhook_url}", flush=True)
            await asyncio.wait_for(
                bot.set_webhook(
                    url=webhook_url,
                    secret_token=WEBHOOK_SECRET or None,
                    drop_pending_updates=False,
                    max_connections=20,
                    allowed_updates=allowed_updates,
                ),
                timeout=12,
            )
            info = await asyncio.wait_for(bot.get_webhook_info(), timeout=8)
            print(f"Telegram webhook set successfully pending={info.pending_update_count} last_error={getattr(info, 'last_error_message', None)!r}", flush=True)
            return
        except Exception as e:
            print(f"Webhook setup failed attempt={attempt}: {type(e).__name__}: {e}", flush=True)
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)
    print("Webhook setup failed after 3 attempts; service remains online", flush=True)


async def on_startup(app: web.Application):
    global webhook_task
    webhook_task = asyncio.create_task(configure_webhook())
    app["webhook_task"] = webhook_task
    print("Faina startup complete; webhook configuration running in background", flush=True)


async def on_shutdown(app: web.Application):
    task = app.get("webhook_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await bot.session.close()


def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET or None,
        handle_in_background=True,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", "10000"))
    print(f"Faina bot starting on port {port}", flush=True)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
