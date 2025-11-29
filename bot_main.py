import os
import json
import datetime
import threading
import asyncio
from pathlib import Path
from urllib.request import urlretrieve
from flask import Flask, render_template, request, send_from_directory
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ---------- Config ----------
BASE = Path(__file__).parent
DATA_FILE = BASE / "orders.json"
PRODUCT_FILE = BASE / "products.json"
TEMPLATES = BASE / "templates"
STATIC = BASE / "static"
IMAGES = STATIC / "images"

# Ensure folders
TEMPLATES.mkdir(exist_ok=True)
STATIC.mkdir(exist_ok=True)
IMAGES.mkdir(parents=True, exist_ok=True)

# Env
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")            # BotFather token
ORDER_GROUP_ID = None
try:
    gid_raw = os.environ.get("ORDER_GROUP_ID") or os.environ.get("GROUP_ID")
    if gid_raw:
        ORDER_GROUP_ID = int(gid_raw)
except:
    ORDER_GROUP_ID = None
WEB_URL = os.environ.get("WEB_URL") or os.environ.get("WEBAPP_URL") or ""

# ---------- Default static & templates (created if missing) ----------
STYLE = STATIC / "style.css"
if not STYLE.exists():
    STYLE.write_text('''
body{font-family:Arial,Helvetica,sans-serif;background:#fff;color:#111;margin:0;padding:18px}
.container{max-width:1000px;margin:0 auto}
.header{font-size:28px;margin-bottom:14px}
.card{border:1px solid #eee;padding:12px;border-radius:8px;display:inline-block;width:300px;margin:10px;vertical-align:top}
.card img{width:100%;height:160px;object-fit:cover;background:#f6f6f6}
.btn{display:inline-block;padding:8px 12px;border-radius:8px;background:#2b8cff;color:#fff;text-decoration:none}
''', encoding="utf-8")

INDEX_HTML = TEMPLATES / "index.html"
if not INDEX_HTML.exists():
    INDEX_HTML.write_text('''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/style.css"><title>Menu</title></head>
<body><div class="container"><div class="header">Altindan — Menu</div>
<div><a href="?lang=uz">uz</a> | <a href="?lang=ru">ru</a></div>
<div style="margin-top:16px">
{% for p in products %}
  <div class="card">
    <img src="{{ url_for('static', filename='images/'+p.image) }}" alt="{{ p.name_ru }}">
    <h3>{{ p['name_'+(lang if lang in ['uz','ru'] else 'ru')] }}</h3>
    <div style="font-weight:bold;margin-top:8px">{{ p.price }} so'm</div>
    <div style="margin-top:8px"><a class="btn" href="{{ web_url }}/order/{{ p.id }}?lang={{ lang }}">Buyurtma</a></div>
  </div>
{% endfor %}
</div></div></body></html>''', encoding="utf-8")

ORDER_HTML = TEMPLATES / "order.html"
if not ORDER_HTML.exists():
    ORDER_HTML.write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/style.css"></head><body>
<div class="container"><h2>Buyurtma — {{ product['name_ru'] }}</h2>
<form method="post">
<label>Ism: <input name="name" required></label><br><br>
<label>Tel: <input name="phone" required></label><br><br>
<label>Miqdor (kg): <input name="qty" value="1" required></label><br><br>
<label>Izoh:<br><textarea name="note"></textarea></label><br><br>
<input type="hidden" name="lang" value="{{ lang }}">
<button class="btn" type="submit">Yuborish</button>
</form></div></body></html>''', encoding="utf-8")

ORDERED_HTML = TEMPLATES / "ordered.html"
if not ORDERED_HTML.exists():
    ORDERED_HTML.write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/style.css"></head>
<body><div class="container"><h2>Rahmat!</h2><p>Buyurtmangiz qabul qilindi.</p></div></body></html>''', encoding="utf-8")

# ---------- Default products.json ----------
if not PRODUCT_FILE.exists():
    sample = [
        {"id":"p1","name_uz":"Chuchvara 1kg","name_ru":"Чучвара 1кг","price":20000,"image":"p1.jpg"},
        {"id":"p2","name_uz":"Manty 1kg","name_ru":"Манты 1кг","price":25000,"image":"p2.jpg"}
    ]
    PRODUCT_FILE.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

# create placeholder images if missing
try:
    with PRODUCT_FILE.open("r", encoding="utf-8") as f:
        _products = json.load(f)
except:
    _products = []
for p in _products:
    imgname = p.get("image") or f"{p.get('id')}.jpg"
    target = IMAGES / imgname
    if not target.exists():
        try:
            urlretrieve(f"https://via.placeholder.com/800x400?text={p.get('id')}", str(target))
        except:
            target.write_text("", encoding="utf-8")

# ---------- Flask app ----------
app = Flask(__name__, template_folder=str(TEMPLATES), static_folder=str(STATIC))

def load_products():
    try:
        with PRODUCT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

@app.route("/")
def index():
    lang = request.args.get("lang", "ru")
    products = load_products()
    web_url = WEB_URL if WEB_URL else request.url_root.rstrip("/")
    return render_template("index.html", products=products, lang=lang, web_url=web_url)

@app.route("/order/<pid>", methods=["GET","POST"])
def order(pid):
    products = load_products()
    product = next((p for p in products if p.get("id")==pid), None)
    if not product:
        return "Mahsulot topilmadi", 404
    if request.method == "POST":
        order = {
            "product_id": pid,
            "product_name": product.get("name_ru"),
            "price": product.get("price"),
            "qty": request.form.get("qty","1"),
            "name": request.form.get("name","Anonim"),
            "phone": request.form.get("phone",""),
            "note": request.form.get("note",""),
            "time": datetime.datetime.now().isoformat()
        }
        # save orders
        try:
            if not DATA_FILE.exists():
                DATA_FILE.write_text("[]", encoding="utf-8")
            with DATA_FILE.open("r", encoding="utf-8") as f:
                arr = json.load(f)
        except:
            arr = []
        arr.append(order)
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
        # send to telegram group async
        try:
            if 'aioloop' in globals() and globals()['aioloop'] is not None and BOT_TOKEN and ORDER_GROUP_ID:
                asyncio.run_coroutine_threadsafe(send_order_to_group_async(order), globals()['aioloop'])
        except Exception as e:
            print("Send error:", e)
        return render_template("ordered.html")
    return render_template("order.html", product=product, lang=request.args.get("lang","ru"))

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC), filename)

# ---------- Telegram (aiogram v3) ----------
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

def build_order_text(o: dict) -> str:
    return (f"🆕 Yangi buyurtma\nMahsulot: {o.get('product_name')}\nMiqdor: {o.get('qty')}\nIsm: {o.get('name')}\nTel: {o.get('phone')}\nIzoh: {o.get('note')}\nVaqt: {o.get('time')}")

async def send_order_to_group_async(order: dict):
    if not bot:
        print("Bot not configured.")
        return
    text = build_order_text(order)
    try:
        await bot.send_message(ORDER_GROUP_ID, text)
    except Exception as e:
        print("Telegram send error:", e)

async def cmd_start(message: types.Message):
    text = "Добро пожаловать"
    rows = []
    if WEB_URL:
        rows.append([types.InlineKeyboardButton(text="Открыть", web_app=types.WebAppInfo(url=f"{WEB_URL}?lang=ru"))])
    else:
        rows.append([types.InlineKeyboardButton(text="Открыть (не настроено)", callback_data="no_webapp")])
    rows.append([types.InlineKeyboardButton(text="✍️ Оставить отзыв", web_app=types.WebAppInfo(url=f"{WEB_URL}?lang=ru"))]) if WEB_URL else None
    kb = types.InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, reply_markup=kb)

async def cmd_report(message: types.Message):
    if ORDER_GROUP_ID and message.chat.id != ORDER_GROUP_ID:
        return await message.reply("Ruxsat yo'q.")
    try:
        if DATA_FILE.exists():
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
    except:
        data = []
    total = len(data)
    total_kg = 0.0
    total_sum = 0.0
    for d in data:
        try:
            q = float(d.get('qty',0))
            p = float(d.get('price',0))
            total_kg += q
            total_sum += q*p
        except:
            pass
    await message.reply(f"📊 Oy yakunlari:\nJami buyurtma: {total} ta\nJami kg: {total_kg} kg\nJami summa: {int(total_sum)} so'm")

# register handlers
if bot:
    dp.message.register(cmd_start, Command(commands=["start"]))
    dp.message.register(cmd_report, Command(commands=["report"]))
else:
    print("BOT_TOKEN not set — Telegram bot disabled (only web runs).")

# ---------- Run ----------
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # start flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Flask started in background.")

    # if no bot token, keep running web only
    if not bot:
        print("BOT_TOKEN not set. Only web active.")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        raise SystemExit

    # start aiogram loop
    aioloop = asyncio.new_event_loop()
    globals()['aioloop'] = aioloop
    asyncio.set_event_loop(aioloop)
    print("Starting aiogram polling...")
    try:
        aioloop.run_until_complete(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        print("Stopped.")
    except Exception as e:
        print("Aiogram error:", e)
    finally:
        try:
            aioloop.run_until_complete(aioloop.shutdown_asyncgens())
            aioloop.close()
        except:
            pass

