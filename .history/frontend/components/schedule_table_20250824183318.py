"""
修正 schedule_table.py 中的 create_dataframe 方法
請替換整個 schedule_table.py 檔案
"""
import pandas as pd
from datetime import datetime
from typing import Dict, List, Set, Union

from backend.models import ScheduleSlot

class ScheduleTable:
    """排班表格生成器"""
    
    def create_dataframe(self, schedule: Dict[str, ScheduleSlot],
                        scheduler, 
                        weekdays: Union[List[str], Set[str]], 
                        holidays: Union[List[str], Set[str]]) -> pd.DataFrame:
        """創建排班DataFrame
        
        Args:
            schedule: 排班字典
            scheduler: 排程器物件
            weekdays: 平日列表或集合
            holidays: 假日列表或集合
        
        Returns:
            pd.DataFrame: 排班資料表
        """
        schedule_data = []
        
        # 處理 set 或 list 類型
        if isinstance(holidays, set):
            holidays_list = list(holidays)
        else:
            holidays_list = holidays
            
        if isinstance(weekdays, set):
            weekdays_list = list(weekdays)
        else:
            weekdays_list = weekdays
        
        # 合併並排序所有日期
        all_dates = sorted(holidays_list + weekdays_list)
        
        # 為了後續檢查方便，確保有 set 版本
        holidays_set = set(holidays_list) if not isinstance(holidays, set) else holidays
        
        for date_str in all_dates:
            if date_str in schedule:
                slot = schedule[date_str]
                is_holiday = date_str in holidays_set
                
                # 解析日期
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    weekday_name = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
                except ValueError:
                    # 如果日期格式錯誤，跳過
                    continue
                
                # 取得可選醫師
                attending_available = ""
                resident_available = ""
                
                # 檢查 scheduler 是否有 get_available_doctors 方法
                if hasattr(scheduler, 'get_available_doctors'):
                    if not slot.attending:
                        avail = scheduler.get_available_doctors(
                            date_str, "主治", schedule,
                            scheduler.doctor_map, scheduler.constraints,
                            weekdays_list, holidays_list  # 傳遞 list 版本
                        )
                        attending_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                    
                    if not slot.resident:
                        avail = scheduler.get_available_doctors(
                            date_str, "總醫師", schedule,
                            scheduler.doctor_map, scheduler.constraints,
                            weekdays_list, holidays_list  # 傳遞 list 版本
                        )
                        resident_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                else:
                    # 如果 scheduler 沒有這個方法，只顯示基本資訊
                    if not slot.attending:
                        attending_available = "無法檢查可用醫師"
                    if not slot.resident:
                        resident_available = "無法檢查可用醫師"
                
                # 建立資料列
                schedule_data.append({
                    '日期': f"{dt.month}/{dt.day}",
                    '星期': weekday_name,
                    '類型': '假日' if is_holiday else '平日',
                    '主治醫師': slot.attending or f'❌ 未排 ({attending_available})',
                    '住院醫師': slot.resident or f'❌ 未排 ({resident_available})'
                })
        
        return pd.DataFrame(schedule_data)
    
    def apply_styles(self, df: pd.DataFrame) -> pd.DataFrame.style:
        """套用樣式到DataFrame"""
        def highlight_schedule(row):
            styles = [''] * len(row)
            
            # 類型欄位樣式
            if row['類型'] == '假日':
                styles[2] = 'background-color: #ffcdd2'
            else:
                styles[2] = 'background-color: #c5cae9'
            
            # 主治醫師欄位樣式
            if '❌' in str(row['主治醫師']):
                styles[3] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
            else:
                styles[3] = 'background-color: #e3f2fd; color: #1976d2'
            
            # 住院醫師欄位樣式
            if '❌' in str(row['住院醫師']):
                styles[4] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
            else:
                styles[4] = 'background-color: #f3e5f5; color: #7b1fa2'
            
            return styles
        
        return df.style.apply(highlight_schedule, axis=1)