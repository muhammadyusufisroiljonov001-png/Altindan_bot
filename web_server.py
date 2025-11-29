import os, json
from flask import Flask, request, jsonify, send_from_directory, abort
from telegram import Bot
from pathlib import Path

app = Flask(__name__, static_folder="web", static_url_path="/")

# Telegram token va guruh id (bot service ham bu qiymatni env orqali oladi)
TOKEN = os.getenv("TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
# Agar GROUP_ID env mavjud bo'lsa, intga o'tkazamiz
try:
    if GROUP_ID:
        GROUP_ID_INT = int(GROUP_ID)
    else:
        GROUP_ID_INT = None
except:
    GROUP_ID_INT = None

bot = Bot(token=TOKEN) if TOKEN else None

# products.json faylini o'qish
ROOT = Path(__file__).parent
PROD_FILE = ROOT / "products.json"

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.static_folder, 'static'), filename)

@app.route('/api/products')
def api_products():
    if not PROD_FILE.exists():
        return jsonify([]), 200
    with open(PROD_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error":"No JSON"}), 400
    # build message
    title = data.get('title_uz') or data.get('title_ru') or data.get('productId','-')
    price = data.get('price','-')
    addr = data.get('address', '-')
    qty = data.get('qty',1)
    img = data.get('img')
    t = data.get('time','-')

    text = (f"📥 New order\n\n"
            f"Product: {title}\n"
            f"Qty: {qty}\n"
            f"Price: {price}\n"
            f"Address: {addr}\n"
            f"Time: {t}")

    if not bot or not GROUP_ID_INT:
        return jsonify({"error":"Bot token or GROUP_ID not configured on server"}), 500

    try:
        # If image present, send as photo with caption
        if img:
            bot.send_photo(chat_id=GROUP_ID_INT, photo=img, caption=text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id=GROUP_ID_INT, text=text)
        return jsonify({"ok":True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Run Flask
    app.run(host='0.0.0.0', port=port)

