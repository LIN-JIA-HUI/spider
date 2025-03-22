import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class GPUParser:
    """GPU 資料解析類"""
    
    @staticmethod
    def extract_vendor(product_name):
        """從產品名稱提取廠商"""
        # 方法 1: 從名稱開頭到第一個空格
        if product_name and ' ' in product_name:
            vendor = product_name.split(' ')[0]
            return vendor
        
        # 方法 2: 如果上述方法失敗，則使用關鍵詞匹配作為備用
        vendors = {
            'NVIDIA': ['NVIDIA', 'GeForce', 'RTX', 'GTX', 'Quadro', 'Tesla'],
            'AMD': ['AMD', 'Radeon', 'RX', 'Vega', 'Fury', 'FirePro'],
            'Intel': ['Intel', 'Arc', 'Iris', 'UHD Graphics', 'HD Graphics'],
            'Matrox': ['Matrox'],
            'S3': ['S3'],
            '3dfx': ['3dfx', 'Voodoo'],
            'ATI': ['ATI'],
            'SiS': ['SiS'],
            'XGI': ['XGI']
        }
        
        product_name = product_name.upper()
        for vendor, keywords in vendors.items():
            for keyword in keywords:
                if keyword.upper() in product_name:
                    return vendor
        
        return "Unknown"
    
    @staticmethod
    def parse_product_list(html):
        """解析產品列表頁面"""
        soup = BeautifulSoup(html, 'html.parser')
        gpu_list = []
        
        try:
            # 1. 精確查找 class="processors" 的表格
            processors_table = soup.find('table', class_='processors')
            if not processors_table:
                logger.warning("找不到 class='processors' 的表格")
                return gpu_list

            # 2. 找到 thead 中的列標題
            thead = processors_table.find('thead', class_='colheader')
            if not thead:
                logger.warning("找不到 class='colheader' 的表頭")
                return gpu_list

            # 3. 找到所有的 th，確定 Product Name 的位置
            headers = thead.find_all('th')
            product_name_index = -1
            for i, th in enumerate(headers):
                if th.get_text(strip=True) == 'Product Name':
                    product_name_index = i
                    break

            if product_name_index == -1:
                logger.warning("找不到 Product Name 列")
                return gpu_list

            # 4. 直接找表格中的所有行（不通過 tbody）
            rows = processors_table.find_all('tr')
            
            # 跳過表頭行
            for row in rows[1:]:  # 從第二行開始
                cells = row.find_all('td')
                if len(cells) > product_name_index:
                    # 獲取產品名稱單元格
                    product_cell = cells[product_name_index]
                    
                    # 獲取產品名稱和連結
                    product_link = product_cell.find('a')
                    if product_link:
                        product_name = product_link.get_text(strip=True)
                        product_url = product_link.get('href')
                        
                        if product_name and product_url:
                            gpu_list.append({
                                'name': product_name,
                                'url': product_url
                            })
                            logger.info(f"找到 GPU: {product_name}")

            logger.info(f"共找到 {len(gpu_list)} 個 GPU")
            
        except Exception as e:
            logger.error(f"解析產品列表時出錯: {str(e)}")
            logger.exception(e)
        
        return gpu_list
    
    @staticmethod
    def parse_product_detail(html, url):
        """解析產品詳情頁面"""
        soup = BeautifulSoup(html, 'html.parser')
        product_data = {}
        specs_data = []
        
        try:
            # 獲取標題
            h1 = soup.find('h1')
            if h1:
                product_data['F_Product'] = h1.get_text(strip=True)
                product_data['F_Vendor'] = GPUParser.extract_vendor(product_data['F_Product'])
            
            # 獲取圖片 URL
            img_wrapper = soup.find(class_='gpudb-large-image__wrapper')
            if img_wrapper and img_wrapper.find('img'):
                product_data['F_GPU_Image_URL'] = img_wrapper.find('img').get('src')
            
            # 獲取描述
            desc = soup.find(class_='desc p')
            if desc:
                product_data['F_Desc'] = desc.get_text(strip=True)
            
            # 獲取規格區塊
            sections = soup.find_all(class_='sectioncontainer')
            
            for section in sections:
                # 跳過相對性能區塊
                if section.find(class_='gpudb-relative-performance'):
                    continue
                
                # 嘗試獲取區塊標題
                header = section.find(['h2'])
                if not header:
                    continue
                
                category_name = header.get_text(strip=True)
                
                # 嘗試查找定義列表 (dl)
                definition_lists = section.find_all('dl')
                for dl in definition_lists:
                    
                    # 獲取所有的定義術語和描述
                    terms = dl.find_all('dt')
                    descriptions = dl.find_all('dd')
                    
                    # 配對處理
                    for i in range(min(len(terms), len(descriptions))):
                        spec_name = terms[i].get_text(strip=True)
                        
                        # 處理描述中可能的鏈接
                        spec_value = ""
                        for content in descriptions[i].contents:
                            if content.name == 'a':
                                spec_value += content.get_text(strip=True)
                            elif isinstance(content, str):
                                spec_value += content.strip()
                        
                        spec_value = spec_value.strip()
                        
                        if spec_name and spec_value:
                            specs_data.append({
                                'category': category_name,
                                'name': spec_name,
                                'value': spec_value
                            })
            
            logger.info(f"解析 GPU {product_data.get('F_Product', 'Unknown')} 完成，找到 {len(specs_data)} 條規格")
        except Exception as e:
            logger.error(f"解析產品詳情時出錯: {str(e)}")
        
        return product_data, specs_data
    
    @staticmethod
    def parse_boards_section(html):
        """解析主板區域"""
        soup = BeautifulSoup(html, 'html.parser')
        board_data = []
        
        try:
            boards_section = soup.find(id='boards')
            if not boards_section:
                return board_data
            
            # 獲取標題
            h2 = boards_section.find('h2')
            section_title = h2.get_text(strip=True) if h2 else "Boards"
            
            # 獲取表格
            table = boards_section.find('table')
            if not table:
                return board_data
            
            # 獲取列頭
            thead = table.find('thead')
            if not thead:
                return board_data
            
            header_cells = thead.find_all('th', class_='sort-key')
            headers = [cell.get_text(strip=True) for cell in header_cells]
            
            # 獲取資料行
            tbody = table.find('tbody')
            if not tbody:
                return board_data
            
            rows = tbody.find_all('tr')
            for row in rows:
                board_info = {'title': section_title}
                
                # 獲取主板名稱和連結
                title_cell = row.find(class_='board-table-title__inner')
                if title_cell and title_cell.find('a'):
                    link = title_cell.find('a')
                    board_info['name'] = link.get_text(strip=True)
                    board_info['url'] = link.get('href')
                
                # 獲取評測連結
                review_link = row.find('a', class_='board-review-by-tpu')
                if review_link:
                    board_info['review_url'] = review_link.get('href')
                
                # 獲取規格數據
                cells = row.find_all('td')
                for i, header in enumerate(headers):
                    if i < len(cells):
                        board_info[header] = cells[i].get_text(strip=True)
                
                board_data.append(board_info)
        except Exception as e:
            logger.error(f"解析主板區域時出錯: {str(e)}")
        
        return board_data
    
    @staticmethod
    def parse_review_options(html):
        """解析評測頁面選項"""
        soup = BeautifulSoup(html, 'html.parser')
        options = []
        
        try:
            # 尋找下拉選單
            select = soup.find(id='pagesel')
            if not select:
                return options
            
            # 獲取所有選項
            all_options = select.find_all('option')
            
            # 尋找指定選項
            target_keywords = [
                'Pictures & Teardown',
                'Temperatures & Fan noise',
                'Cooler Performance Comparison',
                'Overclocking & Power Limits'
            ]
            
            for option in all_options:
                text = option.get_text(strip=True)
                value = option.get('value')
                
                # 移除數字前綴 (如 "4-", "39-" 等)
                clean_text = re.sub(r'^\d+\-\s*', '', text)
                
                for keyword in target_keywords:
                    if keyword.lower() in clean_text.lower() and value:
                        options.append({
                            'text': clean_text,  # 存儲移除數字前綴後的文本
                            'original_text': text,  # 保留原始文本供參考
                            'value': value
                        })
                        break
        except Exception as e:
            logger.error(f"解析評測選項時出錯: {str(e)}")
        
        return options
    
    @staticmethod
    def parse_review_content(html, review_type):
        """解析評測內容"""
        soup = BeautifulSoup(html, 'html.parser')
        content = {}
        review_data = []
        images_data = []  # 存儲圖片數據
        
        try:
            # 首先嘗試尋找 class="text p" 內的所有 h2 標籤
            text_divs = soup.find_all('div', class_='text p')
            found_title = False
            h2_contents = []  # 用於存儲所有 h2 及其內容
            
            if text_divs:
                # 遍歷所有 text div
                for div in text_divs:
                    # 獲取該 div 中的所有 h2 標籤
                    h2_tags = div.find_all('h2')
                    
                    # 如果找到 h2 標籤
                    if h2_tags:
                        # 使用第一個 h2 作為主標題（如果還沒有標題的話）
                        if not found_title:
                            content['title'] = h2_tags[0].get_text(strip=True)
                            found_title = True
                        
                        # 遍歷該 div 中的所有 h2 標籤
                        for i in range(len(h2_tags)):
                            current_h2 = h2_tags[i]
                            next_h2 = h2_tags[i + 1] if i + 1 < len(h2_tags) else None
                            
                            # 收集當前 h2 的內容
                            section_content = []
                            current = current_h2.next_sibling
                            
                            # 收集到下一個 h2 之前的所有內容
                            while current and (not next_h2 or current != next_h2):
                                if isinstance(current, str):
                                    text = current.strip()
                                    if text:
                                        section_content.append(text)
                                elif current.name in ['p', 'span', 'div']:
                                    text = current.get_text(strip=True)
                                    if text:
                                        section_content.append(text)
                                current = current.next_sibling
                            
                            # 將該部分添加到結果中
                            h2_contents.append({
                                'title': current_h2.get_text(strip=True),
                                'content': '\n'.join(section_content)
                            })
                
                # 將所有內容合併到 body 中
                content['sections'] = h2_contents
                content['body'] = '\n\n'.join(section['content'] for section in h2_contents)
            
            # 提取圖片元素
            responsive_images = soup.find_all('div', class_='responsive-image-xx')
            current_section = "General"
            
            # 尋找所有標題，用於確定圖片所屬區域
            headers = soup.find_all(['h2'])
            header_positions = {}
            
            for header in headers:
                header_text = header.get_text(strip=True)
                header_positions[header] = {
                    'text': header_text,
                    'position': header.sourceline  # 獲取元素在源碼中的行號
                }
            
            # 處理每個響應式圖片
            for img_div in responsive_images:
                # 查找該圖片前面最近的標題
                img_position = img_div.sourceline
                closest_header = None
                closest_distance = float('inf')
                
                for header, data in header_positions.items():
                    if data['position'] < img_position and img_position - data['position'] < closest_distance:
                        closest_distance = img_position - data['position']
                        closest_header = data['text']
                
                section = closest_header if closest_header else current_section
                
                # 提取圖片 URL
                img_tag = img_div.find('img')
                if img_tag and img_tag.get('src'):
                    img_url = img_tag.get('src')
                    img_alt = img_tag.get('alt', '')
                    
                    # 添加到圖片數據列表
                    images_data.append({
                        'section': section,
                        'url': img_url,
                        'alt': img_alt,
                        'type': 'chart' if 'chart' in img_url.lower() or 'graph' in img_url.lower() else 'image'
                    })
                    
                    # 添加到結構化數據中
                    review_data.append({
                        'data_type': 'Image',
                        'data_key': section,
                        'data_value': img_url,
                        'data_unit': 'URL',
                        'product_name': content.get('title', '')
                    })
            
            # 更新每個章節的圖片
            for section in h2_contents:
                section_title = section['title']
                section['images'] = [img for img in images_data if img['section'] == section_title]
            
            # 添加圖片資訊到返回內容
            content['images'] = images_data
            
            # 根據評測類型提取結構化數據
            if "Temperature" in review_type or "Fan noise" in review_type:
                # 提取溫度表格
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr', class_='active')
                    
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            product_name = cells[0].get_text(strip=True)
                            
                            # 根據表格結構提取數據
                            data_entries = []
                            for i, cell in enumerate(cells[1:], 1):
                                value_text = cell.get_text(strip=True)
                                
                                # 嘗試提取數值和單位
                                match = re.search(r'(\d+(?:\.\d+)?)\s*([°C|dBA|RPM|W]+)', value_text)
                                if match:
                                    value, unit = match.groups()
                                    data_entries.append({
                                        'product_name': product_name,
                                        'data_key': f'col_{i}',
                                        'data_value': value,
                                        'data_unit': unit
                                    })
                            
                            review_data.extend(data_entries)
                            
            # 超頻和功耗限制表格解析
            elif "Overclocking" in review_type or "Power Limits" in review_type:
                # 找到所有表格
                tables = soup.find_all('table')
                for table in tables:
                    # 獲取表頭
                    headers = []
                    thead = table.find('thead')
                    if thead:
                        header_cells = thead.find_all('th')
                        headers = [cell.get_text(strip=True) for cell in header_cells]
                    
                    # 提取數據行
                    rows = table.find('tbody').find_all('tr', class_='active') if table.find('tbody') else []
                    
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            product_name = cells[0].get_text(strip=True)
                            
                            # 提取每個單元格的數據
                            for i, cell in enumerate(cells[1:], 1):
                                if i < len(headers):
                                    header_name = headers[i]
                                else:
                                    header_name = f'col_{i}'
                                
                                value_text = cell.get_text(strip=True)
                                
                                # 嘗試提取數值和單位
                                # 匹配如 "3244 MHz", "103.0 FPS", "360/400 W" 等格式
                                match = re.search(r'(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?)\s*([A-Za-z]+)?', value_text)
                                if match:
                                    value = match.group(1)
                                    unit = match.group(2) if match.group(2) else ""
                                    
                                    review_data.append({
                                        'data_type': 'Overclock',
                                        'data_key': header_name,
                                        'data_value': value,
                                        'data_unit': unit,
                                        'product_name': product_name
                                    })
            
            # 電路板分析特定數據提取
            elif "Circuit" in review_type or "PCB" in review_type:
                # 提取 GPU VRM 相數
                gpu_phase_match = re.search(r'A\s+(\d+\+\d+)\s+phase\s+VRM\s+powers\s+the\s+GPU', content['body'])
                if gpu_phase_match:
                    review_data.append({
                        'data_type': 'GPU',
                        'data_key': 'MEM項數',
                        'data_value': gpu_phase_match.group(1),
                        'data_unit': '',  # 移除 phase 單位
                        'product_name': content.get('title', '')
                    })
                
                # 提取 GPU 控制器型號
                gpu_controller_match = re.search(r'managed\s+by\s+a\s+Monolithic\s+Power\s+Systems\s+(MP\d+[A-Z]*)', content['body'])
                if gpu_controller_match:
                    review_data.append({
                        'data_type': 'GPU',
                        'data_key': '控制器型號',
                        'data_value': gpu_controller_match.group(1),
                        'data_unit': '',
                        'product_name': content.get('title', '')
                    })
                
                # 提取 GPU MOS規格
                gpu_mos_match = re.search(r'GPU\s+power\s+phases\s+use\s+(\w+\s+\w+\s+\w+\s+DrMOS)(?:\s+with\s+a\s+rating\s+of\s+(\d+)\s+A)?', content['body'])
                if gpu_mos_match:
                    mos_spec = gpu_mos_match.group(1)
                    if gpu_mos_match.group(2):  # 如果有電流規格
                        mos_spec += f" {gpu_mos_match.group(2)}A"
                    
                    review_data.append({
                        'data_type': 'GPU',
                        'data_key': 'MOS規格',
                        'data_value': mos_spec,
                        'data_unit': '',
                        'product_name': content.get('title', '')
                    })
                
                # 提取 Memory VRM 相數
                mem_phase_match = re.search(r'memory\s+chips\s+is\s+a\s+(\d+\+\d+)\s+phase\s+VRM', content['body'])
                if mem_phase_match:
                    review_data.append({
                        'data_type': 'Memory',
                        'data_key': 'MEM項數',
                        'data_value': mem_phase_match.group(1),
                        'data_unit': '',  # 移除 phase 單位
                        'product_name': content.get('title', '')
                    })
                
                # 提取 Memory 控制器型號
                mem_controller_match = re.search(r'driven\s+by\s+a\s+(?:second\s+)?Monolithic\s+Power\s+Systems\s+(MP\d+[A-Z]*)', content['body'])
                if mem_controller_match:
                    review_data.append({
                        'data_type': 'Memory',
                        'data_key': '控制器型號',
                        'data_value': mem_controller_match.group(1),
                        'data_unit': '',
                        'product_name': content.get('title', '')
                    })
                
                # 提取 Memory 芯片型號和速率
                mem_chip_match = re.search(r'memory\s+chips\s+are\s+made\s+by\s+(\w+),\s+and\s+bear\s+the\s+model\s+number\s+([\w\-]+),\s+they\s+are\s+rated\s+for\s+(\d+)\s+Gbps', content['body'])
                if mem_chip_match:
                    manufacturer = mem_chip_match.group(1)
                    model = mem_chip_match.group(2)
                    speed = mem_chip_match.group(3)
                    
                    review_data.append({
                        'data_type': 'Memory',
                        'data_key': 'MOS規格',
                        'data_value': f"{model} {speed}",
                        'data_unit': 'Gbps',
                        'product_name': content.get('title', '')
                    })
                
                # 提取 Memory MOS規格 (如果有)
                mem_mos_match = re.search(r'memory\s+is\s+handled\s+by\s+(\w+\s+\w+\s+\w+\s+DrMOS)', content['body'])
                if mem_mos_match:
                    review_data.append({
                        'data_type': 'Memory',
                        'data_key': 'MOS規格',
                        'data_value': mem_mos_match.group(1),
                        'data_unit': '',
                        'product_name': content.get('title', '')
                    })
            
            # 從文本中提取其他通用數據
            # 提取重量
            weight_match = re.search(r'weighs\s+(\d+(?:\.\d+)?)\s*g', content['body'])
            if weight_match:
                review_data.append({
                    'data_type': 'Weight',
                    'data_key': 'weight',
                    'data_value': weight_match.group(1),
                    'data_unit': 'g',
                    'product_name': content.get('title', '')
                })
            
            # 提取熱管數量
            heatpipe_match = re.search(r'(\w+)\s+heatpipes', content['body'])
            if heatpipe_match:
                # 將文字數字轉換為數字
                word_to_num = {
                    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
                    'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10'
                }
                
                heatpipe_count = heatpipe_match.group(1).lower()
                if heatpipe_count in word_to_num:
                    heatpipe_count = word_to_num[heatpipe_count]
                
                review_data.append({
                    'data_type': 'Heatpipes',
                    'data_key': 'count',
                    'data_value': heatpipe_count,
                    'data_unit': 'count',
                    'product_name': content.get('title', '')
                })
            
        except Exception as e:
            logger.error(f"解析評測內容時出錯: {str(e)}")
        
        return content, review_data