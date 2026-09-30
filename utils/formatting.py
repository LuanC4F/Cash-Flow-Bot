"""
Formatting utilities - Format tiền, ngày, parse input
"""

from typing import Tuple, Optional


def escape_markdown(text: str) -> str:
    """
    Escape các ký tự đặc biệt trong Telegram Markdown
    
    Args:
        text: Chuỗi cần escape
    
    Returns:
        Chuỗi đã escape
    """
    if not text:
        return ""
    
    # Các ký tự đặc biệt trong Markdown cần escape
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    result = text
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def format_currency(amount: float) -> str:
    """
    Format số tiền theo định dạng Việt Nam
    
    Args:
        amount: Số tiền
    
    Returns:
        Chuỗi đã format (ví dụ: 1.500.000đ)
    """
    if amount >= 0:
        return f"{amount:,.0f}đ".replace(",", ".")
    else:
        return f"-{abs(amount):,.0f}đ".replace(",", ".")


def parse_amount(amount_str: str) -> Optional[float]:
    """
    Parse chuỗi số tiền thành số
    
    Hỗ trợ các định dạng:
    - 50000
    - 50.000
    - 50,000
    - 50k (= 50,000)
    - 1.5m (= 1,500,000)
    - 1tr (= 1,000,000)
    
    Args:
        amount_str: Chuỗi số tiền
    
    Returns:
        Số tiền đã parse, hoặc None nếu không hợp lệ
    """
    if not amount_str:
        return None
    
    # Loại bỏ khoảng trắng và ký tự đ
    amount_str = amount_str.strip().lower().replace('đ', '').replace('d', '')
    
    # Xử lý suffix đặc biệt
    multiplier = 1
    
    if amount_str.endswith('tr'):
        multiplier = 1_000_000
        amount_str = amount_str[:-2]
    elif amount_str.endswith('m'):
        multiplier = 1_000_000
        amount_str = amount_str[:-1]
    elif amount_str.endswith('k'):
        multiplier = 1_000
        amount_str = amount_str[:-1]
    
    # Loại bỏ dấu phân cách (. và ,)
    amount_str = amount_str.replace(".", "").replace(",", "")
    
    try:
        amount = float(amount_str) * multiplier
        if amount <= 0:
            return None
        return amount
    except ValueError:
        return None


def parse_transaction_input(text: str) -> Tuple[Optional[float], str]:
    """
    Parse input giao dịch từ người dùng
    
    Ví dụ:
    - "50000 Ăn sáng" -> (50000, "Ăn sáng")
    - "50k coffee" -> (50000, "coffee")
    - "1.5m Lương" -> (1500000, "Lương")
    
    Args:
        text: Chuỗi input từ người dùng
    
    Returns:
        Tuple (amount, description)
    """
    if not text:
        return None, ""
    
    parts = text.strip().split(maxsplit=1)
    
    if not parts:
        return None, ""
    
    amount = parse_amount(parts[0])
    description = parts[1] if len(parts) > 1 else ""
    
    return amount, description


def get_month_name(month: int) -> str:
    """Lấy tên tháng bằng tiếng Việt"""
    months = {
        1: "Tháng 1", 2: "Tháng 2", 3: "Tháng 3",
        4: "Tháng 4", 5: "Tháng 5", 6: "Tháng 6",
        7: "Tháng 7", 8: "Tháng 8", 9: "Tháng 9",
        10: "Tháng 10", 11: "Tháng 11", 12: "Tháng 12"
    }
    return months.get(month, f"Tháng {month}")


def get_category_emoji(category: str) -> str:
    """Get emoji for expense category"""
    emojis = {
        'living': '🏠',
        'personal': '👤',
        'work': '💼',
        'entertainment': '🎮',
        'health': '🏥',
        'food': '🍜',
        'transport': '🚗',
        'shared': '🏘',
        'other': '📝',
    }
    return emojis.get(category.lower(), '📝')
