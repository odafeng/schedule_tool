"""
Stage 2 元件（修正版 - 確保狀態正確同步）
穩定的 Terminal 效果，避免 HTML 渲染問題
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from typing import List, Dict
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper
import json


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
        render_auto_fill_tab_native(swapper)

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
                # 同步更新 session state
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
                    # 重要：同步更新 session state
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


def render_auto_fill_tab_native(swapper):
    """使用 Streamlit 原生組件實現 Terminal 效果"""
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
    if "auto_fill_should_run" not in st.session_state:
        st.session_state.auto_fill_should_run = False

    # 控制按鈕
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if not st.session_state.auto_fill_running and not st.session_state.auto_fill_should_run:
            if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
                st.session_state.auto_fill_logs = []
                st.session_state.auto_fill_result = None
                st.session_state.auto_fill_start_time = time.time()
                st.session_state.auto_fill_should_run = True
                st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
                st.rerun()
        else:
            st.button("⏸️ 執行中...", disabled=True, use_container_width=True)
    
    with col2:
        if st.button("🧹 清空日誌", use_container_width=True, 
                    disabled=st.session_state.auto_fill_running):
            st.session_state.auto_fill_logs = []
            st.session_state.auto_fill_result = None
            st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
            st.session_state.auto_fill_should_run = False
            st.rerun()
    
    with col3:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()
    
    # 執行自動填補（如果需要）
    if st.session_state.auto_fill_should_run and not st.session_state.auto_fill_running:
        st.session_state.auto_fill_running = True
        st.session_state.auto_fill_should_run = False
        execute_auto_fill_simple(swapper)

    # Terminal 容器
    st.markdown("#### 📟 執行終端")
    
    # 創建一個深色背景的容器
    with st.container():
        # 狀態欄
        if st.session_state.auto_fill_running or st.session_state.auto_fill_logs:
            progress = st.session_state.auto_fill_progress
            elapsed = 0
            if st.session_state.auto_fill_start_time:
                elapsed = time.time() - st.session_state.auto_fill_start_time
            
            # 使用 columns 顯示即時統計
            stat_cols = st.columns(5)
            with stat_cols[0]:
                if st.session_state.auto_fill_running:
                    st.info(f"🟢 執行中")
                else:
                    st.success(f"✅ 完成")
            with stat_cols[1]:
                st.metric("耗時", f"{elapsed:.1f}s", label_visibility="visible")
            with stat_cols[2]:
                st.metric("直接填補", progress["filled"], label_visibility="visible")
            with stat_cols[3]:
                st.metric("交換解決", progress["swapped"], label_visibility="visible")
            with stat_cols[4]:
                st.metric("失敗", progress["failed"], label_visibility="visible")
        
        # 日誌顯示區域
        if st.session_state.auto_fill_logs:
            # 使用 container 來顯示日誌
            log_container = st.container()
            with log_container:
                # 使用 code block 顯示日誌（深色背景）
                log_lines = []
                for log in st.session_state.auto_fill_logs[-100:]:  # 最後100行
                    if isinstance(log, dict):
                        timestamp = log.get("timestamp", "")
                        level = log.get("level", "INFO")
                        message = log.get("message", "")
                        
                        # 添加 emoji 標記不同級別
                        level_icons = {
                            "SUCCESS": "✅",
                            "ERROR": "❌",
                            "WARNING": "⚠️",
                            "INFO": "ℹ️",
                            "DEBUG": "🔍"
                        }
                        icon = level_icons.get(level, "▶")
                        log_lines.append(f"[{timestamp}] {icon} {message}")
                    else:
                        log_lines.append(str(log))
                
                # 使用 text_area 顯示（可以滾動）
                st.text_area(
                    "執行日誌",
                    value="\n".join(log_lines),
                    height=400,
                    disabled=True,
                    label_visibility="collapsed"
                )
        else:
            # 顯示空的日誌區域
            st.info("💤 等待執行...")
    
    # 顯示執行結果
    if st.session_state.auto_fill_result:
        st.divider()
        display_execution_result(st.session_state.auto_fill_result)


def execute_auto_fill_simple(swapper):
    """簡化版執行自動填補 - 加強版本，顯示詳細搜索過程"""
    max_backtracks = 20000
    
    # 創建進度容器
    progress_container = st.container()
    with progress_container:
        progress_bar = st.progress(0)
        status_text = st.empty()
        metrics_placeholder = st.empty()
        
    # 初始化詳細統計
    search_metrics = {
        "gaps_processed": 0,
        "direct_fills_attempted": 0,
        "swap_searches_initiated": 0,
        "chains_explored": 0,
        "backtracks": 0,
        "depth_reached": 0,
        "constraints_checked": 0
    }
    
    # 定義增強版日誌回調函數
    def enhanced_log_callback(message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # 包含毫秒
        log_entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message
        }
        st.session_state.auto_fill_logs.append(log_entry)
        
        # 更新詳細統計
        if "處理空缺" in message:
            search_metrics["gaps_processed"] += 1
        elif "嘗試直接填補" in message:
            search_metrics["direct_fills_attempted"] += 1
        elif "開始搜索交換鏈" in message:
            search_metrics["swap_searches_initiated"] += 1
        elif "探索交換路徑" in message:
            search_metrics["chains_explored"] += 1
        elif "回溯" in message:
            search_metrics["backtracks"] += 1
            # 提取回溯次數
            import re
            match = re.search(r'第 (\d+) 次', message)
            if match:
                backtrack_count = int(match.group(1))
                # 更新進度條（基於回溯次數）
                progress = min(10 + (backtrack_count / max_backtracks) * 80, 90)
                progress_bar.progress(int(progress))
        elif "檢查約束" in message:
            search_metrics["constraints_checked"] += 1
        elif "深度" in message:
            import re
            match = re.search(r'深度[：:]\s*(\d+)', message)
            if match:
                depth = int(match.group(1))
                search_metrics["depth_reached"] = max(search_metrics["depth_reached"], depth)
        
        # 更新進度統計
        if "直接填補成功" in message:
            st.session_state.auto_fill_progress["filled"] += 1
            enhanced_log_callback(f"✅ 成功填補 1 個空缺", "SUCCESS")
        elif "交換鏈執行成功" in message:
            st.session_state.auto_fill_progress["swapped"] += 1
            enhanced_log_callback(f"🔄 成功執行 1 個交換鏈", "SUCCESS")
        elif "無法解決" in message:
            st.session_state.auto_fill_progress["failed"] += 1
            enhanced_log_callback(f"❌ 1 個空缺無法解決", "WARNING")
        
        # 定期更新顯示的指標
        if search_metrics["gaps_processed"] % 5 == 0 or "回溯" in message:
            with metrics_placeholder.container():
                cols = st.columns(4)
                with cols[0]:
                    st.metric("處理空缺", search_metrics["gaps_processed"])
                with cols[1]:
                    st.metric("探索路徑", search_metrics["chains_explored"])
                with cols[2]:
                    st.metric("回溯次數", search_metrics["backtracks"])
                with cols[3]:
                    st.metric("最大深度", search_metrics["depth_reached"])
    
    # 設置增強版日誌回調
    swapper.set_log_callback(enhanced_log_callback)
    
    # 設置更詳細的搜索參數
    swapper.search_config = {
        "max_depth": 10,  # 增加搜索深度
        "beam_width": 5,  # 束搜索寬度
        "timeout": 60,    # 超時時間（秒）
        "verbose": True   # 詳細輸出
    }
    
    try:
        status_text.text("🚀 開始執行智慧自動填補...")
        enhanced_log_callback("="*50, "INFO")
        enhanced_log_callback("開始執行智慧自動填補系統", "INFO")
        enhanced_log_callback(f"演算法配置:", "INFO")
        enhanced_log_callback(f"  - 最大回溯次數: {max_backtracks:,}", "INFO")
        enhanced_log_callback(f"  - 搜索深度: {swapper.search_config.get('max_depth', 5)}", "INFO")
        enhanced_log_callback(f"  - 束寬度: {swapper.search_config.get('beam_width', 3)}", "INFO")
        enhanced_log_callback("="*50, "INFO")
        
        # 詳細分析初始狀態
        enhanced_log_callback(f"初始狀態分析:", "INFO")
        enhanced_log_callback(f"  - 總空缺數: {len(swapper.gaps)}", "INFO")
        
        # 分析空缺難度
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium_gaps = len([g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota])
        hard_gaps = len([g for g in swapper.gaps if not g.candidates_with_quota and not g.candidates_over_quota])
        
        enhanced_log_callback(f"  - 簡單空缺: {easy_gaps} (有配額餘額)", "INFO")
        enhanced_log_callback(f"  - 中等空缺: {medium_gaps} (需要交換)", "INFO")
        enhanced_log_callback(f"  - 困難空缺: {hard_gaps} (無可用醫師)", "INFO")
        enhanced_log_callback("="*50, "INFO")
        
        progress_bar.progress(10)
        status_text.text("🔍 深度分析空缺中...")
        
        # 開始計時
        start_time = time.time()
        
        # 執行自動填補（這裡應該會產生大量日誌）
        enhanced_log_callback("開始執行自動填補演算法...", "INFO")
        results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        
        # 計算詳細耗時
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        progress_bar.progress(90)
        status_text.text("📊 分析執行結果...")
        
        # 詳細的結果分析
        enhanced_log_callback("="*50, "INFO")
        enhanced_log_callback("執行結果分析:", "INFO")
        enhanced_log_callback(f"  - 總耗時: {elapsed_time:.3f} 秒", "INFO")
        enhanced_log_callback(f"  - 平均每次回溯: {(elapsed_time/max(search_metrics['backtracks'], 1)*1000):.2f} 毫秒", "INFO")
        enhanced_log_callback(f"  - 直接填補: {len(results.get('direct_fills', []))} 個", "INFO")
        enhanced_log_callback(f"  - 交換解決: {len(results.get('swap_chains', []))} 個", "INFO")
        enhanced_log_callback(f"  - 剩餘空缺: {len(results.get('remaining_gaps', []))} 個", "INFO")
        
        # 如果回溯次數太少，發出警告
        if search_metrics["backtracks"] < 100 and len(results.get('remaining_gaps', [])) > 0:
            enhanced_log_callback("⚠️ 警告：回溯次數較少，可能未充分探索解空間", "WARNING")
            enhanced_log_callback(f"  實際回溯: {search_metrics['backtracks']} 次", "WARNING")
            enhanced_log_callback(f"  建議增加搜索深度或調整演算法參數", "WARNING")
        
        # 添加搜索統計
        results["elapsed_time"] = elapsed_time
        results["search_metrics"] = search_metrics
        
        if swapper.search_stats:
            results["paths_explored"] = swapper.search_stats.get("chains_explored", 0)
            enhanced_log_callback(f"  - 總探索路徑: {results['paths_explored']:,}", "INFO")
        
        enhanced_log_callback("="*50, "INFO")
        
        # 重要：同步更新 schedule 到 session state
        st.session_state.stage2_schedule = swapper.schedule
        
        # 儲存結果
        st.session_state.auto_fill_result = results
        
        # 最終狀態
        if results["remaining_gaps"]:
            enhanced_log_callback(
                f"執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決",
                "WARNING"
            )
            status_text.warning(f"⚠️ 完成！還有 {len(results['remaining_gaps'])} 個空缺未解決")
            
            # 分析未解決的原因
            enhanced_log_callback("未解決空缺分析:", "WARNING")
            for i, gap in enumerate(results["remaining_gaps"][:5], 1):  # 只顯示前5個
                enhanced_log_callback(f"  {i}. {gap.get('date', 'N/A')} - {gap.get('reason', '未知原因')}", "WARNING")
        else:
            enhanced_log_callback("完美執行！所有空缺已填補", "SUCCESS")
            status_text.success("✅ 完美執行！所有空缺已填補")
        
        progress_bar.progress(100)
        
    except Exception as e:
        enhanced_log_callback(f"執行失敗：{str(e)}", "ERROR")
        status_text.error(f"❌ 執行失敗：{str(e)}")
        
        # 顯示錯誤詳情
        import traceback
        enhanced_log_callback("錯誤詳情:", "ERROR")
        for line in traceback.format_exc().split('\n'):
            if line.strip():
                enhanced_log_callback(f"  {line}", "ERROR")
    finally:
        st.session_state.auto_fill_running = False
        # 延遲後重新載入
        time.sleep(2)
        st.rerun()


def display_execution_result(results):
    """顯示執行結果"""
    st.markdown("### 📊 執行結果")
    
    # 結果統計
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("⏱️ 總耗時", f"{results.get('elapsed_time', 0):.2f} 秒")
    
    with col2:
        st.metric("✅ 直接填補", len(results.get('direct_fills', [])))
    
    with col3:
        st.metric("🔄 交換解決", len(results.get('swap_chains', [])))
    
    with col4:
        st.metric("❌ 剩餘空缺", len(results.get('remaining_gaps', [])))
    
    # 詳細資訊
    if results.get("remaining_gaps"):
        with st.expander("❌ 無法解決的空缺", expanded=True):
            gap_data = []
            for gap in results["remaining_gaps"]:
                gap_data.append({
                    "日期": gap.get('date', 'N/A'),
                    "角色": gap.get('role', 'N/A'),
                    "原因": gap.get('reason', '無原因資訊')
                })
            
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
            st.session_state.auto_fill_progress = {"filled": 0, "swapped": 0, "failed": 0}
            st.rerun()
    
    with col2:
        if len(results.get('remaining_gaps', [])) == 0:
            if st.button("➡️ 進入 Stage 3", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
        else:
            if st.button("➡️ 接受並進入 Stage 3", type="secondary", use_container_width=True):
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
        
        # 創建空缺分析 DataFrame
        gap_summary = pd.DataFrame({
            "類型": ["🟢 簡單", "🟡 中等", "🔴 困難"],
            "數量": [
                len(gap_analysis["easy"]),
                len(gap_analysis["medium"]),
                len(gap_analysis["hard"])
            ],
            "說明": [
                "有配額餘額，可直接填補",
                "需要交換班次才能填補",
                "無可用醫師，需要特殊處理"
            ]
        })
        
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