import requests
import razorpay
import sqlite3
import hmac
import hashlib
import os
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ══════════════════════════════════════════
#               ⚙️  CONFIG
# ══════════════════════════════════════════
BOT_TOKEN      = "8651711814:AAFYaEHDFy8hEjzzEVfhkJo-F_kzceoyOS4"
ADMIN_ID       = 8451049817

# ── Likes API (smmhype.com) ──
SMMHYPE_KEY    = "YOUR_SMMHYPE_API_KEY"   # ← apna smmhype.com API key daalo
SMMHYPE_URL    = "https://smmhype.com/api/v2"
SVC_LIKE_ECO   = "498"    # Economy Likes  ₹99/1000   +2K/Day  Refill 30D
SVC_LIKE_PREM  = "19564"  # Premium Likes  ₹120/1000  No Drop  Refill 30D

PRICE_LIKE_ECO  = 99    # ₹ per 1000
PRICE_LIKE_PREM = 120   # ₹ per 1000

# ── Comments API (tntsmm.in) ──
TNTSMM_KEY     = "7d01eb30166546130c171b26eecee191"
TNTSMM_URL     = "https://tntsmm.in/api/v2"
SVC_COMMENT    = "12634"  # YT Custom Comment  ₹200/1000  2K+/Day  Instant

PRICE_COMMENT  = 200  # ₹ per 1000

# ── Razorpay ──
RAZORPAY_KEY    = "rzp_live_Sc7lXEOJ2ZWjPL"
RAZORPAY_SECRET = "KxRu3ssMBcNLTQ7LxMY0jZIQ"
WEBHOOK_SECRET  = "ayush@123"

# ── App URL (auto-detect Replit, fallback to Railway) ──
REPLIT_DOMAIN   = os.environ.get("REPLIT_DEV_DOMAIN", "")
if REPLIT_DOMAIN:
    APP_URL      = f"https://{REPLIT_DOMAIN}"
    WEBHOOK_PATH = f"/api/{BOT_TOKEN}"
else:
    APP_URL      = "https://smm-production-e703.up.railway.app"
    WEBHOOK_PATH = f"/{BOT_TOKEN}"

client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

# ══════════════════════════════════════════
#               🗄️  DATABASE
# ══════════════════════════════════════════
def db():
    return sqlite3.connect("users.db", check_same_thread=False)

def init_db():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users
        (telegram_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, banned INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments
        (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS orders
        (order_id TEXT, telegram_id INTEGER, service TEXT, link TEXT, quantity INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

init_db()

def get_balance(tg):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone()
    if not r:
        cur.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg,))
        conn.commit(); conn.close()
        return 0.0
    conn.close()
    return round(r[0], 2)

def update_balance(tg, amt):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amt, tg))
    conn.commit(); conn.close()

def is_banned(tg):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT banned FROM users WHERE telegram_id=?", (tg,))
    r = cur.fetchone(); conn.close()
    return r and r[0] == 1

def payment_exists(pid):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM payments WHERE payment_id=?", (pid,))
    r = cur.fetchone(); conn.close()
    return r is not None

def save_payment(pid, tg, amt):
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO payments VALUES (?,?,?)", (pid, tg, amt))
    conn.commit(); conn.close()

def save_order(order_id, tg, service, link, qty):
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO orders (order_id, telegram_id, service, link, quantity) VALUES (?,?,?,?,?)",
                (order_id, tg, service, link, qty))
    conn.commit(); conn.close()

# ══════════════════════════════════════════
#              🎨  KEYBOARDS
# ══════════════════════════════════════════
def kb_main():
    return ReplyKeyboardMarkup([
        ["👤  My Account",   "💰  Add Balance"],
        ["📦  My Orders",    "🛒  Services"],
        ["🎧  Support"]
    ], resize_keyboard=True)

def kb_services():
    return ReplyKeyboardMarkup([
        ["▶️  YouTube Likes"],
        ["💬  YouTube Comments"],
        ["⬅️  Back"]
    ], resize_keyboard=True)

def kb_likes():
    return ReplyKeyboardMarkup([
        ["⚡  Economy Likes  ₹99/1K"],
        ["👑  Premium Likes  ₹120/1K"],
        ["⬅️  Back"]
    ], resize_keyboard=True)

def kb_confirm():
    return ReplyKeyboardMarkup([
        ["✅  Confirm Order", "❌  Cancel"]
    ], resize_keyboard=True)

KB_BACK = ReplyKeyboardMarkup([["⬅️  Back"]], resize_keyboard=True)

# ══════════════════════════════════════════
#            🖼️  MESSAGE TEMPLATES
# ══════════════════════════════════════════
def msg_welcome(name, bal):
    return (
        "╔══════════════════════╗\n"
        "║   🚀 <b>YT SMM PANEL</b>      ║\n"
        "╚══════════════════════╝\n\n"
        f"👋 Hey <b>{name}</b>, welcome back!\n\n"
        "⚡ <b>Why choose us?</b>\n"
        "  ├ 🎯 Real YouTube Engagement\n"
        "  ├ 🔒 No Drop Guarantee (Premium)\n"
        "  ├ ⚡ Instant Processing\n"
        "  └ 💸 Lowest Market Rates\n\n"
        "─────────────────────────\n"
        f"💰 <b>Your Balance:</b>  ₹{bal}\n"
        "─────────────────────────\n\n"
        "👇 Choose an option below:"
    )

def msg_account(tg, name, bal):
    return (
        "╔═══════════════════╗\n"
        "║  👤 <b>MY ACCOUNT</b>     ║\n"
        "╚═══════════════════╝\n\n"
        f"🆔 <b>User ID:</b>  <code>{tg}</code>\n"
        f"👤 <b>Name:</b>     {name}\n"
        f"💰 <b>Balance:</b>  ₹{bal}\n\n"
        "─────────────────────\n"
        "Use <b>💰 Add Balance</b> to recharge."
    )

def msg_services():
    return (
        "╔═══════════════════╗\n"
        "║   🛒 <b>OUR SERVICES</b>  ║\n"
        "╚═══════════════════╝\n\n"
        "▶️ <b>YouTube Likes</b>\n"
        "  ├ ⚡ Economy  — ₹99/1000\n"
        "  │     +2K/Day | Refill 30 Days\n"
        "  └ 👑 Premium  — ₹120/1000\n"
        "        No Drop | Refill 30 Days\n\n"
        "💬 <b>YouTube Comments</b>\n"
        "  └ ✍️ Custom  — ₹200/1000\n"
        "        Instant | 2K+/Day\n\n"
        "👇 Select a service:"
    )

def msg_likes_menu():
    return (
        "╔════════════════════════╗\n"
        "║   ▶️  <b>YOUTUBE LIKES</b>    ║\n"
        "╚════════════════════════╝\n\n"
        "⚡ <b>Economy Likes</b>  —  ₹99/1000\n"
        "  ├ Speed: +2,000/Day\n"
        "  ├ Quality: High\n"
        "  └ Refill: 30 Days\n\n"
        "👑 <b>Premium Likes</b>  —  ₹120/1000\n"
        "  ├ Speed: +1,000/Day\n"
        "  ├ Quality: High  |  No Drop\n"
        "  └ Refill: 30 Days\n\n"
        "👇 Choose a plan:"
    )

def msg_order_summary(service_name, qty, price, link):
    return (
        "╔════════════════════╗\n"
        "║  📋 <b>ORDER SUMMARY</b>  ║\n"
        "╚════════════════════╝\n\n"
        f"📌 <b>Service:</b>  {service_name}\n"
        f"🔢 <b>Quantity:</b>  {qty:,}\n"
        f"💰 <b>Price:</b>     ₹{price}\n"
        f"🔗 <b>Link:</b>\n<code>{link}</code>\n\n"
        "─────────────────────\n"
        "Tap <b>✅ Confirm Order</b> to proceed."
    )

def msg_order_placed(order_id, service_name, qty):
    return (
        "╔══════════════════════╗\n"
        "║  ✅ <b>ORDER PLACED!</b>     ║\n"
        "╚══════════════════════╝\n\n"
        f"🎉 Your order is being processed!\n\n"
        f"📌 <b>Service:</b>   {service_name}\n"
        f"🔢 <b>Quantity:</b>  {qty:,}\n"
        f"🆔 <b>Order ID:</b>  <code>{order_id}</code>\n\n"
        "─────────────────────────\n"
        "📦 Track via <b>My Orders</b> menu.\n"
        "⏱️ Delivery starts within minutes!"
    )

STATUS_EMOJI = {
    "pending":    "🟡",
    "processing": "🔵",
    "in progress":"🔵",
    "completed":  "🟢",
    "partial":    "🟠",
    "cancelled":  "🔴",
    "canceled":   "🔴",
}

def status_icon(st):
    return STATUS_EMOJI.get(st.lower(), "⚪") if st else "⚪"

# ══════════════════════════════════════════
#          📡  ORDER STATUS CHECK
# ══════════════════════════════════════════
def check_order_status(order_id, api_url, api_key):
    try:
        r = requests.post(api_url, data={"key": api_key, "action": "status", "order": order_id}, timeout=8)
        return r.json()
    except:
        return None

def api_info_for_service(service):
    if service in ("likes_eco", "likes_prem"):
        return SMMHYPE_URL, SMMHYPE_KEY
    return TNTSMM_URL, TNTSMM_KEY

SERVICE_NAMES = {
    "likes_eco":  "⚡ Economy Likes",
    "likes_prem": "👑 Premium Likes",
    "comments":   "💬 YT Comments",
}

# ══════════════════════════════════════════
#            🤖  STATE TRACKER
# ══════════════════════════════════════════
user_steps = {}

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# ── /start ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg   = update.message.chat_id
    name = update.message.from_user.first_name or "User"
    bal  = get_balance(tg)
    await update.message.reply_text(
        msg_welcome(name, bal),
        reply_markup=kb_main(),
        parse_mode="HTML"
    )

# ══════════════════════════════════════════
#           🔑  ADMIN COMMANDS
# ══════════════════════════════════════════
async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    try:
        tg  = int(context.args[0])
        bal = get_balance(tg)
        await update.message.reply_text(f"👤 User <code>{tg}</code>\n💰 Balance: <b>₹{bal}</b>", parse_mode="HTML")
    except:
        await update.message.reply_text("Usage: /balance USER_ID")

async def cmd_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    try:
        tg  = int(context.args[0])
        amt = float(context.args[1])
        update_balance(tg, amt)
        await update.message.reply_text(f"✅ Added <b>₹{amt}</b> to <code>{tg}</code>", parse_mode="HTML")
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                     params={"chat_id": tg, "text": f"🎉 Admin has added ₹{amt} to your account!\n💰 New Balance: ₹{get_balance(tg)}", "parse_mode": "HTML"})
    except:
        await update.message.reply_text("Usage: /addbalance USER_ID AMOUNT")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    try:
        tg = int(context.args[0])
        conn = db(); cur = conn.cursor()
        cur.execute("UPDATE users SET banned=1 WHERE telegram_id=?", (tg,))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🚫 User <code>{tg}</code> banned.", parse_mode="HTML")
    except:
        await update.message.reply_text("Usage: /ban USER_ID")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    try:
        tg = int(context.args[0])
        conn = db(); cur = conn.cursor()
        cur.execute("UPDATE users SET banned=0 WHERE telegram_id=?", (tg,))
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ User <code>{tg}</code> unbanned.", parse_mode="HTML")
    except:
        await update.message.reply_text("Usage: /unban USER_ID")

async def cmd_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT SUM(amount) FROM payments")
    total_recharge = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    cur.execute("SELECT service, quantity FROM orders")
    orders = cur.fetchall()
    conn.close()

    COST = {"likes_eco": 40, "likes_prem": 55, "comments": 80}  # ₹ per 1000 approx
    SELL = {"likes_eco": PRICE_LIKE_ECO, "likes_prem": PRICE_LIKE_PREM, "comments": PRICE_COMMENT}
    rev = cost = 0
    for svc, qty in orders:
        rev  += (qty / 1000) * SELL.get(svc, 0)
        cost += (qty / 1000) * COST.get(svc, 0)

    await update.message.reply_text(
        "╔═══════════════════════╗\n"
        "║  📈 <b>PROFIT DASHBOARD</b>   ║\n"
        "╚═══════════════════════╝\n\n"
        f"💰 <b>Total Recharge:</b>  ₹{round(total_recharge,2)}\n"
        f"💵 <b>Revenue:</b>         ₹{round(rev,2)}\n"
        f"📉 <b>Cost (est.):</b>     ₹{round(cost,2)}\n"
        f"💸 <b>Profit (est.):</b>   ₹{round(rev-cost,2)}\n\n"
        "──────────────────────────\n"
        f"👤 <b>Total Users:</b>   {total_users}\n"
        f"📦 <b>Total Orders:</b>  {total_orders}",
        parse_mode="HTML"
    )

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID: return
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast Your message here")
    msg = " ".join(context.args)
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    users = cur.fetchall(); conn.close()
    sent = fail = 0
    for (uid,) in users:
        try:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         params={"chat_id": uid, "text": f"📢 <b>Announcement</b>\n\n{msg}", "parse_mode": "HTML"})
            sent += 1
        except:
            fail += 1
    await update.message.reply_text(f"✅ Broadcast done!\n📨 Sent: {sent}  ❌ Failed: {fail}")

# ══════════════════════════════════════════
#           💬  MAIN MESSAGE HANDLER
# ══════════════════════════════════════════
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg   = update.message.chat_id
    text = (update.message.text or "").strip()
    step = user_steps.get(tg)

    # Ban check
    if is_banned(tg):
        return await update.message.reply_text("🚫 Your account has been suspended.\nContact @ayushpatelh for support.")

    # ── Back ──
    if text == "⬅️  Back":
        user_steps.pop(tg, None)
        context.user_data.clear()
        return await update.message.reply_text("🏠 Main Menu", reply_markup=kb_main())

    # ── Account ──
    if text == "👤  My Account":
        user = update.message.from_user
        return await update.message.reply_text(
            msg_account(tg, user.first_name, get_balance(tg)),
            parse_mode="HTML", reply_markup=kb_main()
        )

    # ── Support ──
    if text == "🎧  Support":
        return await update.message.reply_text(
            "🎧 <b>Customer Support</b>\n\n"
            "📩 Contact admin: @ayushpatelh\n"
            "⏰ Response time: within 1 hour\n\n"
            "Please share your <b>Order ID</b> when contacting.",
            parse_mode="HTML", reply_markup=kb_main()
        )

    # ── My Orders ──
    if text == "📦  My Orders":
        conn = db(); cur = conn.cursor()
        cur.execute("""SELECT order_id, service, link, quantity FROM orders
                       WHERE telegram_id=? ORDER BY rowid DESC LIMIT 5""", (tg,))
        rows = cur.fetchall(); conn.close()
        if not rows:
            return await update.message.reply_text(
                "📦 <b>My Orders</b>\n\nNo orders yet.\nUse <b>🛒 Services</b> to place your first order!",
                parse_mode="HTML", reply_markup=kb_main()
            )
        lines = ["╔═══════════════════════╗", "║   📦 <b>MY RECENT ORDERS</b>   ║", "╚═══════════════════════╝\n"]
        for i, (oid, svc, link, qty) in enumerate(rows, 1):
            api_url, api_key = api_info_for_service(svc)
            st_raw = (check_order_status(oid, api_url, api_key) or {}).get("status", "Unknown")
            icon   = status_icon(st_raw)
            sname  = SERVICE_NAMES.get(svc, svc)
            lines.append(f"<b>#{i}</b>  {sname}")
            lines.append(f"  🔢 Qty: {qty:,}   {icon} {st_raw.title()}")
            lines.append(f"  🆔 <code>{oid}</code>")
            domain = link.replace("https://","").replace("http://","").split("/")[0]
            lines.append(f"  🔗 {domain}\n")
        return await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=kb_main())

    # ══════════════════════════════
    #  💰  RECHARGE
    # ══════════════════════════════
    if text == "💰  Add Balance":
        user_steps[tg] = "recharge"
        return await update.message.reply_text(
            "💰 <b>Add Balance</b>\n\n"
            "Enter the amount you want to add (in ₹):\n"
            "<i>Minimum: ₹10</i>",
            parse_mode="HTML", reply_markup=KB_BACK
        )

    if step == "recharge":
        if not text.isdigit() or int(text) < 10:
            return await update.message.reply_text("❌ Enter a valid amount (minimum ₹10).")
        amt  = int(text)
        link = client.payment_link.create({
            "amount": amt * 100, "currency": "INR",
            "notes": {"telegram_id": str(tg)}
        })
        user_steps.pop(tg, None)
        return await update.message.reply_text(
            f"💳 <b>Payment Link Ready!</b>\n\n"
            f"💰 Amount: <b>₹{amt}</b>\n\n"
            f"👇 Tap to pay:\n{link['short_url']}\n\n"
            "Balance will be added <b>instantly</b> after payment.",
            parse_mode="HTML", reply_markup=kb_main()
        )

    # ══════════════════════════════
    #  🛒  SERVICES
    # ══════════════════════════════
    if text == "🛒  Services":
        return await update.message.reply_text(
            msg_services(), parse_mode="HTML", reply_markup=kb_services()
        )

    # ── YouTube Likes Category ──
    if text == "▶️  YouTube Likes":
        return await update.message.reply_text(
            msg_likes_menu(), parse_mode="HTML", reply_markup=kb_likes()
        )

    # ── Economy Likes ──
    if text.startswith("⚡  Economy Likes"):
        context.user_data["svc_type"]  = "likes_eco"
        context.user_data["svc_name"]  = "⚡ Economy YT Likes"
        context.user_data["svc_id"]    = SVC_LIKE_ECO
        context.user_data["svc_price"] = PRICE_LIKE_ECO
        user_steps[tg] = "svc_link"
        return await update.message.reply_text(
            "⚡ <b>Economy YouTube Likes</b>\n\n"
            "🔗 Send the <b>YouTube video link</b>:",
            parse_mode="HTML", reply_markup=KB_BACK
        )

    # ── Premium Likes ──
    if text.startswith("👑  Premium Likes"):
        context.user_data["svc_type"]  = "likes_prem"
        context.user_data["svc_name"]  = "👑 Premium YT Likes"
        context.user_data["svc_id"]    = SVC_LIKE_PREM
        context.user_data["svc_price"] = PRICE_LIKE_PREM
        user_steps[tg] = "svc_link"
        return await update.message.reply_text(
            "👑 <b>Premium YouTube Likes</b>\n\n"
            "🔗 Send the <b>YouTube video link</b>:",
            parse_mode="HTML", reply_markup=KB_BACK
        )

    # ── YouTube Comments ──
    if text == "💬  YouTube Comments":
        context.user_data["svc_type"]  = "comments"
        context.user_data["svc_name"]  = "💬 YT Custom Comments"
        context.user_data["svc_id"]    = SVC_COMMENT
        context.user_data["svc_price"] = PRICE_COMMENT
        user_steps[tg] = "svc_link"
        return await update.message.reply_text(
            "💬 <b>YouTube Custom Comments</b>\n\n"
            "🔗 Send the <b>YouTube video link</b>:",
            parse_mode="HTML", reply_markup=KB_BACK
        )

    # ══════════════════════════════
    #  🛒  UNIVERSAL SERVICE FLOW
    # ══════════════════════════════

    # Step 1: link received
    if step == "svc_link":
        if not text.startswith("http"):
            return await update.message.reply_text("❌ Please send a valid URL starting with http:// or https://")
        context.user_data["link"] = text
        user_steps[tg] = "svc_qty"
        svc_type = context.user_data.get("svc_type", "")
        if svc_type == "comments":
            return await update.message.reply_text(
                "🔢 <b>Enter quantity</b> (how many comments):\n"
                "<i>Minimum: 10  |  Maximum: 10,000</i>",
                parse_mode="HTML"
            )
        return await update.message.reply_text(
            "🔢 <b>Enter quantity</b>:\n"
            "<i>Minimum: 100  |  Maximum: 100,000</i>",
            parse_mode="HTML"
        )

    # Step 2: quantity received
    if step == "svc_qty":
        if not text.isdigit() or int(text) <= 0:
            return await update.message.reply_text("❌ Invalid quantity. Enter a positive number.")
        qty   = int(text)
        price = round((qty / 1000) * context.user_data["svc_price"], 2)
        context.user_data["qty"]   = qty
        context.user_data["price"] = price

        svc_type = context.user_data.get("svc_type", "")
        if svc_type == "comments":
            user_steps[tg] = "svc_comments_text"
            return await update.message.reply_text(
                f"✍️ <b>Enter comment text</b>\n\n"
                "For multiple comments, put each on a <b>new line</b>:\n"
                "<code>Great video!\nLoved it 🔥\nAmazing content!</code>\n\n"
                "They will be cycled to fill your quantity.",
                parse_mode="HTML"
            )
        else:
            user_steps[tg] = "svc_confirm"
            return await update.message.reply_text(
                msg_order_summary(
                    context.user_data["svc_name"], qty, price, context.user_data["link"]
                ),
                parse_mode="HTML", reply_markup=kb_confirm()
            )

    # Step 2b: comments text
    if step == "svc_comments_text":
        comment_text = text.strip()
        if not comment_text:
            return await update.message.reply_text("❌ Comment text cannot be empty.")
        context.user_data["comment_text"] = comment_text
        user_steps[tg] = "svc_confirm"
        qty   = context.user_data["qty"]
        price = context.user_data["price"]
        preview = comment_text[:60] + ("…" if len(comment_text) > 60 else "")
        return await update.message.reply_text(
            msg_order_summary(
                context.user_data["svc_name"], qty, price, context.user_data["link"]
            ) + f"\n📝 <b>Comment:</b>\n<i>{preview}</i>",
            parse_mode="HTML", reply_markup=kb_confirm()
        )

    # Step 3: confirm / cancel
    if step == "svc_confirm":
        if text != "✅  Confirm Order":
            user_steps.pop(tg, None); context.user_data.clear()
            return await update.message.reply_text("❌ Order cancelled.", reply_markup=kb_main())

        bal   = get_balance(tg)
        price = context.user_data["price"]
        if bal < price:
            return await update.message.reply_text(
                f"❌ <b>Insufficient Balance!</b>\n\n"
                f"💰 Your Balance: ₹{bal}\n"
                f"💸 Required:     ₹{price}\n\n"
                f"Tap <b>💰 Add Balance</b> to recharge.",
                parse_mode="HTML", reply_markup=kb_main()
            )

        svc_type = context.user_data["svc_type"]
        qty      = context.user_data["qty"]
        link     = context.user_data["link"]
        svc_id   = context.user_data["svc_id"]
        svc_name = context.user_data["svc_name"]

        # Build API payload
        payload = {
            "key": SMMHYPE_KEY if svc_type.startswith("likes") else TNTSMM_KEY,
            "action": "add",
            "service": svc_id,
            "link": link,
            "quantity": qty,
        }
        api_url = SMMHYPE_URL if svc_type.startswith("likes") else TNTSMM_URL

        # Add comments field if needed
        if svc_type == "comments":
            payload["key"] = TNTSMM_KEY
            raw_lines = [l.strip() for l in context.user_data["comment_text"].split("\n") if l.strip()]
            if not raw_lines: raw_lines = [context.user_data["comment_text"]]
            repeated = []
            while len(repeated) < qty:
                repeated.extend(raw_lines)
            payload["comments"] = "\n".join(repeated[:qty])

        res = requests.post(api_url, data=payload).json()

        if "order" in res:
            update_balance(tg, -price)
            save_order(res["order"], tg, svc_type, link, qty)
            # Notify admin
            requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                params={
                    "chat_id": ADMIN_ID,
                    "text": (
                        f"🆕 New Order!\n"
                        f"👤 User: {tg}\n"
                        f"📌 Service: {svc_name}\n"
                        f"🔢 Qty: {qty:,}\n"
                        f"💰 Charged: ₹{price}\n"
                        f"🆔 Order ID: {res['order']}"
                    )
                }
            )
            await update.message.reply_text(
                msg_order_placed(res["order"], svc_name, qty),
                parse_mode="HTML", reply_markup=kb_main()
            )
        else:
            err = res.get("error", "Unknown error")
            await update.message.reply_text(
                f"❌ <b>Order Failed</b>\n\n<i>{err}</i>\n\nPlease try again or contact support.",
                parse_mode="HTML", reply_markup=kb_main()
            )

        user_steps.pop(tg, None); context.user_data.clear()

# ══════════════════════════════════════════
#           📋  REGISTER HANDLERS
# ══════════════════════════════════════════
telegram_app.add_handler(CommandHandler("start",        start))
telegram_app.add_handler(CommandHandler("balance",      cmd_balance))
telegram_app.add_handler(CommandHandler("addbalance",   cmd_addbalance))
telegram_app.add_handler(CommandHandler("ban",          cmd_ban))
telegram_app.add_handler(CommandHandler("unban",        cmd_unban))
telegram_app.add_handler(CommandHandler("profit",       cmd_profit))
telegram_app.add_handler(CommandHandler("broadcast",    cmd_broadcast))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ══════════════════════════════════════════
#              🌐  FLASK SERVER
# ══════════════════════════════════════════
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    data   = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    loop   = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_app.process_update(update))
    loop.close()
    return "ok"

@app.route("/webhook", methods=["POST"])
@app.route("/api/webhook", methods=["POST"])
def razorpay_webhook():
    body = request.data
    sig  = request.headers.get("X-Razorpay-Signature", "")
    gen  = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(gen, sig):
        return {"status": "invalid"}, 400
    data = request.json
    if data.get("event") == "payment_link.paid":
        entity = data["payload"]["payment_link"]["entity"]
        tg     = int(entity["notes"]["telegram_id"])
        amt    = entity["amount_paid"] / 100
        pid    = entity["id"]
        if payment_exists(pid):
            return {"status": "duplicate"}
        update_balance(tg, amt)
        save_payment(pid, tg, amt)
        new_bal = get_balance(tg)
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={
                "chat_id": tg,
                "text": (
                    f"✅ <b>Payment Successful!</b>\n\n"
                    f"💰 Added: <b>₹{amt}</b>\n"
                    f"💳 New Balance: <b>₹{new_bal}</b>\n\n"
                    "You can now place orders 🎉"
                ),
                "parse_mode": "HTML"
            }
        )
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": ADMIN_ID, "text": f"💰 New Payment\nUser: {tg}\nAmount: ₹{amt}"}
        )
    return {"status": "ok"}

@app.route("/api/healthz")
@app.route("/healthz")
def health():
    return {"status": "ok", "bot": "running"}

# ══════════════════════════════════════════
#                🚀  STARTUP
# ══════════════════════════════════════════
if __name__ == "__main__":
    # Initialize telegram app once at startup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_app.initialize())

    # Set webhook
    full_webhook_url = APP_URL + WEBHOOK_PATH
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    result = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        params={"url": full_webhook_url}
    ).json()

    print("═" * 45)
    print(f"  🚀 YT SMM Bot Started")
    print(f"  📡 Webhook: {full_webhook_url}")
    print(f"  ✅ Telegram: {result.get('description', result)}")
    print("═" * 45)

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
