"""
Stage 2 元件（穩定版）
- 背景執行緒只寫 queue，不觸碰 UI
- 使用 st_autorefresh 拉式刷新，避免 WebSocketClosedError 連環報
- 統一使用 st.rerun()
"""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime
from math import inf
from typing import Dict, List

import pandas as pd
import streamlit as st
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper

# 綁定 Script Run Context（不同版本的 Streamlit 模組路徑略有差異）
try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx  # >= 1.28
except Exception:  # pragma: no cover
    try:
        # 舊版 fallback
        from streamlit.scriptrunner.script_run_context import (
            add_script_run_ctx,  # type: ignore
        )
    except Exception:
        add_script_run_ctx = None  # 沒有也能跑，只是少了自動清理能力

# 拉式刷新（安裝：pip install streamlit-autorefresh）
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None  # 若沒裝，就退回輕量 rerun 策略（最後面有保底）


# =============================
# Public Entrypoint
# =============================
def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染 Stage 2：進階智慧交換補洞系統"""
    st.subheader("🔧 Stage 2: 進階智慧交換補洞系統")

    if not st.session_state.get("stage2_schedule"):
        st.error("請先完成 Stage 1")
        return

    # 初始化或取得 Stage 2 Swapper
    if st.session_state.get("stage2_swapper") is None:
        with st.spinner("正在初始化 Stage 2 系統..."):
            try:
                st.session_state.stage2_swapper = Stage2AdvancedSwapper(
                    schedule=st.session_state.stage2_schedule,
                    doctors=st.session_state.doctors,
                    constraints=st.session_state.constraints,
                    weekdays=weekdays,
                    holidays=holidays,
                )
                # 清空上一輪自動填補的結果（若存在）
                for k in ("auto_fill_results", "execution_logs"):
                    if k in st.session_state:
                        del st.session_state[k]
            except Exception as e:
                st.error(f"初始化失敗：{e}")
                return

    swapper = st.session_state.stage2_swapper

    # 狀態列
    _render_stage2_status(swapper)

    # 三個主頁籤
    tab1, tab2, tab3 = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📈 執行報告"])
    with tab1:
        _render_calendar_view_tab(swapper, weekdays, holidays)
    with tab2:
        _render_auto_fill_tab_safe(swapper)
    with tab3:
        _render_execution_report_tab(swapper)

    # 流程導引
    st.divider()
    try:
        report = swapper.get_detailed_report()
        unfilled = report["summary"]["unfilled_slots"]
        if unfilled == 0:
            st.success("🎉 所有空缺已成功填補！")
            if st.button("➡️ 進入 Stage 3：確認與發佈", type="primary", use_container_width=True):
                for k in ("auto_fill_results", "execution_logs"):
                    if k in st.session_state:
                        del st.session_state[k]
                st.session_state.current_stage = 3
                st.rerun()
        elif unfilled <= 2:
            st.warning(f"⚠️ 還有 {unfilled} 個空缺未填補")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 繼續嘗試", use_container_width=True):
                    for k in ("auto_fill_results", "execution_logs"):
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()
            with c2:
                if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                    for k in ("auto_fill_results", "execution_logs"):
                        if k in st.session_state:
                            del st.session_state[k]
                    st.session_state.current_stage = 3
                    st.rerun()
        else:
            st.error(f"❌ 還有 {unfilled} 個空缺需要處理")
    except Exception as e:
        st.error(f"無法判定目前狀態：{e}")


# =============================
# Status Bar
# =============================
def _render_stage2_status(swapper):
    """顯示 Stage 2 系統狀態（健壯處理）"""
    try:
        report = swapper.get_detailed_report()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "填充率",
                f"{report['summary']['fill_rate']:.1%}",
                delta=f"{report['summary']['filled_slots']}/{report['summary']['total_slots']}",
            )
        with col2:
            st.metric("剩餘空缺", report["summary"]["unfilled_slots"])
        with col3:
            st.metric("已應用交換", report.get("applied_swaps", 0))
        with col4:
            st.metric(
                "狀態",
                "✅ 完成" if report["summary"]["unfilled_slots"] == 0 else "🔄 進行中",
            )
    except Exception as e:
        st.error(f"無法取得狀態：{e}")


# =============================
# Calendar Tab
# =============================
def _render_calendar_view_tab(swapper, weekdays: list, holidays: list):
    st.markdown("### 📅 互動式月曆檢視")

    with st.expander("📖 使用說明", expanded=False):
        st.info(
            "- 🖱️ 滑鼠懸浮空缺格檢視候選醫師\n"
            "- 🟢 有配額可直接安排；🟡 需交換；🔴 無可用\n"
            "- 候選名單會附上原因說明"
        )

    # 月曆
    try:
        from frontend.components.calendar_view import render_calendar_view

        year = st.session_state.selected_year
        month = st.session_state.selected_month
        gap_details = swapper.get_gap_details_for_calendar()

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
        st.error(f"無法顯示日曆：{e}")

    # 摘要
    st.divider()
    st.markdown("### 📊 空缺統計摘要")
    try:
        total = len(swapper.gaps)
        easy = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium = len(
            [g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota]
        )
        hard = total - easy - medium
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("總空缺數", total)
        with c2:
            st.metric("🟢 可直接填補", easy)
        with c3:
            st.metric("🟡 需要調整", medium)
        with c4:
            st.metric("🔴 困難空缺", hard)
    except Exception as e:
        st.error(f"無法顯示統計：{e}")

    # 快速操作
    st.divider()
    st.markdown("### ⚡ 快速操作")
    q1, q2, q3 = st.columns(3)
    with q1:
        if st.button("🔄 重新分析空缺", use_container_width=True):
            with st.spinner("正在重新分析..."):
                swapper.gaps = swapper._analyze_gaps_advanced()
            st.success("✅ 空缺分析已更新")
            st.rerun()
    with q2:
        easy_gaps = [g for g in swapper.gaps if g.candidates_with_quota]
        if easy_gaps:
            if st.button(
                f"✅ 快速填補 {len(easy_gaps)} 個簡單空缺",
                use_container_width=True,
                type="primary",
            ):
                with st.spinner("正在填補簡單空缺..."):
                    filled = 0
                    for gap in swapper.gaps[:]:
                        if gap.candidates_with_quota:
                            best = swapper._select_best_candidate(gap.candidates_with_quota, gap)
                            if swapper._apply_direct_fill(gap, best):
                                filled += 1
                    st.session_state.stage2_schedule = swapper.schedule
                    st.success(f"✅ 已成功填補 {filled} 個空缺")
                    st.rerun()
    with q3:
        if st.button("💾 匯出當前狀態", use_container_width=True):
            try:
                year = st.session_state.selected_year
                month = st.session_state.selected_month
                report = swapper.get_detailed_report()
                export_data = {
                    "timestamp": datetime.now().isoformat(),
                    "year": year,
                    "month": month,
                    "schedule": {
                        date: {"attending": slot.attending, "resident": slot.resident}
                        for date, slot in swapper.schedule.items()
                    },
                    "statistics": {
                        "total_gaps": len(swapper.gaps),
                        "easy_gaps": len([g for g in swapper.gaps if g.candidates_with_quota]),
                        "medium_gaps": len(
                            [
                                g
                                for g in swapper.gaps
                                if g.candidates_over_quota and not g.candidates_with_quota
                            ]
                        ),
                        "hard_gaps": len(
                            [
                                g
                                for g in swapper.gaps
                                if not g.candidates_with_quota and not g.candidates_over_quota
                            ]
                        ),
                        "fill_rate": report["summary"]["fill_rate"],
                    },
                }
                json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 下載 JSON",
                    data=json_str,
                    file_name=f"schedule_stage2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )
            except Exception as e:
                st.error(f"匯出失敗：{e}")


# =============================
# Auto-Fill Tab (Stable Console)
# =============================
def _render_auto_fill_tab_safe(swapper):
    """智慧填補（穩定版）：背景執行緒 + queue + 拉式刷新"""
    st.markdown("### 🤖 智慧自動填補系統 v2.0（即時主控台）")

    # 美化樣式
    st.markdown(
        """
        <style>
          .cli-box{
              background:#0b1020;color:#e6edf3;font-family:ui-monospace,Menlo,Consolas,monospace;
              border:1px solid #263143;border-radius:12px;padding:14px;height:360px;overflow:auto;
              box-shadow:0 10px 30px rgba(0,0,0,.25);
          }
          .cli-header{display:flex;gap:12px;align-items:center;margin-bottom:10px}
          .dot{width:10px;height:10px;border-radius:50%}
          .red{background:#ff5f56}.yellow{background:#ffbd2e}.green{background:#27c93f}
          .muted{color:#9fb0c5}
          .stat-pill{background:#111931;border:1px solid #1e2a44;border-radius:10px;padding:6px 10px;margin-right:8px}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 目前空缺概況
    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("總空缺", report["summary"]["unfilled_slots"])
    with c2:
        st.metric("🟢 簡單", len(report["gap_analysis"]["easy"]))
    with c3:
        st.metric("🟡 中等", len(report["gap_analysis"]["medium"]))
    with c4:
        st.metric("🔴 困難", len(report["gap_analysis"]["hard"]))

    # Session 狀態
    ss = st.session_state
    ss.setdefault("cli_running", False)
    ss.setdefault("cli_logs", [])
    ss.setdefault("cli_queue", queue.Queue())
    ss.setdefault("cli_start_time", None)
    ss.setdefault("cli_initial_gaps", None)
    ss.setdefault("cli_result", None)
    ss.setdefault("execution_logs", [])

    # 控制列
    b1, b2, _sp = st.columns([1, 1, 2])
    with b1:
        start_btn = st.button(
            "🚀 開始智慧填補（即時）", type="primary", use_container_width=True, disabled=ss.cli_running
        )
    with b2:
        reset_btn = st.button("🧹 清空主控台", use_container_width=True, disabled=ss.cli_running)

    if reset_btn and not ss.cli_running:
        ss.cli_logs = []
        ss.cli_result = None
        ss.execution_logs = []
        _drain_queue_to_logs(ss)  # 清一下殘留
        st.toast("主控台已清空")

    # 佈局佔位
    header_ph = st.empty()
    stat_ph = st.empty()
    cli_ph = st.empty()
    st.divider()

    # 回呼：背景 thread 專用（只入列，不動 UI）
    def _log_cb(message: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            ss.cli_queue.put_nowait(f"[{ts}] {message}")
        except Exception:
            pass  # queue 暫滿時忽略，避免阻塞

    # 背景執行緒工作
    def _worker(max_backtracks: int):
        try:
            swapper.set_log_callback(_log_cb)
            result = swapper.run_auto_fill_with_backtracking(max_backtracks=max_backtracks)
            ss.cli_result = result
            ss.execution_logs = ss.cli_logs[:]
            ss.stage2_schedule = swapper.schedule
        finally:
            ss.cli_running = False
            try:
                swapper.set_log_callback(None)
            except Exception:
                pass

    # 開始執行
    MAX_BACKTRACKS = 20_000
    if start_btn and not ss.cli_running:
        # 清理舊狀態
        ss.cli_logs = []
        ss.cli_result = None
        ss.execution_logs = []
        ss.cli_start_time = time.time()
        ss.cli_initial_gaps = report["summary"]["unfilled_slots"]
        _flush_queue(ss.cli_queue)
        ss.cli_running = True

        t = threading.Thread(target=_worker, kwargs={"max_backtracks": MAX_BACKTRACKS}, daemon=True)
        if add_script_run_ctx:
            try:
                add_script_run_ctx(t)  # 綁定 Script Run Context，頁面終止時可被清理
            except Exception:
                pass
        t.start()
        st.rerun()

    # 取出新日誌
    _drain_queue_to_logs(ss)

    # 計算即時指標
    cur = swapper.get_detailed_report()
    remaining = cur["summary"]["unfilled_slots"]
    initial = ss.cli_initial_gaps if ss.cli_initial_gaps is not None else remaining
    solved = max(0, initial - remaining)
    elapsed = (time.time() - ss.cli_start_time) if ss.cli_start_time else 0.0
    eta_sec = (remaining * (elapsed / solved)) if solved > 0 else inf

    # 頁面呈現
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
            <span class="stat-pill">⌛ 估計完成：{'∞' if eta_sec==inf else f'{eta_sec:.1f}s'}</span>
            <span class="stat-pill">🧩 剩餘空缺：{remaining}</span>
            <span class="stat-pill">✅ 已解決：{solved}/{initial}</span>
            <span class="stat-pill">↩️ 最大回溯：{MAX_BACKTRACKS:,}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    last_400 = ss.cli_logs[-400:]
    cli_ph.markdown("<div class='cli-box'><pre>" + "\n".join(last_400) + "</pre></div>", unsafe_allow_html=True)

    # 結束後：摘要與後續行為
    if not ss.cli_running and ss.cli_result is not None:
        _render_run_result(ss)

    # 仍在執行：拉式刷新
    if ss.cli_running:
        if st_autorefresh:
            st_autorefresh(interval=500, key="stage2_cli_refresh")
        else:
            # 保底方案：極輕量延遲提示 + 讓使用者自行操作（避免伺服端強制 rerun）
            st.caption("（安裝 `streamlit-autorefresh` 可自動更新畫面）")


def _render_run_result(ss):
    """執行結果摘要（與 Stage 3 導引）"""
    res = ss.cli_result or {}
    st.success("執行完成")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("⏱️ 總耗時", f"{(time.time()-ss.cli_start_time):.2f}s" if ss.cli_start_time else "—")
    with c2:
        st.metric("直接填補", len(res.get("direct_fills", [])))
    with c3:
        st.metric("交換解決", len(res.get("swap_chains", [])))
    with c4:
        st.metric("剩餘空缺", len(res.get("remaining_gaps", [])))

    if res.get("remaining_gaps"):
        with st.expander("❌ 無法解決的空缺（點開檢視）", expanded=False):
            for g in res["remaining_gaps"]:
                st.write(f"- {g.get('date', '?')} {g.get('role', '')} → {g.get('reason', '無原因資訊')}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔁 再跑一次（清空主控台）", use_container_width=True):
            ss.cli_logs = []
            ss.cli_result = None
            ss.execution_logs = []
            st.rerun()
    with b2:
        if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
            ss.current_stage = 3
            st.rerun()


# =============================
# Execution Report Tab
# =============================
def _render_execution_report_tab(swapper):
    st.markdown("### 📈 執行報告")
    try:
        report = swapper.get_detailed_report()

        st.markdown("#### 📊 總體統計")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("總格位", report["summary"]["total_slots"])
        with c2:
            st.metric("已填格位", report["summary"]["filled_slots"])
        with c3:
            st.metric("填充率", f"{report['summary']['fill_rate']:.1%}")
        with c4:
            st.metric("狀態歷史", report.get("state_history", 0))

        st.markdown("#### 🎯 優化指標")
        metrics = report["optimization_metrics"]
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("平均優先級", f"{metrics['average_priority']:.1f}")
        with mc2:
            st.metric("最大機會成本", f"{metrics['max_opportunity_cost']:.1f}")
        with mc3:
            st.metric("總未來影響", f"{metrics['total_future_impact']:.1f}")

        if "search_stats" in report and report["search_stats"].get("chains_explored", 0) > 0:
            st.markdown("#### 🔍 搜索統計")
            stats = report["search_stats"]
            sc1, sc2, sc3, sc4 = st.columns(4)
            with sc1:
                st.metric("探索路徑", f"{stats['chains_explored']:,}")
            with sc2:
                st.metric("找到方案", stats.get("chains_found", 0))
            with sc3:
                st.metric("搜索時間", f"{stats.get('search_time', 0):.2f} 秒")
            with sc4:
                st.metric("最大深度", f"{stats.get('max_depth_reached', 0)} 層")

        violations = swapper.validate_all_constraints()
        if violations:
            st.markdown("#### ❌ 約束違規")
            for v in violations:
                st.error(v)
        else:
            st.success("✅ 所有約束條件均已滿足")

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
        st.error(f"無法生成報告：{e}")


# =============================
# Helpers
# =============================
def _flush_queue(q: queue.Queue):
    """清空 Queue，避免歷史殘留"""
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        return


def _drain_queue_to_logs(ss):
    """把 queue 新訊息灌入 ss.cli_logs"""
    q = ss.cli_queue
    while True:
        try:
            msg = q.get_nowait()
            ss.cli_logs.append(msg)
        except queue.Empty:
            break
