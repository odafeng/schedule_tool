"""
整合版執行排班頁面 - 三階段排班流程
"""

import streamlit as st
from backend.utils.holiday_manager import get_month_calendar_with_memory
from backend.utils.validation import validate_doctor_data

# 匯入元件
from frontend.components.algorithm_params_component import render_algorithm_parameters
from frontend.components.stage_progress_component import render_stage_progress
from frontend.components.stage1_component import render_stage1
from frontend.components.stage2_component import render_stage2_advanced
from frontend.components.stage3_component import render_stage3


def render():
    """渲染執行排班頁面"""
    st.header("🚀 智慧排班系統 - 三階段執行")

    # 檢查前置條件
    valid, errors = validate_doctor_data(st.session_state.doctors)

    if not valid:
        st.error("請先完成以下設定：")
        for error in errors:
            st.write(f"• {error}")
        return

    # 取得月份資料
    holiday_manager = st.session_state.holiday_manager
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    weekdays, holidays = get_month_calendar_with_memory(year, month, holiday_manager)

    # 初始化 session state
    if "current_stage" not in st.session_state:
        st.session_state.current_stage = 1

    if "stage1_results" not in st.session_state:
        st.session_state.stage1_results = None

    if "selected_solution" not in st.session_state:
        st.session_state.selected_solution = None

    if "stage2_schedule" not in st.session_state:
        st.session_state.stage2_schedule = None
        
    if "stage2_swapper" not in st.session_state:
        st.session_state.stage2_swapper = None

    # 如果還在 Stage 1，顯示參數設定
    if st.session_state.current_stage == 1:
        render_algorithm_parameters()
        st.divider()

    # 顯示當前階段
    render_stage_progress()

    # 根據當前階段顯示不同內容
    if st.session_state.current_stage == 1:
        render_stage1(weekdays, holidays)
    elif st.session_state.current_stage == 2:
        render_stage2_advanced(weekdays, holidays)
    elif st.session_state.current_stage == 3:
        render_stage3(weekdays, holidays)