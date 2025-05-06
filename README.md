# GPU 評測爬蟲系統說明文件

## 專案概述

本專案是一套 GPU 評測爬蟲系統，從 [TechPowerUp](https://www.techpowerup.com/gpu-specs/) 網站收集 GPU 產品評測資料。系統支援完整爬取及增量更新功能，用於維護評測資料庫。

## 系統需求

- Python 3.8+
- SQL Server 資料庫
  - 正式環境與測試爬蟲機：必須使用 SQL Server 18
  - 本地開發環境：可依據個人電腦已安裝的 SQL Server 版本
- 以下套件 (見 requirements.txt):
  - fastapi
  - uvicorn
  - aiohttp
  - beautifulsoup4
  - python-dotenv
  - pyodbc
  - colorama

## 系統啟動方式

1. 確保已安裝所有依賴套件:
```bash
pip install -r requirements.txt
```

2. 設定 `.env` 檔案:
```
DB_SERVER=你的資料庫伺服器位置
DB_NAME=資料庫名稱
DB_USER=使用者名稱
DB_PASSWORD=密碼
```

3. 啟動爬蟲 API 服務:
```bash
python scraper.py
```

服務預設在 http://localhost:8104 啟動

## API 端點說明

系統提供以下 REST API 端點:

### 1. 啟動爬蟲 - 完整模式

```
GET /run-scraper
```

查詢參數:
- `mode`: 可選，爬蟲模式
  - 不提供: 執行完整爬蟲
  - `full`: 執行全量評測更新
  - `incremental`: 執行增量評測更新

範例:
```
GET http://localhost:8000/run-scraper?mode=full
```

回應:
```json
{
  "success": true,
  "message": "全量更新任務已在背景啟動，完成後將發送郵件通知"
}
```

### 2. 啟動指定 GPU 爬蟲

```
GET /run-scraper-selected
```

查詢參數:
- `gpu_name`: 要爬取的 GPU 名稱 (選填)

範例:
```
GET http://localhost:8000/run-scraper-selected?gpu_name=Radeon RX 9070 XT
```

回應:
```json
{
  "success": true,
  "message": "已開始爬取 GPU: Radeon RX 9070 XT，完成後將發送通知"
}
```

### 3. 查詢爬蟲狀態

```
GET /status
```

回應範例:
```json
{
  "is_running": true,
  "last_result": {
    "mode": "full_update",
    "started_at": "2023-06-01T10:15:30.123456",
    "stats": {
      "updated_reviews": 156,
      "elapsed_time": 1850.75
    },
    "success": true
  },
  "current_task": {
    "task_info": "全量更新",
    "progress": 75,
    "products_processed": 42,
    "reviews_processed": 156
  }
}
```

## 系統核心組件

### `scraper.py`
爬蟲應用程式的主要入口點:
- 包含 FastAPI 應用定義
- `GPUScraper` 類別處理爬蟲邏輯
- 背景任務管理

關鍵方法:
```python
class GPUScraper:
    async def run(self):  # 執行完整爬蟲
    async def run_selected(self, gpu_name=None):  # 執行指定 GPU 爬蟲
    async def fetch_url(self, url, absolute=True, check_processed=True):  # 非同步獲取頁面
    async def scrape_product_list(self):  # 爬取產品列表
    async def scrape_product_detail(self, gpu):  # 爬取產品詳情
    async def scrape_review(self, review_url):  # 爬取評測內容
```

### `utils/update_review.py`
評測資料更新的核心模組:
- 管理增量與完整更新流程
- 執行評測資料的提取與儲存

主要方法:
```python
class UpdateManager:
    async def crawl_review_urls(self):  # 爬取所有評測 URL
    async def crawl_review_subpages(self):  # 爬取評測子頁面 URL 與內容
    async def update_review(self, review_info):  # 更新單一評測資料
    async def incremental_update(self):  # 執行增量更新流程
    async def full_update(self):  # 執行全量更新流程
```

### `utils/parsers.py`
處理 HTML 內容解析:
- 從網頁提取結構化資料
- 使用 BeautifulSoup 解析 DOM

主要方法:
```python
class GPUParser:
    @staticmethod
    def parse_product_list(html):  # 解析產品列表頁
    @staticmethod
    def parse_product_detail(html, url):  # 解析產品詳情頁
    @staticmethod
    def parse_boards_section(html):  # 解析主板區域
    @staticmethod
    def parse_review_options(html):  # 解析評測選項
    @staticmethod
    def parse_review_content(html, review_type):  # 解析評測內容
    @staticmethod
    def parse_review_posted_date(html):  # 解析評測發布日期
```

### `utils/state_manager.py`
管理爬蟲狀態:
- 追蹤進度與統計資料
- 提供狀態查詢介面

主要方法:
```python
class ScrapeState:
    def add_product(self, product_id, product_name):  # 記錄已處理的產品
    def add_review(self, product_id, board_name):  # 記錄已處理的評測
    def get_stats(self):  # 獲取統計資訊
    def set_progress(self, progress):  # 設置進度百分比
```

### `utils/database.py`
處理資料庫操作:
- 提供 SQL Server 連接與操作
- 管理交易與錯誤復原

主要方法:
```python
class Database:
    async def connect(self):  # 連接資料庫
    async def disconnect(self):  # 關閉資料庫連接
    async def run_db_query(self, query_func):  # 執行數據庫查詢
    async def create_review(self, board_id, review_type, title, content):  # 建立評測記錄
    async def create_review_data(self, review_id, data_type, data_key, data_value, data_unit, product_name):  # 建立評測資料
```

### `utils/anti_crawl.py`
實現爬蟲抗偵測機制:
- 管理請求標頭與延遲
- 處理 HTTP 請求失敗重試

主要方法:
```python
class AntiCrawl:
    def get_headers(self):  # 生成隨機請求標頭
    def get_random_delay(self):  # 獲取隨機延遲時間
    async def handle_retry_async(self, attempt):  # 處理重試邏輯
```

## 實際運行流程

### 增量更新流程

1. 檢索所有已有評測記錄
2. 對每筆記錄檢查來源網站是否有更新 (比對發布日期)
3. 只處理有變更的評測
4. 更新資料庫中的內容

```python
# 增量更新啟動方式
curl "http://localhost:8104/run-scraper?mode=incremental"
```

### 完整更新流程

1. 更新所有產品的評測 URL
2. 更新所有評測子頁面 URL
3. 更新所有評測內容與規格

```python
# 完整更新啟動方式
curl "http://localhost:8104/run-scraper?mode=full"
```

## 常見問題排除

1. 資料庫連線失敗
   - 檢查 `.env` 檔案設定
   - 確認 SQL Server 服務已啟動
   - 確認網路可連接到資料庫伺服器

2. 爬蟲被網站封鎖
   - 檢查 `anti_crawl.py` 中的延遲設定，可能需要增加延遲
   - 考慮更新 User-Agent 字串
   - 可能需要使用代理伺服器 (目前未實作)

3. 評測解析錯誤
   - 檢查 `parsers.py` 中的解析邏輯
   - 網站結構可能已變更，需要更新解析器

## 數據結構

系統使用以下關鍵資料表:

1. `dbo.C_Product`: 儲存 GPU 產品基本資訊
2. `dbo.C_Product_Review`: 儲存評測內容
3. `dbo.C_S_Flag`: 儲存技術規格類別
4. `dbo.C_Specs_Database`: 儲存產品技術規格以及儲存評測數

需要對 `C_Product_Review` 表進行以下修改:

```sql
-- 在 C_Product_Review 表中添加兩個欄位
ALTER TABLE dbo.C_Product_Review ADD F_Main_Review_URL NVARCHAR(500);
ALTER TABLE dbo.C_Product_Review ADD F_Page_URL NVARCHAR(500);
```

欄位說明:
- `F_Main_Review_URL`: 存儲主評測頁面 URL (如 https://www.techpowerup.com/review/asus-radeon-rx-9070-xt-tuf-oc/)
- `F_Page_URL`: 存儲具體子頁面的 URL (如 /review/asus-radeon-rx-9070-xt-tuf-oc/39.html)

## **資料欄位對照表**

| **分類**               | **屬性英文**      | **屬性名稱**    | **預設值** |
|------------------------|-------------------|-----------------|-----------|
| **Board Design (顯卡基本規格)**        | Length            | 長度            | null      |
|                        | Width             | 寬度            | null      |
|                        | Height            | 高度            | null      |
|                        | Outputs    | 輸出接口        | null      |
|                        | SlotWidth         | 插槽寬度        | null      |
|                        | TDP               | TDP             | null      |
|                        | SuggestedPSU      | 建議電源        | null      |
|                        | PowerConnectors       | 電源接口        | null      |
|                        | BoardNumber       | 板卡型號        | null      |
| **Graphics Card (板卡設計)**       | ReleaseDate       | 發布日期        | null      |
|                        | Announced         | 公告日期        | null      |
| **Clock Speeds (時脈速度)**        | BaseClock         | 基礎時脈        | null      |
|                        | BoostClock        | 加速時脈        | null      |
|                        | MemoryClock       | 記憶體時脈      | null      |
| **Physical Properties (物理特性與散熱)** | Weight            | 重量            | null      |
|                        | Pipe       | 熱管數量        | null      |
|                        | IdleGPUTemp (新增)             | 閒置溫度            | null      |
|                        | GamingGPUTemp (原Temp)            | 負載溫度            | null      |
|                        | MemoryTemp (新增)             | 記憶體溫度            | null      |
|                        | Noice             | 噪音            | null      |
| **TDP Compare (功耗超頻)**         | TDPComparison     | 預設功耗        | null      |
|                        | TDPDefault        | 最大功耗        | null      |
|                        | TDPMax            | 功耗比較        | null      |
|                        | AvgGPUClock   | Avg. GPU Clock  | null      |
|                        | MaxMemoryClock       | Max. Memory Clock | null      |
|                        | Performance    | Performance     | null      |
|                        | PwrLimitDefMax       | Pwr Limit Def/Max | null      |
|                        | OCPerfMaxPwr    | OC Perf at Max Pwr | null      |
| **GPU**                 | GPUMEMCount       | MEM顆數         | null      |
|                        | GPUControllerModel| 控制器型號      | null      |
|                        | GPUMOSSpec        | MOS規格         | null      |
| **Memory**              | MemoryMEMCount    | MEM顆數         | null      |
|                        | MemoryControllerModel| 控制器型號    | null      |
|                        | MemoryMOSSpec     | MOS規格         | null      |

## 開發與維護注意事項

- TechPowerUp 網站結構變更時需更新解析器
- 系統設計為低流量爬取，避免對目標網站造成負擔
- 請勿移除或縮短延遲時間，以免目標網站封鎖 IP

## 監控與日誌

系統日誌輸出到控制台，可透過以下方式檢視:

1. 直接在控制台觀察
2. 使用 `>` 重導向到檔案:
```bash
python scraper.py > scraper.log
```

當前任務狀態可透過 `/status` API 端點隨時查詢。