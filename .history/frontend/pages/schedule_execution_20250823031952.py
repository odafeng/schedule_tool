"""
整合版執行排班頁面 - 三階段排班流程（配合新 Stage 2）
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import copy

from backend.algorithms.stage1_greedy_beam import Stage1Scheduler, SchedulingState
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
from backend.algorithms.stage3_publish import Stage3Publisher
from backend.utils.holiday_manager import get_month_calendar_with_memory
from backend.utils.validation import validate_doctor_data
from backend.models import ScheduleConstraints


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


def render_algorithm_parameters():
    """渲染演算法參數設定區域"""
    st.subheader("⚙️ 演算法參數設定")

    # 取得或初始化 constraints
    if "constraints" not in st.session_state:
        st.session_state.constraints = ScheduleConstraints()

    constraints = st.session_state.constraints

    # 基本參數設定
    with st.expander("🔧 基本參數", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            constraints.max_consecutive_days = st.slider(
                "最大連續值班天數",
                min_value=1,
                max_value=5,
                value=constraints.max_consecutive_days,
                help="醫師最多可連續值班的天數限制",
            )

        with col2:
            constraints.beam_width = st.slider(
                "束搜索寬度",
                min_value=3,
                max_value=10,
                value=constraints.beam_width,
                help="Beam Search 保留的候選解數量，越大越精確但越慢",
            )

        with col3:
            constraints.csp_timeout = st.slider(
                "CSP超時(秒)",
                min_value=5,
                max_value=30,
                value=constraints.csp_timeout,
                help="CSP求解器的最大執行時間",
            )

    # 儲存更新的 constraints
    st.session_state.constraints = constraints

    # 顯示當前設定摘要
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("連續值班限制", f"{constraints.max_consecutive_days} 天")

    with col2:
        st.metric("束寬度", constraints.beam_width)

    with col3:
        st.metric("CSP超時", f"{constraints.csp_timeout} 秒")


def render_stage_progress():
    """顯示階段進度"""
    stages = ["Stage 1: 快速排班", "Stage 2: 智慧補洞", "Stage 3: 確認發佈"]
    current = st.session_state.current_stage - 1

    # 使用進度條顯示
    progress = (current + 1) / 3
    st.progress(progress)

    # 顯示階段標籤
    cols = st.columns(3)
    for i, (col, stage) in enumerate(zip(cols, stages)):
        with col:
            if i < current:
                st.success(f"✅ {stage}")
            elif i == current:
                st.info(f"🔄 {stage}")
            else:
                st.text(f"⏳ {stage}")


def render_stage1(weekdays: list, holidays: list):
    """渲染 Stage 1: Greedy + Beam Search"""
    st.subheader("📋 Stage 1: Greedy + Beam Search 快速排班")

    st.info(
        """
    **階段目標**：使用 Greedy 初始化 + Beam Search 優化，快速填充 70-95% 的排班格位。
    
    **策略**：
    - 假日優先排班（約束更緊）
    - 稀缺醫師優先安排
    - 保證不違反硬約束
    """
    )

    # 顯示預估資訊（使用當前參數）
    constraints = st.session_state.constraints
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("束搜索寬度", constraints.beam_width)

    with col2:
        st.metric("預計填充率", "85-95%")

    with col3:
        estimated_time = len(weekdays + holidays) * 0.1 * (constraints.beam_width / 5)
        st.metric("預計時間", f"{estimated_time:.0f} 秒")

    # 檢查是否已有結果
    if st.session_state.stage1_results is not None:
        # 已有結果，直接顯示
        results = st.session_state.stage1_results
        st.success(f"✅ Stage 1 已完成，生成了 {len(results)} 個候選方案")
        
        # 顯示結果表格
        display_stage1_results(results)
        
        # 提供重新執行的選項
        if st.button("🔄 重新執行 Stage 1", use_container_width=True):
            st.session_state.stage1_results = None
            st.rerun()
    else:
        # 沒有結果，顯示執行按鈕
        if st.button("🚀 開始 Stage 1 排班", type="primary", use_container_width=True):
            execute_stage1(weekdays, holidays, constraints.beam_width)
            st.rerun()


def display_stage1_results(results):
    """顯示 Stage 1 結果"""
    # 顯示每個方案
    st.subheader("📊 候選方案比較")

    comparison_data = []
    for i, state in enumerate(results):
        comparison_data.append(
            {
                "方案": f"方案 {i+1}",
                "分數": f"{state.score:.0f}",
                "填充率": f"{state.fill_rate:.1%}",
                "已填格數": state.filled_count,
                "未填格數": len(state.unfilled_slots),
            }
        )

    df = pd.DataFrame(comparison_data)
    st.dataframe(df, use_container_width=True)

    # 選擇方案
    st.subheader("🎯 選擇方案進入 Stage 2")
    
    # 保存選擇的索引到 session state
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0

    selected_index = st.radio(
        "選擇一個方案繼續：",
        range(len(results)),
        index=st.session_state.selected_index,
        format_func=lambda x: f"方案 {x+1} (分數: {results[x].score:.0f}, 填充率: {results[x].fill_rate:.1%})",
        key="solution_radio",
    )
    
    # 更新選擇的索引
    st.session_state.selected_index = selected_index

    col1, col2 = st.columns(2)

    with col1:
        if st.button("👁️ 預覽選中方案", key="preview_solution"):
            # 使用 expander 直接顯示，避免重新載入
            preview_schedule_inline(results[selected_index].schedule)

    with col2:
        if st.button("✅ 採用並進入 Stage 2", type="primary", key="adopt_solution"):
            st.session_state.selected_solution = results[selected_index]
            st.session_state.stage2_schedule = copy.deepcopy(
                results[selected_index].schedule
            )
            st.session_state.current_stage = 2
            st.rerun()


def execute_stage1(weekdays: list, holidays: list, beam_width: int):
    """執行 Stage 1"""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress):
        progress_bar.progress(progress)
        status_text.text(f"Stage 1 進度：{int(progress * 100)}%")

    # 執行 Stage 1
    scheduler = Stage1Scheduler(
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays,
    )

    with st.spinner("正在執行 Greedy + Beam Search..."):
        results = scheduler.run(
            beam_width=beam_width, progress_callback=update_progress
        )

    progress_bar.progress(1.0)
    status_text.text("Stage 1 完成！")

    # 儲存結果到 session state
    st.session_state.stage1_results = results
    
    # 顯示成功訊息
    st.success(f"✅ Stage 1 完成，生成了 {len(results)} 個候選方案")


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
            st.session_state.current_stage = 3
            st.rerun()
    elif report['summary']['unfilled_slots'] <= 2:
        st.warning(f"⚠️ 還有 {report['summary']['unfilled_slots']} 個空缺未填補")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 繼續嘗試", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")


def render_stage2_status(swapper: Stage2AdvancedSwapper):
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
    
    # 空缺分類摘要
    with st.expander("📊 空缺分類摘要", expanded=False):
        gap_col1, gap_col2, gap_col3 = st.columns(3)
        
        with gap_col1:
            st.info(f"""
            **🟢 簡單空缺**
            - 數量：{len(report['gap_analysis']['easy'])}
            - 特徵：有醫師可直接填補
            """)
        
        with gap_col2:
            st.warning(f"""
            **🟡 中等空缺**
            - 數量：{len(report['gap_analysis']['medium'])}
            - 特徵：需要交換才能填補
            """)
        
        with gap_col3:
            st.error(f"""
            **🔴 困難空缺**
            - 數量：{len(report['gap_analysis']['hard'])}
            - 特徵：無可用醫師
            """)
    
    # 搜索統計（如果有的話）
    if 'search_stats' in report and report['search_stats']['chains_explored'] > 0:
        with st.expander("🔍 搜索統計", expanded=False):
            stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
            
            with stats_col1:
                st.metric("探索路徑", report['search_stats']['chains_explored'])
            
            with stats_col2:
                st.metric("找到方案", report['search_stats']['chains_found'])
            
            with stats_col3:
                st.metric("搜索時間", f"{report['search_stats']['search_time']:.1f}秒")
            
            with stats_col4:
                st.metric("最大深度", report['search_stats']['max_depth_reached'])


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
        
        **快速操作：**
        - 使用下方按鈕可快速填補所有簡單空缺
        - 點擊「重新分析」更新空缺資訊
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
                    # 更新 session state
                    st.session_state.stage2_schedule = swapper.schedule
                    st.rerun()
    
    with col3:
        if st.button("💾 匯出當前狀態", use_container_width=True):
            import json
            
            export_data = {
                "timestamp": datetime.now().isoformat(),
                "year": year,
                "month": month,
                "schedule": {
                    date: {
                        "attending": slot.attending,
                        "resident": slot.resident
                    }
                    for date, slot in swapper.schedule.items()
                },
                "statistics": {
                    "total_gaps": total_gaps,
                    "easy_gaps": easy_gaps,
                    "medium_gaps": medium_gaps,
                    "hard_gaps": hard_gaps,
                    "fill_rate": swapper.get_detailed_report()['summary']['fill_rate']
                }
            }
            
            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 下載 JSON",
                data=json_str,
                file_name=f"schedule_stage2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )


def render_auto_fill_tab(swapper: Stage2AdvancedSwapper):
    """自動填補標籤頁"""
    st.markdown("### 🤖 智慧自動填補系統")
    
    st.info("""
    **深度搜索引擎 v2.0**
    
    系統將自動執行以下步驟：
    1. **直接填補**：使用有配額餘額的醫師填補簡單空缺
    2. **深度搜索**：探索多達 3-5 步的複雜交換鏈
    3. **激進策略**：當標準方法無效時，嘗試跨類型交換
    4. **智能回溯**：檢測死路並自動調整策略
    
    搜索時間最長可達 2 分鐘，以確保找到最佳解決方案。
    """)
    
    # 顯示當前空缺狀況
    report = swapper.get_detailed_report()
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return
    
    st.warning(f"📍 當前有 **{report['summary']['unfilled_slots']}** 個空缺需要處理")
    
    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
        # 創建一個容器來顯示執行日誌
        log_container = st.container()
        
        with log_container:
            # 自動設定最佳參數
            max_backtracks = 10  # 固定使用 10 次回溯
            
            # 執行自動填補
            results = swapper.run_auto_fill_with_backtracking(max_backtracks)
            
            # 更新 schedule
            st.session_state.stage2_schedule = swapper.schedule
            
            # 顯示執行結果
            if results['remaining_gaps']:
                st.warning(f"""
                ⚠️ **執行完成（部分成功）**
                - ✅ 直接填補：{len(results['direct_fills'])} 個
                - 🔄 交換解決：{len(results['swap_chains'])} 個
                - ↩️ 回溯次數：{len(results['backtracks'])}
                - ❌ 剩餘空缺：{len(results['remaining_gaps'])} 個
                """)
                
                # 顯示剩餘空缺詳情
                with st.expander("❌ 無法解決的空缺", expanded=True):
                    for gap in results['remaining_gaps']:
                        st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")
                
                st.info("💡 建議：可以嘗試「交換鏈探索」手動處理剩餘空缺，或調整醫師配額後重試")
            else:
                st.success(f"""
                ✅ **完美執行！所有空缺已填補**
                - 直接填補：{len(results['direct_fills'])} 個
                - 交換解決：{len(results['swap_chains'])} 個
                - 回溯次數：{len(results['backtracks'])}
                """)
            
            # 顯示交換鏈詳情（如果有）
            if results['swap_chains']:
                with st.expander(f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)", expanded=False):
                    for i, swap_info in enumerate(results['swap_chains']):
                        st.write(f"**交換 {i+1}**: {swap_info['gap']}")
                        for step in swap_info['chain']:
                            st.write(f"  - {step}")
            
            st.rerun()


def render_gap_analysis_tab(swapper: Stage2AdvancedSwapper):
    """空缺分析標籤頁"""
    st.markdown("### 📊 空缺詳細分析")
    
    if not swapper.gaps:
        st.success("🎉 所有空缺已填補完成！")
        return
    
    # 顯示前 20 個空缺
    gaps_to_show = swapper.gaps[:20]
    
    # 創建表格資料
    gap_data = []
    for gap in gaps_to_show:
        gap_data.append({
            "日期": gap.date,
            "角色": gap.role,
            "類型": "假日" if gap.is_holiday else "平日",
            "優先級": f"{gap.priority_score:.1f}",
            "可直接安排": len(gap.candidates_with_quota),
            "需調整安排": len(gap.candidates_over_quota),
            "機會成本": f"{gap.opportunity_cost:.1f}",
            "未來影響": f"{gap.future_impact_score:.1f}"
        })
    
    df = pd.DataFrame(gap_data)
    
    # 使用顏色標記
    def color_priority(val):
        if float(val) > 70:
            return 'background-color: #ffcdd2'  # 紅色
        elif float(val) > 40:
            return 'background-color: #fff9c4'  # 黃色
        else:
            return 'background-color: #c8e6c9'  # 綠色
    
    styled_df = df.style.applymap(color_priority, subset=['優先級'])
    st.dataframe(styled_df, use_container_width=True)
    
    # 詳細檢視
    st.markdown("### 🔍 空缺詳細檢視")
    
    selected_gap_idx = st.selectbox(
        "選擇要檢視的空缺",
        range(len(gaps_to_show)),
        format_func=lambda x: f"{gaps_to_show[x].date} {gaps_to_show[x].role} (優先級: {gaps_to_show[x].priority_score:.1f})"
    )
    
    if selected_gap_idx is not None:
        gap = gaps_to_show[selected_gap_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"""
            **基本資訊**
            - 日期：{gap.date}
            - 角色：{gap.role}
            - 假日：{'是' if gap.is_holiday else '否'}
            - 週末：{'是' if gap.is_weekend else '否'}
            """)
            
            st.success(f"""
            **可直接安排醫師**
            {', '.join(gap.candidates_with_quota) if gap.candidates_with_quota else '無'}
            """)
        
        with col2:
            st.warning(f"""
            **評分指標**
            - 嚴重度：{gap.severity:.1f}
            - 機會成本：{gap.opportunity_cost:.1f}
            - 未來影響：{gap.future_impact_score:.1f}
            - 唯一性：{gap.uniqueness_score:.1f}
            - 綜合優先級：{gap.priority_score:.1f}
            """)
            
            st.warning(f"""
            **需調整安排醫師**
            {', '.join(gap.candidates_over_quota) if gap.candidates_over_quota else '無'}
            """)


def render_swap_exploration_tab(swapper: Stage2AdvancedSwapper):
    """交換鏈探索標籤頁"""
    st.markdown("### 🔄 交換鏈探索")
    
    # 選擇目標空缺
    gaps_with_a = [g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota]
    
    if not gaps_with_a:
        st.info("沒有需要交換的空缺")
        return
    
    selected_gap_idx = st.selectbox(
        "選擇要探索交換鏈的空缺",
        range(len(gaps_with_a)),
        format_func=lambda x: f"{gaps_with_a[x].date} {gaps_with_a[x].role}"
    )
    
    if selected_gap_idx is not None:
        gap = gaps_with_a[selected_gap_idx]
        
        # 搜索深度設定
        max_depth = st.slider("搜索深度", 1, 5, 3, 
                             help="建議使用 3-4，深度越大找到解的機會越高，但搜索時間越長")
        
        if st.button("🔍 開始深度搜索", use_container_width=True):
            # 創建容器顯示搜索進度
            search_container = st.container()
            
            with search_container:
                # 執行搜索
                chains = swapper.find_multi_step_swap_chains(gap, max_depth)
                
                if chains:
                    st.success(f"✅ 搜索完成！找到 {len(chains)} 個可行交換鏈")
                    
                    # 顯示前 5 個方案
                    for i, chain in enumerate(chains[:5]):
                        complexity_badge = "🟢 簡單" if chain.complexity <= 2 else "🟡 中等" if chain.complexity <= 3 else "🔴 複雜"
                        
                        with st.expander(f"方案 {i+1} | 分數: {chain.total_score:.1f} | {complexity_badge} ({chain.complexity} 步)"):
                            for j, step in enumerate(chain.steps):
                                if j == 0:
                                    st.success(f"步驟 {j+1}: {step.description}")
                                else:
                                    st.info(f"步驟 {j+1}: {step.description}")
                            
                            st.write(f"**驗證訊息**: {chain.validation_message}")
                            
                            # 應用按鈕
                            if st.button(f"✅ 應用此方案", key=f"apply_chain_{i}"):
                                if swapper.apply_swap_chain(chain):
                                    st.success("✅ 交換鏈應用成功！")
                                    st.session_state.stage2_schedule = swapper.schedule
                                    st.rerun()
                                else:
                                    st.error("❌ 交換鏈應用失敗")
                else:
                    st.warning("""
                    ⚠️ 未找到可行的交換鏈
                    
                    **可能的原因：**
                    - 所有候選醫師都已達到配額上限
                    - 沒有可以安全移動的班次
                    - 約束條件過於嚴格
                    
                    **建議：**
                    - 嘗試增加搜索深度
                    - 考慮調整醫師配額
                    - 檢查是否有過多的不可值班日限制
                    """)


def render_execution_report_tab(swapper: Stage2AdvancedSwapper):
    """執行報告標籤頁"""
    st.markdown("### 📈 執行報告")
    
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
        st.metric("狀態歷史", report['state_history'])
    
    # 優化指標
    st.markdown("#### 🎯 優化指標")
    metrics = report['optimization_metrics']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("平均優先級", f"{metrics['average_priority']:.1f}")
    with col2:
        st.metric("最大機會成本", f"{metrics['max_opportunity_cost']:.1f}")
    with col3:
        st.metric("總未來影響", f"{metrics['total_future_impact']:.1f}")
    
    # 搜索統計（如果有）
    if 'search_stats' in report and report['search_stats']['chains_explored'] > 0:
        st.markdown("#### 🔍 搜索統計")
        stats = report['search_stats']
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("探索路徑", f"{stats['chains_explored']:,}")
        with col2:
            st.metric("找到方案", stats['chains_found'])
        with col3:
            st.metric("搜索時間", f"{stats['search_time']:.2f} 秒")
        with col4:
            st.metric("最大深度", f"{stats['max_depth_reached']} 層")
    
    # 關鍵空缺列表
    if report['gap_analysis']['critical']:
        st.markdown("#### ⚠️ 關鍵空缺 (Top 5)")
        critical_df = pd.DataFrame(report['gap_analysis']['critical'])
        st.dataframe(critical_df, use_container_width=True)
    
    # 約束違規檢查
    violations = swapper.validate_all_constraints()
    if violations:
        st.markdown("#### ❌ 約束違規")
        for violation in violations:
            st.error(violation)
    else:
        st.success("✅ 所有約束條件均已滿足")
    
    # 下載報告
    st.divider()
    if st.button("📥 下載詳細報告", use_container_width=True):
        import json
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button(
            label="💾 下載 JSON 報告",
            data=report_json,
            file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )


def preview_schedule_inline(schedule: dict):
    """內嵌預覽排班表（避免頁面重載）"""
    with st.container():
        st.markdown("### 📅 排班預覽")
        
        data = []
        for date_str in sorted(schedule.keys()):
            slot = schedule[date_str]
            data.append({
                '日期': date_str,
                '主治醫師': slot.attending or '(空)',
                '總醫師': slot.resident or '(空)'
            })
        
        df = pd.DataFrame(data)
        
        # 添加統計信息
        filled_attending = len([d for d in data if d['主治醫師'] != '(空)'])
        filled_resident = len([d for d in data if d['總醫師'] != '(空)'])
        total = len(data)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("主治醫師填充", f"{filled_attending}/{total}")
        with col2:
            st.metric("總醫師填充", f"{filled_resident}/{total}")
        with col3:
            st.metric("總填充率", f"{(filled_attending + filled_resident)/(total*2):.1%}")
        
        # 使用 container 來顯示表格，避免 expander 的問題
        st.dataframe(df, use_container_width=True, height=400)


def render_stage3(weekdays: list, holidays: list):
    """渲染 Stage 3: 確認與發佈"""
    st.subheader("📤 Stage 3: 確認與發佈")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 2")
        return

    # 初始化發佈器
    publisher = Stage3Publisher(
        schedule=st.session_state.stage2_schedule,
        doctors=st.session_state.doctors,
        weekdays=weekdays,
        holidays=holidays,
    )

    # 顯示品質報告
    report = publisher.quality_report

    # 接受度等級
    acceptance_colors = {
        "Ideal": "success",
        "Acceptable": "warning",
        "Needs discussion": "error",
    }

    st.markdown(f"### 📊 排班品質評估")

    col1, col2, col3 = st.columns(3)

    with col1:
        color = acceptance_colors.get(report.acceptance_level, "info")
        if color == "success":
            st.success(f"⭐ 接受度：{report.acceptance_level}")
        elif color == "warning":
            st.warning(f"⭐ 接受度：{report.acceptance_level}")
        else:
            st.error(f"⭐ 接受度：{report.acceptance_level}")

    with col2:
        st.metric("填充率", f"{report.fill_rate:.1%}")

    with col3:
        st.metric("總問題數", report.total_issues)

    # 顯示問題清單
    if report.critical_issues or report.minor_issues:
        st.markdown("### ⚠️ 問題清單")

        if report.critical_issues:
            with st.expander(
                f"🔴 重要問題 ({len(report.critical_issues)})", expanded=True
            ):
                for issue in report.critical_issues:
                    st.error(f"• {issue}")

        if report.minor_issues:
            with st.expander(
                f"🟡 次要問題 ({len(report.minor_issues)})", expanded=False
            ):
                for issue in report.minor_issues:
                    st.warning(f"• {issue}")

    # 預覽排班表
    st.markdown("### 📋 排班表預覽")
    df = publisher.export_to_dataframe()
    st.dataframe(df, use_container_width=True)

    # 統計資訊
    with st.expander("📊 詳細統計", expanded=False):
        stats_df = publisher._create_statistics_df()
        st.dataframe(stats_df, use_container_width=True)

    # 匯出選項
    st.markdown("### 📥 匯出與發佈")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 匯出 Excel", use_container_width=True):
            filename = publisher.export_to_excel()
            with open(filename, "rb") as f:
                st.download_button(
                    label="💾 下載 Excel",
                    data=f,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            st.success(f"✅ 已生成 Excel 檔案")

    with col2:
        if st.button("📄 匯出 PDF", use_container_width=True):
            st.info("PDF 匯出功能開發中...")

    with col3:
        if st.button("📤 發佈到 LINE", use_container_width=True):
            message = publisher.generate_summary_message()
            st.text_area("LINE 訊息預覽：", message, height=200)
            st.info("LINE 推播功能需要設定 LINE Notify Token")

    # 完成選項
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 返回 Stage 2 修改", use_container_width=True):
            st.session_state.current_stage = 2
            st.rerun()

    with col2:
        if st.button("✅ 確認並結束", type="primary", use_container_width=True):
            st.success("🎉 排班流程完成！")
            st.balloons()
            # 清除狀態，準備下次排班
            st.session_state.current_stage = 1
            st.session_state.stage1_results = None
            st.session_state.selected_solution = None
            st.session_state.stage2_schedule = None
            st.session_state.stage2_swapper = None