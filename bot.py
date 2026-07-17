import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os

from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ================= CONFIG =================
BOT_TOKEN = "8651711814:AAFYaEHDFy8hEjzzEVfhkJo-F_kzceoyOS4"

RAZORPAY_KEY = "YOUR_KEY"
RAZORPAY_SECRET = "YOUR_SECRET"
WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET"

COMMENT_API_URL = "https://smm-jupiter.com/api/v2"
COMMENT_API_KEY = "YOUR_COMMENT_KEY"
COMMENT_SERVICE_ID = "13259"

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

# ================= DB =================
conn = sqlite3.connect("smm.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    telegram_id INTEGER,
    amount REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT,
    telegram_id INTEGER,
    service TEXT,
    link TEXT,
    qty INTEGER
)
""")

conn.commit()

user_steps = {}

# ================= UI =================
def menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"]
    ], resize_keyboard=True)

BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id

    cursor.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (tg_id,))
    conn.commit()

    await update.message.reply_text("🔥 SMM BOT ACTIVE", reply_markup=menu())

# ================= SERVICES =================
async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💬 Comments ₹250/1000", callback_data="comments")]
    ]

    await update.message.reply_text(
        "Select Service:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= CALLBACK =================
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    tg_id = q.message.chat_id

    if q.data == "comments":
        user_steps[tg_id] = "c_link"
        await q.message.reply_text("🔗 Send Link:")

# ================= MAIN =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id
    text = update.message.text
    step = user_steps.get(tg_id)

    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0

    # ================= MENU =================
    if text == "🛒 Services":
        await services(update, context)

    elif text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{balance}")

    elif text == "💰 Recharge":
        user_steps[tg_id] = "recharge"

        await update.message.reply_text("Enter amount:")

    # ================= RECHARGE =================
    elif step == "recharge":
        try:
            amount = int(text)

            payment = client.payment_link.create({
                "amount": amount * 100,
                "currency": "INR",
                "notes": {"telegram_id": str(tg_id)}
            })

            await update.message.reply_text(
                f"💳 Pay here:\n{payment['short_url']}"
            )

            user_steps[tg_id] = None

        except:
            await update.message.reply_text("❌ Invalid amount")

    # ================= COMMENTS FLOW =================
    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"

        await update.message.reply_text(
            "💬 Send comments (one per line)"
        )

    elif step == "c_text":
        comments = [c.strip() for c in text.split("\n") if c.strip()]
        qty = len(comments)
        price = round((qty / 1000) * 250, 2)

        context.user_data["comments"] = comments
        context.user_data["qty"] = qty
        context.user_data["price"] = price

        user_steps[tg_id] = "c_confirm"

        await update.message.reply_text(
            f"📦 SUMMARY\n\n"
            f"💬 Comments: {qty}\n"
            f"💰 Price: ₹{price}\n\n"
            f"👉 YES / NO"
        )

    elif step == "c_confirm":

        if text.lower() == "no":
            user_steps[tg_id] = None
            await update.message.reply_text("❌ Cancelled")
            return

        if text.lower() != "yes":
            await update.message.reply_text("👉 YES or NO only")
            return

        link = context.user_data.get("link")
        comments = context.user_data.get("comments")
        qty = context.user_data.get("qty")
        price = context.user_data.get("price")

        if balance &lt; price:
            await update.message.reply_text("❌ Low Balance")
            return

        # deduct
        cursor.execute(
            "UPDATE users SET balance=balance-? WHERE telegram_id=?",
            (price, tg_id)
        )
        conn.commit()

        # API ORDER
        res = requests.post(COMMENT_API_URL, data={
            "key": COMMENT_API_KEY,
            "action": "add",
            "service": COMMENT_SERVICE_ID,
            "link": link,
            "comments": "\n".join(comments)
        }).json()

        order_id = res.get("order", "NA")

        cursor.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?)",
            (order_id, tg_id, "comments", link, qty)
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ ORDER PLACED\n\n"
            f"💬 Comments: {qty}\n"
            f"💰 Paid: ₹{price}\n"
            f"📦 ID: {order_id}"
        )

        user_steps[tg_id] = None

    # ================= ORDERS =================
    elif text == "📦 Orders":
        cursor.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No orders")
            return

        msg = "📦 LAST ORDERS\n\n"
        for r in rows[-5:]:
            msg += f"{r[2]} | {r[4]} | {r[0]}\n"

        await update.message.reply_text(msg)

# ================= RAZORPAY WEBHOOK =================
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.data

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "invalid"}, 400

    data = request.json

    if data.get("event") == "payment_link.paid":
        entity = data["payload"]["payment_link"]["entity"]

        tg_id = int(entity["notes"]["telegram_id"])
        amount = entity["amount_paid"] / 100
        payment_id = entity["id"]

        cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
        if cursor.fetchone():
            return {"status": "duplicate"}

        cursor.execute("INSERT INTO payments VALUES (?,?,?)",
                       (payment_id, tg_id, amount))

        cursor.execute(
            "UPDATE users SET balance=balance+? WHERE telegram_id=?",
            (amount, tg_id)
        )

        conn.commit()

    return {"status": "ok"}

# ================= RUN =================
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT &amp; ~filters.COMMAND, handle))

    app.run_polling()

if __name__ == "__main__":
    run_bot()
