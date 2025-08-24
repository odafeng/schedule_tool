"""
PDF 日曆生成器 - 支援中文顯示
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import calendar
from datetime import datetime
from typing import Dict, List
from backend.models import Doctor, ScheduleSlot
import os
import platform
import streamlit as st


class PDFCalendarGenerator:
    """PDF 日曆生成器"""
    
    def __init__(self, schedule: Dict[str, ScheduleSlot], 
                 doctors: List[Doctor],
                 weekdays: List[str], 
                 holidays: List[str],
                 year: int, 
                 month: int):
        self.schedule = schedule
        self.doctors = doctors
        self.weekdays = weekdays
        self.holidays = holidays
        self.year = year
        self.month = month
        
        # 註冊中文字體
        self.chinese_font = self._register_chinese_font()
    
    def _register_chinese_font(self):
        """註冊中文字體，依序嘗試不同的方法"""
        
        # 方法1: 使用內建的 CID 字體（最可靠）
        try:
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            return 'STSong-Light'
        except:
            pass
        
        # 方法2: 根據操作系統尋找系統字體
        system = platform.system()
        font_paths = []
        
        if system == "Windows":
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微軟雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑體
                "C:/Windows/Fonts/simsun.ttc",  # 宋體
                "C:/Windows/Fonts/msjh.ttc",   # 微軟正黑體
            ]
        elif system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
            ]
        elif system == "Linux":
            font_paths = [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            ]
        
        # 嘗試每個可能的字體路徑
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_name = os.path.basename(font_path).split('.')[0]
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    return font_name
                except:
                    continue
        
        # 方法3: 嘗試從專案目錄載入字體
        project_fonts = [
            "fonts/NotoSansCJKtc-Regular.ttf",
            "fonts/SourceHanSans-Regular.ttf",
            "fonts/DroidSansFallback.ttf",
        ]
        
        for font_file in project_fonts:
            if os.path.exists(font_file):
                try:
                    font_name = os.path.basename(font_file).split('.')[0]
                    pdfmetrics.registerFont(TTFont(font_name, font_file))
                    return font_name
                except:
                    continue
        
        # 方法4: 使用 Helvetica 作為最後的後備選項
        st.warning("無法找到中文字體，PDF 中的中文可能無法正確顯示。建議下載 Noto Sans CJK 字體並放置在專案的 fonts 目錄中。")
        return 'Helvetica'
    
    def generate(self, filename: str):
        """生成 PDF 檔案"""
        doc = SimpleDocTemplate(
            filename,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        
        # 建立內容
        story = []
        
        # 添加標題
        story.append(self._create_title())
        story.append(Spacer(1, 0.3*inch))
        
        # 添加月曆
        story.append(self._create_calendar_table())
        story.append(PageBreak())
        
        # 添加統計表
        stats_elements = self._create_statistics_table()
        for element in stats_elements:
            story.append(element)
        
        # 生成 PDF
        doc.build(story)
    
    def _create_title(self):
        """創建標題"""
        styles = getSampleStyleSheet()
        
        # 如果沒有中文字體，使用英文標題
        if self.chinese_font == 'Helvetica':
            title_text = f"Doctor Schedule - {self.year}/{self.month:02d}"
        else:
            title_text = f"{self.year}年{self.month}月 醫師排班表"
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName=self.chinese_font
        )
        
        return Paragraph(title_text, title_style)
    
    def _create_calendar_table(self):
        """創建月曆表格"""
        # 準備表格資料
        data = []
        
        # 星期標題
        if self.chinese_font == 'Helvetica':
            weekday_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        else:
            weekday_names = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
        data.append(weekday_names)
        
        # 生成月曆
        cal = calendar.monthcalendar(self.year, self.month)
        
        for week in cal:
            week_data = []
            for day_of_week, day in enumerate(week):
                if day == 0:
                    week_data.append("")
                else:
                    date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
                    
                    if self.chinese_font == 'Helvetica':
                        # 英文版本
                        cell_content = f"Day {day}\n"
                        if date_str in self.schedule:
                            slot = self.schedule[date_str]
                            if slot.attending:
                                cell_content += f"A: {slot.attending}\n"
                            if slot.resident:
                                cell_content += f"R: {slot.resident}"
                    else:
                        # 中文版本
                        cell_content = f"{day}日\n"
                        if date_str in self.schedule:
                            slot = self.schedule[date_str]
                            if slot.attending:
                                cell_content += f"主治: {slot.attending}\n"
                            if slot.resident:
                                cell_content += f"總醫: {slot.resident}"
                    
                    week_data.append(cell_content)
            
            data.append(week_data)
        
        # 創建表格
        table = Table(data, colWidths=[1.5*inch]*7, rowHeights=[0.4*inch] + [1.2*inch]*len(cal))
        
        # 設定表格樣式
        style = TableStyle([
            # 整體樣式
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTNAME', (0, 0), (-1, -1), self.chinese_font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            
            # 星期標題樣式
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTNAME', (0, 0), (-1, 0), self.chinese_font),
        ])
        
        # 標記假日和週末
        for week_idx, week in enumerate(cal, start=1):
            for day_idx, day in enumerate(week):
                if day != 0:
                    date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
                    
                    # 假日背景色
                    if date_str in self.holidays:
                        style.add('BACKGROUND', (day_idx, week_idx), (day_idx, week_idx), 
                                 colors.HexColor('#ffe6e6'))
                    # 週末背景色
                    elif day_idx in [5, 6]:
                        style.add('BACKGROUND', (day_idx, week_idx), (day_idx, week_idx), 
                                 colors.HexColor('#fff4e6'))
                    # 平日背景色
                    else:
                        style.add('BACKGROUND', (day_idx, week_idx), (day_idx, week_idx), 
                                 colors.HexColor('#e6f3ff'))
        
        table.setStyle(style)
        return table
    
    def _create_statistics_table(self):
        """創建統計表格"""
        # 準備資料
        if self.chinese_font == 'Helvetica':
            headers = ['Doctor Name', 'Role', 'Weekday Duties', 'Holiday Duties', 'Total']
            subtitle = "Duty Statistics"
        else:
            headers = ['醫師姓名', '角色', '平日值班', '假日值班', '總值班數']
            subtitle = "值班統計"
        
        data = [headers]
        
        # 統計每個醫師的值班數
        doctor_stats = {}
        for doctor in self.doctors:
            doctor_stats[doctor.name] = {
                'role': doctor.role if self.chinese_font != 'Helvetica' else 
                        ('Attending' if doctor.role == '主治' else 'Resident'),
                'weekday': 0,
                'holiday': 0,
                'total': 0
            }
        
        for date_str, slot in self.schedule.items():
            is_holiday = date_str in self.holidays
            
            if slot.attending and slot.attending in doctor_stats:
                if is_holiday:
                    doctor_stats[slot.attending]['holiday'] += 1
                else:
                    doctor_stats[slot.attending]['weekday'] += 1
                doctor_stats[slot.attending]['total'] += 1
            
            if slot.resident and slot.resident in doctor_stats:
                if is_holiday:
                    doctor_stats[slot.resident]['holiday'] += 1
                else:
                    doctor_stats[slot.resident]['weekday'] += 1
                doctor_stats[slot.resident]['total'] += 1
        
        # 加入資料
        for doctor_name, stats in doctor_stats.items():
            data.append([
                doctor_name,
                stats['role'],
                str(stats['weekday']),
                str(stats['holiday']),
                str(stats['total'])
            ])
        
        # 創建表格
        table = Table(data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        
        # 設定樣式
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), self.chinese_font),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
        ]))
        
        # 添加標題
        styles = getSampleStyleSheet()
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName=self.chinese_font
        )
        
        elements = []
        elements.append(Paragraph(subtitle, subtitle_style))
        elements.append(Spacer(1, 0.2*inch))
        elements.append(table)
        
        return elements