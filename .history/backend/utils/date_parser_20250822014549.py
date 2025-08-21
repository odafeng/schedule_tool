"""
日期範圍解析工具 - 增強版
支援多種輸入格式並確保輸出為 YYYY-MM-DD 格式
"""
import calendar
from typing import List, Set, Union
import re
from datetime import date, datetime

def parse_date_range(input_str: str, year: int, month: int) -> List[str]:
    """
    解析日期範圍字串，轉換為完整的 YYYY-MM-DD 格式
    
    Args:
        input_str: 輸入字串，如 "15,17,18,21-23"
        year: 目標年份
        month: 目標月份
        
    Returns:
        解析後的日期字串列表，如 ["2025-08-15", "2025-08-17", ...]
        
    Raises:
        ValueError: 當輸入格式錯誤或日期無效時
    """
    if not input_str or not input_str.strip():
        return []
    
    # 獲取該月的天數
    _, max_day = calendar.monthrange(year, month)
    
    # 用於收集所有有效日期
    dates = set()
    
    # 移除所有空白
    cleaned_input = input_str.replace(" ", "")
    
    # 分割逗號分隔的部分
    parts = cleaned_input.split(",")
    
    for part in parts:
        if not part:
            continue
            
        if "-" in part:
            # 處理範圍，如 "21-23"
            try:
                range_parts = part.split("-", 1)
                if len(range_parts) != 2:
                    raise ValueError(f"無效的範圍格式: {part}")
                
                start_str, end_str = range_parts
                if not start_str or not end_str:
                    raise ValueError(f"範圍不完整: {part}")
                
                start_day = int(start_str)
                end_day = int(end_str)
                
                # 驗證日期範圍
                if start_day < 1:
                    raise ValueError(f"起始日期必須大於0: {start_day}")
                if end_day > max_day:
                    raise ValueError(f"結束日期超出該月天數: {end_day} (該月只有 {max_day} 天)")
                if start_day > end_day:
                    raise ValueError(f"起始日期不能大於結束日期: {part}")
                
                # 加入範圍內的所有日期
                for day in range(start_day, end_day + 1):
                    if day <= max_day:  # 確保不超出月份天數
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
    
    # 轉換為完整的 YYYY-MM-DD 格式並排序
    date_strings = []
    for day in sorted(dates):
        # 使用標準的 YYYY-MM-DD 格式
        date_obj = date(year, month, day)
        date_strings.append(date_obj.strftime("%Y-%m-%d"))
    
    return date_strings

def validate_date_input(input_str: str) -> str:
    """
    驗證日期輸入格式
    
    Args:
        input_str: 使用者輸入的字串
        
    Returns:
        錯誤訊息，如果沒有錯誤則返回空字串
    """
    if not input_str or not input_str.strip():
        return ""
    
    # 移除空白進行檢查
    cleaned = input_str.replace(" ", "")
    
    # 檢查是否包含無效字符
    if not re.match(r'^[0-9,\-]*$', cleaned):
        return "只能包含數字、逗號和連字號"
    
    # 檢查是否有連續的分隔符
    if ",," in cleaned or "--" in cleaned:
        return "不能有連續的分隔符"
    
    # 檢查是否以分隔符開頭或結尾
    if cleaned.startswith(",") or cleaned.endswith(","):
        return "不能以逗號開頭或結尾"
    if cleaned.startswith("-") or cleaned.endswith("-"):
        return "不能以連字號開頭或結尾"
    
    # 檢查範圍格式的有效性
    parts = cleaned.split(",")
    for part in parts:
        if "-" in part:
            range_parts = part.split("-")
            if len(range_parts) != 2:
                return f"範圍格式錯誤: {part}"
            if not range_parts[0] or not range_parts[1]:
                return f"範圍不完整: {part}"
            try:
                start = int(range_parts[0])
                end = int(range_parts[1])
                if start > end:
                    return f"起始值不能大於結束值: {part}"
                if start < 1 or start > 31:
                    return f"日期必須在 1-31 之間: {start}"
                if end < 1 or end > 31:
                    return f"日期必須在 1-31 之間: {end}"
            except ValueError:
                return f"範圍必須是數字: {part}"
        elif part:  # 非空的單個日期
            try:
                day = int(part)
                if day < 1 or day > 31:
                    return f"日期必須在 1-31 之間: {day}"
            except ValueError:
                return f"日期必須是數字: {part}"
    
    return ""

def format_dates_for_display(dates: List[str]) -> str:
    """
    格式化日期列表用於顯示
    
    Args:
        dates: 日期字串列表 (YYYY-MM-DD 格式)
        
    Returns:
        格式化的顯示字串，如 "1, 3, 5-7, 10日"
    """
    if not dates:
        return "無"
    
    # 提取日期數字
    days = []
    for date_str in dates:
        try:
            # 處理 YYYY-MM-DD 格式
            if "-" in date_str and len(date_str.split("-")) == 3:
                day = int(date_str.split("-")[2])
                days.append(day)
            # 處理純數字（向後兼容）
            elif date_str.isdigit():
                days.append(int(date_str))
        except (IndexError, ValueError):
            continue
    
    if not days:
        return "無"
    
    days.sort()
    
    # 合併連續的日期為範圍
    ranges = []
    i = 0
    while i < len(days):
        start = days[i]
        end = start
        
        # 找到連續序列的結束
        while i + 1 < len(days) and days[i + 1] == end + 1:
            i += 1
            end = days[i]
        
        # 添加範圍或單個日期
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")
        
        i += 1
    
    # 格式化輸出
    if len(ranges) <= 5:
        return f"{', '.join(ranges)}日"
    else:
        # 顯示前3個和後2個
        preview = ', '.join(ranges[:3]) + " ... " + ', '.join(ranges[-2:])
        return f"{preview} (共{len(days)}天)"

def normalize_dates_to_full_format(
    dates: Union[List[str], List[int], List], 
    year: int, 
    month: int,
    strict_month_check: bool = False
) -> List[str]:
    """
    將各種格式的日期列表標準化為 YYYY-MM-DD 格式
    
    Args:
        dates: 混合格式的日期列表（可能包含整數、字串等）
        year: 目標年份
        month: 目標月份
        strict_month_check: 是否嚴格檢查月份（True: 只保留指定年月的日期）
    
    Returns:
        標準化的日期字串列表 ["YYYY-MM-DD", ...]
    """
    if not dates:
        return []
    
    normalized = set()
    _, max_day = calendar.monthrange(year, month)
    
    for date_item in dates:
        if date_item is None:
            continue
            
        # 處理整數格式（日期數字）
        if isinstance(date_item, int):
            if 1 <= date_item <= max_day:
                date_obj = date(year, month, date_item)
                normalized.add(date_obj.strftime("%Y-%m-%d"))
        
        # 處理字串格式
        elif isinstance(date_item, str):
            # 如果是純數字字串
            if date_item.isdigit():
                day = int(date_item)
                if 1 <= day <= max_day:
                    date_obj = date(year, month, day)
                    normalized.add(date_obj.strftime("%Y-%m-%d"))
            
            # 如果已經是 YYYY-MM-DD 格式
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_item):
                try:
                    # 驗證日期有效性
                    dt = datetime.strptime(date_item, "%Y-%m-%d")
                    
                    if strict_month_check:
                        # 嚴格模式：只保留指定年月的日期
                        if dt.year == year and dt.month == month:
                            normalized.add(date_item)
                        else:
                            # 嘗試轉換為當前年月的相同日期
                            if 1 <= dt.day <= max_day:
                                new_date = date(year, month, dt.day)
                                normalized.add(new_date.strftime("%Y-%m-%d"))
                    else:
                        # 寬鬆模式：保留所有有效的 YYYY-MM-DD 日期
                        normalized.add(date_item)
                        
                except ValueError:
                    # 無效的日期格式，忽略
                    pass
            
            # 如果是範圍格式 "1,3,5-7"
            elif "," in date_item or "-" in date_item:
                try:
                    parsed = parse_date_range(date_item, year, month)
                    normalized.update(parsed)
                except:
                    pass
        
        # 處理 date 或 datetime 物件
        elif isinstance(date_item, date):
            if strict_month_check:
                if date_item.year == year and date_item.month == month:
                    normalized.add(date_item.strftime("%Y-%m-%d"))
            else:
                normalized.add(date_item.strftime("%Y-%m-%d"))
                
        elif isinstance(date_item, datetime):
            if strict_month_check:
                if date_item.year == year and date_item.month == month:
                    normalized.add(date_item.strftime("%Y-%m-%d"))
            else:
                normalized.add(date_item.strftime("%Y-%m-%d"))
    
    return sorted(list(normalized))

def convert_dates_for_storage(dates: List, year: int, month: int) -> List[str]:
    """
    確保日期列表在儲存前轉換為正確的 YYYY-MM-DD 格式
    
    這是最重要的函數，用於在儲存醫師資料前確保格式正確
    
    Args:
        dates: 可能包含各種格式的日期列表
        year: 當前選擇的年份
        month: 當前選擇的月份
    
    Returns:
        標準化的 YYYY-MM-DD 格式日期列表
    """
    # 使用嚴格模式，只保留指定年月的日期
    return normalize_dates_to_full_format(dates, year, month, strict_month_check=True)

# 測試函數
if __name__ == "__main__":
    print("="*50)
    print("日期解析工具測試")
    print("="*50)
    
    # 測試案例
    test_cases = [
        ("1,3,5-7,10", 2025, 8),
        ("15-20,25", 2025, 8),
        ("1", 2025, 8),
        ("1-5,10-15,20-25", 2025, 8),
    ]
    
    for input_str, year, month in test_cases:
        print(f"\n輸入: '{input_str}' ({year}年{month}月)")
        
        # 驗證格式
        error = validate_date_input(input_str)
        if error:
            print(f"❌ 錯誤: {error}")
        else:
            # 解析日期
            dates = parse_date_range(input_str, year, month)
            print(f"✅ 解析結果 ({len(dates)}天):")
            if len(dates) <= 10:
                print(f"   {dates}")
            else:
                print(f"   {dates[:5]} ... {dates[-2:]}")
            
            # 格式化顯示
            display = format_dates_for_display(dates)
            print(f"📅 顯示格式: {display}")
    
    # 測試標準化功能
    print("\n" + "="*50)
    print("測試日期標準化")
    print("="*50)
    
    mixed_dates = [5, "7", "10-12", date(2025, 8, 15), "2025-08-20"]
    normalized = normalize_dates_to_full_format(mixed_dates, 2025, 8)
    print(f"混合輸入: {mixed_dates}")
    print(f"標準化後: {normalized}")