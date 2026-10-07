"""
utils/menu_tracker.py
Quản lý active menu ID và danh sách message menu của bot.
Giúp vô hiệu hóa các menu cũ dở dang khi người dùng /start lại bot.
"""

import os
import json
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# File lưu session để duy trì qua các lần restart/redeploy
SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".menu_sessions.json")

_ACTIVE_MENUS: Dict[int, int] = {}
_TRACKED_MENUS: Dict[int, List[int]] = {}


def _load_sessions():
    global _ACTIVE_MENUS, _TRACKED_MENUS
    if not os.path.exists(SESSION_FILE):
        return
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _ACTIVE_MENUS = {int(k): int(v) for k, v in data.get("active", {}).items()}
            _TRACKED_MENUS = {int(k): [int(m) for m in v] for k, v in data.get("tracked", {}).items()}
    except Exception as e:
        logger.debug(f"Không thể đọc file menu session: {e}")


def _save_sessions():
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "active": _ACTIVE_MENUS,
                "tracked": _TRACKED_MENUS,
            }, f, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Không thể ghi file menu session: {e}")


# Load ngay khi module import
_load_sessions()


def set_active_menu(user_id: int, message_id: int) -> None:
    """Ghi nhận message_id này là active menu duy nhất của user."""
    if not user_id or not message_id:
        return
    _ACTIVE_MENUS[user_id] = message_id
    mids = _TRACKED_MENUS.setdefault(user_id, [])
    if message_id not in mids:
        mids.append(message_id)
    if len(mids) > 20:
        _TRACKED_MENUS[user_id] = mids[-20:]
    _save_sessions()


def get_active_menu(user_id: int) -> Optional[int]:
    """Lấy active menu_id của user."""
    return _ACTIVE_MENUS.get(user_id)


def track_menu_id(user_id: int, message_id: int) -> None:
    """Lưu thêm 1 message_id của bot vào danh sách cần dọn dẹp sau này."""
    if not user_id or not message_id:
        return
    mids = _TRACKED_MENUS.setdefault(user_id, [])
    if message_id not in mids:
        mids.append(message_id)
    if len(mids) > 20:
        _TRACKED_MENUS[user_id] = mids[-20:]
    _save_sessions()


def get_tracked_menu_ids(user_id: int) -> List[int]:
    """Lấy danh sách các message_ids đã theo dõi của user."""
    return list(_TRACKED_MENUS.get(user_id, []))


def clear_tracked_menu_ids(user_id: int) -> None:
    """Xóa danh sách message_ids cũ sau khi đã dọn dẹp."""
    if user_id in _TRACKED_MENUS:
        _TRACKED_MENUS[user_id] = []
        _save_sessions()


def is_message_stale(user_id: int, message_id: int) -> bool:
    """Kiểm tra message_id này có phải từ phiên cũ (trước active menu) không."""
    if not user_id or not message_id:
        return False
    active = _ACTIVE_MENUS.get(user_id)
    if active and message_id < active:
        return True
    return False
