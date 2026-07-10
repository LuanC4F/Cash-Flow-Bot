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
SHEET_CUSTOMERS = os.getenv("SHEET_CUSTOMERS", "Customers")
SHEET_EXPENSE_USERS = os.getenv("SHEET_EXPENSE_USERS", "ExpenseUsers")

# Bảo mật: Chỉ cho phép user ID này sử dụng bot
# Để lấy ID: chat với @userinfobot trên Telegram
_raw_uid = os.getenv("ALLOWED_USER_ID", "").strip().strip('"').strip("'")
ALLOWED_USER_ID = None
if _raw_uid:
    try:
        ALLOWED_USER_ID = int(_raw_uid)
    except ValueError:
        pass

# SePay + VietQR payment config
SEPAY_API_TOKEN = os.getenv("SEPAY_API_TOKEN", "")
VIETQR_BANK_ID = os.getenv("VIETQR_BANK_ID", "MB")
VIETQR_ACCOUNT_NO = os.getenv("VIETQR_ACCOUNT_NO", "")
VIETQR_ACCOUNT_NAME = os.getenv("VIETQR_ACCOUNT_NAME", "")

# Timezone Vietnam (UTC+7)
from datetime import timezone, timedelta
VN_TIMEZONE = timezone(timedelta(hours=7))
