import os, json, base64, logging
import httpx
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("matin-agent")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "MATIN0893/faina-bot")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "matin-agent")
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0") or 0)
ADMIN_USERNAME = os.environ.get("ADMIN_TELEGRAM_USERNAME", "MATIN_0893").lstrip("@").lower()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_FILE_BYTES = 90000

app = FastAPI(title="MATIN Agent")

@app.get("/")
async def root():
    return {"service":"MATIN Agent","status":"ok"}

@app.get("/health")
async def health():
    return {"status":"ok","telegram":bool(BOT_TOKEN),"gemini":bool(GEMINI_KEY),"github":bool(GITHUB_TOKEN)}

def allowed(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if ADMIN_ID and user.id == ADMIN_ID:
        return True
    return bool(user.username and user.username.lower() == ADMIN_USERNAME)

async def gh(method: str, url: str, **kwargs):
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept":"application/vnd.github+json", "X-GitHub-Api-Version":"2022-11-28"}
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.request(method, url, headers=headers, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None

async def repo_tree():
    data = await gh("GET", f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1")
    return [x["path"] for x in data.get("tree",[]) if x.get("type") == "blob"]

async def read_file(path: str):
    data = await gh("GET", f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}")
    if data.get("size",0) > MAX_FILE_BYTES:
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")

async def write_file(path: str, content: str, message: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    existing = None
    try:
        existing = await gh("GET", url + f"?ref={GITHUB_BRANCH}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404: raise
    body = {"message":message,"content":base64.b64encode(content.encode()).decode(),"branch":GITHUB_BRANCH}
    if existing: body["sha"] = existing["sha"]
    return await gh("PUT", url, json=body)

async def delete_file(path: str, message: str):
    url=f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    existing=await gh("GET", url+f"?ref={GITHUB_BRANCH}")
    return await gh("DELETE", url, json={"message":message,"sha":existing["sha"],"branch":GITHUB_BRANCH})

async def gemini(parts: list[dict], system: str = ""):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    all_parts = ([{"text":system}] if system else []) + parts
    payload={"contents":[{"role":"user","parts":all_parts}],"generationConfig":{"temperature":0.15,"responseMimeType":"application/json"}}
    async with httpx.AsyncClient(timeout=120) as c:
        r=await c.post(url,json=payload)
        r.raise_for_status()
        data=r.json()
    text=data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)

async def plan(task: str, paths: list[str]):
    system="""You are MATIN Agent, a senior software engineer. Return ONLY valid JSON: {\"paths\":[\"existing/path\"],\"reason\":\"short\"}. Select only relevant existing repository paths. Never invent paths. Prefer 1-8 files."""
    return await gemini([{"text":f"TASK:\n{task}\n\nREPOSITORY FILES:\n"+"\n".join(paths)}],system)

async def implement(task: str, files: dict[str,str]):
    system="""You are MATIN Agent, an autonomous senior software engineer. Return ONLY valid JSON: {\"summary\":\"...\",\"writes\":[{\"path\":\"path\",\"content\":\"complete file content\"}],\"deletes\":[\"path\"]}. For writes output complete contents, not patches. You may create files. Make the smallest correct production-quality change. Preserve unrelated code. Never expose secrets."""
    context="\n\n".join(f"===== {p} =====\n{c}" for p,c in files.items())
    return await gemini([{"text":f"TASK:\n{task}\n\nCURRENT FILES:\n{context}"}],system)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("🤖 MATIN Agent online.\n\nОтправь задачу текстом или голосом. Я анализирую код → меняю GitHub → Render автоматически деплоит.\n\n/status /files /help")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    try:
        paths=await repo_tree()
        await update.message.reply_text(f"🟢 MATIN Agent\nRepo: {GITHUB_REPO}\nBranch: {GITHUB_BRANCH}\nFiles: {len(paths)}")
    except Exception as e: await update.message.reply_text(f"🔴 GitHub error: {e}")

async def files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    try:
        paths=await repo_tree()
        await update.message.reply_text(("📁 Files:\n"+"\n".join(paths[:150]))[:3900])
    except Exception as e: await update.message.reply_text(f"🔴 {e}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("Просто отправляй задачу. Например: «исправь ошибку авторизации», «добавь endpoint», «создай модуль». Голос тоже принимается.")

async def transcribe_voice(update: Update, bot):
    tg_file=await bot.get_file(update.message.voice.file_id)
    data=await tg_file.download_as_bytearray()
    b64=base64.b64encode(bytes(data)).decode()
    result=await gemini([
        {"text":"Transcribe this Russian/Tajik voice message as a coding instruction. Return JSON {\"text\":\"...\"}."},
        {"inline_data":{"mime_type":"audio/ogg","data":b64}}
    ])
    return result.get("text","")

async def process_task(update: Update, task: str):
    msg=await update.message.reply_text("🧠 Анализирую проект…")
    try:
        paths=await repo_tree()
        selected=(await plan(task,paths)).get("paths",[])[:8]
        files={}
        for path in selected:
            content=await read_file(path)
            if content is not None: files[path]=content
        result=await implement(task,files)
        writes=result.get("writes",[]); deletes=result.get("deletes",[])
        for item in writes: await write_file(item["path"],item["content"],f"MATIN Agent: {task[:60]}")
        for path in deletes: await delete_file(path,f"MATIN Agent: remove {path}")
        await msg.edit_text(f"✅ Готово\n\n{result.get('summary','Изменения внесены.')}\n\nИзменено: {len(writes)}\nУдалено: {len(deletes)}\n\nGitHub обновлён.")
    except Exception as e:
        log.exception("task failed")
        await msg.edit_text(f"❌ Ошибка агента:\n{str(e)[:3500]}")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await process_task(update, update.message.text.strip())

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("🎙️ Распознаю голос…")
    try:
        text=await transcribe_voice(update,context.bot)
        if not text: raise RuntimeError("Не удалось распознать голос")
        await process_task(update,text)
    except Exception as e: await update.message.reply_text(f"❌ Голос: {str(e)[:3000]}")

def main():
    if not BOT_TOKEN or not GEMINI_KEY or not GITHUB_TOKEN: raise RuntimeError("Set BOT_TOKEN, GEMINI_KEY and GITHUB_TOKEN")
    tg=Application.builder().token(BOT_TOKEN).build()
    tg.add_handler(CommandHandler("start",start)); tg.add_handler(CommandHandler("status",status)); tg.add_handler(CommandHandler("files",files_cmd)); tg.add_handler(CommandHandler("help",help_cmd))
    tg.add_handler(MessageHandler(filters.VOICE,voice_handler)); tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    tg.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import threading, uvicorn
    threading.Thread(target=lambda: uvicorn.run(app,host="0.0.0.0",port=int(os.environ.get("PORT","10000"))),daemon=True).start()
    main()
