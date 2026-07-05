"""
Basic handlers - /start, /help, /menu với Inline Buttons
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import config

logger = logging.getLogger(__name__)


def get_main_menu_keyboard():
    """Tạo keyboard menu chính - 2 buttons/hàng"""
    keyboard = [
        [
            InlineKeyboardButton("💸 Chi Tiêu", callback_data="menu_chi"),
            InlineKeyboardButton("🛒 Bán Hàng", callback_data="menu_ban"),
        ],
        [
            InlineKeyboardButton("📦 Sản Phẩm", callback_data="menu_sanpham"),
            InlineKeyboardButton("💳 Nợ Khách", callback_data="menu_no"),
        ],
        [
            InlineKeyboardButton("📊 Thống Kê", callback_data="menu_thongke"),
            InlineKeyboardButton("👥 Quản Lý User", callback_data="admin_users"),
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
            InlineKeyboardButton("🛒 Ghi Bán", callback_data="sales_add"),
            InlineKeyboardButton("📋 Lịch Sử", callback_data="sales_history"),
        ],
        [
            InlineKeyboardButton("🔍 Chi Tiết", callback_data="sales_detail"),
            InlineKeyboardButton("✏️ Sửa Đơn", callback_data="sales_edit"),
        ],
        [
            InlineKeyboardButton("💹 Lãi Tháng", callback_data="sales_profit"),
            InlineKeyboardButton("🗑 Xóa", callback_data="sales_delete"),
        ],
        [
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_stats_keyboard():
    """Keyboard thống kê - có nút tháng cũ"""
    keyboard = [
        [
            InlineKeyboardButton("📅 Hôm Nay", callback_data="stats_today"),
            InlineKeyboardButton("📆 Tháng Này", callback_data="stats_month"),
        ],
        [
            InlineKeyboardButton("💹 Lợi Nhuận", callback_data="stats_profit"),
            InlineKeyboardButton("📂 Tháng Cũ", callback_data="stats_months"),
        ],
        [
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard():
    """Keyboard quay lại"""
    keyboard = [[InlineKeyboardButton("🔙 Menu Chính", callback_data="menu_main")]]
    return InlineKeyboardMarkup(keyboard)


async def safe_edit(query, text, reply_markup=None):
    """Edit message an toàn - fallback không Markdown nếu parse lỗi"""
    try:
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            # Thử lại không Markdown nếu do ký tự đặc biệt
            try:
                clean_text = text.replace('*', '').replace('_', '').replace('`', '')
                await query.edit_message_text(clean_text, reply_markup=reply_markup)
            except Exception:
                raise e

# Import bảo mật từ utils/security.py
# Tùy chỉnh thông báo tại: utils/security.py, dòng 11
from utils.security import check_permission, UNAUTHORIZED_MESSAGE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start - phân quyền 3 cấp"""
    user = update.effective_user
    
    # Admin: menu đầy đủ
    if check_permission(user.id):
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
        return
    
    # Non-admin: check expense user + debt
    from services import sheets
    from utils.formatting import format_currency
    from utils.security import is_expense_user
    
    tid = str(user.id)
    has_expense = is_expense_user(user.id)
    debts = sheets.get_debts_by_telegram_id(tid)
    
    # Expense user + có nợ: hiện cả 2
    if has_expense and debts:
        from handlers.user_expense import get_user_expense_menu
        
        customer = debts[0]['customer']
        total = sum(d['amount'] for d in debts)
        
        text = f"👋 Xin chào {user.first_name or 'bạn'}!\n\n"
        text += f"📋 *CÔNG NỢ HIỆN TẠI*\n👤 {customer}\n\n"
        for d in debts:
            note_text = f" - {d['note']}" if d['note'] else ""
            text += f"• {d['date']}: {format_currency(d['amount'])}{note_text}\n"
        text += f"\n━━━━━━━━━━━━━━━━━\n"
        text += f"💰 *Tổng nợ: {format_currency(total)}*\n\n"
        text += "📌 *Chọn chức năng bên dưới:*"
        
        keyboard = [
            [InlineKeyboardButton(f"💳 Thanh Toán {format_currency(total)}", callback_data=f"custpay_{customer[:15]}")],
            [InlineKeyboardButton("🔄 Kiểm Tra Lại", callback_data="cust_refresh")],
        ]
        # Add expense menu buttons
        keyboard.append([InlineKeyboardButton("💸 Ghi Chi Tiêu", callback_data="uexp_add")])
        keyboard.append([
            InlineKeyboardButton("📋 Hôm Nay", callback_data="uexp_today"),
            InlineKeyboardButton("📊 Tháng Này", callback_data="uexp_month"),
        ])
        keyboard.append([InlineKeyboardButton("🗑 Xóa Chi Tiêu", callback_data="uexp_delete")])
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        await _notify_admin_customer_start(context, user, debts)
        return
    
    # Expense user only (không nợ)
    if has_expense:
        from handlers.user_expense import get_user_expense_menu
        
        await update.message.reply_text(
            f"👋 Xin chào {user.first_name or 'bạn'}!\n\n"
            f"💸 *CHI TIÊU CỦA BẠN*\n\n"
            f"📌 Chọn chức năng bên dưới:",
            parse_mode='Markdown',
            reply_markup=get_user_expense_menu()
        )
        return
    
    # Khách nợ (không có expense access)
    if debts:
        customer = debts[0]['customer']
        total = sum(d['amount'] for d in debts)
        
        text = f"👋 Xin chào {user.first_name or 'bạn'}!\n\n"
        text += f"📋 *CÔNG NỢ HIỆN TẠI*\n"
        text += f"👤 {customer}\n\n"
        
        for d in debts:
            note_text = f" - {d['note']}" if d['note'] else ""
            text += f"• {d['date']}: {format_currency(d['amount'])}{note_text}\n"
        
        text += f"\n━━━━━━━━━━━━━━━━━\n"
        text += f"💰 *Tổng nợ: {format_currency(total)}*"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Thanh Toán {format_currency(total)}", callback_data=f"custpay_{customer[:15]}")],
            [InlineKeyboardButton("🔄 Kiểm Tra Lại", callback_data="cust_refresh")],
        ])
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)
        await _notify_admin_customer_start(context, user, debts)
        return
    
    # User lạ: không có quyền gì
    await update.message.reply_text(
        f"👋 Xin chào {user.first_name or 'bạn'}!\n\n"
        f"Bot này được sử dụng để quản lý thanh toán.\n"
        f"Hiện bạn không có khoản nợ nào.\n\n"
        f"📱 ID của bạn: `{user.id}`",
        parse_mode='Markdown'
    )


async def _notify_admin_customer_start(context, user, debts):
    """Gửi thông báo cho admin khi khách /start bot"""
    if not config.ALLOWED_USER_ID:
        return
    
    try:
        from utils.formatting import format_currency
        
        name = user.full_name or user.first_name or 'N/A'
        username = f"@{user.username}" if user.username else 'Không có'
        
        text = f"🔔 *KHÁCH VỪA START BOT*\n\n"
        text += f"👤 Tên: {name}\n"
        text += f"📱 ID: `{user.id}`\n"
        text += f"🏷 Username: {username}\n"
        
        if debts:
            customer = debts[0]['customer']
            total = sum(d['amount'] for d in debts)
            text += f"\n━━━ 💳 Công Nợ ━━━\n"
            text += f"👤 Khách: {customer}\n"
            text += f"📋 Số khoản nợ: {len(debts)}\n"
            text += f"💰 Tổng nợ: {format_currency(total)}\n"
            
            for d in debts:
                note_text = f" - {d['note']}" if d['note'] else ''
                text += f"  • {d['date']}: {format_currency(d['amount'])}{note_text}\n"
        else:
            text += f"\n✅ Không có khoản nợ nào."
        
        await context.bot.send_message(
            chat_id=config.ALLOWED_USER_ID,
            text=text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Lỗi gửi thông báo admin (customer start): {e}")


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
    
    # Menu Nợ Khách
    elif data == "menu_no":
        from handlers.debt import get_debt_keyboard
        text = """
💳 *QUẢN LÝ NỢ*

Bấm nút bên dưới để thao tác:
"""
        await safe_edit(query, text, get_debt_keyboard())
    
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

*🛒 Bán Hàng:* Chọn SP → nhập giá bán → nhập SL → Nhập người mua → Ghi chú

━━━ *💡 Mẹo* ━━━
• `50k` = 50,000đ
• `1m` = 1,000,000đ
"""
        await safe_edit(query, help_text, get_back_keyboard())
    
    # Admin: Quản lý Expense Users
    elif data == "admin_users":
        from services import sheets
        users = sheets.get_expense_users()
        
        text = "👥 *QUẢN LÝ USER CHI TIÊU*\n\n"
        
        if users:
            for u in users:
                status_icon = "✅" if u['status'] == 'active' else "❌"
                text += f"{status_icon} {u['name']} (`{u['telegram_id']}`)\n"
        else:
            text += "📭 Chưa có user nào.\n"
        
        text += "\n━━━━━━━━━━━━━━━━━\n"
        text += "➕ Để cấp quyền: `/capquyen <TelegramID> <Tên>`\n"
        text += "➖ Bấm nút để thu hồi quyền"
        
        keyboard = []
        active_users = [u for u in users if u['status'] == 'active']
        for u in active_users:
            keyboard.append([InlineKeyboardButton(
                f"❌ Thu hồi: {u['name']}", 
                callback_data=f"admin_rmuser_{u['telegram_id']}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="menu_main")])
        
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("admin_rmuser_"):
        from services import sheets
        tid = data.replace("admin_rmuser_", "")
        
        success = sheets.remove_expense_user(tid)
        if success:
            text = f"✅ Đã thu hồi quyền chi tiêu của user `{tid}`.\nSheet data vẫn giữ nguyên."
        else:
            text = f"❌ Không tìm thấy user `{tid}`."
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Quản Lý User", callback_data="admin_users")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await safe_edit(query, text, keyboard)
    
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
            
            text = f"📊 CHI TIÊU {month_name.upper()}/{summary['year']}\n\n"
            text += f"📊 Số lần chi: {summary['count']}\n"
            text += f"💸 Tổng chi: {format_currency(summary['total'])}\n\n"
            
            if summary['by_category']:
                text += "📂 Theo loại:\n"
                for cat, total in summary['by_category'].items():
                    emoji = get_category_emoji(cat)
                    text += f"   {emoji} {cat}: {format_currency(total)}\n"
            
            # Thêm chi tiêu theo ngày
            if summary.get('by_day'):
                text += "\n📅 Theo ngày:\n"
                sorted_days = sorted(summary['by_day'].items())
                for day, total in sorted_days:
                    text += f"   • Ngày {day}: {format_currency(total)}\n"
            
            # Tạo keyboard với buttons cho từng ngày có chi tiêu
            keyboard = []
            if summary.get('by_day'):
                days = sorted(summary['by_day'].keys())
                row = []
                for day in days:
                    row.append(InlineKeyboardButton(
                        f"📅 {day}", 
                        callback_data=f"expense_day_{day}"
                    ))
                    if len(row) == 4:  # 4 buttons/hàng
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data="menu_chi")])
            
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
    # Xem chi tiết chi tiêu theo ngày
    elif data.startswith("expense_day_"):
        from services import sheets
        from utils.formatting import format_currency, get_category_emoji, get_month_name
        
        try:
            day = int(data.replace("expense_day_", ""))
            expenses = sheets.get_expenses_by_date(day)
            
            from datetime import datetime
            import config
            month = datetime.now(config.VN_TIMEZONE).month
            year = datetime.now(config.VN_TIMEZONE).year
            
            if not expenses:
                text = f"📅 CHI TIÊU NGÀY {day}/{month}/{year}\n\n📭 Không có chi tiêu."
            else:
                total = sum(e['amount'] for e in expenses)
                text = f"📅 CHI TIÊU NGÀY {day}/{month}/{year}\n\n"
                text += f"📊 Số lần: {len(expenses)} | 💸 Tổng: {format_currency(total)}\n\n"
                
                for i, e in enumerate(expenses, 1):
                    emoji = get_category_emoji(e['category'])
                    desc = e['description'] or 'N/A'
                    text += f"{i}. {emoji} {format_currency(e['amount'])}\n"
                    text += f"   📝 {desc}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 Về Tháng", callback_data="expense_month")],
                [InlineKeyboardButton("🔙 Menu Chi", callback_data="menu_chi")]
            ]
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
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
                    profit = float(s['profit']) if s['profit'] else 0
                    profit_emoji = "📈" if profit >= 0 else "📉"
                    text += f"🏷 *{s['sku']}* - Row {s['row']}\n"
                    text += f"   📅 {s['date']} | Qty: {s['quantity']}\n"
                    text += f"   {profit_emoji} Profit: {format_currency(profit)}\n\n"
            
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
            
            expense_summary = sheets.get_month_expense_summary()
            work_expense = sum(
                v for k, v in expense_summary['by_category'].items()
                if k.lower() == 'work'
            )
            net_profit = summary['total_profit'] - work_expense
            
            text = f"💹 LỢI NHUẬN {month_name.upper()}/{summary['year']}\n\n"
            text += f"🛒 Số lần bán: {summary['sale_count']}\n"
            text += f"📦 Tổng SP: {summary['total_quantity']}\n"
            text += f"💰 Doanh thu: {format_currency(summary['total_revenue'])}\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"📈 Lãi gộp: {format_currency(summary['total_profit'])}\n"
            text += f"💼 Chi phí CV: -{format_currency(work_expense)}\n"
            text += f"📊 *Lợi nhuận: {format_currency(net_profit)}*\n"
            
            # Thêm doanh thu theo ngày
            if summary.get('by_day'):
                text += "\n📅 Theo ngày:\n"
                sorted_days = sorted(summary['by_day'].items())
                for day, data_day in sorted_days:
                    text += f"   • Ngày {day}: {format_currency(data_day['revenue'])} (Lãi: {format_currency(data_day['profit'])})\n"
            
            # Tạo keyboard với buttons cho từng ngày có bán hàng
            keyboard = []
            if summary.get('by_day'):
                days = sorted(summary['by_day'].keys())
                row = []
                for day in days:
                    row.append(InlineKeyboardButton(
                        f"📅 {day}", 
                        callback_data=f"sales_day_{day}"
                    ))
                    if len(row) == 4:  # 4 buttons/hàng
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Menu Bán", callback_data="menu_ban")])
            
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
    # Xem chi tiết bán hàng theo ngày
    elif data.startswith("sales_day_"):
        from services import sheets
        from utils.formatting import format_currency
        
        try:
            day = int(data.replace("sales_day_", ""))
            sales = sheets.get_sales_by_date(day)
            
            from datetime import datetime
            import config
            month = datetime.now(config.VN_TIMEZONE).month
            year = datetime.now(config.VN_TIMEZONE).year
            
            if not sales:
                text = f"📅 BÁN HÀNG NGÀY {day}/{month}/{year}\n\n📭 Không có đơn hàng."
            else:
                total_revenue = sum(s['price'] for s in sales)
                total_profit = sum(s['profit'] for s in sales)
                
                text = f"📅 BÁN HÀNG NGÀY {day}/{month}/{year}\n\n"
                text += f"🛒 Số đơn: {len(sales)} | 💰 Thu: {format_currency(total_revenue)}\n"
                text += f"📈 Lợi nhuận: {format_currency(total_profit)}\n\n"
                
                for i, s in enumerate(sales, 1):
                    profit_emoji = "📈" if float(s['profit']) >= 0 else "📉"
                    customer = s['customer'] or 'N/A'
                    text += f"{i}. {s['sku']} x{s['quantity']}\n"
                    text += f"   💰 {format_currency(s['price'])} | {profit_emoji} {format_currency(s['profit'])}\n"
                    text += f"   👤 {customer}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 Về Tháng", callback_data="sales_profit")],
                [InlineKeyboardButton("🔙 Menu Bán", callback_data="menu_ban")]
            ]
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
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
    
    # Danh sách tháng cũ
    elif data == "stats_months":
        from services import sheets
        from utils.formatting import get_month_name
        
        try:
            available = sheets.get_available_months()
            
            if not available:
                await query.answer("❌ Không có dữ liệu tháng cũ.", show_alert=True)
                return
            
            text = "📂 *THỐNG KÊ THÁNG CŨ*\n\n"
            text += "Chọn tháng để xem báo cáo:"
            
            keyboard = []
            # 2 buttons per row
            row = []
            for item in available:
                m, y = item['month'], item['year']
                label = f"📅 {get_month_name(m)}/{y}"
                row.append(InlineKeyboardButton(label, callback_data=f"stats_histmonth_{m}_{y}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Thống Kê", callback_data="menu_thongke")])
            
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Thống kê tháng cũ cụ thể
    elif data.startswith("stats_histmonth_"):
        from services import sheets
        from utils.formatting import format_currency, get_month_name, get_category_emoji
        
        try:
            parts = data.replace("stats_histmonth_", "").split("_")
            month = int(parts[0])
            year = int(parts[1])
            month_name = get_month_name(month)
            
            expense_summary = sheets.get_month_expense_summary(month, year)
            sales_summary = sheets.get_month_sales_summary(month, year)
            
            balance = sales_summary['total_profit'] - expense_summary['total']
            balance_emoji = "📈" if balance >= 0 else "📉"
            
            text = f"📅 *TỔNG KẾT {month_name.upper()}/{year}*\n\n"
            text += f"━━━ *💰 Thu nhập* ━━━\n"
            text += f"🛒 Bán: {sales_summary['sale_count']} | Doanh thu: {format_currency(sales_summary['total_revenue'])}\n"
            text += f"📈 Lợi nhuận: {format_currency(sales_summary['total_profit'])}\n\n"
            text += f"━━━ *💸 Chi tiêu* ━━━\n"
            text += f"📊 Số lần: {expense_summary['count']} | 💸 Tổng: {format_currency(expense_summary['total'])}\n"
            
            if expense_summary['by_category']:
                text += "\n📂 Theo loại:\n"
                for cat, total in expense_summary['by_category'].items():
                    emoji = get_category_emoji(cat)
                    text += f"   {emoji} {cat}: {format_currency(total)}\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━\n"
            text += f"{balance_emoji} *Còn lại: {format_currency(balance)}*"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📋 Chi tiết chi tiêu", callback_data=f"hist_expense_{month}_{year}"),
                    InlineKeyboardButton("💹 Chi tiết bán hàng", callback_data=f"hist_sales_{month}_{year}"),
                ],
                [InlineKeyboardButton("🔙 Tháng Cũ", callback_data="stats_months")],
                [InlineKeyboardButton("🔙 Thống Kê", callback_data="menu_thongke")],
            ])
            
            await safe_edit(query, text, keyboard)
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: `{str(e)}`", get_back_keyboard())
    
    # Chi tiết chi tiêu tháng cũ
    elif data.startswith("hist_expense_"):
        from services import sheets
        from utils.formatting import format_currency, get_month_name, get_category_emoji
        
        try:
            parts = data.replace("hist_expense_", "").split("_")
            month = int(parts[0])
            year = int(parts[1])
            month_name = get_month_name(month)
            
            summary = sheets.get_month_expense_summary(month, year)
            
            text = f"📊 CHI TIÊU {month_name.upper()}/{year}\n\n"
            text += f"📊 Số lần chi: {summary['count']}\n"
            text += f"💸 Tổng chi: {format_currency(summary['total'])}\n\n"
            
            if summary['by_category']:
                text += "📂 Theo loại:\n"
                for cat, total in summary['by_category'].items():
                    emoji = get_category_emoji(cat)
                    text += f"   {emoji} {cat}: {format_currency(total)}\n"
            
            if summary.get('by_day'):
                text += "\n📅 Theo ngày:\n"
                sorted_days = sorted(summary['by_day'].items())
                for day, total in sorted_days:
                    text += f"   • Ngày {day}: {format_currency(total)}\n"
            
            keyboard = []
            if summary.get('by_day'):
                days = sorted(summary['by_day'].keys())
                row = []
                for day in days:
                    row.append(InlineKeyboardButton(
                        f"📅 {day}",
                        callback_data=f"hist_exday_{day}_{month}_{year}"
                    ))
                    if len(row) == 4:
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Tổng kết tháng", callback_data=f"stats_histmonth_{month}_{year}")])
            keyboard.append([InlineKeyboardButton("🔙 Thống Kê", callback_data="menu_thongke")])
            
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
    # Chi tiết chi tiêu theo ngày của tháng cũ
    elif data.startswith("hist_exday_"):
        from services import sheets
        from utils.formatting import format_currency, get_category_emoji
        
        try:
            parts = data.replace("hist_exday_", "").split("_")
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            
            expenses = sheets.get_expenses_by_date(day, month, year)
            
            if not expenses:
                text = f"📅 CHI TIÊU NGÀY {day}/{month}/{year}\n\n📭 Không có chi tiêu."
            else:
                total = sum(e['amount'] for e in expenses)
                text = f"📅 CHI TIÊU NGÀY {day}/{month}/{year}\n\n"
                text += f"📊 Số lần: {len(expenses)} | 💸 Tổng: {format_currency(total)}\n\n"
                
                for i, e in enumerate(expenses, 1):
                    emoji = get_category_emoji(e['category'])
                    desc = e['description'] or 'N/A'
                    text += f"{i}. {emoji} {format_currency(e['amount'])}\n"
                    text += f"   📝 {desc}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 Chi tiêu tháng", callback_data=f"hist_expense_{month}_{year}")],
                [InlineKeyboardButton("🔙 Tổng kết tháng", callback_data=f"stats_histmonth_{month}_{year}")]
            ]
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
    # Chi tiết bán hàng tháng cũ
    elif data.startswith("hist_sales_"):
        from services import sheets
        from utils.formatting import format_currency, get_month_name
        
        try:
            parts = data.replace("hist_sales_", "").split("_")
            month = int(parts[0])
            year = int(parts[1])
            month_name = get_month_name(month)
            
            summary = sheets.get_month_sales_summary(month, year)
            
            expense_summary = sheets.get_month_expense_summary(month, year)
            work_expense = sum(
                v for k, v in expense_summary['by_category'].items()
                if k.lower() == 'work'
            )
            net_profit = summary['total_profit'] - work_expense
            
            text = f"💹 LỢI NHUẬN {month_name.upper()}/{year}\n\n"
            text += f"🛒 Số lần bán: {summary['sale_count']}\n"
            text += f"📦 Tổng SP: {summary['total_quantity']}\n"
            text += f"💰 Doanh thu: {format_currency(summary['total_revenue'])}\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"📈 Lãi gộp: {format_currency(summary['total_profit'])}\n"
            text += f"💼 Chi phí CV: -{format_currency(work_expense)}\n"
            text += f"📊 *Lợi nhuận: {format_currency(net_profit)}*\n"
            
            if summary.get('by_day'):
                text += "\n📅 Theo ngày:\n"
                sorted_days = sorted(summary['by_day'].items())
                for day, data_day in sorted_days:
                    text += f"   • Ngày {day}: {format_currency(data_day['revenue'])} (Lãi: {format_currency(data_day['profit'])})\n"
            
            keyboard = []
            if summary.get('by_day'):
                days = sorted(summary['by_day'].keys())
                row = []
                for day in days:
                    row.append(InlineKeyboardButton(
                        f"📅 {day}",
                        callback_data=f"hist_sday_{day}_{month}_{year}"
                    ))
                    if len(row) == 4:
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Tổng kết tháng", callback_data=f"stats_histmonth_{month}_{year}")])
            keyboard.append([InlineKeyboardButton("🔙 Thống Kê", callback_data="menu_thongke")])
            
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
    
    # Chi tiết bán hàng theo ngày của tháng cũ
    elif data.startswith("hist_sday_"):
        from services import sheets
        from utils.formatting import format_currency
        
        try:
            parts = data.replace("hist_sday_", "").split("_")
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            
            sales = sheets.get_sales_by_date(day, month, year)
            
            if not sales:
                text = f"📅 BÁN HÀNG NGÀY {day}/{month}/{year}\n\n📭 Không có đơn hàng."
            else:
                total_revenue = sum(s['price'] for s in sales)
                total_profit = sum(s['profit'] for s in sales)
                
                text = f"📅 BÁN HÀNG NGÀY {day}/{month}/{year}\n\n"
                text += f"🛒 Số đơn: {len(sales)} | 💰 Thu: {format_currency(total_revenue)}\n"
                text += f"📈 Lợi nhuận: {format_currency(total_profit)}\n\n"
                
                for i, s in enumerate(sales, 1):
                    profit_emoji = "📈" if float(s['profit']) >= 0 else "📉"
                    customer = s['customer'] or 'N/A'
                    text += f"{i}. {s['sku']} x{s['quantity']}\n"
                    text += f"   💰 {format_currency(s['price'])} | {profit_emoji} {format_currency(s['profit'])}\n"
                    text += f"   👤 {customer}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 Bán hàng tháng", callback_data=f"hist_sales_{month}_{year}")],
                [InlineKeyboardButton("🔙 Tổng kết tháng", callback_data=f"stats_histmonth_{month}_{year}")]
            ]
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await safe_edit(query, f"❌ Lỗi: {str(e)}", get_back_keyboard())
