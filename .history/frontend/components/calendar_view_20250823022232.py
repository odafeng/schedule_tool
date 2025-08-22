"""
互動式月曆視圖組件
"""
import streamlit as st
import calendar
from datetime import date, datetime
from typing import Dict, List, Optional
from backend.models import ScheduleSlot, Doctor

class InteractiveCalendarView:
    """互動式月曆視圖生成器"""
    
    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month
        self.cal = calendar.monthcalendar(year, month)
        
    def render_interactive_calendar(self, 
                                   schedule: Dict[str, ScheduleSlot],
                                   doctors: List[Doctor],
                                   weekdays: List[str],
                                   holidays: List[str],
                                   gap_details: Dict = None) -> None:
        """渲染互動式月曆視圖"""
        
        # 注入CSS樣式
        st.markdown(self._get_calendar_styles(), unsafe_allow_html=True)
        
        # 生成月曆HTML
        html = self._generate_calendar_html(schedule, doctors, weekdays, holidays, gap_details)
        st.markdown(html, unsafe_allow_html=True)
        
        # 顯示圖例
        self._render_legend()
    
    def _get_calendar_styles(self) -> str:
        """取得日曆樣式"""
        return """
        <style>
        .calendar-container {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .calendar-header {
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #2c3e50;
        }
        
        .calendar-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 3px;
        }
        
        .calendar-weekday {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px;
            text-align: center;
            font-weight: bold;
            font-size: 14px;
            border-radius: 5px;
        }
        
        .calendar-day {
            background: #f8f9fa;
            min-height: 120px;
            padding: 8px;
            vertical-align: top;
            position: relative;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            transition: all 0.3s ease;
        }
        
        .calendar-day:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
            z-index: 10;
        }
        
        .calendar-day.holiday {
            background: linear-gradient(135deg, #ffe5e5 0%, #ffcccc 100%);
        }
        
        .calendar-day.weekend {
            background: linear-gradient(135deg, #fff3cd 0%, #ffe5a1 100%);
        }
        
        .day-number {
            font-weight: bold;
            color: #495057;
            margin-bottom: 5px;
            font-size: 14px;
        }
        
        .doctor-slot {
            font-size: 11px;
            padding: 3px 6px;
            margin: 3px 0;
            border-radius: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .attending-slot {
            background: linear-gradient(90deg, #d4edda 0%, #c3e6cb 100%);
            color: #155724;
            border-left: 3px solid #28a745;
        }
        
        .resident-slot {
            background: linear-gradient(90deg, #d1ecf1 0%, #bee5eb 100%);
            color: #0c5460;
            border-left: 3px solid #17a2b8;
        }
        
        .empty-slot {
            background: #f8d7da;
            color: #721c24;
            border-left: 3px solid #dc3545;
            cursor: help;
            position: relative;
            padding: 3px 6px;
            margin: 3px 0;
            border-radius: 4px;
            font-size: 11px;
        }
        
        .gap-info {
            display: none;
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 12px;
            border-radius: 8px;
            font-size: 12px;
            width: 280px;
            z-index: 1000;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            margin-bottom: 5px;
        }
        
        .empty-slot:hover .gap-info {
            display: block;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateX(-50%) translateY(10px); }
            to { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
        
        .gap-info::after {
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 8px solid transparent;
            border-top-color: #34495e;
        }
        
        .gap-info-title {
            font-weight: bold;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid rgba(255,255,255,0.2);
            color: #3498db;
            font-size: 13px;
        }
        
        .doctors-section {
            margin: 6px 0;
        }
        
        .doctors-section-title {
            font-weight: bold;
            margin-bottom: 4px;
            font-size: 11px;
        }
        
        .doctor-available {
            background: #27ae60;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            margin: 2px;
            display: inline-block;
            font-size: 10px;
        }
        
        .doctor-restricted {
            background: #e67e22;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            margin: 2px;
            display: inline-block;
            font-size: 10px;
        }
        
        .reason-text {
            font-size: 9px;
            color: #ecf0f1;
            font-style: italic;
            margin-left: 10px;
            display: block;
        }
        
        .no-doctors-text {
            color: #95a5a6;
            font-style: italic;
            font-size: 10px;
        }
        
        .calendar-legend {
            margin-top: 20px;
            padding: 15px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 8px;
        }
        
        .legend-title {
            font-weight: bold;
            margin-bottom: 10px;
            color: #2c3e50;
        }
        
        .legend-item {
            display: inline-block;
            margin: 5px 15px 5px 0;
            font-size: 13px;
        }
        
        .legend-color {
            display: inline-block;
            width: 24px;
            height: 14px;
            margin-right: 6px;
            border-radius: 3px;
            vertical-align: middle;
            border: 1px solid rgba(0,0,0,0.1);
        }
        </style>
        """
    
    def _generate_calendar_html(self,
                               schedule: Dict[str, ScheduleSlot],
                               doctors: List[Doctor],
                               weekdays: List[str],
                               holidays: List[str],
                               gap_details: Dict) -> str:
        """生成月曆HTML"""
        
        html = '<div class="calendar-container">'
        html += f'<div class="calendar-header">📅 {self.year}年 {self.month}月 排班表</div>'
        html += '<table class="calendar-table">'
        
        # 星期標題
        html += '<tr>'
        for day_name in ['週一', '週二', '週三', '週四', '週五', '週六', '週日']:
            html += f'<td class="calendar-weekday">{day_name}</td>'
        html += '</tr>'
        
        # 生成每週
        for week in self.cal:
            html += '<tr>'
            for day_of_week, day in enumerate(week):
                if day == 0:
                    html += '<td style="background: transparent; border: none;"></td>'
                else:
                    html += self._generate_day_cell(
                        day, day_of_week, schedule, doctors, 
                        weekdays, holidays, gap_details
                    )
            html += '</tr>'
        
        html += '</table>'
        html += '</div>'
        
        return html
    
    def _generate_day_cell(self, day: int, day_of_week: int,
                          schedule: Dict[str, ScheduleSlot],
                          doctors: List[Doctor],
                          weekdays: List[str],
                          holidays: List[str],
                          gap_details: Dict) -> str:
        """生成單日格子"""
        
        date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
        
        # 判斷日期類型
        is_holiday = date_str in holidays
        is_weekend = day_of_week in [5, 6]
        
        # 決定格子樣式
        cell_class = "calendar-day"
        if is_holiday:
            cell_class += " holiday"
        elif is_weekend:
            cell_class += " weekend"
        
        html = f'<td class="{cell_class}">'
        html += f'<div class="day-number">{day}日'
        if is_holiday:
            html += ' 🎉'
        elif is_weekend:
            html += ' 🌟'
        html += '</div>'
        
        # 顯示排班資訊
        if date_str in schedule:
            slot = schedule[date_str]
            
            # 主治醫師
            if slot.attending:
                html += f'<div class="doctor-slot attending-slot">👨‍⚕️ 主治: {slot.attending}</div>'
            else:
                html += self._generate_empty_slot_html(
                    date_str, "主治", gap_details
                )
            
            # 住院醫師  
            if slot.resident:
                html += f'<div class="doctor-slot resident-slot">👩‍⚕️ 住院: {slot.resident}</div>'
            else:
                html += self._generate_empty_slot_html(
                    date_str, "住院", gap_details
                )
        
        html += '</td>'
        
        return html
    
    def _generate_empty_slot_html(self, date_str: str, role: str, 
                                 gap_details: Dict) -> str:
        """生成空格的HTML（含hover提示）"""
        
        html = '<div class="empty-slot">'
        html += f'❌ {role}未排'
        
        # 添加hover提示
        if gap_details and date_str in gap_details:
            if role in gap_details[date_str]:
                info = gap_details[date_str][role]
                
                html += '<div class="gap-info">'
                html += f'<div class="gap-info-title">📋 {date_str} {role}醫師狀況</div>'
                
                # 可直接安排的醫師（原B類）
                if info.get('available_doctors'):
                    html += '<div class="doctors-section">'
                    html += '<div class="doctors-section-title">✅ 可直接安排：</div>'
                    for doc in info['available_doctors'][:5]:
                        html += f'<span class="doctor-available">{doc}</span>'
                    if len(info['available_doctors']) > 5:
                        html += f'<span class="reason-text">...還有{len(info["available_doctors"])-5}位醫師</span>'
                    html += '</div>'
                
                # 需要調整的醫師（原A類）
                if info.get('restricted_doctors'):
                    html += '<div class="doctors-section">'
                    html += '<div class="doctors-section-title">⚠️ 需調整後可安排：</div>'
                    for doc_info in info['restricted_doctors'][:3]:
                        html += f'<span class="doctor-restricted">{doc_info["name"]}</span>'
                        html += f'<span class="reason-text">原因：{doc_info["reason"]}</span>'
                    if len(info['restricted_doctors']) > 3:
                        html += f'<span class="reason-text">...還有{len(info["restricted_doctors"])-3}位醫師</span>'
                    html += '</div>'
                
                # 統計資訊
                if not info.get('available_doctors') and not info.get('restricted_doctors'):
                    html += '<div class="no-doctors-text">⚠️ 目前沒有可用的醫師</div>'
                
                if info.get('unavailable_count', 0) > 0:
                    html += f'<div class="reason-text" style="margin-top:8px;">另有 {info["unavailable_count"]} 位醫師因請假或其他原因不可值班</div>'
                
                html += '</div>'
        
        html += '</div>'
        
        return html
    
    def _render_legend(self):
        """渲染圖例"""
        st.markdown("""
        <div class="calendar-legend">
            <div class="legend-title">📍 圖例說明</div>
            <div class="legend-item">
                <span class="legend-color" style="background: linear-gradient(90deg, #d4edda 0%, #c3e6cb 100%);"></span>
                主治醫師已排班
            </div>
            <div class="legend-item">
                <span class="legend-color" style="background: linear-gradient(90deg, #d1ecf1 0%, #bee5eb 100%);"></span>
                住院醫師已排班
            </div>
            <div class="legend-item">
                <span class="legend-color" style="background: #f8d7da;"></span>
                未排班（滑鼠移上查看詳情）
            </div>
            <div class="legend-item">
                <span class="legend-color" style="background: linear-gradient(135deg, #ffe5e5 0%, #ffcccc 100%);"></span>
                國定假日
            </div>
            <div class="legend-item">
                <span class="legend-color" style="background: linear-gradient(135deg, #fff3cd 0%, #ffe5a1 100%);"></span>
                週末
            </div>
        </div>
        """, unsafe_allow_html=True)


# 原有的 CalendarView 類保留向後相容
class CalendarView:
    """月曆視圖生成器（舊版）"""
    
    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month
        self.num_days = calendar.monthrange(year, month)[1]
        self.first_day = date(year, month, 1)
        self.start_weekday = self.first_day.weekday()
    
    def generate_html(self, schedule: Dict[str, ScheduleSlot], 
                     scheduler, weekdays: List[str], holidays: List[str]) -> str:
        """生成月曆HTML（舊版）"""
        from frontend.utils.styles import get_calendar_css
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


def render_calendar_view(schedule: Dict[str, ScheduleSlot],
                        doctors: List[Doctor],
                        year: int, month: int,
                        weekdays: List[str],
                        holidays: List[str],
                        gap_details: Dict = None):
    """渲染月曆視圖的便利函數"""
    
    calendar_view = InteractiveCalendarView(year, month)
    calendar_view.render_interactive_calendar(
        schedule, doctors, weekdays, holidays, gap_details
    )