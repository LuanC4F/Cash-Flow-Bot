"""
User Expense Handlers - Chi tiêu cho user được cấp quyền
Mỗi user có sheet riêng, chỉ thấy data của mình.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount, get_month_name, get_category_emoji

logger = logging.getLogger(__name__)

# Conversation states
UEXP_AMOUNT, UEXP_DESC, UEXP_DATE = range(3)
UEXP_EDIT_ROW, UEXP_EDIT_FIELD, UEXP_EDIT_VALUE = range(20, 23)

# Reuse categories from expense.py
CATEGORIES = [
    ("Living", "🏠", "Sinh hoạt"),
    ("Personal", "👤", "Cá nhân"),
    ("Work", "💼", "Công việc"),
    ("Food", "🍜", "Ăn uống"),
    ("Transport", "🚗", "Di chuyển"),
    ("Health", "🏥", "Sức khỏe"),
    ("Entertainment", "🎮", "Giải trí"),
]


# ==================== KEYBOARDS ====================

def get_user_expense_menu():
    """Menu chi tiêu cho user"""
    keyboard = [
        [InlineKeyboardButton("💸 Ghi Chi Tiêu", callback_data="uexp_add")],
        [
            InlineKeyboardButton("📋 Hôm Nay", callback_data="uexp_today"),
            InlineKeyboardButton("📊 Tháng Này", callback_data="uexp_month"),
        ],
        [
            InlineKeyboardButton("📜 Lịch Sử", callback_data="uexp_history"),
        ],
        [
            InlineKeyboardButton("✏️ Sửa Chi Tiêu", callback_data="uexp_edit"),
            InlineKeyboardButton("🗑 Xóa Chi Tiêu", callback_data="uexp_delete"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_category_keyboard():
    """Keyboard chọn category cho user"""
    keyboard = []
    row = []
    for i, (cat, emoji, name) in enumerate(CATEGORIES):
        row.append(InlineKeyboardButton(f"{emoji} {name}", callback_data=f"ucat_{cat}"))
        if len(row) == 2 or i == len(CATEGORIES) - 1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Hủy", callback_data="uexp_cancel")])
    return InlineKeyboardMarkup(keyboard)


def get_user_cancel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Hủy", callback_data="uexp_cancel")]
    ])


# ==================== GHI CHI TIÊU ====================

async def uexp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu ghi chi tiêu - chọn category"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "💸 *GHI CHI TIÊU*\n\n"
            "📝 *Bước 1/3:* Chọn loại chi tiêu\n\n"
            "👇 Chọn category:",
            parse_mode='Markdown',
            reply_markup=get_user_category_keyboard()
        )
        return UEXP_AMOUNT
    return UEXP_AMOUNT


async def uexp_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn category, hỏi số tiền"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("ucat_"):
        category = query.data[5:]
        context.user_data['uexp_category'] = category
        
        emoji = "📝"
        for cat, e, name in CATEGORIES:
            if cat == category:
                emoji = e
                break
        
        await query.edit_message_text(
            f"✅ Loại: {emoji} *{category}*\n\n"
            "📝 *Bước 2/3:* Nhập số tiền\n\n"
            "_Ví dụ: 50k, 50000, 1.5m_",
            parse_mode='Markdown',
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_AMOUNT
    
    return UEXP_AMOUNT


async def uexp_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận số tiền, hỏi mô tả"""
    amount = parse_amount(update.message.text.strip())
    
    if amount is None:
        await update.message.reply_text(
            "❌ Số tiền không hợp lệ!\n\nVui lòng nhập lại (ví dụ: 50k, 50000):",
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_AMOUNT
    
    context.user_data['uexp_amount'] = amount
    
    await update.message.reply_text(
        f"✅ Số tiền: *{format_currency(amount)}*\n\n"
        "📝 *Bước 3/3:* Nhập mô tả\n\n"
        "_Ví dụ: Ăn trưa, Đổ xăng, Mua sách_",
        parse_mode='Markdown',
        reply_markup=get_user_cancel_keyboard()
    )
    return UEXP_DESC


async def uexp_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận mô tả, hỏi ngày"""
    description = update.message.text.strip()
    context.user_data['uexp_desc'] = description
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Hôm Nay", callback_data="uexp_date_today")],
        [InlineKeyboardButton("📅 Hôm Qua", callback_data="uexp_date_yesterday")],
        [InlineKeyboardButton("❌ Hủy", callback_data="uexp_cancel")],
    ])
    
    await update.message.reply_text(
        f"✅ Mô tả: *{description}*\n\n"
        "📅 *Chọn ngày:*\n\n"
        "Bấm nút hoặc nhập ngày (VD: `05/07/2026`)",
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    return UEXP_DATE


async def uexp_date_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn ngày nhanh qua button"""
    query = update.callback_query
    await query.answer()
    
    from datetime import timedelta, datetime
    import config
    
    if query.data == "uexp_date_today":
        date = sheets.get_local_date()
    elif query.data == "uexp_date_yesterday":
        yesterday = datetime.now(config.VN_TIMEZONE) - timedelta(days=1)
        date = yesterday.strftime('%d/%m/%Y')
    else:
        date = sheets.get_local_date()
    
    return await _uexp_save_cb(query, context, date)


async def uexp_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhập ngày thủ công"""
    text = update.message.text.strip()
    
    from datetime import datetime
    try:
        datetime.strptime(text, '%d/%m/%Y')
        date = text
    except ValueError:
        await update.message.reply_text(
            "❌ Sai định dạng! Nhập lại: `dd/mm/yyyy`\n"
            "Ví dụ: `05/07/2026`",
            parse_mode='Markdown',
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_DATE
    
    return await _uexp_save_msg(update, context, date)


async def _uexp_save_cb(query, context, date):
    """Lưu chi tiêu từ callback"""
    amount = context.user_data.get('uexp_amount', 0)
    category = context.user_data.get('uexp_category', 'Living')
    description = context.user_data.get('uexp_desc', '')
    tid = str(query.from_user.id)
    
    try:
        result = sheets.add_user_expense(tid, amount, description, category, date=date)
        emoji = get_category_emoji(category)
        text = f"✅ ĐÃ GHI CHI TIÊU!\n\n💸 Số tiền: {format_currency(amount)}\n📝 Mô tả: {description}\n{emoji} Loại: {category}\n📅 Ngày: {result['date']}\n"
        today = sheets.get_user_today_expense_summary(tid)
        text += f"━━━ Chi tiêu hôm nay ━━━\n📊 Số lần: {today['count']} | 💸 Tổng: {format_currency(today['total'])}"
        await query.edit_message_text(text, reply_markup=get_user_expense_menu())
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}")
    
    context.user_data.clear()
    return ConversationHandler.END


async def _uexp_save_msg(update, context, date):
    """Lưu chi tiêu từ text message"""
    amount = context.user_data.get('uexp_amount', 0)
    category = context.user_data.get('uexp_category', 'Living')
    description = context.user_data.get('uexp_desc', '')
    tid = str(update.effective_user.id)
    
    try:
        result = sheets.add_user_expense(tid, amount, description, category, date=date)
        emoji = get_category_emoji(category)
        text = f"✅ ĐÃ GHI CHI TIÊU!\n\n💸 Số tiền: {format_currency(amount)}\n📝 Mô tả: {description}\n{emoji} Loại: {category}\n📅 Ngày: {result['date']}\n"
        today = sheets.get_user_today_expense_summary(tid)
        text += f"━━━ Chi tiêu hôm nay ━━━\n📊 Số lần: {today['count']} | 💸 Tổng: {format_currency(today['total'])}"
        await update.message.reply_text(text, reply_markup=get_user_expense_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")
    
    context.user_data.clear()
    return ConversationHandler.END


async def uexp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "❌ Đã hủy.",
            reply_markup=get_user_expense_menu()
        )
    context.user_data.clear()
    return ConversationHandler.END


# ==================== THỐNG KÊ ====================

async def uexp_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem chi tiêu hôm nay"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        expenses = sheets.get_user_today_expenses(tid)
        summary = sheets.get_user_today_expense_summary(tid)
        
        if not expenses:
            text = "📋 CHI TIÊU HÔM NAY\n\n📭 Chưa có chi tiêu nào."
        else:
            text = f"📋 CHI TIÊU HÔM NAY ({summary['count']} khoản)\n\n"
            for e in expenses:
                emoji = get_category_emoji(e['category'])
                text += f"• {emoji} {format_currency(e['amount'])} - {e['description']}\n"
            text += f"\n━━━━━━━━━━━━━━━━━\n"
            text += f"💸 Tổng: {format_currency(summary['total'])}"
        
        await query.edit_message_text(text, reply_markup=get_user_expense_menu())
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_user_expense_menu())


async def uexp_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem thống kê tháng"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        summary = sheets.get_user_month_expense_summary(tid)
        month_name = get_month_name(summary['month'])
        
        text = f"📊 CHI TIÊU {month_name.upper()}/{summary['year']}\n\n"
        text += f"📝 Số lần chi: {summary['count']}\n"
        text += f"💸 Tổng chi: {format_currency(summary['total'])}\n"
        
        if summary['by_category']:
            text += "\n📂 Theo loại:\n"
            sorted_cats = sorted(summary['by_category'].items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats:
                emoji = get_category_emoji(cat)
                pct = (amount / summary['total'] * 100) if summary['total'] > 0 else 0
                text += f"   {emoji} {cat}: {format_currency(amount)} ({pct:.0f}%)\n"
        
        if summary['by_day']:
            text += "\n📅 Theo ngày:\n"
            sorted_days = sorted(summary['by_day'].items())
            for day, amount in sorted_days:
                text += f"   • Ngày {day}: {format_currency(amount)}\n"
        
        keyboard = []
        if summary.get('by_day'):
            days = sorted(summary['by_day'].keys())
            row = []
            for day in days:
                row.append(InlineKeyboardButton(f"📅 {day}", callback_data=f"uexp_day_{day}"))
                if len(row) == 4:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton("💸 Ghi Chi Tiêu", callback_data="uexp_add"),
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 Menu", callback_data="uexp_menu"),
        ])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_user_expense_menu())


async def uexp_day_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chi tiết chi tiêu theo ngày"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    day = int(query.data.replace("uexp_day_", ""))
    
    try:
        expenses = sheets.get_user_expenses_by_date(tid, day)
        
        if not expenses:
            text = f"📅 NGÀY {day}\n\n📭 Không có chi tiêu."
        else:
            total = sum(e['amount'] for e in expenses)
            text = f"📅 CHI TIÊU NGÀY {expenses[0]['date']}\n\n"
            for e in expenses:
                emoji = get_category_emoji(e['category'])
                text += f"• {emoji} {format_currency(e['amount'])} - {e['description']}\n"
            text += f"\n━━━━━━━━━━━━━━━━━\n"
            text += f"💸 Tổng: {format_currency(total)}"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Tháng", callback_data="uexp_month")],
            [InlineKeyboardButton("🔙 Menu", callback_data="uexp_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_user_expense_menu())


async def uexp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quay lại menu chi tiêu"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    await query.edit_message_text(
        f"💸 *CHI TIÊU CỦA BẠN*\n\nXin chào {user.first_name or 'bạn'}!\n📌 Chọn chức năng:",
        parse_mode='Markdown',
        reply_markup=get_user_expense_menu()
    )


# ==================== LỊCH SỬ THÁNG TRƯỚC ====================

async def uexp_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiện danh sách tháng có dữ liệu chi tiêu"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        months = sheets.get_user_available_months(tid)
        
        if not months:
            await query.edit_message_text(
                "📜 *LỊCH SỬ CHI TIÊU*\n\n📭 Chưa có dữ liệu tháng trước.",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
            return
        
        text = "📜 *LỊCH SỬ CHI TIÊU*\n\n📅 Chọn tháng để xem:\n"
        
        keyboard = []
        for m in months:
            month_name = get_month_name(m['month'])
            btn_text = f"📅 {month_name}/{m['year']}"
            callback = f"uexp_hmonth_{m['month']}_{m['year']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])
        
        keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="uexp_menu")])
        
        await query.edit_message_text(
            text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_user_expense_menu())


async def uexp_history_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem chi tiết chi tiêu 1 tháng trong lịch sử"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    # Parse: uexp_hmonth_7_2026
    parts = query.data.split('_')
    month = int(parts[2])
    year = int(parts[3])
    
    try:
        summary = sheets.get_user_month_expense_summary(tid, month=month, year=year)
        month_name = get_month_name(month)
        
        text = f"📜 CHI TIÊU {month_name.upper()}/{year}\n\n"
        text += f"📝 Số lần chi: {summary['count']}\n"
        text += f"💸 Tổng chi: {format_currency(summary['total'])}\n"
        
        if summary['by_category']:
            text += "\n📂 Theo loại:\n"
            sorted_cats = sorted(summary['by_category'].items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats:
                emoji = get_category_emoji(cat)
                pct = (amount / summary['total'] * 100) if summary['total'] > 0 else 0
                text += f"   {emoji} {cat}: {format_currency(amount)} ({pct:.0f}%)\n"
        
        if summary['by_day']:
            text += "\n📅 Theo ngày:\n"
            sorted_days = sorted(summary['by_day'].items())
            for day, amount in sorted_days:
                text += f"   • Ngày {day}: {format_currency(amount)}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Lịch Sử", callback_data="uexp_history")],
            [InlineKeyboardButton("🔙 Menu", callback_data="uexp_menu")],
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_user_expense_menu())


# ==================== XÓA CHI TIÊU ====================

UEXP_DELETE_ROW = 10

async def uexp_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa chi tiêu - hiện 10 khoản gần nhất"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        expenses = sheets.get_user_recent_expenses(tid, limit=10)
        
        if not expenses:
            await query.edit_message_text(
                "🗑 *XÓA CHI TIÊU*\n\n📭 Chưa có chi tiêu nào.",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
            return ConversationHandler.END
        
        text = "🗑 *XÓA CHI TIÊU*\n\n📋 *10 khoản gần nhất:*\n"
        for e in expenses:
            emoji = get_category_emoji(e['category'])
            text += f"• *Row {e['row']}*: {format_currency(e['amount'])} - {e['description']} ({e['date']})\n"
        text += "\n⚠️ Nhập số row cần xóa:"
        
        await query.edit_message_text(
            text, parse_mode='Markdown',
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_DELETE_ROW
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}")
        return ConversationHandler.END


async def uexp_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác nhận và xóa"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ! Nhập lại:",
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_DELETE_ROW
    
    tid = str(update.effective_user.id)
    
    try:
        success = sheets.delete_user_expense(tid, row_num)
        if success:
            await update.message.reply_text(
                f"✅ *Đã xóa chi tiêu ở row {row_num}*",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
        else:
            await update.message.reply_text(
                f"❌ Không thể xóa row {row_num}.",
                reply_markup=get_user_expense_menu()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")
    
    return ConversationHandler.END


# ==================== SỬA CHI TIÊU USER ====================

async def uexp_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu sửa chi tiêu - hiện 10 khoản gần nhất"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        expenses = sheets.get_user_recent_expenses(tid, limit=10)
        
        if not expenses:
            await query.edit_message_text(
                "✏️ *SỬA CHI TIÊU*\n\n📭 Chưa có chi tiêu nào.",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
            return ConversationHandler.END
        
        text = "✏️ *SỬA CHI TIÊU*\n\n📋 *10 khoản gần nhất:*\n"
        for e in expenses:
            emoji = get_category_emoji(e['category'])
            text += f"• *Row {e['row']}*: {format_currency(e['amount'])} - {e['description']} ({e['date']})\n"
        text += "\n⚠️ Nhập số row cần sửa:"
        
        await query.edit_message_text(
            text, parse_mode='Markdown',
            reply_markup=get_user_cancel_keyboard()
        )
        return UEXP_EDIT_ROW
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}")
        return ConversationHandler.END


async def uexp_edit_select_row(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn row → hiện menu chọn field"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Số row không hợp lệ! Nhập lại:", reply_markup=get_user_cancel_keyboard())
        return UEXP_EDIT_ROW
    
    context.user_data['uedit_row'] = row_num
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Sửa Ngày", callback_data="ueditf_date")],
        [InlineKeyboardButton("💸 Sửa Số Tiền", callback_data="ueditf_amount")],
        [InlineKeyboardButton("📝 Sửa Mô Tả", callback_data="ueditf_description")],
        [InlineKeyboardButton("❌ Hủy", callback_data="uexp_cancel")],
    ])
    
    await update.message.reply_text(
        f"✏️ Sửa *Row {row_num}*\n\nChọn field cần sửa:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    return UEXP_EDIT_FIELD


async def uexp_edit_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn field → hỏi giá trị mới"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("ueditf_", "")
    context.user_data['uedit_field'] = field
    
    prompts = {
        'date': "📅 Nhập ngày mới (VD: `05/07/2026`):",
        'amount': "💸 Nhập số tiền mới (VD: `50k`, `1.5m`):",
        'description': "📝 Nhập mô tả mới:"
    }
    
    await query.edit_message_text(
        prompts.get(field, "Nhập giá trị mới:"),
        parse_mode='Markdown',
        reply_markup=get_user_cancel_keyboard()
    )
    return UEXP_EDIT_VALUE


async def uexp_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lưu giá trị mới"""
    row_num = context.user_data.get('uedit_row')
    field = context.user_data.get('uedit_field')
    raw = update.message.text.strip()
    tid = str(update.effective_user.id)
    
    if field == 'date':
        from datetime import datetime as dt
        try:
            dt.strptime(raw, '%d/%m/%Y')
            value = raw
        except ValueError:
            await update.message.reply_text("❌ Sai định dạng! Nhập lại: `dd/mm/yyyy`", parse_mode='Markdown', reply_markup=get_user_cancel_keyboard())
            return UEXP_EDIT_VALUE
    elif field == 'amount':
        value = parse_amount(raw)
        if value is None:
            await update.message.reply_text("❌ Số tiền không hợp lệ! Nhập lại:", reply_markup=get_user_cancel_keyboard())
            return UEXP_EDIT_VALUE
    else:
        value = raw
    
    try:
        success = sheets.edit_user_expense(tid, row_num, field, value)
        if success:
            await update.message.reply_text(
                f"✅ Đã sửa *Row {row_num}* — {field}: `{value}`",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
        else:
            await update.message.reply_text(f"❌ Không thể sửa.", reply_markup=get_user_expense_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}", reply_markup=get_user_expense_menu())
    
    context.user_data.clear()
    return ConversationHandler.END
