"""
假日月曆設定頁面
"""
import streamlit as st
import calendar
from datetime import date
import pandas as pd

from backend.utils import get_month_calendar

def render():
    """渲染假日設定頁面"""
    st.header("假日與補班管理")
    
    # 獲取當月日期
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    num_days = calendar.monthrange(year, month)[1]
    
    col1, col2 = st.columns(2)
    
    with col1:
        render_holiday_selector(year, month, num_days)
    
    with col2:
        render_workday_selector(year, month, num_days)
    
    # 顯示月曆預覽
    render_calendar_preview(year, month)

def render_holiday_selector(year: int, month: int, num_days: int):
    """渲染假日選擇器"""
    st.subheader("🎉 自訂假日")
    st.info("選擇平日設為假日")
    
    # 生成日期選項
    dates = []
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date.weekday() < 5:  # 平日
            dates.append(current_date.strftime("%Y-%m-%d"))
    
    selected_holidays = st.multiselect(
        "選擇假日",
        dates,
        default=list(st.session_state.holidays)
    )
    st.session_state.holidays = set(selected_holidays)
    
    # 顯示統計
    st.metric("自訂假日數", len(selected_holidays))

def render_workday_selector(year: int, month: int, num_days: int):
    """渲染補班日選擇器"""
    st.subheader("💼 補班日")
    st.info("選擇週末設為工作日")
    
    # 生成週末日期
    weekend_dates = []
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date.weekday() >= 5:  # 週末
            weekend_dates.append(current_date.strftime("%Y-%m-%d"))
    
    selected_workdays = st.multiselect(
        "選擇補班日",
        weekend_dates,
        default=list(st.session_state.workdays)
    )
    st.session_state.workdays = set(selected_workdays)
    
    # 顯示統計
    st.metric("補班日數", len(selected_workdays))

def render_calendar_preview(year: int, month: int):
    """渲染月曆預覽"""
    st.subheader("📅 月曆預覽")
    
    weekdays, holidays = get_month_calendar(
        year, month, 
        st.session_state.holidays,
        st.session_state.workdays
    )
    
    # 建立月曆視圖
    cal_data = []
    week = []
    first_day = date(year, month, 1)
    start_weekday = first_day.weekday()
    num_days = calendar.monthrange(year, month)[1]
    
    # 填充開始的空白
    for _ in range(start_weekday):
        week.append("")
    
    # 填充日期
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        date_str = current_date.strftime("%Y-%m-%d")
        
        if date_str in holidays:
            week.append(f"🎉 {day}")
        elif date_str in weekdays:
            week.append(f"💼 {day}")
        else:
            week.append(str(day))
        
        if len(week) == 7:
            cal_data.append(week)
            week = []
    
    # 填充結尾的空白
    while week and len(week) < 7:
        week.append("")
    if week:
        cal_data.append(week)
    
    # 顯示月曆
    df_cal = pd.DataFrame(cal_data, columns=['一', '二', '三', '四', '五', '六', '日'])
    st.dataframe(df_cal, use_container_width=True)
    
    # 顯示統計資訊
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("總天數", len(weekdays) + len(holidays))
    with col2:
        st.metric("平日", len(weekdays))
    with col3:
        st.metric("假日", len(holidays))
    
    # 圖例說明
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
        <b>圖例：</b> 💼 平日 | 🎉 假日
    </div>
    """, unsafe_allow_html=True)