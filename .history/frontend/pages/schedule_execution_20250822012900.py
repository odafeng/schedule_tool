"""
整合版執行排班頁面 - 三階段排班流程（含演算法參數設定）
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import copy

from backend.algorithms.stage1_greedy_beam import Stage1Scheduler, SchedulingState
from backend.algorithms.stage2_interactiveCSP import Stage2InteractiveFiller
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
        render_stage2(weekdays, holidays)
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

    # 進階CSP設定
    with st.expander("🎯 進階CSP設定", expanded=False):
        st.info(
            """
        **Arc Consistency (AC-3)**
        透過約束傳播提前偵測無解，大幅減少搜索空間
        
        **Conflict-Directed Backjumping**
        智慧回溯機制，直接跳回衝突源頭，避免無謂搜索
        """
        )

        col1, col2 = st.columns(2)

        with col1:
            st.session_state.use_ac3 = st.checkbox(
                "啟用 Arc Consistency",
                value=st.session_state.get("use_ac3", True),
                help="使用AC-3演算法進行約束傳播",
            )

        with col2:
            st.session_state.use_backjump = st.checkbox(
                "啟用 Conflict-Directed Backjumping",
                value=st.session_state.get("use_backjump", True),
                help="使用智慧回溯避免無謂搜索",
            )

        constraints.neighbor_expansion = st.slider(
            "鄰域展開上限",
            min_value=5,
            max_value=20,
            value=constraints.neighbor_expansion,
            help="每個變數展開的最大候選數",
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
        ac3_status = "✅" if st.session_state.get("use_ac3", True) else "❌"
        st.metric("AC-3", ac3_status)

    with col4:
        backjump_status = "✅" if st.session_state.get("use_backjump", True) else "❌"
        st.metric("Backjumping", backjump_status)


def render_stage_progress():
    """顯示階段進度"""
    stages = ["Stage 1: 快速排班", "Stage 2: 互動補洞", "Stage 3: 確認發佈"]
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
        st.success(f"✅ Stage 1 已完成！生成了 {len(results)} 個候選方案")
        
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
            st.rerun()  # 執行完後重新載入頁面以顯示結果
            
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


def execute_stage1(weekdays: list, holidays: list, beam_width: int):
    """執行 Stage 1（修正版）"""
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
    
    # 加入 debug 輸出
    print(f"✅ Generated {len(results)} solutions")
    for i, state in enumerate(results):
        print(f"Solution {i+1}: Score={state.score:.2f}, Fill rate={state.fill_rate:.1%}")
    
    # 顯示成功訊息
    st.success(f"✅ Stage 1 完成！生成了 {len(results)} 個候選方案")


def render_stage2(weekdays: list, holidays: list):
    """渲染 Stage 2: 互動式補洞"""
    st.subheader("🔧 Stage 2: 互動式補洞")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 1")
        return

    # 初始化 Stage 2 填充器
    filler = Stage2InteractiveFiller(
        schedule=st.session_state.stage2_schedule,
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays,
    )

    # 顯示完成狀態
    status = filler.get_completion_status()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("填充率", f"{status['fill_rate']:.1%}")
    with col2:
        st.metric("未填格數", status["unfilled_slots"])
    with col3:
        st.metric("危急空格", len(status["critical_gaps"]))
    with col4:
        if status["is_complete"]:
            st.success("✅ 已完成")
        else:
            st.warning("⏳ 未完成")

    # 如果已完成，提供進入 Stage 3 的選項
    if status["is_complete"] or status["unfilled_slots"] <= 1:
        st.success("🎉 排班已完成或接近完成！")
        if st.button(
            "➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True
        ):
            st.session_state.current_stage = 3
            st.rerun()
        return

    # 顯示未填格列表
    st.subheader("🔍 未填格列表（按嚴重度排序）")

    # 使用分頁顯示未填格
    tab1, tab2, tab3 = st.tabs(["🔴 手動填充", "🤖 CSP 自動填充", "🔄 交換建議"])

    with tab1:
        render_manual_filling(filler)

    with tab2:
        render_csp_filling(filler)

    with tab3:
        render_swap_suggestions(filler)


def render_manual_filling(filler: Stage2InteractiveFiller):
    """渲染手動填充介面"""
    st.markdown("### 點選空格進行填充")

    # 顯示前10個最嚴重的空格
    gaps_to_show = filler.gaps[:10]

    for gap in gaps_to_show:
        with st.expander(
            f"🔍 {gap.date} - {gap.role} "
            f"({'假日' if gap.is_holiday else '平日'}) "
            f"[嚴重度: {gap.severity:.0f}]",
            expanded=False,
        ):
            # 顯示候選人
            candidates = filler.get_candidate_details(gap.date, gap.role)

            if not candidates:
                st.error("❌ 此位置無可用醫師")
                continue

            st.markdown("**候選醫師：**")

            for i, candidate in enumerate(candidates[:5]):
                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

                with col1:
                    st.text(f"{i+1}. {candidate.name}")

                with col2:
                    st.text(f"分數: +{candidate.score_delta:.0f}")

                with col3:
                    feasibility_color = (
                        "🟢"
                        if candidate.feasibility > 0.7
                        else "🟡" if candidate.feasibility > 0.3 else "🔴"
                    )
                    st.text(f"{feasibility_color} {candidate.feasibility:.0%}")

                with col4:
                    if st.button(
                        "選擇", key=f"select_{gap.date}_{gap.role}_{candidate.name}"
                    ):
                        if filler.apply_assignment(gap.date, gap.role, candidate.name):
                            st.success(f"✅ 已將 {candidate.name} 排入 {gap.date}")
                            st.session_state.stage2_schedule = filler.schedule
                            st.rerun()

                # 顯示優缺點
                if candidate.pros:
                    st.success("優點: " + ", ".join(candidate.pros))
                if candidate.cons:
                    st.warning("缺點: " + ", ".join(candidate.cons))


def render_csp_filling(filler: Stage2InteractiveFiller):
    """渲染 CSP 自動填充介面"""
    st.markdown("### 🤖 CSP 局部求解")

    st.info(
        """
    使用 CSP (約束滿足問題) 演算法自動填充局部區域的空格。
    演算法會考慮所有約束條件，找出可行解。
    """
    )

    # 選擇目標空格
    gaps = filler.gaps[:20]
    gap_options = [f"{g.date} - {g.role}" for g in gaps]

    if not gap_options:
        st.info("沒有未填格")
        return

    selected_gap_index = st.selectbox(
        "選擇目標空格：", range(len(gap_options)), format_func=lambda x: gap_options[x]
    )

    selected_gap = gaps[selected_gap_index]

    neighborhood_size = st.slider("鄰域大小（前後幾天）", 1, 5, 3)

    if st.button("🤖 執行 CSP 求解", type="primary"):
        with st.spinner("正在執行 CSP 求解..."):
            solution = filler.apply_csp_local(
                selected_gap.date, selected_gap.role, neighborhood_size
            )

        if solution:
            st.success(f"✅ CSP 找到解！填充了 {len(solution)} 個位置")

            # 顯示解的詳情
            st.markdown("**填充結果：**")
            for var, doctor_name in solution.items():
                st.write(f"• {var.date} {var.role}: {doctor_name}")

            # 應用解
            if st.button("✅ 應用此解"):
                for var, doctor_name in solution.items():
                    filler.apply_assignment(var.date, var.role, doctor_name)
                st.session_state.stage2_schedule = filler.schedule
                st.success("已應用 CSP 解")
                st.rerun()
        else:
            st.warning("❌ CSP 無法找到可行解，請嘗試調整參數或手動填充")


def render_swap_suggestions(filler: Stage2InteractiveFiller):
    """渲染交換建議"""
    st.markdown("### 🔄 智慧交換建議")

    suggestions = filler.get_swap_suggestions(max_suggestions=5)

    if not suggestions:
        st.info("暫無交換建議")
        return

    st.markdown("**系統建議的有益交換：**")

    for i, suggestion in enumerate(suggestions):
        with st.expander(
            f"建議 {i+1}: {suggestion.description} (改善 +{suggestion.score_improvement:.0f}分)"
        ):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**原位置：**")
                st.write(f"• 日期: {suggestion.date2}")
                st.write(f"• 角色: {suggestion.role2}")
                st.write(f"• 醫師: {suggestion.doctor2}")

            with col2:
                st.markdown("**新位置：**")
                st.write(f"• 日期: {suggestion.date1}")
                st.write(f"• 角色: {suggestion.role1}")
                st.write(f"• 醫師: {suggestion.doctor2}")

            if st.button(f"執行交換", key=f"swap_{i}"):
                # 執行交換
                filler.schedule[suggestion.date1].attending = suggestion.doctor2
                filler.schedule[suggestion.date2].attending = None
                st.session_state.stage2_schedule = filler.schedule
                st.success("✅ 交換完成")
                st.rerun()


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

def preview_schedule(schedule: dict):
    """預覽排班表"""
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
    
    st.dataframe(df, use_container_width=True, height=400)