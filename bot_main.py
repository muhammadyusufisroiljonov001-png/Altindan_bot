# bot_main.py
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")  # misol: https://altindan-web.onrender.com
GROUP_ID = os.getenv("GROUP_ID")  # ixtiyoriy: -100...

if not TOKEN:
    logger.error("TOKEN not set in env")
    raise SystemExit("Missing TOKEN environment variable")

# Start / menu handler — yuboradi inline tugmalar (WebApp tugma)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = []
    if WEBAPP_URL:
        kb.append([ InlineKeyboardButton("📦 Открыть", web_app=WebAppInfo(url=WEBAPP_URL)) ])
    else:
        kb.append([ InlineKeyboardButton("  Открыть ", callback_data="no_webapp") ])
    kb.append([ InlineKeyboardButton("✍️ Оставить отзыв", callback_data="feedback") ])
    await update.message.reply_text("Добро пожаловать", reply_markup=InlineKeyboardMarkup(kb))

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# /setgroup - agar guruhga botni admin qilib qo'ysang, guruh ichida /setgroup yozib id olasiz
async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        await update.message.reply_text("Chat not found")
        return
    gid = chat.id
    try:
        import json
        with open('settings.json', 'w', encoding='utf-8') as f:
            json.dump({"group_id": gid}, f, ensure_ascii=False, indent=2)
        await update.message.reply_text(f"Group id saved: {gid}")
    except Exception as e:
        await update.message.reply_text(f"Cannot save group id: {e}")

# simple fallback
async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos /menu yoki /start ni bosing.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fallback_text))

    logger.info("Starting bot (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()



