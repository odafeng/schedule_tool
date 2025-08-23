"""
Stage 2 元件（簡化版）
整合所有功能，不再需要 stage2_tabs.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper

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

    # 主要操作區 - 只有三個標籤
    tab1, tab2, tab3 = st.tabs([
        "📅 日曆檢視",
        "🤖 智慧填補", 
        "📈 執行報告"
    ])

    with tab1:
        render_calendar_view_tab(swapper, weekdays, holidays)

    with tab2:
        render_auto_fill_tab(swapper)
        
    with tab3:
        render_execution_report_tab(swapper)

    # 進入 Stage 3 的按鈕
    st.divider()
    
    report = swapper.get_detailed_report()
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 所有空缺已成功填補！")
        if st.button("➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True):
            if 'auto_fill_results' in st.session_state:
                del st.session_state.auto_fill_results
            st.session_state.current_stage = 3
            st.rerun()
    elif report['summary']['unfilled_slots'] <= 2:
        st.warning(f"⚠️ 還有 {report['summary']['unfilled_slots']} 個空缺未填補")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 繼續嘗試", use_container_width=True):
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.rerun()
        with col2:
            if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")


def render_stage2_status(swapper):
    """顯示 Stage 2 系統狀態"""
    report = swapper.get_detailed_report()
    
    # 主要指標
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "填充率", 
            f"{report['summary']['fill_rate']:.1%}",
            delta=f"{report['summary']['filled_slots']}/{report['summary']['total_slots']}"
        )
    
    with col2:
        st.metric(
            "剩餘空缺", 
            report['summary']['unfilled_slots'],
            delta=-len(report['gap_analysis']['easy']) if report['gap_analysis']['easy'] else None
        )
    
    with col3:
        st.metric(
            "已應用交換", 
            report['applied_swaps'],
            help="成功執行的交換鏈數量"
        )
    
    with col4:
        status = "✅ 完成" if report['summary']['unfilled_slots'] == 0 else "🔄 進行中"
        st.metric("狀態", status)


def render_calendar_view_tab(swapper, weekdays: list, holidays: list):
    """日曆檢視標籤頁"""
    st.markdown("### 📅 互動式月曆檢視")
    
    # 使用說明
    with st.expander("📖 使用說明", expanded=False):
        st.info("""
        **互動功能：**
        - 🖱️ 將滑鼠移至空缺格子上，查看可用醫師詳情
        - ✅ **綠色標籤**：可直接安排的醫師（有配額餘額）
        - ⚠️ **橙色標籤**：需要調整才能安排的醫師（例如：配額已滿、連續值班限制）
        - 每個醫師會顯示具體的限制原因
        """)
    
    # 取得詳細的空缺資訊
    gap_details = swapper.get_gap_details_for_calendar()
    
    # 渲染互動式日曆
    from frontend.components.calendar_view import render_calendar_view
    
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    render_calendar_view(
        schedule=swapper.schedule,
        doctors=st.session_state.doctors,
        year=year,
        month=month,
        weekdays=weekdays,
        holidays=holidays,
        gap_details=gap_details
    )
    
    # 顯示統計摘要
    st.divider()
    st.markdown("### 📊 空缺統計摘要")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_gaps = len(swapper.gaps)
    easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
    medium_gaps = len([g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota])
    hard_gaps = len([g for g in swapper.gaps if not g.candidates_with_quota and not g.candidates_over_quota])
    
    with col1:
        st.metric("總空缺數", total_gaps)
    
    with col2:
        st.metric("🟢 可直接填補", easy_gaps, 
                 help="有醫師配額餘額可直接安排")
    
    with col3:
        st.metric("🟡 需要調整", medium_gaps,
                 help="醫師配額已滿，需要交換班次")
    
    with col4:
        st.metric("🔴 困難空缺", hard_gaps,
                 help="沒有可用醫師")
    
    # 快速操作按鈕
    st.divider()
    st.markdown("### ⚡ 快速操作")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 重新分析空缺", use_container_width=True):
            with st.spinner("正在重新分析..."):
                swapper.gaps = swapper._analyze_gaps_advanced()
            st.success("✅ 空缺分析已更新")
            st.rerun()
    
    with col2:
        if easy_gaps > 0:
            if st.button(f"✅ 快速填補 {easy_gaps} 個簡單空缺", 
                        use_container_width=True, type="primary"):
                with st.spinner(f"正在填補 {easy_gaps} 個空缺..."):
                    filled_count = 0
                    for gap in swapper.gaps[:]:
                        if gap.candidates_with_quota:
                            best_doctor = swapper._select_best_candidate(
                                gap.candidates_with_quota, gap
                            )
                            if swapper._apply_direct_fill(gap, best_doctor):
                                filled_count += 1
                    
                    st.success(f"✅ 已成功填補 {filled_count} 個空缺")
                    st.session_state.stage2_schedule = swapper.schedule
                    st.rerun()