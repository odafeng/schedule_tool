"""
執行排班頁面 - 整合假日管理器版本
"""
import streamlit as st
from backend.algorithms import BeamSearchScheduler
from backend.utils.holiday_manager import get_month_calendar_with_memory
from backend.utils.validation import validate_doctor_data
from backend.analyzers import ComplexityAnalyzer
from frontend.utils.session_manager import SessionManager
import pandas as pd

def render():
    """渲染執行排班頁面"""
    st.header("🚀 執行自動排班")
    
    # 檢查前置條件
    valid, errors = validate_doctor_data(st.session_state.doctors)
    
    if not valid:
        st.error("請先完成以下設定：")
        for error in errors:
            st.write(f"• {error}")
        return
    
    # 使用新的方式獲取月份資料
    holiday_manager = st.session_state.holiday_manager
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 使用 holiday_manager 取得平日和假日列表
    weekdays, holidays = get_month_calendar_with_memory(year, month, holiday_manager)
    
    # 顯示問題複雜度分析
    render_complexity_analysis(weekdays, holidays)
    
    # 排班參數顯示
    render_schedule_parameters(weekdays, holidays)
    
    # 進階選項
    render_advanced_options()
    
    # 執行按鈕
    render_execution_button(weekdays, holidays)

def render_complexity_analysis(weekdays: list, holidays: list):
    """渲染複雜度分析"""
    with st.expander("📊 問題複雜度分析", expanded=True):
        analyzer = ComplexityAnalyzer()
        analysis = analyzer.analyze(
            st.session_state.doctors,
            weekdays,
            holidays
        )
        
        # 第一行：基本資訊與難度
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("問題難度", analysis['difficulty'])
            st.metric("總天數", analysis['total_days'])
        
        with col2:
            st.metric("主治醫師", f"{analysis['attending_count']}人")
            st.metric("住院醫師", f"{analysis['resident_count']}人")
        
        with col3:
            st.metric("約束密度", f"{analysis['constraint_density']:.1%}")
            st.metric("最高個人衝突", f"{analysis['max_personal_conflict']:.1%}")
        
        with col4:
            feasible = "✅ 可行" if analysis['is_feasible'] else "❌ 不可行"
            st.metric("可行性", feasible)
            st.metric("瓶頸數", len(analysis['bottlenecks']))
        
        # 第二行：供需比分析（分角色）
        st.subheader("📊 供需比分析")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            ratio = analysis['weekday_attending_ratio']
            delta = "充足" if ratio >= 1.5 else "緊張" if ratio >= 1.0 else "不足"
            st.metric("平日主治", f"{ratio:.2f}", delta)
        
        with col2:
            ratio = analysis['weekday_resident_ratio']
            delta = "充足" if ratio >= 1.5 else "緊張" if ratio >= 1.0 else "不足"
            st.metric("平日住院", f"{ratio:.2f}", delta)
        
        with col3:
            ratio = analysis['holiday_attending_ratio']
            delta = "充足" if ratio >= 1.5 else "緊張" if ratio >= 1.0 else "不足"
            st.metric("假日主治", f"{ratio:.2f}", delta)
        
        with col4:
            ratio = analysis['holiday_resident_ratio']
            delta = "充足" if ratio >= 1.5 else "緊張" if ratio >= 1.0 else "不足"
            st.metric("假日住院", f"{ratio:.2f}", delta)
        
        # 瓶頸指標
        st.metric("🔴 最小供需比（瓶頸）", f"{analysis['min_supply_ratio']:.2f}")
        
        # 第三行：搜索空間分析
        st.subheader("🔍 搜索空間分析")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("搜索空間(log10)", f"{analysis['search_space_log10']:.1f}")
        
        with col2:
            st.metric("困難日數量", 
                     f"{analysis['hardest_days_count']}天",
                     f"每日選項中位數: {analysis['median_daily_options']:.0f}")
        
        with col3:
            # 顯示可行性細節
            details = analysis['feasibility_details']
            if not details['overall']:
                problems = []
                if not details['weekday_attending']:
                    problems.append("平日主治")
                if not details['weekday_resident']:
                    problems.append("平日住院")
                if not details['holiday_attending']:
                    problems.append("假日主治")
                if not details['holiday_resident']:
                    problems.append("假日住院")
                if details['daily_gaps']:
                    problems.append(f"{len(details['daily_gaps'])}天無人")
                
                st.error("不可行原因：" + "、".join(problems))
        
        # 顯示瓶頸詳情
        if analysis['bottlenecks']:
            st.warning("⚠️ 識別到的瓶頸：")
            for bottleneck in analysis['bottlenecks']:
                st.write(f"• {bottleneck}")
        
        # 顯示特定問題日期（如果有）
        if analysis['feasibility_details']['daily_gaps']:
            with st.expander("🚨 問題日期詳情", expanded=False):
                gaps = analysis['feasibility_details']['daily_gaps']
                gap_df = pd.DataFrame(gaps)
                st.dataframe(gap_df, use_container_width=True)

def render_schedule_parameters(weekdays: list, holidays: list):
    """渲染排班參數"""
    st.subheader("📋 排班參數")
    
    attending_count = len([d for d in st.session_state.doctors if d.role == "主治"])
    resident_count = len([d for d in st.session_state.doctors if d.role == "總醫師"])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("主治醫師", attending_count)
    with col2:
        st.metric("總醫師", resident_count)
    with col3:
        st.metric("平日數", len(weekdays))
    with col4:
        st.metric("假日數", len(holidays))
    
    # 顯示總格位數
    total_slots = (len(weekdays) + len(holidays)) * 2
    st.info(f"📊 **總格位數：{total_slots}** （每天需要1位主治+1位住院）")
    
    # 顯示當前設定
    constraints = st.session_state.constraints
    st.divider()
    st.markdown("### ⚙️ 當前演算法設定")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"""
        **基本參數**
        - 最大連續值班: {constraints.max_consecutive_days}天
        - 束搜索寬度: {constraints.beam_width}
        """)
    
    with col2:
        st.info(f"""
        **進階參數**
        - CSP超時: {constraints.csp_timeout}秒
        - 鄰域展開: {constraints.neighbor_expansion}
        - AC-3: {'✅ 啟用' if st.session_state.use_ac3 else '❌ 停用'}
        - 智慧回溯: {'✅ 啟用' if st.session_state.use_backjump else '❌ 停用'}
        """)

def render_advanced_options():
    """渲染進階選項"""
    with st.expander("🔬 進階選項", expanded=False):
        st.session_state.collect_all_solutions = st.checkbox(
            "收集所有候選解（用於ML訓練）", 
            value=True,
            help="收集搜索過程中的所有解，用於機器學習訓練資料生成"
        )
        
        st.info("""
        📌 **收集解池的好處**：
        - 生成大量標註資料用於訓練排班AI
        - 分析不同解的特徵分布
        - 了解演算法的搜索路徑
        - 找出潛在的優化方向
        """)

def render_execution_button(weekdays: list, holidays: list):
    """渲染執行按鈕"""
    
    # 執行前的最後檢查
    st.divider()
    st.markdown("### 🎯 執行排班")
    
    # 顯示預估時間
    total_days = len(weekdays) + len(holidays)
    estimated_time = estimate_execution_time(total_days, st.session_state.constraints.beam_width)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"⏱️ 預估執行時間：{estimated_time}")
    
    with col2:
        if st.button("🚀 開始排班", type="primary", use_container_width=True):
            execute_scheduling(weekdays, holidays)

def estimate_execution_time(total_days: int, beam_width: int) -> str:
    """估算執行時間"""
    # 簡單的時間估算公式
    base_time = total_days * beam_width * 0.1  # 秒
    
    if base_time < 60:
        return f"{base_time:.0f} 秒"
    elif base_time < 300:
        return f"{base_time/60:.1f} 分鐘"
    else:
        return f"{base_time/60:.0f} 分鐘"

def execute_scheduling(weekdays: list, holidays: list):
    """執行排班"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def update_progress(progress):
        progress_bar.progress(progress)
        status_text.text(f"排班進度：{int(progress * 100)}%")
    
    # 執行排班
    scheduler = BeamSearchScheduler(
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays
    )
    
    with st.spinner("正在執行智慧排班..."):
        result = scheduler.run(
            progress_callback=update_progress,
            collect_all_solutions=st.session_state.get('collect_all_solutions', True),
            use_ac3=st.session_state.get('use_ac3', True),
            use_backjump=st.session_state.get('use_backjump', True)
        )
        st.session_state.schedule_result = result
        st.session_state.last_scheduler = scheduler
    
    progress_bar.progress(1.0)
    status_text.text("排班完成！")
    
    # 顯示結果摘要
    render_result_summary(result, scheduler)

def render_result_summary(result, scheduler):
    """渲染結果摘要"""
    st.success("✅ 排班完成！")
    
    # 主要指標
    st.markdown("### 📊 排班結果")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_slots = result.statistics['total_slots']
        filled_slots = result.statistics['filled_slots']
        fill_rate = filled_slots/total_slots*100 if total_slots > 0 else 0
        st.metric("填充率", f"{fill_rate:.1f}%",
                 f"{filled_slots}/{total_slots}")
    with col2:
        st.metric("總分數", f"{result.score:.0f}")
    with col3:
        st.metric("未填格數", len(result.unfilled_slots))
    with col4:
        if 'score_breakdown' in result.statistics:
            breakdown = result.statistics['score_breakdown']
            st.metric("公平性分數", f"{breakdown.get('fairness', 0):.1f}")
        else:
            st.metric("狀態", "完成")
    
    # 顯示解池統計
    if st.session_state.get('collect_all_solutions') and hasattr(scheduler, 'solution_pool') and scheduler.solution_pool:
        with st.expander("🗂️ 解池統計", expanded=False):
            try:
                pool_metrics = scheduler.solution_pool.get_diversity_metrics()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("解池大小", pool_metrics.get('pool_size', 0))
                    st.metric("平均分數", f"{pool_metrics.get('avg_score', 0):.1f}")
                with col2:
                    st.metric("唯一解數量", pool_metrics.get('unique_schedules', 0))
                    st.metric("特徵多樣性", f"{pool_metrics.get('feature_diversity', 0):.3f}")
                with col3:
                    grade_dist = pool_metrics.get('grade_distribution', {})
                    if grade_dist:
                        grade_text = ", ".join([f"{g}:{c}" for g, c in grade_dist.items()])
                        st.metric("等級分布", grade_text)
                    else:
                        st.metric("等級分布", "N/A")
            except Exception as e:
                st.warning(f"無法取得解池統計：{str(e)}")
    
    # 顯示CSP求解統計
    if hasattr(st.session_state, 'csp_stats') and st.session_state.csp_stats:
        with st.expander("🔍 CSP求解統計", expanded=False):
            csp_stats = st.session_state.csp_stats
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("求解狀態", 
                         "✅ 成功" if csp_stats.get('solved', False) else "⚠️ 部分解")
            with col2:
                st.metric("探索節點數", csp_stats.get('nodes_explored', 0))
            with col3:
                st.metric("CSP前未填格", csp_stats.get('unfilled_before', 0))
            with col4:
                st.metric("CSP後未填格", csp_stats.get('unfilled_after', 0))
    
    # 顯示建議
    if hasattr(result, 'suggestions') and result.suggestions:
        with st.expander("💡 系統建議", expanded=True):
            for suggestion in result.suggestions:
                st.write(f"• {suggestion}")
    
    # 快速操作
    st.divider()
    st.markdown("### 🎬 下一步")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("👉 前往 **[結果檢視]** 查看詳細排班表")
    with col2:
        st.info("📊 前往 **[統計分析]** 查看數據分析")
    with col3:
        st.info("🤖 前往 **[ML訓練資料]** 匯出訓練資料")