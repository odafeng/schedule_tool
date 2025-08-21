"""
醫師智慧排班系統 - 主程式入口
"""
import streamlit as st
from frontend.pages import (
    doctor_management,
    calendar_settings,
    schedule_execution,
    schedule_viewer,
    statistics_analysis,
    ml_analytics
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
    st.markdown("支援主治醫師與總醫師的自動排班，使用束搜索、CSP演算法、機器學習等技術。")
    
    # 主要功能分頁
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "👥 醫師管理", 
        "📅 假日設定", 
        "🚀 執行排班", 
        "📊 結果檢視", 
        "📈 統計分析", 
        "🤖 ML訓練資料"
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
    
    with tab6:
        ml_analytics.render()
    
    # 頁尾
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>醫師智慧排班系統 v2.0 | 使用束搜索、CSP與機器學習</p>
        <p>© 2024 Hospital Scheduling System with ML</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()