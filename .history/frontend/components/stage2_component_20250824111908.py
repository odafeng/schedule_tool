"""
Stage 2 元件（修正版）
解決 WebSocket 錯誤和回溯狀態同步問題
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from typing import List, Dict, Optional
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
import json
from collections import deque
import copy


def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染新的 Stage 2: 進階智慧交換補洞系統（修正版）"""
    st.subheader("🔧 Stage 2: 進階智慧交換補洞系統")

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

    # 顯示系統狀態
    render_stage2_status(swapper)

    # 主要操作區 - 只有三個標籤
    tab1, tab2, tab3 = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📈 執行報告"])

    with tab1:
        render_calendar_view_tab(swapper, weekdays, holidays)

    with tab2:
        render_auto_fill_tab_fixed(swapper)

    with tab3:
        render_execution_report_tab(swapper)

    # 進入 Stage 3 的按鈕
    st.divider()

    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 所有空缺已成功填補！")
        if st.button(
            "➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True
        ):
            # 確保最終排程已同步
            st.session_state.stage2_schedule = swapper.schedule
            if "auto_fill_results" in st.session_state:
                del st.session_state.auto_fill_results
            st.session_state.current_stage = 3
            st.rerun()
    elif report["summary"]["unfilled_slots"] <= 2:
        st.warning(f"⚠️ 還有 {report['summary']['unfilled_slots']} 個空缺未填補")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 繼續嘗試", use_container_width=True):
                if "auto_fill_results" in st.session_state:
                    del st.session_state.auto_fill_results
                st.rerun()
        with col2:
            if st.button(
                "➡️ 接受並進入 Stage 3", type="primary", use_container_width=True
            ):
                # 確保最終排程已同步
                st.session_state.stage2_schedule = swapper.schedule
                if "auto_fill_results" in st.session_state:
                    del st.session_state.auto_fill_results
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")


def render_stage2_status(swapper):
    """顯示 Stage 2 系統狀態"""
    try:
        # 強制更新 swapper 的內部狀態
        swapper._analyze_gaps_advanced()
        report = swapper.get_detailed_report()

        # 主要指標
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "填充率",
                f"{report['summary']['fill_rate']:.1%}",
                delta=f"{report['summary']['filled_slots']}/{report['summary']['total_slots']}",
            )

        with col2:
            st.metric(
                "剩餘空缺",
                report["summary"]["unfilled_slots"],
                delta=(
                    -len(report["gap_analysis"]["easy"])
                    if report["gap_analysis"]["easy"]
                    else None
                ),
            )

        with col3:
            st.metric(
                "已應用交換", report["applied_swaps"], help="成功執行的交換鏈數量"
            )

        with col4:
            status = (
                "✅ 完成" if report["summary"]["unfilled_slots"] == 0 else "🔄 進行中"
            )
            st.metric("狀態", status)
    except Exception as e:
        st.error(f"無法取得狀態: {str(e)}")


def render_auto_fill_tab_fixed(swapper):
    """修正版的自動填補標籤頁 - 解決 WebSocket 和狀態同步問題"""
    st.markdown("### 🤖 智慧自動填補系統 v4.0 (Fixed)")

    # 取得目前空缺概況
    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return

    # 顯示空缺統計
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總空缺", report["summary"]["unfilled_slots"])
    with col2:
        st.metric(
            "🟢 簡單",
            len(report["gap_analysis"]["easy"]),
            help="有配額餘額，可直接填補",
        )
    with col3:
        st.metric("🟡 中等", len(report["gap_analysis"]["medium"]), help="需要交換班次")
    with col4:
        st.metric("🔴 困難", len(report["gap_analysis"]["hard"]), help="無可用醫師")

    st.divider()

    # 初始化 session state
    if "auto_fill_logs" not in st.session_state:
        st.session_state.auto_fill_logs = []
    if "auto_fill_progress" not in st.session_state:
        st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
    if "auto_fill_result" not in st.session_state:
        st.session_state.auto_fill_result = None

    # 控制按鈕區
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        run_button = st.button(
            "🚀 開始智慧填補", type="primary", use_container_width=True
        )

    with col2:
        if st.button("🧹 清空日誌", use_container_width=True):
            st.session_state.auto_fill_logs = []
            st.session_state.auto_fill_progress = {
                "filled": 0,
                "swapped": 0,
                "failed": 0,
            }
            st.session_state.auto_fill_result = None
            st.rerun()

    with col3:
        if st.button("📥 下載日誌", use_container_width=True):
            if st.session_state.auto_fill_logs:
                log_text = "\n".join(st.session_state.auto_fill_logs)
                st.download_button(
                    label="💾 下載 TXT",
                    data=log_text,
                    file_name=f"auto_fill_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                )

    # 執行區域
    if run_button:
        # 清空舊資料
        st.session_state.auto_fill_logs = []
        st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
        st.session_state.auto_fill_result = None

        # 創建日誌容器
        log_container = st.container()
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 執行自動填補（不使用 st.status 避免 WebSocket 問題）
        execute_auto_fill_safe(swapper, log_container, progress_bar, status_text)

    # 顯示歷史日誌（如果有）
    if st.session_state.auto_fill_logs:
        st.markdown("#### 📟 執行日誌")

        # 使用 expander 來顯示日誌
        with st.expander("查看詳細日誌", expanded=True):
            # 顯示統計
            progress = st.session_state.auto_fill_progress
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("✅ 直接填補", progress["filled"])
            with col2:
                st.metric("🔄 交換解決", progress["swapped"])
            with col3:
                st.metric("❌ 失敗", progress["failed"])

            # 創建黑色背景的終端機風格日誌顯示區
            log_text = "\n".join(
                st.session_state.auto_fill_logs[-100:]
            )  # 只顯示最後100條

            # 使用 HTML/CSS 創建黑色背景的日誌區
            st.markdown(
                f"""
                <div style="
                    background-color: #0d0d0d;
                    color: #f0f0f0;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 14px;
                    font-weight: 400;
                    line-height: 1.5;
                    padding: 15px;
                    border-radius: 5px;
                    height: 400px;
                    overflow-y: auto;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    border: 1px solid #333333;
                ">
                    <pre style="color: #f0f0f0; margin: 0; font-weight: 400; opacity: 1;">{log_text}</pre>
                </div>
                """,
                unsafe_allow_html=True
            )

    # 顯示執行結果（如果有）
    if st.session_state.auto_fill_result:
        st.divider()
        display_execution_result(st.session_state.auto_fill_result)


def execute_auto_fill_safe(swapper, log_container, progress_bar, status_text):
    """安全執行自動填補 - 避免 WebSocket 錯誤並正確處理回溯"""
    max_backtracks = 2000  # 減少回溯次數避免超時

    # 進度追蹤
    progress_data = {"filled": 0, "swapped": 0, "failed": 0}
    search_metrics = {
        "gaps_processed": 0,
        "chains_explored": 0,
        "backtracks": 0,
        "depth_reached": 0,
        "last_gap_count": len(swapper.gaps),
    }

    # 創建日誌顯示區域
    with log_container:
        log_display = st.empty()
        metrics_display = st.empty()

    def add_log(message: str, level: str = "INFO"):
        """添加日誌並更新顯示"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # 決定圖標和顏色代碼（用於終端機風格）
        level_styles = {
            "SUCCESS": ("✅", "\033[92m"),  # 綠色
            "ERROR": ("❌", "\033[91m"),  # 紅色
            "WARNING": ("⚠️", "\033[93m"),  # 黃色
            "INFO": ("ℹ️", "\033[94m"),  # 藍色
            "DEBUG": ("🔍", "\033[90m"),  # 灰色
        }
        icon, color = level_styles.get(level.upper(), ("▶", "\033[0m"))

        # 格式化日誌
        log_line = f"[{timestamp}] {icon} {message}"
        st.session_state.auto_fill_logs.append(log_line)

        # 限制日誌數量避免記憶體問題
        if len(st.session_state.auto_fill_logs) > 500:
            st.session_state.auto_fill_logs = st.session_state.auto_fill_logs[-400:]

        should_update = (
            len(st.session_state.auto_fill_logs) % 10 == 0  # 每 10 條更新
            or level in ["SUCCESS", "ERROR", "WARNING"]  # 重要訊息立即更新
            or "完成" in message
            or "失敗" in message  # 關鍵字立即更新
        )

        if should_update:
            # 更新顯示（黑色背景終端機風格）
            recent_logs = st.session_state.auto_fill_logs[-20:]
            log_html = f"""
            <div style="
                background-color: #0d0d0d;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 14px;
                font-weight: 400;
                line-height: 1.5;
                padding: 15px;
                border-radius: 5px;
                height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                border: 1px solid #333333;
            ">
                <pre style="color: #f0f0f0; margin: 0; font-weight: 400; opacity: 1;">{"<br>".join(recent_logs)}</pre>
            </div>
            """
            log_display.markdown(log_html, unsafe_allow_html=True)
            if level in ["SUCCESS", "ERROR", "WARNING"]:
                time.sleep(0.1)  # 重要訊息停留 0.1 秒

        # 更新進度
        if "直接填補成功" in message:
            progress_data["filled"] += 1
            st.session_state.auto_fill_progress["filled"] = progress_data["filled"]
        elif "交換鏈執行成功" in message:
            progress_data["swapped"] += 1
            st.session_state.auto_fill_progress["swapped"] = progress_data["swapped"]
        elif "無法解決" in message:
            progress_data["failed"] += 1
            st.session_state.auto_fill_progress["failed"] = progress_data["failed"]

        # 更新搜索指標
        if "處理空缺" in message:
            search_metrics["gaps_processed"] += 1
        elif "探索交換路徑" in message:
            search_metrics["chains_explored"] += 1
        elif "回溯" in message:
            search_metrics["backtracks"] += 1
            # 更新進度條
            progress = min(
                0.1 + (search_metrics["backtracks"] / max_backtracks) * 0.8, 0.9
            )
            progress_bar.progress(progress)
            status_text.text(
                f"執行中... (回溯: {search_metrics['backtracks']}/{max_backtracks})"
            )

        # 檢測空缺數量變化（避免遞迴）
        if "檢測中" not in message:  # 防止遞迴
            current_gap_count = len(swapper.gaps)
            if current_gap_count != search_metrics["last_gap_count"]:
                if current_gap_count < search_metrics["last_gap_count"]:
                    # 直接添加到日誌列表，不要再次調用 add_log
                    change_msg = f"📉 [檢測中] 空缺減少: {search_metrics['last_gap_count']} → {current_gap_count}"
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    log_line = f"[{timestamp}] ✅ {change_msg}"
                    st.session_state.auto_fill_logs.append(log_line)
                elif current_gap_count > search_metrics["last_gap_count"]:
                    # 直接添加到日誌列表，不要再次調用 add_log
                    change_msg = f"📈 [檢測中] 空缺增加: {search_metrics['last_gap_count']} → {current_gap_count} (可能因回溯)"
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    log_line = f"[{timestamp}] ⚠️ {change_msg}"
                    st.session_state.auto_fill_logs.append(log_line)
                search_metrics["last_gap_count"] = current_gap_count

        # 定期顯示進度統計
        if (
            search_metrics["gaps_processed"] % 5 == 0
            and search_metrics["gaps_processed"] > 0
        ):
            with metrics_display.container():
                cols = st.columns(5)
                with cols[0]:
                    st.metric("處理", search_metrics["gaps_processed"])
                with cols[1]:
                    st.metric("填補", progress_data["filled"])
                with cols[2]:
                    st.metric("交換", progress_data["swapped"])
                with cols[3]:
                    st.metric("失敗", progress_data["failed"])
                with cols[4]:
                    st.metric("剩餘", current_gap_count)

    # 設置日誌回調
    swapper.set_log_callback(add_log)

    try:
        # 保存初始狀態（用於比較）
        initial_schedule = copy.deepcopy(swapper.schedule)
        initial_gaps = len(swapper.gaps)

        # 開始執行
        progress_bar.progress(0.05)
        status_text.text("開始執行智慧填補...")

        add_log("=" * 50, "INFO")
        add_log("開始執行智慧自動填補系統", "INFO")
        add_log(f"演算法配置:", "INFO")
        add_log(f"  - 最大回溯次數: {max_backtracks:,}", "INFO")
        add_log(f"  - 搜索深度: 5", "INFO")
        add_log(f"  - 束寬度: 5", "INFO")
        add_log("=" * 50, "INFO")

        # 分析初始狀態
        add_log(f"初始狀態分析:", "INFO")
        add_log(f"  - 總空缺數: {len(swapper.gaps)}", "INFO")

        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium_gaps = len(
            [
                g
                for g in swapper.gaps
                if g.candidates_over_quota and not g.candidates_with_quota
            ]
        )
        hard_gaps = len(
            [
                g
                for g in swapper.gaps
                if not g.candidates_with_quota and not g.candidates_over_quota
            ]
        )

        add_log(f"  - 簡單空缺: {easy_gaps} (有配額餘額)", "INFO")
        add_log(f"  - 中等空缺: {medium_gaps} (需要交換)", "INFO")
        add_log(f"  - 困難空缺: {hard_gaps} (無可用醫師)", "INFO")
        add_log("=" * 50, "INFO")

        # 開始計時
        start_time = time.time()

        # 執行自動填補（降低回溯次數）
        add_log("開始執行自動填補演算法...", "INFO")

        # 使用較小的回溯次數並定期檢查時間
        results = None
        try:
            results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        except Exception as e:
            add_log(f"執行中斷: {str(e)}", "WARNING")
            # 即使中斷也要保存當前進度
            results = {
                "direct_fills": [],
                "swap_chains": [],
                "remaining_gaps": [
                    {"date": g.date, "role": g.role, "reason": "執行中斷"}
                    for g in swapper.gaps
                ],
            }

        # 計算耗時
        elapsed_time = time.time() - start_time

        # 最終狀態檢查
        final_gaps = len(swapper.gaps)
        actual_improvement = initial_gaps - final_gaps

        # 結果分析
        add_log("=" * 50, "INFO")
        add_log("執行結果分析:", "INFO")
        add_log(f"  - 總耗時: {elapsed_time:.3f} 秒", "INFO")
        add_log(f"  - 初始空缺: {initial_gaps} 個", "INFO")
        add_log(f"  - 最終空缺: {final_gaps} 個", "INFO")
        add_log(f"  - 實際改善: {actual_improvement} 個", "INFO")
        add_log(f"  - 直接填補: {len(results.get('direct_fills', []))} 個", "INFO")
        add_log(f"  - 交換解決: {len(results.get('swap_chains', []))} 個", "INFO")
        add_log(f"  - 總回溯次數: {search_metrics['backtracks']}", "INFO")
        add_log("=" * 50, "INFO")

        results["elapsed_time"] = elapsed_time
        results["search_metrics"] = search_metrics
        results["actual_improvement"] = actual_improvement

        # 重要：同步更新 schedule 到 session state
        st.session_state.stage2_schedule = copy.deepcopy(swapper.schedule)
        st.session_state.auto_fill_result = results

        # 強制更新 swapper 的內部狀態
        swapper._analyze_gaps_advanced()

        # 最終狀態
        progress_bar.progress(1.0)
        if results.get("remaining_gaps"):
            add_log(
                f"執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決",
                "WARNING",
            )
            status_text.text(f"⚠️ 完成！還有 {len(results['remaining_gaps'])} 個空缺")
        else:
            add_log("完美執行！所有空缺已填補", "SUCCESS")
            status_text.text("✅ 完美執行！所有空缺已填補")

    except Exception as e:
        add_log(f"執行失敗：{str(e)}", "ERROR")
        status_text.text(f"❌ 執行失敗：{str(e)}")

        import traceback

        for line in traceback.format_exc().split("\n"):
            if line.strip():
                add_log(f"  {line}", "ERROR")

        # 保存錯誤狀態
        st.session_state.auto_fill_result = {
            "error": str(e),
            "remaining_gaps": [
                {"date": g.date, "role": g.role, "reason": "執行錯誤"}
                for g in swapper.gaps
            ],
        }


def render_calendar_view_tab(swapper, weekdays: list, holidays: list):
    """日曆檢視標籤頁"""
    st.markdown("### 📅 互動式月曆檢視")

    # 使用說明
    with st.expander("📖 使用說明", expanded=False):
        st.info(
            """
            **互動功能：**
            - 🖱️ 將滑鼠移至空缺格子上，查看可用醫師詳情
            - ✅ **綠色標籤**：可直接安排的醫師（有配額餘額）
            - ⚠️ **橙色標籤**：需要調整才能安排的醫師
            - 每個醫師會顯示具體的限制原因
            """
        )

    # 新增手動重新整理按鈕
    if st.button("🔄 重新整理日曆", use_container_width=True):
        # 強制重新分析空缺
        swapper._analyze_gaps_advanced()
        st.rerun()

    try:
        # 取得詳細的空缺資訊
        gap_details = swapper.get_gap_details_for_calendar()

        # 渲染互動式日曆
        from frontend.components.calendar_view import render_calendar_view

        year = st.session_state.selected_year
        month = st.session_state.selected_month

        # 確保使用最新的 schedule
        render_calendar_view(
            schedule=swapper.schedule,  # 直接使用 swapper 的 schedule
            doctors=st.session_state.doctors,
            year=year,
            month=month,
            weekdays=weekdays,
            holidays=holidays,
            gap_details=gap_details,
        )
    except Exception as e:
        st.error(f"無法顯示日曆: {str(e)}")

    # 顯示統計摘要和快速操作
    st.divider()
    st.markdown("### 📊 空缺統計摘要")

    try:
        col1, col2, col3, col4 = st.columns(4)

        total_gaps = len(swapper.gaps)
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium_gaps = len(
            [
                g
                for g in swapper.gaps
                if g.candidates_over_quota and not g.candidates_with_quota
            ]
        )
        hard_gaps = len(
            [
                g
                for g in swapper.gaps
                if not g.candidates_with_quota and not g.candidates_over_quota
            ]
        )

        with col1:
            st.metric("總空缺數", total_gaps)
        with col2:
            st.metric("🟢 可直接填補", easy_gaps)
        with col3:
            st.metric("🟡 需要調整", medium_gaps)
        with col4:
            st.metric("🔴 困難空缺", hard_gaps)
    except Exception as e:
        st.error(f"無法顯示統計: {str(e)}")

    # 快速操作按鈕
    st.divider()
    st.markdown("### ⚡ 快速操作")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 重新分析空缺", use_container_width=True):
            with st.spinner("正在重新分析..."):
                swapper.gaps = swapper._analyze_gaps_advanced()
                st.session_state.stage2_schedule = swapper.schedule
            st.success("✅ 空缺分析已更新")
            st.rerun()

    with col2:
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        if easy_gaps > 0:
            if st.button(
                f"✅ 快速填補 {easy_gaps} 個簡單空缺",
                use_container_width=True,
                type="primary",
            ):
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

    with col3:
        if st.button("💾 匯出當前狀態", use_container_width=True):
            year = st.session_state.selected_year
            month = st.session_state.selected_month

            export_data = {
                "timestamp": datetime.now().isoformat(),
                "year": year,
                "month": month,
                "schedule": {
                    date: {"attending": slot.attending, "resident": slot.resident}
                    for date, slot in swapper.schedule.items()
                },
                "statistics": {
                    "total_gaps": total_gaps,
                    "easy_gaps": easy_gaps,
                    "medium_gaps": medium_gaps,
                    "hard_gaps": hard_gaps,
                    "fill_rate": swapper.get_detailed_report()["summary"]["fill_rate"],
                },
            }

            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 下載 JSON",
                data=json_str,
                file_name=f"schedule_stage2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )


def display_execution_result(results):
    """顯示執行結果"""
    st.markdown("### 📊 執行結果")

    # 結果統計
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("⏱️ 總耗時", f"{results.get('elapsed_time', 0):.2f} 秒")

    with col2:
        st.metric("✅ 直接填補", len(results.get("direct_fills", [])))

    with col3:
        st.metric("🔄 交換解決", len(results.get("swap_chains", [])))

    with col4:
        st.metric("❌ 剩餘空缺", len(results.get("remaining_gaps", [])))

    with col5:
        improvement = results.get("actual_improvement", 0)
        st.metric("📈 實際改善", improvement, delta=f"-{improvement} 空缺")

    # 詳細資訊
    if results.get("remaining_gaps"):
        with st.expander("❌ 無法解決的空缺", expanded=True):
            gap_data = []
            for gap in results["remaining_gaps"]:
                gap_data.append(
                    {
                        "日期": gap.get("date", "N/A"),
                        "角色": gap.get("role", "N/A"),
                        "原因": gap.get("reason", "無原因資訊"),
                    }
                )

            if gap_data:
                gap_df = pd.DataFrame(gap_data)
                st.dataframe(gap_df, use_container_width=True, hide_index=True)

        st.info("💡 建議：可以嘗試調整醫師配額後重試，或手動處理剩餘空缺")

    if results.get("swap_chains"):
        with st.expander(f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)"):
            for i, swap_info in enumerate(results["swap_chains"], 1):
                st.write(f"**交換 {i}**: {swap_info.get('gap', 'N/A')}")
                if "chain" in swap_info:
                    for step in swap_info["chain"]:
                        st.write(f"  • {step}")

    # 操作按鈕
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 再執行一次", use_container_width=True):
            st.session_state.auto_fill_logs = []
            st.session_state.auto_fill_result = None
            st.session_state.auto_fill_progress = {
                "filled": 0,
                "swapped": 0,
                "failed": 0,
            }
            st.rerun()

    with col2:
        if len(results.get("remaining_gaps", [])) == 0:
            if st.button("➡️ 進入 Stage 3", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
        else:
            if st.button(
                "➡️ 接受並進入 Stage 3", type="secondary", use_container_width=True
            ):
                st.session_state.current_stage = 3
                st.rerun()


def render_execution_report_tab(swapper):
    """執行報告標籤頁"""
    st.markdown("### 📈 執行報告")

    try:
        report = swapper.get_detailed_report()

        # 總體統計
        st.markdown("#### 📊 總體統計")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("總格位", report["summary"]["total_slots"])
        with col2:
            st.metric("已填格位", report["summary"]["filled_slots"])
        with col3:
            st.metric("填充率", f"{report['summary']['fill_rate']:.1%}")
        with col4:
            st.metric("狀態歷史", report["state_history"])

        # 優化指標
        st.markdown("#### 🎯 優化指標")
        metrics = report["optimization_metrics"]

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("平均優先級", f"{metrics['average_priority']:.1f}")
        with col2:
            st.metric("最大機會成本", f"{metrics['max_opportunity_cost']:.1f}")
        with col3:
            st.metric("總未來影響", f"{metrics['total_future_impact']:.1f}")

        # 搜索統計（如果有）
        if "search_stats" in report and report["search_stats"]["chains_explored"] > 0:
            st.markdown("#### 🔍 搜索統計")
            stats = report["search_stats"]

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("探索路徑", f"{stats['chains_explored']:,}")
            with col2:
                st.metric("找到方案", stats["chains_found"])
            with col3:
                st.metric("搜索時間", f"{stats['search_time']:.2f} 秒")
            with col4:
                st.metric("最大深度", f"{stats['max_depth_reached']} 層")

        # 空缺分析
        st.markdown("#### 🔍 空缺分析")
        gap_analysis = report["gap_analysis"]

        gap_summary = pd.DataFrame(
            {
                "類型": ["🟢 簡單", "🟡 中等", "🔴 困難"],
                "數量": [
                    len(gap_analysis["easy"]),
                    len(gap_analysis["medium"]),
                    len(gap_analysis["hard"]),
                ],
                "說明": [
                    "有配額餘額，可直接填補",
                    "需要交換班次才能填補",
                    "無可用醫師，需要特殊處理",
                ],
            }
        )

        st.dataframe(gap_summary, use_container_width=True, hide_index=True)

        # 約束違規檢查
        st.markdown("#### ✅ 約束檢查")
        violations = swapper.validate_all_constraints()
        if violations:
            st.error("發現約束違規：")
            for violation in violations:
                st.warning(f"• {violation}")
        else:
            st.success("✅ 所有約束條件均已滿足")

        # 下載報告
        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            if st.button("📥 下載詳細報告", use_container_width=True):
                report_json = json.dumps(report, ensure_ascii=False, indent=2)
                st.download_button(
                    label="💾 下載 JSON 報告",
                    data=report_json,
                    file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )

        with col2:
            if st.button("📊 生成視覺化報告", use_container_width=True):
                st.info("視覺化報告功能開發中...")

    except Exception as e:
        st.error(f"無法生成報告: {str(e)}")
