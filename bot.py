import logging
import sqlite3
import threading
import requests
import razorpay

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
    ContextTypes,
    filters,
)

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = "8651711814:AAFYaEHDFy8hEjzzEVfhkJo-F_kzceoyOS4"

# Razorpay
RAZORPAY_KEY = "YOUR_RAZORPAY_KEY"
RAZORPAY_SECRET = "YOUR_RAZORPAY_SECRET"

# Like API
LIKE_API_URL = "https://smmhype.com/api/v2"
LIKE_API_KEY = "YOUR_SMMHYPE_API_KEY"

LIKE_SERVICE_99 = "498"
LIKE_SERVICE_120 = "19564"

# Comment API
COMMENT_API_URL = "https://tntsmm.in/api/v2"
COMMENT_API_KEY = "YOUR_TNTSMM_API_KEY"

COMMENT_SERVICE = "12634"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger(__name__)

# ==============================
# DATABASE
# ==============================

conn = sqlite3.connect(
    "smm.db",
    check_same_thread=False
)

db_lock = threading.Lock()

user_steps = {}

processing_users = set()

processing_lock = threading.Lock()


def init_db():

    with db_lock:

        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            telegram_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments(
            payment_id TEXT PRIMARY KEY,
            telegram_id INTEGER,
            amount REAL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT,
            telegram_id INTEGER,
            service TEXT,
            link TEXT,
            qty INTEGER
        )
        """)

        conn.commit()


def get_balance(user_id):

    with db_lock:

        cur = conn.cursor()

        cur.execute(
            "SELECT balance FROM users WHERE telegram_id=?",
            (user_id,)
        )

        row = cur.fetchone()

        if row:
            return row[0]

        return 0.0


# ==============================
# MAIN MENU
# ==============================

def menu():

    return ReplyKeyboardMarkup(

        [

            ["👤 Account", "💰 Recharge"],

            ["🛒 Services", "📦 Orders"]

        ],

        resize_keyboard=True

    )


BACK = ReplyKeyboardMarkup(

    [["⬅ Back"]],

    resize_keyboard=True

)

# ==============================
# START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    tg = update.message.chat_id

    with db_lock:

        cur = conn.cursor()

        cur.execute(

            "INSERT OR IGNORE INTO users(telegram_id) VALUES(?)",

            (tg,)

        )

        conn.commit()

    txt = f"""
<b>🚀 Welcome to Premium SMM Panel</b>

━━━━━━━━━━━━━━━━━━

💙 High Quality Services

⚪ YouTube Likes Economy

🔥 YouTube Likes HQ

💬 Custom Comments

━━━━━━━━━━━━━━━━━━

Use menu below.
"""

    await update.message.reply_text(

        txt,

        parse_mode="HTML",

        reply_markup=menu()

    )

# ==============================
# SERVICES MENU
# ==============================

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [

        [

            InlineKeyboardButton(

                "⚪ Likes Economy ₹99",

                callback_data="likes99"

            )

        ],

        [

            InlineKeyboardButton(

                "🔥 Likes HQ ₹120",

                callback_data="likes120"

            )

        ],

        [

            InlineKeyboardButton(

                "💬 Custom Comments ₹200",

                callback_data="comments"

            )

        ]

    ]

    txt = """
<b>🚀 YOUTUBE SERVICES</b>

━━━━━━━━━━━━━━━━━━

⚪ Likes Economy

• High Quality

• +2K / Day

• Refill 30 Days

<b>₹99 / 1000</b>

━━━━━━━━━━━━━━━━━━

🔥 Likes HQ

• No Drop

• High Quality

• +1K / Day

• Refill 30 Days

<b>₹120 / 1000</b>

━━━━━━━━━━━━━━━━━━

💬 Custom Comments

• Instant Start

• 2K+ / Day

• No Refill

<b>₹200 / 1000</b>

━━━━━━━━━━━━━━━━━━

Select Service 👇
"""

    await update.message.reply_text(

        txt,

        parse_mode="HTML",

        reply_markup=InlineKeyboardMarkup(keyboard)

    )

# ==============================
# ACCOUNT
# ==============================

async def account(update: Update):

    bal = get_balance(update.message.chat_id)

    await update.message.reply_text(

        f"""

👤 <b>Your Account</b>

━━━━━━━━━━━━

💰 Balance

<b>₹{bal:.2f}</b>

━━━━━━━━━━━━

""",

        parse_mode="HTML"

    )

# ==============================
# MESSAGE HANDLER
# ==============================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    txt = update.message.text

    if txt == "🛒 Services":

        await services(update, context)

        return

    if txt == "👤 Account":

        await account(update)

        return

    if txt == "💰 Recharge":

        user_steps[update.message.chat_id] = "recharge"

        await update.message.reply_text(

            "💰 Enter Recharge Amount",

            reply_markup=BACK

        )

        return

    if txt == "📦 Orders":

        await update.message.reply_text(

            "📦 Orders module will be added in Part 4."

        )

        return

# ==============================
# CALLBACK
# ==============================

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    tg = query.message.chat_id

    if query.data == "likes99":

        user_steps[tg] = "like99_link"

        await query.message.reply_text(

            "🔗 Send YouTube Video Link"

        )

    elif query.data == "likes120":

        user_steps[tg] = "like120_link"

        await query.message.reply_text(

            "🔗 Send YouTube Video Link"

        )

    elif query.data == "comments":

        user_steps[tg] = "comment_link"

        await query.message.reply_text(

            "🔗 Send YouTube Video Link"

        )

# ==============================
# MAIN
# ==============================

init_db()

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(
    CallbackQueryHandler(callback)
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle
    )
)

print("Bot Started...")

app.run_polling()
