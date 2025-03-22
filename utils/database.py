import os
import logging
import pyodbc
import re
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
    
    async def create_product(self, product_data):
        """創建產品記錄"""
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
    
    async def create_spec_category(self, category_name):
        """創建或獲取規格類別"""
        try:
            now = datetime.now()
            
            # 檢查是否已存在
            sql = "SELECT F_SeqNo, F_ID FROM dbo.C_S_Flag WHERE F_Type = ? AND F_Name = ?"
            self.cursor.execute(sql, ('GPU 規格參數', category_name))
            existing = self.cursor.fetchone()
            
            if existing:
                return type('Category', (), {"F_SeqNo": existing[0], "F_ID": existing[1], "F_Name": category_name})
            
            # 獲取最大 ID
            self.cursor.execute("SELECT MAX(CAST(F_ID AS INT)) FROM dbo.C_S_Flag WHERE F_Type = ?", ('GPU 規格參數',))
            max_id = self.cursor.fetchone()[0]
            
            next_id = "1"
            if max_id:
                next_id = str(max_id + 1)
            
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
    
    async def create_spec(self, product_id, category_id, spec_name, spec_value):
        """創建規格記錄"""
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
            
            return type('Spec', (), {
                "F_SeqNo": new_id, 
                "F_Master_ID": str(product_id),
                "F_Name": spec_name,
                "F_Value": spec_value
            })
        except Exception as e:
            self.conn.rollback()
            logger.error(f"規格記錄創建失敗: {str(e)}")
            raise
    
    async def create_review(self, product_id, review_type, title, desc):
        """創建評測記錄"""
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
            
            return type('Review', (), {
                "F_SeqNo": new_id, 
                "F_Type": review_type,
                "F_Title": title
            })
        except Exception as e:
            self.conn.rollback()
            logger.error(f"評測記錄創建失敗: {str(e)}")
            raise
    
    async def create_review_data(self, review_id, data_type, data_key, data_value, data_unit, product_name):
        """創建評測數據記錄"""
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
            
            return type('ReviewData', (), {
                "F_SeqNo": new_id, 
                "F_Review_ID": review_id,
                "F_Data_Type": data_type
            })
        except Exception as e:
            self.conn.rollback()
            logger.error(f"評測數據記錄創建失敗: {str(e)}")
            raise