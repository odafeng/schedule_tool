"""
假日月曆設定頁面 - 具備記憶功能版本
"""
import streamlit as st
import calendar
from datetime import date, datetime
import pandas as pd
from backend.utils.holiday_manager import HolidayManager, get_month_calendar_with_memory

def render():
    """渲染假日設定頁面"""
    st.header("📅 假日與補班管理")
    
    # 初始化假日管理器
    if 'holiday_manager' not in st.session_state:
        st.session_state.holiday_manager = HolidayManager()
    
    holiday_manager = st.session_state.holiday_manager
    
    # 獲取當前選擇的年月
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 主要操作區
    tab1, tab2, tab3, tab4 = st.tabs(["📅 月曆預覽", "🎉 假日管理", "💼 補班管理", "📊 統計資訊"])
    
    with tab1:
        render_calendar_preview(year, month, holiday_manager)
    
    with tab2:
        render_holiday_management(year, month, holiday_manager)
    
    with tab3:
        render_workday_management(year, month, holiday_manager)
    
    with tab4:
        render_statistics(year, holiday_manager)

def render_calendar_preview(year: int, month: int, holiday_manager: HolidayManager):
    """渲染月曆預覽"""
    st.subheader(f"📅 {year}年{month}月 月曆預覽")
    
    # 取得假日和平日列表
    weekdays, holidays = get_month_calendar_with_memory(year, month, holiday_manager)
    
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
        
        # 取得假日資訊
        holiday_info = holiday_manager.get_holiday_info(date_str)
        is_workday = holiday_manager.is_workday(date_str)
        
        if holiday_info:
            # 是假日，顯示假日名稱
            week.append(f"🎉 {day}\n{holiday_info.get('name', '')[:4]}")
        elif is_workday:
            # 是補班日
            week.append(f"💼 {day}\n補班")
        elif date_str in holidays:
            # 一般週末
            week.append(f"😴 {day}")
        else:
            # 一般平日
            week.append(f"{day}")
        
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
    st.dataframe(df_cal, use_container_width=True, height=300)
    
    # 顯示統計資訊
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總天數", num_days)
    with col2:
        st.metric("平日", len(weekdays))
    with col3:
        st.metric("假日", len(holidays))
    with col4:
        st.metric("淨假日", len(holidays) - len([d for d in holidays if holiday_manager.is_workday(d)]))
    
    # 圖例說明
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-top: 10px;">
        <b>圖例說明：</b><br>
        🎉 國定假日或自訂假日 | 😴 週末 | 💼 補班日 | 數字 一般平日
    </div>
    """, unsafe_allow_html=True)

def render_holiday_management(year: int, month: int, holiday_manager: HolidayManager):
    """渲染假日管理介面"""
    st.subheader("🎉 假日管理")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 新增假日
        st.markdown("### 新增自訂假日")
        
        selected_date = st.date_input(
            "選擇日期",
            value=date(year, month, 1),
            min_value=date(year, 1, 1),
            max_value=date(year, 12, 31),
            key="add_holiday_date"
        )
        
        holiday_name = st.text_input("假日名稱", placeholder="例如：醫院週年慶")
        
        is_recurring = st.checkbox("每年循環", help="勾選後，每年的這一天都會是假日")
        
        if st.button("➕ 新增假日", type="primary", use_container_width=True):
            date_str = selected_date.strftime("%Y-%m-%d")
            if holiday_manager.add_custom_holiday(date_str, holiday_name or "自訂假日", is_recurring):
                st.success(f"✅ 成功新增假日：{date_str} {holiday_name}")
                st.rerun()
            else:
                st.warning("⚠️ 該日期已經是假日")
    
    with col2:
        # 顯示現有假日
        st.markdown("### 本月假日列表")
        
        # 取得本月所有假日
        holidays_list = []
        _, holiday_dates = get_month_calendar_with_memory(year, month, holiday_manager)
        
        for date_str in sorted(holiday_dates):
            holiday_info = holiday_manager.get_holiday_info(date_str)
            if holiday_info:
                holidays_list.append({
                    "日期": date_str,
                    "名稱": holiday_info.get("name", "假日"),
                    "類型": holiday_info.get("type", "unknown")
                })
        
        if holidays_list:
            for holiday in holidays_list:
                with st.container():
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.text(f"{holiday['日期']} - {holiday['名稱']}")
                    with col_b:
                        if holiday['類型'] == 'custom':
                            if st.button("🗑️", key=f"del_{holiday['日期']}"):
                                holiday_manager.remove_custom_holiday(holiday['日期'])
                                st.rerun()
        else:
            st.info("本月暫無假日")
    
    # 批量匯入/匯出功能
    st.divider()
    st.markdown("### 批量操作")
    
    col3, col4 = st.columns(2)
    
    with col3:
        uploaded_file = st.file_uploader(
            "匯入假日 CSV",
            type=['csv'],
            help="CSV 格式：date,name,type,recurring"
        )
        if uploaded_file is not None:
            if st.button("📥 匯入"):
                # 儲存暫存檔案
                temp_path = f"temp_{uploaded_file.name}"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                if holiday_manager.import_holidays_from_csv(temp_path):
                    st.success("✅ 成功匯入假日資料")
                    st.rerun()
                else:
                    st.error("❌ 匯入失敗，請檢查 CSV 格式")
                
                # 清理暫存檔案
                import os
                os.remove(temp_path)
    
    with col4:
        if st.button("📤 匯出假日資料", use_container_width=True):
            csv_path = f"holidays_{year}.csv"
            if holiday_manager.export_holidays_to_csv(year, csv_path):
                with open(csv_path, "rb") as f:
                    st.download_button(
                        label="💾 下載 CSV",
                        data=f,
                        file_name=csv_path,
                        mime="text/csv"
                    )
                # 清理檔案
                import os
                os.remove(csv_path)

def render_workday_management(year: int, month: int, holiday_manager: HolidayManager):
    """渲染補班日管理介面"""
    st.subheader("💼 補班日管理")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 新增補班日
        st.markdown("### 新增補班日")
        
        # 只顯示週末供選擇
        weekend_dates = []
        num_days = calendar.monthrange(year, month)[1]
        for day in range(1, num_days + 1):
            current_date = date(year, month, day)
            if current_date.weekday() >= 5:  # 週末
                weekend_dates.append(current_date)
        
        if weekend_dates:
            selected_workday = st.selectbox(
                "選擇週末作為補班日",
                weekend_dates,
                format_func=lambda x: f"{x.strftime('%Y-%m-%d')} ({['週一','週二','週三','週四','週五','週六','週日'][x.weekday()]})"
            )
            
            workday_name = st.text_input("補班說明", placeholder="例如：春節補班")
            
            compensate_date = st.date_input(
                "補償假日（選填）",
                value=None,
                help="這個補班日是為了補償哪個假日"
            )
            
            if st.button("➕ 新增補班日", type="primary", use_container_width=True):
                date_str = selected_workday.strftime("%Y-%m-%d")
                compensate_str = compensate_date.strftime("%Y-%m-%d") if compensate_date else None
                
                if holiday_manager.add_makeup_workday(date_str, workday_name or "補班日", compensate_str):
                    st.success(f"✅ 成功新增補班日：{date_str}")
                    st.rerun()
                else:
                    st.warning("⚠️ 該日期已經是補班日")
        else:
            st.info("本月沒有週末可設為補班日")
    
    with col2:
        # 顯示現有補班日
        st.markdown("### 本月補班日列表")
        
        workdays_list = holiday_manager.get_all_workdays_in_year(year)
        month_workdays = [
            w for w in workdays_list 
            if datetime.strptime(w['date'], "%Y-%m-%d").month == month
        ]
        
        if month_workdays:
            for workday in month_workdays:
                with st.container():
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.text(f"{workday['date']} - {workday.get('name', '補班日')}")
                    with col_b:
                        if st.button("🗑️", key=f"del_work_{workday['date']}"):
                            holiday_manager.remove_makeup_workday(workday['date'])
                            st.rerun()
        else:
            st.info("本月暫無補班日")

def render_statistics(year: int, holiday_manager: HolidayManager):
    """渲染統計資訊"""
    st.subheader(f"📊 {year}年 假日統計")
    
    # 取得統計資料
    stats = holiday_manager.get_statistics(year)
    
    # 顯示主要指標
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("總假日數", stats['total_holidays'])
    
    with col2:
        st.metric("總補班日數", stats['total_workdays'])
    
    with col3:
        st.metric("淨假日數", stats['net_holidays'])
    
    with col4:
        total_days = 365 if year % 4 != 0 else 366
        work_days = total_days - stats['net_holidays']
        st.metric("工作日數", work_days)
    
    # 假日類型分布
    st.divider()
    st.markdown("### 假日類型分布")
    
    if stats['holiday_types']:
        df_types = pd.DataFrame(
            list(stats['holiday_types'].items()),
            columns=['類型', '天數']
        )
        
        # 類型中文對照
        type_mapping = {
            'national': '國定假日',
            'traditional': '傳統節日',
            'custom': '自訂假日',
            'spring_festival': '春節',
            'unknown': '其他'
        }
        
        df_types['類型'] = df_types['類型'].map(lambda x: type_mapping.get(x, x))
        
        # 顯示圖表
        st.bar_chart(df_types.set_index('類型'))
    else:
        st.info("暫無假日資料")
    
    # 清除資料功能
    st.divider()
    st.markdown("### ⚠️ 危險操作")
    
    if st.button("🗑️ 清除所有自訂假日和補班日", type="secondary"):
        if holiday_manager.clear_user_defined_holidays():
            st.success("✅ 已清除所有自訂假日和補班日")
            st.rerun()
        else:
            st.error("❌ 清除失敗")