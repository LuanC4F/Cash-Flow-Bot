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


def safe_get_records(sheet) -> List[Dict]:
    """Get all records an toàn - xử lý header trùng/rỗng"""
    try:
        return sheet.get_all_records()
    except Exception:
        # Fallback: đọc thủ công khi header có vấn đề
        all_values = sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return []
        
        headers = all_values[0]
        # Lọc bỏ header rỗng, chỉ giữ cột có header
        valid_cols = [i for i, h in enumerate(headers) if h.strip()]
        clean_headers = [headers[i] for i in valid_cols]
        
        records = []
        for row in all_values[1:]:
            record = {}
            for idx, col_idx in enumerate(valid_cols):
                if col_idx < len(row):
                    record[clean_headers[idx]] = row[col_idx]
                else:
                    record[clean_headers[idx]] = ''
            records.append(record)
        return records


# ==================== PRODUCTS ====================

def get_all_products() -> List[Dict]:
    """Get all products"""
    sheet = get_client().worksheet(config.SHEET_PRODUCTS)
    records = safe_get_records(sheet)
    
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


def get_product(sku: str) -> Optional[Dict]:
    """Get product by SKU (alias for find_product_by_sku)"""
    return find_product_by_sku(sku)


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
    records = safe_get_records(sheet)
    
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
    records = safe_get_records(sheet)
    
    total_revenue = 0
    total_profit = 0
    total_quantity = 0
    sale_count = 0
    by_day = {}  # Thêm thống kê theo ngày
    
    for row in records:
        date_str = row.get('Date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                if dt.month == month and dt.year == year:
                    qty = row.get('Qty', 0) or 0
                    price = row.get('Price', 0) or 0  # Price = Tổng tiền thu
                    profit = row.get('Profit', 0) or 0
                    day = dt.day
                    
                    total_revenue += price
                    total_profit += profit
                    total_quantity += qty
                    sale_count += 1
                    
                    # Thống kê theo ngày
                    if day not in by_day:
                        by_day[day] = {'revenue': 0, 'profit': 0, 'count': 0}
                    by_day[day]['revenue'] += price
                    by_day[day]['profit'] += profit
                    by_day[day]['count'] += 1
            except ValueError:
                pass
    
    return {
        'month': month,
        'year': year,
        'sale_count': sale_count,
        'total_quantity': total_quantity,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'by_day': by_day
    }


def get_sales_by_date(day: int, month: int = None, year: int = None) -> List[Dict]:
    """Get sales details for a specific date"""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    target_date = f"{day:02d}/{month:02d}/{year}"
    
    sheet = get_client().worksheet(config.SHEET_SALES)
    records = safe_get_records(sheet)
    
    sales = []
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == target_date:
            sales.append({
                'row': i,
                'date': row.get('Date', ''),
                'sku': row.get('SKU', ''),
                'quantity': row.get('Qty', 0),
                'price': row.get('Price', 0),
                'profit': row.get('Profit', 0),
                'customer': row.get('Customer', ''),
                'note': row.get('Note', '')
            })
    
    return sales


def get_recent_sales(limit: int = 10) -> List[Dict]:
    """Get recent sales"""
    sheet = get_client().worksheet(config.SHEET_SALES)
    records = safe_get_records(sheet)
    
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


def get_sale_by_row(row_num: int) -> Optional[Dict]:
    """Get sale details by row number"""
    try:
        sheet = get_client().worksheet(config.SHEET_SALES)
        row_values = sheet.row_values(row_num)
        
        if not row_values or len(row_values) < 6:
            return None
        
        return {
            'row': row_num,
            'date': row_values[0] if len(row_values) > 0 else '',
            'sku': row_values[1] if len(row_values) > 1 else '',
            'quantity': int(row_values[2]) if len(row_values) > 2 and row_values[2] else 0,
            'price': float(row_values[3]) if len(row_values) > 3 and row_values[3] else 0,
            'cost': float(row_values[4]) if len(row_values) > 4 and row_values[4] else 0,
            'profit': float(row_values[5]) if len(row_values) > 5 and row_values[5] else 0,
            'customer': row_values[6] if len(row_values) > 6 else '',
            'note': row_values[7] if len(row_values) > 7 else ''
        }
    except Exception:
        return None


def update_sale(row_num: int, quantity: int = None, price: float = None, 
                customer: str = None, note: str = None) -> bool:
    """
    Update sale by row number.
    Only updates fields that are provided (not None).
    Recalculates profit if price or quantity changes.
    """
    try:
        sheet = get_client().worksheet(config.SHEET_SALES)
        
        # Get current values
        current = get_sale_by_row(row_num)
        if not current:
            return False
        
        # Update values
        new_qty = quantity if quantity is not None else current['quantity']
        new_price = price if price is not None else current['price']
        new_customer = customer if customer is not None else current['customer']
        new_note = note if note is not None else current['note']
        
        # Recalculate profit
        cost = current['cost']
        new_profit = new_price - (cost * new_qty)
        
        # Update cells
        if quantity is not None:
            sheet.update_cell(row_num, 3, new_qty)  # Column C = Qty
        if price is not None:
            sheet.update_cell(row_num, 4, new_price)  # Column D = Price
            sheet.update_cell(row_num, 6, new_profit)  # Column F = Profit
        if customer is not None:
            sheet.update_cell(row_num, 7, new_customer)  # Column G = Customer
        if note is not None:
            sheet.update_cell(row_num, 8, new_note)  # Column H = Note
        
        # If quantity changed, also update profit
        if quantity is not None and price is None:
            sheet.update_cell(row_num, 6, new_profit)
        
        return True
    except Exception:
        return False


# ==================== EXPENSES ====================

# Column mapping: A=Date, B=Amount, C=Description, D=Category
EXPENSE_COLS = {'date': 1, 'amount': 2, 'description': 3, 'category': 4}


def add_expense(amount: float, description: str, category: str = "Living", date: str = None) -> Dict:
    """Add expense. If date is None, uses today."""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    
    if date is None:
        date = get_local_date()
    row_data = [date, amount, description, category]
    sheet.append_row(row_data)
    
    return {
        'date': date,
        'amount': amount,
        'description': description,
        'category': category
    }


def edit_expense(row_num: int, field: str, value) -> bool:
    """Edit a single field of an expense by row number.
    field: 'date', 'amount', 'description'
    """
    col = EXPENSE_COLS.get(field)
    if not col:
        return False
    try:
        sheet = get_client().worksheet(config.SHEET_EXPENSES)
        sheet.update_cell(row_num, col, value)
        return True
    except Exception:
        return False


def get_today_expenses() -> List[Dict]:
    """Get today's expenses"""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = safe_get_records(sheet)
    
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
    records = safe_get_records(sheet)
    
    total = 0
    count = 0
    by_category = {}
    by_day = {}  # Thêm thống kê theo ngày
    
    for row in records:
        date_str = row.get('Date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                if dt.month == month and dt.year == year:
                    amount = row.get('Amount', 0) or 0
                    category = row.get('Category', 'Other') or 'Other'
                    day = dt.day
                    
                    total += amount
                    count += 1
                    by_category[category] = by_category.get(category, 0) + amount
                    by_day[day] = by_day.get(day, 0) + amount
            except ValueError:
                pass
    
    return {
        'month': month,
        'year': year,
        'count': count,
        'total': total,
        'by_category': by_category,
        'by_day': by_day
    }


def get_expenses_by_date(day: int, month: int = None, year: int = None) -> List[Dict]:
    """Get expense details for a specific date"""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    target_date = f"{day:02d}/{month:02d}/{year}"
    
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = safe_get_records(sheet)
    
    expenses = []
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == target_date:
            expenses.append({
                'row': i,
                'date': row.get('Date', ''),
                'amount': row.get('Amount', 0),
                'description': row.get('Description', ''),
                'category': row.get('Category', '')
            })
    
    return expenses


def get_recent_expenses(limit: int = 10) -> List[Dict]:
    """Get recent expenses"""
    sheet = get_client().worksheet(config.SHEET_EXPENSES)
    records = safe_get_records(sheet)
    
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


# ==================== AVAILABLE MONTHS ====================

def get_available_months() -> List[Dict]:
    """
    Get all months that have saved data (Sales or Expenses).
    Returns sorted list of {month, year} dicts, newest first.
    Excludes current month (already has its own button).
    """
    months_set = set()
    
    # Scan Sales sheet
    try:
        sales_sheet = get_client().worksheet(config.SHEET_SALES)
        for row in safe_get_records(sales_sheet):
            date_str = row.get('Date', '')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, '%d/%m/%Y')
                    months_set.add((dt.month, dt.year))
                except ValueError:
                    pass
    except Exception:
        pass
    
    # Scan Expenses sheet
    try:
        expense_sheet = get_client().worksheet(config.SHEET_EXPENSES)
        for row in safe_get_records(expense_sheet):
            date_str = row.get('Date', '')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, '%d/%m/%Y')
                    months_set.add((dt.month, dt.year))
                except ValueError:
                    pass
    except Exception:
        pass
    
    # Exclude current month
    now = datetime.now(config.VN_TIMEZONE)
    current = (now.month, now.year)
    months_set.discard(current)
    
    # Sort newest first
    result = [{'month': m, 'year': y} for m, y in months_set]
    result.sort(key=lambda x: (x['year'], x['month']), reverse=True)
    
    return result


# ==================== CUSTOMERS ====================

def get_all_saved_customers() -> List[Dict]:
    """Get all customers from Customers sheet, newest first."""
    try:
        sheet = get_client().worksheet(config.SHEET_CUSTOMERS)
        records = safe_get_records(sheet)
    except Exception:
        return []
    
    customers = []
    for i, row in enumerate(records, start=2):
        name = row.get('Name', '').strip()
        if name:
            customers.append({
                'row': i,
                'name': name,
                'telegram_id': str(row.get('TelegramID', '')).strip()
            })
    
    # Newest first (highest row = most recently added)
    customers.reverse()
    return customers


def find_saved_customer(name: str) -> Optional[Dict]:
    """Find a customer by name (case-insensitive)."""
    for c in get_all_saved_customers():
        if c['name'].lower() == name.lower():
            return c
    return None


def save_customer(name: str, telegram_id: str = '') -> Dict:
    """Save customer to Customers sheet. Updates TID if customer already exists."""
    existing = find_saved_customer(name)
    
    if existing:
        # Update TID if we have a new one and old one is empty
        if telegram_id and not existing['telegram_id']:
            sheet = get_client().worksheet(config.SHEET_CUSTOMERS)
            sheet.update_cell(existing['row'], 2, telegram_id)
            existing['telegram_id'] = telegram_id
        return existing
    
    # New customer
    sheet = get_client().worksheet(config.SHEET_CUSTOMERS)
    sheet.append_row([name, telegram_id], value_input_option='USER_ENTERED')
    return {'name': name, 'telegram_id': telegram_id}


def update_customer_telegram_id(name: str, telegram_id: str) -> bool:
    """Update Telegram ID for an existing customer."""
    existing = find_saved_customer(name)
    if not existing:
        return False
    
    sheet = get_client().worksheet(config.SHEET_CUSTOMERS)
    sheet.update_cell(existing['row'], 2, telegram_id)
    return True


def migrate_customers_from_debts() -> int:
    """One-time migration: extract unique customers from Debts into Customers sheet.
    Optimized to minimize API calls (reads sheets once each).
    """
    # Read all data upfront (2 API calls total)
    all_debts = get_all_debts()
    existing_customers = get_all_saved_customers()
    existing_names = {c['name'].lower() for c in existing_customers}
    
    # Collect unique new customers from debts
    new_customers = {}  # key: lowercase name, value: (name, tid)
    for d in all_debts:
        name = d['customer'].strip()
        tid = d.get('telegram_id', '')
        key = name.lower()
        
        if not name or key in existing_names or key in new_customers:
            continue
        new_customers[key] = (name, tid)
    
    if not new_customers:
        return 0
    
    # Batch write all new customers at once
    sheet = get_client().worksheet(config.SHEET_CUSTOMERS)
    rows = [[name, tid] for name, tid in new_customers.values()]
    sheet.append_rows(rows, value_input_option='USER_ENTERED')
    
    return len(rows)


# ==================== DEBT MANAGEMENT ==

def add_debt(customer: str, amount: float, note: str = "", telegram_id: str = "") -> Dict:
    """Add new debt record. Auto-populates Telegram ID and saves customer."""
    sheet = get_client().worksheet(config.SHEET_DEBTS)
    date = get_local_date()
    
    # Auto-populate Telegram ID from Customers sheet first, then Debts
    if not telegram_id:
        telegram_id = get_customer_telegram_id(customer)
    
    # Columns: Date | Customer | Amount | Note | Status | PaidDate | TelegramID
    row = [date, customer, amount, note, "pending", "", telegram_id]
    sheet.append_row(row, value_input_option='USER_ENTERED')
    
    # Auto-save to Customers sheet
    save_customer(customer, telegram_id)
    
    return {
        'date': date,
        'customer': customer,
        'amount': amount,
        'note': note,
        'status': 'pending',
        'telegram_id': telegram_id
    }


def get_all_debts(status: str = None) -> List[Dict]:
    """Get all debts, optionally filter by status (pending/paid)"""
    sheet = get_client().worksheet(config.SHEET_DEBTS)
    records = safe_get_records(sheet)
    
    debts = []
    for i, row in enumerate(records, start=2):
        debt_status = row.get('Status', 'pending')
        if status is None or debt_status == status:
            debts.append({
                'row': i,
                'date': row.get('Date', ''),
                'customer': row.get('Customer', ''),
                'amount': float(row.get('Amount', 0) or 0),
                'note': row.get('Note', ''),
                'status': debt_status,
                'paid_date': row.get('PaidDate', ''),
                'telegram_id': str(row.get('TelegramID', '')).strip()
            })
    
    return debts


def get_debts_by_customer(customer: str) -> List[Dict]:
    """Get all pending debts for a specific customer"""
    all_debts = get_all_debts(status='pending')
    return [d for d in all_debts if d['customer'].lower() == customer.lower()]


def get_debts_by_telegram_id(telegram_id: str) -> List[Dict]:
    """Get all pending debts linked to a Telegram ID"""
    tid = str(telegram_id).strip()
    all_debts = get_all_debts(status='pending')
    return [d for d in all_debts if d.get('telegram_id') == tid]


def get_customer_name_by_telegram_id(telegram_id: str) -> str:
    """Get customer name from their Telegram ID"""
    debts = get_debts_by_telegram_id(telegram_id)
    if debts:
        return debts[0]['customer']
    return ''


def auto_link_telegram_id(customer: str, telegram_id: str) -> int:
    """
    Auto-link Telegram ID to all pending debt records of a customer
    that don't have a TelegramID yet. Returns count of updated rows.
    """
    sheet = get_client().worksheet(config.SHEET_DEBTS)
    debts = get_all_debts(status='pending')
    count = 0
    for d in debts:
        if d['customer'].lower() == customer.lower() and not d.get('telegram_id'):
            sheet.update_cell(d['row'], 7, telegram_id)
            count += 1
    return count


def get_customer_total_debt(customer: str) -> float:
    """Get total pending debt for a customer"""
    debts = get_debts_by_customer(customer)
    return sum(d['amount'] for d in debts)


def get_all_customers_with_debt() -> List[Dict]:
    """Get list of all customers with pending debt"""
    debts = get_all_debts(status='pending')
    
    # Group by customer
    customers = {}
    for d in debts:
        name = d['customer']
        if name not in customers:
            customers[name] = {'customer': name, 'total': 0, 'count': 0, 'telegram_id': ''}
        customers[name]['total'] += d['amount']
        customers[name]['count'] += 1
        # Lấy telegram_id từ bất kỳ khoản nợ nào có
        if d.get('telegram_id') and not customers[name]['telegram_id']:
            customers[name]['telegram_id'] = d['telegram_id']
    
    return list(customers.values())


def mark_debt_paid(row_num: int) -> bool:
    """Mark a debt as paid"""
    try:
        sheet = get_client().worksheet(config.SHEET_DEBTS)
        paid_date = get_local_date()
        # Column E = Status, Column F = PaidDate
        sheet.update_cell(row_num, 5, 'paid')
        sheet.update_cell(row_num, 6, paid_date)
        return True
    except Exception:
        return False


def mark_customer_debts_paid(customer: str) -> int:
    """Mark all debts for a customer as paid, return count"""
    debts = get_debts_by_customer(customer)
    count = 0
    for d in debts:
        if mark_debt_paid(d['row']):
            count += 1
    return count


def get_debt_summary() -> Dict:
    """Get overall debt summary"""
    debts = get_all_debts(status='pending')
    
    total_amount = sum(d['amount'] for d in debts)
    customers = set(d['customer'] for d in debts)
    
    return {
        'total_amount': total_amount,
        'debt_count': len(debts),
        'customer_count': len(customers)
    }


def delete_debt(row_num: int) -> bool:
    """Delete debt by row number"""
    try:
        sheet = get_client().worksheet(config.SHEET_DEBTS)
        sheet.delete_rows(row_num)
        return True
    except Exception:
        return False


def get_customer_telegram_id(customer: str) -> str:
    """Get Telegram ID: Customers sheet first, then Debts fallback."""
    # 1. Check Customers sheet (permanent storage)
    saved = find_saved_customer(customer)
    if saved and saved.get('telegram_id'):
        return saved['telegram_id']
    
    # 2. Fallback: check pending debts
    for d in get_all_debts(status='pending'):
        if d['customer'].lower() == customer.lower() and d.get('telegram_id'):
            return d['telegram_id']
    # 3. Fallback: check paid debts
    for d in get_all_debts(status='paid'):
        if d['customer'].lower() == customer.lower() and d.get('telegram_id'):
            return d['telegram_id']
    return ''


def set_customer_telegram_id(customer: str, telegram_id: str) -> int:
    """
    Set Telegram ID for all debt records of a customer.
    Returns number of rows updated.
    """
    sheet = get_client().worksheet(config.SHEET_DEBTS)
    debts = get_all_debts(status='pending')
    count = 0
    for d in debts:
        if d['customer'].lower() == customer.lower():
            # Column G (7) = TelegramID
            sheet.update_cell(d['row'], 7, telegram_id)
            count += 1
    return count


# ==================== EXPENSE USERS ====================

import time

_expense_users_cache = []
_expense_users_cache_time = 0

import logging as _log
_logger = _log.getLogger(__name__)


def _normalize_tid(raw) -> str:
    """Normalize TelegramID from Google Sheets (may be int, float, or string)."""
    s = str(raw).strip()
    # Handle float like "7955498476.0" → "7955498476"
    if s.endswith('.0'):
        s = s[:-2]
    return s


def get_expense_users(status_filter: str = None) -> List[Dict]:
    """Get all expense users. Optional filter: 'active' or 'inactive'."""
    global _expense_users_cache, _expense_users_cache_time
    
    # Cache for 60 seconds to avoid hitting API quota on every message/callback
    if time.time() - _expense_users_cache_time < 60 and _expense_users_cache:
        users = _expense_users_cache
    else:
        try:
            sheet = get_client().worksheet(config.SHEET_EXPENSE_USERS)
            records = safe_get_records(sheet)
            
            users = []
            for i, row in enumerate(records, start=2):
                raw_tid = row.get('TelegramID', '')
                tid = _normalize_tid(raw_tid)
                status = str(row.get('Status', 'active')).strip().lower()
                if tid:
                    users.append({
                        'row': i,
                        'telegram_id': tid,
                        'name': str(row.get('Name', '')).strip(),
                        'status': status,
                        'sheet_name': str(row.get('SheetName', '')).strip()
                    })
            
            _expense_users_cache = users
            _expense_users_cache_time = time.time()
            _logger.info(f"[ExpenseUsers] Loaded {len(users)} users: {[(u['telegram_id'], u['status']) for u in users]}")
        except Exception as e:
            _logger.error(f"[ExpenseUsers] Failed to load: {e}")
            # Fallback to cache if API fails
            users = _expense_users_cache
    
    if status_filter:
        return [u for u in users if u['status'] == status_filter]
    return users


def is_expense_user(telegram_id) -> bool:
    """Check if a user has active expense tracking access."""
    tid = _normalize_tid(telegram_id)
    active_users = get_expense_users(status_filter='active')
    result = any(u['telegram_id'] == tid for u in active_users)
    _logger.info(f"[ExpenseUsers] is_expense_user({tid}) → {result} (active: {[u['telegram_id'] for u in active_users]})")
    return result


def get_expense_user_info(telegram_id: str) -> Optional[Dict]:
    """Get expense user info by Telegram ID."""
    tid = _normalize_tid(telegram_id)
    for u in get_expense_users():
        if u['telegram_id'] == tid:
            return u
    return None


def add_expense_user(telegram_id: str, name: str) -> Dict:
    """Grant expense tracking access. Creates personal sheet if needed."""
    global _expense_users_cache_time
    _expense_users_cache_time = 0
    
    tid = str(telegram_id).strip()
    sheet_name = f"Chi_{tid}"
    
    # Check if already exists
    existing = get_expense_user_info(tid)
    if existing:
        if existing['status'] == 'inactive':
            # Reactivate
            sheet = get_client().worksheet(config.SHEET_EXPENSE_USERS)
            sheet.update_cell(existing['row'], 3, 'active')
            existing['status'] = 'active'
        return existing
    
    # Add to ExpenseUsers sheet
    sheet = get_client().worksheet(config.SHEET_EXPENSE_USERS)
    sheet.append_row([tid, name, 'active', sheet_name], value_input_option='USER_ENTERED')
    
    # Create personal expense sheet if not exists
    try:
        get_client().worksheet(sheet_name)
    except Exception:
        spreadsheet = get_client()
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=4)
        ws.append_row(['Date', 'Amount', 'Description', 'Category'], value_input_option='USER_ENTERED')
    
    return {'telegram_id': tid, 'name': name, 'status': 'active', 'sheet_name': sheet_name}


def remove_expense_user(telegram_id: str) -> bool:
    """Revoke expense tracking access (set inactive, keep sheet data)."""
    global _expense_users_cache_time
    _expense_users_cache_time = 0
    
    tid = str(telegram_id).strip()
    existing = get_expense_user_info(tid)
    if not existing:
        return False
    
    sheet = get_client().worksheet(config.SHEET_EXPENSE_USERS)
    sheet.update_cell(existing['row'], 3, 'inactive')
    return True


# ==================== USER EXPENSE CRUD ====================

def _get_user_sheet(telegram_id: str):
    """Get the personal expense sheet for a user."""
    info = get_expense_user_info(str(telegram_id).strip())
    if not info:
        raise ValueError("User không có quyền chi tiêu")
    return get_client().worksheet(info['sheet_name'])


def add_user_expense(telegram_id: str, amount: float, description: str, category: str, date: str = None) -> Dict:
    """Add expense to user's personal sheet. If date is None, uses today."""
    sheet = _get_user_sheet(telegram_id)
    if date is None:
        date = get_local_date()
    sheet.append_row([date, amount, description, category], value_input_option='USER_ENTERED')
    return {'date': date, 'amount': amount, 'description': description, 'category': category}


def edit_user_expense(telegram_id: str, row_num: int, field: str, value) -> bool:
    """Edit a single field of a user's expense by row number."""
    col = EXPENSE_COLS.get(field)
    if not col:
        return False
    try:
        sheet = _get_user_sheet(telegram_id)
        sheet.update_cell(row_num, col, value)
        return True
    except Exception:
        return False


def get_user_today_expenses(telegram_id: str) -> List[Dict]:
    """Get today's expenses for a user."""
    sheet = _get_user_sheet(telegram_id)
    records = safe_get_records(sheet)
    today = get_local_date()
    
    expenses = []
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == today:
            expenses.append({
                'row': i,
                'date': today,
                'amount': row.get('Amount', 0),
                'description': row.get('Description', ''),
                'category': row.get('Category', '')
            })
    return expenses


def get_user_today_expense_summary(telegram_id: str) -> Dict:
    """Get today's expense summary for a user."""
    expenses = get_user_today_expenses(telegram_id)
    total = sum(e['amount'] for e in expenses)
    by_category = {}
    for e in expenses:
        cat = e['category'] or 'Other'
        by_category[cat] = by_category.get(cat, 0) + e['amount']
    return {'count': len(expenses), 'total': total, 'by_category': by_category}


def get_user_month_expense_summary(telegram_id: str, month: int = None, year: int = None) -> Dict:
    """Get monthly expense summary for a user."""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    sheet = _get_user_sheet(telegram_id)
    records = safe_get_records(sheet)
    
    total = 0
    count = 0
    by_category = {}
    by_day = {}
    
    for row in records:
        date_str = row.get('Date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                if dt.month == month and dt.year == year:
                    amount = row.get('Amount', 0) or 0
                    category = row.get('Category', 'Other') or 'Other'
                    day = dt.day
                    
                    total += amount
                    count += 1
                    by_category[category] = by_category.get(category, 0) + amount
                    by_day[day] = by_day.get(day, 0) + amount
            except ValueError:
                pass
    
    return {
        'month': month, 'year': year,
        'count': count, 'total': total,
        'by_category': by_category, 'by_day': by_day
    }


def get_user_expenses_by_date(telegram_id: str, day: int, month: int = None, year: int = None) -> List[Dict]:
    """Get expense details for a specific date for a user."""
    if month is None:
        month = datetime.now(config.VN_TIMEZONE).month
    if year is None:
        year = datetime.now(config.VN_TIMEZONE).year
    
    target_date = f"{day:02d}/{month:02d}/{year}"
    sheet = _get_user_sheet(telegram_id)
    records = safe_get_records(sheet)
    
    expenses = []
    for i, row in enumerate(records, start=2):
        if row.get('Date', '') == target_date:
            expenses.append({
                'row': i, 'date': target_date,
                'amount': row.get('Amount', 0),
                'description': row.get('Description', ''),
                'category': row.get('Category', '')
            })
    return expenses


def delete_user_expense(telegram_id: str, row_num: int) -> bool:
    """Delete a user's expense by row number."""
    try:
        sheet = _get_user_sheet(telegram_id)
        sheet.delete_rows(row_num)
        return True
    except Exception:
        return False
