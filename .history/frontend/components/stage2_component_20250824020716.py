"""
Stage 2 元件（修正版）
避免回調函數中的 UI 更新問題
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
        render_auto_fill_tab_safe(swapper)

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


def render_auto_fill_tab_safe(swapper):
    """智慧填補標籤頁（內建 CLI 即時主控台）"""
    st.markdown("### 🤖 智慧自動填補系統 v2.0（即時主控台）")

    # ---------- CLI 風格樣式 ----------
    st.markdown(
        """
    <style>
      .cli-box{
          background:#0b1020; color:#e6edf3; font-family:ui-monospace,Menlo,Consolas,monospace;
          border:1px solid #263143; border-radius:12px; padding:14px; height:360px; overflow:auto;
          box-shadow: 0 10px 30px rgba(0,0,0,.25);
      }
      .cli-header{display:flex; gap:12px; align-items:center; margin-bottom:10px}
      .dot{width:10px;height:10px;border-radius:50%}
      .red{background:#ff5f56}.yellow{background:#ffbd2e}.green{background:#27c93f}
      .muted{color:#9fb0c5}
      .stat-pill{background:#111931;border:1px solid #1e2a44;border-radius:10px;padding:6px 10px;margin-right:8px}
    </style>
    """,
        unsafe_allow_html=True,
    )

    # ---------- 取得目前空缺概況 ----------
    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return

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

    # ---------- Session State ----------
    ss = st.session_state
    ss.setdefault("cli_running", False)
    ss.setdefault("cli_logs", [])
    ss.setdefault("cli_queue", queue.Queue())
    ss.setdefault("cli_start_time", None)
    ss.setdefault("cli_initial_gaps", None)
    ss.setdefault("cli_result", None)  # 保存 run 結果
    ss.setdefault("execution_logs", [])  # 兼容舊欄位（結果頁 expander 使用）

    # ---------- 控制列 ----------
    top_c1, top_c2, top_c3 = st.columns([1, 1, 2])
    with top_c1:
        start_btn = st.button(
            "🚀 開始智慧填補（即時）",
            type="primary",
            use_container_width=True,
            disabled=ss.cli_running,
        )
    with top_c2:
        reset_btn = st.button(
            "🧹 清空主控台", use_container_width=True, disabled=ss.cli_running
        )

    if reset_btn and not ss.cli_running:
        ss.cli_logs = []
        ss.cli_result = None
        ss.execution_logs = []
        st.toast("主控台已清空")

    # ---------- 佈局 ----------
    header_ph = st.empty()
    stat_ph = st.empty()
    cli_ph = st.empty()
    st.divider()

    # ---------- 內部工具 ----------
    def _drain_queue_to_logs():
        """把背景回呼丟進 queue 的訊息撈到 ss.cli_logs。"""
        q = ss.cli_queue
        while True:
            try:
                msg = q.get_nowait()
                ss.cli_logs.append(msg)
            except queue.Empty:
                break

    def _log_cb(message: str, level: str = "info"):
        """回呼：只入列，不直接動 UI。"""
        ts = datetime.now().strftime("%H:%M:%S")
        ss.cli_queue.put(f"[{ts}] {message}")

    def _worker(max_backtracks: int):
        """背景執行演算法；完成後寫回狀態。"""
        try:
            swapper.set_log_callback(_log_cb)
            result = swapper.run_auto_fill_with_backtracking(
                max_backtracks=max_backtracks
            )
            # 保存結果與最新 schedule
            ss.cli_result = result
            ss.execution_logs = ss.cli_logs[:]  # 讓結果頁 expander 也能看到完整日誌
            ss.stage2_schedule = swapper.schedule
        finally:
            ss.cli_running = False

    # ---------- 啟動執行 ----------
    MAX_BACKTRACKS = 20000
    if start_btn and not ss.cli_running:
        ss.cli_logs = []
        ss.cli_result = None
        ss.cli_start_time = time.time()
        ss.cli_initial_gaps = report["summary"]["unfilled_slots"]
        ss.cli_running = True

        t = threading.Thread(
            target=_worker, kwargs={"max_backtracks": MAX_BACKTRACKS}, daemon=True
        )
        t.start()
        # 立即 rerun 進入即時畫面
        st.experimental_rerun()

    # ---------- 即時畫面（每次 render 都刷新一次） ----------
    # 先把新訊息撈出
    _drain_queue_to_logs()

    # 計算指標
    cur_report = swapper.get_detailed_report()
    remaining = cur_report["summary"]["unfilled_slots"]
    initial = ss.cli_initial_gaps if ss.cli_initial_gaps is not None else remaining
    solved = max(0, initial - remaining)
    elapsed = (time.time() - ss.cli_start_time) if ss.cli_start_time else 0.0
    eta_sec = inf
    if solved > 0:
        sec_per_gap = elapsed / solved
        eta_sec = remaining * sec_per_gap

    # 標頭與指標列
    header_ph.markdown(
        """
        <div class="cli-header">
            <div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div>
            <div class="muted">Stage 2 Streaming Console</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    stat_ph.markdown(
        f"""
        <div>
            <span class="stat-pill">⏱ 已用時間：{elapsed:.1f}s</span>
            <span class="stat-pill">⌛ 估計完成：{('∞' if eta_sec==inf else f'{eta_sec:.1f}s')}</span>
            <span class="stat-pill">🧩 剩餘空缺：{remaining}</span>
            <span class="stat-pill">✅ 已解決：{solved}/{initial}</span>
            <span class="stat-pill">↩️ 最大回溯：{MAX_BACKTRACKS:,}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # CLI 內容
    last_400 = ss.cli_logs[-400:]  # 避免超長
    cli_html = "<div class='cli-box'><pre>" + "\n".join(last_400) + "</pre></div>"
    cli_ph.markdown(cli_html, unsafe_allow_html=True)

    # ---------- 結束後顯示摘要 / 行為 ----------
    if not ss.cli_running and ss.cli_result is not None:
        res = ss.cli_result

        st.success("執行完成")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(
                "⏱️ 總耗時",
                f"{(time.time()-ss.cli_start_time):.2f}s" if ss.cli_start_time else "—",
            )
        with c2:
            st.metric("直接填補", len(res.get("direct_fills", [])))
        with c3:
            st.metric("交換解決", len(res.get("swap_chains", [])))
        with c4:
            st.metric("剩餘空缺", len(res.get("remaining_gaps", [])))

        if res.get("remaining_gaps"):
            with st.expander("❌ 無法解決的空缺（點開檢視）", expanded=False):
                for g in res["remaining_gaps"]:
                    st.write(
                        f"- {g['date']} {g['role']} → {g.get('reason', '無原因資訊')}"
                    )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("🔁 再跑一次（清空主控台）", use_container_width=True):
                ss.cli_logs = []
                ss.cli_result = None
                ss.execution_logs = []
                st.experimental_rerun()
        with b2:
            if st.button(
                "➡️ 接受並進入 Stage 3", type="primary", use_container_width=True
            ):
                ss.current_stage = 3
                st.experimental_rerun()

    # ---------- 若仍在執行：小延遲後自動刷新 ----------
    from streamlit_autorefresh import st_autorefresh
    if ss.cli_running:
        st_autorefresh(interval=500, key="stage2_cli_refresh")


def execute_auto_fill_safe(swapper, report):
    """執行自動填補（安全版本 - 不使用回調）"""
    max_backtracks = 20000

    # 創建一個簡單的日誌收集器
    logs = []

    # 定義一個簡單的日誌函數（只收集，不更新 UI）
    def simple_log_callback(message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{timestamp}] {message}")

    # 暫時設定日誌回調
    original_callback = swapper.log_callback
    swapper.set_log_callback(simple_log_callback)

    # 開始時間
    start_time = time.time()

    # 顯示執行中狀態
    with st.spinner(f"🔄 正在執行智慧填補... (最多 {max_backtracks:,} 次回溯)"):
        try:
            # 執行自動填補
            results = swapper.run_auto_fill_with_backtracking(max_backtracks)

            # 計算總耗時
            elapsed_time = time.time() - start_time
            results["elapsed_time"] = elapsed_time

            # 添加搜索統計
            if swapper.search_stats:
                results["paths_explored"] = swapper.search_stats.get(
                    "chains_explored", 0
                )

            # 儲存結果
            st.session_state.execution_logs = logs
            st.session_state.stage2_schedule = swapper.schedule
            st.session_state.auto_fill_results = results

            # 顯示完成訊息
            if results["remaining_gaps"]:
                st.warning(
                    f"⚠️ 執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決"
                )
            else:
                st.success("🎉 完美執行！所有空缺已填補")

            # 恢復原始回調
            swapper.log_callback = original_callback

            # 重新載入頁面
            time.sleep(1)
            st.rerun()

        except Exception as e:
            # 恢復原始回調
            swapper.log_callback = original_callback
            st.error(f"❌ 執行失敗：{str(e)}")


def display_results(results):
    """顯示執行結果"""
    # 顯示執行結果
    col1, col2 = st.columns([2, 1])

    with col1:
        if results.get("remaining_gaps"):
            st.warning(
                f"""
            ⚠️ **執行完成（部分成功）**
            - ✅ 直接填補：{len(results.get('direct_fills', []))} 個
            - 🔄 交換解決：{len(results.get('swap_chains', []))} 個
            - ↩️ 回溯次數：{len(results.get('backtracks', []))}
            - ❌ 剩餘空缺：{len(results.get('remaining_gaps', []))} 個
            """
            )
        else:
            st.success(
                f"""
            ✅ **完美執行！所有空缺已填補**
            - 直接填補：{len(results.get('direct_fills', []))} 個
            - 交換解決：{len(results.get('swap_chains', []))} 個
            - 回溯次數：{len(results.get('backtracks', []))}
            """
            )

    with col2:
        st.metric("⏱️ 總耗時", f"{results.get('elapsed_time', 0):.2f} 秒")
        st.metric("🔍 探索路徑", f"{results.get('paths_explored', 0):,}")

    # 顯示剩餘空缺詳情
    if results.get("remaining_gaps"):
        with st.expander("❌ 無法解決的空缺", expanded=True):
            for gap in results["remaining_gaps"]:
                st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")

        st.info("💡 建議：可以嘗試調整醫師配額後重試，或手動處理剩餘空缺")

    # 顯示交換鏈詳情（如果有）
    if results.get("swap_chains"):
        with st.expander(
            f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)", expanded=False
        ):
            for i, swap_info in enumerate(results["swap_chains"]):
                st.write(f"**交換 {i+1}**: {swap_info['gap']}")
                for step in swap_info["chain"]:
                    st.write(f"  - {step}")

    # 顯示執行日誌
    if st.session_state.execution_logs:
        with st.expander("📜 執行日誌", expanded=False):
            # 限制顯示的日誌行數
            log_text = "\n".join(st.session_state.execution_logs[-50:])
            st.code(log_text, language="")


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
