import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import google.generativeai as genai

# Инициализация токенов из Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# Настройка Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Инициализация aiogram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хэндлеры бота
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я Фаина, ваш помощник. Чем могу помочь?")

@dp.message()
async def handle_message(message: types.Message):
    try:
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except Exception as e:
        await message.answer("Произошла ошибка при обработке запроса.")

# Фейковый веб-сервер для бесплатного тарифа Render
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
    # 1. Запуск веб-сервера для Render
    await start_web_server()
    
    # 2. Удаление старых вебхуков и запуск бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
