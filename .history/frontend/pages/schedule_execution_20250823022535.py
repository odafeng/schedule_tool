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
        render_stage2_advanced(weekdays, holidays)  # 使用新的 Stage 2
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

    # 進階設定（針對新 Stage 2）
    with st.expander("🎯 Stage 2 進階設定", expanded=False):
        st.info(
            """
            **智慧交換系統設定**
            - 前瞻性評估：預測填補決策對未來的影響
            - 多步交換鏈：支援複雜的多步驟交換
            - 回溯機制：自動從錯誤決策中恢復
            """
        )

        col1, col2 = st.columns(2)

        with col1:
            st.session_state.max_backtracks = st.slider(
                "最大回溯次數",
                min_value=1,
                max_value=10,
                value=st.session_state.get("max_backtracks", 5),
                help="檢測到死路時的最大回溯次數"
            )

        with col2:
            st.session_state.max_swap_depth = st.slider(
                "交換鏈最大深度",
                min_value=1,
                max_value=5,
                value=st.session_state.get("max_swap_depth", 3),
                help="多步交換的最大步數"
            )

    # 儲存更新的 constraints
    st.session_state.constraints = constraints

    # 顯示當前設定摘要
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("連續值班限制", f"{constraints.max_consecutive_days} 天")

    with col2:
        st.metric("束寬度", constraints.beam_width)

    with col3:
        st.metric("最大回溯", st.session_state.get("max_backtracks", 5))

    with col4:
        st.metric("交換深度", st.session_state.get("max_swap_depth", 3))


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

    # 主要操作區 - 新增日曆視圖tab
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 日曆檢視",  # 新增的tab
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
            - 特徵：有B類醫師可直接填補
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


def render_auto_fill_tab(swapper: Stage2AdvancedSwapper):
    """自動填補標籤頁"""
    st.markdown("### 🤖 智慧自動填補系統")
    
    st.info("""
    系統將自動執行以下步驟：
    1. **直接填補**：使用有配額餘額的醫師（B類）
    2. **智慧交換**：透過交換鏈使用超額醫師（A類）
    3. **回溯優化**：檢測死路並自動調整策略
    """)
    
    # 參數設定
    col1, col2 = st.columns(2)
    
    with col1:
        max_backtracks = st.number_input(
            "最大回溯次數",
            min_value=1,
            max_value=10,
            value=st.session_state.get("max_backtracks", 5),
            help="當遇到無解時的最大重試次數"
        )
    
    with col2:
        confirm_each_step = st.checkbox(
            "逐步確認",
            value=False,
            help="每個重要步驟都需要手動確認"
        )
    
    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
        with st.spinner("正在執行智慧填補..."):
            results = swapper.run_auto_fill_with_backtracking(max_backtracks)
            
            # 更新 schedule
            st.session_state.stage2_schedule = swapper.schedule
            
            # 顯示執行結果
            st.success(f"""
            ✅ **執行完成**
            - 直接填補：{len(results['direct_fills'])} 個
            - 交換解決：{len(results['swap_chains'])} 個
            - 回溯次數：{len(results['backtracks'])}
            - 剩餘空缺：{len(results['remaining_gaps'])} 個
            """)
            
            # 如果有剩餘空缺，顯示詳情
            if results['remaining_gaps']:
                with st.expander("❌ 無法解決的空缺", expanded=True):
                    for gap in results['remaining_gaps']:
                        st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")


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
            "B類醫師": len(gap.candidates_with_quota),
            "A類醫師": len(gap.candidates_over_quota),
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
            **B類醫師（有配額）**
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
            **A類醫師（超額）**
            {', '.join(gap.candidates_over_quota) if gap.candidates_over_quota else '無'}
            """)

def render_execution_report_tab(swapper: Stage2AdvancedSwapper):
    """執行報告標籤頁"""
    st.markdown("### 📈 執行報告")
    
    report = swapper.get_detailed_report()
    
    # 總體統計
    st.markdown("#### 總體統計")
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
    st.markdown("#### 優化指標")
    metrics = report['optimization_metrics']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("平均優先級", f"{metrics['average_priority']:.1f}")
    with col2:
        st.metric("最大機會成本", f"{metrics['max_opportunity_cost']:.1f}")
    with col3:
        st.metric("總未來影響", f"{metrics['total_future_impact']:.1f}")
    
    # 問題空缺列表
    if report['gap_analysis']['critical']:
        st.markdown("#### ⚠️ 關鍵空缺")
        critical_df = pd.DataFrame(report['gap_analysis']['critical'])
        st.dataframe(critical_df, use_container_width=True)
    
    # 下載報告
    if st.button("📥 下載詳細報告", use_container_width=True):
        import json
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button(
            label="💾 下載 JSON 報告",
            data=report_json,
            file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

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
            from datetime import datetime
            
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