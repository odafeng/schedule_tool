"""
Stage 2 元件（修正 CLI 主控台版本）
解決渲染問題和畫面跳閃
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from typing import List, Dict
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
import json
import threading
import queue
from math import inf


def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染新的 Stage 2: 進階智慧交換補洞系統"""
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
        render_auto_fill_tab_simplified(swapper)

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
                if "auto_fill_results" in st.session_state:
                    del st.session_state.auto_fill_results
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")


def render_stage2_status(swapper):
    """顯示 Stage 2 系統狀態"""
    try:
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
        - ⚠️ **橙色標籤**：需要調整才能安排的醫師（例如：配額已滿、連續值班限制）
        - 每個醫師會顯示具體的限制原因
        """
        )

    try:
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
    except Exception as e:
        st.error(f"無法顯示日曆: {str(e)}")

    # 顯示統計摘要
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
            st.metric("🟢 可直接填補", easy_gaps, help="有醫師配額餘額可直接安排")

        with col3:
            st.metric("🟡 需要調整", medium_gaps, help="醫師配額已滿，需要交換班次")

        with col4:
            st.metric("🔴 困難空缺", hard_gaps, help="沒有可用醫師")
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


def render_auto_fill_tab_simplified(swapper):
    """簡化版智慧填補標籤頁（使用炫酷的 Terminal 風格）"""
    st.markdown("### 🤖 智慧自動填補系統 v2.0")

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

    # 注入 Terminal 樣式
    st.markdown(
        """
        <style>
        .terminal-container {
            background: #0c1021;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 1rem;
            margin: 1rem 0;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }
        
        .terminal-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #30363d;
        }
        
        .terminal-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        
        .dot-red { background: #ff5f56; }
        .dot-yellow { background: #ffbd2e; }  
        .dot-green { background: #27c93f; }
        
        .terminal-title {
            color: #8b949e;
            font-size: 0.875rem;
            margin-left: auto;
            font-family: 'SF Mono', Monaco, monospace;
        }
        
        .terminal-log {
            background: #0d1117;
            color: #58a6ff;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            padding: 1rem;
            border-radius: 8px;
            height: 400px;
            overflow-y: auto;
            overflow-x: hidden;
            font-size: 13px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .terminal-log::-webkit-scrollbar {
            width: 8px;
        }
        
        .terminal-log::-webkit-scrollbar-track {
            background: #161b22;
            border-radius: 4px;
        }
        
        .terminal-log::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 4px;
        }
        
        .terminal-log::-webkit-scrollbar-thumb:hover {
            background: #484f58;
        }
        
        .log-entry {
            margin: 2px 0;
            padding: 2px 0;
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from { 
                opacity: 0;
                transform: translateY(-2px);
            }
            to { 
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .log-timestamp {
            color: #484f58;
            font-weight: 500;
        }
        
        .log-success { color: #3fb950; }
        .log-info { color: #58a6ff; }
        .log-warning { color: #d29922; }
        .log-error { color: #f85149; }
        .log-debug { color: #8b949e; }
        
        .terminal-stats {
            display: flex;
            gap: 1rem;
            margin-top: 0.5rem;
            padding: 0.5rem;
            background: #161b22;
            border-radius: 6px;
            font-size: 0.85rem;
            color: #8b949e;
            font-family: 'SF Mono', Monaco, monospace;
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .stat-label {
            color: #484f58;
        }
        
        .stat-value {
            color: #58a6ff;
            font-weight: 600;
        }
        
        .pulse-dot {
            width: 6px;
            height: 6px;
            background: #3fb950;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 初始化 session state
    if "auto_fill_running" not in st.session_state:
        st.session_state.auto_fill_running = False
    if "auto_fill_logs" not in st.session_state:
        st.session_state.auto_fill_logs = []
    if "auto_fill_start_time" not in st.session_state:
        st.session_state.auto_fill_start_time = None
    if "auto_fill_result" not in st.session_state:
        st.session_state.auto_fill_result = None
    if "auto_fill_progress" not in st.session_state:
        st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}

    # 控制按鈕
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if not st.session_state.auto_fill_running:
            if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
                # 清空之前的結果
                st.session_state.auto_fill_logs = []
                st.session_state.auto_fill_result = None
                st.session_state.auto_fill_start_time = time.time()
                st.session_state.auto_fill_running = True
                st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
                
                # 執行填補
                execute_auto_fill_with_terminal(swapper)
        else:
            st.info("🔄 正在執行智慧填補...")
    
    with col2:
        if st.button("🧹 清空日誌", use_container_width=True, 
                    disabled=st.session_state.auto_fill_running):
            st.session_state.auto_fill_logs = []
            st.session_state.auto_fill_result = None
            st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
            st.rerun()
    
    with col3:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # Terminal 風格的日誌顯示
    terminal_placeholder = st.empty()
    
    # 渲染 Terminal
    render_terminal_log(terminal_placeholder)
    
    # 顯示執行結果
    if st.session_state.auto_fill_result:
        st.divider()
        display_auto_fill_result(st.session_state.auto_fill_result)


def render_terminal_log(placeholder):
    """渲染 Terminal 風格的日誌"""
    logs = st.session_state.auto_fill_logs
    progress = st.session_state.auto_fill_progress
    is_running = st.session_state.auto_fill_running
    
    # 格式化日誌內容
    formatted_logs = []
    for log in logs[-100:]:  # 只顯示最後100行
        # 解析日誌格式 [timestamp] level: message
        if isinstance(log, dict):
            timestamp = log.get("timestamp", "")
            level = log.get("level", "INFO")
            message = log.get("message", "")
        else:
            # 如果是字符串，嘗試解析
            parts = str(log).split("] ", 1)
            if len(parts) == 2:
                timestamp = parts[0].replace("[", "")
                message = parts[1]
                # 判斷日誌級別
                if "成功" in message or "完成" in message:
                    level = "SUCCESS"
                elif "失敗" in message or "錯誤" in message:
                    level = "ERROR"
                elif "警告" in message or "注意" in message:
                    level = "WARNING"
                elif "調試" in message or "檢查" in message:
                    level = "DEBUG"
                else:
                    level = "INFO"
            else:
                timestamp = datetime.now().strftime("%H:%M:%S")
                message = str(log)
                level = "INFO"
        
        # 應用顏色
        level_class = f"log-{level.lower()}"
        formatted_logs.append(
            f'<div class="log-entry"><span class="log-timestamp">[{timestamp}]</span> <span class="{level_class}">{message}</span></div>'
        )
    
    # 計算運行時間
    if st.session_state.auto_fill_start_time:
        elapsed = time.time() - st.session_state.auto_fill_start_time
        elapsed_str = f"{elapsed:.1f}s"
    else:
        elapsed_str = "0.0s"
    
    # 生成 HTML
    terminal_html = f'''
    <div class="terminal-container">
        <div class="terminal-header">
            <div class="terminal-dot dot-red"></div>
            <div class="terminal-dot dot-yellow"></div>
            <div class="terminal-dot dot-green"></div>
            <div class="terminal-title">Stage 2 Auto-Fill Console</div>
        </div>
        
        <div class="terminal-log" id="terminal-log-content">
            {"".join(formatted_logs) if formatted_logs else '<div class="log-entry log-debug">等待執行...</div>'}
        </div>
        
        <div class="terminal-stats">
            <div class="stat-item">
                {f'<div class="pulse-dot"></div>' if is_running else ''}
                <span class="stat-label">狀態:</span>
                <span class="stat-value">{"執行中" if is_running else "就緒"}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">耗時:</span>
                <span class="stat-value">{elapsed_str}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">直接填補:</span>
                <span class="stat-value">{progress["filled"]}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">交換解決:</span>
                <span class="stat-value">{progress["swapped"]}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">失敗:</span>
                <span class="stat-value">{progress["failed"]}</span>
            </div>
        </div>
    </div>
    
    <script>
        // 自動滾動到底部
        (function() {{
            var terminal = document.getElementById('terminal-log-content');
            if(terminal) {{
                terminal.scrollTop = terminal.scrollHeight;
            }}
        }})();
    </script>
    '''
    
    # 使用 st.markdown 並確保 unsafe_allow_html=True
    with placeholder.container():
        st.markdown(terminal_html, unsafe_allow_html=True)


def execute_auto_fill_with_terminal(swapper):
    """執行自動填補並更新 Terminal"""
    max_backtracks = 20000
    
    # 定義日誌回調函數
    def terminal_log_callback(message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 添加到日誌
        log_entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message
        }
        st.session_state.auto_fill_logs.append(log_entry)
        
        # 更新進度統計
        if "直接填補成功" in message:
            st.session_state.auto_fill_progress["filled"] += 1
        elif "交換鏈執行成功" in message:
            st.session_state.auto_fill_progress["swapped"] += 1
        elif "無法解決" in message:
            st.session_state.auto_fill_progress["failed"] += 1
    
    # 設置日誌回調
    swapper.set_log_callback(terminal_log_callback)
    
    try:
        # 添加開始日誌
        terminal_log_callback("🚀 開始執行智慧自動填補", "INFO")
        terminal_log_callback(f"設定最大回溯次數: {max_backtracks:,}", "INFO")
        
        # 執行自動填補
        results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        
        # 計算總耗時
        elapsed_time = time.time() - st.session_state.auto_fill_start_time
        results["elapsed_time"] = elapsed_time
        
        # 添加搜索統計
        if swapper.search_stats:
            results["paths_explored"] = swapper.search_stats.get("chains_explored", 0)
        
        # 儲存結果
        st.session_state.auto_fill_result = results
        st.session_state.stage2_schedule = swapper.schedule
        
        # 添加完成日誌
        if results["remaining_gaps"]:
            terminal_log_callback(
                f"⚠️ 執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決",
                "WARNING"
            )
        else:
            terminal_log_callback("✅ 完美執行！所有空缺已填補", "SUCCESS")
        
        terminal_log_callback(f"總耗時: {elapsed_time:.2f} 秒", "INFO")
        
    except Exception as e:
        terminal_log_callback(f"❌ 執行失敗：{str(e)}", "ERROR")
    finally:
        st.session_state.auto_fill_running = False
        # 重新載入頁面以更新顯示
        time.sleep(1)
        st.rerun()


def execute_auto_fill_sync(swapper):
    """同步執行自動填補（避免線程問題）"""
    max_backtracks = 20000
    
    # 定義日誌回調函數
    def log_callback(message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        st.session_state.auto_fill_logs.append(log_entry)
    
    # 設置日誌回調
    swapper.set_log_callback(log_callback)
    
    try:
        # 顯示進度條
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 開始執行
        status_text.text("正在執行智慧填補...")
        
        # 執行自動填補
        results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        
        # 計算總耗時
        elapsed_time = time.time() - st.session_state.auto_fill_start_time
        results["elapsed_time"] = elapsed_time
        
        # 添加搜索統計
        if swapper.search_stats:
            results["paths_explored"] = swapper.search_stats.get("chains_explored", 0)
        
        # 儲存結果
        st.session_state.auto_fill_result = results
        st.session_state.stage2_schedule = swapper.schedule
        
        # 更新進度
        progress_bar.progress(100)
        
        # 顯示完成訊息
        if results["remaining_gaps"]:
            status_text.warning(
                f"⚠️ 執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決"
            )
        else:
            status_text.success("🎉 完美執行！所有空缺已填補")
        
    except Exception as e:
        st.error(f"❌ 執行失敗：{str(e)}")
    finally:
        st.session_state.auto_fill_running = False
        # 重新載入頁面以更新顯示
        time.sleep(1)
        st.rerun()


def display_auto_fill_result(results):
    """顯示自動填補結果"""
    st.markdown("### 📊 執行結果")
    
    # 顯示執行統計
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("⏱️ 總耗時", f"{results.get('elapsed_time', 0):.2f} 秒")
    
    with col2:
        st.metric("✅ 直接填補", len(results.get('direct_fills', [])))
    
    with col3:
        st.metric("🔄 交換解決", len(results.get('swap_chains', [])))
    
    with col4:
        st.metric("❌ 剩餘空缺", len(results.get('remaining_gaps', [])))
    
    # 顯示剩餘空缺詳情
    if results.get("remaining_gaps"):
        with st.expander("❌ 無法解決的空缺", expanded=True):
            for gap in results["remaining_gaps"]:
                st.write(f"- {gap['date']} {gap['role']}: {gap.get('reason', '無原因資訊')}")
        
        st.info("💡 建議：可以嘗試調整醫師配額後重試，或手動處理剩餘空缺")
    
    # 顯示交換鏈詳情（如果有）
    if results.get("swap_chains"):
        with st.expander(
            f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)", expanded=False
        ):
            for i, swap_info in enumerate(results["swap_chains"]):
                st.write(f"**交換 {i+1}**: {swap_info.get('gap', 'N/A')}")
                if "chain" in swap_info:
                    for step in swap_info["chain"]:
                        st.write(f"  - {step}")
    
    # 操作按鈕
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 再執行一次", use_container_width=True):
            st.session_state.auto_fill_logs = []
            st.session_state.auto_fill_result = None
            st.rerun()
    
    with col2:
        if len(results.get('remaining_gaps', [])) == 0:
            if st.button("➡️ 進入 Stage 3", type="primary", use_container_width=True):
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
            report_json = json.dumps(report, ensure_ascii=False, indent=2)
            st.download_button(
                label="💾 下載 JSON 報告",
                data=report_json,
                file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )
    except Exception as e:
        st.error(f"無法生成報告: {str(e)}")