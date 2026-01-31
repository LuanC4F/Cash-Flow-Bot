# 💰 CashFlow Bot - Telegram

Telegram bot for expense tracking and sales profit calculation with Google Sheets.

## ✨ Features

### 💸 Expenses
- Record expenses with categories (Living, Personal, Work, Food, etc.)
- View daily/monthly expenses
- Statistics by category

### 📦 Products
- Manage product list with cost price
- Add / update / delete products

### 🛒 Sales & Profit
- Record sales with customer info
- Auto-calculate profit from cost
- Monthly profit reports

### 📊 Statistics
- Daily summary (income/expenses)
- Monthly summary
- Profit reports

## 📁 Project Structure

```
QuanLyThuChi_Bot/
├── bot.py                  # 🚪 Entry point
├── config.py               # ⚙️ Configuration
├── credentials.json        # 🔑 Google Service Account (don't commit!)
├── .env                    # 🔐 Environment variables (don't commit!)
│
├── services/               # 🔌 External services
│   └── sheets.py           # Google Sheets operations
│
├── handlers/               # 🎮 Command handlers
│   ├── basic.py            # /start, /help
│   ├── product.py          # /sanpham, /themsp, /suasp, /xoasp
│   ├── sales.py            # /ban, /dsbh, /laithang, /xoabh
│   └── expense.py          # /chi, /chitieu, /homnay, /thang
│
└── utils/                  # 🧰 Utilities
    └── formatting.py       # Currency format, input parsing
```

## 🔧 Installation

### 1. Install dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup Google Sheets

Create a new Google Sheet with 3 sheets:

**Sheet 1: Products**
| SKU | Name | Cost |
|-----|------|------|
| SP01 | Áo thun | 150000 |

**Sheet 2: Sales**
| Date | SKU | Qty | Price | Cost | Profit | Customer | Note |
|------|-----|-----|-------|------|--------|----------|------|

**Sheet 3: Expenses**
| Date | Amount | Description | Category |
|------|--------|-------------|----------|

### 3. Configure `.env`

```env
BOT_TOKEN=your_telegram_bot_token
SHEET_ID=your_google_sheet_id
SHEET_PRODUCTS=Products
SHEET_SALES=Sales
SHEET_EXPENSES=Expenses
```

### 4. Run bot

```bash
source venv/bin/activate
python bot.py
```

## 📖 Usage Guide

### 💸 Expenses

| Command | Description | Example |
|---------|-------------|---------|
| `/chi` | Record expense | `/chi 50k Lunch` |
| `/chitieu` | View today's expenses | `/chitieu` |
| `/xoachi` | Delete expense | `/xoachi 5` |

**Categories:** Living (default), Personal, Work, Food, Transport, Health, Entertainment

### 📦 Products

| Command | Description | Example |
|---------|-------------|---------|
| `/sanpham` | View product list | `/sanpham` |
| `/themsp` | Add product | `/themsp SP01 T-shirt 150k` |
| `/suasp` | Update cost | `/suasp SP01 200k` |
| `/xoasp` | Delete product | `/xoasp SP01` |

### 🛒 Sales

| Command | Description | Example |
|---------|-------------|---------|
| `/ban` | Record sale | `/ban SP01 250k 2 John` |
| `/dsbh` | Sales history | `/dsbh` |
| `/laithang` | Monthly profit | `/laithang` |
| `/xoabh` | Delete sale | `/xoabh 5` |

### 📊 Statistics

| Command | Description |
|---------|-------------|
| `/homnay` | Today's summary |
| `/thang` | Monthly summary |

### 💡 Amount Formatting

| Format | Result |
|--------|--------|
| `50k` | 50,000đ |
| `1m` or `1tr` | 1,000,000đ |
| `1.5m` | 1,500,000đ |

## 📊 Google Sheet Structure

### Products
| SKU | Name | Cost |
|-----|------|------|
| SP01 | T-shirt | 150000 |

### Sales
| Date | SKU | Qty | Price | Cost | Profit | Customer | Note |
|------|-----|-----|-------|------|--------|----------|------|
| 31/01/2026 | SP01 | 2 | 250000 | 150000 | 200000 | John | |

### Expenses
| Date | Amount | Description | Category |
|------|--------|-------------|----------|
| 31/01/2026 | 50000 | Lunch | Food |

## 📝 License

MIT License
