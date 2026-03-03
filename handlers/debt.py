"""
Debt Management Handlers - Quản lý nợ khách hàng
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount
from utils.security import check_permission, UNAUTHORIZED_MESSAGE


# Conversation states
NO_CUSTOMER, NO_AMOUNT, NO_NOTE, NO_TELEGRAM_ID = range(4)
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
    """Nhận ghi chú, hỏi Telegram ID"""
    note = update.message.text.strip()
    context.user_data['debt_note'] = note
    
    customer = context.user_data.get('debt_customer', '')
    amount = context.user_data.get('debt_amount', 0)
    
    # Kiểm tra khách đã có Telegram ID chưa
    existing_tid = sheets.get_customer_telegram_id(customer)
    if existing_tid:
        # Đã có → bỏ qua, hoàn thành luôn
        context.user_data['debt_telegram_id'] = existing_tid
        await complete_debt(update, context, note)
        return ConversationHandler.END
    
    text = f"""📝 GHI NỢ MỚI

✅ Khách hàng: {customer}
✅ Số tiền: {format_currency(amount)}
✅ Ghi chú: {note}

Bước 4/4: Nhập Telegram ID của khách (để đòi nợ tự động)
Hoặc bấm Bỏ qua:"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Bỏ qua", callback_data="debt_skip_tid")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_debt")]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)
    return NO_TELEGRAM_ID


async def ghino_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua ghi chú, hỏi Telegram ID"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['debt_note'] = ''
    customer = context.user_data.get('debt_customer', '')
    amount = context.user_data.get('debt_amount', 0)
    
    # Kiểm tra khách đã có Telegram ID chưa
    existing_tid = sheets.get_customer_telegram_id(customer)
    if existing_tid:
        context.user_data['debt_telegram_id'] = existing_tid
        await complete_debt(query, context, '', is_callback=True)
        return ConversationHandler.END
    
    text = f"""📝 GHI NỢ MỚI

✅ Khách hàng: {customer}
✅ Số tiền: {format_currency(amount)}

Bước 4/4: Nhập Telegram ID của khách (để đòi nợ tự động)
Hoặc bấm Bỏ qua:"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Bỏ qua", callback_data="debt_skip_tid")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_debt")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)
    return NO_TELEGRAM_ID


async def ghino_telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận Telegram ID và hoàn thành"""
    tid = update.message.text.strip()
    context.user_data['debt_telegram_id'] = tid
    note = context.user_data.get('debt_note', '')
    await complete_debt(update, context, note)
    return ConversationHandler.END


async def ghino_skip_tid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bỏ qua Telegram ID"""
    query = update.callback_query
    await query.answer()
    context.user_data['debt_telegram_id'] = ''
    note = context.user_data.get('debt_note', '')
    await complete_debt(query, context, note, is_callback=True)
    return ConversationHandler.END


async def complete_debt(update_or_query, context, note: str, is_callback: bool = False):
    """Hoàn thành ghi nợ"""
    customer = context.user_data.get('debt_customer', '')
    amount = context.user_data.get('debt_amount', 0)
    telegram_id = context.user_data.get('debt_telegram_id', '')
    
    try:
        result = sheets.add_debt(customer, amount, note, telegram_id=telegram_id)
        
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
            telegram_id = sheets.get_customer_telegram_id(customer)
            
            text = f"👤 NỢ CỦA: {customer}\n"
            if telegram_id:
                text += f"📱 Telegram ID: {telegram_id}\n"
            text += "\n"
            
            for d in debts:
                note_text = f" ({d['note']})" if d['note'] else ""
                text += f"• {d['date']}: {format_currency(d['amount'])}{note_text}\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━\n💰 Tổng nợ: {format_currency(total)}"
            
            keyboard = [
                [InlineKeyboardButton(f"💳 Tạo Link TT ({format_currency(total)})", callback_data=f"debt_paylink_{customer[:15]}")],
            ]
            # Thêm nút "Đòi nợ" nếu có Telegram ID
            if telegram_id:
                keyboard.append([InlineKeyboardButton(f"📨 Đòi Nợ ({customer})", callback_data=f"debt_doino_{customer[:15]}")])
            else:
                keyboard.append([InlineKeyboardButton(f"📱 Thêm Telegram ID", callback_data=f"debt_settid_{customer[:15]}")])
            keyboard.append([InlineKeyboardButton(f"✅ Trả Hết Nợ ({customer})", callback_data=f"debt_payall_{customer[:15]}")])
            keyboard.append([InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")])
        
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
        
        caption = f"🧾 ĐƠN HÀNG: {result['order_code']}\n"
        caption += f"👤 {customer}\n"
        caption += f"💰 {format_currency(total)}"
        
        keyboard = [
            [InlineKeyboardButton("🏦 APP NGÂN HÀNG", url=result['checkout_url'])],
            [InlineKeyboardButton("🔄 Kiểm Tra Thanh Toán", callback_data=f"debt_checkpay_{result['order_code']}")],
            [InlineKeyboardButton("❌ Hủy đơn", callback_data=f"debt_cancelqr_{customer[:15]}")],
        ]
        
        # Gửi ảnh QR code
        qr_url = result.get('qr_code', '')
        checkout_url = result.get('checkout_url', '')
        chat_id = query.message.chat_id
        
        qr_msg = None
        sent = False
        
        if qr_url:
            # Cách 1: Gửi URL trực tiếp cho Telegram tải
            try:
                qr_msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent = True
            except Exception:
                pass
            
            # Cách 2: Tự tải về bytes rồi gửi
            if not sent:
                try:
                    import urllib.request
                    import io
                    
                    req = urllib.request.Request(qr_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        qr_bytes = io.BytesIO(resp.read())
                        qr_bytes.name = 'qr_payment.png'
                    
                    qr_msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=qr_bytes,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    sent = True
                except Exception:
                    pass
        
        if not sent:
            # Cách 3: Gửi link text
            caption += f"\n\n🔗 Link: {checkout_url}"
            qr_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        # Lưu QR message ID để xóa sau khi thanh toán/hủy
        if qr_msg:
            context.user_data['qr_message_id'] = qr_msg.message_id
            context.user_data['qr_chat_id'] = chat_id
        
        # Xóa message "⏳ Đang tạo QR..." cho gọn
        try:
            await query.message.delete()
        except Exception:
            pass
    
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi tạo QR: {str(e)}", reply_markup=get_back_keyboard())


async def debt_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiểm tra trạng thái thanh toán PayOS"""
    query = update.callback_query
    
    order_code_str = query.data.replace("debt_checkpay_", "")
    
    try:
        from services.payos_service import check_payment_status
        
        order_code = int(order_code_str)
        result = check_payment_status(order_code)
        
        customer = context.user_data.get('payos_customer', '')
        chat_id = query.message.chat_id
        
        if result['status'] == 'PAID':
            # ✅ Thanh toán thành công → xóa QR + cập nhật sheet
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Tự động đánh dấu tất cả nợ đã trả trong sheet
            count = sheets.mark_customer_debts_paid(customer)
            
            text = f"""✅ ĐÃ THANH TOÁN THÀNH CÔNG!

👤 Khách: {customer}
💰 Số tiền: {format_currency(result['amount'])}
📋 Mã đơn: {order_code}

🎉 Đã tự động đánh dấu {count} khoản nợ đã trả!"""
            
            # Dọn dẹp user_data
            context.user_data.pop('payos_order', None)
            context.user_data.pop('payos_customer', None)
            context.user_data.pop('qr_message_id', None)
            context.user_data.pop('qr_chat_id', None)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=get_debt_keyboard()
            )
        
        elif result['status'] == 'CANCELLED':
            # ❌ Đã hủy → xóa QR
            try:
                await query.message.delete()
            except Exception:
                pass
            
            text = f"❌ Thanh toán đã bị HỦY!\n\nMã đơn: {order_code}"
            
            keyboard = [
                [InlineKeyboardButton("💳 Tạo Link Mới", callback_data=f"debt_paylink_{customer[:15]}")],
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ]
            
            # Dọn dẹp user_data
            context.user_data.pop('payos_order', None)
            context.user_data.pop('payos_customer', None)
            context.user_data.pop('qr_message_id', None)
            context.user_data.pop('qr_chat_id', None)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        else:
            # ⏳ PENDING → hiện popup, giữ QR để khách quét
            await query.answer(
                "⏳ Chưa thanh toán.\nGửi link cho khách và bấm Kiểm Tra lại sau.",
                show_alert=True
            )
    
    except Exception as e:
        await query.answer(f"❌ Lỗi: {str(e)}", show_alert=True)


async def debt_cancel_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy đơn QR thanh toán - xóa message QR"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_cancelqr_", "")
    chat_id = query.message.chat_id
    
    # Xóa message QR
    try:
        await query.message.delete()
    except Exception:
        pass
    
    # Dọn dẹp user_data
    context.user_data.pop('payos_order', None)
    context.user_data.pop('payos_customer', None)
    context.user_data.pop('qr_message_id', None)
    context.user_data.pop('qr_chat_id', None)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❌ Đã hủy đơn thanh toán của {customer}.",
        reply_markup=get_debt_keyboard()
    )


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


async def debt_conv_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all: tự động kết thúc conversation cũ khi user bấm nút khác"""
    return ConversationHandler.END


# ==================== ĐÒI NỢ ====================

SET_TID = 20  # State cho conversation set Telegram ID

async def debt_doino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gửi tin nhắn đòi nợ đến Telegram của khách"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_doino_", "")
    
    try:
        # Lấy thông tin nợ
        debts = sheets.get_debts_by_customer(customer)
        telegram_id = sheets.get_customer_telegram_id(customer)
        
        if not debts:
            await query.edit_message_text(
                f"🎉 {customer} không còn nợ!",
                reply_markup=get_debt_keyboard()
            )
            return
        
        if not telegram_id:
            await query.edit_message_text(
                f"❌ Chưa có Telegram ID của {customer}.\n"
                f"Vui lòng thêm Telegram ID trước khi đòi nợ.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📱 Thêm Telegram ID", callback_data=f"debt_settid_{customer[:15]}")],
                    [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
                ])
            )
            return
        
        total = sum(d['amount'] for d in debts)
        
        # Tạo nội dung tin nhắn cho khách
        msg = f"📩 THÔNG BÁO CÔNG NỢ\n\n"
        msg += f"👤 Xin chào {customer},\n\n"
        msg += f"Bạn hiện có {len(debts)} khoản nợ chưa thanh toán:\n\n"
        
        for d in debts:
            note_text = f" - {d['note']}" if d['note'] else ""
            msg += f"• {d['date']}: {format_currency(d['amount'])}{note_text}\n"
        
        msg += f"\n━━━━━━━━━━━━━━━━━\n"
        msg += f"💰 Tổng nợ: {format_currency(total)}\n\n"
        msg += f"Vui lòng thanh toán bằng cách bấm nút bên dưới 👇"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Thanh Toán {format_currency(total)}", callback_data=f"custpay_{customer[:15]}")],
        ])
        
        # Gửi tin nhắn đến khách
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=msg,
                reply_markup=keyboard
            )
            
            # Thông báo cho admin
            await query.edit_message_text(
                f"✅ Đã gửi thông báo đòi nợ đến {customer}!\n"
                f"📱 Telegram ID: {telegram_id}\n"
                f"💰 Tổng nợ: {format_currency(total)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"👤 Xem {customer}", callback_data=f"debt_customer_{customer[:15]}")],
                    [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
                ])
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Không gửi được tin nhắn đến {customer}!\n\n"
                f"Lỗi: {str(e)}\n\n"
                f"💡 Khách cần /start bot này trước thì bot mới nhắn tin được.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
                ])
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())


# ==================== SET TELEGRAM ID ====================

async def debt_set_tid_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu cập nhật Telegram ID cho khách"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("debt_settid_", "")
    context.user_data['settid_customer'] = customer
    
    existing_tid = sheets.get_customer_telegram_id(customer)
    
    text = f"📱 CẬP NHẬT TELEGRAM ID\n\n"
    text += f"👤 Khách: {customer}\n"
    if existing_tid:
        text += f"📱 ID hiện tại: {existing_tid}\n"
    text += f"\n📝 Nhập Telegram ID mới của khách:\n"
    text += f"(Khách lấy ID bằng cách chat với @userinfobot)"
    
    await query.edit_message_text(
        text,
        reply_markup=get_cancel_keyboard()
    )
    
    return SET_TID


async def debt_set_tid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận và lưu Telegram ID"""
    tid = update.message.text.strip()
    customer = context.user_data.get('settid_customer', '')
    
    if not tid.isdigit():
        await update.message.reply_text(
            "❌ Telegram ID phải là số!\n\nVui lòng nhập lại:",
            reply_markup=get_cancel_keyboard()
        )
        return SET_TID
    
    try:
        count = sheets.set_customer_telegram_id(customer, tid)
        
        text = f"✅ Đã cập nhật Telegram ID cho {customer}!\n"
        text += f"📱 ID: {tid}\n"
        text += f"📋 Đã cập nhật {count} khoản nợ."
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"👤 Xem {customer}", callback_data=f"debt_customer_{customer[:15]}")],
                [InlineKeyboardButton("🔙 Quản Lý Nợ", callback_data="menu_no")]
            ])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}", reply_markup=get_back_keyboard())
    
    context.user_data.pop('settid_customer', None)
    return ConversationHandler.END


# ==================== KHÁCH TỰ THANH TOÁN ====================
# Các handler này KHÔNG kiểm tra quyền admin
# để khách nợ có thể tự thanh toán qua QR

async def cust_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Khách bấm nút Thanh Toán → tạo QR PayOS"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("custpay_", "")
    chat_id = query.message.chat_id
    
    try:
        from services.payos_service import create_payment_link
        
        total = sheets.get_customer_total_debt(customer)
        
        if total <= 0:
            await query.edit_message_text(
                f"🎉 {customer} không còn nợ!\nCảm ơn bạn đã thanh toán.",
            )
            return
        
        await query.edit_message_text("⏳ Đang tạo mã thanh toán...")
        
        result = create_payment_link(customer, total, f"Tra no - {customer}")
        
        # Lưu thông tin để kiểm tra sau
        context.user_data['cust_order'] = result['order_code']
        context.user_data['cust_customer'] = customer
        
        caption = f"🧾 THANH TOÁN CÔNG NỢ\n\n"
        caption += f"👤 {customer}\n"
        caption += f"💰 {format_currency(total)}\n\n"
        caption += f"📱 Quét mã QR hoặc bấm nút bên dưới để thanh toán"
        
        keyboard = [
            [InlineKeyboardButton("🏦 MỞ APP NGÂN HÀNG", url=result['checkout_url'])],
            [InlineKeyboardButton("🔄 Kiểm Tra Thanh Toán", callback_data=f"custcheck_{result['order_code']}")],
            [InlineKeyboardButton("❌ Hủy", callback_data=f"custcancel_{customer[:15]}")],
        ]
        
        qr_url = result.get('qr_code', '')
        checkout_url = result.get('checkout_url', '')
        
        qr_msg = None
        sent = False
        
        if qr_url:
            try:
                qr_msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent = True
            except Exception:
                pass
            
            if not sent:
                try:
                    import urllib.request
                    import io
                    
                    req = urllib.request.Request(qr_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        qr_bytes = io.BytesIO(resp.read())
                        qr_bytes.name = 'qr_payment.png'
                    
                    qr_msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=qr_bytes,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    sent = True
                except Exception:
                    pass
        
        if not sent:
            caption += f"\n\n🔗 Link: {checkout_url}"
            qr_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        # Xóa message "Đang tạo..."
        try:
            await query.message.delete()
        except Exception:
            pass
    
    except Exception as e:
        await query.edit_message_text(
            f"❌ Lỗi tạo thanh toán: {str(e)}\n\nVui lòng liên hệ chủ shop.",
        )


async def cust_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Khách kiểm tra trạng thái thanh toán"""
    query = update.callback_query
    
    order_code_str = query.data.replace("custcheck_", "")
    
    try:
        from services.payos_service import check_payment_status
        
        order_code = int(order_code_str)
        result = check_payment_status(order_code)
        
        customer = context.user_data.get('cust_customer', '')
        chat_id = query.message.chat_id
        
        if result['status'] == 'PAID':
            # Xóa QR
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Cập nhật sheet
            count = sheets.mark_customer_debts_paid(customer)
            
            text = f"✅ THANH TOÁN THÀNH CÔNG!\n\n"
            text += f"👤 {customer}\n"
            text += f"💰 {format_currency(result['amount'])}\n\n"
            text += f"🎉 Đã thanh toán {count} khoản nợ.\n"
            text += f"Cảm ơn bạn! 🙏"
            
            await context.bot.send_message(chat_id=chat_id, text=text)
            
            # Dọn dẹp
            context.user_data.pop('cust_order', None)
            context.user_data.pop('cust_customer', None)
        
        elif result['status'] == 'CANCELLED':
            try:
                await query.message.delete()
            except Exception:
                pass
            
            text = f"❌ Thanh toán đã bị hủy.\n\nBấm nút bên dưới để thử lại."
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"💳 Thanh Toán Lại", callback_data=f"custpay_{customer[:15]}")]
                ])
            )
            
            context.user_data.pop('cust_order', None)
            context.user_data.pop('cust_customer', None)
        
        else:
            # PENDING → popup, giữ QR
            await query.answer(
                "⏳ Chưa nhận được thanh toán.\nVui lòng thanh toán và kiểm tra lại.",
                show_alert=True
            )
    
    except Exception as e:
        await query.answer(f"❌ Lỗi: {str(e)}", show_alert=True)


async def cust_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Khách hủy thanh toán"""
    query = update.callback_query
    await query.answer()
    
    customer = query.data.replace("custcancel_", "")
    chat_id = query.message.chat_id
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❌ Đã hủy thanh toán.\n\nNếu muốn thanh toán sau, vui lòng liên hệ chủ shop.",
    )
    
    context.user_data.pop('cust_order', None)
    context.user_data.pop('cust_customer', None)

