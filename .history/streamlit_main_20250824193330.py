"""
<<<<<<< HEAD
Streamlit 前端應用程式 - 配合新引擎版本
使用模組化元件架構
"""

import streamlit as st
import os

# 匯入各個元件模組
from ui_config import (
    setup_page_config, 
    inject_custom_css, 
    display_header,
    setup_sidebar_navigation,
    init_session_state,
    get_current_section,
    show_section_header,
    display_readme,
    display_engine_info  # 新增
)
from system_settings import render_system_settings
from doctor_management import render_doctor_management
from schedule_generation import render_schedule_generation
from results_display import render_schedule_results

def initialize_date_settings():
    """初始化日期設定，確保 session_state 中有必要的變數"""
    if 'current_year' not in st.session_state:
        st.session_state.current_year = 2025
    if 'current_month' not in st.session_state:
        st.session_state.current_month = 1
    if 'valid_holidays' not in st.session_state:
        st.session_state.valid_holidays = []
    if 'valid_workdays' not in st.session_state:
        st.session_state.valid_workdays = []
    
    return (
        st.session_state.current_year,
        st.session_state.current_month,
        st.session_state.valid_holidays,
        st.session_state.valid_workdays
    )

def main():
    """主程式入口"""
    # 初始化 session state
    if 'current_section' not in st.session_state:
        st.session_state.current_section = 'schedule'
    if 'show_readme' not in st.session_state:
        st.session_state.show_readme = False
    if 'engine_version' not in st.session_state:
        st.session_state.engine_version = '3.0.0'  # 新引擎版本
        
    # 1. 初始化 UI 設定
    setup_page_config()
    inject_custom_css()
    init_session_state()
    
    # 2. 顯示系統標題
    display_header()
    
    # 3. 初始化日期設定
    year, month, valid_holidays, valid_workdays = initialize_date_settings()
    
    # 4. 設置側邊欄導航
    setup_sidebar_navigation()
    
    # 5. 在側邊欄顯示引擎資訊（新增）
    with st.sidebar:
        st.markdown("---")
        display_engine_info()
    
    # 6. 檢查是否要顯示 README
    if st.session_state.get('show_readme', False):
        display_readme()
        return
    
    # 7. 根據當前區塊顯示內容
    current_section = get_current_section()
    
    if current_section == "doctors":
        show_section_header("醫師管理", "👥", "管理醫師資料、配額與偏好設定")
        render_doctor_management(year, month)
    
    elif current_section == "schedule":
        show_section_header("排班設定", "📅", "設定排班月份與特殊日期")
        year, month, valid_holidays, valid_workdays = render_system_settings()
        st.session_state.current_year = year
        st.session_state.current_month = month
        st.session_state.valid_holidays = valid_holidays
        st.session_state.valid_workdays = valid_workdays
    
    elif current_section == "optimize":
        show_section_header("產生班表", "🚀", "使用統一智慧引擎生成最佳排班")
        render_schedule_generation(year, month, valid_holidays, valid_workdays)
    
    elif current_section == "results":
        show_section_header("結果分析", "📊", "檢視與分析排班結果")
        if st.session_state.get('schedule_results'):
            render_schedule_results(year, month)
        else:
            st.info("📌 請先在「產生班表」頁面生成排班結果")
=======
醫師智慧排班系統 - 主程式入口
"""
import os
import streamlit as st

# 嘗試載入環境變數（如果有安裝 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 如果沒有安裝 python-dotenv，忽略

from frontend.pages import (
    doctor_management,
    calendar_settings,
    schedule_execution,
    schedule_viewer,
    statistics_analysis
)
from frontend.utils.styles import load_custom_css
from frontend.utils.session_manager import SessionManager

def main():
    # 頁面配置
    st.set_page_config(
        page_title="醫師智慧排班系統",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 載入自訂CSS樣式
    load_custom_css()
    
    # 初始化Session State
    SessionManager.initialize()
    
    # 側邊欄設定
    with st.sidebar:
        st.title("⚙️ 系統設定")
        SessionManager.render_sidebar_settings()
    
    # 主頁面標題
    st.title("Intelli-CR｜醫師智慧排班系統")
    st.markdown("v3.0.0 ｜ Designed by Dr. Shih-Feng Huang")
    
    # 主要功能分頁
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "👥 醫師管理", 
        "📅 假日設定", 
        "🚀 執行排班", 
        "📊 當月班表 (功能開發中)", 
        "📈 統計分析 (功能開發中)"
    ])
    
    with tab1:
        doctor_management.render()
    
    with tab2:
        calendar_settings.render()
    
    with tab3:
        schedule_execution.render()
    
    with tab4:
        schedule_viewer.render()
    
    with tab5:
        statistics_analysis.render()
    
    # 頁尾
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>醫師智慧排班系統 v3.0 | 使用束搜索、鏈交換以及智慧通知</p>
        <p>© 2025 Intelli-CR Scheduling System with LINE Integration</p>
    </div>
    """, unsafe_allow_html=True)
>>>>>>> Intelli-CR

if __name__ == "__main__":
    main()