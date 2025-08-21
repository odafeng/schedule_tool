"""
醫師管理維護頁面
"""
import streamlit as st
from backend.models import Doctor

def render():
    """渲染醫師管理頁面"""
    st.header("醫師名單管理")
    
    # 快速測試資料
    with st.expander("🧪 載入測試資料", expanded=False):
        render_test_data_loader()
    
    # 新增醫師表單
    with st.expander("➕ 新增醫師", expanded=False):
        render_add_doctor_form()
    
    # 顯示現有醫師
    col1, col2 = st.columns(2)
    
    with col1:
        render_doctor_list("主治")
    
    with col2:
        render_doctor_list("住院")

def render_test_data_loader():
    """渲染測試資料載入器"""
    test_scenario = st.selectbox(
        "選擇測試場景",
        ["基本測試 (6主治+7住院)", "困難測試 (衝突多)", "大規模測試 (10+10)"]
    )
    
    if st.button("載入測試資料", type="secondary"):
        st.session_state.doctors = []
        
        if test_scenario == "基本測試 (6主治+7住院)":
            # 6位主治醫師
            for i in range(1, 7):
                st.session_state.doctors.append(Doctor(
                    name=f"主治{i}",
                    role="主治",
                    weekday_quota=4,
                    holiday_quota=2,
                    unavailable_dates=[],
                    preferred_dates=[]
                ))
            
            # 7位住院醫師
            for i in range(1, 8):
                st.session_state.doctors.append(Doctor(
                    name=f"住院{i}",
                    role="住院",
                    weekday_quota=5,
                    holiday_quota=2,
                    unavailable_dates=[],
                    preferred_dates=[]
                ))
            
        elif test_scenario == "困難測試 (衝突多)":
            year = st.session_state.selected_year
            month = st.session_state.selected_month
            
            # 建立衝突的不可值班日
            dates = [f"{year}-{month:02d}-{d:02d}" for d in range(5, 15)]
            
            # 3位主治醫師（衝突多）
            st.session_state.doctors.append(Doctor(
                name="主治A",
                role="主治",
                weekday_quota=3,
                holiday_quota=1,
                unavailable_dates=dates[:5],
                preferred_dates=[dates[10]] if len(dates) > 10 else []
            ))
            st.session_state.doctors.append(Doctor(
                name="主治B",
                role="主治",
                weekday_quota=3,
                holiday_quota=1,
                unavailable_dates=dates[3:8],
                preferred_dates=[]
            ))
            st.session_state.doctors.append(Doctor(
                name="主治C",
                role="主治",
                weekday_quota=4,
                holiday_quota=2,
                unavailable_dates=dates[6:9],
                preferred_dates=[]
            ))
            
            # 4位住院醫師（衝突多）
            for i in range(1, 5):
                unavail = dates[i:i+3] if i < 7 else []
                st.session_state.doctors.append(Doctor(
                    name=f"住院{i}",
                    role="住院",
                    weekday_quota=4,
                    holiday_quota=2,
                    unavailable_dates=unavail,
                    preferred_dates=[]
                ))
        
        else:  # 大規模測試
            # 10位主治醫師
            for i in range(1, 11):
                st.session_state.doctors.append(Doctor(
                    name=f"主治{i:02d}",
                    role="主治",
                    weekday_quota=3,
                    holiday_quota=1,
                    unavailable_dates=[],
                    preferred_dates=[]
                ))
            
            # 10位住院醫師
            for i in range(1, 11):
                st.session_state.doctors.append(Doctor(
                    name=f"住院{i:02d}",
                    role="住院",
                    weekday_quota=3,
                    holiday_quota=1,
                    unavailable_dates=[],
                    preferred_dates=[]
                ))
        
        st.success(f"已載入 {test_scenario}")
        st.rerun()

def render_add_doctor_form():
    """渲染新增醫師表單"""
    with st.form("add_doctor_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            name = st.text_input("醫師姓名")
            role = st.selectbox("角色", ["主治", "住院"])
        
        with col2:
            weekday_quota = st.number_input("平日配額", min_value=0, max_value=20, value=5)
            holiday_quota = st.number_input("假日配額", min_value=0, max_value=10, value=2)
        
        with col3:
            unavailable = st.text_area("不可值班日(YYYY-MM-DD，每行一個)")
            preferred = st.text_area("優先值班日(YYYY-MM-DD，每行一個)")
        
        if st.form_submit_button("新增醫師", type="primary"):
            if name:
                unavailable_dates = [d.strip() for d in unavailable.split('\n') if d.strip()]
                preferred_dates = [d.strip() for d in preferred.split('\n') if d.strip()]
                
                new_doctor = Doctor(
                    name=name,
                    role=role,
                    weekday_quota=weekday_quota,
                    holiday_quota=holiday_quota,
                    unavailable_dates=unavailable_dates,
                    preferred_dates=preferred_dates
                )
                st.session_state.doctors.append(new_doctor)
                st.success(f"已新增醫師：{name}")
                st.rerun()
            else:
                st.error("請輸入醫師姓名")

def render_doctor_list(role: str):
    """渲染醫師列表"""
    if role == "主治":
        st.subheader("👨‍⚕️ 主治醫師")
        doctors = [d for d in st.session_state.doctors if d.role == "主治"]
    else:
        st.subheader("👨‍⚕️ 住院醫師")
        doctors = [d for d in st.session_state.doctors if d.role == "住院"]
    
    if doctors:
        for doc in doctors:
            with st.container():
                st.markdown(f"""
                <div class="doctor-card">
                    <h4>{doc.name}</h4>
                    <p>平日配額: {doc.weekday_quota} | 假日配額: {doc.holiday_quota}</p>
                    <p>不可值班: {len(doc.unavailable_dates)}天 | 優先值班: {len(doc.preferred_dates)}天</p>
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"編輯", key=f"edit_{doc.name}"):
                        st.session_state[f"editing_{doc.name}"] = True
                with col2:
                    if st.button(f"刪除", key=f"del_{doc.name}"):
                        st.session_state.doctors.remove(doc)
                        st.rerun()
                
                # 編輯表單
                if st.session_state.get(f"editing_{doc.name}", False):
                    render_edit_doctor_form(doc)
    else:
        st.info(f"尚未新增{role}醫師")

def render_edit_doctor_form(doctor: Doctor):
    """渲染編輯醫師表單"""
    with st.form(f"edit_form_{doctor.name}"):
        col1, col2 = st.columns(2)
        
        with col1:
            weekday_quota = st.number_input(
                "平日配額", 
                min_value=0, 
                max_value=20, 
                value=doctor.weekday_quota
            )
            holiday_quota = st.number_input(
                "假日配額", 
                min_value=0, 
                max_value=10, 
                value=doctor.holiday_quota
            )
        
        with col2:
            unavailable = st.text_area(
                "不可值班日",
                value='\n'.join(doctor.unavailable_dates)
            )
            preferred = st.text_area(
                "優先值班日",
                value='\n'.join(doctor.preferred_dates)
            )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("儲存"):
                doctor.weekday_quota = weekday_quota
                doctor.holiday_quota = holiday_quota
                doctor.unavailable_dates = [d.strip() for d in unavailable.split('\n') if d.strip()]
                doctor.preferred_dates = [d.strip() for d in preferred.split('\n') if d.strip()]
                st.session_state[f"editing_{doctor.name}"] = False
                st.success("已更新")
                st.rerun()
        
        with col2:
            if st.form_submit_button("取消"):
                st.session_state[f"editing_{doctor.name}"] = False
                st.rerun()