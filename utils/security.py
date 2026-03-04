"""
Security utilities - Kiểm tra quyền truy cập
"""

import config


def check_permission(user_id: int) -> bool:
    """
    Kiểm tra quyền truy cập của user.
    Chỉ ALLOWED_USER_ID mới được phép dùng bot.
    Nếu không cấu hình ALLOWED_USER_ID → KHÔNG AI được dùng.
    """
    if not config.ALLOWED_USER_ID:
        return False  # Chưa cấu hình → chặn tất cả
    return user_id == config.ALLOWED_USER_ID


def is_admin(user_id: int) -> bool:
    """Kiểm tra user có phải admin không"""
    return check_permission(user_id)


UNAUTHORIZED_MESSAGE = "🚫 Đi chỗ khác chơi, đại ca Luân mới được phép dùng bot này 👌."
