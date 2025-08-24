"""
Supabase 客戶端模組
處理所有 Supabase 相關的操作
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client
import streamlit as st

# 載入環境變數
load_dotenv()


class SupabaseManager:
    """Supabase 管理器"""
    
    def __init__(self):
        """初始化 Supabase 連線"""
        self.client: Optional[Client] = None
        self.bucket_name = os.getenv('SUPABASE_BUCKET', 'schedules')
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化 Supabase 客戶端"""
        try:
            # 從環境變數讀取設定
            url = os.getenv('SUPABASE_URL')
            anon_key = os.getenv('SUPABASE_ANON_KEY')
            
            if not url or not anon_key:
                st.warning("Supabase 設定未完成，請在 .env 檔案中設定")
                return False
            
            # 建立客戶端
            self.client = create_client(url, anon_key)
            
            # 確保 bucket 存在
            self._ensure_bucket_exists()
            
            return True
            
        except Exception as e:
            st.error(f"Supabase 連線失敗: {str(e)}")
            return False
    
    def _ensure_bucket_exists(self):
        """確保 Storage Bucket 存在"""
        if not self.client:
            return
        
        try:
            # 檢查 bucket 是否存在
            buckets = self.client.storage.list_buckets()
            bucket_exists = any(b['name'] == self.bucket_name for b in buckets)
            
            if not bucket_exists:
                # 建立 bucket
                self.client.storage.create_bucket(
                    self.bucket_name,
                    options={
                        'public': False,  # 私有 bucket
                        'file_size_limit': 52428800,  # 50MB
                        'allowed_mime_types': [
                            'application/pdf',
                            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        ]
                    }
                )
                st.success(f"✅ 成功建立 Storage Bucket: {self.bucket_name}")
        
        except Exception as e:
            # 可能是權限問題，但不影響使用
            pass
    
    def upload_file(self, file_path: str, file_data: bytes, 
                   content_type: str = "application/pdf") -> Optional[str]:
        """
        上傳檔案到 Supabase Storage
        
        Args:
            file_path: 儲存路徑 (例如: "2025/01/schedule_20250115.pdf")
            file_data: 檔案內容
            content_type: MIME 類型
        
        Returns:
            簽名的下載 URL 或 None
        """
        if not self.client:
            st.error("Supabase 未連線")
            return None
        
        try:
            # 上傳檔案
            response = self.client.storage.from_(self.bucket_name).upload(
                path=file_path,
                file=file_data,
                file_options={"content-type": content_type}
            )
            
            # 生成簽名 URL (30天有效)
            expiry = 30 * 24 * 60 * 60  # 30天
            
            signed_response = self.client.storage.from_(self.bucket_name).create_signed_url(
                path=file_path,
                expires_in=expiry
            )
            
            if signed_response and 'signedURL' in signed_response:
                return signed_response['signedURL']
            else:
                st.error("無法生成簽名 URL")
                return None
                
        except Exception as e:
            st.error(f"上傳失敗: {str(e)}")
            return None
    
    def upload_schedule_pdf(self, pdf_filename: str, year: int, month: int) -> Optional[str]:
        """
        上傳排班 PDF 到 Supabase
        
        Args:
            pdf_filename: 本地 PDF 檔案路徑
            year: 年份
            month: 月份
        
        Returns:
            簽名的下載 URL 或 None
        """
        try:
            # 讀取 PDF 檔案
            with open(pdf_filename, 'rb') as f:
                pdf_data = f.read()
            
            # 生成儲存路徑
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            storage_path = f"{year}/{month:02d}/schedule_{year}{month:02d}_{timestamp}.pdf"
            
            # 上傳並取得 URL
            download_url = self.upload_file(
                file_path=storage_path,
                file_data=pdf_data,
                content_type="application/pdf"
            )
            
            if download_url:
                # 儲存上傳紀錄
                self._save_upload_record(storage_path, download_url, year, month)
                
            return download_url
            
        except Exception as e:
            st.error(f"PDF 上傳失敗: {str(e)}")
            return None
    
    def upload_schedule_excel(self, excel_filename: str, year: int, month: int) -> Optional[str]:
        """
        上傳排班 Excel 到 Supabase
        
        Args:
            excel_filename: 本地 Excel 檔案路徑
            year: 年份
            month: 月份
        
        Returns:
            簽名的下載 URL 或 None
        """
        try:
            # 讀取 Excel 檔案
            with open(excel_filename, 'rb') as f:
                excel_data = f.read()
            
            # 生成儲存路徑
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            storage_path = f"{year}/{month:02d}/schedule_{year}{month:02d}_{timestamp}.xlsx"
            
            # 上傳並取得 URL
            download_url = self.upload_file(
                file_path=storage_path,
                file_data=excel_data,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            return download_url
            
        except Exception as e:
            st.error(f"Excel 上傳失敗: {str(e)}")
            return None
    
    def list_files(self, path: str = "") -> list:
        """
        列出指定路徑下的檔案
        
        Args:
            path: 路徑 (例如: "2025/01/")
        
        Returns:
            檔案列表
        """
        if not self.client:
            return []
        
        try:
            files = self.client.storage.from_(self.bucket_name).list(path)
            return files
        except Exception as e:
            st.error(f"無法列出檔案: {str(e)}")
            return []
    
    def delete_file(self, file_path: str) -> bool:
        """
        刪除檔案
        
        Args:
            file_path: 檔案路徑
        
        Returns:
            是否成功
        """
        if not self.client:
            return False
        
        try:
            self.client.storage.from_(self.bucket_name).remove([file_path])
            return True
        except Exception as e:
            st.error(f"刪除失敗: {str(e)}")
            return False
    
    def _save_upload_record(self, file_path: str, download_url: str, 
                           year: int, month: int):
        """儲存上傳紀錄"""
        import json
        
        record = {
            "uploaded_at": datetime.now().isoformat(),
            "file_path": file_path,
            "download_url": download_url,
            "year": year,
            "month": month,
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
        }
        
        # 儲存到本地
        os.makedirs("data/upload_history", exist_ok=True)
        filename = f"data/upload_history/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    
    def get_status(self) -> dict:
        """取得連線狀態"""
        return {
            "connected": self.client is not None,
            "bucket": self.bucket_name,
            "url": os.getenv('SUPABASE_URL', 'Not configured')
        }


# 全域實例
_supabase_manager = None


def get_supabase_manager() -> SupabaseManager:
    """取得 Supabase 管理器的單例實例"""
    global _supabase_manager
    if _supabase_manager is None:
        _supabase_manager = SupabaseManager()
    return _supabase_manager


def test_connection():
    """測試 Supabase 連線"""
    manager = get_supabase_manager()
    status = manager.get_status()
    
    if status['connected']:
        st.success(f"✅ Supabase 已連線")
        st.info(f"Bucket: {status['bucket']}")
        st.info(f"URL: {status['url']}")
        return True
    else:
        st.error("❌ Supabase 未連線")
        return False