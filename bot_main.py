import os, json
from uuid import uuid4
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

ORDERS_FILE = "orders.json"
SETTINGS_FILE = "settings.json"

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

orders = load_json(ORDERS_FILE, [])
settings = load_json(SETTINGS_FILE, {})
# settings example: {"group_id": null, "user_langs": {}}

TOKEN = os.environ.get("TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")  # e.g. https://your-app.up.railway.app

# translations
TRANSLATIONS = {
    "uz": {
        "start": "Salom! /menu orqali menyuni oching.",
        "menu_text": "Menyu:",
        "group_saved": "Guruh saqlandi.",
        "order_received_user": "✅ Buyurtmangiz qabul qilindi! Tez orada guruhga yuboriladi.",
        "webapp_not_config": "WEBAPP_URL sozlanmagan."
    },
    "ru": {
        "start": "Привет! Открой меню через /menu.",
        "menu_text": "Меню:",
        "group_saved": "Группа сохранена.",
        "order_received_user": "✅ Ваш заказ принят! Скоро отправим в группу.",
        "webapp_not_config": "WEBAPP_URL не настроен."
    }
}

def t(key, lang):
    if lang not in TRANSLATIONS:
        lang = "uz"
    return TRANSLATIONS[lang].get(key, TRANSLATIONS["uz"].get(key, key))

def get_user_lang(user_id, user_obj=None):
    user_langs = settings.get("user_langs", {})
    uid = str(user_id)
    if uid in user_langs:
        return user_langs[uid]
    if user_obj and getattr(user_obj, "language_code", None):
        lc = user_obj.language_code[:2].lower()
        if lc == "ru":
            return "ru"
        if lc in ("uz","uzb"):
            return "uz"
    return "uz"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update.effective_user.id, update.effective_user)
    await update.message.reply_text(t("start", lang))

async def setlang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or args[0] not in ("uz","ru"):
        await update.message.reply_text("Usage: /setlang uz  OR  /setlang ru")
        return
    lang = args[0]
    uid = str(update.effective_user.id)
    settings.setdefault("user_langs", {})[uid] = lang
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text(f"OK — language set to {lang}")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_lang(user.id, user)
    if not WEBAPP_URL:
        await update.message.reply_text(t("webapp_not_config", lang))
        return
    url = WEBAPP_URL
    if "?" in url:
        url = f"{url}&lang={lang}"
    else:
        url = f"{url}?lang={lang}"
    kb = InlineKeyboardMarkup.from_row([
        InlineKeyboardButton("🛍 Открыть меню", web_app=WebAppInfo(url=url))
    ])
    await update.message.reply_text(t("menu_text", lang), reply_markup=kb)

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    lang = get_user_lang(user.id, user)
    if chat.type in ("group", "supergroup"):
        settings["group_id"] = chat.id
        save_json(SETTINGS_FILE, settings)
        await update.message.reply_text(t("group_saved", lang))
    else:
        await update.message.reply_text("Iltimos bu buyruqni guruh ichida yuboring.")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    import csv
    filename = f"orders_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id","username","product","qty","address","timestamp","lang"])
        for o in orders:
            writer.writerow([o.get("id"), o.get("username"), o.get("product"), o.get("qty"), o.get("address"), o.get("timestamp"), o.get("lang", "")])
    await context.bot.send_document(chat_id=chat_id, document=open(filename,"rb"))
    try: os.remove(filename)
    except: pass

async def webapp_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not getattr(msg, "web_app_data", None):
        return
    data_str = msg.web_app_data.data
    try:
        payload = json.loads(data_str)
    except:
        payload = {"raw": data_str}
    lang = payload.get("lang") or get_user_lang(msg.from_user.id, msg.from_user)
    order = {
        "id": str(uuid4()),
        "user_id": msg.from_user.id,
        "username": msg.from_user.username or f"{msg.from_user.first_name or ''}",
        "product": payload.get("product"),
        "qty": payload.get("qty"),
        "address": payload.get("address"),
        "timestamp": payload.get("time") or datetime.utcnow().isoformat(),
        "lang": lang,
        "raw": payload
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    await msg.reply_text(t("order_received_user", lang))
    group_id = settings.get("group_id")
    if group_id:
        if lang == "ru":
            txt = (f"📥 *Новый заказ*\n\n"
                   f"ID: `{order['id']}`\n"
                   f"From: @{order['username']} (`{order['user_id']}`)\n"
                   f"Product: {order['product']}\nQty: {order['qty']}\nAddress: {order['address']}\nTime: {order['timestamp']}")
        else:
            txt = (f"📥 *Yangi buyurtma*\n\n"
                   f"ID: `{order['id']}`\n"
                   f"From: @{order['username']} (`{order['user_id']}`)\n"
                   f"Product: {order['product']}\nQty: {order['qty']}\nAddress: {order['address']}\nTime: {order['timestamp']}")
        try:
            await context.bot.send_message(chat_id=group_id, text=txt, parse_mode="Markdown")
        except Exception as e:
            print("Group send error:", e)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("setlang", setlang))
    app.add_handler(MessageHandler(filters.ALL & filters.UpdateType.MESSAGE, webapp_data_handler))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
