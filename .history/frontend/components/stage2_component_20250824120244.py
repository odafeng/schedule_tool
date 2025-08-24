"""
Stage 2 元件（簡化版）
更簡潔、使用者友善的介面
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from typing import List, Dict, Optional
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
import json
import copy
import calendar


def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染簡化的 Stage 2: 進階智慧交換補洞系統"""
    st.subheader("🔧 Stage 2: 智慧補洞系統")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 1")
        return

    # 初始化或取得 Stage 2 系統
    if st.session_state.stage2_swapper is None:
        with st.spinner("正在初始化 Stage 2 系統..."):
            try:
                st.session_state.stage2_swapper = Stage2AdvancedSwapper(
                    schedule=st.session_state.stage2_schedule,
                    doctors=st.session_state.doctors,
                    constraints=st.session_state.constraints,
                    weekdays=weekdays,
                    holidays=holidays,
                )
                # 清除自動填補結果
                if "auto_fill_results" in st.session_state:
                    del st.session_state.auto_fill_results
            except Exception as e:
                st.error(f"初始化失敗: {str(e)}")
                return

    swapper = st.session_state.stage2_swapper

    # 簡單的狀態顯示
    report = swapper.get_detailed_report()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("填充率", f"{report['summary']['fill_rate']:.1%}")
    with col2:
        st.metric("剩餘空缺", report["summary"]["unfilled_slots"])
    with col3:
        status = "✅ 完成" if report["summary"]["unfilled_slots"] == 0 else "🔄 進行中"
        st.metric("狀態", status)

    # 初始化 tab 狀態
    if "stage2_active_tab" not in st.session_state:
        st.session_state.stage2_active_tab = 0

    # 主要操作區 - 三個標籤
    tabs = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📊 最終輸出"])

    with tabs[0]:
        render_calendar_view_simplified(swapper, weekdays, holidays)

    with tabs[1]:
        render_auto_fill_simplified(swapper)

    with tabs[2]:
        render_final_output(swapper, weekdays, holidays)


def render_calendar_view_simplified(swapper, weekdays: list, holidays: list):
    """簡化的日曆檢視標籤頁"""
    st.markdown("### 📅 當前排班狀態")

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
        gap_details=gap_details,
    )


def render_auto_fill_simplified(swapper):
    """簡化的智慧填補標籤頁"""
    st.markdown("### 🤖 智慧自動填補")

    # 取得目前空缺概況
    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return

    # 顯示簡單統計
    st.info(f"目前還有 **{report['summary']['unfilled_slots']}** 個空缺需要處理")

    # 初始化 session state
    if "auto_fill_logs" not in st.session_state:
        st.session_state.auto_fill_logs = []
    if "auto_fill_running" not in st.session_state:
        st.session_state.auto_fill_running = False

    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True, 
                 disabled=st.session_state.auto_fill_running):
        st.session_state.auto_fill_running = True
        st.session_state.auto_fill_logs = []
        
        # 創建日誌容器
        log_container = st.container()
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 執行自動填補
        execute_auto_fill_simple(swapper, log_container, progress_bar, status_text)
        
        # 完成後自動跳轉到最終輸出頁
        st.session_state.auto_fill_running = False
        st.session_state.stage2_active_tab = 2  # 切換到第三個 tab
        st.success("✅ 填補完成！請查看最終輸出")
        time.sleep(1)
        st.rerun()

    # 顯示現有日誌
    if st.session_state.auto_fill_logs:
        st.markdown("#### 執行日誌")
        log_text = "\n".join(st.session_state.auto_fill_logs[-20:])  # 只顯示最近20條
        st.code(log_text, language="text")


def execute_auto_fill_simple(swapper, log_container, progress_bar, status_text):
    """簡化的自動填補執行函式"""
    max_backtracks = 1000  # 減少回溯次數加快執行

    def add_log(message: str):
        """添加日誌"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        st.session_state.auto_fill_logs.append(log_line)
        
        # 每10條更新一次顯示
        if len(st.session_state.auto_fill_logs) % 10 == 0:
            with log_container:
                st.code("\n".join(st.session_state.auto_fill_logs[-20:]), language="text")

    # 設置日誌回調
    swapper.set_log_callback(lambda msg, level: add_log(msg))
    swapper.set_log_level('quiet')  # 設為安靜模式，減少日誌輸出

    try:
        # 開始執行
        progress_bar.progress(0.1)
        status_text.text("開始執行智慧填補...")
        add_log("開始執行智慧填補系統")

        initial_gaps = len(swapper.gaps)
        add_log(f"初始空缺數: {initial_gaps}")

        # 執行自動填補
        start_time = time.time()
        results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        elapsed_time = time.time() - start_time

        # 更新結果到 session state
        final_gaps = len(swapper.gaps)
        st.session_state.auto_fill_results = {
            "total_backtracks": results.get("backtracks", []),
            "swap_attempts": len(results.get("swap_chains", [])),
            "remaining_gaps": final_gaps,
            "elapsed_time": elapsed_time
        }

        # 同步更新 schedule
        st.session_state.stage2_schedule = copy.deepcopy(swapper.schedule)

        # 最終狀態
        progress_bar.progress(1.0)
        add_log(f"執行完成！耗時: {elapsed_time:.2f} 秒")
        add_log(f"剩餘空缺: {final_gaps} 個")
        status_text.text(f"✅ 完成！剩餘 {final_gaps} 個空缺")

    except Exception as e:
        add_log(f"執行失敗：{str(e)}")
        status_text.text(f"❌ 執行失敗：{str(e)}")


def render_final_output(swapper, weekdays: list, holidays: list):
    """最終輸出標籤頁"""
    st.markdown("### 📊 最終輸出")

    # 簡單統計資訊
    if st.session_state.auto_fill_results:
        col1, col2, col3 = st.columns(3)
        results = st.session_state.auto_fill_results
        
        with col1:
            st.metric("總回溯次數", len(results.get("total_backtracks", [])))
        with col2:
            st.metric("嘗試交換次數", results.get("swap_attempts", 0))
        with col3:
            st.metric("剩餘空格數", results.get("remaining_gaps", 0))
    else:
        st.info("尚未執行智慧填補")

    st.divider()

    # 可編輯的日曆表格
    st.markdown("### 📝 手動調整班表")
    st.info("您可以直接在下方表格中調整每個日期的值班醫師")

    # 建立可編輯的資料表
    schedule_data = []
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    num_days = calendar.monthrange(year, month)[1]

    # 取得所有醫師名單
    all_doctors = [doc.name for doc in st.session_state.doctors]
    attending_doctors = [doc.name for doc in st.session_state.doctors if doc.role == "主治"]
    resident_doctors = [doc.name for doc in st.session_state.doctors if doc.role == "總醫師"]

    for day in range(1, num_days + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday_name = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
        
        if date_str in swapper.schedule:
            slot = swapper.schedule[date_str]
            schedule_data.append({
                '日期': f"{month}/{day}",
                '星期': weekday_name,
                '類型': '假日' if date_str in holidays else '平日',
                '主治醫師': slot.attending or "（空缺）",
                '總醫師': slot.resident or "（空缺）",
                'date_str': date_str  # 隱藏欄位用於追蹤
            })

    df = pd.DataFrame(schedule_data)

    # 使用 data_editor 允許編輯
    edited_df = st.data_editor(
        df[['日期', '星期', '類型', '主治醫師', '總醫師']],
        column_config={
            "主治醫師": st.column_config.SelectboxColumn(
                "主治醫師",
                options=["（空缺）"] + attending_doctors,
                required=False
            ),
            "總醫師": st.column_config.SelectboxColumn(
                "總醫師",
                options=["（空缺）"] + resident_doctors,
                required=False
            ),
        },
        disabled=['日期', '星期', '類型'],
        use_container_width=True,
        hide_index=True,
        key="schedule_editor"
    )

    # 儲存按鈕
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("💾 儲存修改", use_container_width=True):
            # 更新 schedule
            for idx, row in edited_df.iterrows():
                date_str = schedule_data[idx]['date_str']
                if date_str in swapper.schedule:
                    swapper.schedule[date_str].attending = None if row['主治醫師'] == "（空缺）" else row['主治醫師']
                    swapper.schedule[date_str].resident = None if row['總醫師'] == "（空缺）" else row['總醫師']
            
            # 同步到 session state
            st.session_state.stage2_schedule = copy.deepcopy(swapper.schedule)
            st.success("✅ 班表已更新")
            st.rerun()

    with col2:
        # 匯出 CSV
        csv_data = edited_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下載 CSV",
            data=csv_data,
            file_name=f"schedule_{year}_{month:02d}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col3:
        # 進入 Stage 3
        remaining_gaps = sum(1 for _, row in edited_df.iterrows() 
                           if row['主治醫師'] == "（空缺）" or row['總醫師'] == "（空缺）")
        
        if remaining_gaps == 0:
            if st.button("➡️ 進入 Stage 3：確認發佈", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
        else:
            if st.button(f"➡️ 接受並進入 Stage 3（還有 {remaining_gaps} 個空缺）", 
                        type="secondary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()