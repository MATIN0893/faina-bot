import os, json, base64, asyncio, logging, re
from typing import Any
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("matin-agent")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "MATIN0893/matin-agent")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0") or 0)
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
    uid = update.effective_user.id if update.effective_user else 0
    return ADMIN_ID != 0 and uid == ADMIN_ID

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
    raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return raw

async def write_file(path: str, content: str, message: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    existing = None
    try: existing = await gh("GET", url + f"?ref={GITHUB_BRANCH}")
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
    contents=[]
    if system:
        parts=[{"text":system}]+parts
    contents.append({"role":"user","parts":parts})
    payload={"contents":contents,"generationConfig":{"temperature":0.15,"responseMimeType":"application/json"}}
    async with httpx.AsyncClient(timeout=120) as c:
        r=await c.post(url,json=payload)
        r.raise_for_status()
        data=r.json()
    text=data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)

async def plan(task: str, paths: list[str]):
    system="""You are MATIN Agent, a senior software engineer. Return ONLY valid JSON. Decide which repository files are relevant to the user's task. Do not invent paths. JSON: {\"paths\":[\"existing/path\"],\"reason\":\"short\"}. Prefer 1-8 relevant files. If a new file is needed, do not include it; it will be created later."""
    return await gemini([{"text":f"TASK:\n{task}\n\nREPOSITORY FILES:\n"+"\n".join(paths)}],system)

async def implement(task: str, files: dict[str,str]):
    system="""You are MATIN Agent, an autonomous senior software engineer. Return ONLY valid JSON. Make the smallest correct production-quality change. Preserve unrelated code. JSON schema: {\"summary\":\"...\",\"writes\":[{\"path\":\"path\",\"content\":\"complete file content\"}],\"deletes\":[\"path\"]}. For writes, output COMPLETE contents, not patches. You may create new files. Never expose secrets or tokens. If the task is ambiguous, make the safest reasonable implementation."""
    context="\n\n".join(f"===== {p} =====\n{c}" for p,c in files.items())
    return await gemini([{"text":f"TASK:\n{task}\n\nCURRENT FILES:\n{context}"}],system)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("🤖 MATIN Agent online.\n\nНапиши задачу обычным текстом или голосом. Я проанализирую код → внесу изменения в GitHub → Render сам задеплоит.\n\nКоманды: /status /files /help")

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
        text="📁 Files:\n"+"\n".join(paths[:150])
        await update.message.reply_text(text[:3900])
    except Exception as e: await update.message.reply_text(f"🔴 {e}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("Команды: /status — состояние, /files — список файлов.\nПросто отправь задачу: «исправь…», «добавь…», «создай…». Голос тоже принимается.")

async def transcribe_voice(update: Update):
    voice=update.message.voice
    tg_file=await context_bot.get_file(voice.file_id)
    data=await tg_file.download_as_bytearray()
    b64=base64.b64encode(bytes(data)).decode()
    parts=[{"text":"Transcribe this Russian/Tajik voice message exactly as a coding instruction. Return JSON {\\\"text\\\":\\\"...\\\"}."},{"inline_data":{"mime_type":"audio/ogg","data":b64}}]
    result=await gemini(parts)
    return result.get("text","")

context_bot=None

async def handle_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    task=update.message.text.strip()
    if not task: return
    msg=await update.message.reply_text("🧠 Анализирую проект…")
    try:
        paths=await repo_tree()
        p=await plan(task,paths)
        selected=p.get("paths",[])[:8]
        files={}
        for path in selected:
            content=await read_file(path)
            if content is not None: files[path]=content
        result=await implement(task,files)
        writes=result.get("writes",[])
        deletes=result.get("deletes",[])
        for item in writes:
            await write_file(item["path"],item["content"],f"MATIN Agent: {task[:60]}")
        for path in deletes:
            await delete_file(path,f"MATIN Agent: remove {path}")
        summary=result.get("summary","Готово")
        await msg.edit_text(f"✅ Готово\n\n{summary}\n\nИзменено: {len(writes)}\nУдалено: {len(deletes)}\n\nGitHub обновлён. Если Render подключён к ветке — deploy запустится автоматически.")
    except Exception as e:
        log.exception("task failed")
        await msg.edit_text(f"❌ Ошибка агента:\n{str(e)[:3500]}")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    global context_bot
    context_bot=context.bot
    await update.message.reply_text("🎙️ Распознаю голос…")
    try:
        text=await transcribe_voice(update)
        if not text: raise RuntimeError("Не удалось распознать голос")
        update.message.text=text
        await handle_task(update,context)
    except Exception as e:
        await update.message.reply_text(f"❌ Голос: {str(e)[:3000]}")

def main():
    if not BOT_TOKEN or not GEMINI_KEY or not GITHUB_TOKEN:
        raise RuntimeError("Set BOT_TOKEN, GEMINI_KEY and GITHUB_TOKEN")
    global context_bot
    tg=Application.builder().token(BOT_TOKEN).build()
    context_bot=tg.bot
    tg.add_handler(CommandHandler("start",start))
    tg.add_handler(CommandHandler("status",status))
    tg.add_handler(CommandHandler("files",files_cmd))
    tg.add_handler(CommandHandler("help",help_cmd))
    tg.add_handler(MessageHandler(filters.VOICE,voice_handler))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_task))
    tg.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: __import__('uvicorn').run(app,host='0.0.0.0',port=int(os.environ.get('PORT','10000'))),daemon=True).start()
    main()
