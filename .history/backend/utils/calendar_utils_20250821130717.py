"""
月曆工具函數
"""
import calendar
from datetime import date, datetime, timedelta
from typing import List, Tuple, Set, Dict

def get_month_calendar(year: int, month: int, custom_holidays: Set[str] = None, 
                       custom_workdays: Set[str] = None) -> Tuple[List[str], List[str]]:
    """
    生成指定月份的平日和假日列表
    
    Args:
        year: 年份
        month: 月份
        custom_holidays: 自訂假日集合 (YYYY-MM-DD格式)
        custom_workdays: 自訂補班日集合 (YYYY-MM-DD格式)
    
    Returns:
        (平日列表, 假日列表)
    """
    if custom_holidays is None:
        custom_holidays = set()
    if custom_workdays is None:
        custom_workdays = set()
    
    weekdays = []
    holidays = []
    
    # 獲取該月的天數
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 判斷是否為假日
        is_weekend = current_date.weekday() >= 5  # 週六或週日
        
        if date_str in custom_workdays:
            # 補班日
            weekdays.append(date_str)
        elif date_str in custom_holidays or (is_weekend and date_str not in custom_workdays):
            # 自訂假日或週末（非補班日）
            holidays.append(date_str)
        else:
            # 一般平日
            weekdays.append(date_str)
    
    return weekdays, holidays

def check_consecutive_days(schedule: Dict, doctor_name: str, 
                          target_date: str, max_consecutive: int) -> bool:
    """
    檢查是否違反連續值班限制
    
    Args:
        schedule: 排班表字典
        doctor_name: 醫師姓名
        target_date: 目標日期
        max_consecutive: 最大連續天數
    
    Returns:
        True if violates constraint, False otherwise
    """
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    consecutive_count = 1
    
    # 檢查前面的連續天數
    for i in range(1, max_consecutive):
        check_date = (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if check_date in schedule:
            slot = schedule[check_date]
            if slot.attending == doctor_name or slot.resident == doctor_name:
                consecutive_count += 1
            else:
                break
    
    # 檢查後面的連續天數
    for i in range(1, max_consecutive):
        check_date = (target_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        if check_date in schedule:
            slot = schedule[check_date]
            if slot.attending == doctor_name or slot.resident == doctor_name:
                consecutive_count += 1
            else:
                break
    
    return consecutive_count > max_consecutive

def get_weekday_name(date_str: str) -> str:
    """獲取星期幾的中文名稱"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday_names = ['一', '二', '三', '四', '五', '六', '日']
    return weekday_names[dt.weekday()]