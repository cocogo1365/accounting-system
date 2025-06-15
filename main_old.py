# main_old.py - 暴力記帳系統主程式
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import uuid
import os
import re
import base64
import requests
from datetime import datetime
from typing import Dict, List
import json

# 建立必要的資料夾
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = FastAPI(title="暴力記帳系統", description="拍照→辨識→記帳，就這麼簡單！")


# 暴力AI辨識類別
class BrutalReceiptAI:
    def __init__(self):
        # 分類關鍵字（從資料庫載入）
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
        except:
            # 如果資料庫有問題，使用預設分類
            return {
                '餐費': ['餐廳', '小吃', '咖啡', '便當', '火鍋', '燒烤', '飲料'],
                '交通': ['加油', '停車', '高鐵', '計程車', '捷運', '公車', '機票'],
                '辦公用品': ['文具', '紙張', '印表機', '電腦', '筆', '資料夾'],
                '軟體服務': ['訂閱', 'SaaS', 'Office', 'Adobe', 'Google', 'AWS'],
                '設備': ['電腦', '螢幕', '鍵盤', '滑鼠', '椅子', '桌子'],
                '雜費': ['水電', '電話', '網路', '清潔', '維修']
            }

    def process_receipt(self, image_path: str) -> Dict:
        """暴力處理發票：OCR → 解析 → 分類"""

        print(f"🔍 開始處理發票: {image_path}")

        # 1. 模擬OCR辨識（實際應該調用Google Vision API）
        text = self._simulate_ocr(image_path)
        print(f"📝 OCR結果: {text[:100]}...")

        # 2. 暴力解析發票資料
        data = self._brutal_parse(text)
        print(f"🔧 解析結果: {data}")

        # 3. 暴力分類
        data['category'] = self._brutal_categorize(data['merchant'])
        print(f"🏷️ 分類結果: {data['category']}")

        return data

    def _simulate_ocr(self, image_path: str) -> str:
        """模擬OCR結果（實際使用時要接Google Vision API）"""
        # 這裡模擬一個台灣發票的OCR結果
        fake_receipts = [
            """
            統一發票
            AB12345678
            113年12月16日
            星巴克咖啡
            統編: 28555485
            品項: 美式咖啡大杯
            數量: 1
            單價: 120
            小計: 120
            營業稅: 6
            總計: 126
            """,
            """
            電子發票
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
            發票
            EF11223344
            2024年12月16日
            台北車站停車場
            停車費: 50
            時數: 3小時
            總金額: 50
            """
        ]

        # 隨機選一個模擬結果
        import random
        return random.choice(fake_receipts)

    def _brutal_parse(self, text: str) -> Dict:
        """暴力解析發票內容"""

        result = {
            'invoice_number': '',
            'date': '',
            'merchant': '',
            'amount': 0,
            'tax_amount': 0,
            'items': []
        }

        # 發票號碼：兩個英文字母+8個數字
        invoice_match = re.search(r'[A-Z]{2}\d{8}', text)
        if invoice_match:
            result['invoice_number'] = invoice_match.group()

        # 總金額：各種可能的表示方式
        amount_patterns = [
            r'總計[：:\s]*\$?(\d{1,6})',
            r'合計[：:\s]*\$?(\d{1,6})',
            r'含稅總計[：:\s]*(\d{1,6})',
            r'總金額[：:\s]*(\d{1,6})',
            r'NT\$\s*(\d{1,6})',
            r'金額[：:\s]*(\d{1,6})'
        ]

        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                result['amount'] = int(match.group(1))
                break

        # 如果沒找到總計，找單價
        if result['amount'] == 0:
            price_match = re.search(r'(\d{1,4})', text)
            if price_match:
                result['amount'] = int(price_match.group(1))

        # 日期解析
        date_patterns = [
            r'(\d{2,3})[年/\-.](\d{1,2})[月/\-.](\d{1,2})',  # 民國年
            r'(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})',  # 西元年
            r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 2024/12/16
        ]

        for pattern in date_patterns:
            date_match = re.search(pattern, text)
            if date_match:
                year = int(date_match.group(1))
                if year < 1000:  # 民國年轉西元年
                    year += 1911
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                result['date'] = f"{year}-{month:02d}-{day:02d}"
                break

        # 如果沒有日期，使用今天
        if not result['date']:
            result['date'] = datetime.now().strftime('%Y-%m-%d')

        # 商家名稱：找最長的中文字串
        chinese_texts = re.findall(r'[\u4e00-\u9fff]+', text)
        if chinese_texts:
            # 過濾掉常見的無用詞
            filtered = [t for t in chinese_texts if t not in ['統一發票', '電子發票', '營業稅', '總計', '合計']]
            if filtered:
                result['merchant'] = max(filtered, key=len)

        # 如果沒找到中文商家名，找英文
        if not result['merchant']:
            english_match = re.search(r'[A-Za-z]+', text)
            if english_match:
                result['merchant'] = english_match.group()

        # 預設商家名稱
        if not result['merchant']:
            result['merchant'] = '未知商家'

        # 稅額計算（台灣營業稅5%）
        if result['amount'] > 0:
            result['tax_amount'] = round(result['amount'] * 0.05)

        return result

    def _brutal_categorize(self, merchant: str) -> str:
        """暴力分類：看商家名包含什麼關鍵字"""

        if not merchant:
            return '雜費'

        merchant_lower = merchant.lower()

        for category, keywords in self.categories.items():
            for keyword in keywords:
                if keyword.lower() in merchant_lower:
                    return category

        return '雜費'  # 預設分類


# 建立AI實例
ai = BrutalReceiptAI()


# API路由
@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    """拍照上傳發票，自動辨識存檔"""

    try:
        # 1. 檢查檔案類型
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="請上傳圖片檔案")

        # 2. 儲存照片
        file_id = str(uuid.uuid4())
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        file_path = f"uploads/{file_id}.{file_extension}"

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        print(f"📁 檔案已儲存: {file_path}")

        # 3. AI暴力辨識
        receipt_data = ai.process_receipt(file_path)

        # 4. 存入資料庫
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO receipts 
            (photo_path, invoice_number, date, merchant, amount, tax_amount, category, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_path,
            receipt_data['invoice_number'],
            receipt_data['date'],
            receipt_data['merchant'],
            receipt_data['amount'],
            receipt_data['tax_amount'],
            receipt_data['category'],
            f"自動辨識: {receipt_data['merchant']}"
        ))

        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"💾 資料已存入資料庫，ID: {receipt_id}")

        return {
            "success": True,
            "message": "發票辨識完成！",
            "data": {
                **receipt_data,
                "id": receipt_id
            }
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
            SELECT id, date, merchant, amount, category, created_at
            FROM receipts 
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        receipts = cursor.fetchall()
        conn.close()

        # 轉換為字典格式
        result = []
        for receipt in receipts:
            result.append({
                "id": receipt[0],
                "date": receipt[1],
                "merchant": receipt[2],
                "amount": receipt[3],
                "category": receipt[4],
                "created_at": receipt[5]
            })

        return {"receipts": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫錯誤: {str(e)}")


@app.get("/monthly-report/{year}/{month}")
def monthly_report(year: int, month: int):
    """月報表：暴力統計"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        # 該月所有支出（按分類統計）
        cursor.execute('''
            SELECT category, SUM(amount), COUNT(*) 
            FROM receipts 
            WHERE date LIKE ? 
            GROUP BY category
            ORDER BY SUM(amount) DESC
        ''', (f"{year}-{month:02d}%",))

        categories = cursor.fetchall()

        # 總計
        cursor.execute('''
            SELECT SUM(amount), SUM(tax_amount), COUNT(*) 
            FROM receipts 
            WHERE date LIKE ?
        ''', (f"{year}-{month:02d}%",))

        total = cursor.fetchone()

        # 每日支出
        cursor.execute('''
            SELECT date, SUM(amount), COUNT(*)
            FROM receipts 
            WHERE date LIKE ?
            GROUP BY date
            ORDER BY date
        ''', (f"{year}-{month:02d}%",))

        daily_expenses = cursor.fetchall()

        conn.close()

        return {
            "period": f"{year}-{month:02d}",
            "total_amount": total[0] or 0,
            "total_tax": total[1] or 0,
            "total_receipts": total[2] or 0,
            "by_category": [
                {"category": c[0], "amount": c[1], "count": c[2]}
                for c in categories
            ],
            "daily_expenses": [
                {"date": d[0], "amount": d[1], "count": d[2]}
                for d in daily_expenses
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"報表錯誤: {str(e)}")


@app.get("/yearly-summary/{year}")
def yearly_summary(year: int):
    """年度總結"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        # 年度總計
        cursor.execute('''
            SELECT SUM(amount), SUM(tax_amount), COUNT(*)
            FROM receipts 
            WHERE date LIKE ?
        ''', (f"{year}%",))

        annual_total = cursor.fetchone()

        # 月度統計
        monthly_data = []
        for month in range(1, 13):
            cursor.execute('''
                SELECT SUM(amount), COUNT(*)
                FROM receipts 
                WHERE date LIKE ?
            ''', (f"{year}-{month:02d}%",))

            month_data = cursor.fetchone()
            monthly_data.append({
                "month": f"{year}-{month:02d}",
                "amount": month_data[0] or 0,
                "count": month_data[1] or 0
            })

        conn.close()

        return {
            "year": year,
            "total_expense": annual_total[0] or 0,
            "total_tax": annual_total[1] or 0,
            "total_receipts": annual_total[2] or 0,
            "monthly_breakdown": monthly_data,
            "average_monthly": (annual_total[0] or 0) / 12
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"年度報表錯誤: {str(e)}")


@app.get("/", response_class=HTMLResponse)
def main_page():
    """主頁面：超簡單網頁界面"""
    return """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <title>📱 暴力記帳系統</title>
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
                background: linear-gradient(45deg, #ff6b6b, #ee5a24);
                color: white; 
                border: none; 
                padding: 20px 40px; 
                font-size: 18px; 
                border-radius: 50px; 
                cursor: pointer;
                margin: 20px;
                box-shadow: 0 10px 20px rgba(255,107,107,0.3);
                transition: all 0.3s ease;
            }
            .camera-btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 15px 30px rgba(255,107,107,0.4);
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
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
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
            <h1>📱 暴力記帳系統</h1>

            <div class="upload-section">
                <h2>📷 拍發票，秒記帳</h2>
                <form id="uploadForm" enctype="multipart/form-data">
                    <input type="file" id="file" accept="image/*" capture="camera" style="display: none;" required>
                    <button type="button" class="camera-btn" onclick="document.getElementById('file').click()">
                        📸 拍照上傳發票
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
            </div>

            <div class="recent-receipts">
                <h2>📊 最近記錄</h2>
                <div id="recentList"></div>
            </div>
        </div>

        <script>
            // 檔案選擇處理
            document.getElementById('file').onchange = async function(e) {
                const file = e.target.files[0];
                if (!file) return;

                const formData = new FormData();
                formData.append('file', file);

                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = '<div class="result loading">🔄 正在辨識發票，請稍候...</div>';

                try {
                    const response = await fetch('/upload-receipt', {
                        method: 'POST',
                        body: formData
                    });

                    const result = await response.json();

                    if (result.success) {
                        resultDiv.innerHTML = `
                            <div class="result success">
                                <h3>✅ 記帳成功！</h3>
                                <p><strong>商家:</strong> ${result.data.merchant}</p>
                                <p><strong>金額:</strong> $${result.data.amount}</p>
                                <p><strong>分類:</strong> ${result.data.category}</p>
                                <p><strong>日期:</strong> ${result.data.date}</p>
                                <p><strong>發票號碼:</strong> ${result.data.invoice_number || '未辨識'}</p>
                            </div>
                        `;

                        // 重新載入統計資料
                        loadStats();
                        loadRecentReceipts();

                    } else {
                        resultDiv.innerHTML = `
                            <div class="result error">
                                <h3>❌ 辨識失敗</h3>
                                <p>${result.error}</p>
                                <p>💡 請確保照片清晰，包含完整發票資訊</p>
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

                // 清空檔案選擇
                document.getElementById('file').value = '';
            };

            // 載入統計資料
            async function loadStats() {
                try {
                    const now = new Date();
                    const response = await fetch(`/monthly-report/${now.getFullYear()}/${now.getMonth() + 1}`);
                    const data = await response.json();

                    document.getElementById('monthlyTotal').textContent = `$${data.total_amount.toLocaleString()}`;
                    document.getElementById('monthlyCount').textContent = data.total_receipts;

                    const avg = data.total_receipts > 0 ? data.total_amount / data.total_receipts : 0;
                    document.getElementById('avgAmount').textContent = `$${Math.round(avg)}`;

                } catch (error) {
                    console.error('載入統計資料失敗:', error);
                }
            }

            // 載入最近記錄
            async function loadRecentReceipts() {
                try {
                    const response = await fetch('/receipts?limit=10');
                    const data = await response.json();

                    let html = '';
                    data.receipts.forEach(receipt => {
                        html += `
                            <div class="receipt-item">
                                <div>
                                    <strong>${receipt.merchant}</strong><br>
                                    <small>${receipt.date}</small>
                                </div>
                                <div style="text-align: right;">
                                    <div class="receipt-amount">$${receipt.amount}</div>
                                    <div class="receipt-category">${receipt.category}</div>
                                </div>
                            </div>
                        `;
                    });

                    document.getElementById('recentList').innerHTML = html || '<p style="text-align: center; color: #666;">還沒有記錄，快拍第一張發票吧！</p>';

                } catch (error) {
                    console.error('載入最近記錄失敗:', error);
                }
            }

            // 頁面載入時初始化
            window.onload = function() {
                loadStats();
                loadRecentReceipts();
            };
        </script>
    </body>
    </html>
    """


# 啟動應用
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8080))  # 改成 8080
    print("🚀 啟動暴力記帳系統...")
    print(f"📱 訪問網址: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)