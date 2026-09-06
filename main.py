import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from docx import Document
from openpyxl import Workbook
from google import genai
from google.genai import types as gtypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8788964110:AAF2HPogUT5TZritKmvA2UOQKIGRwIG-XHI")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AQ.Ab8RN6JT_g3Az9mFgTYYQq2Ljw62em6y46E_sPuEOOzL3vRTWw")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    welcome_text = (
        "Ассалому алейкум! Я Фаина — ваш школьный помощник и секретарь.\n\n"
        "Я помогу вам быстро подготовить любые документы:\n"
        "• Отправьте фото списка учеников или рукописного документа.\n"
        "• Отправьте текст или задачу (приказы, поощрения, рефераты, таблицы).\n\n"
        "Я приготовлю всё в формате Word или Excel с правильным таджикским алфавитом (Ғ, Ӣ, Қ, Ӯ, Ҳ, Ҷ)!"
    )
    await message.answer(welcome_text)

@dp.message()
async def handle_message(message: types.Message):
    status_msg = await message.answer("Помощница Фаина обрабатывает ваш запрос... ⏳")
    
    sys_prompt = (
        "Ты — идеальный школьный секретарь. Твоя задача — формировать школьные документы "
        "(приказы, отчеты, списки учеников, рефераты, поощрения). "
        "ОБЯЗАТЕЛЬНО соблюдай правила таджикского алфавита и правильно пиши спецбуквы: Ғ, Ӣ, Қ, Ӯ, Ҳ, Ҷ."
    )

    try:
        current_gemini_key = os.environ.get("GEMINI_KEY", GEMINI_KEY)
        if not current_gemini_key:
            await status_msg.edit_text("Ошибка: Не указан GEMINI_KEY в настройках Render.")
            return

        ai_client = genai.Client(api_key=current_gemini_key)

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
        await status_msg.edit_text(f"Ошибка при обработке: {e}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
