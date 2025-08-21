"""
醫師管理維護頁面 - 自動儲存版本
"""
import streamlit as st
import calendar
from datetime import datetime, date
from backend.models import Doctor
from backend.utils.date_parser import parse_date_range, validate_date_input, format_dates_for_display
from frontend.utils.session_manager import SessionManager

def auto_save_doctors():
    """自動儲存醫師資料到 doctors.json"""
    if SessionManager.save_doctors():
        return True
    return False

def render():
    """渲染醫師管理頁面"""
    st.header("醫師名單管理")
    
    # 載入上次設定按鈕 - 保留手動儲存按鈕但改為選項
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if st.button("📂 載入上次設定", type="secondary", use_container_width=True):
            if SessionManager.load_doctors():
                st.success("已載入上次的醫師設定！")
                st.rerun()
            else:
                st.warning("找不到先前儲存的醫師設定")
    
    with col2:
        # 提供手動儲存選項（備用）
        if st.button("💾 手動儲存", type="secondary", use_container_width=True):
            if SessionManager.save_doctors():
                st.success("醫師設定已儲存！")
            else:
                st.error("儲存失敗")
    
    with col3:
        doctor_count = len(st.session_state.doctors)
        attending_count = len([d for d in st.session_state.doctors if d.role == "主治"])
        resident_count = len([d for d in st.session_state.doctors if d.role == "總醫師"])
        st.metric("醫師總數", f"{doctor_count}", f"主治:{attending_count} 總醫師:{resident_count}")
    
    # 顯示自動儲存狀態
    st.info("💡 **自動儲存已啟用** - 所有變更會自動儲存到 doctors.json")
    
    st.divider()
    
    # 新增醫師表單
    with st.expander("➕ 新增醫師", expanded=False):
        render_add_doctor_form()
    
    # 顯示現有醫師
    col1, col2 = st.columns(2)
    
    with col1:
        render_doctor_list("主治")
    
    with col2:
        render_doctor_list("總醫師")

def render_date_input_section(title: str, current_dates: list, key_prefix: str):
    """
    渲染日期輸入區域
    
    Args:
        title: 區域標題
        current_dates: 目前的日期列表
        key_prefix: session key 前綴
    
    Returns:
        tuple: (選擇的日期列表, 是否有錯誤)
    """
    st.subheader(title)
    
    # 建立 tabs
    tab1, tab2 = st.tabs(["📅 月曆選擇", "✏️ 手動輸入"])
    
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 取得月份的所有日期用於月曆選擇
    _, max_day = calendar.monthrange(year, month)
    available_dates = []
    for day in range(1, max_day + 1):
        available_dates.append(date(year, month, day))
    
    selected_dates = []
    has_error = False
    
    with tab1:
        st.write(f"選擇 {year} 年 {month} 月的日期：")
        
        # 從現有日期中提取屬於當前年月的日期
        current_month_dates = []
        for date_str in current_dates:
            try:
                if date_str.startswith(f"{year}-{month:02d}-"):
                    day = int(date_str.split("-")[2])
                    current_month_dates.append(date(year, month, day))
            except:
                continue
        
        # 多選日期輸入
        selected_calendar_dates = st.multiselect(
            "選擇日期",
            options=available_dates,
            default=current_month_dates,
            format_func=lambda x: f"{x.day}日",
            key=f"{key_prefix}_calendar"
        )
        
        # 轉換為字串格式
        calendar_date_strings = [d.strftime("%Y-%m-%d") for d in selected_calendar_dates]
        selected_dates.extend(calendar_date_strings)
    
    with tab2:
        st.write("輸入日期範圍（格式：15,17,18,21-23）：")
        
        # 從現有日期生成輸入字串
        current_input = ""
        current_days = []
        for date_str in current_dates:
            try:
                if date_str.startswith(f"{year}-{month:02d}-"):
                    day = int(date_str.split("-")[2])
                    current_days.append(day)
            except:
                continue
        
        if current_days:
            current_days.sort()
            current_input = ",".join(map(str, current_days))
        
        manual_input = st.text_input(
            "日期範圍",
            value=current_input,
            placeholder="例如：1,5,10-15,20",
            key=f"{key_prefix}_manual",
            help="支援單個日期（如 5）和範圍（如 10-15），用逗號分隔"
        )
        
        # 即時驗證
        if manual_input:
            format_error = validate_date_input(manual_input)
            if format_error:
                st.error(f"格式錯誤：{format_error}")
                has_error = True
            else:
                try:
                    manual_dates = parse_date_range(manual_input, year, month)
                    selected_dates.extend(manual_dates)
                    
                    # 顯示預覽
                    if manual_dates:
                        preview = format_dates_for_display(manual_dates)
                        st.success(f"將新增日期：{preview}")
                except ValueError as e:
                    st.error(f"日期錯誤：{str(e)}")
                    has_error = True
    
    # 移除重複並排序
    unique_dates = sorted(list(set(selected_dates)))
    
    # 顯示最終預覽
    if unique_dates:
        st.info(f"**總計選擇：** {format_dates_for_display(unique_dates)}")
    
    return unique_dates, has_error

def render_add_doctor_form():
    """渲染新增醫師表單"""
    with st.form("add_doctor_form"):
        st.subheader("新增醫師資訊")
        
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("醫師姓名*", placeholder="請輸入醫師姓名")
            role = st.selectbox("角色*", ["主治", "總醫師"])
        
        with col2:
            weekday_quota = st.number_input("平日配額", min_value=0, max_value=20, value=5)
            holiday_quota = st.number_input("假日配額", min_value=0, max_value=10, value=2)
        
        st.divider()
        
        # 不可值班日期選擇
        unavailable_dates, unavail_error = render_date_input_section(
            "❌ 不可值班日", [], "add_unavailable"
        )
        
        st.divider()
        
        # 優先值班日期選擇
        preferred_dates, pref_error = render_date_input_section(
            "⭐ 優先值班日", [], "add_preferred"
        )
        
        # 檢查日期衝突
        conflict_dates = set(unavailable_dates) & set(preferred_dates)
        if conflict_dates:
            st.error(f"發現衝突日期：{format_dates_for_display(list(conflict_dates))} 不能同時是不可值班日和優先值班日")
        
        # 提交按鈕
        submit_disabled = not name or unavail_error or pref_error or bool(conflict_dates)
        
        if st.form_submit_button("新增醫師", type="primary", disabled=submit_disabled):
            if name:
                # 檢查姓名是否重複
                existing_names = [d.name for d in st.session_state.doctors]
                if name in existing_names:
                    st.error(f"醫師姓名 '{name}' 已存在")
                else:
                    new_doctor = Doctor(
                        name=name,
                        role=role,
                        weekday_quota=weekday_quota,
                        holiday_quota=holiday_quota,
                        unavailable_dates=unavailable_dates,
                        preferred_dates=preferred_dates
                    )
                    st.session_state.doctors.append(new_doctor)
                    
                    # 自動儲存到 doctors.json
                    if auto_save_doctors():
                        st.success(f"✅ 已新增醫師：{name} (已自動儲存)")
                    else:
                        st.warning(f"✅ 已新增醫師：{name} (自動儲存失敗，請手動儲存)")
                    
                    st.rerun()
            else:
                st.error("請輸入醫師姓名")

def render_doctor_list(role: str):
    """渲染醫師列表"""
    if role == "主治":
        st.subheader("👨‍⚕️ 主治醫師")
        doctors = [d for d in st.session_state.doctors if d.role == "主治"]
    else:
        st.subheader("👩‍⚕️ 總醫師")
        doctors = [d for d in st.session_state.doctors if d.role == "總醫師"]
    
    if doctors:
        for doc in doctors:
            with st.container():
                # 醫師資訊卡片
                st.markdown(f"""
                <div style="
                    border: 1px solid #ddd; 
                    border-radius: 10px; 
                    padding: 15px; 
                    margin: 10px 0;
                    background-color: #f9f9f9;
                ">
                    <h4 style="margin: 0 0 10px 0; color: #333;">{doc.name}</h4>
                    <p style="margin: 5px 0; font-size: 14px;">
                        📅 平日配額: <strong>{doc.weekday_quota}</strong> | 假日配額: <strong>{doc.holiday_quota}</strong>
                    </p>
                    <p style="margin: 5px 0; font-size: 14px;">
                        ❌ 不可值班: <strong>{len(doc.unavailable_dates)}</strong>天 | 
                        ⭐ 優先值班: <strong>{len(doc.preferred_dates)}</strong>天
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✏️ 編輯", key=f"edit_{doc.name}", use_container_width=True):
                        st.session_state[f"editing_{doc.name}"] = True
                        st.rerun()
                with col2:
                    if st.button(f"🗑️ 刪除", key=f"del_{doc.name}", use_container_width=True):
                        st.session_state.doctors.remove(doc)
                        
                        # 自動儲存到 doctors.json
                        if auto_save_doctors():
                            st.success(f"已刪除醫師：{doc.name} (已自動儲存)")
                        else:
                            st.warning(f"已刪除醫師：{doc.name} (自動儲存失敗，請手動儲存)")
                        
                        st.rerun()
                
                # 編輯表單
                if st.session_state.get(f"editing_{doc.name}", False):
                    render_edit_doctor_form(doc)
    else:
        st.info(f"尚未新增{role}醫師")

def render_edit_doctor_form(doctor: Doctor):
    """渲染編輯醫師表單"""
    with st.form(f"edit_form_{doctor.name}"):
        st.subheader(f"編輯醫師：{doctor.name}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            weekday_quota = st.number_input(
                "平日配額", 
                min_value=0, 
                max_value=20, 
                value=doctor.weekday_quota
            )
        
        with col2:
            holiday_quota = st.number_input(
                "假日配額", 
                min_value=0, 
                max_value=10, 
                value=doctor.holiday_quota
            )
        
        st.divider()
        
        # 不可值班日期選擇
        unavailable_dates, unavail_error = render_date_input_section(
            "❌ 不可值班日", doctor.unavailable_dates, f"edit_unavailable_{doctor.name}"
        )
        
        st.divider()
        
        # 優先值班日期選擇
        preferred_dates, pref_error = render_date_input_section(
            "⭐ 優先值班日", doctor.preferred_dates, f"edit_preferred_{doctor.name}"
        )
        
        # 檢查日期衝突
        conflict_dates = set(unavailable_dates) & set(preferred_dates)
        if conflict_dates:
            st.error(f"發現衝突日期：{format_dates_for_display(list(conflict_dates))} 不能同時是不可值班日和優先值班日")
        
        col1, col2 = st.columns(2)
        submit_disabled = unavail_error or pref_error or bool(conflict_dates)
        
        with col1:
            if st.form_submit_button("💾 儲存", disabled=submit_disabled, use_container_width=True):
                doctor.weekday_quota = weekday_quota
                doctor.holiday_quota = holiday_quota
                doctor.unavailable_dates = unavailable_dates
                doctor.preferred_dates = preferred_dates
                st.session_state[f"editing_{doctor.name}"] = False
                
                # 自動儲存到 doctors.json
                if auto_save_doctors():
                    st.success(f"✅ 已更新醫師：{doctor.name} (已自動儲存)")
                else:
                    st.warning(f"✅ 已更新醫師：{doctor.name} (自動儲存失敗，請手動儲存)")
                
                st.rerun()
        
        with col2:
            if st.form_submit_button("❌ 取消", use_container_width=True):
                st.session_state[f"editing_{doctor.name}"] = False
                st.rerun()