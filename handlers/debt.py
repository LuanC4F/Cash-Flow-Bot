"""
Debt Management Handlers - Quản lý nợ khách hàng
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount
from utils.security import check_permission, UNAUTHORIZED_MESSAGE


# Conversation states
NO_CUSTOMER, NO_AMOUNT, NO_NOTE = range(3)
TRANO_SELECT = 10
XOANO_SELECT = 11


def get_debt_keyboard():
    """Keyboard quản lý nợ"""
    keyboard = [
        [
            InlineKeyboardButton("📝 Ghi Nợ", callback_data="debt_add"),
            InlineKeyboardButton("📋 DS Nợ", callback_data="debt_list"),
        ],
        [
            InlineKeyboardButton("👤 Theo Khách", callback_data="debt_by_customer"),
            InlineKeyboardButton("✅ Trả Nợ", callback_data="debt_pay"),
        ],
        [
            InlineKeyboardButton("📊 Tổng Kết", callback_data="debt_summary"),
            InlineKeyboardButton("🗑 Xóa", callback_data="debt_delete"),
        ],
        [
            InlineKeyboardButton("🔙 Menu", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Keyboard hủy"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_debt")]
    ])


def get_back_keyboard():
    """Keyboard quay lại"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
    ])


# ==================== MENU NỢ ====================

async def no_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /no - Mở menu nợ"""
    if not check_permission(update.effective_user.id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    
    await update.message.reply_text(
        "💳 *QUẢN LÝ NỢ*\n\nChọn chức năng:",
        parse_mode='Markdown',
        reply_markup=get_debt_keyboard()
    )


# ==================== GHI NỢ MỚI ====================

async def ghino_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu ghi nợ - hiển thị khách hàng đã có hoặc tạo mới"""
    query = update.callback_query
    if query:
        await query.answer()
        
        # Lấy danh sách khách đang nợ
        customers = sheets.get_all_customers_with_debt()
        
        text = "📝 GHI NỢ MỚI\n\n"
        
        keyboard = []
        
        if customers:
            text += "👤 Chọn khách hàng đã có:\n\n"
            customers.sort(key=lambda x: x['total'], reverse=True)
            
            for c in customers:
                text += f"• {c['customer']}: {format_currency(c['total'])} ({c['count']} khoản)\n"
            
            # Tạo buttons cho từng khách
            row = []
            for c in customers[:8]:  # Tối đa 8 khách
                row.append(InlineKeyboardButton(
                    f"👤 {c['customer'][:12]}", 
                    callback_data=f"debt_addto_{c['customer'][:15]}"
                ))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            text += "\n━━━━━━━━━━━━━━━━━\n"
        
        text += "📝 Hoặc nhập tên khách hàng mới:"
        
        keyboard.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel_debt")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return NO_CUSTOMER
    
    return NO_CUSTOMER


async def ghino_select_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chọn khách hàng từ button"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_addto_", "")
    context.user_data['debt_customer'] = customer
    
    existing_debt = sheets.get_customer_total_debt(customer)
    
    text = f"""📝 GHI NỢ MỚI

✅ Khách hàng: {customer}
⚠️ Nợ hiện tại: {format_currency(existing_debt)}

Bước 2/3: Nhập số tiền nợ thêm:"""
    
    await query.edit_message_text(
        text,
        reply_markup=get_cancel_keyboard()
    )
    
    return NO_AMOUNT


async def ghino_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận tên khách, hỏi số tiền"""
    customer = update.message.text.strip()
    context.user_data['debt_customer'] = customer
    
    # Kiểm tra xem khách này có nợ cũ không
    existing_debt = sheets.get_customer_total_debt(customer)
    
    text = f"""📝 GHI NỢ MỚI

✅ Khách hàng: {customer}
"""
    
    if existing_debt > 0:
        text += f"⚠️ Nợ cũ: {format_currency(existing_debt)}\n"
    
    text += "\nBước 2/3: Nhập số tiền nợ:"
    
    await update.message.reply_text(
        text,
        reply_markup=get_cancel_keyboard()
    )
    
    return NO_AMOUNT


async def ghino_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận số tiền, hỏi ghi chú"""
    amount = parse_amount(update.message.text)
    
    if not amount:
        await update.message.reply_text(
            "❌ Số tiền không hợp lệ!\n\nVui lòng nhập lại (ví dụ: 500k, 1.5m):",
            reply_markup=get_cancel_keyboard()
        )
        return NO_AMOUNT
    
    context.user_data['debt_amount'] = amount
    customer = context.user_data.get('debt_customer', '')
    
    text = f"""📝 GHI NỢ MỚI

✅ Khách hàng: {customer}
✅ Số tiền: {format_currency(amount)}

Bước 3/3: Nhập ghi chú (ví dụ: Mua YTBIOS x3)
Hoặc bấm Bỏ qua:"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Bỏ qua", callback_data="debt_skip_note")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_debt")]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)
    
    return NO_NOTE


async def ghino_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận ghi chú và hoàn thành"""
    note = update.message.text.strip()
    await complete_debt(update, context, note)
    return ConversationHandler.END


async def ghino_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua ghi chú"""
    query = update.callback_query
    await query.answer()
    await complete_debt(query, context, "", is_callback=True)
    return ConversationHandler.END


async def complete_debt(update_or_query, context, note: str, is_callback: bool = False):
    """Hoàn thành ghi nợ"""
    customer = context.user_data.get('debt_customer', '')
    amount = context.user_data.get('debt_amount', 0)
    
    try:
        result = sheets.add_debt(customer, amount, note)
        
        # Lấy tổng nợ mới của khách
        total_debt = sheets.get_customer_total_debt(customer)
        
        note_text = f"📝 Ghi chú: {note}\n" if note else ""
        
        text = f"""✅ ĐÃ GHI NỢ!

👤 Khách hàng: {customer}
💰 Số tiền: {format_currency(amount)}
{note_text}
━━━━━━━━━━━━━━━━━
💳 Tổng nợ hiện tại: {format_currency(total_debt)}"""
        
        if is_callback:
            await update_or_query.edit_message_text(
                text,
                reply_markup=get_debt_keyboard()
            )
        else:
            await update_or_query.message.reply_text(
                text,
                reply_markup=get_debt_keyboard()
            )
    except Exception as e:
        error_text = f"❌ Lỗi: {str(e)}"
        if is_callback:
            await update_or_query.edit_message_text(error_text)
        else:
            await update_or_query.message.reply_text(error_text)
    
    context.user_data.clear()


# ==================== DANH SÁCH NỢ ====================

async def debt_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị danh sách tất cả nợ pending"""
    query = update.callback_query
    await query.answer()
    
    try:
        debts = sheets.get_all_debts(status='pending')
        
        if not debts:
            text = "📋 DANH SÁCH NỢ\n\n🎉 Không có ai nợ!"
        else:
            total = sum(d['amount'] for d in debts)
            text = f"📋 DANH SÁCH NỢ ({len(debts)} khoản)\n\n"
            
            for d in debts[-15:]:  # Hiển thị 15 khoản gần nhất
                note_text = f" - {d['note']}" if d['note'] else ""
                text += f"• Row {d['row']}: {d['customer']} - {format_currency(d['amount'])}{note_text}\n"
            
            if len(debts) > 15:
                text += f"\n... và {len(debts) - 15} khoản khác"
            
            text += f"\n━━━━━━━━━━━━━━━━━\n💰 Tổng nợ: {format_currency(total)}"
        
        await query.edit_message_text(
            text,
            reply_markup=get_debt_keyboard()
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


# ==================== NỢ THEO KHÁCH ====================

async def debt_by_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị nợ theo từng khách hàng"""
    query = update.callback_query
    await query.answer()
    
    try:
        customers = sheets.get_all_customers_with_debt()
        
        if not customers:
            text = "👤 NỢ THEO KHÁCH\n\n🎉 Không có ai nợ!"
            await query.edit_message_text(text, reply_markup=get_debt_keyboard())
            return
        
        total = sum(c['total'] for c in customers)
        text = f"👤 NỢ THEO KHÁCH ({len(customers)} người)\n\n"
        
        # Sort by total debt descending
        customers.sort(key=lambda x: x['total'], reverse=True)
        
        for c in customers:
            text += f"• {c['customer']}: {format_currency(c['total'])} ({c['count']} khoản)\n"
        
        text += f"\n━━━━━━━━━━━━━━━━━\n💰 Tổng nợ: {format_currency(total)}"
        
        # Tạo buttons cho từng khách
        keyboard = []
        row = []
        for c in customers[:8]:  # Tối đa 8 buttons
            row.append(InlineKeyboardButton(
                f"👤 {c['customer'][:10]}", 
                callback_data=f"debt_customer_{c['customer'][:15]}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


async def debt_customer_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem chi tiết nợ của 1 khách"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_customer_", "")
    
    try:
        debts = sheets.get_debts_by_customer(customer)
        
        if not debts:
            text = f"👤 NỢ CỦA: {customer}\n\n🎉 Đã trả hết!"
            keyboard = [
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ]
        else:
            total = sum(d['amount'] for d in debts)
            text = f"👤 NỢ CỦA: {customer}\n\n"
            
            for d in debts:
                note_text = f" ({d['note']})" if d['note'] else ""
                text += f"• {d['date']}: {format_currency(d['amount'])}{note_text}\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━\n💰 Tổng nợ: {format_currency(total)}"
            
            keyboard = [
                [InlineKeyboardButton(f"💳 Tạo Link TT ({format_currency(total)})", callback_data=f"debt_paylink_{customer[:15]}")],
                [InlineKeyboardButton(f"✅ Trả Hết Nợ ({customer})", callback_data=f"debt_payall_{customer[:15]}")],
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


# ==================== PAYOS THANH TOÁN ====================

async def debt_create_paylink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tạo QR thanh toán PayOS cho khách"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_paylink_", "")
    
    try:
        from services.payos_service import create_payment_link
        
        # Lấy tổng nợ
        total = sheets.get_customer_total_debt(customer)
        
        if total <= 0:
            await query.edit_message_text(
                f"🎉 {customer} không còn nợ!",
                reply_markup=get_debt_keyboard()
            )
            return
        
        # Thông báo đang tạo
        await query.edit_message_text("⏳ Đang tạo QR thanh toán...")
        
        # Tạo link PayOS
        result = create_payment_link(customer, total, f"Tra no - {customer}")
        
        # Lưu order_code để kiểm tra sau
        context.user_data['payos_order'] = result['order_code']
        context.user_data['payos_customer'] = customer
        
        caption = f"""💳 QR THANH TOÁN

👤 Khách: {customer}
💰 Số tiền: {format_currency(total)}
📋 Mã đơn: {result['order_code']}

💡 Gửi QR này cho khách quét để thanh toán.
Sau khi thanh toán xong, bấm Kiểm Tra bên dưới."""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Kiểm Tra Thanh Toán", callback_data=f"debt_checkpay_{result['order_code']}")],
            [InlineKeyboardButton(f"👤 Quay lại {customer}", callback_data=f"debt_customer_{customer[:15]}")],
            [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
        ]
        
        # Gửi ảnh QR code
        qr_url = result.get('qr_code', '')
        chat_id = query.message.chat_id
        
        if qr_url:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=qr_url,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Fallback: gửi link nếu không có QR
            caption += f"\n\n🔗 Link: {result['checkout_url']}"
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi tạo QR: {str(e)}", reply_markup=get_back_keyboard())


async def debt_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiểm tra trạng thái thanh toán PayOS"""
    query = update.callback_query
    await query.answer()
    
    order_code_str = query.data.replace("debt_checkpay_", "")
    
    try:
        from services.payos_service import check_payment_status
        
        order_code = int(order_code_str)
        result = check_payment_status(order_code)
        
        customer = context.user_data.get('payos_customer', '')
        
        if result['status'] == 'PAID':
            # Tự động đánh dấu tất cả nợ đã trả
            count = sheets.mark_customer_debts_paid(customer)
            
            text = f"""✅ ĐÃ THANH TOÁN THÀNH CÔNG!

👤 Khách: {customer}
💰 Số tiền: {format_currency(result['amount'])}
📋 Mã đơn: {order_code}

🎉 Đã tự động đánh dấu {count} khoản nợ đã trả!"""
            
            context.user_data.pop('payos_order', None)
            context.user_data.pop('payos_customer', None)
            
            await query.edit_message_text(text, reply_markup=get_debt_keyboard())
        
        elif result['status'] == 'CANCELLED':
            text = f"❌ Thanh toán đã bị HỦY!\n\nMã đơn: {order_code}"
            
            keyboard = [
                [InlineKeyboardButton(f"💳 Tạo Link Mới", callback_data=f"debt_paylink_{customer[:15]}")],
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        else:
            # PENDING
            text = f"""⏳ CHƯA THANH TOÁN

👤 Khách: {customer}
📋 Mã đơn: {order_code}
📊 Trạng thái: Đang chờ thanh toán

💡 Gửi link cho khách và bấm Kiểm Tra lại sau."""
            
            keyboard = [
                [InlineKeyboardButton("🔄 Kiểm Tra Lại", callback_data=f"debt_checkpay_{order_code}")],
                [InlineKeyboardButton(f"👤 Quay lại {customer}", callback_data=f"debt_customer_{customer[:15]}")],
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi kiểm tra: {str(e)}", reply_markup=get_back_keyboard())


# ==================== TRẢ NỢ ====================

async def trano_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu đánh dấu trả nợ"""
    query = update.callback_query
    await query.answer()
    
    try:
        debts = sheets.get_all_debts(status='pending')
        
        if not debts:
            await query.edit_message_text(
                "✅ TRẢ NỢ\n\n🎉 Không có ai nợ!",
                reply_markup=get_debt_keyboard()
            )
            return ConversationHandler.END
        
        text = "✅ TRẢ NỢ\n\n📋 Danh sách nợ:\n"
        for d in debts[-10:]:
            text += f"• Row {d['row']}: {d['customer']} - {format_currency(d['amount'])}\n"
        
        text += "\n📝 Nhập số row để đánh dấu đã trả:"
        
        await query.edit_message_text(text, reply_markup=get_cancel_keyboard())
        
        return TRANO_SELECT
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())
        return ConversationHandler.END


async def trano_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác nhận trả nợ theo row"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!\n\nVui lòng nhập lại:",
            reply_markup=get_cancel_keyboard()
        )
        return TRANO_SELECT
    
    try:
        success = sheets.mark_debt_paid(row_num)
        
        if success:
            text = f"✅ Đã đánh dấu row {row_num} đã trả nợ!"
        else:
            text = f"❌ Không thể cập nhật row {row_num}"
        
        await update.message.reply_text(text, reply_markup=get_debt_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())
    
    return ConversationHandler.END


async def trano_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trả hết nợ của 1 khách"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_payall_", "")
    
    try:
        count = sheets.mark_customer_debts_paid(customer)
        
        if count > 0:
            text = f"✅ Đã đánh dấu {count} khoản nợ của {customer} đã trả!"
        else:
            text = f"ℹ️ {customer} không có nợ pending"
        
        await query.edit_message_text(text, reply_markup=get_debt_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


# ==================== TỔNG KẾT ====================

async def debt_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị tổng kết nợ"""
    query = update.callback_query
    await query.answer()
    
    try:
        summary = sheets.get_debt_summary()
        customers = sheets.get_all_customers_with_debt()
        
        text = f"""📊 TỔNG KẾT NỢ

💰 Tổng nợ: {format_currency(summary['total_amount'])}
👥 Số người nợ: {summary['customer_count']}
"""
        
        if customers:
            text += "\n📋 Top nợ nhiều nhất:\n"
            customers.sort(key=lambda x: x['total'], reverse=True)
            for c in customers[:5]:
                text += f"   • {c['customer']}: {format_currency(c['total'])}\n"
        
        await query.edit_message_text(text, reply_markup=get_debt_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


# ==================== XÓA NỢ ====================

async def xoano_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa nợ"""
    query = update.callback_query
    await query.answer()
    
    try:
        debts = sheets.get_all_debts()
        
        if not debts:
            await query.edit_message_text(
                "🗑 XÓA NỢ\n\n📭 Không có khoản nợ nào.",
                reply_markup=get_debt_keyboard()
            )
            return ConversationHandler.END
        
        text = "🗑 XÓA NỢ\n\n📋 Danh sách nợ:\n"
        for d in debts[-10:]:
            status = "✅" if d['status'] == 'paid' else "⏳"
            text += f"• Row {d['row']}: {status} {d['customer']} - {format_currency(d['amount'])}\n"
        
        text += "\n⚠️ Nhập số row cần xóa:"
        
        await query.edit_message_text(text, reply_markup=get_cancel_keyboard())
        
        return XOANO_SELECT
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())
        return ConversationHandler.END


async def xoano_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác nhận xóa nợ"""
    try:
        row_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Số row không hợp lệ!",
            reply_markup=get_cancel_keyboard()
        )
        return XOANO_SELECT
    
    try:
        success = sheets.delete_debt(row_num)
        
        if success:
            text = f"✅ Đã xóa khoản nợ ở row {row_num}!"
        else:
            text = f"❌ Không thể xóa row {row_num}"
        
        await update.message.reply_text(text, reply_markup=get_debt_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())
    
    return ConversationHandler.END


# ==================== CANCEL ====================

async def cancel_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "❌ Đã hủy thao tác.",
            reply_markup=get_debt_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Đã hủy thao tác.",
            reply_markup=get_debt_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END
