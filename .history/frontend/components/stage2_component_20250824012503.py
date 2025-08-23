"""
Stage 2 元件（極簡版）
避免所有 state 和回調問題
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper


def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染新的 Stage 2: 進階智慧交換補洞系統"""
    st.subheader("🔧 Stage 2: 進階智慧交換補洞系統")

    # 檢查前置條件
    if 'stage2_schedule' not in st.session_state or not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 1")
        return

    # 初始化 swapper（每次都重新創建，避免 state 問題）
    try:
        swapper = Stage2AdvancedSwapper(
            schedule=st.session_state.stage2_schedule,
            doctors=st.session_state.doctors,
            constraints=st.session_state.constraints,
            weekdays=weekdays,
            holidays=holidays,
        )
        # 關閉日誌回調，避免問題
        swapper.log_callback = None
    except Exception as e:
        st.error(f"初始化失敗: {str(e)}")
        return

    # 顯示系統狀態
    try:
        report = swapper.get_detailed_report()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("填充率", f"{report['summary']['fill_rate']:.1%}")
        with col2:
            st.metric("剩餘空缺", report['summary']['unfilled_slots'])
        with col3:
            st.metric("已填格位", report['summary']['filled_slots'])
        with col4:
            st.metric("總格位", report['summary']['total_slots'])
    except:
        st.warning("無法顯示狀態")

    # 主要操作區
    tab1, tab2, tab3 = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📈 執行報告"])

    with tab1:
        render_calendar_simple(swapper, weekdays, holidays)

    with tab2:
        render_auto_fill_simple(swapper, weekdays, holidays)
        
    with tab3:
        render_report_simple(swapper)

    # 進入 Stage 3 的按鈕
    st.divider()
    
    try:
        report = swapper.get_detailed_report()
        unfilled = report['summary']['unfilled_slots']
        
        if unfilled == 0:
            st.success("🎉 所有空缺已成功填補！")
            if st.button("➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
        elif unfilled <= 2:
            st.warning(f"⚠️ 還有 {unfilled} 個空缺未填補")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 繼續嘗試", use_container_width=True):
                    st.rerun()
            with col2:
                if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                    st.session_state.current_stage = 3
                    st.rerun()
        else:
            st.error(f"❌ 還有 {unfilled} 個空缺需要處理")
    except:
        pass


def render_calendar_simple(swapper, weekdays, holidays):
    """簡單的日曆檢視"""
    st.markdown("### 📅 月曆檢視")
    
    try:
        # 簡單顯示空缺統計
        total_gaps = len(swapper.gaps)
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium_gaps = len([g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota])
        hard_gaps = len([g for g in swapper.gaps if not g.candidates_with_quota and not g.candidates_over_quota])
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總空缺數", total_gaps)
        with col2:
            st.metric("🟢 可直接填補", easy_gaps)
        with col3:
            st.metric("🟡 需要調整", medium_gaps)
        with col4:
            st.metric("🔴 困難空缺", hard_gaps)
        
        # 顯示空缺列表
        if swapper.gaps:
            st.markdown("#### 空缺列表")
            gap_data = []
            for gap in swapper.gaps[:10]:  # 只顯示前10個
                gap_data.append({
                    "日期": gap.date,
                    "角色": gap.role,
                    "類型": "假日" if gap.is_holiday else "平日",
                    "可用醫師": len(gap.candidates_with_quota),
                    "需調整醫師": len(gap.candidates_over_quota)
                })
            df = pd.DataFrame(gap_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            if len(swapper.gaps) > 10:
                st.info(f"還有 {len(swapper.gaps) - 10} 個空缺未顯示")
    except Exception as e:
        st.error(f"無法顯示日曆: {str(e)}")

    # 快速填補按鈕
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 重新分析空缺", use_container_width=True):
            st.rerun()
    
    with col2:
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        if easy_gaps > 0:
            if st.button(f"✅ 快速填補 {easy_gaps} 個簡單空缺", use_container_width=True, type="primary"):
                with st.spinner(f"正在填補..."):
                    filled = 0
                    for gap in swapper.gaps[:]:
                        if gap.candidates_with_quota:
                            best = gap.candidates_with_quota[0]
                            if gap.role == "主治":
                                swapper.schedule[gap.date].attending = best
                            else:
                                swapper.schedule[gap.date].resident = best
                            filled += 1
                    
                    st.session_state.stage2_schedule = swapper.schedule
                    st.success(f"✅ 已填補 {filled} 個空缺")
                    time.sleep(1)
                    st.rerun()


def render_auto_fill_simple(swapper, weekdays, holidays):
    """簡單的自動填補介面"""
    st.markdown("### 🤖 智慧自動填補")
    
    # 顯示當前狀態
    report = swapper.get_detailed_report()
    
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 所有空缺都已填補完成！")
        return
    
    # 空缺概況
    st.markdown("#### 📊 空缺概況")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總空缺", report['summary']['unfilled_slots'])
    with col2:
        st.metric("🟢 簡單", len(report['gap_analysis']['easy']))
    with col3:
        st.metric("🟡 中等", len(report['gap_analysis']['medium']))
    with col4:
        st.metric("🔴 困難", len(report['gap_analysis']['hard']))
    
    st.divider()
    
    # 執行按鈕
    st.markdown("#### 🚀 執行填補")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 簡單填補
        if st.button("📦 執行簡單填補", use_container_width=True):
            with st.spinner("執行中..."):
                filled = 0
                for gap in swapper.gaps[:]:
                    if gap.candidates_with_quota:
                        best = gap.candidates_with_quota[0]
                        if gap.role == "主治":
                            swapper.schedule[gap.date].attending = best
                        else:
                            swapper.schedule[gap.date].resident = best
                        filled += 1
                
                st.session_state.stage2_schedule = swapper.schedule
                st.success(f"✅ 已填補 {filled} 個簡單空缺")
                time.sleep(1)
                st.rerun()
    
    with col2:
        # 完整自動填補（簡化版）
        if st.button("🎯 執行完整自動填補", type="primary", use_container_width=True):
            execute_simple_auto_fill(swapper)


def execute_simple_auto_fill(swapper):
    """執行簡化版自動填補"""
    
    # 關閉所有日誌
    swapper.log_callback = None
    
    with st.spinner("🔄 正在執行智慧填補...這可能需要幾分鐘"):
        try:
            start_time = time.time()
            
            # 執行自動填補（限制回溯次數以加快速度）
            results = swapper.run_auto_fill_with_backtracking(max_backtracks=1000)
            
            elapsed = time.time() - start_time
            
            # 更新 session state
            st.session_state.stage2_schedule = swapper.schedule
            
            # 顯示結果
            st.success(f"✅ 執行完成！耗時 {elapsed:.1f} 秒")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("直接填補", len(results.get('direct_fills', [])))
            with col2:
                st.metric("交換解決", len(results.get('swap_chains', [])))
            with col3:
                st.metric("剩餘空缺", len(results.get('remaining_gaps', [])))
            
            # 顯示剩餘空缺
            if results.get('remaining_gaps'):
                with st.expander("剩餘空缺詳情"):
                    for gap in results['remaining_gaps'][:10]:
                        st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")
            
            # 延遲後重新載入
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.error(f"執行失敗: {str(e)}")


def render_report_simple(swapper):
    """簡單的報告頁面"""
    st.markdown("### 📈 執行報告")
    
    try:
        report = swapper.get_detailed_report()
        
        # 總體統計
        st.markdown("#### 📊 總體統計")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("總格位", report['summary']['total_slots'])
        with col2:
            st.metric("已填格位", report['summary']['filled_slots'])
        with col3:
            st.metric("填充率", f"{report['summary']['fill_rate']:.1%}")
        with col4:
            st.metric("未填格位", report['summary']['unfilled_slots'])
        
        # 下載報告
        st.divider()
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button(
            label="💾 下載報告 JSON",
            data=report_json,
            file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
        
    except Exception as e:
        st.error(f"無法生成報告: {str(e)}")