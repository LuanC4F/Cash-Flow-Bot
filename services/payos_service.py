"""
PayOS Payment Service - Tạo link thanh toán và kiểm tra trạng thái
Sử dụng PayOS REST API trực tiếp (theo payos_integration_guide)
"""

import os
import hmac
import hashlib
import time
import requests
import logging

logger = logging.getLogger(__name__)


class PayOSService:
    """
    Class xử lý tạo payment link + verify webhook.
    Signature = HMAC_SHA256(checksum_key, rawData)
    rawData: các field sắp xếp theo thứ tự ALPHABET, nối bằng &
    """

    BASE_URL = "https://api-merchant.payos.vn"

    def __init__(self):
        self.client_id = os.getenv("PAYOS_CLIENT_ID", "")
        self.api_key = os.getenv("PAYOS_API_KEY", "")
        self.checksum_key = os.getenv("PAYOS_CHECKSUM_KEY", "")

        if not all([self.client_id, self.api_key, self.checksum_key]):
            raise ValueError(
                "❌ PayOS chưa được cấu hình! "
                "Thêm PAYOS_CLIENT_ID, PAYOS_API_KEY, PAYOS_CHECKSUM_KEY vào .env"
            )

    # =============================
    # TẠO SIGNATURE (CHUẨN PAYOS)
    # =============================
    def _create_signature(self, data: dict) -> str:
        """
        signature = HMAC_SHA256(checksum_key, rawData)

        rawData format (BẮT BUỘC ĐÚNG THỨ TỰ ALPHABET):
        amount=xxx&cancelUrl=xxx&description=xxx&orderCode=xxx&returnUrl=xxx
        """
        raw_data = (
            f"amount={data['amount']}"
            f"&cancelUrl={data['cancelUrl']}"
            f"&description={data['description']}"
            f"&orderCode={data['orderCode']}"
            f"&returnUrl={data['returnUrl']}"
        )

        return hmac.new(
            self.checksum_key.encode(),
            raw_data.encode(),
            hashlib.sha256
        ).hexdigest()

    def _get_headers(self) -> dict:
        """Headers chuẩn cho mọi request đến PayOS API"""
        return {
            "Content-Type": "application/json",
            "x-client-id": self.client_id,
            "x-api-key": self.api_key,
        }

    # =============================
    # TẠO LINK THANH TOÁN PAYOS
    # =============================
    def create_payment_link_raw(
        self,
        order_code: int,
        amount: int,
        description: str,
        return_url: str = "https://t.me",
        cancel_url: str = "https://t.me",
    ) -> dict:
        """
        Gọi PayOS API tạo payment link.

        Params:
            order_code (int): Mã đơn hàng (PHẢI là int, unique)
            amount (int): Số tiền (VND, BẮT BUỘC int)
            description (str): Mô tả đơn hàng (tối đa 25 ký tự)
            return_url (str): URL redirect khi thanh toán thành công
            cancel_url (str): URL redirect khi huỷ thanh toán

        Returns:
            dict: Response từ PayOS chứa checkoutUrl, QR info, etc.
        """
        url = f"{self.BASE_URL}/v2/payment-requests"

        payload = {
            "orderCode": int(order_code),
            "amount": int(amount),
            "description": description,
            "cancelUrl": cancel_url,
            "returnUrl": return_url,
        }

        # 🔐 TÍNH SIGNATURE SAU KHI CÓ PAYLOAD
        payload["signature"] = self._create_signature(payload)

        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers(),
            timeout=15,
        )

        try:
            return response.json()
        except Exception:
            return {
                "error": "INVALID_RESPONSE",
                "status_code": response.status_code,
                "raw": response.text,
            }

    # =============================
    # KIỂM TRA TRẠNG THÁI THANH TOÁN
    # =============================
    def get_payment_status_raw(self, order_code: int) -> dict:
        """
        Kiểm tra trạng thái thanh toán qua PayOS API.

        Returns:
            dict: Response từ PayOS chứa status, amount, etc.
        """
        url = f"{self.BASE_URL}/v2/payment-requests/{order_code}"

        response = requests.get(
            url,
            headers=self._get_headers(),
            timeout=15,
        )

        try:
            return response.json()
        except Exception:
            return {
                "error": "INVALID_RESPONSE",
                "status_code": response.status_code,
                "raw": response.text,
            }

    # =============================
    # VERIFY WEBHOOK SIGNATURE
    # =============================
    def verify_webhook(self, data: dict, signature: str) -> bool:
        """
        Verify signature từ PayOS webhook callback.

        rawData format:
        orderCode=xxx&amount=xxx&description=xxx
        """
        raw_data = (
            f"orderCode={data['orderCode']}"
            f"&amount={data['amount']}"
            f"&description={data['description']}"
        )

        expected_signature = hmac.new(
            self.checksum_key.encode(),
            raw_data.encode(),
            hashlib.sha256
        ).hexdigest()

        return expected_signature == signature


# ============================================================
# SINGLETON + WRAPPER FUNCTIONS
# Giữ nguyên interface cũ để handlers/debt.py không cần sửa
# ============================================================

_payos_service = None


def _get_service() -> PayOSService:
    """Get PayOS service (singleton)"""
    global _payos_service
    if _payos_service is None:
        _payos_service = PayOSService()
    return _payos_service


def create_payment_link(customer: str, amount: int, description: str = "") -> dict:
    """
    Tạo link thanh toán PayOS.

    Args:
        customer: Tên khách hàng
        amount: Số tiền (VND, int)
        description: Mô tả (tùy chọn)

    Returns:
        dict: {order_code, checkout_url, qr_code}
    """
    service = _get_service()

    # Tạo order_code unique từ timestamp
    order_code = int(time.time() * 1000) % 2147483647  # PayOS giới hạn int32

    desc = description or f"Tra no - {customer}"
    # PayOS giới hạn description 25 ký tự
    if len(desc) > 25:
        desc = desc[:25]

    render_url = os.getenv("RENDER_EXTERNAL_URL", "https://t.me")

    # Gọi PayOS REST API
    response = service.create_payment_link_raw(
        order_code=order_code,
        amount=int(amount),
        description=desc,
        return_url=f"{render_url}/payment/success",
        cancel_url=f"{render_url}/payment/cancel",
    )

    logger.info(f"PayOS create response: code={response.get('code')}, desc={response.get('desc')}")

    # Kiểm tra response
    if response.get("code") != "00":
        error_msg = response.get("desc", response.get("error", "Unknown error"))
        logger.error(f"PayOS error: {error_msg} | Full response: {response}")
        raise Exception(f"PayOS error: {error_msg}")

    data = response.get("data", {})
    checkout_url = data.get("checkoutUrl", "")

    # =============================
    # TẠO QR CODE URL (DÙNG VIETQR)
    # =============================
    # VietQR API tạo ảnh QR đẹp, chuẩn ngân hàng VN
    # Format: https://img.vietqr.io/image/{mã_NH}-{số_TK}-compact.png?amount=xxx&addInfo=xxx
    bin_code = data.get("bin", "")
    account_number = data.get("accountNumber", "")
    pay_description = data.get("description", desc)

    if bin_code and account_number:
        qr_code = (
            f"https://img.vietqr.io/image/"
            f"{bin_code}-{account_number}-compact.png"
            f"?amount={int(amount)}&addInfo={pay_description}"
        )
        logger.info(f"VietQR URL generated: {qr_code}")
    else:
        # Fallback: dùng base64 QR từ PayOS (nếu có)
        qr_code = data.get("qrCode", "")
        if not qr_code:
            # Fallback cuối: tạo QR từ checkout URL
            import urllib.parse
            encoded_url = urllib.parse.quote(checkout_url, safe="")
            qr_code = f"https://quickchart.io/qr?text={encoded_url}&size=400"
        logger.info(f"Fallback QR used (no VietQR data)")

    return {
        "order_code": order_code,
        "checkout_url": checkout_url,
        "qr_code": qr_code,
    }


def check_payment_status(order_code: int) -> dict:
    """
    Kiểm tra trạng thái thanh toán.

    Args:
        order_code: Mã đơn hàng

    Returns:
        dict: {status, amount, order_code}
        status: PENDING, PAID, CANCELLED, EXPIRED
    """
    service = _get_service()

    response = service.get_payment_status_raw(order_code)

    logger.info(f"PayOS status response: code={response.get('code')}, desc={response.get('desc')}")

    if response.get("code") != "00":
        error_msg = response.get("desc", "Unknown error")
        logger.error(f"PayOS status error: {error_msg}")
        raise Exception(f"PayOS error: {error_msg}")

    data = response.get("data", {})

    return {
        "status": data.get("status", "UNKNOWN"),
        "amount": data.get("amount", 0),
        "order_code": order_code,
    }
