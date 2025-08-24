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
        """取得日曆樣式 - 簡潔專業風格"""
        return """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        .calendar-container {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            padding: 24px;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
            margin: 20px 0;
        }
        
        .calendar-header {
            text-align: center;
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 24px;
            color: #1e293b;
            letter-spacing: -0.5px;
        }
        
        .calendar-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 4px;
        }
        
        .calendar-weekday {
            background: #475569;
            color: #ffffff;
            padding: 14px 8px;
            text-align: center;
            font-weight: 600;
            font-size: 14px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        
        .calendar-day {
            background: #f8fafc;
            min-height: 140px;
            padding: 12px;
            vertical-align: top;
            position: relative;
            border: 2px solid #e2e8f0;
            transition: all 0.2s ease;
        }
        
        .calendar-day:hover {
            border-color: #3b82f6;
            background: #ffffff;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
            z-index: 10;
        }
        
        .calendar-day.holiday {
            background: #fef2f2;
            border-color: #fecaca;
        }
        
        .calendar-day.weekend {
            background: #fefce8;
            border-color: #fde68a;
        }
        
        .day-number {
            font-weight: 700;
            color: #334155;
            margin-bottom: 8px;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .day-icon {
            font-size: 14px;
        }
        
        .doctor-slot {
            font-size: 13px;
            padding: 6px 10px;
            margin: 4px 0;
            border-radius: 6px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .attending-slot {
            background: #dcfce7;
            color: #14532d;
            border: 1px solid #86efac;
        }
        
        .resident-slot {
            background: #dbeafe;
            color: #1e3a8a;
            border: 1px solid #93c5fd;
        }
        
        .empty-slot {
            background: #fee2e2;
            color: #7f1d1d;
            border: 1px solid #fca5a5;
            cursor: help;
            position: relative;
            padding: 6px 10px;
            margin: 4px 0;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .empty-slot:hover {
            background: #fecaca;
        }
        
        /* Tooltip 樣式 */
        .gap-info {
            display: none;
            position: absolute;
            bottom: calc(100% + 10px);
            left: 50%;
            transform: translateX(-50%);
            background: #1e293b;
            color: #ffffff;
            padding: 16px;
            border-radius: 10px;
            font-size: 13px;
            width: 320px;
            z-index: 1000;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            line-height: 1.5;
        }
        
        .empty-slot:hover .gap-info {
            display: block;
            animation: tooltipFadeIn 0.2s ease;
        }
        
        @keyframes tooltipFadeIn {
            from { 
                opacity: 0; 
                transform: translateX(-50%) translateY(5px); 
            }
            to { 
                opacity: 1; 
                transform: translateX(-50%) translateY(0); 
            }
        }
        
        .gap-info::after {
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 10px solid transparent;
            border-top-color: #1e293b;
        }
        
        .gap-info-title {
            font-weight: 600;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid #475569;
            color: #60a5fa;
            font-size: 14px;
        }
        
        .doctors-section {
            margin: 10px 0;
        }
        
        .doctors-section-title {
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 12px;
            color: #e2e8f0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .doctor-badge {
            padding: 4px 10px;
            border-radius: 16px;
            margin: 3px;
            display: inline-block;
            font-size: 12px;
            font-weight: 500;
        }
        
        .doctor-available {
            background: #10b981;
            color: #ffffff;
        }
        
        .doctor-restricted {
            background: #f59e0b;
            color: #ffffff;
        }
        
        .reason-text {
            font-size: 11px;
            color: #94a3b8;
            margin-top: 4px;
            display: block;
            font-style: normal;
        }
        
        .no-doctors-text {
            color: #94a3b8;
            font-size: 12px;
            padding: 8px 0;
        }
        
        /* 圖例樣式 */
        .calendar-legend {
            margin-top: 24px;
            padding: 20px;
            background: #f8fafc;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
        }
        
        .legend-title {
            font-weight: 600;
            margin-bottom: 12px;
            color: #1e293b;
            font-size: 16px;
        }
        
        .legend-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            font-size: 14px;
            color: #475569;
        }
        
        .legend-color {
            display: inline-block;
            width: 32px;
            height: 20px;
            margin-right: 10px;
            border-radius: 4px;
        }
        
        /* 響應式設計 */
        @media (max-width: 768px) {
            .calendar-day {
                min-height: 100px;
                padding: 8px;
            }
            
            .day-number {
                font-size: 14px;
            }
            
            .doctor-slot, .empty-slot {
                font-size: 11px;
                padding: 4px 6px;
            }
            
            .gap-info {
                width: 280px;
                font-size: 12px;
            }
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
        html += f'<div class="calendar-header">{self.year}年 {self.month}月 排班表</div>'
        html += '<table class="calendar-table">'
        
        # 星期標題
        html += '<tr>'
        for day_name in ['一', '二', '三', '四', '五', '六', '日']:
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
        html += f'<div class="day-number">'
        html += f'{day}'
        if is_holiday:
            html += '<span class="day-icon">🔴</span>'
        elif is_weekend:
            html += '<span class="day-icon">🟡</span>'
        html += '</div>'
        
        # 顯示排班資訊
        if date_str in schedule:
            slot = schedule[date_str]
            
            # 主治醫師
            if slot.attending:
                html += f'<div class="doctor-slot attending-slot">主治｜{slot.attending}</div>'
            else:
                html += self._generate_empty_slot_html(
                    date_str, "主治", gap_details
                )
            
            # 住院醫師  
            if slot.resident:
                html += f'<div class="doctor-slot resident-slot">住院｜{slot.resident}</div>'
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
        html += f'空缺｜{role}'
        
        # 添加hover提示
        if gap_details and date_str in gap_details:
            if role in gap_details[date_str]:
                info = gap_details[date_str][role]
                
                html += '<div class="gap-info">'
                html += f'<div class="gap-info-title">{date_str} {role}醫師狀況</div>'
                
                # 可直接安排的醫師
                if info.get('available_doctors'):
                    html += '<div class="doctors-section">'
                    html += '<div class="doctors-section-title">可直接安排</div>'
                    html += '<div>'
                    for doc in info['available_doctors'][:5]:
                        html += f'<span class="doctor-badge doctor-available">{doc}</span>'
                    if len(info['available_doctors']) > 5:
                        html += f'<span class="reason-text">另有 {len(info["available_doctors"])-5} 位醫師可選</span>'
                    html += '</div></div>'
                
                # 需要調整的醫師
                if info.get('restricted_doctors'):
                    html += '<div class="doctors-section">'
                    html += '<div class="doctors-section-title">需調整後可安排</div>'
                    for doc_info in info['restricted_doctors'][:3]:
                        html += f'<div style="margin: 6px 0;">'
                        html += f'<span class="doctor-badge doctor-restricted">{doc_info["name"]}</span>'
                        html += f'<span class="reason-text">{doc_info["reason"]}</span>'
                        html += '</div>'
                    if len(info['restricted_doctors']) > 3:
                        html += f'<span class="reason-text">另有 {len(info["restricted_doctors"])-3} 位醫師</span>'
                    html += '</div>'
                
                # 統計資訊
                if not info.get('available_doctors') and not info.get('restricted_doctors'):
                    html += '<div class="no-doctors-text">⚠️ 目前沒有可用的醫師</div>'
                
                if info.get('unavailable_count', 0) > 0:
                    html += f'<div class="reason-text" style="margin-top:12px; padding-top:12px; border-top:1px solid #475569;">另有 {info["unavailable_count"]} 位醫師因請假或其他原因不可值班</div>'
                
                html += '</div>'
        
        html += '</div>'
        
        return html
    
    def _render_legend(self):
        """渲染圖例"""
        st.markdown("""
        <div class="calendar-legend">
            <div class="legend-title">圖例說明</div>
            <div class="legend-grid">
                <div class="legend-item">
                    <span class="legend-color" style="background: #dcfce7; border: 1px solid #86efac;"></span>
                    主治醫師已排班
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background: #dbeafe; border: 1px solid #93c5fd;"></span>
                    住院醫師已排班
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background: #fee2e2; border: 1px solid #fca5a5;"></span>
                    空缺（滑鼠移上查看詳情）
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background: #fef2f2; border: 1px solid #fecaca;"></span>
                    國定假日
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background: #fefce8; border: 1px solid #fde68a;"></span>
                    週末
                </div>
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
            # 使用正確的參數呼叫 get_available_doctors
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
        
        # 住院醫師（注意：這裡應該使用"總醫師"而不是原本錯誤的參數）
        if slot.resident:
            cell_html += f'<div class="doctor-info resident">👨‍⚕️ 住院: {slot.resident}</div>'
        else:
            # 顯示未填格和可選醫師
            available_resident = scheduler.get_available_doctors(
                date_str, "總醫師", schedule,  # 修正：使用"總醫師"而不是錯誤的參數
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