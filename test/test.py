import asyncio
import requests
import logging
import sys
from bs4 import BeautifulSoup
from utils.parsers import GPUParser

# 設置日誌
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

# 測試函數
async def test_temperature_parsing():
    print("開始測試溫度資料抓取...")
    url = 'https://www.techpowerup.com/review/msi-geforce-rtx-5060-ti-gaming-16-gb/40.html'
    # 從本地HTML檔案讀取，或直接提供HTML字串
    # 添加瀏覽器標頭以避免被阻擋
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.techpowerup.com/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
    }
    
    try:
        # 添加 headers 和 timeout 參數
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html_content = response.text
        
        # 保存 HTML 到文件以備後用
        with open('temperature_page2.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"成功下載HTML內容，長度: {len(html_content)} 字元")
        print(f"已保存至 'temperature_page.html'")
    except requests.exceptions.RequestException as e:
        print(f"下載HTML失敗: {e}")
        # 嘗試從本地文件讀取
        try:
            with open('temperature_page.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
                print(f"從本地文件讀取HTML，長度: {len(html_content)} 字元")
        except FileNotFoundError:
            print("本地文件不存在，無法繼續測試。")
            return
    
    # 使用 GPUParser 的方法解析
    review_type = "Temperatures & Fan noise"  # 設定評測類型以觸發正確的解析邏輯
    content, review_data, specs_data = GPUParser.parse_review_content(html_content, review_type)
    
    # 輸出解析結果
    print("\n=== 解析結果摘要 ===")
    
    # 檢查是否找到溫度相關數據
    temp_specs = [spec for spec in specs_data if spec['category'] == 'Physical Properties']
    
    if temp_specs:
        print(f"\n找到 {len(temp_specs)} 項溫度/噪音相關數據:")
        for spec in temp_specs:
            print(f"- {spec['name']}: {spec['value']}")
    else:
        print("未找到任何溫度或噪音相關數據")
    
    print("\n=== 完整解析結果 ===")
    print(f"Content keys: {list(content.keys()) if content else 'None'}")
    print(f"Review data: {review_data}")
    print(f"Specs data: {specs_data}")

if __name__ == "__main__":
    asyncio.run(test_temperature_parsing())