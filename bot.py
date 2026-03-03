"""
CashFlow Bot - Telegram Bot quản lý thu chi
Main entry point
"""

import os
import logging
import threading
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ConversationHandler,
    filters
)

import config

# Import handlers
from handlers.basic import start_command, help_command, button_callback

# Product handlers
from handlers.product import (
    sanpham_command, themsp_command, suasp_command, xoasp_command,
    themsp_start, themsp_sku, themsp_name, themsp_cost,
    suasp_start, suasp_sku, suasp_cost,
    xoasp_start, xoasp_confirm,
    cancel_conversation,
    THEMSP_SKU, THEMSP_NAME, THEMSP_COST,
    SUASP_SKU, SUASP_COST,
    XOASP_SKU
)

# Sales handlers
from handlers.sales import (
    ban_command, dsbh_command, laithang_command, xoabh_command,
    ban_start, ban_select_sp, ban_price, ban_qty, ban_qty_skip, 
    ban_customer, ban_customer_skip, ban_note, ban_note_skip,
    xoabh_start, xoabh_confirm,
    chitiet_start, chitiet_show,
    suabh_start, suabh_select_field, suabh_get_field, suabh_save,
    cancel_sales,
    BAN_SELECT_SP, BAN_PRICE, BAN_QTY, BAN_CUSTOMER, BAN_NOTE,
    XOABH_ROW, CHITIET_ROW, SUABH_ROW, SUABH_FIELD, SUABH_VALUE
)

# Expense handlers
from handlers.expense import (
    chi_command, chitieu_command, homnay_command, thang_command, xoachi_command,
    chi_start, chi_select_category, chi_amount, chi_desc,
    xoachi_start, xoachi_confirm,
    cancel_expense,
    CHI_AMOUNT, CHI_DESC,
    XOACHI_ROW
)

# Debt handlers
from handlers.debt import (
    no_command, 
    ghino_start, ghino_customer, ghino_amount, ghino_note, ghino_skip_note,
    ghino_select_customer,
    debt_list, debt_by_customer, debt_customer_detail, debt_summary,
    debt_create_paylink, debt_check_payment, debt_cancel_qr,
    trano_start, trano_confirm, trano_all,
    xoano_start, xoano_confirm,
    cancel_debt,
    NO_CUSTOMER, NO_AMOUNT, NO_NOTE, TRANO_SELECT, XOANO_SELECT
)

# Cấu hình logging - Chỉ hiển thị log quan trọng
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Tắt log rối từ các thư viện khác
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def self_ping():
    """Tự ping chính mình mỗi 5 phút để giữ Render không spin down"""
    import time
    import urllib.request
    
    time.sleep(30)  # Đợi server khởi động
    render_url = os.getenv('RENDER_EXTERNAL_URL', '')
    
    if not render_url:
        return
    
    ping_url = f"{render_url}/{config.BOT_TOKEN}"
    
    while True:
        try:
            req = urllib.request.Request(ping_url, method='HEAD')
            urllib.request.urlopen(req, timeout=30)
            logger.info("✅ Self-ping OK")
        except Exception:
            pass  # Bỏ qua lỗi, chỉ cần request đến Render
        
        time.sleep(300)  # 5 phút


# ==================== BẢO MẬT ====================
# Thông báo khi không có quyền - Tùy chỉnh tại đây (dòng 79)
UNAUTHORIZED_MESSAGE = "🚫 Bạn không có quyền sử dụng bot này."


async def check_user_permission(update: Update, context) -> bool:
    """
    Kiểm tra quyền truy cập của user.
    Trả về True nếu được phép, False nếu không.
    """
    # Nếu không cấu hình ALLOWED_USER_ID thì cho phép tất cả
    if not config.ALLOWED_USER_ID:
        return True
    
    user_id = update.effective_user.id if update.effective_user else None
    
    if user_id != config.ALLOWED_USER_ID:
        # Gửi thông báo từ chối
        if update.message:
            await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        elif update.callback_query:
            await update.callback_query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        return False
    
    return True


async def error_handler(update: Update, context):
    """Xử lý lỗi"""
    error_msg = str(context.error)
    
    # Bỏ qua lỗi Conflict (có bot khác đang chạy)
    if "Conflict" in error_msg and "terminated by other" in error_msg:
        logger.warning("⚠️ Conflict detected - another bot instance may be running")
        return
    
    # Bỏ qua lỗi network tạm thời
    if "NetworkError" in error_msg or "TimedOut" in error_msg:
        logger.warning(f"⚠️ Network issue: {error_msg}")
        return
    
    logger.error(f"Exception while handling an update: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Có lỗi xảy ra. Vui lòng thử lại sau.",
                parse_mode='Markdown'
            )
        except Exception:
            pass  # Bỏ qua nếu không gửi được


async def unknown_command(update: Update, context):
    """Xử lý lệnh không xác định"""
    if not await check_user_permission(update, context):
        return
    
    await update.message.reply_text(
        "❓ Lệnh không được nhận dạng.\n\n"
        "💡 Dùng `/start` để mở menu hoặc `/help` để xem hướng dẫn.",
        parse_mode='Markdown'
    )


def main():
    """Khởi chạy bot"""
    # Kiểm tra config
    if not config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN không được tìm thấy trong file .env")
        return
    
    if not config.SHEET_ID:
        logger.error("❌ SHEET_ID không được tìm thấy trong file .env")
        return
    
    # Tạo application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # ==================== PRODUCT CONVERSATIONS ====================
    
    # Thêm sản phẩm
    themsp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(themsp_start, pattern="^sanpham_add$")],
        states={
            THEMSP_SKU: [MessageHandler(filters.TEXT & ~filters.COMMAND, themsp_sku)],
            THEMSP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, themsp_name)],
            THEMSP_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, themsp_cost)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern="^cancel_conversation$"),
            CommandHandler("cancel", cancel_conversation),
        ],
        per_message=False,
    )
    
    # Sửa giá sản phẩm
    suasp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(suasp_start, pattern="^sanpham_edit$")],
        states={
            SUASP_SKU: [MessageHandler(filters.TEXT & ~filters.COMMAND, suasp_sku)],
            SUASP_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, suasp_cost)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern="^cancel_conversation$"),
            CommandHandler("cancel", cancel_conversation),
        ],
        per_message=False,
    )
    
    # Xóa sản phẩm
    xoasp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(xoasp_start, pattern="^sanpham_delete$")],
        states={
            XOASP_SKU: [MessageHandler(filters.TEXT & ~filters.COMMAND, xoasp_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern="^cancel_conversation$"),
            CommandHandler("cancel", cancel_conversation),
        ],
        per_message=False,
    )
    
    # ==================== SALES CONVERSATIONS ====================
    
    # Ghi bán hàng
    ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ban_start, pattern="^sales_add$")],
        states={
            BAN_SELECT_SP: [CallbackQueryHandler(ban_select_sp, pattern="^sp_")],
            BAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_price)],
            BAN_QTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ban_qty),
                CallbackQueryHandler(ban_qty_skip, pattern="^skip_step$"),
            ],
            BAN_CUSTOMER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ban_customer),
                CallbackQueryHandler(ban_customer_skip, pattern="^skip_step$"),
            ],
            BAN_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ban_note),
                CallbackQueryHandler(ban_note_skip, pattern="^skip_step$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_sales, pattern="^cancel_sales$"),
            CommandHandler("cancel", cancel_sales),
        ],
        per_message=False,
    )
    
    # Xóa bán hàng
    xoabh_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(xoabh_start, pattern="^sales_delete$")],
        states={
            XOABH_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, xoabh_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_sales, pattern="^cancel_sales$"),
            CommandHandler("cancel", cancel_sales),
        ],
        per_message=False,
    )
    
    # Xem chi tiết đơn hàng
    chitiet_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(chitiet_start, pattern="^sales_detail$")],
        states={
            CHITIET_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, chitiet_show)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_sales, pattern="^cancel_sales$"),
            CommandHandler("cancel", cancel_sales),
        ],
        per_message=False,
    )
    
    # Sửa đơn hàng
    suabh_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(suabh_start, pattern="^sales_edit$")],
        states={
            SUABH_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, suabh_select_field)],
            SUABH_FIELD: [CallbackQueryHandler(suabh_get_field, pattern="^edit_")],
            SUABH_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, suabh_save)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_sales, pattern="^cancel_sales$"),
            CommandHandler("cancel", cancel_sales),
        ],
        per_message=False,
    )
    
    # ==================== EXPENSE CONVERSATIONS ====================
    
    # Ghi chi tiêu
    chi_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(chi_start, pattern="^expense_add$")],
        states={
            CHI_AMOUNT: [
                CallbackQueryHandler(chi_select_category, pattern="^cat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chi_amount),
            ],
            CHI_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, chi_desc)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_expense, pattern="^cancel_expense$"),
            CommandHandler("cancel", cancel_expense),
        ],
        per_message=False,
    )
    
    # Xóa chi tiêu
    xoachi_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(xoachi_start, pattern="^expense_delete$")],
        states={
            XOACHI_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, xoachi_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_expense, pattern="^cancel_expense$"),
            CommandHandler("cancel", cancel_expense),
        ],
        per_message=False,
    )
    
    # ==================== DEBT CONVERSATIONS ====================
    
    # Ghi nợ mới
    ghino_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ghino_start, pattern="^debt_add$")],
        states={
            NO_CUSTOMER: [
                CallbackQueryHandler(ghino_select_customer, pattern="^debt_addto_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_customer),
            ],
            NO_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_amount)],
            NO_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_note),
                CallbackQueryHandler(ghino_skip_note, pattern="^debt_skip_note$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_debt, pattern="^cancel_debt$"),
            CommandHandler("cancel", cancel_debt),
        ],
        per_message=False,
    )
    
    # Trả nợ
    trano_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(trano_start, pattern="^debt_pay$")],
        states={
            TRANO_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, trano_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_debt, pattern="^cancel_debt$"),
            CommandHandler("cancel", cancel_debt),
        ],
        per_message=False,
    )
    
    # Xóa nợ
    xoano_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(xoano_start, pattern="^debt_delete$")],
        states={
            XOANO_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, xoano_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_debt, pattern="^cancel_debt$"),
            CommandHandler("cancel", cancel_debt),
        ],
        per_message=False,
    )
    
    # ==================== ĐĂNG KÝ HANDLERS ====================
    
    # Conversation handlers (phải đăng ký trước)
    application.add_handler(themsp_conv)
    application.add_handler(suasp_conv)
    application.add_handler(xoasp_conv)
    application.add_handler(ban_conv)
    application.add_handler(xoabh_conv)
    application.add_handler(chitiet_conv)
    application.add_handler(suabh_conv)
    application.add_handler(chi_conv)
    application.add_handler(xoachi_conv)
    application.add_handler(ghino_conv)
    application.add_handler(trano_conv)
    application.add_handler(xoano_conv)
    
    # Basic commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", start_command))
    
    # Debt callback handlers (đăng ký TRƯỚC button_callback để pattern matching hoạt động)
    application.add_handler(CallbackQueryHandler(debt_list, pattern="^debt_list$"))
    application.add_handler(CallbackQueryHandler(debt_by_customer, pattern="^debt_by_customer$"))
    application.add_handler(CallbackQueryHandler(debt_customer_detail, pattern="^debt_customer_"))
    application.add_handler(CallbackQueryHandler(debt_create_paylink, pattern="^debt_paylink_"))
    application.add_handler(CallbackQueryHandler(debt_check_payment, pattern="^debt_checkpay_"))
    application.add_handler(CallbackQueryHandler(debt_cancel_qr, pattern="^debt_cancelqr_"))
    application.add_handler(CallbackQueryHandler(trano_all, pattern="^debt_payall_"))
    application.add_handler(CallbackQueryHandler(debt_summary, pattern="^debt_summary$"))
    
    # Callback handler cho inline buttons (menu navigation) - Phải ở cuối vì không có pattern
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Command handlers (backup mode)
    application.add_handler(CommandHandler("sanpham", sanpham_command))
    application.add_handler(CommandHandler("themsp", themsp_command))
    application.add_handler(CommandHandler("suasp", suasp_command))
    application.add_handler(CommandHandler("xoasp", xoasp_command))
    
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("dsbh", dsbh_command))
    application.add_handler(CommandHandler("laithang", laithang_command))
    application.add_handler(CommandHandler("xoabh", xoabh_command))
    
    application.add_handler(CommandHandler("chi", chi_command))
    application.add_handler(CommandHandler("chitieu", chitieu_command))
    application.add_handler(CommandHandler("homnay", homnay_command))
    application.add_handler(CommandHandler("thang", thang_command))
    application.add_handler(CommandHandler("xoachi", xoachi_command))
    
    # Debt commands
    application.add_handler(CommandHandler("no", no_command))
    
    # Handler cho lệnh không xác định
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Đăng ký error handler
    application.add_error_handler(error_handler)
    
    # Chạy bot
    logger.info("🚀 CashFlow Bot đang khởi động...")
    logger.info(f"📊 Sheet ID: {config.SHEET_ID[:20]}...")
    
    # Lấy URL webhook từ env (Render tự set RENDER_EXTERNAL_URL)
    webhook_url = os.getenv('RENDER_EXTERNAL_URL', '')
    port = int(os.getenv('PORT', 10000))
    
    if webhook_url:
        # ===== PRODUCTION: Webhook mode =====
        logger.info(f"🌐 Webhook mode: {webhook_url}")
        
        # Self-ping giữ Render không sleep (chỉ 144 requests/ngày vs polling 30,000+)
        ping_thread = threading.Thread(target=self_ping, daemon=True)
        ping_thread.start()
        logger.info("🔄 Self-ping started (every 5 min)")
        
        application.run_webhook(
            listen='0.0.0.0',
            port=port,
            url_path=config.BOT_TOKEN,
            webhook_url=f"{webhook_url}/{config.BOT_TOKEN}",
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        # ===== LOCAL: Polling mode =====
        logger.info("🔄 Polling mode (local development)")
        logger.info("💡 Nhấn Ctrl+C để dừng bot")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )


if __name__ == "__main__":
    main()
