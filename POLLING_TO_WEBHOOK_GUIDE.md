# 🔄 Hướng Dẫn Chuyển Polling → Webhook

> **Dùng cho:** Telegram Bot Python (`python-telegram-bot` >= 20.0) deploy trên Render.com
> **Tại sao:** Polling tốn usage 24/7 → hết free tier nhanh. Webhook gần như 0 usage.

---

## 📊 So Sánh

| | Polling | Webhook |
|---|---------|---------|
| Cách hoạt động | Bot liên tục hỏi Telegram "có tin nhắn mới?" | Telegram gửi đến bot khi có tin nhắn |
| Usage trên Render | Rất cao (chạy 24/7) | Gần 0 khi không dùng |
| Cold start | Không | ~20-30s lần đầu sau khi idle |
| Cần Flask | ✅ Phải chạy riêng | ❌ Không cần |
| Cần UptimeRobot | ✅ Giữ bot alive | ❌ Không cần |
| Cần self-ping | ✅ Giữ bot alive | ❌ Không cần |

---

## 🛠 4 Bước Chuyển Đổi

### Bước 1: Sửa `requirements.txt`

```diff
- python-telegram-bot>=20.0
+ python-telegram-bot[webhooks]>=20.0

- flask>=3.0.0
# (xóa flask, không cần nữa)
```

> `[webhooks]` sẽ cài thêm package `tornado` làm web server, thay thế Flask.

---

### Bước 2: Xóa code cũ trong `bot.py`

**Xóa các import không cần:**
```diff
- import threading
- from flask import Flask
```

**Xóa toàn bộ Flask app:**
```diff
- app = Flask(__name__)
- 
- @app.route('/')
- def home():
-     return Response("Bot is running!", ...)
- 
- @app.route('/health')
- def health():
-     return Response("OK", ...)
- 
- @app.route('/ping')
- def ping():
-     return Response("pong", ...)
- 
- def run_flask():
-     port = int(os.getenv('PORT', 10000))
-     app.run(host='0.0.0.0', port=port, threaded=True)
```

**Xóa self-ping (nếu có):**
```diff
- def self_ping():
-     ...
```

**Xóa Flask/ping threads trong main():**
```diff
- flask_thread = threading.Thread(target=run_flask, daemon=True)
- flask_thread.start()
- 
- ping_thread = threading.Thread(target=self_ping, daemon=True)
- ping_thread.start()
```

---

### Bước 3: Thay `run_polling()` bằng code webhook

**Tìm đoạn này ở cuối `bot.py`:**
```python
application.run_polling(
    allowed_updates=Update.ALL_TYPES,
    drop_pending_updates=True
)
```

**Thay bằng:**
```python
import os

# Lấy URL webhook từ env
webhook_url = os.getenv('RENDER_EXTERNAL_URL', '')
port = int(os.getenv('PORT', 10000))

if webhook_url:
    # ===== PRODUCTION: Webhook mode =====
    logger.info(f"🌐 Webhook mode: {webhook_url}")
    application.run_webhook(
        listen='0.0.0.0',
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{webhook_url}/{BOT_TOKEN}",
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )
else:
    # ===== LOCAL: Polling mode =====
    logger.info("🔄 Polling mode (local development)")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
```

> **Giải thích:**
> - Có `RENDER_EXTERNAL_URL` → chạy webhook (production)
> - Không có → chạy polling (local dev bình thường)
> - `url_path=BOT_TOKEN` → bảo mật, chỉ Telegram biết URL webhook

---

### Bước 4: Thêm Environment Variable trên Render

Vào **Render Dashboard** → Service → **Environment** → thêm:

| Key | Value |
|-----|-------|
| `RENDER_EXTERNAL_URL` | `https://ten-service-cua-ban.onrender.com` |

> ⚠️ Không có `/` ở cuối URL!

---

## ✅ Checklist Sau Khi Chuyển

- [ ] `requirements.txt` có `python-telegram-bot[webhooks]`, không có `flask`
- [ ] Đã xóa Flask app, routes, `run_flask()`, `self_ping()`, `threading`
- [ ] Đã thay `run_polling()` bằng code webhook
- [ ] Đã thêm `RENDER_EXTERNAL_URL` trên Render
- [ ] Đã tắt UptimeRobot monitor (không cần nữa)
- [ ] Test local bình thường (vẫn dùng polling)
- [ ] Push → Render deploy thành công
- [ ] Bot phản hồi trên Telegram

---

## ❓ FAQ

**Q: Bot chậm lần đầu (~30s)?**
A: Bình thường! Render free tier cần thời gian cold start. Các lần sau sẽ nhanh.

**Q: Test local có bị ảnh hưởng không?**
A: Không! Khi không có `RENDER_EXTERNAL_URL`, bot tự động dùng polling.

**Q: Còn cần UptimeRobot không?**
A: Không cần nữa. Webhook không cần giữ bot alive.

**Q: Nếu muốn quay lại polling?**
A: Đổi lại `python-telegram-bot` (bỏ `[webhooks]`), xóa code webhook, thêm lại `run_polling()`.

---

*Tạo bởi: Antigravity AI Assistant*
*Ngày: 2026-02-15*
