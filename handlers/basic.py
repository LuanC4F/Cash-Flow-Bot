"""
Basic handlers - /start, /help, /menu với Inline Buttons
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest


def get_main_menu_keyboard():
    """Tạo keyboard menu chính - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("💸 Chi Tiêu", callback_data="menu_chi"),
            InlineKeyboardButton("🛒 Bán Hàng", callback_data="menu_ban"),
        ],
        [
            InlineKeyboardButton("📦 Sản Phẩm", callback_data="menu_sanpham"),
            InlineKeyboardButton("📊 Thống Kê", callback_data="menu_thongke"),
        ],
        [
            InlineKeyboardButton("❓ Hướng Dẫn", callback_data="menu_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_expense_keyboard():
    """Keyboard chi tiêu - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("💸 Ghi Chi Tiêu", callback_data="expense_add"),
        ],
        [
            InlineKeyboardButton("📋 Hôm Nay", callback_data="chitieu_today"),
            InlineKeyboardButton("📊 Tháng", callback_data="expense_month"),
        ],
        [
            InlineKeyboardButton("🗑 Xóa Chi Tiêu", callback_data="expense_delete"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_product_keyboard():
    """Keyboard sản phẩm - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Danh Sách SP", callback_data="sanpham_list"),
        ],
        [
            InlineKeyboardButton("➕ Thêm SP", callback_data="sanpham_add"),
            InlineKeyboardButton("✏️ Sửa Giá", callback_data="sanpham_edit"),
        ],
        [
            InlineKeyboardButton("🗑 Xóa SP", callback_data="sanpham_delete"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_sales_keyboard():
    """Keyboard bán hàng - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("🛒 Ghi Bán Hàng", callback_data="sales_add"),
        ],
        [
            InlineKeyboardButton("📋 Lịch Sử", callback_data="sales_history"),
            InlineKeyboardButton("💹 Lãi Tháng", callback_data="sales_profit"),
        ],
        [
            InlineKeyboardButton("🗑 Xóa Giao Dịch", callback_data="sales_delete"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_stats_keyboard():
    """Keyboard thống kê - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("📅 Hôm Nay", callback_data="stats_today"),
            InlineKeyboardButton("📆 Tháng Này", callback_data="stats_month"),
        ],
        [
            InlineKeyboardButton("💹 Lợi Nhuận", callback_data="stats_profit"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard():
    """Keyboard quay lại"""
    keyboard = [[InlineKeyboardButton("🔙 Menu Chính", callback_data="menu_main")]]
    return InlineKeyboardMarkup(keyboard)


async def safe_edit(query, text, reply_markup=None):
    """Edit message an toàn - bỏ qua lỗi 'message not modified'"""
    try:
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise e

# Import bảo mật từ utils/security.py
# Tùy chỉnh thông báo tại: utils/security.py, dòng 11
from utils.security import check_permission, UNAUTHORIZED_MESSAGE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    user = update.effective_user
    
    # Kiểm tra quyền
    if not check_permission(user.id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    
    welcome_message = f"""
🎉 *Chào mừng {user.first_name or 'bạn'}!*

*CashFlow Bot* - Quản lý thu chi & tính lãi bán hàng tự động.

━━━━━━━━━━━━━━━━━
📌 *Chọn chức năng bên dưới:*
"""
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /help"""
    # Kiểm tra quyền
    if not check_permission(update.effective_user.id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    
    help_text = """
📖 *HƯỚNG DẪN SỬ DỤNG*

━━━ *💸 CHI TIÊU* ━━━
Bấm nút 💸 Ghi Chi Tiêu để được hướng dẫn từng bước.
Hoặc: `/chi 50k Ăn trưa`

━━━ *📦 SẢN PHẨM* ━━━
Bấm nút ➕ Thêm SP để thêm sản phẩm mới.
Hoặc: `/themsp SP01 Áo thun 150k`

━━━ *🛒 BÁN HÀNG* ━━━
Bấm nút 🛒 Ghi Bán Hàng để ghi nhận bán hàng.
Hoặc: `/ban SP01 250k`

━━━ *📊 THỐNG KÊ* ━━━
`/homnay` - Tổng kết hôm nay
`/thang` - Tổng kết tháng

━━━ *💡 MẸO* ━━━
• `50k` = 50,000đ
• `1m` = 1,000,000đ
"""
    
    await update.message.reply_text(
        help_text, 
        parse_mode='Markdown',
        reply_markup=get_back_keyboard()
    )


# ==================== CALLBACK HANDLERS ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng bấm nút"""
    query = update.callback_query
    
    # Kiểm tra quyền
    if not check_permission(query.from_user.id):
        await query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        return
    
    await query.answer()
    
    data = query.data
    
    # Menu chính
    if data == "menu_main":
        text = """
🎉 *MENU CHÍNH*

📌 *Chọn chức năng:*
"""
        await safe_edit(query, text, get_main_menu_keyboard())
    
    # Menu Chi Tiêu
    elif data == "menu_chi":
        text = """
💸 *CHI TIÊU*

Bấm nút bên dưới để thao tác:
"""
        await safe_edit(query, text, get_expense_keyboard())
    
    # Menu Sản Phẩm
    elif data == "menu_sanpham":
        text = """
📦 *SẢN PHẨM*

Bấm nút bên dưới để thao tác:
"""
        await safe_edit(query, text, get_product_keyboard())
    
    # Menu Bán Hàng
    elif data == "menu_ban":
        text = """
🛒 *BÁN HÀNG*

Bấm nút bên dưới để thao tác:
"""
        await safe_edit(query, text, get_sales_keyboard())
    
    # Menu Thống Kê
    elif data == "menu_thongke":
        text = """
📊 *THỐNG KÊ*

Xem báo cáo thu chi và lợi nhuận:
"""
        await safe_edit(query, text, get_stats_keyboard())
    
    # Menu Help
    elif data == "menu_help":
        help_text = """
📖 *HƯỚNG DẪN NHANH*

*💸 Chi Tiêu:* Bấm nút → chọn loại → nhập số tiền → nhập mô tả

*📦 Sản Phẩm:* Thêm SP trước khi bán

*🛒 Bán Hàng:* Chọn SP → nhập giá bán → nhập SL → nhập người mua

━━━ *💡 Mẹo* ━━━
• `50k` = 50,000đ
• `1m` = 1,000,000đ
"""
        await safe_edit(query, help_text, get_back_keyboard())
    
    # ===== ACTIONS =====
    
    # Xem chi tiêu hôm nay
    elif data == "chitieu_today":
        from services import sheets
        from utils.formatting import format_currency, get_category_emoji
        
        try:
            expenses = sheets.get_today_expenses()
            summary = sheets.get_today_expense_summary()
            date = sheets.get_local_date()
            
            if not expenses:
                text = f"💸 *CHI TIÊU - {date}*\n\n📭 Chưa có chi tiêu nào hôm nay."
            else:
                text = f"💸 *CHI TIÊU - {date}*\n\n"
                for e in expenses:
                    emoji = get_category_emoji(e['category'])
                    text += f"{emoji} *Row {e['row']}*: {format_currency(e['amount'])}\n"
                    text += f"   📝 {e['description']}\n\n"
                
                text += f"━━━━━━━━━━━━━━━━━\n"
                text += f"💸 *Tổng chi: {format_currency(summary['total'])}*"
            
            await safe_edit(query, text, get_expense_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Thống kê chi tiêu tháng
    elif data == "expense_month":
        from services import sheets
        from utils.formatting import format_currency, get_month_name, get_category_emoji
        
        try:
            summary = sheets.get_month_expense_summary()
            month_name = get_month_name(summary['month'])
            
            text = f"📊 *CHI TIÊU {month_name.upper()}/{summary['year']}*\n\n"
            text += f"📊 Số lần chi: {summary['count']}\n"
            text += f"💸 *Tổng chi: {format_currency(summary['total'])}*\n\n"
            
            if summary['by_category']:
                text += "📂 *Theo loại:*\n"
                for cat, total in summary['by_category'].items():
                    emoji = get_category_emoji(cat)
                    text += f"   {emoji} {cat}: {format_currency(total)}\n"
            
            await safe_edit(query, text, get_expense_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Xem danh sách sản phẩm
    elif data == "sanpham_list":
        from services import sheets
        from utils.formatting import format_currency
        
        try:
            products = sheets.get_all_products()
            
            if not products:
                text = "📦 *DANH SÁCH SẢN PHẨM*\n\n📭 Chưa có sản phẩm nào."
            else:
                text = "📦 *DANH SÁCH SẢN PHẨM*\n\n"
                for p in products:
                    text += f"🏷 *{p['sku']}* - {p['name']}\n"
                    text += f"   💵 Cost: {format_currency(p['cost'])}\n\n"
            
            await safe_edit(query, text, get_product_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Lịch sử bán hàng
    elif data == "sales_history":
        from services import sheets
        from utils.formatting import format_currency
        
        try:
            sales = sheets.get_recent_sales(limit=10)
            
            if not sales:
                text = "🛒 *LỊCH SỬ BÁN HÀNG*\n\n📭 Chưa có giao dịch nào."
            else:
                text = "🛒 *LỊCH SỬ BÁN HÀNG*\n\n"
                for s in sales:
                    profit_emoji = "📈" if s['profit'] >= 0 else "📉"
                    text += f"🏷 *{s['sku']}* - Row {s['row']}\n"
                    text += f"   📅 {s['date']} | Qty: {s['quantity']}\n"
                    text += f"   {profit_emoji} Profit: {format_currency(s['profit'])}\n\n"
            
            await safe_edit(query, text, get_sales_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Lợi nhuận tháng
    elif data in ["sales_profit", "stats_profit"]:
        from services import sheets
        from utils.formatting import format_currency, get_month_name
        
        try:
            summary = sheets.get_month_sales_summary()
            month_name = get_month_name(summary['month'])
            
            text = f"💹 *LỢI NHUẬN {month_name.upper()}/{summary['year']}*\n\n"
            text += f"🛒 Số lần bán: {summary['sale_count']}\n"
            text += f"📦 Tổng SP: {summary['total_quantity']}\n"
            text += f"💰 Doanh thu: {format_currency(summary['total_revenue'])}\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"📈 *Lợi nhuận: {format_currency(summary['total_profit'])}*"
            
            await safe_edit(query, text, get_stats_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Thống kê hôm nay
    elif data == "stats_today":
        from services import sheets
        from utils.formatting import format_currency
        
        try:
            date = sheets.get_local_date()
            expense_summary = sheets.get_today_expense_summary()
            sales_summary = sheets.get_today_sales_summary()
            
            balance = sales_summary['total_profit'] - expense_summary['total']
            balance_emoji = "📈" if balance >= 0 else "📉"
            
            text = f"📊 *TỔNG KẾT {date}*\n\n"
            text += f"━━━ *💰 Thu nhập* ━━━\n"
            text += f"🛒 Bán: {sales_summary['sale_count']} | 📈 Lãi: {format_currency(sales_summary['total_profit'])}\n\n"
            text += f"━━━ *💸 Chi tiêu* ━━━\n"
            text += f"📊 Số lần: {expense_summary['count']} | 💸 Tổng: {format_currency(expense_summary['total'])}\n\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"{balance_emoji} *Còn lại: {format_currency(balance)}*"
            
            await safe_edit(query, text, get_stats_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Thống kê tháng
    elif data == "stats_month":
        from services import sheets
        from utils.formatting import format_currency, get_month_name
        
        try:
            expense_summary = sheets.get_month_expense_summary()
            sales_summary = sheets.get_month_sales_summary()
            month_name = get_month_name(expense_summary['month'])
            
            balance = sales_summary['total_profit'] - expense_summary['total']
            balance_emoji = "📈" if balance >= 0 else "📉"
            
            text = f"📅 *TỔNG KẾT {month_name.upper()}/{expense_summary['year']}*\n\n"
            text += f"━━━ *💰 Thu nhập* ━━━\n"
            text += f"🛒 Bán: {sales_summary['sale_count']} | Doanh thu: {format_currency(sales_summary['total_revenue'])}\n"
            text += f"📈 Lợi nhuận: {format_currency(sales_summary['total_profit'])}\n\n"
            text += f"━━━ *💸 Chi tiêu* ━━━\n"
            text += f"📊 Số lần: {expense_summary['count']} | 💸 Tổng: {format_currency(expense_summary['total'])}\n\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"{balance_emoji} *Còn lại: {format_currency(balance)}*"
            
            await safe_edit(query, text, get_stats_keyboard())
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
