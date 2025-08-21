"""
醫師資料模型
"""
from dataclasses import dataclass, field, asdict
from typing import List, Literal

@dataclass
class Doctor:
    """醫師資料模型"""
    name: str
    role: Literal["主治", "住院"]
    weekday_quota: int  # 平日配額
    holiday_quota: int  # 假日配額
    unavailable_dates: List[str] = field(default_factory=list)  # 不可值班日
    preferred_dates: List[str] = field(default_factory=list)    # 優先值班日
    
    def to_dict(self):
        """轉換為字典格式"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        """從字典建立實例"""
        return cls(**data)
    
    def is_available_on(self, date: str) -> bool:
        """檢查特定日期是否可值班"""
        return date not in self.unavailable_dates
    
    def prefers_date(self, date: str) -> bool:
        """檢查是否為偏好日期"""
        return date in self.preferred_dates