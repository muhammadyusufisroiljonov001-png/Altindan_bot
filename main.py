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
```

---

## File: `requirements.txt`

```
Flask>=2.0
aiogram==3.4.1
aiohttp>=3.8
python-dotenv>=1.0
gunicorn>=21.2
Werkzeug>=2.0
```

---

## File: `Procfile`

```
web: gunicorn --bind 0.0.0.0:$PORT main:app
worker: python main.py
```

---

## File: `runtime.txt`

```
python-3.11.16
```

---

## File: `.gitignore`

```
.env
__pycache__/
*.pyc
.vscode/
instance/
```

---

## File: `database.json` (expanded — 9 products)

```json
{
  "products": [
    {
      "id": "p1",
      "name_uz": "Go'shtli chuchvara — 1 kg",
      "name_ru": "Пельмени с говядиной — 1 кг",
      "price": 45000,
      "image": "images/chuchvara_beef_1kg.jpg",
      "desc_uz": "Yuqori sifatli mol go‘shtidan tayyorlangan.",
      "desc_ru": "Приготовлены из высококачественной говядины."
    },
    {
      "id": "p2",
      "name_uz": "Tovuqli chuchvara — 1 kg",
      "name_ru": "Пельмени с курицей — 1 кг",
      "price": 33000,
      "image": "images/chuchvara_chicken_1kg.jpg",
      "desc_uz": "Yengil va mazali tovuq go‘shtidan tayyorlangan.",
      "desc_ru": "Нежные и вкусные пельмени с курицей."
    },
    {
      "id": "p3",
      "name_uz": "Tovuqli chuchvara — 500 g",
      "name_ru": "Пельмени с курицей — 500 г",
      "price": 17500,
      "image": "images/chuchvara_chicken_500g.jpg",
      "desc_uz": "Kichik oila uchun qulay o‘ram.",
      "desc_ru": "Удобная упаковка для небольшой семьи."
    },
    {
      "id": "p4",
      "name_uz": "Qo'ziqorinli chuchvara — 1 kg",
      "name_ru": "Пельмени с грибами — 1 кг",
      "price": 38000,
      "image": "images/chuchvara_mushroom_1kg.jpg",
      "desc_uz": "Tabiiy qoʻziqorinlar va maxsus ziravorlar bilan.",
      "desc_ru": "С натуральными грибами и специальными приправами."
    },
    {
      "id": "p5",
      "name_uz": "Krem-sirli chuchvara — 1 kg",
      "name_ru": "Пельмени с сыром — 1 кг",
      "price": 39000,
      "image": "images/chuchvara_cheese_1kg.jpg",
      "desc_uz": "Ichida eritilgan krem-sir bilan boy taʼm.",
      "desc_ru": "Богатый вкус с расплавленным крем-сыром внутри."
    },
    {
      "id": "p6",
      "name_uz": "Sabzavotli vegetarian chuchvara — 1 kg",
      "name_ru": "Вегетарианские пельмени с овощами — 1 кг",
      "price": 30000,
      "image": "images/chuchvara_veggie_1kg.jpg",
      "desc_uz": "Sabzavotlar bilan to‘ldirilgan, vegetarian uchun mos.",
      "desc_ru": "С начинкой из овощей, подходит для вегетарианцев."
    },
    {
      "id": "p7",
      "name_uz": "Qizil baliqli chuchvara — 1 kg",
      "name_ru": "Пельмени с лососем — 1 кг",
      "price": 52000,
      "image": "images/chuchvara_salmon_1kg.jpg",
      "desc_uz": "Yuqori sifatli qizil baliqdan tayyorlangan.",
      "desc_ru": "Приготовлены из высококачественного лосося."
    },
    {
      "id": "p8",
      "name_uz": "Achchiq qoʻy goʻshtli chuchvara — 1 kg",
      "name_ru": "Острые пельмени со бараниной — 1 кг",
      "price": 47000,
      "image": "images/chuchvara_spicy_lamb_1kg.jpg",
      "desc_uz": "Anʼanaviy ziravorlar bilan achchiq lazzat.",
      "desc_ru": "Острый вкус с традиционными специями."
    },
    {
      "id": "p9",
      "name_uz": "Aralash toʻplam (3x500g) — sovg'a paketi",
      "name_ru": "Сборный набор (3x500г) — подарочная упаковка",
      "price": 82000,
      "image": "images/chuchvara_mixed_pack_3x500g.jpg",
      "desc_uz": "Turli xil taʼmlar: mol, tovuq va qoʻziqorin — oilaviy variant.",
      "desc_ru": "Разные вкусы: говядина, курица и грибы — для семейного употребления."
    }
  ],
  "orders": [],
  "admins": [
    {
      "username": "admin",
      "password": "12345"
    }
  ]
}
```

---

## `templates/index.html`

```html
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Menu</title></head>
<body>
  <h1>Menu</h1>
  <ul>
    {% for p in products %}
      <li>
        <a href="{{ url_for('order', product_id=p.id) }}">
          {{ p['name_ru'] if lang=='ru' else p['name_uz'] }} — {{ p.price }} сум
        </a>
      </li>
    {% endfor %}
  </ul>
</body>
</html>
```

---

## `templates/order.html`

```html
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Order</title></head>
<body>
  <h1>{{ product['name_ru'] if lang=='ru' else product['name_uz'] }}</h1>
  <form method="post">
    <input type="hidden" name="lang" value="{{ lang }}">
    <label>Ism: <input name="name"></label><br>
    <label>Tel: <input name="phone"></label><br>
    <label>Soni: <input name="qty" value="1"></label><br>
    <label>Izoh: <textarea name="note"></textarea></label><br>
    <button type="submit">Buyurtma</button>
  </form>
</body>
</html>
```

---

## `templates/ordered.html`

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Ordered</title></head>
<body>
  <h1>Buyurtma qabul qilindi</h1>
  <p>Buyurtma ID: {{ order.id }}</p>
  <p>Mahsulot: {{ order.product_name }}</p>
  <p>Soni: {{ order.qty }}</p>
  <a href="{{ url_for('index') }}">Orqaga</a>
</body></html>
```

---

## `templates/login.html`

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Admin login</title></head>
<body>
  <h1>Admin login</h1>
  {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
  <form method="post">
    <label>Username: <input name="username"></label><br>
    <label>Password: <input name="password" type="password"></label><br>
    <button type="submit">Kirish</button>
  </form>
</body></html>
```

---

## `templates/admin.html`

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Admin</title></head>
<body>
  <h1>Admin panel</h1>
  <h2>Products</h2>
  <ul>
  {% for p in products %}
    <li>{{ p.id }} - {{ p.name_ru }}</li>
  {% endfor %}
  </ul>
  <h2>Orders</h2>
  <ul>
  {% for o in orders %}
    <li>{{ o.id }} — {{ o.product_name }} — {{ o.name }}</li>
  {% endfor %}
  </ul>
  <a href="{{ url_for('admin_logout') }}">Logout</a>
</body></html>
```

---

## `.env.example`

```
BOT_TOKEN=
ORDER_GROUP_ID=
WEB_URL=
SECRET_KEY=
```

---

## `README.md` (brief)

```markdown
# Altindan_bot — Flask + aiogram mini app

Simple web shop + Telegram bot. Uses JSON file as DB.

## Run locally
1. Copy `.env.example` to `.env` and set your BOT_TOKEN and ORDER_GROUP_ID.
2. `pip install -r requirements.txt`
3. `python main.py`
4. Open `http://127.0.0.1:5000`

## Deploy (Render)
- Add `runtime.txt` with `python-3.11.16`
- Add `Procfile` and `requirements.txt`
- In Render → Environment variables add `BOT_TOKEN` and `ORDER_GROUP_ID`
```
