import os
import json
import csv
from datetime import datetime
from uuid import uuid4

from telegram import Update, ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

ORDERS_FILE = "orders.json"
SETTINGS_FILE = "settings.json"

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

orders = load_json(ORDERS_FILE, [])
settings = load_json(SETTINGS_FILE, {})

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable is required")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Buyurtmangizni yozing, men uni guruhga yuboraman.")

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        settings["group_id"] = chat.id
        save_json(SETTINGS_FILE, settings)
        await update.message.reply_text("Bu guruh buyurtmalar uchun saqlandi! Endi har bir buyurtma shu yerga keladi.")
    else:
        await update.message.reply_text("Iltimos, bu buyruqni guruh ichida yuboring.")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)

    filename = f"orders_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id", "user_id", "username", "text", "timestamp"])
        for o in orders:
            writer.writerow([o["id"], o["user_id"], o["username"], o["text"], o["timestamp"]])

    await context.bot.send_document(chat_id=chat_id, document=open(filename, "rb"))
    os.remove(filename)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    text = msg.text.strip()
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        return

    order = {
        "id": str(uuid4()),
        "user_id": user.id,
        "username": user.username or f"{user.first_name or ''}",
        "text": text,
        "timestamp": datetime.utcnow().isoformat()
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)

    await msg.reply_text("Buyurtma qabul qilindi! ✔️")

    group_id = settings.get("group_id")
    if group_id:
        summary = (
            f"📥 *Yangi buyurtma*\n\n"
            f"ID: `{order['id']}`\n"
            f"From: @{order['username']}\n"
            f"Text: {order['text']}\n"
            f"Time: {order['timestamp']}"
        )
        await context.bot.send_message(chat_id=group_id, text=summary, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()

