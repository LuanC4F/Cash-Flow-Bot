"""
SePay + VietQR Payment Service
Thay thế PayOS - miễn phí hoàn toàn, dùng webhook thay polling.
"""

import os
import time
import logging
import re
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

SEPAY_API_TOKEN = os.getenv("SEPAY_API_TOKEN", "")
VIETQR_BANK_ID = os.getenv("VIETQR_BANK_ID", "MB")
VIETQR_ACCOUNT_NO = os.getenv("VIETQR_ACCOUNT_NO", "")
VIETQR_ACCOUNT_NAME = os.getenv("VIETQR_ACCOUNT_NAME", "")
PAYMENT_CODE_PREFIX = os.getenv("PAYMENT_CODE_PREFIX", "BOTNO")


# ==================== IN-MEMORY PAYMENT TRACKING ====================
# {payment_code: {customer, amount, status, created_at, chat_id, qr_message_id, is_customer}}
_pending_payments = {}


def _generate_payment_code() -> str:
    """Sinh mã thanh toán unique: PREFIX + timestamp_short"""
    ts = int(time.time()) % 10000000  # 7 digits
    return f"{PAYMENT_CODE_PREFIX}{ts}"


# ==================== VIETQR ====================

def generate_vietqr_url(amount: int, content: str) -> str:
    """Tạo URL ảnh QR VietQR (miễn phí, không cần API key).
    
    Returns: URL ảnh QR có sẵn số tiền + nội dung CK.
    """
    account_name = quote(VIETQR_ACCOUNT_NAME)
    add_info = quote(content)
    return (
        f"https://img.vietqr.io/image/"
        f"{VIETQR_BANK_ID}-{VIETQR_ACCOUNT_NO}-compact2.jpg"
        f"?amount={amount}&addInfo={add_info}&accountName={account_name}"
    )


# ==================== CREATE PAYMENT ====================

def create_payment(customer: str, amount: int) -> dict:
    """Tạo payment mới: sinh code + QR URL + lưu pending.
    
    Returns: {payment_code, qr_url, amount, bank_info}
    """
    if not VIETQR_ACCOUNT_NO:
        raise ValueError("Chưa cấu hình VIETQR_ACCOUNT_NO trong .env")
    
    payment_code = _generate_payment_code()
    qr_url = generate_vietqr_url(amount, payment_code)
    
    # Lưu vào pending
    _pending_payments[payment_code] = {
        'customer': customer,
        'amount': amount,
        'status': 'pending',
        'created_at': time.time(),
        'chat_id': None,
        'qr_message_id': None,
        'is_customer': False,
    }
    
    logger.info(f"Created payment: {payment_code} for {customer}, {amount} VND")
    
    return {
        'payment_code': payment_code,
        'qr_url': qr_url,
        'amount': amount,
        'bank_id': VIETQR_BANK_ID,
        'account_no': VIETQR_ACCOUNT_NO,
        'account_name': VIETQR_ACCOUNT_NAME,
    }


def update_payment_meta(payment_code: str, chat_id: int = None, 
                        qr_message_id: int = None, is_customer: bool = False):
    """Cập nhật metadata cho payment (chat_id, message_id) sau khi gửi QR."""
    if payment_code in _pending_payments:
        if chat_id is not None:
            _pending_payments[payment_code]['chat_id'] = chat_id
        if qr_message_id is not None:
            _pending_payments[payment_code]['qr_message_id'] = qr_message_id
        _pending_payments[payment_code]['is_customer'] = is_customer


# ==================== CHECK STATUS ====================

def check_payment_status(payment_code: str) -> dict:
    """Kiểm tra thanh toán: gọi API SePay lấy giao dịch gần nhất, so khớp nội dung CK.
    
    Fallback: nếu in-memory đã PAID (do webhook) thì trả luôn.
    """
    # 1. Check in-memory trước (nhanh, webhook đã xác nhận)
    payment = _pending_payments.get(payment_code)
    if not payment:
        return {'status': 'NOT_FOUND'}
    
    if payment['status'] == 'paid':
        return {
            'status': 'PAID',
            'customer': payment['customer'],
            'amount': payment.get('paid_amount', payment['amount']),
        }
    
    # 2. Gọi API SePay kiểm tra giao dịch thật
    try:
        import requests
        headers = {
            'Authorization': f'Bearer {SEPAY_API_TOKEN}',
            'Content-Type': 'application/json',
        }
        resp = requests.get(
            'https://my.sepay.vn/userapi/transactions/list',
            headers=headers,
            params={
                'limit': 10,
                'account_number': VIETQR_ACCOUNT_NO,
            },
            timeout=10,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            transactions = data.get('transactions', [])
            
            for txn in transactions:
                content = (txn.get('transaction_content') or '').upper()
                if payment_code.upper() in content and txn.get('amount_in', 0) > 0:
                    # Tìm thấy giao dịch khớp!
                    amount = int(txn['amount_in'])
                    payment['status'] = 'paid'
                    payment['paid_amount'] = amount
                    logger.info(f"API check: PAID! {payment_code}, amount={amount}")
                    return {
                        'status': 'PAID',
                        'customer': payment['customer'],
                        'amount': amount,
                    }
        else:
            logger.warning(f"SePay API error: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        logger.error(f"SePay API check failed: {e}")
    
    # 3. Chưa tìm thấy → PENDING
    return {
        'status': 'PENDING',
        'customer': payment['customer'],
        'amount': payment['amount'],
    }


def cancel_payment(payment_code: str):
    """Hủy payment pending."""
    if payment_code in _pending_payments:
        _pending_payments[payment_code]['status'] = 'cancelled'
        logger.info(f"Cancelled payment: {payment_code}")


# ==================== WEBHOOK HANDLER ====================

def handle_sepay_webhook(data: dict, auth_header: str) -> dict:
    """Xử lý POST webhook từ SePay.
    
    Args:
        data: JSON body từ SePay
        auth_header: Header Authorization (format: "Apikey xxx")
    
    Returns:
        dict: {matched: bool, payment_code, customer, amount} hoặc {matched: False}
    """
    # 1. Verify API Token
    expected = f"Apikey {SEPAY_API_TOKEN}"
    if auth_header.strip() != expected:
        logger.warning(f"SePay webhook: unauthorized (got: {auth_header[:20]}...)")
        return {'matched': False, 'error': 'unauthorized'}
    
    # 2. Chỉ xử lý tiền VÀO
    transfer_type = data.get('transferType', '')
    if transfer_type != 'in':
        logger.debug(f"SePay webhook: skip transferType={transfer_type}")
        return {'matched': False, 'reason': 'not_incoming'}
    
    # 3. Parse nội dung CK → tìm payment_code
    content = data.get('content', '') or data.get('description', '')
    transfer_amount = int(data.get('transferAmount', 0))
    
    prefix = re.escape(PAYMENT_CODE_PREFIX)
    match = re.search(f'{prefix}(\\d+)', content, re.IGNORECASE)
    
    if not match:
        logger.debug(f"SePay webhook: no payment code in content: {content}")
        return {'matched': False, 'reason': 'no_code'}
    
    payment_code = f"{PAYMENT_CODE_PREFIX}{match.group(1)}"
    
    # 4. Tìm payment pending
    payment = _pending_payments.get(payment_code)
    if not payment:
        logger.warning(f"SePay webhook: payment not found: {payment_code}")
        return {'matched': False, 'reason': 'not_found', 'payment_code': payment_code}
    
    # Idempotency
    if payment['status'] == 'paid':
        logger.info(f"SePay webhook: already paid: {payment_code}")
        return {'matched': False, 'reason': 'already_paid'}
    
    if payment['status'] != 'pending':
        return {'matched': False, 'reason': f'status_{payment["status"]}'}
    
    # 5. Kiểm tra số tiền
    if transfer_amount < payment['amount']:
        logger.warning(
            f"SePay webhook: thiếu tiền. Cần {payment['amount']}, nhận {transfer_amount}. "
            f"Code: {payment_code}"
        )
        return {'matched': False, 'reason': 'insufficient_amount'}
    
    # 6. ✅ Thanh toán thành công!
    payment['status'] = 'paid'
    payment['paid_amount'] = transfer_amount
    
    logger.info(f"SePay webhook: PAID! {payment_code}, {payment['customer']}, {transfer_amount}")
    
    return {
        'matched': True,
        'payment_code': payment_code,
        'customer': payment['customer'],
        'amount': transfer_amount,
        'chat_id': payment['chat_id'],
        'qr_message_id': payment['qr_message_id'],
        'is_customer': payment['is_customer'],
    }


# ==================== CLEANUP ====================

def cleanup_expired(max_age_seconds: int = 1800):
    """Xóa payments quá cũ (default: 30 phút)."""
    now = time.time()
    expired = [
        code for code, p in _pending_payments.items()
        if now - p['created_at'] > max_age_seconds
    ]
    for code in expired:
        del _pending_payments[code]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired payments")


def get_pending_payment_by_customer(customer: str) -> str:
    """Tìm payment_code pending của customer (nếu có)."""
    for code, p in _pending_payments.items():
        if p['customer'] == customer and p['status'] == 'pending':
            return code
    return None
