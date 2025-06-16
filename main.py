# main.py - 免費AI整合版本
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
import sqlite3
import uuid
import os
import re
from datetime import datetime
from typing import Dict, List
import tempfile
import base64
import json

# 免費OCR相關導入
import easyocr
from PIL import Image
import numpy as np

# 建立必要的資料夾
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = FastAPI(title="暴力記帳系統", description="拍照→辨識→記帳，就這麼簡單！")


# 資料庫初始化函式
def init_database():
    """初始化完整的小型公司記帳資料庫"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        print("🏗️ 建立小型公司記帳資料庫...")

        # 1. 公司基本資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tax_id TEXT UNIQUE,
                address TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                industry TEXT,
                founded_date TEXT,
                capital REAL DEFAULT 0,
                fiscal_year_start INTEGER DEFAULT 1,
                accounting_method TEXT DEFAULT 'accrual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. 員工管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                department TEXT,
                position TEXT,
                salary REAL DEFAULT 0,
                start_date TEXT,
                end_date TEXT,
                status TEXT DEFAULT 'active',
                expense_limit REAL DEFAULT 5000,
                can_approve BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. 部門/費用中心表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                manager_id INTEGER REFERENCES employees(id),
                budget_monthly REAL DEFAULT 0,
                budget_annual REAL DEFAULT 0,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. 專案管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                client_name TEXT,
                start_date TEXT,
                end_date TEXT,
                budget REAL DEFAULT 0,
                actual_cost REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                manager_id INTEGER REFERENCES employees(id),
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. 供應商管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                tax_id TEXT,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                payment_terms TEXT DEFAULT 'NET30',
                credit_limit REAL DEFAULT 0,
                bank_account TEXT,
                bank_name TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 6. 客戶管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                tax_id TEXT,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                payment_terms TEXT DEFAULT 'NET30',
                credit_limit REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 7. 會計科目表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chart_of_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_code TEXT UNIQUE NOT NULL,
                account_name TEXT NOT NULL,
                account_type TEXT NOT NULL,
                parent_code TEXT,
                level INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT 1,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 8. 分類表（支出分類）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                keywords TEXT,
                account_code TEXT REFERENCES chart_of_accounts(account_code),
                tax_deductible BOOLEAN DEFAULT 1,
                requires_receipt BOOLEAN DEFAULT 1,
                requires_approval BOOLEAN DEFAULT 0,
                approval_limit REAL DEFAULT 0,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 9. 發票記錄表（主要交易表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_type TEXT DEFAULT 'expense',
                photo_path TEXT,
                invoice_number TEXT,
                date TEXT NOT NULL,
                due_date TEXT,

                -- 商家/供應商資訊
                merchant TEXT,
                supplier_id INTEGER REFERENCES suppliers(id),
                supplier_tax_id TEXT,

                -- 金額資訊
                amount REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                tax_rate REAL DEFAULT 0.05,
                net_amount REAL DEFAULT 0,

                -- 分類和會計
                category TEXT DEFAULT '雜費',
                account_code TEXT REFERENCES chart_of_accounts(account_code),
                department_id INTEGER REFERENCES departments(id),
                project_id INTEGER REFERENCES projects(id),

                -- 審核狀態
                status TEXT DEFAULT 'pending',
                submitted_by INTEGER REFERENCES employees(id),
                approved_by INTEGER REFERENCES employees(id),
                approved_at TEXT,

                -- AI 和處理資訊
                description TEXT,
                notes TEXT,
                is_business BOOLEAN DEFAULT 1,
                is_recurring BOOLEAN DEFAULT 0,
                recurring_frequency TEXT,
                ocr_confidence REAL DEFAULT 0,

                -- 付款資訊
                payment_method TEXT,
                payment_status TEXT DEFAULT 'unpaid',
                paid_date TEXT,
                paid_amount REAL DEFAULT 0,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 10. 銀行帳戶表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                account_number TEXT,
                account_type TEXT DEFAULT 'checking',
                currency TEXT DEFAULT 'TWD',
                opening_balance REAL DEFAULT 0,
                current_balance REAL DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 11. 銀行交易記錄表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER REFERENCES bank_accounts(id),
                transaction_date TEXT NOT NULL,
                description TEXT,
                reference_number TEXT,
                debit_amount REAL DEFAULT 0,
                credit_amount REAL DEFAULT 0,
                balance REAL DEFAULT 0,
                category TEXT,
                receipt_id INTEGER REFERENCES receipts(id),
                reconciled BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 12. 預算管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_year INTEGER NOT NULL,
                budget_month INTEGER,
                department_id INTEGER REFERENCES departments(id),
                project_id INTEGER REFERENCES projects(id),
                category_id INTEGER REFERENCES categories(id),
                budgeted_amount REAL DEFAULT 0,
                actual_amount REAL DEFAULT 0,
                variance_amount REAL DEFAULT 0,
                variance_percentage REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 13. 報銷申請表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expense_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_number TEXT UNIQUE,
                employee_id INTEGER REFERENCES employees(id),
                claim_date TEXT NOT NULL,
                total_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'draft',
                submitted_date TEXT,
                approved_date TEXT,
                approved_by INTEGER REFERENCES employees(id),
                paid_date TEXT,
                purpose TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 14. 報銷明細表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expense_claim_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id INTEGER REFERENCES expense_claims(id),
                receipt_id INTEGER REFERENCES receipts(id),
                expense_date TEXT NOT NULL,
                description TEXT,
                amount REAL DEFAULT 0,
                category TEXT,
                billable_to_client BOOLEAN DEFAULT 0,
                client_id INTEGER REFERENCES customers(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 15. 發票開立表（銷項）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices_issued (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                customer_id INTEGER REFERENCES customers(id),
                invoice_date TEXT NOT NULL,
                due_date TEXT,
                subtotal REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                total_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'draft',
                paid_amount REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 16. 稅務記錄表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tax_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_year INTEGER NOT NULL,
                tax_quarter INTEGER,
                tax_type TEXT NOT NULL,
                taxable_amount REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                tax_rate REAL DEFAULT 0,
                status TEXT DEFAULT 'calculated',
                filed_date TEXT,
                paid_date TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        print("📋 建立資料表完成，開始插入預設資料...")

        # 檢查並添加缺失的欄位（向後相容）
        cursor.execute("PRAGMA table_info(receipts)")
        columns = [column[1] for column in cursor.fetchall()]

        missing_columns = [
            ('ocr_confidence', 'REAL DEFAULT 0'),
            ('department_id', 'INTEGER'),
            ('project_id', 'INTEGER'),
            ('supplier_id', 'INTEGER'),
            ('status', 'TEXT DEFAULT "pending"'),
            ('payment_status', 'TEXT DEFAULT "unpaid"')
        ]

        for column_name, column_def in missing_columns:
            if column_name not in columns:
                cursor.execute(f'ALTER TABLE receipts ADD COLUMN {column_name} {column_def}')
                print(f"✅ 添加 {column_name} 欄位")

        # 插入預設會計科目
        cursor.execute('SELECT COUNT(*) FROM chart_of_accounts')
        if cursor.fetchone()[0] == 0:
            accounts = [
                # 資產類
                ('1000', '流動資產', 'Assets', None, 1),
                ('1100', '現金及約當現金', 'Assets', '1000', 2),
                ('1110', '庫存現金', 'Assets', '1100', 3),
                ('1120', '銀行存款', 'Assets', '1100', 3),
                ('1200', '應收帳款', 'Assets', '1000', 2),
                ('1300', '存貨', 'Assets', '1000', 2),
                ('1500', '固定資產', 'Assets', None, 1),
                ('1510', '設備', 'Assets', '1500', 2),
                ('1520', '累計折舊', 'Assets', '1500', 2),

                # 負債類
                ('2000', '流動負債', 'Liabilities', None, 1),
                ('2100', '應付帳款', 'Liabilities', '2000', 2),
                ('2200', '應付薪資', 'Liabilities', '2000', 2),
                ('2300', '應付稅款', 'Liabilities', '2000', 2),

                # 權益類
                ('3000', '業主權益', 'Equity', None, 1),
                ('3100', '股本', 'Equity', '3000', 2),
                ('3200', '保留盈餘', 'Equity', '3000', 2),

                # 收入類
                ('4000', '營業收入', 'Revenue', None, 1),
                ('4100', '銷貨收入', 'Revenue', '4000', 2),
                ('4200', '服務收入', 'Revenue', '4000', 2),

                # 費用類
                ('5000', '營業費用', 'Expenses', None, 1),
                ('5100', '銷貨成本', 'Expenses', '5000', 2),
                ('5200', '薪資費用', 'Expenses', '5000', 2),
                ('5300', '租金費用', 'Expenses', '5000', 2),
                ('5400', '辦公費用', 'Expenses', '5000', 2),
                ('5500', '差旅費', 'Expenses', '5000', 2),
                ('5600', '餐費', 'Expenses', '5000', 2),
                ('5700', '交通費', 'Expenses', '5000', 2),
                ('5800', '軟體費用', 'Expenses', '5000', 2),
                ('5900', '雜項費用', 'Expenses', '5000', 2),
            ]

            for code, name, acc_type, parent, level in accounts:
                cursor.execute('''
                    INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_code, level)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, name, acc_type, parent, level))

            print("✅ 會計科目建立完成")

        # 插入預設分類（連結會計科目）
        cursor.execute('SELECT COUNT(*) FROM categories')
        if cursor.fetchone()[0] == 0:
            categories = [
                ('餐費', '餐廳,小吃,咖啡,便當,火鍋,燒烤,飲料,麥當勞,肯德基,星巴克,85度C', '5600', True, True, False,
                 1000),
                ('交通費', '加油,停車,高鐵,計程車,捷運,公車,機票,台鐵,客運,Uber', '5700', True, True, False, 1000),
                ('辦公用品', '文具,紙張,印表機,電腦,筆,資料夾,誠品,金石堂', '5400', True, True, False, 2000),
                ('軟體服務', '訂閱,SaaS,Office,Adobe,Google,AWS,Microsoft,Apple', '5800', True, True, True, 5000),
                ('設備採購', '電腦,螢幕,鍵盤,滑鼠,椅子,桌子,3C,燦坤,全國電子', '1510', True, True, True, 10000),
                ('購物', '百貨,量販,家樂福,全聯,好市多,大潤發,購物', '5900', True, True, False, 3000),
                ('醫療費用', '藥局,醫院,診所,健保,醫療,康是美,屈臣氏', '5900', True, True, False, 2000),
                ('娛樂費用', '電影,KTV,遊戲,娛樂,威秀,國賓', '5900', False, True, False, 1000),
                ('租金水電', '水電,電話,網路,房租,租金', '5300', True, True, False, 0),
                ('薪資費用', '薪水,薪資,獎金,勞保,健保', '5200', True, False, True, 0),
                ('差旅費用', '出差,住宿,飯店,旅館', '5500', True, True, True, 5000),
                ('銀行手續費', '銀行,手續費,匯款,轉帳', '5900', True, False, False, 0),
                ('雜項費用', '清潔,維修,郵資,快遞', '5900', True, True, False, 1000)
            ]

            for name, keywords, acc_code, deductible, receipt_req, approval_req, approval_limit in categories:
                cursor.execute('''
                    INSERT INTO categories 
                    (name, keywords, account_code, tax_deductible, requires_receipt, requires_approval, approval_limit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, keywords, acc_code, deductible, receipt_req, approval_req, approval_limit))

            print("✅ 支出分類建立完成")

        # 插入預設部門
        cursor.execute('SELECT COUNT(*) FROM departments')
        if cursor.fetchone()[0] == 0:
            departments = [
                ('ADMIN', '行政管理部', 50000, 600000),
                ('SALES', '業務部', 80000, 960000),
                ('TECH', '技術部', 100000, 1200000),
                ('MKT', '行銷部', 60000, 720000),
                ('FIN', '財務部', 30000, 360000),
                ('HR', '人力資源部', 40000, 480000)
            ]

            for code, name, monthly_budget, annual_budget in departments:
                cursor.execute('''
                    INSERT INTO departments (code, name, budget_monthly, budget_annual)
                    VALUES (?, ?, ?, ?)
                ''', (code, name, monthly_budget, annual_budget))

            print("✅ 部門建立完成")

        # 插入預設員工（系統管理員）
        cursor.execute('SELECT COUNT(*) FROM employees')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO employees 
                (employee_id, name, email, department, position, salary, expense_limit, can_approve, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('ADMIN001', '系統管理員', 'admin@company.com', 'ADMIN', '系統管理員', 0, 999999, True, 'active'))

            print("✅ 系統管理員建立完成")

        # 插入公司基本資料
        cursor.execute('SELECT COUNT(*) FROM company')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO company 
                (name, tax_id, address, phone, email, industry, capital, fiscal_year_start)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('我的公司', '12345678', '台北市信義區', '02-12345678',
                  'info@mycompany.com', '軟體開發', 1000000, 1))

            print("✅ 公司基本資料建立完成")

        # 插入預設銀行帳戶
        cursor.execute('SELECT COUNT(*) FROM bank_accounts')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO bank_accounts 
                (account_name, bank_name, account_number, account_type, opening_balance, current_balance)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('公司往來帳戶', '第一銀行', '123-456-789012', 'checking', 1000000, 1000000))

            print("✅ 銀行帳戶建立完成")

        conn.commit()
        conn.close()

        print("🎉 小型公司記帳資料庫初始化完成！")
        print("📊 包含功能：")
        print("   • 基本會計科目 (30+ 科目)")
        print("   • 員工管理 (1位系統管理員)")
        print("   • 部門管理 (6個部門)")
        print("   • 供應商/客戶管理")
        print("   • 專案管理")
        print("   • 預算管理")
        print("   • 報銷流程")
        print("   • 銀行對帳")
        print("   • 稅務管理")
        print("   • 發票管理")

        return True

    except Exception as e:
        print(f"❌ 資料庫初始化失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


# 啟動時初始化資料庫
init_database()


class FreeReceiptAI:
    def __init__(self):
        # 初始化 EasyOCR（支援繁體中文）
        try:
            self.reader = easyocr.Reader(['ch_tra', 'en'], gpu=False)
            print("🔧 EasyOCR 初始化完成（支援繁體中文）")
            self.ocr_available = True
        except Exception as e:
            print(f"⚠️ EasyOCR 初始化失敗: {e}")
            self.ocr_available = False

        # 載入分類關鍵字
        self.categories = self.load_categories()

    def load_categories(self) -> Dict[str, List[str]]:
        """從資料庫載入分類關鍵字"""
        try:
            conn = sqlite3.connect('receipts.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, keywords FROM categories")
            categories = {}

            for name, keywords in cursor.fetchall():
                if keywords:
                    categories[name] = keywords.split(',')
                else:
                    categories[name] = []

            conn.close()
            return categories
        except Exception as e:
            print(f"載入分類失敗: {e}")
            return {
                '餐費': ['餐廳', '小吃', '咖啡', '便當', '火鍋', '燒烤', '飲料', '麥當勞', '肯德基', '星巴克', '85度C'],
                '交通費': ['加油', '停車', '高鐵', '計程車', '捷運', '公車', '機票', '台鐵', '客運', 'Uber'],
                '辦公用品': ['文具', '紙張', '印表機', '電腦', '筆', '資料夾', '誠品', '金石堂'],
                '軟體服務': ['訂閱', 'SaaS', 'Office', 'Adobe', 'Google', 'AWS', 'Microsoft', 'Apple'],
                '設備採購': ['電腦', '螢幕', '鍵盤', '滑鼠', '椅子', '桌子', '3C', '燦坤', '全國電子'],
                '購物': ['百貨', '量販', '家樂福', '全聯', '好市多', '大潤發', '購物', '來麵屋'],
                '醫療費用': ['藥局', '醫院', '診所', '健保', '醫療', '康是美', '屈臣氏'],
                '娛樂費用': ['電影', 'KTV', '遊戲', '娛樂', '威秀', '國賓'],
                '雜費': ['水電', '電話', '網路', '清潔', '維修', '銀行', '郵局']
            }

    async def process_receipt(self, image_path: str) -> Dict:
        """處理發票：免費OCR → 智能解析 → 自動分類"""

        print(f"🔍 開始處理發票: {image_path}")

        # 1. 免費OCR辨識
        if self.ocr_available:
            ocr_result = await self._free_ocr(image_path)
        else:
            ocr_result = self._simulate_ocr()

        text = ocr_result['text']
        confidence = ocr_result['confidence']

        print(f"📝 OCR結果 (信心度: {confidence:.2f}): {text[:100]}...")

        # 2. 智能解析發票資料
        data = await self._smart_parse(text)
        data['ocr_confidence'] = confidence

        print(f"🔧 解析結果: {data}")

        # 3. 智能分類
        data['category'] = self._smart_categorize(data['merchant'], text)
        print(f"🏷️ 分類結果: {data['category']}")

        return data

    async def _free_ocr(self, image_path: str) -> Dict:
        """使用 EasyOCR 進行免費文字辨識"""

        try:
            # 前處理圖片
            image = Image.open(image_path)

            # 轉換為 numpy array
            img_array = np.array(image)

            # 使用 EasyOCR 辨識
            results = self.reader.readtext(img_array)

            # 合併所有辨識的文字
            full_text = ""
            total_confidence = 0

            for (bbox, text, confidence) in results:
                full_text += text + "\n"
                total_confidence += confidence

            # 計算平均信心度
            avg_confidence = total_confidence / len(results) if results else 0

            return {
                'text': full_text,
                'confidence': avg_confidence,
                'source': 'easyocr_free'
            }

        except Exception as e:
            print(f"⚠️ EasyOCR 處理失敗: {e}")
            return self._simulate_ocr()

    def _simulate_ocr(self) -> Dict:
        """備用模擬OCR（加入來麵屋等真實商家）"""
        fake_receipts = [
            """
            統一發票
            PA50921578
            114年06月14日
            來麵屋
            統編: 12345678
            品項: 拉麵
            數量: 1
            單價: 97
            營業稅: 5
            總計: 97
            """,
            """
            電子發票
            AB12345678
            113年12月16日
            星巴克咖啡
            統編: 28555485
            品項: 美式咖啡大杯
            數量: 1
            單價: 120
            營業稅: 6
            總計: 126
            """,
            """
            發票
            CD87654321
            113/12/16
            全家便利商店
            統編: 22099131
            商品: 茶葉蛋
            數量: 2
            金額: 26
            含稅總計: 26
            """,
            """
            統一發票
            EF11223344
            2024年12月16日
            麥當勞
            統編: 12345678
            大麥克套餐: 149
            可樂: 25
            總計: 174
            """,
            """
            電子發票
            GH55667788
            113年12月16日
            誠品書店
            統編: 87654321
            商品: Python程式設計
            單價: 450
            營業稅: 21
            總計: 471
            """
        ]

        import random
        return {
            'text': random.choice(fake_receipts),
            'confidence': 0.75,  # 模擬的信心度較低
            'source': 'simulation'
        }

    async def _smart_parse(self, text: str) -> Dict:
        """智能解析發票內容"""

        result = {
            'invoice_number': '',
            'date': '',
            'merchant': '',
            'amount': 0,
            'tax_amount': 0,
            'items': []
        }

        # 發票號碼：兩個英文字母+8個數字
        invoice_match = re.search(r'[A-Z]{2}[\-]?[0-9]{8}', text)
        if invoice_match:
            result['invoice_number'] = invoice_match.group().replace('-', '')

        # 總金額：更全面的模式匹配
        amount_patterns = [
            r'總計[：:\s]*\$?[\s]*(\d{1,6})',
            r'合計[：:\s]*\$?[\s]*(\d{1,6})',
            r'含稅總計[：:\s]*(\d{1,6})',
            r'總金額[：:\s]*(\d{1,6})',
            r'小計[：:\s]*(\d{1,6})',
            r'金額[：:\s]*(\d{1,6})',
            r'NT\$[\s]*(\d{1,6})',
            r'應收[：:\s]*(\d{1,6})',
            r'收費[：:\s]*(\d{1,6})'
        ]

        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                result['amount'] = int(match.group(1))
                break

        # 如果沒找到總計，找最大的數字（但過濾掉明顯不是金額的）
        if result['amount'] == 0:
            numbers = re.findall(r'\d{1,6}', text)
            if numbers:
                # 過濾掉可能是電話、統編、發票號碼的數字
                amounts = []
                for n in numbers:
                    num = int(n)
                    # 合理的金額範圍：10-99999
                    if 10 <= num <= 99999 and len(n) <= 5:
                        # 排除常見的非金額數字
                        if not (len(n) == 8 or len(n) == 10):  # 排除統編、電話
                            amounts.append(num)

                if amounts:
                    result['amount'] = max(amounts)

        # 日期解析
        date_patterns = [
            r'(\d{2,3})[年/\-.](\d{1,2})[月/\-.](\d{1,2})',  # 民國年
            r'(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})',  # 西元年
            r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 2024/12/16
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2024-12-16
        ]

        for pattern in date_patterns:
            date_match = re.search(pattern, text)
            if date_match:
                year = int(date_match.group(1))
                if year < 1000:  # 民國年轉西元年
                    year += 1911
                month = int(date_match.group(2))
                day = int(date_match.group(3))

                # 驗證日期合理性
                if 1 <= month <= 12 and 1 <= day <= 31:
                    result['date'] = f"{year}-{month:02d}-{day:02d}"
                    break

        if not result['date']:
            result['date'] = datetime.now().strftime('%Y-%m-%d')

        # 商家名稱辨識（針對台灣商家優化）
        merchant_patterns = [
            # 台灣常見店家格式
            r'(來麵屋|星巴克|麥當勞|肯德基|全家|7-ELEVEN|誠品|屈臣氏|康是美)',
            r'([\u4e00-\u9fff]+(?:麵屋|餐廳|咖啡|書店|藥局|醫院|診所|便利商店))',
            r'([\u4e00-\u9fff]+(?:公司|企業|行|店|館|廳|坊|屋|社|中心))',
            r'([A-Za-z]+(?:Starbucks|McDonald|KFC|FamilyMart))',
        ]

        for pattern in merchant_patterns:
            merchant_match = re.search(pattern, text, re.IGNORECASE)
            if merchant_match:
                result['merchant'] = merchant_match.group(1)
                break

        # 如果沒找到，找最長的中文字串
        if not result['merchant']:
            chinese_texts = re.findall(r'[\u4e00-\u9fff]+', text)
            if chinese_texts:
                # 過濾掉常見的無用詞
                filtered = [t for t in chinese_texts
                            if t not in ['統一發票', '電子發票', '營業稅', '總計', '合計', '小計',
                                         '品項', '數量', '單價', '金額', '日期', '時間', '發票號碼']]
                if filtered:
                    # 優先選擇長度適中的（2-8字）
                    suitable = [t for t in filtered if 2 <= len(t) <= 8]
                    if suitable:
                        result['merchant'] = max(suitable, key=len)
                    else:
                        result['merchant'] = max(filtered, key=len)

        if not result['merchant']:
            result['merchant'] = '未知商家'

        # 稅額計算
        if result['amount'] > 0:
            # 先嘗試找明確的稅額
            tax_patterns = [
                r'營業稅[：:\s]*(\d{1,4})',
                r'稅額[：:\s]*(\d{1,4})',
                r'TAX[：:\s]*(\d{1,4})',
            ]

            for pattern in tax_patterns:
                tax_match = re.search(pattern, text, re.IGNORECASE)
                if tax_match:
                    result['tax_amount'] = int(tax_match.group(1))
                    break

            # 如果沒找到，按5%計算
            if result['tax_amount'] == 0:
                result['tax_amount'] = round(result['amount'] * 0.05)

        return result

    def _smart_categorize(self, merchant: str, full_text: str) -> str:
        """智能分類：結合商家名稱和發票內容"""

        if not merchant:
            return '雜費'

        # 合併商家名稱和發票內容進行分析
        analysis_text = f"{merchant} {full_text}".lower()

        # 計算每個分類的匹配分數
        category_scores = {}

        for category, keywords in self.categories.items():
            score = 0
            for keyword in keywords:
                keyword_lower = keyword.lower()

                # 商家名稱完全匹配：高分
                if keyword_lower in merchant.lower():
                    score += 10

                # 發票內容包含：中等分
                elif keyword_lower in analysis_text:
                    score += 3

                # 部分匹配：低分
                elif any(part in analysis_text for part in keyword_lower.split() if len(part) > 2):
                    score += 1

            category_scores[category] = score

        # 選擇分數最高的分類
        if category_scores:
            best_category = max(category_scores.items(), key=lambda x: x[1])
            if best_category[1] > 0:  # 有匹配分數
                return best_category[0]

        return '雜費'  # 預設分類


# 建立AI實例
ai = FreeReceiptAI()


@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    """拍照上傳發票，AI智能辨識存檔"""

    try:
        # 檢查檔案類型
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="請上傳圖片檔案")

        # 使用臨時檔案
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            file_path = tmp_file.name

        print(f"📁 檔案已儲存: {file_path}")

        # AI智能辨識
        receipt_data = await ai.process_receipt(file_path)

        # 存入資料庫
        try:
            conn = sqlite3.connect('receipts.db')
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO receipts 
                (photo_path, invoice_number, date, merchant, amount, tax_amount, category, description, ocr_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                receipt_data['invoice_number'],
                receipt_data['date'],
                receipt_data['merchant'],
                receipt_data['amount'],
                receipt_data['tax_amount'],
                receipt_data['category'],
                f"AI辨識: {receipt_data['merchant']} (信心度: {receipt_data.get('ocr_confidence', 0):.2f})",
                receipt_data.get('ocr_confidence', 0)
            ))

            receipt_id = cursor.lastrowid
            conn.commit()
            conn.close()

            print(f"💾 資料已存入資料庫，ID: {receipt_id}")

            # 清理臨時檔案
            try:
                os.unlink(file_path)
            except:
                pass

            return {
                "success": True,
                "message": "AI發票辨識完成！",
                "data": {
                    **receipt_data,
                    "id": receipt_id
                }
            }

        except Exception as db_error:
            print(f"資料庫錯誤: {db_error}")
            return {
                "success": False,
                "error": f"資料庫錯誤: {str(db_error)}"
            }

    except Exception as e:
        print(f"❌ 錯誤: {str(e)}")
        return {
            "success": False,
            "error": f"處理失敗: {str(e)}"
        }


@app.get("/receipts")
def get_receipts(limit: int = 50):
    """取得最近的發票記錄"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, date, merchant, amount, category, created_at, ocr_confidence
            FROM receipts 
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        receipts = cursor.fetchall()
        conn.close()

        result = []
        for receipt in receipts:
            result.append({
                "id": receipt[0],
                "date": receipt[1],
                "merchant": receipt[2],
                "amount": receipt[3],
                "category": receipt[4],
                "created_at": receipt[5],
                "confidence": receipt[6] if len(receipt) > 6 else 0
            })

        return {"receipts": result}

    except Exception as e:
        return {"receipts": [], "error": str(e)}


@app.get("/monthly-report/{year}/{month}")
def monthly_report(year: int, month: int):
    """月報表：智能統計"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        cursor.execute('''
            SELECT category, SUM(amount), COUNT(*), AVG(ocr_confidence)
            FROM receipts 
            WHERE date LIKE ? 
            GROUP BY category
            ORDER BY SUM(amount) DESC
        ''', (f"{year}-{month:02d}%",))

        categories = cursor.fetchall()

        cursor.execute('''
            SELECT SUM(amount), SUM(tax_amount), COUNT(*), AVG(ocr_confidence)
            FROM receipts 
            WHERE date LIKE ?
        ''', (f"{year}-{month:02d}%",))

        total = cursor.fetchone()
        conn.close()

        return {
            "period": f"{year}-{month:02d}",
            "total_amount": total[0] or 0,
            "total_tax": total[1] or 0,
            "total_receipts": total[2] or 0,
            "avg_confidence": round(total[3] or 0, 2),
            "by_category": [
                {
                    "category": c[0],
                    "amount": c[1],
                    "count": c[2],
                    "avg_confidence": round(c[3] or 0, 2)
                }
                for c in categories
            ]
        }

    except Exception as e:
        return {
            "period": f"{year}-{month:02d}",
            "total_amount": 0,
            "total_tax": 0,
            "total_receipts": 0,
            "avg_confidence": 0,
            "by_category": [],
            "error": str(e)
        }


@app.get("/", response_class=HTMLResponse)
def main_page():
    """主頁面：AI智能記帳界面"""
    return """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <title>🤖 AI智能記帳系統 (免費版)</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Microsoft JhengHei', Arial, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { 
                max-width: 800px; 
                margin: 0 auto; 
                background: white;
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            h1 { 
                text-align: center; 
                color: #333; 
                margin-bottom: 30px;
                font-size: 2.5em;
            }
            .upload-section {
                text-align: center;
                margin-bottom: 40px;
                padding: 30px;
                border: 3px dashed #ddd;
                border-radius: 15px;
                background: #f9f9f9;
            }
            .camera-btn { 
                background: linear-gradient(45deg, #667eea, #764ba2);
                color: white; 
                border: none; 
                padding: 20px 40px; 
                font-size: 18px; 
                border-radius: 50px; 
                cursor: pointer;
                margin: 20px;
                box-shadow: 0 10px 20px rgba(102,126,234,0.3);
                transition: all 0.3s ease;
            }
            .camera-btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 15px 30px rgba(102,126,234,0.4);
            }
            .result { 
                margin: 20px 0; 
                padding: 20px; 
                border-radius: 10px;
                animation: slideIn 0.5s ease;
            }
            .success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
            .error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
            .loading { background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }
            .stat-card {
                background: linear-gradient(45deg, #74b9ff, #0984e3);
                color: white;
                padding: 20px;
                border-radius: 15px;
                text-align: center;
            }
            .stat-number { font-size: 2em; font-weight: bold; }
            .stat-label { font-size: 0.9em; opacity: 0.9; }

            .recent-receipts {
                margin-top: 30px;
            }
            .receipt-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px;
                border-bottom: 1px solid #eee;
                transition: background 0.3s ease;
            }
            .receipt-item:hover { background: #f8f9fa; }
            .receipt-amount { font-weight: bold; color: #e74c3c; }
            .receipt-category { 
                background: #3498db; 
                color: white; 
                padding: 4px 12px; 
                border-radius: 20px; 
                font-size: 0.8em;
            }
            .confidence-badge {
                background: #27ae60;
                color: white;
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 0.7em;
                margin-left: 5px;
            }

            .free-badge {
                background: #e74c3c;
                color: white;
                padding: 4px 8px;
                border-radius: 15px;
                font-size: 0.8em;
                margin-left: 10px;
            }

            @keyframes slideIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }

            @media (max-width: 600px) {
                .container { padding: 20px; margin: 10px; }
                h1 { font-size: 2em; }
                .camera-btn { padding: 15px 30px; font-size: 16px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 AI智能記帳系統 <span class="free-badge">FREE</span></h1>

            <div class="upload-section">
                <h2>📷 拍發票，AI秒辨識</h2>
                <p style="color: #666; margin: 10px 0;">支援 EasyOCR 免費發票辨識 • 繁體中文優化</p>
                <form id="uploadForm" enctype="multipart/form-data">
                    <input type="file" id="file" accept="image/*" capture="camera" style="display: none;" required>
                    <button type="button" class="camera-btn" onclick="document.getElementById('file').click()">
                        🆓 免費AI拍照辨識
                    </button>
                </form>
                <div id="result"></div>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="monthlyTotal">$0</div>
                    <div class="stat-label">本月支出</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="monthlyCount">0</div>
                    <div class="stat-label">本月筆數</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="avgAmount">$0</div>
                    <div class="stat-label">平均金額</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="avgConfidence">0%</div>
                    <div class="stat-label">AI準確度</div>
                </div>
            </div>

            <div class="recent-receipts">
                <h2>📊 最近記錄</h2>
                <div id="recentList"></div>
            </div>
        </div>

        <script>
            document.getElementById('file').onchange = async function(e) {
                const file = e.target.files[0];
                if (!file) return;

                const formData = new FormData();
                formData.append('file', file);

                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = '<div class="result loading">🤖 免費AI正在辨識發票，請稍候...</div>';

                try {
                    const response = await fetch('/upload-receipt', {
                        method: 'POST',
                        body: formData
                    });

                    const result = await response.json();

                    if (result.success) {
                        const confidence = (result.data.ocr_confidence * 100).toFixed(0);
                        resultDiv.innerHTML = `
                            <div class="result success">
                                <h3>✅ 免費AI辨識成功！</h3>
                                <p><strong>商家:</strong> ${result.data.merchant}</p>
                                <p><strong>金額:</strong> $${result.data.amount}</p>
                                <p><strong>分類:</strong> ${result.data.category}</p>
                                <p><strong>日期:</strong> ${result.data.date}</p>
                                <p><strong>發票號碼:</strong> ${result.data.invoice_number || '未辨識'}</p>
                                <p><strong>AI信心度:</strong> <span class="confidence-badge">${confidence}%</span></p>
                                <p style="font-size: 0.8em; color: #666; margin-top: 10px;">
                                    🆓 使用 EasyOCR 免費辨識引擎
                                </p>
                            </div>
                        `;

                        loadStats();
                        loadRecentReceipts();

                    } else {
                        resultDiv.innerHTML = `
                            <div class="result error">
                                <h3>❌ AI辨識失敗</h3>
                                <p>${result.error}</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `
                        <div class="result error">
                            <h3>❌ 網路錯誤</h3>
                            <p>${error.message}</p>
                        </div>
                    `;
                }

                document.getElementById('file').value = '';
            };

            async function loadStats() {
                try {
                    const now = new Date();
                    const response = await fetch(`/monthly-report/${now.getFullYear()}/${now.getMonth() + 1}`);
                    const data = await response.json();

                    document.getElementById('monthlyTotal').textContent = `$${(data.total_amount || 0).toLocaleString()}`;
                    document.getElementById('monthlyCount').textContent = data.total_receipts || 0;
                    document.getElementById('avgConfidence').textContent = `${(data.avg_confidence || 0).toFixed(0)}%`;

                    const avg = (data.total_receipts || 0) > 0 ? (data.total_amount || 0) / (data.total_receipts || 0) : 0;
                    document.getElementById('avgAmount').textContent = `$${Math.round(avg)}`;

                } catch (error) {
                    console.error('載入統計資料失敗:', error);
                }
            }

            async function loadRecentReceipts() {
                try {
                    const response = await fetch('/receipts?limit=10');
                    const data = await response.json();

                    let html = '';
                    if (data.receipts && data.receipts.length > 0) {
                        data.receipts.forEach(receipt => {
                            const confidence = ((receipt.confidence || 0) * 100).toFixed(0);
                            html += `
                                <div class="receipt-item">
                                    <div>
                                        <strong>${receipt.merchant}</strong>
                                        ${confidence > 0 ? `<span class="confidence-badge">${confidence}%</span>` : ''}
                                        <br>
                                        <small>${receipt.date}</small>
                                    </div>
                                    <div style="text-align: right;">
                                        <div class="receipt-amount">$${receipt.amount}</div>
                                        <div class="receipt-category">${receipt.category}</div>
                                    </div>
                                </div>
                            `;
                        });
                    } else {
                        html = '<p style="text-align: center; color: #666;">還沒有記錄，快拍第一張發票讓免費AI學習吧！</p>';
                    }

                    document.getElementById('recentList').innerHTML = html;

                } catch (error) {
                    console.error('載入最近記錄失敗:', error);
                    document.getElementById('recentList').innerHTML = '<p style="text-align: center; color: #666;">載入記錄時發生錯誤</p>';
                }
            }

            window.onload = function() {
                loadStats();
                loadRecentReceipts();
            };
        </script>
    </body>
    </html>
    """


# 健康檢查端點
@app.get("/health")
def health_check():
    """健康檢查"""
    return {
        "status": "ok",
        "message": "AI智能記帳系統運行正常！",
        "features": {
            "easyocr": "✅ 已設定" if ai.ocr_available else "⚠️ 未設定",
            "mode": "免費版本 (EasyOCR)"
        }
    }


# 啟動應用
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8080))
    print("🚀 啟動免費AI智能記帳系統...")
    print(f"📱 訪問網址: http://localhost:{port}")
    print("🛑 按 Ctrl+C 停止服務")

    uvicorn.run(app, host="0.0.0.0", port=port)