"""
Product handlers với Conversation Flow
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from services import sheets
from utils.formatting import format_currency, parse_amount
from utils.security import check_permission, UNAUTHORIZED_MESSAGE

# Conversation states
THEMSP_SKU, THEMSP_NAME, THEMSP_COST = range(3)
SUASP_SKU, SUASP_COST = range(3, 5)
XOASP_SKU = 5


def get_product_keyboard():
    """Keyboard sản phẩm với đầy đủ buttons"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Xem Danh Sách", callback_data="sanpham_list"),
        ],
        [
            InlineKeyboardButton("➕ Thêm SP", callback_data="sanpham_add"),
            InlineKeyboardButton("✏️ Sửa Giá", callback_data="sanpham_edit"),
            InlineKeyboardButton("🗑 Xóa SP", callback_data="sanpham_delete"),
        ],
        [
            InlineKeyboardButton("🔙 Menu Chính", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Keyboard hủy"""
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_conversation")]]
    return InlineKeyboardMarkup(keyboard)


# ==================== COMMAND HANDLERS ====================

async def sanpham_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sanpham command"""
    try:
        products = sheets.get_all_products()
        
        if not products:
            text = "📦 *DANH SÁCH SẢN PHẨM*\n\n📭 Chưa có sản phẩm nào."
        else:
            text = "📦 *DANH SÁCH SẢN PHẨM*\n\n"
            for p in products:
                text += f"🏷 *{p['sku']}* - {p['name']}\n"
                text += f"   💵 Cost: {format_currency(p['cost'])}\n\n"
        
        await update.message.reply_text(
            text, 
            parse_mode='Markdown',
            reply_markup=get_product_keyboard()
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


# ==================== THÊM SẢN PHẨM - CONVERSATION ====================

async def themsp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu thêm sản phẩm - hỏi SKU"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "➕ *THÊM SẢN PHẨM MỚI*\n\n"
            "📝 *Bước 1/3:* Nhập mã sản phẩm (SKU)\n\n"
            "_Ví dụ: SP01, AOTHUN01_",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    else:
        await update.message.reply_text(
            "➕ *THÊM SẢN PHẨM MỚI*\n\n"
            "📝 *Bước 1/3:* Nhập mã sản phẩm (SKU)\n\n"
            "_Ví dụ: SP01, AOTHUN01_",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    
    return THEMSP_SKU


async def themsp_sku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận SKU, hỏi tên"""
    sku = update.message.text.strip().upper()
    
    # Kiểm tra SKU đã tồn tại chưa
    if sheets.find_product_by_sku(sku):
        await update.message.reply_text(
            f"❌ SKU `{sku}` đã tồn tại!\n\n"
            "Vui lòng nhập SKU khác:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return THEMSP_SKU
    
    context.user_data['new_product_sku'] = sku
    
    await update.message.reply_text(
        f"✅ SKU: *{sku}*\n\n"
        "📝 *Bước 2/3:* Nhập tên sản phẩm\n\n"
        "_Ví dụ: Áo thun nam_",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    
    return THEMSP_NAME


async def themsp_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận tên, hỏi giá"""
    name = update.message.text.strip()
    context.user_data['new_product_name'] = name
    
    sku = context.user_data.get('new_product_sku', '')
    
    await update.message.reply_text(
        f"✅ SKU: *{sku}*\n"
        f"✅ Tên: *{name}*\n\n"
        "📝 *Bước 3/3:* Nhập giá gốc\n\n"
        "_Ví dụ: 150k, 150000, 1.5m_",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    
    return THEMSP_COST


async def themsp_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận giá gốc và tạo sản phẩm"""
    cost = parse_amount(update.message.text.strip())
    
    if cost is None:
        await update.message.reply_text(
            "❌ Giá không hợp lệ!\n\n"
            "Vui lòng nhập lại (ví dụ: 150k, 150000):",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return THEMSP_COST
    
    sku = context.user_data.get('new_product_sku', '')
    name = context.user_data.get('new_product_name', '')
    
    try:
        success = sheets.add_product(sku, name, cost)
        
        if success:
            await update.message.reply_text(
                "✅ *ĐÃ THÊM SẢN PHẨM!*\n\n"
                f"🏷 *SKU:* {sku}\n"
                f"📦 *Tên:* {name}\n"
                f"💵 *Giá gốc:* {format_currency(cost)}\n\n"
                f"💡 Dùng `/ban {sku} [giá bán]` để ghi bán hàng.",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Có lỗi xảy ra. Vui lòng thử lại.",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Lỗi: `{str(e)}`",
            parse_mode='Markdown',
            reply_markup=get_product_keyboard()
        )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END


# ==================== SỬA GIÁ - CONVERSATION ====================

async def suasp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu sửa giá - hỏi SKU"""
    query = update.callback_query
    if query:
        await query.answer()
        
        # Hiển thị danh sách sản phẩm trước
        try:
            products = sheets.get_all_products()
            if products:
                text = "✏️ *SỬA GIÁ SẢN PHẨM*\n\n"
                text += "📦 *Danh sách hiện tại:*\n"
                for p in products:
                    text += f"• `{p['sku']}` - {p['name']} ({format_currency(p['cost'])})\n"
                text += "\n📝 Nhập SKU sản phẩm cần sửa:"
            else:
                text = "✏️ *SỬA GIÁ SẢN PHẨM*\n\n📭 Chưa có sản phẩm nào."
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_product_keyboard())
                return ConversationHandler.END
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_cancel_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return SUASP_SKU


async def suasp_sku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận SKU, hỏi giá mới"""
    sku = update.message.text.strip().upper()
    
    product = sheets.find_product_by_sku(sku)
    if not product:
        await update.message.reply_text(
            f"❌ Không tìm thấy `{sku}`!\n\n"
            "Vui lòng nhập SKU khác:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return SUASP_SKU
    
    context.user_data['edit_sku'] = sku
    context.user_data['edit_product'] = product
    
    await update.message.reply_text(
        f"📦 *{product['name']}* (`{sku}`)\n"
        f"💵 Giá hiện tại: {format_currency(product['cost'])}\n\n"
        "📝 Nhập giá gốc mới:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    
    return SUASP_COST


async def suasp_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận giá mới và cập nhật"""
    cost = parse_amount(update.message.text.strip())
    
    if cost is None:
        await update.message.reply_text(
            "❌ Giá không hợp lệ!\n\nVui lòng nhập lại:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return SUASP_COST
    
    sku = context.user_data.get('edit_sku', '')
    product = context.user_data.get('edit_product', {})
    
    try:
        success = sheets.update_product(sku, cost=cost)
        
        if success:
            await update.message.reply_text(
                "✅ *ĐÃ CẬP NHẬT!*\n\n"
                f"🏷 *{sku}* - {product.get('name', '')}\n"
                f"💵 Giá cũ: {format_currency(product.get('cost', 0))}\n"
                f"💵 *Giá mới: {format_currency(cost)}*",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Có lỗi xảy ra.",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== XÓA SẢN PHẨM - CONVERSATION ====================

async def xoasp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu xóa - hỏi SKU"""
    query = update.callback_query
    if query:
        await query.answer()
        
        try:
            products = sheets.get_all_products()
            if products:
                text = "🗑 *XÓA SẢN PHẨM*\n\n"
                text += "📦 *Danh sách hiện tại:*\n"
                for p in products:
                    text += f"• `{p['sku']}` - {p['name']}\n"
                text += "\n⚠️ Nhập SKU sản phẩm cần xóa:"
            else:
                text = "🗑 *XÓA SẢN PHẨM*\n\n📭 Chưa có sản phẩm nào."
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_product_keyboard())
                return ConversationHandler.END
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_cancel_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END
    
    return XOASP_SKU


async def xoasp_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận SKU và xóa"""
    sku = update.message.text.strip().upper()
    
    product = sheets.find_product_by_sku(sku)
    if not product:
        await update.message.reply_text(
            f"❌ Không tìm thấy `{sku}`!\n\nVui lòng nhập SKU khác:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return XOASP_SKU
    
    try:
        success = sheets.delete_product(sku)
        
        if success:
            await update.message.reply_text(
                "✅ *ĐÃ XÓA SẢN PHẨM!*\n\n"
                f"🗑 {sku} - {product['name']}",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Có lỗi xảy ra.",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
    
    return ConversationHandler.END


# ==================== CANCEL ====================

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "❌ *Đã hủy!*\n\n📌 Chọn chức năng:",
            parse_mode='Markdown',
            reply_markup=get_product_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ *Đã hủy!*",
            parse_mode='Markdown',
            reply_markup=get_product_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END


# ==================== COMMAND HANDLERS (giữ lại để tương thích) ====================

async def themsp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /themsp command"""
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "📝 Cách dùng: `/themsp [SKU] [Tên] [Giá gốc]`\n"
            "Ví dụ: `/themsp SP01 Áo thun 150k`\n\n"
            "💡 Hoặc bấm nút ➕ Thêm SP để được hướng dẫn từng bước.",
            parse_mode='Markdown',
            reply_markup=get_product_keyboard()
        )
        return
    
    sku = context.args[0].upper()
    cost = parse_amount(context.args[-1])
    if cost is None:
        await update.message.reply_text("❌ Giá gốc không hợp lệ.", parse_mode='Markdown')
        return
    
    name = ' '.join(context.args[1:-1]).strip('"').strip("'")
    if not name:
        await update.message.reply_text("❌ Vui lòng nhập tên sản phẩm.", parse_mode='Markdown')
        return
    
    try:
        success = sheets.add_product(sku, name, cost)
        if success:
            await update.message.reply_text(
                f"✅ *Đã thêm!*\n\n🏷 {sku} - {name}\n💵 {format_currency(cost)}",
                parse_mode='Markdown',
                reply_markup=get_product_keyboard()
            )
        else:
            await update.message.reply_text(f"❌ SKU `{sku}` đã tồn tại.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def suasp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /suasp command"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 Cách dùng: `/suasp [SKU] [Giá mới]`\n"
            "Ví dụ: `/suasp SP01 200k`",
            parse_mode='Markdown'
        )
        return
    
    sku = context.args[0].upper()
    cost = parse_amount(context.args[1])
    
    if cost is None:
        await update.message.reply_text("❌ Giá không hợp lệ.", parse_mode='Markdown')
        return
    
    try:
        product = sheets.find_product_by_sku(sku)
        if not product:
            await update.message.reply_text(f"❌ Không tìm thấy `{sku}`.", parse_mode='Markdown')
            return
        
        success = sheets.update_product(sku, cost=cost)
        if success:
            await update.message.reply_text(
                f"✅ *Đã cập nhật {sku}*\n💵 {format_currency(product['cost'])} → {format_currency(cost)}",
                parse_mode='Markdown'
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')


async def xoasp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /xoasp command"""
    if not context.args:
        await update.message.reply_text(
            "📝 Cách dùng: `/xoasp [SKU]`\n"
            "Ví dụ: `/xoasp SP01`",
            parse_mode='Markdown'
        )
        return
    
    sku = context.args[0].upper()
    
    try:
        product = sheets.find_product_by_sku(sku)
        if not product:
            await update.message.reply_text(f"❌ Không tìm thấy `{sku}`.", parse_mode='Markdown')
            return
        
        success = sheets.delete_product(sku)
        if success:
            await update.message.reply_text(f"✅ Đã xóa `{sku}`.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: `{str(e)}`", parse_mode='Markdown')
