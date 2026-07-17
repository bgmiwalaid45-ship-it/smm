import logging
import os
import sqlite3
import threading
import hmac
import hashlib

import requests
import razorpay

from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("smm_bot")

# ================= CONFIG =================
# Hardcoded directly in source per request. Keep this repo PRIVATE — anyone
# with access to this file has full control of the bot, the Razorpay
# account, and the SMM panel key.
BOT_TOKEN = "8651711814:AAFYaEHDFy8hEjzzEVfhkJo-F_kzceoyOS4"
RAZORPAY_KEY = "YOUR_RAZORPAY_KEY_ID"
RAZORPAY_SECRET = "YOUR_RAZORPAY_KEY_SECRET"
WEBHOOK_SECRET = "YOUR_RAZORPAY_WEBHOOK_SECRET"

COMMENT_API_URL = "https://smm-jupiter.com/api/v2"
COMMENT_API_KEY = "YOUR_SMM_PANEL_API_KEY"
COMMENT_SERVICE_ID = "13259"

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

# ================= DB =================
# check_same_thread=False lets multiple threads (bot event loop + Flask
# webhook thread) touch the same connection, but sqlite3 objects are NOT
# thread-safe for concurrent writes. All access goes through db_lock below.
conn = sqlite3.connect("smm.db", check_same_thread=False)
db_lock = threading.Lock()


def init_db():
    with db_lock:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                telegram_id INTEGER,
                amount REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT,
                telegram_id INTEGER,
                service TEXT,
                link TEXT,
                qty INTEGER
            )
        """)
        conn.commit()


def get_balance(tg_id: int) -> float:
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
        row = cur.fetchone()
        return row[0] if row else 0.0


user_steps = {}
# Tracks users who currently have an order in flight, so a duplicate "YES"
# tap (or duplicate webhook delivery) can't double-charge / double-order.
processing_lock = threading.Lock()
processing_users = set()

# ================= UI =================
def menu():
    return ReplyKeyboardMarkup([
        ["👤 Account", "💰 Recharge"],
        ["📦 Orders", "🛒 Services"],
    ], resize_keyboard=True)


BACK = ReplyKeyboardMarkup([["⬅️ Back"]], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.message.chat_id

    with db_lock:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (tg_id,))
        conn.commit()

    await update.message.reply_text("🔥 SMM BOT ACTIVE", reply_markup=menu())

# ================= SERVICES =================
async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💬 Comments ₹250/1000", callback_data="comments")]
    ]
    await update.message.reply_text(
        "Select Service:",
        reply_markup=InlineKeyboardMarkup(keyboard),
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

    balance = get_balance(tg_id)

    # ================= MENU =================
    if text == "🛒 Services":
        await services(update, context)

    elif text == "👤 Account":
        await update.message.reply_text(f"💰 Balance: ₹{balance:.2f}")

    elif text == "💰 Recharge":
        user_steps[tg_id] = "recharge"
        await update.message.reply_text("Enter amount:")

    # ================= RECHARGE =================
    elif step == "recharge":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError("amount must be positive")

            payment = client.payment_link.create({
                "amount": amount * 100,
                "currency": "INR",
                "notes": {"telegram_id": str(tg_id)},
            })

            await update.message.reply_text(
                f"💳 Pay here:\n{payment['short_url']}"
            )
            user_steps[tg_id] = None

        except ValueError:
            await update.message.reply_text("❌ Enter a valid positive amount")
        except razorpay.errors.BadRequestError as e:
            log.warning("Razorpay payment link creation failed for %s: %s", tg_id, e)
            await update.message.reply_text("❌ Payment provider rejected this amount, try again")
        except Exception:
            log.exception("Unexpected error creating payment link for %s", tg_id)
            await update.message.reply_text("❌ Something went wrong, please try again later")

    # ================= COMMENTS FLOW =================
    elif step == "c_link":
        context.user_data["link"] = text
        user_steps[tg_id] = "c_text"
        await update.message.reply_text("💬 Send comments (one per line)")

    elif step == "c_text":
        comments = [c.strip() for c in text.split("\n") if c.strip()]
        if not comments:
            await update.message.reply_text("❌ Send at least one non-empty line")
            return

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

        # Prevent double-submission: if this user already has an order being
        # processed, ignore the extra tap instead of double-charging them.
        with processing_lock:
            if tg_id in processing_users:
                await update.message.reply_text("⏳ Your order is already being processed")
                return
            processing_users.add(tg_id)

        try:
            link = context.user_data.get("link")
            comments = context.user_data.get("comments")
            qty = context.user_data.get("qty")
            price = context.user_data.get("price")

            if not comments or not link or price is None:
                await update.message.reply_text("❌ Session expired, please start again")
                user_steps[tg_id] = None
                return

            # Re-check balance and deduct atomically so two near-simultaneous
            # confirms can't both pass the balance check before either commits.
            with db_lock:
                cur = conn.cursor()
                cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,))
                row = cur.fetchone()
                current_balance = row[0] if row else 0.0

                if current_balance < price:
                    await update.message.reply_text("❌ Low Balance")
                    user_steps[tg_id] = None
                    return

                cur.execute(
                    "UPDATE users SET balance=balance-? WHERE telegram_id=?",
                    (price, tg_id),
                )
                conn.commit()

            # Call the external API. If it fails, refund the deduction.
            try:
                res = requests.post(
                    COMMENT_API_URL,
                    data={
                        "key": COMMENT_API_KEY,
                        "action": "add",
                        "service": COMMENT_SERVICE_ID,
                        "link": link,
                        "comments": "\n".join(comments),
                    },
                    timeout=15,
                ).json()
            except requests.RequestException:
                log.exception("Comment API request failed for %s", tg_id)
                with db_lock:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
                        (price, tg_id),
                    )
                    conn.commit()
                await update.message.reply_text("❌ Order failed, you have been refunded")
                user_steps[tg_id] = None
                return

            order_id = res.get("order")
            if not order_id:
                log.error("Comment API returned no order id for %s: %s", tg_id, res)
                with db_lock:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
                        (price, tg_id),
                    )
                    conn.commit()
                await update.message.reply_text("❌ Order failed, you have been refunded")
                user_steps[tg_id] = None
                return

            with db_lock:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO orders VALUES (?,?,?,?,?)",
                    (order_id, tg_id, "comments", link, qty),
                )
                conn.commit()

            await update.message.reply_text(
                f"✅ ORDER PLACED\n\n"
                f"💬 Comments: {qty}\n"
                f"💰 Paid: ₹{price}\n"
                f"📦 ID: {order_id}"
            )
            user_steps[tg_id] = None

        finally:
            with processing_lock:
                processing_users.discard(tg_id)

    # ================= ORDERS =================
    elif text == "📦 Orders":
        with db_lock:
            cur = conn.cursor()
            cur.execute("SELECT * FROM orders WHERE telegram_id=?", (tg_id,))
            rows = cur.fetchall()

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

    if not signature:
        return {"status": "missing signature"}, 400

    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "invalid"}, 400

    data = request.get_json(silent=True)
    if not data:
        return {"status": "bad payload"}, 400

    if data.get("event") == "payment_link.paid":
        try:
            entity = data["payload"]["payment_link"]["entity"]
            tg_id = int(entity["notes"]["telegram_id"])
            amount = entity["amount_paid"] / 100
            payment_id = entity["id"]
        except (KeyError, TypeError, ValueError):
            log.exception("Malformed webhook payload: %s", data)
            return {"status": "bad payload"}, 400

        with db_lock:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM payments WHERE payment_id=?", (payment_id,))
            if cur.fetchone():
                return {"status": "duplicate"}

            cur.execute(
                "INSERT INTO payments VALUES (?,?,?)",
                (payment_id, tg_id, amount),
            )
            cur.execute(
                "UPDATE users SET balance=balance+? WHERE telegram_id=?",
                (amount, tg_id),
            )
            conn.commit()

    return {"status": "ok"}

# ================= RUN =================
def run_flask():
    # Railway (and most PaaS providers) inject the port to bind via the PORT
    # env var — it's assigned dynamically, so don't hardcode it.
    port = int(os.environ.get("PORT", 5000))
    # debug=False and use_reloader=False are important: the reloader spawns a
    # second process which would double-init everything.
    app_web.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_bot():
    init_db()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()


if __name__ == "__main__":
    run_bot()
