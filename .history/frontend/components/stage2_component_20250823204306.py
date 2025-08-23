"""Stage 2 元件"""

import streamlit as st
import pandas as pd
from datetime import datetime
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
from frontend.components.stage2_tabs import (
    render_stage2_status,
    render_calendar_view_tab,
    render_auto_fill_tab,
    render_gap_analysis_tab,
    render_swap_exploration_tab,
    render_execution_report_tab
)

def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染新的 Stage 2: 進階智慧交換補洞系統"""
    st.subheader("🔧 Stage 2: 進階智慧交換補洞系統")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 1")
        return

    # 初始化或取得 Stage 2 系統
    if st.session_state.stage2_swapper is None:
        with st.spinner("正在初始化 Stage 2 系統..."):
            st.session_state.stage2_swapper = Stage2AdvancedSwapper(
                schedule=st.session_state.stage2_schedule,
                doctors=st.session_state.doctors,
                constraints=st.session_state.constraints,
                weekdays=weekdays,
                holidays=holidays,
            )
            # 清除自動填補結果（新的 swapper 實例）
            if 'auto_fill_results' in st.session_state:
                del st.session_state.auto_fill_results
    
    swapper = st.session_state.stage2_swapper

    # 顯示系統狀態
    render_stage2_status(swapper)

    # 主要操作區
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 日曆檢視",
        "🤖 自動填補", 
        "📊 空缺分析", 
        "🔄 交換鏈探索",
        "📈 執行報告"
    ])

    # 當切換標籤時，我們不清除結果，讓使用者可以在不同標籤間查看

    with tab1:
        render_calendar_view_tab(swapper, weekdays, holidays)

    with tab2:
        render_auto_fill_tab(swapper)

    with tab3:
        render_gap_analysis_tab(swapper)

    with tab4:
        render_swap_exploration_tab(swapper)
        
    with tab5:
        render_execution_report_tab(swapper)

    # 進入 Stage 3 的按鈕
    st.divider()
    
    report = swapper.get_detailed_report()
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 所有空缺已成功填補！")
        if st.button("➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True):
            # 清除自動填補結果
            if 'auto_fill_results' in st.session_state:
                del st.session_state.auto_fill_results
            st.session_state.current_stage = 3
            st.rerun()
    elif report['summary']['unfilled_slots'] <= 2:
        st.warning(f"⚠️ 還有 {report['summary']['unfilled_slots']} 個空缺未填補")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 繼續嘗試", use_container_width=True):
                # 清除自動填補結果，讓使用者可以重新執行
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.rerun()
        with col2:
            if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                # 清除自動填補結果
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")