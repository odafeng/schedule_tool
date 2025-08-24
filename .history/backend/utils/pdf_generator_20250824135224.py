"""
PDF 日曆生成器
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import calendar
from datetime import datetime
from typing import Dict, List
from backend.models import Doctor, ScheduleSlot


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
        
        # 註冊中文字體（需要下載字體檔案）
        try:
            # 嘗試使用系統字體或下載的字體
            pdfmetrics.registerFont(TTFont('ChineseFont', 'NotoSansCJKtc-Regular.ttf'))
            self.chinese_font = 'ChineseFont'
        except:
            # 如果沒有中文字體，使用預設字體
            self.chinese_font = 'Helvetica'
    
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
        story.append(self._create_statistics_table())
        
        # 生成 PDF
        doc.build(story)
    
    def _create_title(self):
        """創建標題"""
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName=self.chinese_font
        )
        
        title_text = f"{self.year}年{self.month}月 醫師排班表"
        return Paragraph(title_text, title_style)
    
    def _create_calendar_table(self):
        """創建月曆表格"""
        # 準備表格資料
        data = []
        
        # 星期標題
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
        data = [['醫師姓名', '角色', '平日值班', '假日值班', '總值班數']]
        
        # 統計每個醫師的值班數
        doctor_stats = {}
        for doctor in self.doctors:
            doctor_stats[doctor.name] = {
                'role': doctor.role,
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
        elements.append(Paragraph("值班統計", subtitle_style))
        elements.append(Spacer(1, 0.2*inch))
        elements.append(table)
        
        return elements[0]  # 返回第一個元素作為示例