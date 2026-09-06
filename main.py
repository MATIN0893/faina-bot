import os
import asyncio
import traceback
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not GEMINI_KEY:
    raise RuntimeError("GEMINI_KEY is not set")

client = genai.Client(api_key=GEMINI_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я Фаина, ваш помощник. Чем могу помочь?")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    prompt = (
        "Ты Фаина — вежливый и полезный AI-помощник. "
        "Отвечай на том же языке, на котором написал пользователь. "
        "Если пользователь пишет на таджикском, отвечай на таджикском. "
        "Не упоминай внутренние ошибки, API или технические детали.\n\n"
        f"Сообщение пользователя:\n{message.text}"
    )

    last_error = None
    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3.6-flash",
                contents=prompt,
            )
            text = getattr(response, "text", None)
            if text:
                await message.answer(text)
                return
            last_error = "Gemini returned an empty response"
        except Exception as e:
            last_error = repr(e)
            print(f"Ошибка Gemini, попытка {attempt + 1}/3: {last_error}")
            traceback.print_exc()
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))

    print(f"Gemini окончательно не ответил: {last_error}")
    await message.answer("Сейчас временно не удалось получить ответ. Попробуй ещё раз через несколько секунд.")

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
