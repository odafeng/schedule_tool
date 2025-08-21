"""
醫師資料模型 - 確保日期格式正確版本
"""
from dataclasses import dataclass, field
from typing import List, Literal
from datetime import datetime, date

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
        # 轉換不可值班日期為正確格式
        self.unavailable_dates = self._convert_dates_to_string(self.unavailable_dates)
        # 轉換優先值班日期為正確格式
        self.preferred_dates = self._convert_dates_to_string(self.preferred_dates)
    
    def _convert_dates_to_string(self, dates: List) -> List[str]:
        """
        將日期列表轉換為字串格式（YYYY-MM-DD）
        
        Args:
            dates: 日期列表（可能包含整數、字串或日期物件）
        
        Returns:
            標準化的日期字串列表
        """
        converted = []
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        for date_item in dates:
            if isinstance(date_item, int):
                # 整數格式（日期數字）- 轉換為當月的日期
                if 1 <= date_item <= 31:
                    try:
                        date_obj = date(current_year, current_month, date_item)
                        converted.append(date_obj.strftime('%Y-%m-%d'))
                    except ValueError:
                        # 如果日期無效（如2月30日），跳過
                        pass
            elif isinstance(date_item, str):
                if date_item.isdigit():
                    # 字串數字格式 - 轉換為當月的日期
                    day = int(date_item)
                    if 1 <= day <= 31:
                        try:
                            date_obj = date(current_year, current_month, day)
                            converted.append(date_obj.strftime('%Y-%m-%d'))
                        except ValueError:
                            pass
                else:
                    # 假設已經是正確格式，驗證並保留
                    try:
                        datetime.strptime(date_item, '%Y-%m-%d')
                        converted.append(date_item)
                    except ValueError:
                        # 嘗試其他格式
                        for fmt in ['%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y']:
                            try:
                                date_obj = datetime.strptime(date_item, fmt)
                                converted.append(date_obj.strftime('%Y-%m-%d'))
                                break
                            except ValueError:
                                continue
            elif isinstance(date_item, date):
                # date 物件 - 直接轉換
                converted.append(date_item.strftime('%Y-%m-%d'))
            elif isinstance(date_item, datetime):
                # datetime 物件 - 轉換為日期
                converted.append(date_item.strftime('%Y-%m-%d'))
        
        # 移除重複並排序
        return sorted(list(set(converted)))
    
    def to_dict(self) -> dict:
        """
        轉換為字典格式（用於序列化）
        
        Returns:
            包含醫師資料的字典
        """
        return {
            'name': self.name,
            'role': self.role,
            'weekday_quota': self.weekday_quota,
            'holiday_quota': self.holiday_quota,
            'unavailable_dates': self._convert_dates_to_string(self.unavailable_dates),
            'preferred_dates': self._convert_dates_to_string(self.preferred_dates)
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
        doctor = cls(
            name=data.get('name', ''),
            role=data.get('role', '主治'),
            weekday_quota=data.get('weekday_quota', 5),
            holiday_quota=data.get('holiday_quota', 2),
            unavailable_dates=data.get('unavailable_dates', []),
            preferred_dates=data.get('preferred_dates', [])
        )
        
        # 確保日期格式正確（__post_init__ 會處理）
        return doctor
    
    def is_available_on(self, date_str: str) -> bool:
        """
        檢查醫師在指定日期是否可值班
        
        Args:
            date_str: 日期字串（YYYY-MM-DD 格式）
        
        Returns:
            是否可值班
        """
        # 檢查不可值班日期
        if date_str in self.unavailable_dates:
            return False
        
        # 也檢查日期數字（向後兼容）
        try:
            if "-" in date_str:
                day = int(date_str.split("-")[2])
                # 檢查是否有舊格式的日期數字
                for unavail_date in self.unavailable_dates:
                    if unavail_date.isdigit() and int(unavail_date) == day:
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
        # 檢查偏好日期
        if date_str in self.preferred_dates:
            return True
        
        # 也檢查日期數字（向後兼容）
        try:
            if "-" in date_str:
                day = int(date_str.split("-")[2])
                # 檢查是否有舊格式的日期數字
                for pref_date in self.preferred_dates:
                    if pref_date.isdigit() and int(pref_date) == day:
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
        return (f"Doctor(name='{self.name}', role='{self.role}', "
                f"weekday_quota={self.weekday_quota}, holiday_quota={self.holiday_quota}, "
                f"unavailable={len(self.unavailable_dates)}天, preferred={len(self.preferred_dates)}天)")