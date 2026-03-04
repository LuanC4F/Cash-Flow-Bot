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
import sys
_raw_uid = os.getenv("ALLOWED_USER_ID", "").strip().strip('"').strip("'")
ALLOWED_USER_ID = None
if _raw_uid:
    try:
        ALLOWED_USER_ID = int(_raw_uid)
        sys.stderr.write(f"✅ ALLOWED_USER_ID = {ALLOWED_USER_ID}\n")
        sys.stderr.flush()
    except ValueError:
        sys.stderr.write(f"❌ ALLOWED_USER_ID invalid: '{_raw_uid}'\n")
        sys.stderr.flush()
else:
    sys.stderr.write(f"⚠️ ALLOWED_USER_ID not set! Raw env = '{os.getenv('ALLOWED_USER_ID', 'MISSING')}'\n")
    sys.stderr.flush()

# Timezone Vietnam (UTC+7)
from datetime import timezone, timedelta
VN_TIMEZONE = timezone(timedelta(hours=7))
