import os
import logging
import pyodbc
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.connect_to_db()
    
    def connect_to_db(self):
        """連接到 SQL Server 資料庫"""
        try:
            logger.info("正在連接資料庫...")
            
            # 從環境變數或預設值獲取連接信息
            server = os.getenv('DB_SERVER', 'localhost')
            database = os.getenv('DB_NAME', 'PM')
            trusted_connection = os.getenv('DB_TRUSTED_CONNECTION', 'yes')
            
            # 使用 Windows 身份驗證連接
            conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection={trusted_connection}'
            
            # 嘗試連接
            self.conn = pyodbc.connect(conn_str)
            self.cursor = self.conn.cursor()
            
            logger.info("資料庫連接成功")
        except Exception as e:
            logger.error(f"資料庫連接失敗: {str(e)}")
            raise
    
    async def disconnect(self):
        """關閉資料庫連接"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("資料庫連接已關閉")
    
    # 一個工具函數來將數據庫操作封裝為非同步形式
    async def run_db_query(self, query_func, *args, **kwargs):
        """執行同步數據庫查詢，並使其表現為非同步"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: query_func(*args, **kwargs))
    
    async def execute_transaction(self, query_func, *args, **kwargs):
        """在事務中執行一系列資料庫操作"""
        def _execute_transaction():
            try:
                # 開始事務
                self.conn.autocommit = False
                result = query_func(*args, **kwargs)
                self.conn.commit()
                return result
            except Exception as e:
                self.conn.rollback()
                logger.error(f"事務執行失敗: {str(e)}")
                raise
            finally:
                # 恢復自動提交
                self.conn.autocommit = True
        
        return await self.run_db_query(_execute_transaction)
    
    async def create_product(self, product_data):
        """創建產品記錄"""
        def _create_product():
            try:
                now = datetime.now()
                
                # 準備插入數據
                insert_data = {
                    "F_Createdate": now,
                    "F_UpdateTime": now,
                    "F_Stat": "1",
                    "F_Keyin": "admin",
                    "F_Security": "S",
                    "F_Owner": "admin",
                    "F_BU": "GNP",
                    **product_data
                }
                
                # 構建SQL插入語句
                columns = ', '.join(insert_data.keys())
                placeholders = ', '.join(['?' for _ in insert_data])
                
                sql = f"INSERT INTO dbo.C_Product ({columns}) OUTPUT INSERTED.F_SeqNo VALUES ({placeholders})"
                
                # 執行插入並獲取新生成的 ID
                self.cursor.execute(sql, list(insert_data.values()))
                new_id = self.cursor.fetchone()[0]
                self.conn.commit()
                
                # 構建返回的產品對象
                product = type('Product', (), {"F_SeqNo": new_id, "F_Product": product_data.get("F_Product", "")})
                
                logger.info(f"產品記錄創建成功: {product.F_Product}, ID: {new_id}")
                return product
            except Exception as e:
                self.conn.rollback()
                logger.error(f"產品記錄創建失敗: {str(e)}")
                raise
        
        return await self.run_db_query(_create_product)
    
    async def create_spec_category(self, category_name):
        """創建或獲取規格類別"""
        def _create_spec_category():
            try:
                now = datetime.now()
                
                # 檢查是否已存在
                sql = "SELECT F_SeqNo, F_ID FROM dbo.C_S_Flag WHERE F_Type = ? AND F_Name = ?"
                self.cursor.execute(sql, ('GPU 規格參數', category_name))
                existing = self.cursor.fetchone()
                
                if existing:
                    logger.info(f"規格類別已存在: {category_name} (ID: {existing[1]})")
                    return type('Category', (), {"F_SeqNo": existing[0], "F_ID": existing[1], "F_Name": category_name})
                
                # 獲取最大 ID
                self.cursor.execute("SELECT MAX(CAST(F_ID AS INT)) FROM dbo.C_S_Flag WHERE F_Type = ?", ('GPU 規格參數',))
                max_id = self.cursor.fetchone()[0]
                
                next_id = "1"
                if max_id:
                    next_id = str(int(max_id) + 1)
                
                # 創建新紀錄
                sql = """
                    INSERT INTO dbo.C_S_Flag (
                        F_Createdate, F_UpdateTime, F_Stat, F_Keyin, F_Security, 
                        F_Type, F_ID, F_Name
                    ) OUTPUT INSERTED.F_SeqNo
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                self.cursor.execute(sql, (
                    now, now, '1', 'admin', 'S',
                    'GPU 規格參數', next_id, category_name
                ))
                
                new_id = self.cursor.fetchone()[0]
                self.conn.commit()
                
                logger.info(f"規格類別創建成功: {category_name} (ID: {next_id})")
                return type('Category', (), {"F_SeqNo": new_id, "F_ID": next_id, "F_Name": category_name})
            except Exception as e:
                self.conn.rollback()
                logger.error(f"規格類別創建失敗: {str(e)}")
                raise
        
        return await self.run_db_query(_create_spec_category)
    
    async def create_spec(self, product_id, category_id, spec_name, spec_value):
        """創建規格記錄"""
        def _create_spec():
            try:
                now = datetime.now()
                
                sql = """
                    INSERT INTO dbo.C_Specs_Database (
                        F_Createdate, F_UpdateTime, F_Stat, F_Keyin, F_Security, F_Owner,
                        F_Master_Table, F_Master_ID, F_Type, F_Name, F_Value
                    ) OUTPUT INSERTED.F_SeqNo
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                self.cursor.execute(sql, (
                    now, now, '1', 'admin', 'S', 'admin',
                    'C_Product', str(product_id), category_id, spec_name, spec_value
                ))
                
                new_id = self.cursor.fetchone()[0]
                self.conn.commit()
                
                logger.debug(f"規格記錄創建成功: {spec_name}={spec_value}, 產品ID: {product_id}")
                
                return type('Spec', (), {
                    "F_SeqNo": new_id, 
                    "F_Master_ID": str(product_id),
                    "F_Name": spec_name,
                    "F_Value": spec_value
                })
            except Exception as e:
                self.conn.rollback()
                logger.error(f"規格記錄創建失敗: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                raise
        
        return await self.run_db_query(_create_spec)
    
    async def create_review(self, product_id, review_type, title, desc):
        """創建評測記錄"""
        def _create_review():
            try:
                now = datetime.now()
                
                sql = """
                    INSERT INTO dbo.C_Product_Review (
                        F_Createdate, F_UpdateTime, F_Stat, F_Keyin, F_Security, F_Owner,
                        F_Master_Table, F_Master_ID, F_Type, F_Title, F_Desc
                    ) OUTPUT INSERTED.F_SeqNo
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                self.cursor.execute(sql, (
                    now, now, '1', 'admin', 'S', 'admin',
                    'C_Product', str(product_id), review_type, title, desc
                ))
                
                new_id = self.cursor.fetchone()[0]
                self.conn.commit()
                
                logger.info(f"評測記錄創建成功: {title}, 產品ID: {product_id}")
                
                return type('Review', (), {
                    "F_SeqNo": new_id, 
                    "F_Type": review_type,
                    "F_Title": title
                })
            except Exception as e:
                self.conn.rollback()
                logger.error(f"評測記錄創建失敗: {str(e)}")
                raise
        
        return await self.run_db_query(_create_review)
    
    async def create_review_data(self, review_id, data_type, data_key, data_value, data_unit, product_name):
        """創建評測數據記錄"""
        def _create_review_data():
            try:
                sql = """
                    INSERT INTO dbo.C_Product_Review_Data (
                        F_Review_ID, F_Data_Type, F_Data_Key, F_Data_Value, F_Data_Unit, F_Product_Name
                    ) OUTPUT INSERTED.F_SeqNo
                    VALUES (?, ?, ?, ?, ?, ?)
                """
                
                self.cursor.execute(sql, (
                    review_id, data_type, data_key, data_value, data_unit, product_name
                ))
                
                new_id = self.cursor.fetchone()[0]
                self.conn.commit()
                
                logger.debug(f"評測數據記錄創建成功: {data_key}={data_value}, 評測ID: {review_id}")
                
                return type('ReviewData', (), {
                    "F_SeqNo": new_id, 
                    "F_Review_ID": review_id,
                    "F_Data_Type": data_type
                })
            except Exception as e:
                self.conn.rollback()
                logger.error(f"評測數據記錄創建失敗: {str(e)}")
                raise
        
        return await self.run_db_query(_create_review_data)
        
    async def create_product_with_specs(self, product_data, specs_data):
        """在單一事務中創建產品及其規格"""
        def _create_product_with_specs():
            try:
                # 開始事務
                self.conn.autocommit = False
                
                # 1. 創建產品
                now = datetime.now()
                insert_data = {
                    "F_Createdate": now,
                    "F_UpdateTime": now,
                    "F_Stat": "1",
                    "F_Keyin": "admin",
                    "F_Security": "S",
                    "F_Owner": "admin",
                    "F_BU": "GNP",
                    **product_data
                }
                
                columns = ', '.join(insert_data.keys())
                placeholders = ', '.join(['?' for _ in insert_data])
                
                sql = f"INSERT INTO dbo.C_Product ({columns}) OUTPUT INSERTED.F_SeqNo VALUES ({placeholders})"
                
                self.cursor.execute(sql, list(insert_data.values()))
                product_id = self.cursor.fetchone()[0]
                
                # 2. 處理所有規格類別
                categories = {}
                for spec in specs_data:
                    category_name = spec['category']
                    if category_name not in categories:
                        # 檢查是否已存在
                        self.cursor.execute(
                            "SELECT F_SeqNo, F_ID FROM dbo.C_S_Flag WHERE F_Type = ? AND F_Name = ?",
                            ('GPU 規格參數', category_name)
                        )
                        existing = self.cursor.fetchone()
                        
                        if existing:
                            categories[category_name] = existing[1]
                            logger.info(f"找到現有規格類別: {category_name} (ID: {existing[1]})")
                        else:
                            # 創建新類別
                            self.cursor.execute(
                                "SELECT MAX(CAST(F_ID AS INT)) FROM dbo.C_S_Flag WHERE F_Type = ?", 
                                ('GPU 規格參數',)
                            )
                            max_id = self.cursor.fetchone()[0]
                            
                            next_id = "1"
                            if max_id:
                                next_id = str(int(max_id) + 1)
                            
                            self.cursor.execute("""
                                INSERT INTO dbo.C_S_Flag (
                                    F_Createdate, F_UpdateTime, F_Stat, F_Keyin, F_Security, 
                                    F_Type, F_ID, F_Name
                                ) OUTPUT INSERTED.F_ID
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                now, now, '1', 'admin', 'S',
                                'GPU 規格參數', next_id, category_name
                            ))
                            
                            category_id = self.cursor.fetchone()[0]
                            categories[category_name] = category_id
                            logger.info(f"創建新規格類別: {category_name} (ID: {category_id})")
                
                # 3. 創建所有規格
                specs_count = 0
                for spec in specs_data:
                    category_id = categories.get(spec['category'])
                    if not category_id:
                        logger.warning(f"找不到規格類別 {spec['category']}，跳過規格 {spec['name']}")
                        continue
                    
                    self.cursor.execute("""
                        INSERT INTO dbo.C_Specs_Database (
                            F_Createdate, F_UpdateTime, F_Stat, F_Keyin, F_Security, F_Owner,
                            F_Master_Table, F_Master_ID, F_Type, F_Name, F_Value
                        ) OUTPUT INSERTED.F_SeqNo
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now, now, '1', 'admin', 'S', 'admin',
                        'C_Product', str(product_id), category_id, spec['name'], spec['value']
                    ))
                    
                    self.cursor.fetchone()  # 取得 ID 但不需要使用
                    specs_count += 1
                
                # 提交事務
                self.conn.commit()
                logger.info(f"成功創建產品 ID: {product_id} 及其 {specs_count} 條規格")
                
                return product_id, categories
            except Exception as e:
                self.conn.rollback()
                logger.error(f"創建產品及規格失敗: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                raise
            finally:
                # 恢復自動提交
                self.conn.autocommit = True
        
        return await self.run_db_query(_create_product_with_specs)