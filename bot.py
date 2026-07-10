"""
CashFlow Bot - Telegram Bot quản lý thu chi
Main entry point
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ConversationHandler,
    filters
)
from telegram.ext._application import ApplicationHandlerStop

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
    chi_date_select, chi_date_input,
    xoachi_start, xoachi_confirm,
    suachi_start, suachi_select_row, suachi_select_field, suachi_save,
    cancel_expense,
    CHI_AMOUNT, CHI_DESC, CHI_DATE,
    XOACHI_ROW,
    SUACHI_ROW, SUACHI_FIELD, SUACHI_VALUE
)

# Debt handlers
from handlers.debt import (
    no_command, 
    ghino_start, ghino_customer, ghino_amount, ghino_note, ghino_skip_note,
    ghino_select_customer, ghino_more_customers, ghino_new_customer,
    ghino_telegram_id, ghino_skip_tid,
    debt_list, debt_by_customer, debt_customer_detail, debt_summary,
    debt_create_paylink, debt_check_payment, debt_cancel_qr,
    debt_doino, debt_set_tid_start, debt_set_tid_confirm,
    cust_pay, cust_check, cust_cancel, cust_refresh,
    trano_start, trano_confirm, trano_all,
    xoano_start, xoano_confirm,
    cancel_debt, debt_conv_fallback,
    NO_CUSTOMER, NO_AMOUNT, NO_NOTE, NO_TELEGRAM_ID, TRANO_SELECT, XOANO_SELECT, SET_TID
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


# ==================== BẢO MẬT TOÀN CỤC ====================
from utils.security import check_permission, is_expense_user, UNAUTHORIZED_MESSAGE as SEC_UNAUTHORIZED


async def global_permission_check(update: Update, context):
    """
    Chặn user không phải admin.
    Cho phép:
    - /start (để bot ghi nhận user)
    - custpay_, custcheck_, custcancel_ (khách thanh toán)
    - uexp_, ucat_, uexp_menu (expense users)
    """
    user = update.effective_user
    if not user:
        return
    
    # Admin → cho phép mọi thứ
    if check_permission(user.id):
        return
    
    # /start → cho phép
    if update.message and update.message.text:
        if update.message.text.startswith('/start'):
            return
    
    # Nút thanh toán khách → cho phép
    if update.callback_query:
        data = update.callback_query.data or ''
        if data.startswith(('custpay_', 'custcheck_', 'custcancel_', 'cust_refresh')):
            return
    
    # Expense user: cho phép callbacks + text input
    if is_expense_user(user.id):
        if update.callback_query:
            data = update.callback_query.data or ''
            if data.startswith(('uexp_', 'ucat_', 'ueditf_')):
                return
        # Cho phép text input (conversation flow: nhập tiền, mô tả)
        if update.message and update.message.text and not update.message.text.startswith('/'):
            return
    
    # Chặn tất cả còn lại
    if update.callback_query:
        await update.callback_query.answer(SEC_UNAUTHORIZED, show_alert=True)
    elif update.message:
        await update.message.reply_text(SEC_UNAUTHORIZED)
    
    raise ApplicationHandlerStop()


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
            CHI_DATE: [
                CallbackQueryHandler(chi_date_select, pattern="^expense_date_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chi_date_input),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_expense, pattern="^cancel_expense$"),
            CommandHandler("cancel", cancel_expense),
        ],
        per_message=False,
    )
    
    # Sửa chi tiêu
    suachi_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(suachi_start, pattern="^expense_edit$")],
        states={
            SUACHI_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, suachi_select_row)],
            SUACHI_FIELD: [CallbackQueryHandler(suachi_select_field, pattern="^editfield_")],
            SUACHI_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, suachi_save)],
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
                CallbackQueryHandler(ghino_more_customers, pattern="^debt_more_"),
                CallbackQueryHandler(ghino_new_customer, pattern="^debt_newcust$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_customer),
            ],
            NO_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_amount)],
            NO_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_note),
                CallbackQueryHandler(ghino_skip_note, pattern="^debt_skip_note$"),
            ],
            NO_TELEGRAM_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ghino_telegram_id),
                CallbackQueryHandler(ghino_skip_tid, pattern="^debt_skip_tid$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_debt, pattern="^cancel_debt$"),
            CommandHandler("cancel", cancel_debt),
            CallbackQueryHandler(debt_conv_fallback),  # Catch-all: end stale conversation
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
            CallbackQueryHandler(debt_conv_fallback),  # Catch-all
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
            CallbackQueryHandler(debt_conv_fallback),  # Catch-all
        ],
        per_message=False,
    )
    
    # ==================== ĐĂNG KÝ HANDLERS ====================
    
    # 🔒 GLOBAL PERMISSION CHECK (group -1: chạy TRƯỚC tất cả)
    application.add_handler(
        MessageHandler(filters.ALL, global_permission_check), group=-1
    )
    application.add_handler(
        CallbackQueryHandler(global_permission_check), group=-1
    )
    
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
    application.add_handler(suachi_conv)
    application.add_handler(ghino_conv)
    application.add_handler(trano_conv)
    application.add_handler(xoano_conv)
    
    # Set Telegram ID conversation
    set_tid_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(debt_set_tid_start, pattern="^debt_settid_")],
        states={
            SET_TID: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_set_tid_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_debt, pattern="^cancel_debt$"),
            CommandHandler("cancel", cancel_debt),
        ],
        per_message=False,
    )
    application.add_handler(set_tid_conv, group=1)  # Group 1: tránh bị block bởi ConversationHandler group 0
    
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
    application.add_handler(CallbackQueryHandler(debt_doino, pattern="^debt_doino_"))
    application.add_handler(CallbackQueryHandler(trano_all, pattern="^debt_payall_"))
    application.add_handler(CallbackQueryHandler(debt_summary, pattern="^debt_summary$"))
    
    # Customer self-payment handlers (KHÔNG check permission - để khách nợ tự thanh toán)
    application.add_handler(CallbackQueryHandler(cust_pay, pattern="^custpay_"))
    application.add_handler(CallbackQueryHandler(cust_check, pattern="^custcheck_"))
    application.add_handler(CallbackQueryHandler(cust_cancel, pattern="^custcancel_"))
    application.add_handler(CallbackQueryHandler(cust_refresh, pattern="^cust_refresh$"))
    
    # ==================== USER EXPENSE CONVERSATIONS ====================
    # PHẢI đăng ký TRƯỚC button_callback (vì button_callback không có pattern, bắt tất cả)
    from handlers.user_expense import (
        uexp_start, uexp_select_category, uexp_amount, uexp_desc, uexp_cancel,
        uexp_date_select, uexp_date_input,
        uexp_today, uexp_month, uexp_day_detail, uexp_menu,
        uexp_delete_start, uexp_delete_confirm,
        uexp_edit_start, uexp_edit_select_row, uexp_edit_select_field, uexp_edit_save,
        UEXP_AMOUNT, UEXP_DESC, UEXP_DATE, UEXP_DELETE_ROW,
        UEXP_EDIT_ROW, UEXP_EDIT_FIELD, UEXP_EDIT_VALUE
    )
    
    # Ghi chi tiêu user
    uexp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(uexp_start, pattern="^uexp_add$")],
        states={
            UEXP_AMOUNT: [
                CallbackQueryHandler(uexp_select_category, pattern="^ucat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_amount),
            ],
            UEXP_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_desc),
            ],
            UEXP_DATE: [
                CallbackQueryHandler(uexp_date_select, pattern="^uexp_date_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_date_input),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(uexp_cancel, pattern="^uexp_cancel$"),
            CommandHandler("cancel", uexp_cancel),
        ],
        per_message=False,
    )
    application.add_handler(uexp_conv)
    
    # Xóa chi tiêu user
    uexp_del_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(uexp_delete_start, pattern="^uexp_delete$")],
        states={
            UEXP_DELETE_ROW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_delete_confirm),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(uexp_cancel, pattern="^uexp_cancel$"),
            CommandHandler("cancel", uexp_cancel),
        ],
        per_message=False,
    )
    application.add_handler(uexp_del_conv)
    
    # Sửa chi tiêu user
    uexp_edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(uexp_edit_start, pattern="^uexp_edit$")],
        states={
            UEXP_EDIT_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_edit_select_row)],
            UEXP_EDIT_FIELD: [CallbackQueryHandler(uexp_edit_select_field, pattern="^ueditf_")],
            UEXP_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, uexp_edit_save)],
        },
        fallbacks=[
            CallbackQueryHandler(uexp_cancel, pattern="^uexp_cancel$"),
            CommandHandler("cancel", uexp_cancel),
        ],
        per_message=False,
    )
    application.add_handler(uexp_edit_conv)
    
    # Thống kê chi tiêu user (callbacks)
    application.add_handler(CallbackQueryHandler(uexp_today, pattern="^uexp_today$"))
    application.add_handler(CallbackQueryHandler(uexp_month, pattern="^uexp_month$"))
    application.add_handler(CallbackQueryHandler(uexp_day_detail, pattern="^uexp_day_"))
    application.add_handler(CallbackQueryHandler(uexp_menu, pattern="^uexp_menu$"))
    
    # Callback handler cho inline buttons (menu navigation) - Phải ở CUỐI vì không có pattern
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
    
    # Admin: migrate customers
    async def migrate_command(update: Update, context):
        from utils.security import check_permission, UNAUTHORIZED_MESSAGE
        if not check_permission(update.effective_user.id):
            await update.message.reply_text(UNAUTHORIZED_MESSAGE)
            return
        from services import sheets
        await update.message.reply_text("⏳ Đang migrate khách hàng từ Debts → Customers...")
        try:
            count = sheets.migrate_customers_from_debts()
            await update.message.reply_text(f"✅ Đã migrate {count} khách hàng mới vào sheet Customers!")
        except Exception as e:
            await update.message.reply_text(f"❌ Lỗi: {e}")
    
    application.add_handler(CommandHandler("migrate", migrate_command))
    
    # Admin: cấp quyền chi tiêu
    async def capquyen_command(update: Update, context):
        from utils.security import check_permission, UNAUTHORIZED_MESSAGE
        if not check_permission(update.effective_user.id):
            await update.message.reply_text(UNAUTHORIZED_MESSAGE)
            return
        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "❓ Cách dùng: `/capquyen <TelegramID> <Tên>`\n\n"
                "Ví dụ: `/capquyen 123456789 Anh Hiếu`",
                parse_mode='Markdown'
            )
            return
        tid = args[0]
        name = ' '.join(args[1:])
        from services import sheets
        try:
            result = sheets.add_expense_user(tid, name)
            await update.message.reply_text(
                f"✅ Đã cấp quyền chi tiêu!\n\n"
                f"👤 Tên: {name}\n"
                f"📱 TID: `{tid}`\n"
                f"📄 Sheet: `{result.get('sheet_name', f'Chi_{tid}')}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Lỗi: {e}")
    
    application.add_handler(CommandHandler("capquyen", capquyen_command))
    
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
        # ===== PRODUCTION: Webhook mode with Starlette =====
        # Dùng Starlette để xử lý cả Telegram webhook lẫn SePay webhook
        import asyncio
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, PlainTextResponse
        from starlette.routing import Route
        from contextlib import asynccontextmanager
        
        logger.info(f"🌐 Webhook mode: {webhook_url}")
        
        @asynccontextmanager
        async def lifespan(app):
            """Manage bot lifecycle with Starlette."""
            await application.initialize()
            await application.start()
            await application.bot.set_webhook(
                url=f"{webhook_url}/{config.BOT_TOKEN}",
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            logger.info("✅ Bot started + webhook set")
            yield
            await application.stop()
            await application.shutdown()
            logger.info("🛑 Bot stopped")
        
        async def telegram_webhook(request: Request):
            """Handle Telegram updates."""
            try:
                data = await request.json()
                update = Update.de_json(data, application.bot)
                await application.update_queue.put(update)
                return PlainTextResponse("OK")
            except Exception as e:
                logger.error(f"Telegram webhook error: {e}")
                return PlainTextResponse("ERROR", status_code=500)
        
        async def sepay_webhook(request: Request):
            """Handle SePay payment webhooks."""
            try:
                data = await request.json()
                logger.info(f"SePay webhook received: {data}")
                
                from services.sepay_service import handle_webhook
                result = handle_webhook(data)
                
                if result:
                    from handlers.debt import handle_sepay_payment_success
                    await handle_sepay_payment_success(application.bot, result)
                    logger.info(f"SePay payment processed: {result['payment_code']}")
                
                return JSONResponse({"success": True})
            except Exception as e:
                logger.error(f"SePay webhook error: {e}")
                return JSONResponse({"success": False, "error": str(e)}, status_code=500)
        
        async def health_check(request: Request):
            return PlainTextResponse("OK")
        
        starlette_app = Starlette(
            lifespan=lifespan,
            routes=[
                Route(f"/{config.BOT_TOKEN}", telegram_webhook, methods=["POST"]),
                Route("/sepay-webhook", sepay_webhook, methods=["POST"]),
                Route("/health", health_check, methods=["GET"]),
                Route("/", health_check, methods=["GET"]),
            ],
        )
        
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
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

