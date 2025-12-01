# main.py
"""
Mini web + Telegram bot (Flask + aiogram v3)
Simple JSON DB, templates, images folder.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import datetime
import threading
import asyncio
import uuid
import time
from pathlib import Path
from urllib.request import urlretrieve
from flask import (
    Flask, render_template, request, send_from_directory,
    redirect, url_for, session, jsonify
)
from werkzeug.utils import secure_filename

# Optional Telegram
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.filters import Command
    from aiogram.fsm.storage.memory import MemoryStorage
except Exception:
    Bot = None
    Dispatcher = None
    types = None
    Command = None
    MemoryStorage = None

BASE = Path(__file__).parent
DB_FILE = BASE / "database.json"
TEMPLATES = BASE / "templates"
STATIC = BASE / "static"
IMAGES = STATIC / "images"

# Ensure folders
TEMPLATES.mkdir(exist_ok=True)
STATIC.mkdir(exist_ok=True)
IMAGES.mkdir(parents=True, exist_ok=True)

# Env / config
BOT_TOKEN = os.environ.get("BOT_TOKEN") or ""
ORDER_GROUP_ID = None
try:
    gid_raw = os.environ.get("ORDER_GROUP_ID")
    if gid_raw:
        ORDER_GROUP_ID = int(gid_raw)
except Exception:
    ORDER_GROUP_ID = None

WEB_URL = os.environ.get("WEB_URL") or ""
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}

# --- Database helpers (simple JSON) ---
def ensure_db():
    if not DB_FILE.exists():
        sample = {
            "products": [
                {
                    "id": "p1",
                    "name_uz": "Go'shtli chuchvara — 1 kg",
                    "name_ru": "Пельмени с говядиной — 1 кг",
                    "price": 45000,
                    "image": "images/chuchvara_beef_1kg.jpg",
                    "desc_uz": "Yuqori sifatli mol go‘shtidan tayyorlangan.",
                    "desc_ru": "Приготовлены из высококачественной говядины."
                }
            ],
            "orders": [],
            "admins": [{"username": "admin", "password": "12345"}]
        }
        DB_FILE.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

def read_db():
    ensure_db()
    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"products": [], "orders": [], "admins": []}

def write_db(data):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Utils ---
def find_product(pid):
    db = read_db()
    for p in db.get("products", []):
        if p.get("id") == pid:
            return p
    return None

def generate_id(prefix="p"):
    return prefix + uuid.uuid4().hex[:8]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# Create placeholder images if missing
def ensure_sample_images():
    db = read_db()
    for p in db.get("products", []):
        img = p.get("image")
        if img:
            path = IMAGES / img
            if not path.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    urlretrieve(f"https://via.placeholder.com/800x400?text={p.get('id')}", str(path))
                except Exception:
                    path.write_text("", encoding="utf-8")
ensure_sample_images()

# --- Flask app and routes ---
app = Flask(__name__, template_folder=str(TEMPLATES), static_folder=str(STATIC))
app.secret_key = SECRET_KEY

@app.route("/")
def index():
    lang = request.args.get("lang", "ru")
    db = read_db()
    products = db.get("products", [])
    base_url = WEB_URL if WEB_URL else request.host_url.rstrip("/")
    return render_template("index.html", products=products, lang=lang, web_url=base_url)

@app.route("/order/<product_id>", methods=["GET", "POST"])
def order(product_id):
    lang = request.args.get("lang", request.form.get("lang", "ru"))
    product = find_product(product_id)
    if not product:
        return "Mahsulot topilmadi", 404

    if request.method == "POST":
        name = request.form.get("name", "Anonim")
        phone = request.form.get("phone", "")
        try:
            qty = float(request.form.get("qty", "1"))
        except:
            qty = 1.0
        note = request.form.get("note", "")

        order = {
            "id": "o" + uuid.uuid4().hex[:8],
            "product_id": product_id,
            "product_name": product.get(f"name_{lang}", product.get("name_ru")),
            "price": product.get("price", 0),
            "qty": qty,
            "name": name,
            "phone": phone,
            "note": note,
            "time": datetime.datetime.now().isoformat()
        }

        db = read_db()
        db["orders"].append(order)
        write_db(db)

        # send async telegram
        try:
            if globals().get("aioloop"):
                asyncio.run_coroutine_threadsafe(
                    send_order_to_group_async(order), globals()["aioloop"]
                )
        except Exception as e:
            print("Telegram send error:", e)

        return render_template("ordered.html", order=order, lang=lang)

    return render_template("order.html", product=product, lang=lang)

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC), filename)

# --- Admin ---
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        db = read_db()
        for a in db.get("admins", []):
            if a["username"] == username and a["password"] == password:
                session["admin"] = username
                return redirect(url_for("admin_panel"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html", error=None)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

def admin_required(f):
    def wrap(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    wrap.__name__ = f.__name__
    return wrap

@app.route("/admin")
@admin_required
def admin_panel():
    lang = request.args.get("lang", "ru")
    db = read_db()
    return render_template("admin.html", products=db["products"], orders=db["orders"], lang=lang)

# --- API endpoints ---
@app.route("/api/products", methods=["GET", "POST"])
def api_products():
    if request.method == "GET":
        db = read_db()
        return jsonify(db["products"])

    if not session.get("admin"):
        return jsonify({"error": "auth required"}), 403

    data = request.form or request.json or {}
    pid = generate_id("p")
    product = {
        "id": pid,
        "name_uz": data.get("name_uz"),
        "name_ru": data.get("name_ru"),
        "price": float(data.get("price", 0)),
        "image": data.get("image", ""),
        "desc_uz": data.get("desc_uz", ""),
        "desc_ru": data.get("desc_ru", "")
    }

    db = read_db()
    db["products"].append(product)
    write_db(db)
    return jsonify(product), 201

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not session.get("admin"):
        return jsonify({"error": "auth required"}), 403
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "empty filename"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": "invalid file type"}), 400

    filename = secure_filename(f.filename)
    filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    save_path = IMAGES / filename
    f.save(str(save_path))
    return jsonify({
        "filename": filename,
        "url": f"images/{filename}"
    }), 201

# --- Telegram setup ---
bot = None
dp = None
if BOT_TOKEN and Bot:
    try:
        bot = Bot(token=BOT_TOKEN)
        storage = MemoryStorage() if MemoryStorage else None
        dp = Dispatcher(storage=storage)
    except Exception as e:
        print("Aiogram init error:", e)
        bot = None
        dp = None

def build_text(o):
    return (
        f"🆕 Yangi buyurtma\n"
        f"Mahsulot: {o['product_name']}\n"
        f"Miqdor: {o['qty']}\n"
        f"Ism: {o['name']}\n"
        f"Tel: {o['phone']}\n"
        f"Izoh: {o['note']}\n"
        f"Vaqt: {o['time']}"
    )

async def send_order_to_group_async(order):
    if not bot:
        return
    if ORDER_GROUP_ID:
        try:
            await bot.send_message(ORDER_GROUP_ID, build_text(order))
        except Exception as e:
            print("Failed to send order to group:", e)

if dp and types:
    @dp.message(Command("start"))
    async def start_cmd(m: types.Message):
        kb = []
        if WEB_URL:
            kb.append([
                types.InlineKeyboardButton(text="📋 Меню", web_app=types.WebAppInfo(url=f"{WEB_URL}?lang=ru"))
            ])
            kb.append([
                types.InlineKeyboardButton(text="🇺🇿 Menyu", web_app=types.WebAppInfo(url=f"{WEB_URL}?lang=uz"))
            ])
        markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
        await m.answer("Добро пожаловать", reply_markup=markup)

# --- Run server + bot ---
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)

def run_bot_loop():
    if not dp or not bot:
        print("Bot not configured or aiogram missing. Running web only.")
        return

    aioloop = asyncio.new_event_loop()
    asyncio.set_event_loop(aioloop)
    globals()["aioloop"] = aioloop

    print("Starting aiogram polling...")
    try:
        aioloop.run_until_complete(dp.start_polling(bot))
    except Exception as e:
        print("Polling stopped:", e)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Flask started.")

    if not bot or not dp:
        print("Web only mode (Telegram disabled).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down.")
    else:
        run_bot_loop()
