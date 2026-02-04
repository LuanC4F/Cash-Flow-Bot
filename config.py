"""
Config module - Cấu hình và biến môi trường
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Google Sheets
SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

# Sheet names
SHEET_PRODUCTS = os.getenv("SHEET_PRODUCTS", "Products")
SHEET_SALES = os.getenv("SHEET_SALES", "Sales")
SHEET_EXPENSES = os.getenv("SHEET_EXPENSES", "Expenses")
SHEET_DEBTS = os.getenv("SHEET_DEBTS", "Debts")

# Bảo mật: Chỉ cho phép user ID này sử dụng bot
# Để lấy ID: chat với @userinfobot trên Telegram
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
if ALLOWED_USER_ID:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID)

# Timezone Vietnam (UTC+7)
from datetime import timezone, timedelta
VN_TIMEZONE = timezone(timedelta(hours=7))
