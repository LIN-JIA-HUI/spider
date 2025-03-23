import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class ScrapeState:
    """管理爬蟲狀態的類"""
    def __init__(self):
        self.processed_urls = set()
        self.products = {}  # 產品ID到產品資料的映射
        self.categories = {}  # 類別名稱到類別ID的映射
        self.specs_count = 0
        self.reviews_count = 0
        self.error_count = 0
        self.start_time = time.time()
    
    def add_product(self, product_id, product_name):
        """添加已處理的產品"""
        self.products[product_id] = {
            'name': product_name,
            'specs': 0,
            'boards': [],
            'reviews': 0
        }
        logger.info(f"添加產品到狀態管理: {product_name} (ID: {product_id})")
    
    def add_spec(self, product_id):
        """記錄已添加的規格"""
        self.specs_count += 1
        if product_id in self.products:
            self.products[product_id]['specs'] += 1
    
    def add_board(self, product_id, board_id, board_name):
        """記錄已添加的主板"""
        if product_id in self.products:
            self.products[product_id]['boards'].append({
                'id': board_id,
                'name': board_name,
                'reviews_processed': False
            })
            logger.info(f"添加主板到產品 {product_id}: {board_name} (ID: {board_id})")
    
    def add_review(self, product_id, board_name):
        """記錄已添加的評測"""
        self.reviews_count += 1
        if product_id in self.products:
            self.products[product_id]['reviews'] += 1
            # 標記該主板評測已處理
            for board in self.products[product_id]['boards']:
                if board['name'] == board_name:
                    board['reviews_processed'] = True
                    break
            logger.info(f"為產品 {product_id} 的主板 {board_name} 添加評測")
    
    def get_stats(self):
        """獲取爬蟲統計信息"""
        return {
            'products': len(self.products),
            'specs': self.specs_count,
            'reviews': self.reviews_count,
            'errors': self.error_count,
            'elapsed_time': time.time() - self.start_time
        }

class StorageManager:
    """管理資料存儲的類"""
    def __init__(self, db, state):
        self.db = db
        self.state = state
        self.category_cache = {}  # 快取已處理的類別
    
    async def store_product_complete(self, product_data, specs_data, board_data=None):
        """完整處理一個產品的所有資料存儲，確保事務一致性"""
        try:
            # 嘗試使用單一事務處理
            try:
                product_id, categories = await self.db.create_product_with_specs(product_data, specs_data)
                
                # 更新類別快取
                self.category_cache.update(categories)
                
                # 更新狀態
                self.state.add_product(product_id, product_data.get('F_Product', '未知產品'))
                self.state.specs_count += len(specs_data)
                
                logger.info(f"成功在單一事務中創建產品及規格: {product_data.get('F_Product', '未知產品')} (ID: {product_id})")
                return product_id
                
            except Exception as e:
                logger.error(f"單一事務處理失敗，嘗試分步處理: {str(e)}")
                
                # 退回到分步處理
                # 1. 存儲產品主數據
                product = await self.db.create_product(product_data)
                product_id = product.F_SeqNo
                
                # 更新狀態
                self.state.add_product(product_id, product_data.get('F_Product', '未知產品'))
                
                # 2. 處理並存儲所有規格類別和規格數據
                if specs_data:
                    await self._store_all_specs(product_id, specs_data)
                
                logger.info(f"成功通過分步處理創建產品及規格: {product_data.get('F_Product', '未知產品')} (ID: {product_id})")
                return product_id
        except Exception as e:
            logger.error(f"存儲產品完整資料失敗: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.state.error_count += 1
            raise
    
    async def _store_all_specs(self, product_id, specs_data):
        """存儲所有規格資料，確保類別先建立"""
        # 先處理所有類別
        for spec in specs_data:
            category_name = spec['category']
            if category_name not in self.category_cache:
                try:
                    category = await self.db.create_spec_category(category_name)
                    self.category_cache[category_name] = category.F_ID
                    logger.info(f"建立規格類別: {category_name} (ID: {category.F_ID})")
                except Exception as e:
                    logger.error(f"建立規格類別 {category_name} 失敗: {str(e)}")
                    continue
        
        # 再存儲所有規格
        for spec in specs_data:
            try:
                category_name = spec['category']
                if category_name in self.category_cache:
                    await self.db.create_spec(
                        product_id,
                        self.category_cache[category_name],
                        spec['name'],
                        spec['value']
                    )
                    self.state.add_spec(product_id)
                    logger.debug(f"為產品 {product_id} 添加規格: {spec['name']}={spec['value']}")
            except Exception as e:
                logger.error(f"存儲規格資料失敗: {str(e)}")
                continue
    
    async def store_board(self, product_id, board_info):
        """存儲主板資料，使用替代方法建立與GPU的關聯"""
        try:
            # 將主板存儲為獨立產品，但在描述中包含GPU產品ID
            board_data = {
                "F_Product": board_info.get('name', '未知主板'),
                "F_Vendor": board_info.get('vendor', '未知廠商'),
                # 在描述欄位中包含關聯信息
                "F_Desc": f"主板型號: {board_info.get('name', '')} (關聯GPU ID: {product_id})"
            }
            
            # 創建主板產品記錄
            board = await self.db.create_product(board_data)
            board_id = board.F_SeqNo
            
            logger.info(f"已創建主板產品記錄: {board_info.get('name', '')} (ID: {board_id})")
            
            try:
                # 在規格表中添加一條記錄來建立關聯
                # 首先創建或獲取「關聯信息」類別
                relation_category = await self.db.create_spec_category("關聯信息")
                
                # 添加指向GPU產品的規格記錄
                await self.db.create_spec(
                    board_id,  # 主板ID
                    relation_category.F_ID,  # 類別ID
                    "關聯GPU產品ID",  # 規格名稱
                    str(product_id)  # 規格值(GPU ID)
                )
                
                logger.info(f"已建立主板 {board_id} 與GPU {product_id} 的關聯")
                
                # 如果主板有額外規格資料，也可以存儲
                if 'specs' in board_info and board_info['specs']:
                    for spec_category, specs in board_info['specs'].items():
                        # 為每個規格類別創建類別記錄
                        spec_cat = await self.db.create_spec_category(spec_category)
                        
                        # 添加該類別下的所有規格
                        for spec_name, spec_value in specs.items():
                            await self.db.create_spec(
                                board_id,
                                spec_cat.F_ID,
                                spec_name,
                                spec_value
                            )
                            self.state.add_spec(board_id)
                    
                    logger.info(f"已存儲主板 {board_info.get('name', '')} 的 {len(board_info['specs'])} 個類別的規格資料")
            
            except Exception as e:
                logger.error(f"存儲主板關聯資料失敗: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                # 繼續處理，因為主板產品記錄已經成功創建
            
            # 更新狀態
            self.state.add_board(product_id, board_id, board_info.get('name', '未知主板'))
            
            return board_id
        except Exception as e:
            logger.error(f"存儲主板產品記錄失敗: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.state.error_count += 1
            return None
    
    async def store_review(self, product_id, board_id, board_name, review_contents):
        """存儲評測資料，關聯到主板而非GPU"""
        try:
            for content in review_contents:
                # 使用board_id而非product_id
                review = await self.db.create_review(
                    board_id,  # 使用主板ID
                    content['type'],
                    content['content'].get('title', ''),
                    content['content'].get('body', '')
                )
                
                # 儲存結構化數據
                for data_item in content['data']:
                    await self.db.create_review_data(
                        review.F_SeqNo,
                        data_item.get('data_type', content['type']),
                        data_item.get('data_key', ''),
                        data_item.get('data_value', ''),
                        data_item.get('data_unit', ''),
                        data_item.get('product_name', board_name)
                    )
                
                # 更新狀態
                self.state.add_review(product_id, board_name)  # 仍然記錄與GPU的關聯
                logger.info(f"成功存儲評測: {content['type']} 為主板 {board_id}")
            
            return True
        except Exception as e:
            logger.error(f"存儲評測資料失敗: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.state.error_count += 1
            return False