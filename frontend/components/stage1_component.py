"""Stage 1 元件"""

import streamlit as st
import pandas as pd
import copy
from backend.algorithms.stage1_greedy_beam import Stage1Scheduler


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