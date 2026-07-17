import os

# ============================
# Telegram Bot
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# ============================
# Razorpay
# ============================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "YOUR_RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv(
    "RAZORPAY_KEY_SECRET",
    "YOUR_RAZORPAY_KEY_SECRET"
)

# ============================
# Database
# ============================

DATABASE_NAME = os.getenv("DATABASE_NAME", "bot.db")

# ============================
# Admin
# ============================

# Replace with your Telegram numeric user ID
ADMIN_IDS = [
    123456789
]

# ============================
# Currency
# ============================

CURRENCY = "INR"

# ============================
# Business
# ============================

BUSINESS_NAME = "Premium Digital Store"

SUPPORT_USERNAME = "@YourSupport"

# ============================
# Wallet
# ============================

MIN_RECHARGE = 100
MAX_RECHARGE = 50000

# ============================
# Logging
# ============================

LOG_LEVEL = "INFO"

# ============================
# Messages
# ============================

WELCOME_MESSAGE = f"""
🚀 Welcome to {BUSINESS_NAME}

Use the menu below to browse products and manage your wallet.
"""

# ============================
# Product Catalog (Example)
# ============================

PRODUCTS = {
    "ebook_python": {
        "name": "Python E-Book",
        "price": 299,
        "description": "Comprehensive Python learning guide."
    },
    "course_ai": {
        "name": "AI Fundamentals Course",
        "price": 999,
        "description": "Beginner-friendly AI video course."
    }
}
