"""
醫師資料模型 - 確保日期格式正確版本
"""
from dataclasses import dataclass, field
from typing import List, Literal, Union
from datetime import datetime, date
import streamlit as st

@dataclass
class Doctor:
    """醫師資料模型"""
    name: str
    role: Literal["主治", "總醫師"]
    weekday_quota: int = 5
    holiday_quota: int = 2
    unavailable_dates: List[str] = field(default_factory=list)
    preferred_dates: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """初始化後處理，確保日期格式正確"""
        # 嘗試從 session_state 取得年月資訊
        try:
            year = st.session_state.get('selected_year', datetime.now().year)
            month = st.session_state.get('selected_month', datetime.now().month)
        except:
            year = datetime.now().year
            month = datetime.now().month
        
        # 轉換日期格式
        self.unavailable_dates = self._normalize_dates(self.unavailable_dates, year, month)
        self.preferred_dates = self._normalize_dates(self.preferred_dates, year, month)
    
    def _normalize_dates(self, dates: List, year: int, month: int) -> List[str]:
        """
        標準化日期列表為 YYYY-MM-DD 格式
        
        Args:
            dates: 日期列表（可能包含各種格式）
            year: 年份
            month: 月份
        
        Returns:
            標準化的日期字串列表
        """
        if not dates:
            return []
        
        normalized = set()
        
        # 嘗試導入 date_parser，如果失敗則使用簡單轉換
        try:
            from backend.utils.date_parser import normalize_dates_to_full_format
            return normalize_dates_to_full_format(dates, year, month)
        except ImportError:
            # 備用方案：簡單轉換
            import calendar
            _, max_day = calendar.monthrange(year, month)
            
            for date_item in dates:
                if date_item is None:
                    continue
                    
                # 處理整數格式
                if isinstance(date_item, int):
                    if 1 <= date_item <= max_day:
                        date_obj = date(year, month, date_item)
                        normalized.add(date_obj.strftime("%Y-%m-%d"))
                
                # 處理字串格式
                elif isinstance(date_item, str):
                    # 如果是純數字
                    if date_item.isdigit():
                        day = int(date_item)
                        if 1 <= day <= max_day:
                            date_obj = date(year, month, day)
                            normalized.add(date_obj.strftime("%Y-%m-%d"))
                    # 如果已經是 YYYY-MM-DD 格式
                    elif "-" in date_item and len(date_item.split("-")) == 3:
                        try:
                            # 驗證格式
                            datetime.strptime(date_item, "%Y-%m-%d")
                            normalized.add(date_item)
                        except ValueError:
                            pass
                
                # 處理 date 物件
                elif isinstance(date_item, date):
                    normalized.add(date_item.strftime("%Y-%m-%d"))
                
                # 處理 datetime 物件
                elif isinstance(date_item, datetime):
                    normalized.add(date_item.strftime("%Y-%m-%d"))
            
            return sorted(list(normalized))
    
    def to_dict(self) -> dict:
        """
        轉換為字典格式（用於序列化）
        確保日期都是 YYYY-MM-DD 格式
        
        Returns:
            包含醫師資料的字典
        """
        # 確保日期格式正確
        try:
            year = st.session_state.get('selected_year', datetime.now().year)
            month = st.session_state.get('selected_month', datetime.now().month)
        except:
            year = datetime.now().year
            month = datetime.now().month
        
        return {
            'name': self.name,
            'role': self.role,
            'weekday_quota': self.weekday_quota,
            'holiday_quota': self.holiday_quota,
            'unavailable_dates': self._normalize_dates(self.unavailable_dates, year, month),
            'preferred_dates': self._normalize_dates(self.preferred_dates, year, month)
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Doctor':
        """
        從字典建立醫師物件（用於反序列化）
        
        Args:
            data: 包含醫師資料的字典
        
        Returns:
            Doctor 物件
        """
        return cls(
            name=data.get('name', ''),
            role=data.get('role', '主治'),
            weekday_quota=data.get('weekday_quota', 5),
            holiday_quota=data.get('holiday_quota', 2),
            unavailable_dates=data.get('unavailable_dates', []),
            preferred_dates=data.get('preferred_dates', [])
        )
    
    def is_available_on(self, date_str: str) -> bool:
        """
        檢查醫師在指定日期是否可值班
        
        Args:
            date_str: 日期字串（YYYY-MM-DD 格式）
        
        Returns:
            是否可值班
        """
        # 直接檢查日期字串
        if date_str in self.unavailable_dates:
            return False
        
        # 額外檢查：如果 date_str 是純數字，轉換後再檢查
        if date_str.isdigit():
            day = int(date_str)
            for unavail_date in self.unavailable_dates:
                if "-" in unavail_date:
                    try:
                        unavail_day = int(unavail_date.split("-")[2])
                        if unavail_day == day:
                            return False
                    except:
                        pass
        
        # 額外檢查：如果是 YYYY-MM-DD 格式，也檢查日期部分
        if "-" in date_str and len(date_str.split("-")) == 3:
            try:
                check_day = int(date_str.split("-")[2])
                for unavail_date in self.unavailable_dates:
                    if "-" in unavail_date:
                        unavail_day = int(unavail_date.split("-")[2])
                        # 檢查是否同一天（可能不同年月）
                        if unavail_date == date_str:
                            return False
            except:
                pass
        
        return True
    
    def prefers_date(self, date_str: str) -> bool:
        """
        檢查醫師是否偏好在指定日期值班
        
        Args:
            date_str: 日期字串（YYYY-MM-DD 格式）
        
        Returns:
            是否為偏好日期
        """
        # 直接檢查日期字串
        if date_str in self.preferred_dates:
            return True
        
        # 額外檢查：如果 date_str 是純數字，轉換後再檢查
        if date_str.isdigit():
            day = int(date_str)
            for pref_date in self.preferred_dates:
                if "-" in pref_date:
                    try:
                        pref_day = int(pref_date.split("-")[2])
                        if pref_day == day:
                            return True
                    except:
                        pass
        
        # 額外檢查：如果是 YYYY-MM-DD 格式，檢查是否為同一天
        if "-" in date_str and len(date_str.split("-")) == 3:
            try:
                check_day = int(date_str.split("-")[2])
                for pref_date in self.preferred_dates:
                    if pref_date == date_str:
                        return True
            except:
                pass
        
        return False
    
    def get_remaining_quota(self, is_holiday: bool, assigned_count: int) -> int:
        """
        取得剩餘配額
        
        Args:
            is_holiday: 是否為假日
            assigned_count: 已分配的值班數
        
        Returns:
            剩餘配額
        """
        quota = self.holiday_quota if is_holiday else self.weekday_quota
        return max(0, quota - assigned_count)
    
    def __str__(self) -> str:
        """字串表示"""
        return f"{self.name} ({self.role})"
    
    def __repr__(self) -> str:
        """詳細表示"""
        unavail_count = len(self.unavailable_dates)
        pref_count = len(self.preferred_dates)
        return (f"Doctor(name='{self.name}', role='{self.role}', "
                f"weekday_quota={self.weekday_quota}, holiday_quota={self.holiday_quota}, "
                f"unavailable={unavail_count}天, preferred={pref_count}天)")
    
    def get_formatted_dates_summary(self) -> dict:
        """
        取得格式化的日期摘要
        
        Returns:
            包含格式化日期資訊的字典
        """
        try:
            from backend.utils.date_parser import format_dates_for_display
            unavail_display = format_dates_for_display(self.unavailable_dates)
            pref_display = format_dates_for_display(self.preferred_dates)
        except:
            # 備用方案
            unavail_display = f"{len(self.unavailable_dates)}天"
            pref_display = f"{len(self.preferred_dates)}天"
        
        return {
            'unavailable_display': unavail_display,
            'preferred_display': pref_display,
            'unavailable_count': len(self.unavailable_dates),
            'preferred_count': len(self.preferred_dates)
        }