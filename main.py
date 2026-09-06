import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import types as genai_types

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not GEMINI_KEY:
    raise RuntimeError("GEMINI_KEY is not set")

# Short timeout + one SDK attempt prevents Gemini's built-in retries from
# making Telegram users wait tens of seconds when a model is overloaded.
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
    # Fast model first; reliable fallback if the first model is temporarily busy.
    for model in ("gemini-3.5-flash-lite", "gemini-3.6-flash"):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
            )
            text = getattr(response, "text", None)
            if text:
                return text, model
            print(f"Gemini returned empty response from {model}")
        except Exception as e:
            print(f"Gemini {model} failed: {type(e).__name__}: {e}")
    return None, None

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

    # Telegram shows that the bot is working while Gemini generates the answer.
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    text, model = await ask_gemini(prompt)

    if text:
        print(f"Gemini response OK: {model}")
        await message.answer(text)
    else:
        print("Gemini failed on both primary and fallback models")
        await message.answer("Сейчас AI временно занят. Попробуй ещё раз через несколько секунд.")

async def handle_health_check(request):
    return web.Response(text="Bot is live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
