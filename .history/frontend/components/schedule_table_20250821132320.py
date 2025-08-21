"""
排班表格組件
"""
import pandas as pd
from datetime import datetime
from typing import Dict, List

from backend.models import ScheduleSlot

class ScheduleTable:
    """排班表格生成器"""
    
    def create_dataframe(self, schedule: Dict[str, ScheduleSlot],
                        scheduler, weekdays: List[str], 
                        holidays: List[str]) -> pd.DataFrame:
        """創建排班DataFrame"""
        schedule_data = []
        all_dates = sorted(holidays + weekdays)
        
        for date_str in all_dates:
            if date_str in schedule:
                slot = schedule[date_str]
                is_holiday = date_str in holidays
                
                # 解析日期
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                weekday_name = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
                
                # 取得可選醫師
                attending_available = ""
                resident_available = ""
                
                if not slot.attending:
                    avail = scheduler.get_available_doctors(
                        date_str, "主治", schedule,
                        scheduler.doctor_map, scheduler.constraints,
                        scheduler.weekdays, scheduler.holidays
                    )
                    attending_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                
                if not slot.resident:
                    avail = scheduler.get_available_doctors(
                        date_str, "住院", schedule,
                        scheduler.doctor_map, scheduler.constraints,
                        scheduler.weekdays, scheduler.holidays
                    )
                    resident_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                
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
            
            if row['類型'] == '假日':
                styles[2] = 'background-color: #ffcdd2'
            else:
                styles[2] = 'background-color: #c5cae9'
            
            if '❌' in str(row['主治醫師']):
                styles[3] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
            else:
                styles[3] = 'background-color: #e3f2fd; color: #1976d2'
            
            if '❌' in str(row['住院醫師']):
                styles[4] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
            else:
                styles[4] = 'background-color: #f3e5f5; color: #7b1fa2'
            
            return styles
        
        return df.style.apply(highlight_schedule, axis=1)