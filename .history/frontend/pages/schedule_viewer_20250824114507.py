"""
班表檢視與匯出頁面
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from backend.utils import get_month_calendar
from backend.algorithms import Stage2AdvancedSwapper
from frontend.components import CalendarView, ScheduleTable

def render():
    """渲染班表檢視頁面"""
    st.header("排班結果檢視")
    
    if st.session_state.schedule_result is None:
        st.info("請先執行排班")
        return
    
    result = st.session_state.schedule_result
    
    # 獲取月份資料
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    
    # 重建scheduler用於獲取可用醫師資訊
    scheduler = Stage2AdvancedSwapper(
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays
    )
    
    # 顯示模式選擇
    view_mode = st.radio(
        "檢視模式",
        ["月曆視圖", "列表視圖"],
        horizontal=True
    )
    
    if view_mode == "月曆視圖":
        render_calendar_view(result, scheduler, weekdays, holidays)
    else:
        render_list_view(result, scheduler, weekdays, holidays)
    
    # 匯出功能
    render_export_section(result, scheduler)

def render_calendar_view(result, scheduler, weekdays, holidays):
    """渲染月曆視圖"""
    st.subheader("📅 月曆班表")
    
    calendar_view = CalendarView(
        st.session_state.selected_year,
        st.session_state.selected_month
    )
    
    html_content = calendar_view.generate_html(
        result.schedule,
        scheduler,
        weekdays,
        holidays
    )
    
    st.markdown(html_content, unsafe_allow_html=True)
    
    # 圖例說明
    st.markdown("""
    <div style="margin-top: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
        <h4>圖例說明</h4>
        <p>🎉 假日 | 👨‍⚕️ 已排班醫師 | ❌ 未排班（紅底）| ⚠️ 無可用醫師</p>
        <p><span style="background-color: #e3f2fd; padding: 2px 5px;">藍色</span> 主治醫師 | 
           <span style="background-color: #f3e5f5; padding: 2px 5px;">紫色</span> 住院醫師</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 未填格詳細資訊
    if result.unfilled_slots:
        with st.expander(f"⚠️ 未填格詳細資訊 ({len(result.unfilled_slots)} 個)", expanded=False):
            for date_str, role in result.unfilled_slots:
                available = scheduler.get_available_doctors(
                    date_str, role, result.schedule,
                    scheduler.doctor_map, scheduler.constraints,
                    scheduler.weekdays, scheduler.holidays
                )
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                
                if available:
                    st.write(f"📅 **{dt.month}/{dt.day} {role}**")
                    st.write(f"   可選醫師：{', '.join(available)}")
                else:
                    st.write(f"📅 **{dt.month}/{dt.day} {role}**")
                    st.write(f"   ⚠️ 無可用醫師（可能因為配額已滿或連續值班限制）")

def render_list_view(result, scheduler, weekdays, holidays):
    """渲染列表視圖"""
    st.subheader("📋 列表班表")
    
    schedule_table = ScheduleTable()
    df_schedule = schedule_table.create_dataframe(
        result.schedule,
        scheduler,
        weekdays,
        holidays
    )
    
    # 使用顏色標記
    styled_df = schedule_table.apply_styles(df_schedule)
    st.dataframe(styled_df, use_container_width=True, height=600)

def render_export_section(result, scheduler):
    """渲染匯出區塊"""
    st.divider()
    st.subheader("📥 匯出功能")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 匯出CSV
        csv_data = export_to_csv(result, scheduler)
        st.download_button(
            label="📥 下載 CSV",
            data=csv_data,
            file_name=f"schedule_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        # 儲存結果為JSON
        if st.button("💾 儲存排班結果", use_container_width=True):
            save_schedule_result(result, scheduler)
            st.success("結果已儲存")
    
    with col3:
        # 生成列印版
        if st.button("🖨️ 產生列印版", use_container_width=True):
            generate_print_version(result)

def export_to_csv(result, scheduler):
    """匯出為CSV格式"""
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    
    csv_data = []
    all_dates = sorted(holidays + weekdays)
    
    for date_str in all_dates:
        if date_str in result.schedule:
            slot = result.schedule[date_str]
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            csv_data.append({
                '日期': date_str,
                '星期': ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()],
                '類型': '假日' if date_str in holidays else '平日',
                '主治醫師': slot.attending or '未排',
                '住院醫師': slot.resident or '未排'
            })
    
    df_csv = pd.DataFrame(csv_data)
    return df_csv.to_csv(index=False, encoding='utf-8-sig')

def save_schedule_result(result, scheduler):
    """儲存排班結果"""
    save_result = {
        'year': st.session_state.selected_year,
        'month': st.session_state.selected_month,
        'schedule': {k: {'date': v.date, 'attending': v.attending, 'resident': v.resident} 
                    for k, v in result.schedule.items()},
        'statistics': result.statistics,
        'unfilled_details': []
    }
    
    # 加入未填格的可選醫師資訊
    for date_str, role in result.unfilled_slots:
        available = scheduler.get_available_doctors(
            date_str, role, result.schedule,
            scheduler.doctor_map, scheduler.constraints,
            scheduler.weekdays, scheduler.holidays
        )
        save_result['unfilled_details'].append({
            'date': date_str,
            'role': role,
            'available_doctors': available
        })
    
    filename = f"data/schedules/schedule_result_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.json"
    
    # 確保目錄存在
    import os
    os.makedirs("data/schedules", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(save_result, f, ensure_ascii=False, indent=2)

def generate_print_version(result):
    """生成列印版本"""
    st.info("列印版功能開發中...")
    # TODO: 實作產生適合列印的PDF或HTML版本