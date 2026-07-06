"""
Expense handlers với Conversation Flow
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount, get_month_name, get_category_emoji
from utils.security import check_permission, UNAUTHORIZED_MESSAGE

# Conversation states
CHI_AMOUNT, CHI_DESC, CHI_DATE = range(3)
XOACHI_ROW = 3
SUACHI_ROW, SUACHI_FIELD, SUACHI_VALUE = range(4, 7)

# Categories - text đầy đủ
CATEGORIES = [
    ("Living", "🏠", "Sinh hoạt"),
    ("Personal", "👤", "Cá nhân"),
    ("Work", "💼", "Công việc"),
    ("Food", "🍜", "Ăn uống"),
    ("Transport", "🚗", "Di chuyển"),
    ("Health", "🏥", "Sức khỏe"),
    ("Entertainment", "🎮", "Giải trí"),
]


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
            InlineKeyboardButton("✏️ Sửa Chi Tiêu", callback_data="expense_edit"),
            InlineKeyboardButton("🗑 Xóa Chi Tiêu", callback_data="expense_delete"),
        ],
        [
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard():
    """Keyboard chọn category - 2 buttons mỗi hàng để hiển thị đủ text"""
    keyboard = []
    row = []
    for i, (cat, emoji, name) in enumerate(CATEGORIES):
        row.append(InlineKeyboardButton(f"{emoji} {name}", callback_data=f"cat_{cat}"))
        if len(row) == 2 or i == len(CATEGORIES) - 1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel_expense")])
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Keyboard hủy"""
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_expense")]]
    return InlineKeyboardMarkup(keyboard)


# ==================== GHI CHI TIÊU - CONVERSATION ====================

async def chi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu ghi chi tiêu - chọn category"""
    query = update.callback_query
    if query:
        await query.answer()
        
        await query.edit_message_text(
            "💸 *GHI CHI TIÊU*\n\n"
            "📝 *Bước 1/3:* Chọn loại chi tiêu\n\n"
            "👇 Chọn category:",
            parse_mode='Markdown',
            reply_markup=get_category_keyboard()
        )
        
        return CHI_AMOUNT
    
    return CHI_AMOUNT


async def chi_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn category, hỏi số tiền"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("cat_"):
        category = data[4:]  # Lấy category từ callback
        context.user_data['expense_category'] = category
        
        # Tìm emoji
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
            reply_markup=get_cancel_keyboard()
        )
        
        return CHI_AMOUNT
    
    return CHI_AMOUNT


async def chi_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận số tiền, hỏi mô tả"""
    amount = parse_amount(update.message.text.strip())
    
    if amount is None:
        await update.message.reply_text(
            "❌ Số tiền không hợp lệ!\n\n"
            "Vui lòng nhập lại (ví dụ: 50k, 50000):",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return CHI_AMOUNT
    
    context.user_data['expense_amount'] = amount
    category = context.user_data.get('expense_category', 'Living')
    
    await update.message.reply_text(
        f"✅ Số tiền: *{format_currency(amount)}*\n\n"
        "📝 *Bước 3/3:* Nhập mô tả\n\n"
        "_Ví dụ: Ăn trưa, Đổ xăng, Mua sách_",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    
    return CHI_DESC


async def chi_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận mô tả, hỏi ngày"""
    description = update.message.text.strip()
    context.user_data['expense_desc'] = description
    
    amount = context.user_data.get('expense_amount', 0)
    category = context.user_data.get('expense_category', 'Living')
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Hôm Nay", callback_data="expense_date_today")],
        [InlineKeyboardButton("📅 Hôm Qua", callback_data="expense_date_yesterday")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_expense")],
    ])
    
    await update.message.reply_text(
        f"✅ Mô tả: *{description}*\n\n"
        "📅 *Chọn ngày:*\n\n"
        "Bấm nút hoặc nhập ngày (VD: `05/07/2026`)",
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    
    return CHI_DATE


async def chi_date_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn ngày nhanh qua button"""
    query = update.callback_query
    await query.answer()
    
    from datetime import timedelta
    
    if query.data == "expense_date_today":
        date = sheets.get_local_date()
    elif query.data == "expense_date_yesterday":
        from datetime import datetime
        import config
        yesterday = datetime.now(config.VN_TIMEZONE) - timedelta(days=1)
        date = yesterday.strftime('%d/%m/%Y')
    else:
        date = sheets.get_local_date()
    
    return await _save_expense(query, context, date)


async def chi_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhập ngày thủ công"""
    text = update.message.text.strip()
    
    # Validate format dd/mm/yyyy
    from datetime import datetime
    try:
        datetime.strptime(text, '%d/%m/%Y')
        date = text
    except ValueError:
        await update.message.reply_text(
            "❌ Sai định dạng! Nhập lại: `dd/mm/yyyy`\n"
            "Ví dụ: `05/07/2026`",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return CHI_DATE
    
    return await _save_expense_msg(update, context, date)


async def _save_expense(query, context, date):
    """Lưu chi tiêu từ callback query"""
    amount = context.user_data.get('expense_amount', 0)
    category = context.user_data.get('expense_category', 'Living')
    description = context.user_data.get('expense_desc', '')
    
    try:
        result = sheets.add_expense(amount, description, category, date=date)
        emoji = get_category_emoji(category)
        
        text = f"""✅ ĐÃ GHI CHI TIÊU!

💸 Số tiền: {format_currency(amount)}
📝 Mô tả: {description}
{emoji} Loại: {category}
📅 Ngày: {result['date']}
"""
        today_summary = sheets.get_today_expense_summary()
        text += f"━━━ Chi tiêu hôm nay ━━━\n"
        text += f"📊 Số lần: {today_summary['count']} | 💸 Tổng: {format_currency(today_summary['total'])}"
        
        await query.edit_message_text(text, reply_markup=get_expense_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    context.user_data.clear()
    return ConversationHandler.END


async def _save_expense_msg(update, context, date):
    """Lưu chi tiêu từ text message"""
    amount = context.user_data.get('expense_amount', 0)
    category = context.user_data.get('expense_category', 'Living')
    description = context.user_data.get('expense_desc', '')
    
    try:
        result = sheets.add_expense(amount, description, category, date=date)
        emoji = get_category_emoji(category)
        
        text = f"""✅ ĐÃ GHI CHI TIÊU!

💸 Số tiền: {format_currency(amount)}
📝 Mô tả: {description}
{emoji} Loại: {category}
📅 Ngày: {result['date']}
"""
        today_summary = sheets.get_today_expense_summary()
        text += f"━━━ Chi tiêu hôm nay ━━━\n"
        text += f"📊 Số lần: {today_summary['count']} | 💸 Tổng: {format_currency(today_summary['total'])}"
        
        await update.message.reply_text(text, reply_markup=get_expense_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== SỬA CHI TIÊU ====================

async def suachi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu sửa chi tiêu - hiện danh sách hôm nay"""
    query = update.callback_query
    if query:
        await query.answer()
        try:
            expenses = sheets.get_today_expenses()
            if not expenses:
                await query.edit_message_text(
                    "✏️ *SỬA CHI TIÊU*\n\n📭 Chưa có chi tiêu nào hôm nay.",
                    parse_mode='Markdown',
                    reply_markup=get_expense_keyboard()
                )
                return ConversationHandler.END
            
            text = "✏️ *SỬA CHI TIÊU*\n\n📋 *Chi tiêu hôm nay:*\n"
            for e in expenses:
                emoji = get_category_emoji(e['category'])
                text += f"• *Row {e['row']}*: {format_currency(e['amount'])} - {e['description']} ({e['date']})\n"
            text += "\n⚠️ Nhập số row cần sửa:"
            
            await query.edit_message_text(
                text, parse_mode='Markdown',
                reply_markup=get_cancel_keyboard()
            )
            return SUACHI_ROW
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    return SUACHI_ROW


async def suachi_select_row(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn row → hiện menu chọn field"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Số row không hợp lệ! Nhập lại:", reply_markup=get_cancel_keyboard())
        return SUACHI_ROW
    
    context.user_data['edit_row'] = row_num
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Sửa Ngày", callback_data="editfield_date")],
        [InlineKeyboardButton("💸 Sửa Số Tiền", callback_data="editfield_amount")],
        [InlineKeyboardButton("📝 Sửa Mô Tả", callback_data="editfield_description")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_expense")],
    ])
    
    await update.message.reply_text(
        f"✏️ Sửa *Row {row_num}*\n\nChọn field cần sửa:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    return SUACHI_FIELD


async def suachi_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn field → hỏi giá trị mới"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("editfield_", "")
    context.user_data['edit_field'] = field
    
    prompts = {
        'date': "📅 Nhập ngày mới (VD: `05/07/2026`):",
        'amount': "💸 Nhập số tiền mới (VD: `50k`, `1.5m`):",
        'description': "📝 Nhập mô tả mới:"
    }
    
    await query.edit_message_text(
        prompts.get(field, "Nhập giá trị mới:"),
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    return SUACHI_VALUE


async def suachi_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lưu giá trị mới"""
    row_num = context.user_data.get('edit_row')
    field = context.user_data.get('edit_field')
    raw = update.message.text.strip()
    
    # Validate
    if field == 'date':
        from datetime import datetime as dt
        try:
            dt.strptime(raw, '%d/%m/%Y')
            value = raw
        except ValueError:
            await update.message.reply_text("❌ Sai định dạng! Nhập lại: `dd/mm/yyyy`", parse_mode='Markdown', reply_markup=get_cancel_keyboard())
            return SUACHI_VALUE
    elif field == 'amount':
        value = parse_amount(raw)
        if value is None:
            await update.message.reply_text("❌ Số tiền không hợp lệ! Nhập lại:", reply_markup=get_cancel_keyboard())
            return SUACHI_VALUE
    else:
        value = raw
    
    try:
        success = sheets.edit_expense(row_num, field, value)
        if success:
            await update.message.reply_text(
                f"✅ Đã sửa *Row {row_num}* — {field}: `{value}`",
                parse_mode='Markdown',
                reply_markup=get_expense_keyboard()
            )
        else:
            await update.message.reply_text(f"❌ Không thể sửa.", reply_markup=get_expense_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}", reply_markup=get_expense_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== XÓA CHI TIÊU - CONVERSATION ====================

async def xoachi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa chi tiêu"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            expenses = sheets.get_today_expenses()
            
            if not expenses:
                await query.edit_message_text(
                    "🗑 *XÓA CHI TIÊU*\n\n📭 Chưa có chi tiêu nào hôm nay.",
                    parse_mode='Markdown',
                    reply_markup=get_expense_keyboard()
                )
                return ConversationHandler.END
            
            text = "🗑 *XÓA CHI TIÊU*\n\n📋 *Chi tiêu hôm nay:*\n"
            for e in expenses:
                emoji = get_category_emoji(e['category'])
                text += f"• *Row {e['row']}*: {format_currency(e['amount'])} - {e['description']}\n"
            
            text += "\n⚠️ Nhập số row cần xóa:"
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=get_cancel_keyboard()
            )
            
            return XOACHI_ROW
            
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return XOACHI_ROW


async def xoachi_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác nhận và xóa"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return XOACHI_ROW
    
    try:
        success = sheets.delete_expense(row_num)
        
        if success:
            await update.message.reply_text(
                f"✅ *Đã xóa chi tiêu ở row {row_num}*",
                parse_mode='Markdown',
                reply_markup=get_expense_keyboard()
            )
        else:
            await update.message.reply_text(
                f"❌ Không thể xóa row {row_num}.",
                parse_mode='Markdown',
                reply_markup=get_expense_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    return ConversationHandler.END


async def cancel_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "❌ *Đã hủy!*",
            parse_mode='Markdown',
            reply_markup=get_expense_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== COMMAND HANDLERS (backup) ====================

async def chi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chi command"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 Cách dùng: `/chi [số tiền] [mô tả] [category]`\n"
            "Ví dụ: `/chi 50k Ăn trưa`\n\n"
            "💡 Hoặc bấm nút 💸 Ghi Chi Tiêu để được hướng dẫn.",
            parse_mode='Markdown',
            reply_markup=get_expense_keyboard()
        )
        return
    
    amount = parse_amount(context.args[0])
    if amount is None:
        await update.message.reply_text("❌ Số tiền không hợp lệ.", parse_mode='Markdown')
        return
    
    # Parse description và category
    remaining = ' '.join(context.args[1:])
    parts = remaining.rsplit(maxsplit=1)
    
    category_keywords = ['living', 'personal', 'work', 'food', 'transport', 'health', 'entertainment']
    
    if len(parts) == 2 and parts[1].lower() in category_keywords:
        description = parts[0]
        category = parts[1].title()
    else:
        description = remaining
        category = 'Living'
    
    try:
        result = sheets.add_expense(amount, description, category)
        emoji = get_category_emoji(category)
        
        await update.message.reply_text(
            f"✅ *Đã ghi chi tiêu!*\n\n"
            f"💸 {format_currency(amount)} | {emoji} {category}\n"
            f"📝 {description}",
            parse_mode='Markdown',
            reply_markup=get_expense_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def chitieu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chitieu command"""
    try:
        expenses = sheets.get_today_expenses()
        summary = sheets.get_today_expense_summary()
        date = sheets.get_local_date()
        
        if not expenses:
            text = f"💸 CHI TIÊU - {date}\n\n📭 Chưa có chi tiêu nào hôm nay."
        else:
            text = f"💸 CHI TIÊU - {date}\n\n"
            for e in expenses:
                emoji = get_category_emoji(e['category'])
                text += f"{emoji} Row {e['row']}: {format_currency(e['amount'])}\n"
                text += f"   📝 {e['description']}\n\n"
            
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"💸 Tổng chi: {format_currency(summary['total'])}"
        
        await update.message.reply_text(text, reply_markup=get_expense_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def homnay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /homnay command"""
    try:
        date = sheets.get_local_date()
        expense_summary = sheets.get_today_expense_summary()
        sales_summary = sheets.get_today_sales_summary()
        
        balance = sales_summary['total_profit'] - expense_summary['total']
        balance_emoji = "📈" if balance >= 0 else "📉"
        
        text = f"📊 TỔNG KẾT {date}\n\n"
        text += f"━━━ 💰 Thu nhập ━━━\n"
        text += f"🛒 Bán: {sales_summary['sale_count']} | 📈 Lãi: {format_currency(sales_summary['total_profit'])}\n\n"
        text += f"━━━ 💸 Chi tiêu ━━━\n"
        text += f"📊 Số lần: {expense_summary['count']} | 💸 Tổng: {format_currency(expense_summary['total'])}\n\n"
        text += f"━━━━━━━━━━━━━━━━━\n"
        text += f"{balance_emoji} Còn lại: {format_currency(balance)}"
        
        await update.message.reply_text(text, reply_markup=get_expense_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def thang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /thang command"""
    try:
        expense_summary = sheets.get_month_expense_summary()
        sales_summary = sheets.get_month_sales_summary()
        month_name = get_month_name(expense_summary['month'])
        
        balance = sales_summary['total_profit'] - expense_summary['total']
        balance_emoji = "📈" if balance >= 0 else "📉"
        
        text = f"📅 TỔNG KẾT {month_name.upper()}/{expense_summary['year']}\n\n"
        text += f"━━━ 💰 Thu nhập ━━━\n"
        text += f"🛒 Bán: {sales_summary['sale_count']} | Doanh thu: {format_currency(sales_summary['total_revenue'])}\n"
        text += f"📈 Lợi nhuận: {format_currency(sales_summary['total_profit'])}\n\n"
        text += f"━━━ 💸 Chi tiêu ━━━\n"
        text += f"📊 Số lần: {expense_summary['count']} | 💸 Tổng: {format_currency(expense_summary['total'])}\n\n"
        text += f"━━━━━━━━━━━━━━━━━\n"
        text += f"{balance_emoji} Còn lại: {format_currency(balance)}"
        
        await update.message.reply_text(text, reply_markup=get_expense_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def xoachi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /xoachi command"""
    if not context.args:
        await update.message.reply_text(
            "📝 Cách dùng: `/xoachi [row]`\nVí dụ: `/xoachi 5`",
            parse_mode='Markdown'
        )
        return
    
    try:
        row_num = int(context.args[0])
        success = sheets.delete_expense(row_num)
        
        if success:
            await update.message.reply_text(f"✅ Đã xóa row {row_num}.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Không thể xóa row {row_num}.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
