import asyncio
import requests
import logging
import sys
import json
from bs4 import BeautifulSoup
from utils.parsers import GPUParser

# 設置日誌
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# 測試函數
async def test_circuit_analysis_parsing():
    print("開始測試電路板分析資料抓取...")
    urls = [
        'https://www.techpowerup.com/review/sapphire-radeon-rx-7600-xt-pulse/4.html',
        'https://www.techpowerup.com/review/xfx-radeon-rx-6800-xt-speedster-merc-319-black/3.html',
    ]
    
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
    
    all_results = []
    
    for idx, url in enumerate(urls):
        print(f"\n測試 URL {idx+1}/{len(urls)}: {url}")
        file_name = f"circuit_page_{idx+1}.html"
        
        try:
            # 添加 headers 和 timeout 參數
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            html_content = response.text
            
            # 保存 HTML 到文件以備後用
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"成功下載HTML內容，長度: {len(html_content)} 字元")
            print(f"已保存至 '{file_name}'")
        except requests.exceptions.RequestException as e:
            print(f"下載HTML失敗: {e}")
            # 嘗試從本地文件讀取
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    print(f"從本地文件讀取HTML，長度: {len(html_content)} 字元")
            except FileNotFoundError:
                print(f"本地文件 {file_name} 不存在，跳過此測試。")
                continue
        
        # 使用 GPUParser 的方法解析
        review_type = "Circuit Board Analysis"  # 設定評測類型以觸發正確的解析邏輯
        content, review_data, specs_data = GPUParser.parse_review_content(html_content, review_type)
        
        # 保存解析結果到 JSON 文件
        result = {
            "url": url,
            "content": content,
            "review_data": review_data,
            "specs_data": specs_data
        }
        all_results.append(result)
        
        # 輸出解析結果
        print("\n=== 解析結果摘要 ===")
        
        # 分類數據
        gpu_data = [item for item in review_data if item['data_type'] == 'GPU']
        memory_data = [item for item in review_data if item['data_type'] == 'Memory']
        
        # 檢查是否找到 GPU 相關數據
        if gpu_data:
            print(f"\n找到 {len(gpu_data)} 項 GPU 電路數據:")
            for item in gpu_data:
                print(f"- {item['data_key']}: {item['data_value']} {item['data_unit']}")
        else:
            print("未找到任何 GPU 電路數據")
            
        # 檢查是否找到記憶體相關數據
        if memory_data:
            print(f"\n找到 {len(memory_data)} 項記憶體電路數據:")
            for item in memory_data:
                print(f"- {item['data_key']}: {item['data_value']} {item['data_unit']}")
        else:
            print("未找到任何記憶體電路數據")
        
        # 輸出提取出的所有 specs 數據
        print("\n=== 規格數據摘要 ===")
        if specs_data:
            for spec in specs_data:
                print(f"- {spec['category']} | {spec['name']}: {spec['value']}")
        else:
            print("未找到任何規格數據")
        
        # 如果有內容，檢查解析到的文本長度
        if content and 'body' in content:
            print(f"\n內容文本長度: {len(content['body'])} 字元")
            print(f"內容前 100 字元: {content['body'][:100]}...")
    
    # 將所有結果寫入 JSON 文件以便後續分析
    with open('circuit_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("\n所有解析結果已保存至 'circuit_analysis_results.json'")
    
    # 返回結果供後續處理
    return all_results

async def analyze_regex_patterns():
    """分析哪些正則表達式模式被成功匹配"""
    # 首先運行測試獲取數據
    results = await test_circuit_analysis_parsing()
    

if __name__ == "__main__":
    asyncio.run(analyze_regex_patterns())