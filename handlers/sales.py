"""
Sales handlers với Conversation Flow
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount, get_month_name
from utils.security import check_permission, UNAUTHORIZED_MESSAGE

# Conversation states
BAN_SELECT_SP, BAN_PRICE, BAN_QTY, BAN_CUSTOMER, BAN_NOTE = range(5)
XOABH_ROW = 5
CHITIET_ROW = 6
SUABH_ROW, SUABH_FIELD, SUABH_VALUE = range(7, 10)


def get_sales_keyboard():
    """Keyboard bán hàng với đầy đủ buttons"""
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


def get_cancel_keyboard():
    """Keyboard hủy"""
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_sales")]]
    return InlineKeyboardMarkup(keyboard)


def get_skip_keyboard():
    """Keyboard bỏ qua"""
    keyboard = [
        [InlineKeyboardButton("⏭ Bỏ qua", callback_data="skip_step")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_sales")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== GHI BÁN HÀNG - CONVERSATION ====================

async def ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu ghi bán hàng - hiển thị danh sách SP"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            products = sheets.get_all_products()
            
            if not products:
                await query.edit_message_text(
                    "🛒 *GHI BÁN HÀNG*\n\n"
                    "📭 Chưa có sản phẩm nào!\n\n"
                    "💡 Vui lòng thêm sản phẩm trước.",
                    parse_mode='Markdown',
                    reply_markup=get_sales_keyboard()
                )
                return ConversationHandler.END
            
            # Tạo keyboard với danh sách sản phẩm
            keyboard = []
            for p in products:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🏷 {p['sku']} - {p['name']} ({format_currency(p['cost'])})", 
                        callback_data=f"sp_{p['sku']}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel_sales")])
            
            await query.edit_message_text(
                "🛒 *GHI BÁN HÀNG*\n\n"
                "📝 *Bước 1/4:* Chọn sản phẩm\n\n"
                "👇 Chọn SP đã bán:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return BAN_SELECT_SP
            
        except Exception as e:
            await query.edit_message_text(
                f"❌ Lỗi: `{str(e)}`",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
            return ConversationHandler.END
    
    return BAN_SELECT_SP


async def ban_select_sp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn sản phẩm, hỏi giá bán"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("sp_"):
        sku = data[3:]  # Lấy SKU từ callback data
        
        product = sheets.find_product_by_sku(sku)
        if not product:
            await query.edit_message_text(
                f"❌ Không tìm thấy SP `{sku}`!",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
            return ConversationHandler.END
        
        context.user_data['sale_sku'] = sku
        context.user_data['sale_product'] = product
        
        await query.edit_message_text(
            f"✅ Đã chọn: *{product['name']}* (`{sku}`)\n"
            f"💵 Giá gốc/SP: {format_currency(product['cost'])}\n\n"
            "📝 *Bước 2/4:* Nhập *TỔNG TIỀN THU* được\n\n"
            "_Ví dụ: Bán 3 cái được 250k → nhập 250k_",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        
        return BAN_PRICE
    
    return BAN_SELECT_SP


async def ban_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận tổng tiền thu, hỏi số lượng"""
    price = parse_amount(update.message.text.strip())
    
    if price is None:
        await update.message.reply_text(
            "❌ Số tiền không hợp lệ!\n\n"
            "Vui lòng nhập lại (ví dụ: 250k, 250000):",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return BAN_PRICE
    
    context.user_data['sale_price'] = price
    
    await update.message.reply_text(
        f"✅ Tổng tiền thu: *{format_currency(price)}*\n\n"
        "📝 *Bước 3/4:* Nhập số lượng SP đã bán\n\n"
        "_Nhập số hoặc bỏ qua (mặc định = 1)_",
        parse_mode='Markdown',
        reply_markup=get_skip_keyboard()
    )
    
    return BAN_QTY


async def ban_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận số lượng, hỏi người mua"""
    text = update.message.text.strip()
    
    try:
        qty = int(text)
        if qty <= 0:
            qty = 1
    except ValueError:
        qty = 1
    
    context.user_data['sale_qty'] = qty
    
    await update.message.reply_text(
        f"✅ Số lượng: *{qty}*\n\n"
        "📝 *Bước 4/5:* Nhập tên người mua\n\n"
        "_Nhập tên hoặc bỏ qua_",
        parse_mode='Markdown',
        reply_markup=get_skip_keyboard()
    )
    
    return BAN_CUSTOMER


async def ban_qty_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua số lượng"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['sale_qty'] = 1
    
    await query.edit_message_text(
        "✅ Số lượng: *1*\n\n"
        "📝 *Bước 4/5:* Nhập tên người mua\n\n"
        "_Nhập tên hoặc bỏ qua_",
        parse_mode='Markdown',
        reply_markup=get_skip_keyboard()
    )
    
    return BAN_CUSTOMER


async def ban_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận người mua, hỏi ghi chú"""
    customer = update.message.text.strip()
    context.user_data['sale_customer'] = customer
    
    await update.message.reply_text(
        f"✅ Người mua: *{customer}*\n\n"
        "📝 *Bước 5/5:* Nhập ghi chú\n\n"
        "_Ví dụ: Đã ship, COD, v.v. hoặc bỏ qua_",
        parse_mode='Markdown',
        reply_markup=get_skip_keyboard()
    )
    
    return BAN_NOTE


async def ban_customer_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua người mua, hỏi ghi chú"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['sale_customer'] = ""
    
    await query.edit_message_text(
        "✅ Người mua: _(bỏ qua)_\n\n"
        "📝 *Bước 5/5:* Nhập ghi chú\n\n"
        "_Ví dụ: Đã ship, COD, v.v. hoặc bỏ qua_",
        parse_mode='Markdown',
        reply_markup=get_skip_keyboard()
    )
    
    return BAN_NOTE


async def ban_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận ghi chú và hoàn tất"""
    note = update.message.text.strip()
    customer = context.user_data.get('sale_customer', '')
    return await complete_sale(update, context, customer, note=note)


async def ban_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua ghi chú và hoàn tất"""
    query = update.callback_query
    await query.answer()
    customer = context.user_data.get('sale_customer', '')
    return await complete_sale(query, context, customer, note="", is_callback=True)

async def complete_sale(update_or_query, context, customer, note="", is_callback=False):
    """Hoàn tất ghi bán hàng"""
    sku = context.user_data.get('sale_sku', '')
    product = context.user_data.get('sale_product', {})
    price = context.user_data.get('sale_price', 0)  # Tổng tiền thu
    qty = context.user_data.get('sale_qty', 1)
    cost = product.get('cost', 0)  # Giá gốc/sp
    
    try:
        result = sheets.add_sale(
            sku=sku,
            quantity=qty,
            price=price,
            cost=cost,
            customer=customer,
            note=note
        )
        
        profit_emoji = "📈" if result['profit'] >= 0 else "📉"
        total_cost = cost * qty
        
        # Hiển thị ghi chú nếu có
        note_text = f"📝 *Ghi chú:* {note}\n" if note else ""
        
        text = f"""
✅ *ĐÃ GHI BÁN HÀNG!*

🏷 *Sản phẩm:* {product.get('name', '')} ({sku})
📦 *Số lượng:* {qty}
👤 *Người mua:* {customer or 'N/A'}
{note_text}
━━━ *Chi tiết* ━━━
💵 Giá gốc: {format_currency(cost)} × {qty} = {format_currency(total_cost)}
💰 Tổng thu: {format_currency(price)}

━━━ *Kết quả* ━━━
{profit_emoji} *Lợi nhuận: {format_currency(result['profit'])}*
"""
        
        if is_callback:
            await update_or_query.edit_message_text(
                text, 
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
        else:
            await update_or_query.message.reply_text(
                text, 
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
            
    except Exception as e:
        error_text = f"❌ Lỗi: `{str(e)}`"
        if is_callback:
            await update_or_query.edit_message_text(error_text, parse_mode='Markdown')
        else:
            await update_or_query.message.reply_text(error_text, parse_mode='Markdown')
    
    context.user_data.clear()
    return ConversationHandler.END



# ==================== XÓA BÁN HÀNG - CONVERSATION ====================

async def xoabh_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa bán hàng"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            sales = sheets.get_recent_sales(limit=10)
            
            if not sales:
                await query.edit_message_text(
                    "🗑 *XÓA GIAO DỊCH*\n\n📭 Chưa có giao dịch nào.",
                    parse_mode='Markdown',
                    reply_markup=get_sales_keyboard()
                )
                return ConversationHandler.END
            
            text = "🗑 *XÓA GIAO DỊCH*\n\n📋 *Giao dịch gần đây:*\n"
            for s in sales:
                profit = float(s['profit']) if s['profit'] else 0
                profit_emoji = "📈" if profit >= 0 else "📉"
                text += f"• *Row {s['row']}*: {s['sku']} - {format_currency(profit)} ({s['date']})\n"
            
            text += "\n⚠️ Nhập số row cần xóa:"
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=get_cancel_keyboard()
            )
            
            return XOABH_ROW
            
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return XOABH_ROW


async def xoabh_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác nhận và xóa"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return XOABH_ROW
    
    try:
        success = sheets.delete_sale(row_num)
        
        if success:
            await update.message.reply_text(
                f"✅ *Đã xóa giao dịch ở row {row_num}*",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
        else:
            await update.message.reply_text(
                f"❌ Không thể xóa row {row_num}.",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    return ConversationHandler.END


async def cancel_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "❌ *Đã hủy!*",
            parse_mode='Markdown',
            reply_markup=get_sales_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== XEM CHI TIẾT ĐƠN HÀNG ====================

async def chitiet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xem chi tiết"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            sales = sheets.get_recent_sales(limit=10)
            
            if not sales:
                await query.edit_message_text(
                    "🔍 *XEM CHI TIẾT*\n\n📭 Chưa có giao dịch nào.",
                    parse_mode='Markdown',
                    reply_markup=get_sales_keyboard()
                )
                return ConversationHandler.END
            
            text = "🔍 *XEM CHI TIẾT ĐƠN HÀNG*\n\n📋 *Giao dịch gần đây:*\n"
            for s in sales:
                profit = float(s['profit']) if s['profit'] else 0
                text += f"• *Row {s['row']}*: {s['sku']} - {format_currency(profit)} ({s['date']})\n"
            
            text += "\n📝 Nhập số row để xem chi tiết:"
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=get_cancel_keyboard()
            )
            
            return CHITIET_ROW
            
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return CHITIET_ROW


async def chitiet_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị chi tiết đơn hàng"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return CHITIET_ROW
    
    try:
        sale = sheets.get_sale_by_row(row_num)
        
        if not sale:
            await update.message.reply_text(
                f"❌ Không tìm thấy đơn hàng ở row {row_num}",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
            return ConversationHandler.END
        
        # Get product info
        product = sheets.get_product(sale['sku'])
        product_name = product.get('name', sale['sku']) if product else sale['sku']
        
        profit_emoji = "📈" if sale['profit'] >= 0 else "📉"
        total_cost = sale['cost'] * sale['quantity']
        
        text = f"""
🔍 *CHI TIẾT ĐƠN HÀNG - Row {row_num}*

📅 *Ngày:* {sale['date']}
🏷 *Sản phẩm:* {product_name} (`{sale['sku']}`)
📦 *Số lượng:* {sale['quantity']}
👤 *Người mua:* {sale['customer'] or 'N/A'}
📝 *Ghi chú:* {sale['note'] or 'N/A'}

━━━ *Chi tiết tài chính* ━━━
💵 Giá gốc/SP: {format_currency(sale['cost'])}
💰 Tổng gốc: {format_currency(total_cost)}
💎 Tổng thu: {format_currency(sale['price'])}

{profit_emoji} *Lợi nhuận: {format_currency(sale['profit'])}*
"""
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=get_sales_keyboard()
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    return ConversationHandler.END


# ==================== CHỈNH SỬA ĐƠN HÀNG ====================

def get_edit_field_keyboard():
    """Keyboard chọn field cần sửa"""
    keyboard = [
        [
            InlineKeyboardButton("📦 Số lượng", callback_data="edit_qty"),
            InlineKeyboardButton("💰 Tổng thu", callback_data="edit_price"),
        ],
        [
            InlineKeyboardButton("👤 Người mua", callback_data="edit_customer"),
            InlineKeyboardButton("📝 Ghi chú", callback_data="edit_note"),
        ],
        [
            InlineKeyboardButton("❌ Hủy", callback_data="cancel_sales"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def suabh_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu sửa đơn hàng"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            sales = sheets.get_recent_sales(limit=10)
            
            if not sales:
                await query.edit_message_text(
                    "✏️ *SỬA ĐƠN HÀNG*\n\n📭 Chưa có giao dịch nào.",
                    parse_mode='Markdown',
                    reply_markup=get_sales_keyboard()
                )
                return ConversationHandler.END
            
            text = "✏️ *SỬA ĐƠN HÀNG*\n\n📋 *Giao dịch gần đây:*\n"
            for s in sales:
                profit = float(s['profit']) if s['profit'] else 0
                text += f"• *Row {s['row']}*: {s['sku']} - {format_currency(profit)} ({s['date']})\n"
            
            text += "\n📝 Nhập số row cần sửa:"
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=get_cancel_keyboard()
            )
            
            return SUABH_ROW
            
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return SUABH_ROW


async def suabh_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn trường cần sửa"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return SUABH_ROW
    
    # Check if row exists
    sale = sheets.get_sale_by_row(row_num)
    if not sale:
        await update.message.reply_text(
            f"❌ Không tìm thấy đơn hàng ở row {row_num}",
            parse_mode='Markdown',
            reply_markup=get_sales_keyboard()
        )
        return ConversationHandler.END
    
    context.user_data['edit_row'] = row_num
    context.user_data['edit_sale'] = sale
    
    text = f"""
✏️ *SỬA ĐƠN HÀNG - Row {row_num}*

📦 Số lượng: {sale['quantity']}
💰 Tổng thu: {format_currency(sale['price'])}
👤 Người mua: {sale['customer'] or 'N/A'}
📝 Ghi chú: {sale['note'] or 'N/A'}

🔧 *Chọn trường cần sửa:*
"""
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_edit_field_keyboard()
    )
    
    return SUABH_FIELD


async def suabh_get_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận field cần sửa và hỏi giá trị mới"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("edit_", "")
    context.user_data['edit_field'] = field
    
    field_names = {
        'qty': 'Số lượng',
        'price': 'Tổng thu',
        'customer': 'Người mua',
        'note': 'Ghi chú'
    }
    
    field_name = field_names.get(field, field)
    sale = context.user_data.get('edit_sale', {})
    
    current_values = {
        'qty': sale.get('quantity', 0),
        'price': format_currency(sale.get('price', 0)),
        'customer': sale.get('customer', ''),
        'note': sale.get('note', '')
    }
    
    await query.edit_message_text(
        f"✏️ *Sửa {field_name}*\n\n"
        f"Giá trị hiện tại: *{current_values.get(field, 'N/A')}*\n\n"
        f"📝 Nhập giá trị mới:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    
    return SUABH_VALUE


async def suabh_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lưu giá trị mới"""
    new_value = update.message.text.strip()
    row_num = context.user_data.get('edit_row')
    field = context.user_data.get('edit_field')
    
    try:
        if field == 'qty':
            quantity = int(new_value)
            success = sheets.update_sale(row_num, quantity=quantity)
        elif field == 'price':
            price = parse_amount(new_value)
            if price is None:
                await update.message.reply_text(
                    "❌ Số tiền không hợp lệ!\n\nVui lòng nhập lại:",
                    parse_mode='Markdown',
                    reply_markup=get_cancel_keyboard()
                )
                return SUABH_VALUE
            success = sheets.update_sale(row_num, price=price)
        elif field == 'customer':
            success = sheets.update_sale(row_num, customer=new_value)
        elif field == 'note':
            success = sheets.update_sale(row_num, note=new_value)
        else:
            success = False
        
        if success:
            await update.message.reply_text(
                f"✅ *Đã cập nhật row {row_num}!*",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
        else:
            await update.message.reply_text(
                f"❌ Không thể cập nhật row {row_num}.",
                parse_mode='Markdown',
                reply_markup=get_sales_keyboard()
            )
            
    except ValueError:
        await update.message.reply_text(
            "❌ Giá trị không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return SUABH_VALUE
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== COMMAND HANDLERS (backup) ====================

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ban command"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 Cách dùng: `/ban [SKU] [Giá bán] [SL] [Người mua]`\n"
            "Ví dụ: `/ban SP01 250k 2 Minh`\n\n"
            "💡 Hoặc bấm nút 🛒 Ghi Bán Hàng để được hướng dẫn.",
            parse_mode='Markdown',
            reply_markup=get_sales_keyboard()
        )
        return
    
    sku = context.args[0].upper()
    price = parse_amount(context.args[1])
    
    if price is None:
        await update.message.reply_text("❌ Giá bán không hợp lệ.", parse_mode='Markdown')
        return
    
    qty = 1
    customer = ""
    
    if len(context.args) >= 3:
        try:
            qty = int(context.args[2])
        except ValueError:
            customer = context.args[2]
    
    if len(context.args) >= 4:
        customer = ' '.join(context.args[3:])
    
    product = sheets.find_product_by_sku(sku)
    if not product:
        await update.message.reply_text(f"❌ Không tìm thấy `{sku}`.", parse_mode='Markdown')
        return
    
    try:
        result = sheets.add_sale(sku=sku, quantity=qty, price=price, cost=product['cost'], customer=customer)
        profit_emoji = "📈" if result['profit'] >= 0 else "📉"
        
        await update.message.reply_text(
            f"✅ *Đã ghi bán!*\n\n"
            f"🏷 {sku} × {qty} @ {format_currency(price)}\n"
            f"{profit_emoji} Lãi: {format_currency(result['profit'])}",
            parse_mode='Markdown',
            reply_markup=get_sales_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def dsbh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dsbh command"""
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
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_sales_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def laithang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /laithang command"""
    try:
        summary = sheets.get_month_sales_summary()
        month_name = get_month_name(summary['month'])
        
        text = f"💹 *LỢI NHUẬN {month_name.upper()}/{summary['year']}*\n\n"
        text += f"🛒 Số lần bán: {summary['sale_count']}\n"
        text += f"📦 Tổng SP: {summary['total_quantity']}\n"
        text += f"💰 Doanh thu: {format_currency(summary['total_revenue'])}\n"
        text += f"━━━━━━━━━━━━━━━━━\n"
        text += f"📈 *Lợi nhuận: {format_currency(summary['total_profit'])}*"
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_sales_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def xoabh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /xoabh command"""
    if not context.args:
        await update.message.reply_text(
            "📝 Cách dùng: `/xoabh [row]`\nVí dụ: `/xoabh 5`",
            parse_mode='Markdown'
        )
        return
    
    try:
        row_num = int(context.args[0])
        success = sheets.delete_sale(row_num)
        
        if success:
            await update.message.reply_text(f"✅ Đã xóa row {row_num}.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Không thể xóa row {row_num}.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
