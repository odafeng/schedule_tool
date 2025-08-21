"""
Session狀態管理器
"""
import streamlit as st
import json
import os
from datetime import datetime
from typing import List, Set

from backend.models import Doctor, ScheduleConstraints

class SessionManager:
    """管理Streamlit Session State"""
    
    @staticmethod
    def initialize():
        """初始化Session State"""
        if 'doctors' not in st.session_state:
            st.session_state.doctors = []
            
        if 'holidays' not in st.session_state:
            st.session_state.holidays = set()
            
        if 'workdays' not in st.session_state:
            st.session_state.workdays = set()
            
        if 'schedule_result' not in st.session_state:
            st.session_state.schedule_result = None

        if 'selected_year' not in st.session_state:
            st.session_state.selected_year = datetime.now().year
            
        if 'selected_month' not in st.session_state:
            st.session_state.selected_month = datetime.now().month

        if 'csp_stats' not in st.session_state:
            st.session_state.csp_stats = None

        if 'use_ac3' not in st.session_state:
            st.session_state.use_ac3 = True

        if 'use_backjump' not in st.session_state:
            st.session_state.use_backjump = True

        if 'solution_pool' not in st.session_state:
            st.session_state.solution_pool = None

        if 'last_scheduler' not in st.session_state:
            st.session_state.last_scheduler = None
            
        if 'constraints' not in st.session_state:
            st.session_state.constraints = ScheduleConstraints()
    
    @staticmethod
    def render_sidebar_settings():
        """渲染側邊欄設定"""
        # 月份選擇
        st.subheader("📅 排班月份")
        col1, col2 = st.columns(2)
        with col1:
            year = st.number_input("年份", min_value=2024, max_value=2030, 
                                  value=st.session_state.selected_year)
            st.session_state.selected_year = year
        with col2:
            month = st.selectbox("月份", range(1, 13), 
                               index=st.session_state.selected_month - 1,
                               format_func=lambda x: f"{x}月")
            st.session_state.selected_month = month
        
        st.divider()
        
        # 演算法參數
        st.subheader("🔧 演算法參數")
        constraints = st.session_state.constraints
        
        constraints.max_consecutive_days = st.slider(
            "最大連續值班天數", 1, 5, 
            constraints.max_consecutive_days
        )
        constraints.beam_width = st.slider(
            "束搜索寬度", 3, 10, 
            constraints.beam_width
        )
        constraints.csp_timeout = st.slider(
            "CSP超時(秒)", 5, 30, 
            constraints.csp_timeout
        )
        
        # 進階CSP設定
        with st.expander("🎯 進階CSP設定", expanded=False):
            st.info("""
            **Arc Consistency (AC-3)**
            透過約束傳播提前偵測無解，大幅減少搜索空間
            
            **Conflict-Directed Backjumping**
            智慧回溯機制，直接跳回衝突源頭，避免無謂搜索
            """)
            
            st.session_state.use_ac3 = st.checkbox(
                "啟用 Arc Consistency", 
                value=st.session_state.use_ac3,
                help="使用AC-3演算法進行約束傳播"
            )
            st.session_state.use_backjump = st.checkbox(
                "啟用 Conflict-Directed Backjumping", 
                value=st.session_state.use_backjump,
                help="使用智慧回溯避免無謂搜索"
            )
            
            constraints.neighbor_expansion = st.slider(
                "鄰域展開上限", 5, 20, 
                constraints.neighbor_expansion,
                help="每個變數展開的最大候選數"
            )
        
        st.session_state.constraints = constraints
        st.divider()
        
        # 資料管理
        st.subheader("💾 資料管理")
        
        # 儲存按鈕
        if st.button("💾 儲存所有設定", use_container_width=True):
            SessionManager.save_settings()
            st.success("設定已儲存！")
        
        # 載入按鈕
        if st.button("📂 載入設定", use_container_width=True):
            if SessionManager.load_settings():
                st.success("設定已載入！")
                st.rerun()
            else:
                st.error("找不到儲存的設定檔案")
    
    @staticmethod
    def save_settings():
        """儲存設定到檔案"""
        save_data = {
            'doctors': [d.to_dict() for d in st.session_state.doctors],
            'holidays': list(st.session_state.holidays),
            'workdays': list(st.session_state.workdays),
            'year': st.session_state.selected_year,
            'month': st.session_state.selected_month,
            'use_ac3': st.session_state.get('use_ac3', True),
            'use_backjump': st.session_state.get('use_backjump', True),
            'constraints': {
                'max_consecutive_days': st.session_state.constraints.max_consecutive_days,
                'beam_width': st.session_state.constraints.beam_width,
                'csp_timeout': st.session_state.constraints.csp_timeout,
                'neighbor_expansion': st.session_state.constraints.neighbor_expansion
            }
        }
        
        with open('data/configs/schedule_settings.json', 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def load_settings() -> bool:
        """從檔案載入設定"""
        settings_file = 'data/configs/schedule_settings.json'
        
        if not os.path.exists(settings_file):
            return False
        
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            st.session_state.doctors = [
                Doctor.from_dict(d) for d in save_data['doctors']
            ]
            st.session_state.holidays = set(save_data.get('holidays', []))
            st.session_state.workdays = set(save_data.get('workdays', []))
            st.session_state.selected_year = save_data.get('year', datetime.now().year)
            st.session_state.selected_month = save_data.get('month', datetime.now().month)
            st.session_state.use_ac3 = save_data.get('use_ac3', True)
            st.session_state.use_backjump = save_data.get('use_backjump', True)
            
            if 'constraints' in save_data:
                c = save_data['constraints']
                st.session_state.constraints = ScheduleConstraints(
                    max_consecutive_days=c.get('max_consecutive_days', 2),
                    beam_width=c.get('beam_width', 5),
                    csp_timeout=c.get('csp_timeout', 10),
                    neighbor_expansion=c.get('neighbor_expansion', 10)
                )
            
            return True
        except Exception as e:
            st.error(f"載入設定時發生錯誤: {str(e)}")
            return False