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
UEXP_AMOUNT, UEXP_DESC = range(2)

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
        [InlineKeyboardButton("🗑 Xóa Chi Tiêu", callback_data="uexp_delete")],
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
    """Nhận mô tả và hoàn tất"""
    description = update.message.text.strip()
    amount = context.user_data.get('uexp_amount', 0)
    category = context.user_data.get('uexp_category', 'Living')
    tid = str(update.effective_user.id)
    
    try:
        result = sheets.add_user_expense(tid, amount, description, category)
        
        emoji = get_category_emoji(category)
        text = f"""✅ ĐÃ GHI CHI TIÊU!

💸 Số tiền: {format_currency(amount)}
📝 Mô tả: {description}
{emoji} Loại: {category}
📅 Ngày: {result['date']}
"""
        
        today = sheets.get_user_today_expense_summary(tid)
        text += f"━━━ Chi tiêu hôm nay ━━━\n"
        text += f"📊 Số lần: {today['count']} | 💸 Tổng: {format_currency(today['total'])}"
        
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


# ==================== XÓA CHI TIÊU ====================

UEXP_DELETE_ROW = 10

async def uexp_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa chi tiêu"""
    query = update.callback_query
    await query.answer()
    
    tid = str(update.effective_user.id)
    
    try:
        expenses = sheets.get_user_today_expenses(tid)
        
        if not expenses:
            await query.edit_message_text(
                "🗑 *XÓA CHI TIÊU*\n\n📭 Chưa có chi tiêu nào hôm nay.",
                parse_mode='Markdown',
                reply_markup=get_user_expense_menu()
            )
            return ConversationHandler.END
        
        text = "🗑 *XÓA CHI TIÊU*\n\n📋 *Chi tiêu hôm nay:*\n"
        for e in expenses:
            emoji = get_category_emoji(e['category'])
            text += f"• *Row {e['row']}*: {format_currency(e['amount'])} - {e['description']}\n"
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
