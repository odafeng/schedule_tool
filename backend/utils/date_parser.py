"""
日期範圍解析工具
"""
import calendar
from typing import List, Set
import re

def parse_date_range(input_str: str, year: int, month: int) -> List[str]:
    """
    解析日期範圍字串
    
    Args:
        input_str: 輸入字串，如 "15,17,18,21-23"
        year: 目標年份
        month: 目標月份
        
    Returns:
        解析後的日期字串列表，如 ["2024-01-15", "2024-01-17", ...]
        
    Raises:
        ValueError: 當輸入格式錯誤或日期無效時
    """
    if not input_str.strip():
        return []
    
    # 獲取該月的天數
    _, max_day = calendar.monthrange(year, month)
    
    # 用於收集所有有效日期
    dates = set()
    
    # 分割逗號分隔的部分
    parts = input_str.replace(" ", "").split(",")
    
    for part in parts:
        if not part:
            continue
            
        if "-" in part:
            # 處理範圍，如 "21-23"
            try:
                start_str, end_str = part.split("-", 1)
                start_day = int(start_str)
                end_day = int(end_str)
                
                # 驗證日期範圍
                if start_day < 1 or end_day > max_day or start_day > end_day:
                    raise ValueError(f"無效的日期範圍: {part} (該月只有 {max_day} 天)")
                
                # 加入範圍內的所有日期
                for day in range(start_day, end_day + 1):
                    dates.add(day)
                    
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"日期範圍格式錯誤: {part} (應為數字)")
                else:
                    raise
        else:
            # 處理單個日期，如 "15"
            try:
                day = int(part)
                if day < 1 or day > max_day:
                    raise ValueError(f"無效的日期: {day} (該月只有 {max_day} 天)")
                dates.add(day)
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"日期格式錯誤: {part} (應為數字)")
                else:
                    raise
    
    # 轉換為日期字串並排序
    date_strings = []
    for day in sorted(dates):
        date_strings.append(f"{year}-{month:02d}-{day:02d}")
    
    return date_strings

def validate_date_input(input_str: str) -> str:
    """
    驗證日期輸入格式
    
    Args:
        input_str: 使用者輸入的字串
        
    Returns:
        錯誤訊息，如果沒有錯誤則返回空字串
    """
    if not input_str.strip():
        return ""
    
    # 檢查是否包含無效字符
    if not re.match(r'^[0-9,\-\s]*$', input_str):
        return "只能包含數字、逗號、連字號和空格"
    
    # 檢查基本格式
    cleaned = input_str.replace(" ", "")
    
    # 檢查是否有連續的分隔符
    if ",," in cleaned or "--" in cleaned:
        return "不能有連續的分隔符"
    
    # 檢查是否以分隔符開頭或結尾
    if cleaned.startswith(",") or cleaned.endswith(",") or cleaned.startswith("-") or cleaned.endswith("-"):
        return "不能以分隔符開頭或結尾"
    
    return ""

def format_dates_for_display(dates: List[str]) -> str:
    """
    格式化日期列表用於顯示
    
    Args:
        dates: 日期字串列表
        
    Returns:
        格式化的顯示字串
    """
    if not dates:
        return "無"
    
    # 提取日期部分並排序
    days = []
    for date_str in dates:
        try:
            day = int(date_str.split("-")[2])
            days.append(day)
        except (IndexError, ValueError):
            continue
    
    days.sort()
    
    if len(days) <= 5:
        return f"{', '.join(map(str, days))}"
    else:
        return f"{', '.join(map(str, days[:3]))} ... {', '.join(map(str, days[-2:]))} (共{len(days)}天)"