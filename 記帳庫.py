# 步驟1: 建立資料庫 (database_setup.py)
import sqlite3
from datetime import datetime


def create_database():
    """建立記帳系統資料庫"""

    # 連接資料庫（如果不存在會自動建立）
    conn = sqlite3.connect('receipts.db')
    cursor = conn.cursor()

    print("🗄️ 正在建立資料庫...")

    # 建立公司基本資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tax_id TEXT,
            address TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 建立分類表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            keywords TEXT,
            tax_deductible BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 建立發票記錄表（主要的表）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_path TEXT,
            invoice_number TEXT,
            date TEXT,
            merchant TEXT,
            amount REAL DEFAULT 0,
            tax_amount REAL DEFAULT 0,
            category TEXT DEFAULT '雜費',
            description TEXT,
            is_business BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    print("✅ 資料表建立完成！")

    # 插入預設分類
    categories = [
        ('餐費', '餐廳,小吃,咖啡,便當,火鍋,燒烤,飲料', True),
        ('交通', '加油,停車,高鐵,計程車,捷運,公車,機票', True),
        ('辦公用品', '文具,紙張,印表機,電腦,筆,資料夾', True),
        ('軟體服務', '訂閱,SaaS,Office,Adobe,Google,AWS', True),
        ('設備', '電腦,螢幕,鍵盤,滑鼠,椅子,桌子', True),
        ('雜費', '水電,電話,網路,清潔,維修', True)
    ]

    for name, keywords, tax_deductible in categories:
        cursor.execute('''
            INSERT OR IGNORE INTO categories (name, keywords, tax_deductible)
            VALUES (?, ?, ?)
        ''', (name, keywords, tax_deductible))

    print("✅ 預設分類建立完成！")

    # 插入公司資料（如果沒有的話）
    cursor.execute('SELECT COUNT(*) FROM company')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO company (name, tax_id, address)
            VALUES (?, ?, ?)
        ''', ('我的公司', '12345678', '台北市'))
        print("✅ 公司基本資料建立完成！")

    # 提交變更並關閉連接
    conn.commit()
    conn.close()

    print("🎉 資料庫建立完成！檔案名稱: receipts.db")


def show_database_info():
    """顯示資料庫內容"""
    conn = sqlite3.connect('receipts.db')
    cursor = conn.cursor()

    print("\n📊 資料庫內容:")
    print("=" * 50)

    # 顯示所有表格
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("📋 資料表:")
    for table in tables:
        print(f"  - {table[0]}")

    # 顯示分類
    cursor.execute("SELECT name, keywords FROM categories")
    categories = cursor.fetchall()
    print("\n🏷️ 預設分類:")
    for cat in categories:
        print(f"  - {cat[0]}: {cat[1]}")

    # 顯示公司資料
    cursor.execute("SELECT name, tax_id FROM company")
    company = cursor.fetchone()
    if company:
        print(f"\n🏢 公司資料: {company[0]} (統編: {company[1]})")

    # 顯示發票數量
    cursor.execute("SELECT COUNT(*) FROM receipts")
    receipt_count = cursor.fetchone()[0]
    print(f"\n📄 發票記錄: {receipt_count} 筆")

    conn.close()


def add_test_data():
    """新增測試資料"""
    conn = sqlite3.connect('receipts.db')
    cursor = conn.cursor()

    test_receipts = [
        ('AB12345678', '2024-12-15', '星巴克咖啡', 150, 7, '餐費', '早餐會議'),
        ('CD87654321', '2024-12-14', '台灣高鐵', 1490, 71, '交通', '台北到台中出差'),
        ('EF11223344', '2024-12-13', '全家便利商店', 89, 4, '辦公用品', '買文具'),
    ]

    for receipt in test_receipts:
        cursor.execute('''
            INSERT INTO receipts 
            (invoice_number, date, merchant, amount, tax_amount, category, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', receipt)

    conn.commit()
    conn.close()
    print("✅ 測試資料新增完成！")


def view_all_receipts():
    """查看所有發票記錄"""
    conn = sqlite3.connect('receipts.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT date, merchant, amount, category, description 
        FROM receipts 
        ORDER BY date DESC
    ''')

    receipts = cursor.fetchall()

    print("\n📄 所有發票記錄:")
    print("=" * 80)
    print(f"{'日期':<12} {'商家':<20} {'金額':<8} {'分類':<10} {'說明'}")
    print("-" * 80)

    total = 0
    for receipt in receipts:
        date, merchant, amount, category, description = receipt
        print(f"{date:<12} {merchant:<20} ${amount:<7.0f} {category:<10} {description or ''}")
        total += amount

    print("-" * 80)
    print(f"總計: ${total:.0f}")

    conn.close()


# 主程式
if __name__ == "__main__":
    print("📱 記帳系統資料庫建立工具")
    print("=" * 50)

    # 建立資料庫
    create_database()

    # 顯示資料庫資訊
    show_database_info()

    # 詢問是否要新增測試資料
    add_test = input("\n❓ 要新增測試資料嗎？(y/n): ").lower().strip()
    if add_test == 'y':
        add_test_data()
        view_all_receipts()

    print("\n🎉 完成！你可以開始使用記帳系統了！")
    print("💡 下一步：執行主程式 main_old.py")