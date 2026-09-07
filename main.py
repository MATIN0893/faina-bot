import asyncio
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

client = genai.Client(
    api_key=GEMINI_KEY,
    http_options=genai_types.HttpOptions(
        timeout=15000,
        retry_options=genai_types.HttpRetryOptions(attempts=1),
    ),
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я Фаина, ваш помощник. Чем могу помочь?")


async def ask_gemini(prompt: str):
    for model in (
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ):
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

    print(f"Telegram message received chat_id={message.chat.id} text_len={len(message.text)}")

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

    try:
        text = await ask_gemini(prompt)
        if text:
            await message.answer(text)
        else:
            await message.answer("Сейчас AI временно занят. Попробуй ещё раз через несколько секунд.")
    except Exception as e:
        print(f"Telegram handler failed: {type(e).__name__}: {e}")
        try:
            await message.answer("Не удалось обработать сообщение. Попробуй ещё раз.")
        except Exception:
            pass


async def health_check(request):
    return web.Response(text="Bot is live!")


async def configure_webhook():
    webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
    allowed_updates = dp.resolve_used_update_types()

    for attempt in range(1, 4):
        try:
            print(f"Setting Telegram webhook attempt={attempt} url={webhook_url}")
            await bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET or None,
                drop_pending_updates=False,
                max_connections=20,
                allowed_updates=allowed_updates,
            )
            print("Telegram webhook set successfully")

            try:
                info = await bot.get_webhook_info()
                print(
                    "Webhook ready "
                    f"url={info.url} pending={info.pending_update_count} "
                    f"last_error={getattr(info, 'last_error_message', None)!r}"
                )
            except Exception as e:
                print(f"Webhook info check failed: {type(e).__name__}: {e}")
            return
        except Exception as e:
            print(f"Webhook set failed attempt={attempt}: {type(e).__name__}: {e}")
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)

    print("Webhook setup failed after 3 attempts; service remains online")


async def on_startup(bot: Bot):
    await configure_webhook()


def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    dp.startup.register(on_startup)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET or None,
        handle_in_background=True,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    print(f"Faina bot starting on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
