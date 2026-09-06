import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiohttp import web
from docx import Document
from openpyxl import Workbook
from google import genai
from google.genai import types as gtypes

# Укажи токен внутри кавычек (только цифры и буквы, без текста от BotFather)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8788964110:AAGikuaBly9IG8VqaCDE5GeCCvg4Aord8SM")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AQ.Ab8RN6JT_g3Az9mFgTYYQq2Ljw62em6y46E_sPuEOOzL3vRTWw")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_KEY)

async def handle_health_check(request):
    return web.Response(text="Faina Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    welcome_text = (
       Ассалому алейкум! 🙋‍♀️ Я Фаина — ваш школьный помощник и секретарь.

Чем я могу вам помочь сегодня?

📥 Просто отправьте текст или фото страницы, а я оформлю готовые файлы Word или Excel:
▫️ Приказы, заявления и протоколы 📄
▫️ Рефераты и учебные материалы 📖
▫️ Списки, таблицы и отчёты 📊

    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message()
async def handle_message(message: types.Message):
    status_msg = await message.answer("Помощница Фаина обрабатывает ваш запрос... ⏳")
    
    sys_prompt = (
        "Ты — идеальный школьный секретарь. Твоя задача — формировать школьные документы "
        "(приказы, отчеты, списки учеников, рефераты, поощрения). "
        "ОБЯЗАТЕЛЬНО соблюдай правила таджикского алфавита и правильно пиши спецбуквы: Ғ, Ӣ, Қ, Ӯ, Ҳ, Ҷ."
    )

    try:
        if message.photo:
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            photo_bytes = await bot.download_file(file_info.file_path)
            
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    sys_prompt,
                    gtypes.Part.from_bytes(data=photo_bytes.read(), mime_type='image/jpeg'),
                    message.caption or "Считай текст/список с этого фото и оформи аккуратно."
                ]
            )
        else:
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"{sys_prompt}\n\nЗапрос пользователя: {message.text}"
            )

        result_text = response.text

        doc = Document()
        doc.add_heading('Школьный документ', level=1)
        doc.add_paragraph(result_text)
        doc_filename = "Document_Faina.docx"
        doc.save(doc_filename)

        wb = Workbook()
        ws = wb.active
        ws.title = "Список"
        for i, line in enumerate(result_text.split("\n"), start=1):
            ws.cell(row=i, column=1, value=line)
        xls_filename = "Table_Faina.xlsx"
        wb.save(xls_filename)

        await message.answer_document(FSInputFile(doc_filename), caption="📄 Ваш документ Word")
        await message.answer_document(FSInputFile(xls_filename), caption="📊 Ваша таблица Excel")
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"Ошибка: {e}")

async def main():
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
