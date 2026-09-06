import os
import time
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from google import genai
from google.genai import types as genai_types

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://faina-bot-new.onrender.com").rstrip("/")
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not GEMINI_KEY:
    raise RuntimeError("GEMINI_KEY is not set")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set")

# One SDK attempt per model: no hidden retry delays when Gemini is overloaded.
client = genai.Client(
    api_key=GEMINI_KEY,
    http_options=genai_types.HttpOptions(
        timeout=12000,
        retry_options=genai_types.HttpRetryOptions(attempts=1),
    ),
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я Фаина, ваш помощник. Чем могу помочь?")


async def ask_gemini(prompt: str):
    # Fast model first; one immediate fallback. No 3x retry loop.
    for model in ("gemini-3.5-flash-lite", "gemini-3.6-flash"):
        started = time.monotonic()
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
            )
            text = getattr(response, "text", None)
            elapsed = time.monotonic() - started
            if text:
                print(f"Gemini OK model={model} seconds={elapsed:.2f}")
                return text
            print(f"Gemini empty model={model} seconds={elapsed:.2f}")
        except Exception as e:
            elapsed = time.monotonic() - started
            print(f"Gemini failed model={model} seconds={elapsed:.2f} error={type(e).__name__}: {e}")
    return None


@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    prompt = (
        "Ты Фаина — вежливый и полезный AI-помощник. "
        "Отвечай на том же языке, на котором написал пользователь. "
        "Если пользователь пишет на таджикском, отвечай на таджикском. "
        "Отвечай понятно, естественно и без упоминания API, моделей или внутренних ошибок.\n\n"
        f"Сообщение пользователя:\n{message.text}"
    )

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    text = await ask_gemini(prompt)
    if text:
        await message.answer(text)
    else:
        await message.answer("Сейчас AI временно занят. Попробуй ещё раз через несколько секунд.")


async def health_check(request):
    return web.Response(text="Bot is live!")


async def on_startup(bot: Bot):
    webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    print(f"Webhook set: {webhook_url}")


async def main():
    app = web.Application()
    app.router.add_get("/", health_check)

    dp.startup.register(on_startup)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        handle_in_background=True,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    print(f"Faina bot starting on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
