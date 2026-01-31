"""
Security utilities - Kiểm tra quyền truy cập
"""

import config

# ==================== BẢO MẬT ====================
# Thông báo khi không có quyền
# VỊ TRÍ: /Users/daoluutrongluan/Coding/Bot_Python/QuanLyThuChi_Bot/utils/security.py
# DÒNG: 11 (dưới đây)
UNAUTHORIZED_MESSAGE = "🚫 Đi chỗ khác chơi, đại ca Luân mới được phép dùng bot này 👌."


def check_permission(user_id: int) -> bool:
    """
    Kiểm tra quyền truy cập của user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        True nếu được phép, False nếu không
    """
    # Nếu không cấu hình ALLOWED_USER_ID thì cho phép tất cả
    if not config.ALLOWED_USER_ID:
        return True
    
    return user_id == config.ALLOWED_USER_ID


async def deny_access(update):
    """Gửi thông báo từ chối truy cập"""
    if update.message:
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
    elif update.callback_query:
        await update.callback_query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
