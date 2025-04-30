import os
import logging
import pyodbc
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(dotenv_path='./.env')

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_database_schema():
    """更新資料庫結構，添加新欄位"""
    try:
        # 從環境變數獲取連接信息
        server = os.getenv('DB_SERVER')
        database = os.getenv('DB_NAME')
        trusted_connection = os.getenv('DB_TRUSTED_CONNECTION')
        
        # 使用 Windows 身份驗證連接
        connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection={trusted_connection}'
        
        # 連接到資料庫
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        logger.info("成功連接到資料庫")
        
        # 檢查欄位是否已存在
        check_column_sql = """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'C_Product_Review'
        AND COLUMN_NAME = 'F_Main_Review_URL'
        """
        
        cursor.execute(check_column_sql)
        column_exists = cursor.fetchone()[0] > 0
        
        if not column_exists:
            # 添加 F_Main_Review_URL 欄位
            alter_table_sql1 = """
            ALTER TABLE dbo.C_Product_Review ADD F_Main_Review_URL NVARCHAR(500);
            """
            cursor.execute(alter_table_sql1)
            logger.info("成功添加 F_Main_Review_URL 欄位")
        else:
            logger.info("F_Main_Review_URL 欄位已存在")
        
        # 檢查欄位是否已存在
        check_column_sql = """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'C_Product_Review'
        AND COLUMN_NAME = 'F_Page_URL'
        """
        
        cursor.execute(check_column_sql)
        column_exists = cursor.fetchone()[0] > 0
        
        if not column_exists:
            # 添加 F_Page_URL 欄位
            alter_table_sql2 = """
            ALTER TABLE dbo.C_Product_Review ADD F_Page_URL NVARCHAR(500);
            """
            cursor.execute(alter_table_sql2)
            logger.info("成功添加 F_Page_URL 欄位")
        else:
            logger.info("F_Page_URL 欄位已存在")
        
        # 提交事務
        conn.commit()
        logger.info("資料庫結構更新成功")
        
        # 關閉連接
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        logger.error(f"更新資料庫結構失敗: {str(e)}")
        return False

if __name__ == "__main__":
    update_database_schema()
