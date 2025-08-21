"""
月曆視圖組件
"""
import calendar
from datetime import date, datetime
from typing import Dict, List

from backend.models import ScheduleSlot
from frontend.utils.styles import get_calendar_css

class CalendarView:
    """月曆視圖生成器"""
    
    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month
        self.num_days = calendar.monthrange(year, month)[1]
        self.first_day = date(year, month, 1)
        self.start_weekday = self.first_day.weekday()
    
    def generate_html(self, schedule: Dict[str, ScheduleSlot], 
                     scheduler, weekdays: List[str], holidays: List[str]) -> str:
        """生成月曆HTML"""
        html = get_calendar_css()
        html += """
        <table class="calendar-table">
            <tr>
                <th>週一</th>
                <th>週二</th>
                <th>週三</th>
                <th>週四</th>
                <th>週五</th>
                <th>週六</th>
                <th>週日</th>
            </tr>
        """
        
        # 建立月曆格子
        current_day = 1
        week_html = "<tr>"
        
        # 填充月初空白
        for _ in range(self.start_weekday):
            week_html += '<td class="empty-cell"></td>'
        
        # 填充日期
        while current_day <= self.num_days:
            current_date = date(self.year, self.month, current_day)
            date_str = current_date.strftime("%Y-%m-%d")
            
            # 判斷是否為假日
            is_holiday = date_str in holidays
            cell_class = "holiday-cell" if is_holiday else "weekday-cell"
            
            # 取得排班資訊
            cell_html = self._generate_cell_html(
                date_str, current_day, is_holiday, 
                schedule, scheduler, cell_class
            )
            
            week_html += cell_html
            current_day += 1
            
            # 週末換行
            if current_date.weekday() == 6:
                week_html += "</tr>"
                if current_day <= self.num_days:
                    week_html += "<tr>"
        
        # 填充月末空白
        last_day = date(self.year, self.month, self.num_days)
        if last_day.weekday() != 6:
            for _ in range(6 - last_day.weekday()):
                week_html += '<td class="empty-cell"></td>'
            week_html += "</tr>"
        
        html += week_html
        html += "</table>"
        
        return html
    
    def _generate_cell_html(self, date_str: str, day: int, is_holiday: bool,
                           schedule: Dict[str, ScheduleSlot], 
                           scheduler, cell_class: str) -> str:
        """生成單個日期格子的HTML"""
        if date_str not in schedule:
            return f'<td class="{cell_class}"><div class="calendar-date">{day}日</div></td>'
        
        slot = schedule[date_str]
        
        # 開始建立格子內容
        cell_html = f'<td class="{cell_class}">'
        cell_html += f'<div class="calendar-date">{day}日'
        if is_holiday:
            cell_html += ' 🎉'
        cell_html += '</div>'
        
        # 主治醫師
        if slot.attending:
            cell_html += f'<div class="doctor-info attending">👨‍⚕️ 主治: {slot.attending}</div>'
        else:
            # 顯示未填格和可選醫師
            available_attending = scheduler.get_available_doctors(
                date_str, "主治", schedule,
                scheduler.doctor_map, scheduler.constraints,
                scheduler.weekdays, scheduler.holidays
            )
            cell_html += '<div class="empty-slot">❌ 主治未排</div>'
            if available_attending:
                cell_html += f'<div class="available-doctors">可選: {", ".join(available_attending[:3])}'
                if len(available_attending) > 3:
                    cell_html += f' 等{len(available_attending)}人'
                cell_html += '</div>'
            else:
                cell_html += '<div class="available-doctors">⚠️ 無可用醫師</div>'
        
        # 住院醫師
        if slot.resident:
            cell_html += f'<div class="doctor-info resident">👨‍⚕️ 住院: {slot.resident}</div>'
        else:
            # 顯示未填格和可選醫師
            available_resident = scheduler.get_available_doctors(
                date_str, "總醫師", schedule,
                scheduler.doctor_map, scheduler.constraints,
                scheduler.weekdays, scheduler.holidays
            )
            cell_html += '<div class="empty-slot">❌ 住院未排</div>'
            if available_resident:
                cell_html += f'<div class="available-doctors">可選: {", ".join(available_resident[:3])}'
                if len(available_resident) > 3:
                    cell_html += f' 等{len(available_resident)}人'
                cell_html += '</div>'
            else:
                cell_html += '<div class="available-doctors">⚠️ 無可用醫師</div>'
        
        cell_html += '</td>'
        
        return cell_html