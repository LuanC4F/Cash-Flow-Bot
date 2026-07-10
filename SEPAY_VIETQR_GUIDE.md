# Hướng dẫn tích hợp SePay + VietQR — Thanh toán tự động qua chuyển khoản ngân hàng

> **Mục đích:** Tài liệu này dành cho AI Agent đọc để tự triển khai thanh toán tự động bằng SePay + VietQR cho bất kỳ dự án nào. Bao gồm cả hướng dẫn kỹ thuật (code) và hướng dẫn người dùng (thiết lập trên SePay dashboard).

---

## 1. Tổng quan kiến trúc

```
Khách hàng bấm "Thanh toán"
    │
    ▼
[Backend] Tạo payment record trong DB
    → Sinh orderCode = paymentId + OFFSET (tránh trùng giữa các hệ thống)
    → Sinh paymentCode = PREFIX + orderCode (VD: GDS2001234)
    → Tạo QR VietQR miễn phí (URL ảnh QR có sẵn số tiền + nội dung CK)
    │
    ▼
[Frontend] Hiển thị QR + thông tin CK cho khách
    → Khách quét QR bằng app ngân hàng
    → Nội dung chuyển khoản tự điền (VD: "GDS2001234")
    │
    ▼
[Ngân hàng] Giao dịch thành công
    │
    ▼
[SePay] Đọc biến động số dư (qua API ngân hàng)
    → POST webhook về server của bạn
    │
    ▼
[Backend Webhook] Nhận POST từ SePay
    → Xác thực API Token
    → Parse nội dung CK → tìm mã GDS{orderCode}
    → Tìm payment trong DB → kiểm tra số tiền
    → Cập nhật trạng thái payment → xử lý nghiệp vụ (gia hạn, cộng điểm, kích hoạt...)
    │
    ▼
[Frontend Polling] Phát hiện payment.status = 'paid'
    → Hiện thông báo thành công
```

### Ưu điểm so với PayOS / VNPay / Momo

| Tiêu chí | SePay + VietQR | PayOS | VNPay |
|---|---|---|---|
| Chi phí | **Miễn phí hoàn toàn** | Miễn phí 1000 GD, sau đó tính phí | Phí % mỗi GD |
| Đăng ký | Chỉ cần tài khoản ngân hàng cá nhân | Cần ĐKKD hoặc tài khoản merchant | Cần hợp đồng |
| Tốc độ webhook | 3-10 giây sau khi CK | Realtime | Realtime |
| Hạn chế | Chỉ hỗ trợ CK ngân hàng (không ví điện tử) | Đa phương thức | Đa phương thức |
| Phù hợp | Dự án nhỏ, cá nhân, startup | Dự án vừa | Doanh nghiệp |

---

## 2. Đăng ký SePay (Hướng dẫn người dùng)

### Bước 1: Tạo tài khoản
1. Truy cập [https://my.sepay.vn/register](https://my.sepay.vn/register)
2. Đăng ký bằng email
3. Xác nhận email

### Bước 2: Liên kết tài khoản ngân hàng
1. Vào **Tài khoản ngân hàng** → **Thêm tài khoản**
2. Chọn ngân hàng (MB Bank, Vietcombank, Techcombank...)
3. Nhập **số tài khoản** và **tên chủ tài khoản**
4. Làm theo hướng dẫn xác thực (thường là chuyển 1 khoản nhỏ để verify)

> **Lưu ý quan trọng:** SePay hoạt động bằng cách đọc biến động số dư qua API ngân hàng. Một số ngân hàng yêu cầu bạn đăng nhập Internet Banking trên SePay để cấp quyền đọc. MB Bank hỗ trợ tốt nhất.

### Bước 3: Lấy API Token
1. Vào **Cấu hình Công ty** → **API Access**
2. Copy **API Token** (chuỗi dài ~64 ký tự)
3. Lưu token này vào file config của project

### Bước 4: Tạo Webhook
1. Vào **Webhooks** → **Thêm Webhook**

**Bước Cơ bản (1/4):**
- **URL Webhook:** `https://domain-cua-ban.com/api/index.php?route=webhook/sepay`
  - Thay `domain-cua-ban.com` bằng domain thật
  - Route có thể thay đổi tuỳ project (VD: `/api/webhook/sepay`, `/webhook/sepay`)
- **Phương thức:** POST (mặc định)

**Bước Tài khoản (2/4):**
- Chọn **Tuỳ chọn** → tick chọn tài khoản ngân hàng đã liên kết
- **BẬT** toggle **"Dùng để xác thực thanh toán"**
- **TẮT** toggle **"Chỉ gửi khi có mã thanh toán"** (để code tự filter)

**Bước Bảo mật (3/4):**
- Chọn **API Key**
- SePay sẽ gửi header `Authorization: Apikey <token>` trong mỗi request webhook
- Token chính là cái API Token đã copy ở Bước 3

**Bước Cảnh báo (4/4):**
- **BẬT** "Bật cảnh báo khi webhook gặp lỗi liên tiếp" → Để nhận thông báo khi server sập

Bấm **Thêm** để hoàn tất.

---

## 3. Cấu hình Backend (Cho AI Agent)

### 3.1. Constants cần định nghĩa

```php
// SePay API Token (lấy từ SePay Dashboard → Cấu hình Công ty → API Access)
define('SEPAY_API_TOKEN', 'TOKEN_CUA_BAN');

// Thông tin tài khoản ngân hàng (dùng cho VietQR)
define('VIETQR_BANK_ID',      'MB');                // Mã ngân hàng VietQR
define('VIETQR_ACCOUNT_NO',   '0123456789');        // Số tài khoản
define('VIETQR_ACCOUNT_NAME', 'NGUYEN VAN A');      // Tên chủ TK (viết hoa, không dấu)

// Prefix nhúng vào nội dung CK để nhận diện đơn hàng
// Chọn prefix ngắn, dễ nhớ, không trùng với hệ thống khác
define('PAYMENT_CODE_PREFIX', 'GDS');  // VD: GDS, BOT, PAY, ORD...

// Offset cộng vào payment_id để tránh trùng orderCode giữa các hệ thống
// Mỗi project dùng 1 dải khác nhau: 1000000, 2000000, 3000000...
define('ORDER_OFFSET', 2000000);
```

### 3.2. Mã ngân hàng VietQR phổ biến

| Ngân hàng | Mã VietQR |
|---|---|
| MB Bank | `MB` |
| Vietcombank | `VCB` |
| Techcombank | `TCB` |
| BIDV | `BIDV` |
| VietinBank | `CTG` |
| ACB | `ACB` |
| TPBank | `TPB` |
| Sacombank | `STB` |
| VPBank | `VPB` |

> Danh sách đầy đủ: https://api.vietqr.io/v2/banks

### 3.3. Tạo QR VietQR (Miễn phí, không cần API key)

```php
function generateVietQR(int $amount, string $content): string {
    $bankId      = VIETQR_BANK_ID;
    $accountNo   = VIETQR_ACCOUNT_NO;
    $accountName = rawurlencode(VIETQR_ACCOUNT_NAME);
    $addInfo     = rawurlencode($content);
    return "https://img.vietqr.io/image/{$bankId}-{$accountNo}-compact2.jpg"
         . "?amount={$amount}&addInfo={$addInfo}&accountName={$accountName}";
}
```

**Template VietQR có sẵn:**
- `compact` — QR nhỏ gọn
- `compact2` — QR + hiển thị số tiền + nội dung (KHUYÊN DÙNG)
- `print` — QR lớn, phù hợp in
- `qr_only` — Chỉ QR, không thông tin

**Định dạng ảnh:** `.jpg` hoặc `.png` (thay đuôi trong URL)

### 3.4. Tạo Payment (Khi khách bấm thanh toán)

```php
function handleCreatePayment($pdo) {
    // 1. Validate input, tạo record payment trong DB
    // ...
    $paymentId = $pdo->lastInsertId();

    // 2. Sinh orderCode + paymentCode
    $orderCode   = $paymentId + ORDER_OFFSET;         // VD: 2001234
    $paymentCode = PAYMENT_CODE_PREFIX . $orderCode;   // VD: GDS2001234

    // 3. Lưu orderCode vào DB (để webhook tra ngược)
    $pdo->prepare('UPDATE payments SET order_code = ? WHERE id = ?')
        ->execute([$orderCode, $paymentId]);

    // 4. Tạo QR
    $qrUrl = generateVietQR($amount, $paymentCode);

    // 5. Trả về cho frontend
    return [
        'qr_code'      => $qrUrl,          // URL ảnh QR
        'payment_code' => $paymentCode,     // Nội dung CK khách phải ghi
        'amount'       => $amount,          // Số tiền
        'bank_account' => VIETQR_ACCOUNT_NO,
        'bank_name'    => 'MB Bank',        // Tên ngân hàng
        'account_name' => VIETQR_ACCOUNT_NAME,
    ];
}
```

### 3.5. Webhook Handler (Nhận POST từ SePay)

```php
function handleSepayWebhook($pdo, $input) {
    // ========== 1. Xác thực API Token ==========
    $authHeader = $_SERVER['HTTP_AUTHORIZATION']
                  ?? apache_request_headers()['Authorization']
                  ?? '';
    $expected = 'Apikey ' . SEPAY_API_TOKEN;
    if (trim($authHeader) !== $expected) {
        http_response_code(401);
        echo json_encode(['success' => false, 'error' => 'Unauthorized']);
        exit;
    }

    // ========== 2. Chỉ xử lý tiền VÀO ==========
    $transferType = $input['transferType'] ?? '';
    if ($transferType !== 'in') {
        return json_encode(['success' => true]); // Tiền ra → bỏ qua
    }

    // ========== 3. Parse nội dung CK ==========
    $content        = $input['content'] ?? '';
    $transferAmount = (int)($input['transferAmount'] ?? 0);

    $prefix = preg_quote(PAYMENT_CODE_PREFIX, '/');
    if (!preg_match('/' . $prefix . '(\d+)/i', $content, $matches)) {
        // Không tìm thấy mã → giao dịch khác, bỏ qua
        return json_encode(['success' => true]);
    }

    $orderCode = (int)$matches[1];
    $paymentId = $orderCode - ORDER_OFFSET;

    // ========== 4. Tìm payment trong DB ==========
    $payment = $pdo->prepare('SELECT * FROM payments WHERE id = ?');
    $payment->execute([$paymentId]);
    $payment = $payment->fetch();

    if (!$payment) return json_encode(['success' => true]);

    // Idempotency: đã xử lý rồi thì bỏ qua
    if ($payment['status'] === 'paid') {
        return json_encode(['success' => true]);
    }

    // Chỉ xử lý payment đang pending
    if ($payment['status'] !== 'pending') {
        return json_encode(['success' => true]);
    }

    // ========== 5. Kiểm tra số tiền ==========
    if ($transferAmount < (int)$payment['amount']) {
        error_log("SePay: thiếu tiền. Cần {$payment['amount']}, nhận {$transferAmount}");
        return json_encode(['success' => true]);
    }

    // ========== 6. Xử lý nghiệp vụ ==========
    $pdo->beginTransaction();
    try {
        // Cập nhật trạng thái payment
        $pdo->prepare('UPDATE payments SET status = ?, paid_at = NOW() WHERE id = ?')
            ->execute(['paid', $paymentId]);

        // === TUỲ CHỈNH: Thêm logic nghiệp vụ của bạn ở đây ===
        // VD: Gia hạn subscription, kích hoạt tài khoản, gửi email...

        $pdo->commit();
    } catch (Exception $e) {
        $pdo->rollBack();
        error_log('SePay webhook error: ' . $e->getMessage());
    }

    return json_encode(['success' => true]);
}
```

### 3.6. Data format SePay gửi về webhook

```json
{
    "id": 12345,
    "gateway": "MBBank",
    "transactionDate": "2026-07-10 23:30:00",
    "accountNumber": "0346800098",
    "subAccount": null,
    "transferType": "in",
    "transferAmount": 50000,
    "accumulated": 1500000,
    "code": "GDS2001234",
    "content": "GDS2001234",
    "referenceCode": "FT26192xxxxx",
    "description": "DAO LUU TRONG LUAN chuyen tien GDS2001234"
}
```

**Các trường quan trọng:**

| Trường | Mô tả |
|---|---|
| `transferType` | `"in"` = tiền vào, `"out"` = tiền ra |
| `transferAmount` | Số tiền giao dịch (VND, integer) |
| `content` | Nội dung chuyển khoản (chứa mã thanh toán) |
| `code` | Mã giao dịch SePay tự parse |
| `referenceCode` | Mã tham chiếu từ ngân hàng |
| `accountNumber` | Số tài khoản nhận |

---

## 4. Cấu hình Frontend

### 4.1. Hiển thị QR + thông tin CK

Khi API trả về response, frontend cần hiển thị:

```javascript
// Sau khi gọi API tạo payment
const data = await api.createPayment({ ... });

// Hiển thị QR code (URL ảnh từ VietQR)
const qrImg = document.createElement('img');
qrImg.src = data.qr_code;
qrImg.alt = 'QR Code thanh toán';
qrImg.style.maxWidth = '260px';

// Hiển thị thông tin chuyển khoản
const info = `
  Ngân hàng: ${data.bank_name}
  Số tài khoản: ${data.bank_account}
  Chủ tài khoản: ${data.account_name}
  Số tiền: ${data.amount.toLocaleString('vi-VN')}đ
  Nội dung CK: ${data.payment_code}  ← BẮT BUỘC GHI ĐÚNG
`;
```

### 4.2. Polling kiểm tra trạng thái

Sau khi hiện QR, frontend poll API mỗi 2-3 giây để kiểm tra payment đã được thanh toán chưa:

```javascript
const pollInterval = setInterval(async () => {
    const payment = await api.getPaymentStatus(paymentId);
    if (payment.status === 'paid') {
        clearInterval(pollInterval);
        showSuccessMessage();
    }
}, 2500);

// Timeout sau 15 phút
setTimeout(() => {
    clearInterval(pollInterval);
    showExpiredMessage();
}, 15 * 60 * 1000);
```

---

## 5. Checklist triển khai

```
□ 1. Đăng ký SePay (my.sepay.vn)
□ 2. Liên kết tài khoản ngân hàng
□ 3. Lấy API Token (Cấu hình Công ty → API Access)
□ 4. Tạo Webhook trên SePay Dashboard:
     □ URL đúng endpoint backend
     □ Chọn đúng tài khoản ngân hàng
     □ BẬT "Dùng để xác thực thanh toán"
     □ Bảo mật: chọn API Key
     □ BẬT cảnh báo khi webhook lỗi
□ 5. Cấu hình backend:
     □ Định nghĩa constants (API Token, Bank info, Prefix, Offset)
     □ Tạo route cho webhook endpoint
     □ Implement webhook handler
     □ Implement tạo QR + payment
□ 6. Cấu hình frontend:
     □ Hiển thị QR + thông tin CK
     □ Polling kiểm tra trạng thái
     □ Countdown timer (15 phút)
     □ Nút huỷ giao dịch
□ 7. Test end-to-end:
     □ Tạo payment → hiện QR
     □ Chuyển khoản thật (số tiền nhỏ)
     □ Webhook nhận được → payment cập nhật
     □ Frontend phát hiện → hiện thành công
```

---

## 6. Troubleshooting

### Webhook không nhận được
- Kiểm tra URL webhook trên SePay có đúng không (copy paste thử vào trình duyệt, phải trả về JSON)
- Kiểm tra server có chặn POST từ IP lạ không (firewall, .htaccess)
- Kiểm tra SSL certificate có hợp lệ không (SePay yêu cầu HTTPS)

### Webhook nhận được nhưng không xử lý
- Kiểm tra `error_log` trên server
- Kiểm tra API Token có khớp giữa SePay Dashboard và config không
- Kiểm tra `transferType` có phải `"in"` không
- Kiểm tra nội dung CK có chứa đúng PREFIX + orderCode không

### Khách chuyển tiền nhưng không cộng
- Kiểm tra khách có ghi đúng nội dung CK không
- Kiểm tra số tiền chuyển có đủ không (code so sánh `transferAmount >= payment.amount`)
- Kiểm tra payment có đang ở trạng thái `pending` không

### QR không hiển thị
- Kiểm tra URL VietQR có đúng format không
- Kiểm tra mã ngân hàng có đúng không (xem bảng 3.2)
- Thử mở URL QR trực tiếp trên trình duyệt

---

## 7. Lưu ý bảo mật

1. **KHÔNG BAO GIỜ** expose API Token ra frontend (chỉ dùng ở backend)
2. **LUÔN** verify API Token trong webhook handler trước khi xử lý
3. **LUÔN** kiểm tra `transferAmount >= payment.amount` để tránh thanh toán thiếu
4. **LUÔN** kiểm tra idempotency (payment đã paid thì bỏ qua) để tránh xử lý trùng
5. **LUÔN** dùng database transaction khi cập nhật payment + nghiệp vụ
6. **LUÔN** log lại mọi webhook request để debug khi cần

---

## 8. Thông tin tham khảo

- **SePay Dashboard:** https://my.sepay.vn
- **SePay API Docs:** https://docs.sepay.vn
- **VietQR API:** https://vietqr.io (miễn phí, không cần đăng ký)
- **VietQR Bank List:** https://api.vietqr.io/v2/banks
- **VietQR Image Format:** `https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-{TEMPLATE}.jpg?amount={AMOUNT}&addInfo={CONTENT}&accountName={NAME}`
