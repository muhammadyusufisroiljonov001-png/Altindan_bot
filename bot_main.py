import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
GROUP_ID = os.getenv("GROUP_ID")  # may be None
WEBAPP_URL = os.getenv("WEBAPP_URL")  # example: https://altindan-web.onrender.com

if not TOKEN:
    logger.error("TOKEN not set in environment")
    raise SystemExit("Missing TOKEN")

# helper to convert GROUP_ID to int when available
def get_group_id_int():
    gid = GROUP_ID or os.getenv("GROUP_ID")
    if not gid:
        return None
    try:
        return int(gid)
    except:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = []
    if WEBAPP_URL:
        kb.append([ InlineKeyboardButton("📦 Открыть", web_app=WebAppInfo(url=WEBAPP_URL)) ])
    else:
        kb.append([ InlineKeyboardButton("📦 Открыть (не настроено)", callback_data="no_webapp") ])
    kb.append([ InlineKeyboardButton("✍️ Оставить отзыв", callback_data="feedback") ])
    await update.message.reply_text("Добро пожаловать", reply_markup=InlineKeyboardMarkup(kb))

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Command to set group id (run this inside the group, as admin). Bot must have permission to read messages.
async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        await update.message.reply_text("Chat not found")
        return
    gid = chat.id
    # Save into a file settings.json (best effort) — note: not persisted across redeploys
    try:
        import json
        with open('settings.json','w',encoding='utf-8') as f:
            json.dump({"group_id": gid}, f, ensure_ascii=False, indent=2)
        await update.message.reply_text(f"Group id saved: {gid}")
    except Exception as e:
        await update.message.reply_text(f"Cannot save group id: {e}")

# Command to show current group id in use
async def show_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = get_group_id_int()
    # if not in env, try settings file
    if not gid:
        try:
            import json
            with open('settings.json','r',encoding='utf-8') as f:
                s = json.load(f)
            gid = s.get('group_id')
        except:
            gid = None
    await update.message.reply_text(f"Using GROUP_ID = {gid}")

# fallback handler for text
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text or ""
    if txt.startswith('/'):
        return
    await update.message.reply_text("Iltimos /menu ni bosing yoki /start.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("groupid", show_group))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))

    logger.info("Starting bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
