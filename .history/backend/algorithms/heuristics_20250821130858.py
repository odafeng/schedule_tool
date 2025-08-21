"""
啟發式方法與輔助函數
"""
from typing import List, Dict
from collections import defaultdict

from ..models import Doctor, ScheduleSlot, ScheduleConstraints
from ..utils import check_consecutive_days

def get_available_doctors(date_str: str, role: str, 
                         schedule: Dict[str, ScheduleSlot],
                         doctor_map: Dict[str, Doctor],
                         constraints: ScheduleConstraints,
                         weekdays: List[str],
                         holidays: List[str]) -> List[str]:
    """
    獲取某日期某角色的可用醫師列表
    
    Args:
        date_str: 日期字串
        role: 角色（主治/住院）
        schedule: 當前排班表
        doctor_map: 醫師映射表
        constraints: 排班限制
        weekdays: 平日列表
        holidays: 假日列表
    
    Returns:
        可用醫師姓名列表
    """
    # 篩選該角色的醫師
    doctors = [doc for doc in doctor_map.values() if doc.role == role]
    available = []
    
    is_holiday = date_str in holidays
    weekday_counts = defaultdict(int)
    holiday_counts = defaultdict(int)
    
    # 統計當前班數
    for d, slot in schedule.items():
        if d in holidays:
            if slot.attending:
                holiday_counts[slot.attending] += 1
            if slot.resident:
                holiday_counts[slot.resident] += 1
        else:
            if slot.attending:
                weekday_counts[slot.attending] += 1
            if slot.resident:
                weekday_counts[slot.resident] += 1
    
    for doc in doctors:
        # 檢查是否為不可值班日
        if date_str in doc.unavailable_dates:
            continue
            
        # 檢查配額
        if is_holiday:
            if holiday_counts[doc.name] >= doc.holiday_quota:
                continue
        else:
            if weekday_counts[doc.name] >= doc.weekday_quota:
                continue
        
        # 檢查同日是否已排班
        if date_str in schedule:
            slot = schedule[date_str]
            if slot.attending == doc.name or slot.resident == doc.name:
                continue
        
        # 檢查連續值班
        if not check_consecutive_days(schedule, doc.name, date_str, 
                                     constraints.max_consecutive_days):
            available.append(doc.name)
    
    # 優先排序：偏好日期的醫師優先
    preferred = []
    normal = []
    for name in available:
        doc = doctor_map[name]
        if date_str in doc.preferred_dates:
            preferred.append(name)
        else:
            normal.append(name)
    
    return preferred + normal