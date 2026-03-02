"""
PayOS Payment Service - Tạo link thanh toán và kiểm tra trạng thái
"""

import os
import time
from payos import PayOS
from payos.types import CreatePaymentLinkRequest


# PayOS client (singleton)
_payos_client = None


def get_payos_client() -> PayOS:
    """Get PayOS client"""
    global _payos_client
    
    if _payos_client is None:
        client_id = os.getenv('PAYOS_CLIENT_ID', '')
        api_key = os.getenv('PAYOS_API_KEY', '')
        checksum_key = os.getenv('PAYOS_CHECKSUM_KEY', '')
        
        if not all([client_id, api_key, checksum_key]):
            raise ValueError("PayOS chưa được cấu hình! Thêm PAYOS_CLIENT_ID, PAYOS_API_KEY, PAYOS_CHECKSUM_KEY vào env.")
        
        _payos_client = PayOS(
            client_id=client_id,
            api_key=api_key,
            checksum_key=checksum_key,
        )
    
    return _payos_client


def create_payment_link(customer: str, amount: int, description: str = "") -> dict:
    """
    Tạo link thanh toán PayOS
    
    Returns:
        dict: {order_code, checkout_url, qr_code}
    """
    client = get_payos_client()
    
    # Tạo order_code unique từ timestamp
    order_code = int(time.time() * 1000) % 2147483647  # PayOS giới hạn int32
    
    desc = description or f"Thanh toan no - {customer}"
    # PayOS giới hạn description 25 ký tự
    if len(desc) > 25:
        desc = desc[:25]
    
    render_url = os.getenv('RENDER_EXTERNAL_URL', 'https://cash-flow-bot-t5oz.onrender.com')
    
    response = client.payment_requests.create(
        payment_data=CreatePaymentLinkRequest(
            order_code=order_code,
            amount=int(amount),
            description=desc,
            cancel_url=f"{render_url}/payment/cancel",
            return_url=f"{render_url}/payment/success",
        )
    )
    
    # Lấy QR code URL từ PayOS response
    qr_code = ''
    for attr in ['qr_code', 'qrCode', 'qr']:
        if hasattr(response, attr):
            qr_code = getattr(response, attr, '')
            if qr_code:
                break
    
    checkout_url = response.checkout_url
    
    # Nếu PayOS không trả QR → tự tạo từ checkout URL
    if not qr_code:
        import urllib.parse
        encoded_url = urllib.parse.quote(checkout_url, safe='')
        qr_code = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={encoded_url}"
    
    return {
        'order_code': order_code,
        'checkout_url': checkout_url,
        'qr_code': qr_code,
    }


def check_payment_status(order_code: int) -> dict:
    """
    Kiểm tra trạng thái thanh toán
    
    Returns:
        dict: {status, amount, customer}
        status: PENDING, PAID, CANCELLED, EXPIRED
    """
    client = get_payos_client()
    
    response = client.payment_requests.get(order_code=order_code)
    
    return {
        'status': response.status,  # PENDING, PAID, CANCELLED, EXPIRED
        'amount': response.amount if hasattr(response, 'amount') else 0,
        'order_code': order_code,
    }
