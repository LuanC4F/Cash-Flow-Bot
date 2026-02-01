"""
Google Sheets Service - Read/Write data from Google Sheets
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import Optional, List, Dict

import config


# Google Sheets Scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Global client
_client = None
_spreadsheet = None


def get_client():
    """Get Google Sheets client (singleton)"""
    global _client, _spreadsheet
    
    if _client is None:
        # Ưu tiên đọc từ env variable (cho Render/cloud)
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS')
        
        if google_creds_json:
            # Đọc credentials từ env variable
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            # Đọc từ file (cho local development)
            creds = Credentials.from_service_account_file(
                config.CREDENTIALS_FILE, 
                scopes=SCOPES
            )
        
        _client = gspread.authorize(creds)
        _spreadsheet = _client.open_by_key(config.SHEET_ID)
    
    return _spreadsheet


def get_local_now() -> str:
    """Get current time in Vietnam timezone"""
    return datetime.now(config.VN_TIMEZONE).strftime('%d/%m/%Y %H:%M')


def get_local_date() -> str:
    """Get today's date in Vietnam timezone"""
    return datetime.now(config.VN_TIMEZONE).strftime('%d/%m/%Y')


# ==================== PRODUCTS ====================

def get_all_products() -> List[Dict]:
    """Get all products"""
    sheet = get_client().worksheet(config.SHEET_PRODUCTS)
    records = sheet.get_all_records()
    
    products = []
    for i, row in enumerate(records, start=2):  # start=2 because row 1 is header
        products.append({
            'row': i,
            'sku': row.get('SKU', ''),
            'name': row.get('Name', ''),
            'cost': row.get('Cost', 0)
        })
    
    return products


def find_product_by_sku(sku: str) -> Optional[Dict]:
    """Find product by SKU"""
    products = get_all_products()
    
    for p in products:
        if p['sku'].lower() == sku.lower():
            return p
    
    return None


def find_product_by_name(name: str) -> Optional[Dict]:
    """Find product by name (fuzzy search)"""
    products = get_all_products()
    
    # Exact match first
    for p in products:
        if p['name'].lower() == name.lower():
            return p
    
    # Fuzzy match
    for p in products:
        if name.lower() in p['name'].lower():
            return p
    
    return None


def add_product(sku: str, name: str, cost: float) -> bool:
    """Add new product"""
    sheet = get_client().worksheet(config.SHEET_PRODUCTS)
    
    # Check if SKU already exists
    if find_product_by_sku(sku):
        return False
    
    sheet.append_row([sku, name, cost])
    return True


def update_product(sku: str, cost: float = None, name: str = None) -> bool:
    """Update product"""
    product = find_product_by_sku(sku)
    if not product:
        return False
    
    sheet = get_client().worksheet(config.SHEET_PRODUCTS)
    row = product['row']
    
    if name:
        sheet.update_cell(row, 2, name)
    if cost is not None:
        sheet.update_cell(row, 3, cost)
    
    return True


def delete_product(sku: str) -> bool:
    """Delete product"""
    product = find_product_by_sku(sku)
    if not product:
        return False
    
    sheet = get_client().worksheet(config.SHEET_PRODUCTS)
    sheet.delete_rows(product['row'])
    return True


# ==================== SALES ====================

def add_sale(sku: str, quantity: int, price: float, cost: float, 
             customer: str = "", note: str = "") -> Dict:
    """
    Add sale transaction.
    
    Logic mới:
    - price = TỔNG tiền thu được (không phải giá/sản phẩm)
    - profit = price - (cost × quantity)
    - revenue = price (tổng tiền thu)
    """
    sheet = get_client().worksheet(config.SHEET_SALES)
    
    date = get_local_date()
    total_cost = cost * quantity  # Tổng giá gốc
    profit = price - total_cost   # Lợi nhuận = Tổng thu - Tổng gốc
    
    row_data = [date, sku, quantity, price, cost, profit, customer, note]
    sheet.append_row(row_data)
    
    return {
        'date': date,
        'sku': sku,
        'quantity': quantity,
        'price': price,          # Tổng tiền thu
        'cost': cost,            # Giá gốc/sp
        'total_cost': total_cost,  # Tổng giá gốc
        'profit': profit,
        'revenue': price,        # Doanh thu = Tổng tiền thu
        'customer': customer
    }


def get_today_sales() -> List[Dict]:
    """Get today's sales"""
    sheet = get_client().worksheet(config.SHEET_SALES)
    records = sheet.get_all_records()
    
    today = get_local_date()
    sales = []
    
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == today:
            sales.append({
                'row': i,
                'date': row.get('Date', ''),
                'sku': row.get('SKU', ''),
                'quantity': row.get('Qty', 0),
                'price': row.get('Price', 0),
                'cost': row.get('Cost', 0),
                'profit': row.get('Profit', 0),
                'customer': row.get('Customer', ''),
                'note': row.get('Note', '')
            })
    
    return sales


def get_today_sales_summary() -> Dict:
    """Get today's sales summary"""
    sales = get_today_sales()
    
    total_revenue = sum(s['price'] * s['quantity'] for s in sales)
    total_profit = sum(s['profit'] for s in sales)
    total_quantity = sum(s['quantity'] for s in sales)
    
    return {
        'sale_count': len(sales),
        'total_quantity': total_quantity,
        'total_revenue': total_revenue,
        'total_profit': total_profit
    }


def get_month_sales_summary(month: int = None, year: int = None) -> Dict:
    """Get monthly sales summary"""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    sheet = get_client().worksheet(config.SHEET_SALES)
    records = sheet.get_all_records()
    
    total_revenue = 0
    total_profit = 0
    total_quantity = 0
    sale_count = 0
    
    for row in records:
        date_str = row.get('Date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                if dt.month == month and dt.year == year:
                    qty = row.get('Qty', 0) or 0
                    price = row.get('Price', 0) or 0
                    profit = row.get('Profit', 0) or 0
                    
                    total_revenue += price * qty
                    total_profit += profit
                    total_quantity += qty
                    sale_count += 1
            except ValueError:
                pass
    
    return {
        'month': month,
        'year': year,
        'sale_count': sale_count,
        'total_quantity': total_quantity,
        'total_revenue': total_revenue,
        'total_profit': total_profit
    }


def get_recent_sales(limit: int = 10) -> List[Dict]:
    """Get recent sales"""
    sheet = get_client().worksheet(config.SHEET_SALES)
    records = sheet.get_all_records()
    
    sales = []
    for i, row in enumerate(records, start=2):
        sales.append({
            'row': i,
            'date': row.get('Date', ''),
            'sku': row.get('SKU', ''),
            'quantity': row.get('Qty', 0),
            'price': row.get('Price', 0),
            'profit': row.get('Profit', 0),
            'customer': row.get('Customer', '')
        })
    
    # Return last N transactions
    return sales[-limit:][::-1] if sales else []


def delete_sale(row_num: int) -> bool:
    """Delete sale by row number"""
    try:
        sheet = get_client().worksheet(config.SHEET_SALES)
        sheet.delete_rows(row_num)
        return True
    except Exception:
        return False


# ==================== EXPENSES ====================

def add_expense(amount: float, description: str, category: str = "Living") -> Dict:
    """Add expense"""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    
    date = get_local_date()
    row_data = [date, amount, description, category]
    sheet.append_row(row_data)
    
    return {
        'date': date,
        'amount': amount,
        'description': description,
        'category': category
    }


def get_today_expenses() -> List[Dict]:
    """Get today's expenses"""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = sheet.get_all_records()
    
    today = get_local_date()
    expenses = []
    
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == today:
            expenses.append({
                'row': i,
                'date': row.get('Date', ''),
                'amount': row.get('Amount', 0),
                'description': row.get('Description', ''),
                'category': row.get('Category', '')
            })
    
    return expenses


def get_today_expense_summary() -> Dict:
    """Get today's expense summary"""
    expenses = get_today_expenses()
    
    total = sum(e['amount'] for e in expenses)
    
    # Total by category
    by_category = {}
    for e in expenses:
        cat = e['category'] or 'Other'
        by_category[cat] = by_category.get(cat, 0) + e['amount']
    
    return {
        'count': len(expenses),
        'total': total,
        'by_category': by_category
    }


def get_month_expense_summary(month: int = None, year: int = None) -> Dict:
    """Get monthly expense summary"""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = sheet.get_all_records()
    
    total = 0
    count = 0
    by_category = {}
    
    for row in records:
        date_str = row.get('Date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                if dt.month == month and dt.year == year:
                    amount = row.get('Amount', 0) or 0
                    category = row.get('Category', 'Other') or 'Other'
                    
                    total += amount
                    count += 1
                    by_category[category] = by_category.get(category, 0) + amount
            except ValueError:
                pass
    
    return {
        'month': month,
        'year': year,
        'count': count,
        'total': total,
        'by_category': by_category
    }


def get_recent_expenses(limit: int = 10) -> List[Dict]:
    """Get recent expenses"""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = sheet.get_all_records()
    
    expenses = []
    for i, row in enumerate(records, start=2):
        expenses.append({
            'row': i,
            'date': row.get('Date', ''),
            'amount': row.get('Amount', 0),
            'description': row.get('Description', ''),
            'category': row.get('Category', '')
        })
    
    return expenses[-limit:][::-1] if expenses else []


def delete_expense(row_num: int) -> bool:
    """Delete expense by row number"""
    try:
        sheet = get_client().worksheet(config.SHEET_EXPENSES)
        sheet.delete_rows(row_num)
        return True
    except Exception:
        return False
