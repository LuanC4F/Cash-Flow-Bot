# 🚀 CashFlow Bot - Hướng Dẫn Setup Phản Hồi Tức Thì

> Bot phản hồi **ngay lập tức** mỗi khi nhắn tin, không cần chờ cold start.

---

## 📋 Tổng Quan Kiến Trúc

```
Telegram ──webhook──> Render (Web Service)
                         │
                         ├── Bot xử lý tin nhắn
                         ├── Self-ping mỗi 5 phút (giữ alive)
                         └── Đọc/ghi Google Sheets

Cron-job.org ──ping──> Render (backup đánh thức)
```

**3 lớp bảo vệ giữ bot luôn online:**
1. **Webhook mode** - không polling, tiết kiệm usage
2. **Self-ping** - bot tự ping mình mỗi 5 phút, giữ Render không ngủ
3. **Cron-job.org** - backup bên ngoài, đánh thức bot nếu crash/restart

---

## 🛠 Bước 1: Tạo Render Web Service

1. Vào [render.com](https://render.com) → **New** → **Web Service**
2. Connect GitHub repo chứa code bot
3. Cấu hình:

| Setting | Giá trị |
|---------|---------|
| **Name** | `cash-flow-bot` (hoặc tên tùy ý) |
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py` |
| **Plan** | Free |

---

## 🔑 Bước 2: Cấu Hình Environment Variables

Vào **Render Dashboard** → Service → **Environment** → thêm từng biến:

| # | Key | Value | Cách lấy |
|---|-----|-------|----------|
| 1 | `BOT_TOKEN` | `8080122217:AAEJ...` | Lấy từ [@BotFather](https://t.me/BotFather) trên Telegram |
| 2 | `SHEET_ID` | `1MTOsja9pL5H0HpT_...` | Lấy từ URL Google Sheet (giữa `/d/` và `/edit`) |
| 3 | `ALLOWED_USER_ID` | `6527154717` | Chat với [@userinfobot](https://t.me/userinfobot) để lấy ID |
| 4 | `RENDER_EXTERNAL_URL` | `https://cash-flow-bot.onrender.com` | URL service trên Render (không có `/` cuối) |
| 5 | `GOOGLE_CREDENTIALS` | `{"type":"service_account",...}` | Toàn bộ nội dung file `credentials.json` (1 dòng) |

### Cách lấy GOOGLE_CREDENTIALS:
```bash
# Mở file credentials.json, copy toàn bộ nội dung paste vào value
cat credentials.json
```
> ⚠️ Paste nguyên JSON 1 dòng, không xuống hàng!

### Cách lấy RENDER_EXTERNAL_URL:
- Deploy xong → Render hiển thị URL ở đầu trang (dạng `https://xxx.onrender.com`)
- Copy URL đó paste vào
- Nếu deploy lần đầu chưa có URL → deploy trước, thêm URL sau, rồi **Manual Deploy** lại

---

## 📊 Bước 3: Setup Google Sheets

### 3.1. Tạo Google Service Account
1. Vào [Google Cloud Console](https://console.cloud.google.com)
2. Tạo project → Enable **Google Sheets API** + **Google Drive API**
3. Tạo **Service Account** → tải file JSON key → đây là `credentials.json`

### 3.2. Tạo Google Sheet với 4 sheet tabs:

**Tab "Products":**
| SKU | Name | Cost |
|-----|------|------|

**Tab "Sales":**
| Date | SKU | Name | Price | Quantity | Cost | Profit | Customer | Note |
|------|-----|------|-------|----------|------|--------|----------|------|

**Tab "Expenses":**
| Date | Amount | Description | Category |
|------|--------|-------------|----------|

**Tab "Debts":**
| Date | Customer | Amount | Note | Status | PaidDate |
|------|----------|--------|------|--------|----------|

### 3.3. Share Sheet
- Copy email từ `credentials.json` (trường `client_email`)
- Mở Google Sheet → **Share** → paste email → quyền **Editor**

---

## ⏰ Bước 4: Setup Cron-job.org (Backup Keep-Alive)

1. Vào [cron-job.org](https://cron-job.org) → đăng ký miễn phí
2. **Create Cronjob:**

| Setting | Giá trị |
|---------|---------|
| **Title** | `CashFlow Bot Ping` |
| **URL** | `https://cash-flow-bot.onrender.com/` |
| **Schedule** | Every **5 minutes** |
| **Request Method** | GET |
| **Request Timeout** | 60 seconds |

3. **Notifications** → TẮT hết (vì sẽ trả 404, không phải lỗi thật)
   - ❌ execution of the cronjob fails → **TẮT**
   - ❌ the cronjob will be disabled because of too many failures → **TẮT**

4. **Save** → Done!

---

## ✅ Bước 5: Verify

1. Đợi Render deploy xong (2-3 phút)
2. Kiểm tra **Render Logs** thấy:
   ```
   🌐 Webhook mode: https://cash-flow-bot.onrender.com
   🔄 Self-ping started (every 5 min)
   🚀 CashFlow Bot đang khởi động...
   ```
3. Gửi `/start` trên Telegram → Bot phản hồi ngay
4. Đợi 15 phút → gửi `/start` lại → Vẫn phản hồi ngay (self-ping giữ alive)

---

## 🔧 Troubleshooting

### Bot không phản hồi sau deploy:
- Đợi 2-3 phút cho deploy xong
- Kiểm tra Render Logs có lỗi không
- Thử mở `https://your-bot.onrender.com/` trên browser (sẽ thấy 404 = service đang chạy)

### Bot phản hồi chậm lần đầu:
- Bình thường nếu vừa deploy hoặc service restart
- Sau lần đầu, self-ping sẽ giữ bot alive → phản hồi tức thì

### Lỗi "the header row contains duplicates":
- Mở Google Sheet → kiểm tra có cột trống sau cột cuối không → xóa đi
- Code đã có `safe_get_records()` tự xử lý, nhưng nên giữ sheet sạch

### Lỗi "Có lỗi xảy ra" khi xem chi tiêu:
- Do mô tả chứa ký tự đặc biệt (`_`, `*`, `` ` ``)
- Code đã có `safe_edit()` tự fallback, không cần lo

### Kiểm tra webhook:
```
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```
- `url` không rỗng = webhook đang hoạt động
- `last_error_message` = xem lỗi gần nhất

### Reset webhook thủ công:
```
https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook
```
Sau đó **Manual Deploy** lại trên Render.

---

## 📁 Cấu Trúc Files Quan Trọng

```
QuanLyThuChi_Bot/
├── bot.py                  # Entry point - webhook + self-ping
├── config.py               # Load env variables
├── requirements.txt        # python-telegram-bot[webhooks]
├── credentials.json        # Google API key (KHÔNG push lên git!)
├── .env                    # Local env (KHÔNG push lên git!)
├── .gitignore              # Bỏ qua .env, credentials.json
├── handlers/
│   ├── basic.py            # Menu, navigation, safe_edit()
│   ├── product.py          # CRUD sản phẩm
│   ├── sales.py            # Bán hàng
│   ├── expense.py          # Chi tiêu
│   └── debt.py             # Quản lý nợ
├── services/
│   └── sheets.py           # Google Sheets API, safe_get_records()
└── utils/
    ├── formatting.py       # Format tiền, emoji
    └── security.py         # Kiểm tra quyền user
```

---

## 📝 requirements.txt

```txt
python-telegram-bot[webhooks]>=20.0
python-dotenv>=1.0.0
gspread>=5.0.0
google-auth>=2.0.0
```

> ⚠️ `[webhooks]` bắt buộc! Không có sẽ lỗi khi chạy webhook mode.
> ❌ KHÔNG cần `flask` - webhook tự có web server.

---

## 🔄 Khi Cần Update Code

```bash
git add .
git commit -m "mô tả thay đổi"
git push
```
Render tự động deploy khi push. Bot sẽ offline ~2 phút trong lúc deploy.

---

*Tạo bởi: Antigravity AI Assistant*
*Ngày: 2026-03-02*
