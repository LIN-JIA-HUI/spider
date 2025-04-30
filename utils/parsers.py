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
            
            # ===== 改進的圖片 URL 獲取邏輯 =====
            img_url = None
            
            # 嘗試方法 1: 標準圖片包裝器
            img_wrapper = soup.find(class_='gpudb-large-image__wrapper')
            if img_wrapper:
                img_tag = img_wrapper.find('img')
                if img_tag and img_tag.get('src'):
                    img_url = img_tag.get('src')
                    logger.info(f"通過圖片包裝器找到圖片: {img_url}")
            
            # 嘗試方法 2: 產品展示區域
            if not img_url:
                product_imgs = soup.select('.product-showcase img, .card-body img, .product-image img')
                if product_imgs:
                    img_url = product_imgs[0].get('src')
                    logger.info(f"通過產品展示區找到圖片: {img_url}")
            
            # 嘗試方法 3: 尋找任何可能的大圖片
            if not img_url:
                all_imgs = soup.find_all('img')
                for img in all_imgs:
                    src = img.get('src', '')
                    if 'large' in src or 'full' in src or 'big' in src:
                        img_url = src
                        logger.info(f"通過大圖片搜索找到圖片: {img_url}")
                        break
            
            # 嘗試方法 4: 任何圖片
            if not img_url and all_imgs:
                for img in all_imgs:
                    src = img.get('src', '')
                    if src and not src.endswith(('.gif', '.ico')):
                        img_url = src
                        logger.info(f"通過備選方法找到圖片: {img_url}")
                        break
            
            # 確保 URL 完整
            if img_url:
                if img_url.startswith('/'):
                    base_url = 'https://www.techpowerup.com'
                    img_url = urljoin(base_url, img_url)
                    
                product_data['F_GPU_Image_URL'] = img_url
                logger.info(f"最終圖片 URL: {img_url}")
            else:
                logger.warning(f"無法為產品 {product_data.get('F_Product', 'Unknown')} 找到圖片")
            # ===== 圖片 URL 獲取邏輯結束 =====
            
            # 獲取描述
            desc = soup.find(class_='desc p')
            if desc:
                product_data['F_Desc'] = desc.get_text(strip=True)
            
            # 獲取規格區塊
            sections = soup.find_all(class_='sectioncontainer')
            with open('sections_output.txt', 'w', encoding='utf-8') as f:
            # 首先输出 sections 的总数
                f.write(f'Total sections found: {len(sections)}\n\n')

                # 然后遍历 sections，输出每个 section 的内容
                for idx, container in enumerate(sections):
                    sections_in_container = container.find_all('section')  # 查找当前 container 中的所有 section
                    for section_idx,section in enumerate(sections_in_container):
                        # 跳過相對性能區塊
                        f.write(f'Section {idx + 1}, Section {section_idx + 1}:')
                        f.write(section.prettify()) 
                        f.write('\n')

                        if section.find(class_='details jsonly gpudb-relative-performance'):
                            f.write('遇到圖表')
                            f.write('\n')
                            continue
                        
                        # 嘗試獲取區塊標題
                        header = section.find(['h2'])
                        if header:
                            f.write(f'Found header: {header.text}')
                            f.write('\n')
                        else:
                            f.write(f'Not header')
                            f.write('\n')
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
                                    if hasattr(content, 'name') and content.name == 'a':
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
                            # 處理表格數據 (如有)
                            tables = section.find_all('table')
                            for table in tables:
                                headers = []
                                thead = table.find('thead')
                                if thead:
                                    header_cells = thead.find_all('th')
                                    headers = [cell.get_text(strip=True) for cell in header_cells]
                                
                                tbody = table.find('tbody')
                                if tbody:
                                    rows = tbody.find_all('tr')
                                    for row in rows:
                                        cells = row.find_all(['td', 'th'])
                                        if len(cells) > 1:
                                            spec_name = cells[0].get_text(strip=True)
                                            spec_value = cells[1].get_text(strip=True)
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
    def parse_board_details(html, url):
        """解析主板詳細資訊頁面獲取規格"""
        soup = BeautifulSoup(html, 'html.parser')
        specs = {}
        
        try:
            # 查找規格區塊
            sections = soup.find_all(class_='sectioncontainer')
            
            for section in sections:
                header = section.find(['h2'])
                if not header:
                    continue
                
                category_name = header.get_text(strip=True)
                
                # 查找定義列表
                definition_lists = section.find_all('dl')
                category_specs = {}
                
                for dl in definition_lists:
                    terms = dl.find_all('dt')
                    descriptions = dl.find_all('dd')
                    
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
                            category_specs[spec_name] = spec_value
                
                if category_specs:
                    specs[category_name] = category_specs
            
            # 查找其他表格數據
            tables = soup.find_all('table')
            for table in tables:
                table_header = table.find_previous(['h2', 'h3', 'h4'])
                if table_header:
                    table_category = table_header.get_text(strip=True)
                else:
                    table_category = "主板規格"
                
                table_specs = {}
                rows = table.find_all('tr')
                
                # 跳過表頭行
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        spec_name = cells[0].get_text(strip=True)
                        spec_value = cells[1].get_text(strip=True)
                        if spec_name and spec_value:
                            table_specs[spec_name] = spec_value
                
                if table_specs:
                    specs[table_category] = table_specs
            
            logger.info(f"解析主板規格完成，發現 {sum(len(specs[cat]) for cat in specs)} 條規格信息")
        except Exception as e:
            logger.error(f"解析主板規格時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return specs
    
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
            
            # 尋找指定選項 - 擴展關鍵詞列表
            target_keywords = [
                'Pictures & Teardown',
                'Pictures & Cooler',
                'Temperatures & Fan noise',
                'Cooler Performance Comparison',
                'Overclocking & Power Limits',
                'Overclocking',
                'Circuit Board Analysis',
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
                        # logger.info(f"找到評測選項: {clean_text}, URL: {value}")
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
        review_specs_data = []
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
            if "Temperature" in review_type or "Fan noise" in review_type or "Noise" in review_type:
                # 找到表格和active行
                table = soup.find('table', class_='tputbl')
                
                if table and (active_row := table.find('tr', class_='active')):
                    rows = table.find_all('tr')
                    
                    if len(rows) >= 3:
                        # 獲取表頭和欄位名稱
                        category_row = rows[1]  # Idle/Gaming 所在行
                        field_row = rows[2]     # GPU/Memory/Noise 所在行
                        
                        # 獲取欄位名稱
                        field_names = [cell.get_text(strip=True).lower() for cell in field_row.find_all('th')]
                        
                        # 找出 idle 和 Gaming 的範圍
                        category_cells = category_row.find_all('th')
                        current_index = 0
                        idle_range = gaming_range = None
                        
                        for cell in category_cells:
                            cell_text = cell.get_text(strip=True).lower()
                            colspan = int(cell.get('colspan', 1))
                            
                            if cell_text == 'idle':
                                idle_range = (current_index, current_index + colspan - 1)
                            elif cell_text == 'gaming':
                                gaming_range = (current_index, current_index + colspan - 1)
                            
                            current_index += colspan
                        
                        # 動態尋找各欄位的索引
                        field_indices = {}
                        for i, name in enumerate(field_names):
                            if idle_range and i >= idle_range[0] and i <= idle_range[1] and name == 'gpu':
                                field_indices['idle_gpu'] = i
                            if gaming_range and i >= gaming_range[0] and i <= gaming_range[1]:
                                if name == 'gpu':
                                    field_indices['gaming_gpu'] = i
                                elif name == 'memory':
                                    field_indices['memory'] = i
                                elif name == 'noise':
                                    field_indices['gaming_noise'] = i
                        
                        # 獲取顯卡名稱和單元格
                        card_name = active_row.find('th').get_text(strip=True) if active_row.find('th') else "未知顯卡"
                        cells = active_row.find_all('td')
                        
                        # 抓取各項資料
                        results = {}
                        field_mapping = {
                            'idle_gpu': ('IdleGPUTemp', r'(\d+)[°℃]'),
                            'gaming_gpu': ('GamingGPUTemp', r'(\d+)[°℃]'),
                            'memory': ('MemoryTemp', r'(\d+)[°℃]'),
                            'gaming_noise': ('NoiseLevel', r'(\d+(?:\.\d+)?)\s*dBA')
                        }
                        
                        # 遍歷字段抓取數據
                        for field_key, (display_name, regex_pattern) in field_mapping.items():
                            if field_key in field_indices:
                                cell_index = field_indices[field_key] - 1  # 調整索引偏移
                                if 0 <= cell_index < len(cells):
                                    cell_text = cells[cell_index].get_text(strip=True)
                                    if match := re.search(regex_pattern, cell_text):
                                        value = match.group(1)
                                        results[field_key] = value
                                        review_specs_data.append({
                                            'category': 'Physical Properties',
                                            'name': display_name,
                                            'value': value
                                        })
                                        logger.info(f"{card_name} - 成功抓取{display_name}: {value}")
                    else:
                        logger.warning("表格結構不完整，未找到足夠的行")
                else:
                    logger.warning("未找到溫度或噪音相關的表格或被選中顯卡")             
            # 超頻和功耗限制表格解析
            # 超頻表格解析 - 簡化版本
            # 根據評測類型提取超頻資料
            elif "Overclocking" in review_type or "Power Limits" in review_type:
                # 找到表格和active行
                table = soup.find('table', class_='tputbl')
                
                if table and (active_row := table.find('tr', class_='active')):
                    logger.info("找到被選中的顯卡行")
                    rows = table.find_all('tr')
                    
                    if len(rows) >= 2:
                        # 獲取欄位名稱行（通常是第二行，索引1）
                        field_row = rows[1]
                        field_cells = field_row.find_all('th')
                        
                        # 獲取欄位名稱（跳過第一個，因為它是顯卡名稱）
                        field_names = [cell.get_text(strip=True).lower() for cell in field_cells][1:]
                        logger.info(f"欄位名稱: {field_names}")
                        
                        # 獲取顯卡名稱和單元格
                        card_name = active_row.find('th').get_text(strip=True) if active_row.find('th') else "未知顯卡"
                        cells = active_row.find_all('td')
                        
                        # 定義欄位映射（欄位顯示名稱與資料庫存儲名稱的對應）
                        field_mapping = {
                            'avg. gpu clock': 'AvgGPUClock',
                            'max. memory clock': 'MaxMemoryClock',
                            'performance': 'Performance',
                            'pwr limit def/max': 'PwrLimitDefMax',
                            'oc perf at max pwr': 'OCPerfMaxPwr'
                        }
                        
                        # 動態構建欄位索引映射
                        field_indices = {}
                        for i, name in enumerate(field_names):
                            name_lower = name.lower()
                            if name_lower in field_mapping:
                                field_indices[field_mapping[name_lower]] = i
                        
                        logger.info(f"欄位索引: {field_indices}")
                        
                        # 抓取各項資料
                        for db_field_name, index in field_indices.items():
                            if index < len(cells):
                                value = cells[index].get_text(strip=True)
                                if value and value != "…":
                                    review_specs_data.append({
                                        'category': 'TDP Compare',
                                        'name': db_field_name,
                                        'value': value
                                    })
                                    logger.info(f"{card_name} - 成功抓取 {db_field_name}: {value}")
                    else:
                        logger.warning("表格結構不完整，未找到足夠的行")
                else:
                    logger.warning("未找到超頻資料表格或被選中顯卡")
            
            # ========== 改進的電路板分析數據提取 ==========
            elif "Circuit" in review_type or "PCB" in review_type or "Board Analysis" in review_type:
                logger.info(f"開始分析電路板資料，內容長度: {len(content['body'])}")
                logger.debug(f"內容前200字符: {content['body'][:200]}...")
                
                # 使用多種模式匹配 GPU VRM 相數
                gpu_phase_patterns = [
                    # 添加通用模式在最上方
                    r'(?:A|An)\s+(\d+\+\d+|\d+)[\s-]*phase\s+VRM\s+powers\s+the\s+GPU',
                    r'GPU\s+(?:is\s+powered|voltage\s+is(?:\s+powered)?)\s+by\s+(?:a|an)?\s+(\d+\+\d+|\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)[\s-]*phase',
                    # 下面是原有的模式
                    r'A\s+(\d+\+\d+)\s+phase\s+VRM\s+powers\s+the\s+GPU',
                    r'(\d+\+\d+)[\s-]*phase\s+VRM.*powers\s+the\s+GPU',
                    r'GPU\s+is\s+powered\s+by\s+a\s+(\d+\+\d+)[\s-]*phase',
                    r'GPU\s+voltage\s+is\s+(\d+)[\s-]*phase',
                    r'GPU.*?(\d+\+\d+)[\s-]*phase\s+VRM',
                    r'The\s+GPU\s+uses\s+a\s+(\d+\+\d+)[\s-]*phase',
                    r'A\s+(?:massive\s+)?(\d+)[\s-]*phase\s+VRM\s+powers\s+the\s+GPU',
                    r'An\s+(\d+)[\s-]*phase\s+VRM\s+powers\s+the\s+GPU',
                    r'GPU\s+voltage\s+is\s+powered\s+by.*?running\s+with\s+(\d+)\s+power\s+phases',
                    r'GPU\s+voltage\s+is\s+a\s+(\w+)[\s-]*phase\s+design',
                    r'running\s+with\s+(\d+)\s+power\s+phases'
                ]
                
                gpu_phase_found = False
                for pattern in gpu_phase_patterns:
                    gpu_phase_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if gpu_phase_match:
                        gpu_phase_found = True
                        review_data.append({
                            'data_type': 'GPU',
                            'data_key': 'MEM項數',
                            'data_value': gpu_phase_match.group(1),
                            'data_unit': 'phase',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'GPU',
                            'name': 'GPUMEMCount',
                            'value': gpu_phase_match.group(1)
                        })
                        logger.info(f"成功匹配GPU相數: {gpu_phase_match.group(1)}")
                        break
                
                if not gpu_phase_found:
                    logger.warning(f"未找到 GPU VRM 相數資料，評測標題: {content.get('title', '')}")
                
                # 使用多種模式匹配 GPU 控制器型號
                gpu_controller_patterns = [
                    # 添加通用模式在最上方
                    r'(?:managed|controlled)\s+by\s+(?:a|an)\s+(?:\w+\s+)?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'controller\s+(?:is|chip\s+is)\s+(?:a|an)?\s+(?:\w+\s+)?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'(\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)\s+controller',
                    r'voltage\s+controller.*?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'voltage\s+is\s+powered\s+by\s+(?:an\s+)?(?:expensive\s+)?(\w+\s+\w+\d+[A-Z0-9-]+)',
                    # 下面是原有的模式
                    r'managed\s+by\s+a\s+Monolithic\s+Power\s+Systems\s+(MP\d+[A-Z]*)',
                    r'controller\s+is\s+(?:a\s+)?(?:Monolithic\s+Power\s+Systems\s+)?(MP\d+[A-Z]*)',
                    r'(MP\d+[A-Z]*)\s+controller',
                    r'controller\s+chip\s+is\s+(?:a\s+)?(?:Monolithic\s+Power\s+Systems\s+)?(MP\d+[A-Z]*)',
                    r'GPU\s+voltage\s+is\s+powered\s+by\s+(?:an\s+)?(?:expensive\s+)?(\w+\s+\w+\d+[A-Z0-9]*)',
                    r'voltage\s+is\s+powered\s+by\s+(?:an\s+)?(?:expensive\s+)?(\w+\s+\w+\d+[A-Z0-9]*)',
                    r'controlled\s+by\s+(?:an\s+)?(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'managed\s+by\s+an\s+(\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'controlled\s+by\s+an\s+(\w+\s+\w+\d+[A-Z0-9-]+\s+\(\w+\))',
                    r'controlled\s+by\s+a\s+uPI\s+(uP\d+[A-Z0-9]+)\s+voltage\s+controller',
                    r'design\s+managed\s+by\s+an\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'voltage\s+controller.*?(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)'
                ]
                
                controller_found = False
                for pattern in gpu_controller_patterns:
                    gpu_controller_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if gpu_controller_match:
                        controller_found = True
                        review_data.append({
                            'data_type': 'GPU',
                            'data_key': '控制器型號',
                            'data_value': gpu_controller_match.group(1),
                            'data_unit': '',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'GPU',
                            'name': 'GPUControllerModel',
                            'value': gpu_controller_match.group(1)
                        })
                        logger.info(f"成功匹配GPU控制器: {gpu_controller_match.group(1)}")
                        break
                
                if not controller_found:
                    logger.warning(f"未找到 GPU 控制器型號資料，評測標題: {content.get('title', '')}")
                
                # 使用多種模式匹配 GPU MOS 規格
                gpu_mos_patterns = [
                    # 添加通用模式在最上方
                    r'(?:All\s+)?GPU\s+power\s+phases\s+use\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\w+\d+)?(?:\s+\([A-Z0-9]+\))?)\s+DrMOS(?:\s+components)?.*?(?:with\s+a\s+rating\s+of|rated\s+for)\s+(\d+)\s+A',
                    r'DrMOS\s+for\s+the\s+GPU\s+are\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+).*?rated\s+for\s+(\d+)\s+A',
                    r'DrMOS\s+devices\s+are\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'GPU.*?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\w+\d+)?(?:\s+\([A-Z0-9]+\))?)\s+DrMOS.*?(\d+)\s+A',
                    # 下方是原有的模式
                    r'GPU\s+power\s+phases\s+use\s+(\w+\s+\w+\s+\w+\s+DrMOS)(?:\s+with\s+a\s+rating\s+of\s+(\d+)\s+A)?',
                    r'(\w+\s+\w+\s+\w+\s+DrMOS)(?:\s+rated\s+for\s+(\d+)\s+A)?',
                    r'DrMOS\s+devices\s+are\s+(\w+\s+\w+\s+\w+)',
                    r'(\w+\s+\w+\d+[A-Z0-9]*\s+DrMOS)\s+chips\s+are\s+used',
                    r'DrMOS\s+chips\s+are\s+(\w+\s+\w+\d+[A-Z0-9]*)',
                    r'DrMOS\s+chips\s+with\s+a\s+(\d+)\s+A\s+rating'
                    r'DrMOS\s+for\s+the\s+GPU\s+are\s+(\w+\s+\d+[A-Z0-9-]+)',
                    r'GPU\s+power\s+phases\s+use\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\w+\d+)?)',
                    r'GPU.*?DrMOS\s+chips\s+with\s+a\s+(\d+)\s+A\s+rating',
                    r'(\w+\s+(?:&|and)\s+\w+\s+\w+\d+[A-Z0-9-]+)\s+DrMOS.*?GPU.*?rated\s+for\s+(\d+)\s+A',
                    r'All\s+GPU.*?DrMOS.*?rated\s+for\s+(\d+)\s+A',
                    r'All\s+GPU\s+power\s+phases\s+use\s+(\w+\s+\w+\d+[A-Z]+)\s+DrMOS,\s+rated\s+for\s+(\d+)\s+A',
                    r'All\s+GPU\s+power\s+phases\s+use\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)'
                ]
                
                mos_found = False
                for pattern in gpu_mos_patterns:
                    gpu_mos_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if gpu_mos_match:
                        mos_found = True
                        mos_spec = gpu_mos_match.group(1)
                        if len(gpu_mos_match.groups()) > 1 and gpu_mos_match.group(2):  # 如果有電流規格
                            mos_spec = gpu_mos_match.group(1)
                            if len(gpu_mos_match.groups()) > 1 and gpu_mos_match.group(2):  # 如果有電流規格
                                mos_spec += f" {gpu_mos_match.group(2)}A"
                            
                            review_data.append({
                                'data_type': 'GPU',
                                'data_key': 'MOS規格',
                                'data_value': mos_spec,
                                'data_unit': '',
                                'product_name': content.get('title', '')
                            })
                            review_specs_data.append({
                                'category': 'GPU',
                                'name': 'GPUMOSSpec',
                                'value': mos_spec
                            })
                            logger.info(f"成功匹配GPU MOS規格: {mos_spec}")
                            break
                    
                    if not mos_found:
                        logger.warning(f"未找到 GPU MOS規格資料，評測標題: {content.get('title', '')}")
                    
                # 使用多種模式匹配 Memory VRM 相數
                mem_phase_patterns = [
                    # 添加通用模式在最上方
                    r'(?:memory|Memory)\s+(?:chips\s+is|is\s+provided\s+by|power\s+is|voltage\s+uses)\s+(?:a|an)?\s+(\d+\+\d+|\d+|one|two|three|four|five|six|seven|eight|nine|ten)[\s-]*phase',
                     r'Powering\s+the\s+(?:six\s+)?(?:GDDR\d+\s+)?memory\s+chips\s+is\s+(?:a|an)?\s+(\d+\+\d+|\d+)[\s-]*phase\s+VRM',
                    # 下面是原有的模式
                    r'memory\s+chips\s+is\s+a\s+(\d+\+\d+)\s+phase\s+VRM',
                    r'memory\s+is\s+provided\s+by\s+a\s+(\d+\+\d+)\s+phase',
                    r'memory\s+power\s+is\s+a\s+(\d+\+\d+)\s+phase',
                    r'Memory\s+voltage\s+is\s+a\s+(\w+)[\s-]*phase',
                    r'memory\s+voltage\s+uses\s+a\s+(\d+\+\d+)\s+phase',
                    r'memory\s+chips\s+is\s+a\s+(\d+)[\s-]*phase\s+VRM',
                    r'Powering\s+the\s+(?:GDDR\d+\s+)?memory\s+chips\s+is\s+a\s+(\d+)[\s-]*phase\s+VRM',
                    r'Powering\s+the\s+(?:six\s+)?(?:GDDR\d+\s+)?memory\s+chips\s+is\s+a\s+(\d+)[\s-]*phase\s+VRM',
                    r'voltage\s+uses\s+a\s+(\d+)[\s-]*phase'
                ]
                    
                mem_phase_found = False
                for pattern in mem_phase_patterns:
                    mem_phase_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if mem_phase_match:
                        mem_phase_found = True
                        review_data.append({
                            'data_type': 'Memory',
                            'data_key': 'MEM項數',
                            'data_value': mem_phase_match.group(1),
                            'data_unit': 'phase',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'Memory',
                            'name': 'MemoryMEMCount',
                            'value': mem_phase_match.group(1)
                        })
                        logger.info(f"成功匹配記憶體相數: {mem_phase_match.group(1)}")
                        break
                
                if not mem_phase_found:
                    logger.warning(f"未找到記憶體相數資料，評測標題: {content.get('title', '')}")
                    
                # 使用多種模式匹配 Memory 控制器型號
                mem_controller_patterns = [
                    # 添加通用模式在最上方
                    r'(?:driven|controlled)\s+by\s+(?:a|an|another|the\s+same)\s+(?:second\s+)?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'(?:memory|Memory)\s+(?:controller|voltage)\s+is\s+(?:controlled\s+by|(?:a|an)?\s+\w+[\s-]*phase\s+design\s+generated\s+by)\s+(?:a|an)?\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'Both\s+are\s+managed\s+by\s+another\s+(\w+(?:\s+&|\s+and)?\s+\w+)',
                    # 下面是原有的模式
                    r'driven\s+by\s+a\s+(?:second\s+)?Monolithic\s+Power\s+Systems\s+(MP\d+[A-Z]*)',
                    r'memory\s+controller\s+is\s+(?:a\s+)?(?:Monolithic\s+Power\s+Systems\s+)?(MP\d+[A-Z]*)',
                    r'driven\s+by\s+a\s+(?:second\s+)?(\w+\s+\w+\d+[A-Z]*)\s+controller',
                    r'driven\s+by\s+a\s+(\w+\s+\w+\d+[A-Z]*)',
                    r'driven\s+by\s+another\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'driven\s+by\s+another\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'controller\s+is\s+(?:a\s+)?(\w+\s+\w+\d+[A-Z]*)',
                    r'Memory\s+voltage\s+uses.*?controlled\s+by\s+(?:an\s+)?(\w+\s+\w+\d+[A-Z0-9]*)',
                    r'Memory\s+voltage\s+is\s+a.*?design\s+generated\s+by\s+a\s+(\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'Both\s+are\s+managed\s+by\s+another\s+(\w+\s+&\s+\w+)\s+controller',
                    r'driven\s+by\s+the\s+same\s+(\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'design\s+controlled\s+by\s+(?:an\s+)?(\w+\s+\w+\d+[A-Z0-9]*)'
                ]
                
                mem_controller_found = False
                for pattern in mem_controller_patterns:
                    mem_controller_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if mem_controller_match:
                        mem_controller_found = True
                        review_data.append({
                            'data_type': 'Memory',
                            'data_key': '控制器型號',
                            'data_value': mem_controller_match.group(1),
                            'data_unit': '',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'Memory',
                            'name': 'MemoryControllerModel',
                            'value': mem_controller_match.group(1)
                        })
                        logger.info(f"成功匹配記憶體控制器: {mem_controller_match.group(1)}")
                        break
                
                if not mem_controller_found:
                    logger.warning(f"未找到記憶體控制器型號資料，評測標題: {content.get('title', '')}")
                    
                # 使用多種模式匹配 Memory 芯片型號和速率
                # mem_chip_patterns = [
                #     r'memory\s+chips\s+are\s+made\s+by\s+(\w+),\s+and\s+bear\s+the\s+model\s+number\s+([\w\-]+),\s+they\s+are\s+rated\s+for\s+(\d+)\s+Gbps',
                #     r'(\w+)\s+([\w\-]+)\s+memory\s+chips.*?rated\s+(?:at|for)\s+(\d+)\s+Gbps',
                #     r'memory\s+chips\s+(?:are|from)\s+(\w+)\s+([\w\-]+).*?(\d+)\s+Gbps'
                # ]
                
                # mem_chip_found = False
                # for pattern in mem_chip_patterns:
                #     mem_chip_match = re.search(pattern, content['body'], re.IGNORECASE)
                #     if mem_chip_match:
                #         mem_chip_found = True
                #         manufacturer = mem_chip_match.group(1)
                #         model = mem_chip_match.group(2)
                #         speed = mem_chip_match.group(3)
                        
                #         review_data.append({
                #             'data_type': 'Memory',
                #             'data_key': '記憶體型號',
                #             'data_value': f"{manufacturer} {model} {speed}",
                #             'data_unit': 'Gbps',
                #             'product_name': content.get('title', '')
                #         })
                #         review_specs_data.append({
                #             'category': 'Memory',
                #             'name': 'MemoryControllerModel',
                #             'value': f"{manufacturer} {model} {speed}"
                #         })
                #         logger.info(f"成功匹配記憶體晶片型號: {manufacturer} {model} {speed}Gbps")
                #         break
                
                # if not mem_chip_found:
                #     logger.warning(f"未找到記憶體晶片型號資料，評測標題: {content.get('title', '')}")
                
                # 使用多種模式匹配 Memory MOS規格
                mem_mos_patterns = [
                    # 添加通用模式在最上方
                    r'(?:memory|Memory)\s+is\s+handled\s+by\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\w+\d+)?(?:\s+\([A-Z0-9]+\))?)\s+DrMOS(?:\s+chips)?.*?(?:with\s+a|rated\s+for)\s+(\d+)\s+A',
                    r'(?:memory|Memory)\s+VRM\s+uses\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+)\s+DrMOS',
                    r'(?:memory|Memory)\s+power\s+circuitry\s+uses\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+)\s+DrMOS',
                    r'For\s+(?:memory|Memory),\s+(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+).*?(?:with\s+a|rated\s+for)\s+(\d+)\s+A',
                    r'Just\s+like\s+GPU,\s+the\s+(?:memory|Memory).*?(\w+(?:\s+&|\s+and)?\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\w+\d+)?(?:\s+\([A-Z0-9]+\))?)\s+DrMOS.*?(\d+)\s+A',
                    # 下面是原有的模式
                    r'memory\s+is\s+handled\s+by\s+(\w+\s+\w+\s+\w+\s+DrMOS)',
                    r'memory\s+VRM\s+uses\s+(\w+\s+\w+\s+\w+\s+DrMOS)',
                    r'memory\s+power\s+circuitry\s+uses\s+(\w+\s+\w+\s+\w+\s+DrMOS)',
                    r'GPU\s+power\s+phases\s+use\s+(\w+\s+\w+\s+DrMOS)(?:\s+rated\s+for\s+(\d+)\s+A)?',
                    r'memory\s+is\s+handled\s+by\s+(\w+\s+\w+\d+[A-Z]*\s+DrMOS)\s+chips',
                    r'memory\s+is\s+handled\s+by\s+(\w+\s+&\s+\w+\s+\w+\d+[A-Z0-9-]+(?:\s+\([A-Z0-9]+\))?)',
                    r'For\s+memory,\s+(\w+\s+\d+[A-Z0-9-]+)',
                    r'For\s+memory,\s+(\w+\s+\w+\d+[A-Z0-9-]+)\s+DrMOS\s+with\s+a\s+(\d+)\s+A\s+rating\s+are\s+used',
                    r'memory\s+is\s+handled\s+by\s+(\w+\s+\w+\d+[A-Z0-9-]+)',
                    r'memory.*?DrMOS\s+chips\s+with\s+a\s+(\d+)\s+A\s+rating',
                    r'For\s+memory,\s+(\w+\s+(?:&|and)\s+\w+\s+\w+\d+[A-Z0-9-]+).*?with\s+a\s+(\d+)\s+A\s+rating',
                    r'Just\s+like\s+GPU,\s+the\s+memory.*?DrMOS.*?(\d+)\s+A'
                    r'memory\s+uses\s+(\w+\s+\w+\d+[A-Z]*\s+DrMOS)'
                ]
                
                mem_mos_found = False
                for pattern in mem_mos_patterns:
                    mem_mos_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if mem_mos_match:
                        mem_mos_found = True
                        review_data.append({
                            'data_type': 'Memory',
                            'data_key': 'MOS規格',
                            'data_value': mem_mos_match.group(1),
                            'data_unit': '',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'Memory',
                            'name': 'MemoryMOSSpec',
                            'value': mem_mos_match.group(1)
                        })
                        logger.info(f"成功匹配記憶體MOS規格: {mem_mos_match.group(1)}")
                        break
                
                if not mem_mos_found:
                    logger.warning(f"未找到記憶體MOS規格資料，評測標題: {content.get('title', '')}")
            
                # 從文本中提取其他通用數據
            elif "Picture" in review_type or "Teardown" in review_type or "Cooler" in review_type:
                logger.info(f"開始分析拆解重量熱管資料，內容長度: {len(content['body'])}")
                # 提取重量
                weight_patterns = [
                    r'weighs\s+(\d+(?:\.\d+)?)\s*g',
                    r'weight\s+of\s+(\d+(?:\.\d+)?)\s*g',
                    r'weight:?\s+(\d+(?:\.\d+)?)\s*g',
                    r'comes\s+in\s+at\s+(\d+(?:\.\d+)?)\s*g'
                ]
                
                weight_found = False
                for pattern in weight_patterns:
                    weight_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if weight_match:
                        weight_found = True
                        review_data.append({
                            'data_type': 'Physical Properties',
                            'data_key': 'weight',
                            'data_value': weight_match.group(1),
                            'data_unit': 'g',
                            'product_name': content.get('title', '')
                        })
                        review_specs_data.append({
                            'category': 'Physical Properties',
                            'name': 'Weight',
                            'value': weight_match.group(1)
                        })
                        logger.info(f"成功匹配產品重量: {weight_match.group(1)}g")
                        break
                
                if not weight_found:
                    logger.warning(f"未找到產品重量資料，評測標題: {content.get('title', '')}")
                
                # 提取熱管數量
                heatpipe_patterns = [
                    r'(\w+)\s+heatpipes',
                    r'heatpipes:?\s+(\w+)',
                    r'(\d+)\s+heatpipes'
                ]
                
                heatpipe_found = False
                for pattern in heatpipe_patterns:
                    heatpipe_match = re.search(pattern, content['body'], re.IGNORECASE)
                    if heatpipe_match:
                        heatpipe_found = True
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
                        review_specs_data.append({
                            'category': 'Physical Properties',
                            'name': 'Pipe',
                            'value': heatpipe_count
                        })
                        logger.info(f"成功匹配熱管數量: {heatpipe_count}")
                        break
                
                if not heatpipe_found:
                    logger.warning(f"未找到熱管數量資料，評測標題: {content.get('title', '')}")
        except Exception as e:
            logger.error(f"解析評測內容時出錯: {str(e)}")
        
        return content, review_data, review_specs_data
    

    @staticmethod
    def parse_review_posted_date(html):
        """解析評測頁面的發布日期"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            # 一般評測日期在具有特定類別的元素中
            date_element = soup.select_one('div.date')
            
            if date_element:
                date_text = date_element.get_text(strip=True)
                # 從文本中提取日期，格式通常類似 "Posted: Jan 15, 2023"
                match = re.search(r'Posted:\s+(\w+)\s+(\d+),\s+(\d{4})', date_text)
                if match:
                    month_name, day, year = match.groups()
                    # 將月份名稱轉換為數字
                    month_dict = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                    }
                    month = month_dict.get(month_name, 1)
                    return f"{year}-{month:02d}-{int(day):02d}"
            
            return None
        except Exception as e:
            logger.error(f"解析評測發布日期時出錯: {str(e)}")
            return None