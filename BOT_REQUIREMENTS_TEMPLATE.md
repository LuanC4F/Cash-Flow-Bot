# 📋 TELEGRAM BOT - YÊU CẦU & QUY TẮC PHÁT TRIỂN

> **Owner:** Luân (LuanC4F)  
> **Mục đích:** Template này dùng để tạo Telegram Bot mới đúng ý chủ sở hữu ngay từ đầu.

---

## 🎯 1. YÊU CẦU CHUNG

### 1.1. Công nghệ & Stack
- **Ngôn ngữ:** Python 3.10+
- **Framework Bot:** `python-telegram-bot` >= 20.0
- **Database:** Google Sheets (qua `gspread` + `google-auth`)
- **Web Server:** Flask (cho health check khi deploy)
- **Environment:** `python-dotenv` để load `.env`
- **Deploy:** Render.com (Web Service)

### 1.2. Cấu trúc thư mục chuẩn
```
project/
├── bot.py              # Entry point chính
├── config.py           # Load environment variables
├── requirements.txt    # Dependencies
├── .env                # Secrets (KHÔNG push lên git)
├── .env.example        # Template cho .env
├── .gitignore          # Bảo vệ files nhạy cảm
├── credentials.json    # Google Service Account (KHÔNG push)
├── README.md           # Hướng dẫn sử dụng
├── handlers/           # Xử lý commands & callbacks
│   ├── __init__.py
│   ├── basic.py        # /start, /help, menu chính
│   └── [module].py     # Các module khác
├── services/           # Business logic (sheets, API, etc.)
│   ├── __init__.py
│   └── sheets.py       # Google Sheets operations
└── utils/              # Utilities
    ├── __init__.py
    ├── formatting.py   # Format currency, parse amount
    └── security.py     # Permission check
```

---

## 🔐 2. BẢO MẬT

### 2.1. Giới hạn quyền truy cập
- **CHỈ CHO PHÉP 1 USER** (chủ bot) sử dụng
- Sử dụng `ALLOWED_USER_ID` trong `.env`
- Tạo file `utils/security.py` với:
  ```python
  def check_permission(user_id: int) -> bool:
      import config
      if not config.ALLOWED_USER_ID:
          return True  # Không cấu hình = cho phép tất cả
      return user_id == config.ALLOWED_USER_ID
  
  UNAUTHORIZED_MESSAGE = "🚫 Bạn không có quyền sử dụng bot này."
  ```
- **Mọi handler** phải kiểm tra quyền ở đầu function

### 2.2. Files .gitignore BẮT BUỘC
```gitignore
.env
credentials.json
__pycache__/
*.py[cod]
venv/
.vscode/
.DS_Store
```

### 2.3. .env.example (template cho user)
```env
# Telegram Bot Token (lấy từ @BotFather)
BOT_TOKEN=your_bot_token_here

# Google Sheet ID
SHEET_ID=your_sheet_id_here

# Telegram User ID được phép dùng bot (lấy từ @userinfobot)
ALLOWED_USER_ID=123456789
```

---

## 🖥️ 3. GIAO DIỆN & UX

### 3.1. Inline Keyboard Buttons
- **Tối đa 2 buttons/hàng** để không bị cắt chữ trên Desktop
- Text button nên **ngắn gọn nhưng đầy đủ ý nghĩa**
- Luôn có button **"🔙 Menu"** để quay lại

### 3.2. Conversation Flow
- Hiển thị **bước hiện tại** rõ ràng: `Bước 1/5`, `Bước 2/5`...
- Mỗi bước có button **"⏭ Bỏ qua"** nếu optional
- Luôn có button **"❌ Hủy"** để thoát conversation

### 3.3. Emoji chuẩn
| Ý nghĩa | Emoji |
|---------|-------|
| Thành công | ✅ |
| Lỗi | ❌ |
| Cảnh báo | ⚠️ |
| Lợi nhuận dương | 📈 |
| Lợi nhuận âm | 📉 |
| Menu/Back | 🔙 |
| Tiền | 💰 💵 |
| Sản phẩm | 🏷 📦 |
| Bán hàng | 🛒 |
| Chi tiêu | 💸 |
| Người dùng | 👤 |
| Ngày | 📅 📆 |
| Ghi chú | 📝 |

### 3.4. Format tiền tệ
- Hiển thị: `115.000đ` (có dấu chấm phân cách nghìn)
- Nhập liệu: Hỗ trợ `115k`, `115000`, `115.000`
- Function `parse_amount()` xử lý tất cả format

---

## 🔄 4. LOGIC NGHIỆP VỤ

### 4.1. Bán hàng
- **Giá bán = TỔNG TIỀN THU** (không phải giá/sản phẩm)
- **Lợi nhuận = Tổng thu - (Giá gốc × Số lượng)**
- Flow: Chọn SP → Tổng thu → Số lượng → Người mua → Ghi chú

### 4.2. Data types từ Google Sheets
- **LUÔN convert sang đúng type** trước khi xử lý:
  ```python
  profit = float(s['profit']) if s['profit'] else 0
  quantity = int(s['quantity']) if s['quantity'] else 1
  ```
- Google Sheets trả về string, không phải number!

---

## 🌐 5. DEPLOY TRÊN RENDER

### 5.1. Cấu hình cần thiết
- **Service Type:** Web Service
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python bot.py`
- **Environment Variables:**
  - `BOT_TOKEN`
  - `SHEET_ID`
  - `ALLOWED_USER_ID`
  - `GOOGLE_CREDENTIALS` (JSON string của credentials.json)

### 5.2. Web Server cho Health Check
```python
from flask import Flask, Response
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return Response("Bot is running!", status=200, mimetype='text/plain')

@app.route('/health')
def health():
    return Response("OK", status=200, mimetype='text/plain')

def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

# Chạy Flask trong thread riêng trước khi chạy bot
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
```

### 5.3. Google Credentials từ ENV
```python
def get_client():
    google_creds_json = os.getenv('GOOGLE_CREDENTIALS')
    
    if google_creds_json:
        # Cloud: đọc từ env
        creds_dict = json.loads(google_creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        # Local: đọc từ file
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
```

### 5.4. Xử lý lỗi Conflict
```python
async def error_handler(update, context):
    error_msg = str(context.error)
    
    # Bỏ qua lỗi Conflict (bot instance khác đang chạy)
    if "Conflict" in error_msg and "terminated by other" in error_msg:
        return
    
    # Bỏ qua lỗi network tạm thời
    if "NetworkError" in error_msg or "TimedOut" in error_msg:
        return
    
    # Log và xử lý các lỗi khác
    logger.error(f"Error: {context.error}")
```

### 5.5. Drop Pending Updates khi khởi động
```python
application.run_polling(
    allowed_updates=Update.ALL_TYPES,
    drop_pending_updates=True  # Xóa lệnh cũ trong queue
)
```

### 5.6. UptimeRobot
- Tạo monitor HTTP(s) ping đến `/health` mỗi 5 phút
- Giữ cho Render không spin-down

---

## 📊 6. GOOGLE SHEETS SETUP

### 6.1. Tạo Service Account
1. Vào [Google Cloud Console](https://console.cloud.google.com)
2. Tạo project mới
3. Enable **Google Sheets API** và **Google Drive API**
4. Tạo Service Account → Download JSON key

### 6.2. Share Sheet với Service Account
- Copy email từ credentials.json (dạng `xxx@xxx.iam.gserviceaccount.com`)
- Share Google Sheet với email đó (Editor permission)

### 6.3. Cấu trúc Sheet chuẩn

**Sheet "Products":**
| SKU | Name | Cost |
|-----|------|------|

**Sheet "Sales":**
| Date | SKU | Qty | Price | Cost | Profit | Customer | Note |
|------|-----|-----|-------|------|--------|----------|------|

**Sheet "Expenses":**
| Date | Amount | Description | Category |
|------|--------|-------------|----------|

---

## 🔧 7. COMMANDS CHUẨN

### 7.1. Đăng ký với BotFather
```
start - Mở menu chính
help - Xem hướng dẫn
ban - Ghi bán hàng
dsbh - Xem lịch sử bán
laithang - Xem lợi nhuận tháng
chi - Ghi chi tiêu
chitieu - Xem chi tiêu hôm nay
homnay - Tổng hợp hôm nay
thang - Tổng hợp tháng
sanpham - Quản lý sản phẩm
themsp - Thêm sản phẩm mới
suasp - Sửa giá sản phẩm
xoasp - Xóa sản phẩm
xoabh - Xóa giao dịch bán
xoachi - Xóa chi tiêu
cancel - Hủy thao tác
```

---

## 📱 8. GIT & GITHUB

### 8.1. Dùng SSH thay vì HTTPS
```bash
git remote add origin git@github.com:LuanC4F/repo-name.git
```

### 8.2. Commit message chuẩn
- `Initial commit: [Tên bot] with Google Sheets integration`
- `Add [feature name]`
- `Fix [bug description]`
- `Update [component] for [reason]`

---

## ⚠️ 9. LƯU Ý QUAN TRỌNG

1. **Không bao giờ** push `.env` hoặc `credentials.json` lên GitHub
2. **Luôn test local** trước khi push lên Render
3. **Dừng bot local** khi test trên Render (tránh Conflict)
4. **Convert data types** từ Google Sheets trước khi so sánh
5. **2 buttons/hàng** cho Inline Keyboard để không bị cắt chữ
6. **Drop pending updates** khi bot khởi động lại
7. **Health check endpoint** bắt buộc cho Render

---

## 🚀 10. CHECKLIST TRƯỚC KHI DEPLOY

- [ ] `.gitignore` có `.env` và `credentials.json`
- [ ] `.env.example` đã tạo với template
- [ ] `requirements.txt` đầy đủ dependencies
- [ ] Flask health check endpoint đã thêm
- [ ] `GOOGLE_CREDENTIALS` env đã cấu hình trên Render
- [ ] Security check trong tất cả handlers
- [ ] `drop_pending_updates=True` trong run_polling
- [ ] Error handler xử lý Conflict
- [ ] UptimeRobot đã cấu hình

---

**Tạo bởi:** Antigravity AI Assistant  
**Ngày:** 2026-02-01  
**Version:** 1.0
