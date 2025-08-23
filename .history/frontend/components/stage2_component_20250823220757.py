"""
Stage 2 元件（CLI風格增強版）
包含實時日誌顯示和時間估算
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import threading
from typing import List, Dict
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper


def render_stage2_advanced(weekdays: list, holidays: list):
    """渲染新的 Stage 2: 進階智慧交換補洞系統"""
    st.subheader("🔧 Stage 2: 進階智慧交換補洞系統")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 1")
        return

    # 初始化或取得 Stage 2 系統
    if st.session_state.stage2_swapper is None:
        with st.spinner("正在初始化 Stage 2 系統..."):
            st.session_state.stage2_swapper = Stage2AdvancedSwapper(
                schedule=st.session_state.stage2_schedule,
                doctors=st.session_state.doctors,
                constraints=st.session_state.constraints,
                weekdays=weekdays,
                holidays=holidays,
            )
            # 清除自動填補結果（新的 swapper 實例）
            if 'auto_fill_results' in st.session_state:
                del st.session_state.auto_fill_results
    
    swapper = st.session_state.stage2_swapper

    # 顯示系統狀態
    render_stage2_status(swapper)

    # 主要操作區 - 只有三個標籤
    tab1, tab2, tab3 = st.tabs([
        "📅 日曆檢視",
        "🤖 智慧填補", 
        "📈 執行報告"
    ])

    with tab1:
        render_calendar_view_tab(swapper, weekdays, holidays)

    with tab2:
        render_auto_fill_tab_cli(swapper)
        
    with tab3:
        render_execution_report_tab(swapper)

    # 進入 Stage 3 的按鈕
    st.divider()
    
    report = swapper.get_detailed_report()
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 所有空缺已成功填補！")
        if st.button("➡️ 進入 Stage 3: 確認與發佈", type="primary", use_container_width=True):
            if 'auto_fill_results' in st.session_state:
                del st.session_state.auto_fill_results
            st.session_state.current_stage = 3
            st.rerun()
    elif report['summary']['unfilled_slots'] <= 2:
        st.warning(f"⚠️ 還有 {report['summary']['unfilled_slots']} 個空缺未填補")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 繼續嘗試", use_container_width=True):
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.rerun()
        with col2:
            if st.button("➡️ 接受並進入 Stage 3", type="primary", use_container_width=True):
                if 'auto_fill_results' in st.session_state:
                    del st.session_state.auto_fill_results
                st.session_state.current_stage = 3
                st.rerun()
    else:
        st.error(f"❌ 還有 {report['summary']['unfilled_slots']} 個空缺需要處理")


def render_stage2_status(swapper):
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
            with st.spinner("正在重新分析..."):
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
                    st.session_state.stage2_schedule = swapper.schedule
                    st.rerun()
    
    with col3:
        if st.button("💾 匯出當前狀態", use_container_width=True):
            import json
            
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


def render_auto_fill_tab_cli(swapper):
    """智慧填補標籤頁（CLI風格增強版）"""
    st.markdown("### 🤖 智慧自動填補系統 v2.0")
    
    # 系統說明
    with st.expander("📖 系統說明", expanded=False):
        st.info("""
        **深度搜索引擎 v2.0**
        
        系統將自動執行以下步驟：
        1. **直接填補**：使用有配額餘額的醫師填補簡單空缺
        2. **深度搜索**：探索深度5的複雜交換鏈
        3. **激進策略**：當標準方法無效時，嘗試跨類型交換
        4. **智能回溯**：最多執行 20,000 次回溯，確保找到最佳解
        
        搜索時間最長 2 分鐘，以確保充分探索所有可能性。
        """)
    
    # 當前空缺分析
    report = swapper.get_detailed_report()
    
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return
    
    # 空缺概況
    st.markdown("#### 📊 空缺概況")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總空缺", report['summary']['unfilled_slots'])
    with col2:
        st.metric("🟢 簡單", len(report['gap_analysis']['easy']),
                 help="有配額餘額，可直接填補")
    with col3:
        st.metric("🟡 中等", len(report['gap_analysis']['medium']),
                 help="需要交換班次")
    with col4:
        st.metric("🔴 困難", len(report['gap_analysis']['hard']),
                 help="無可用醫師")
    
    # 關鍵空缺列表
    if report['gap_analysis']['critical']:
        st.markdown("#### ⚠️ 優先處理空缺（Top 5）")
        critical_df = pd.DataFrame(report['gap_analysis']['critical'])
        critical_df = critical_df.rename(columns={
            'date': '日期',
            'role': '角色',
            'priority': '優先級',
            'severity': '嚴重度'
        })
        st.dataframe(critical_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # 執行按鈕和結果顯示
    st.markdown("#### 🚀 執行智慧填補")
    
    # 初始化 session state 來儲存執行結果
    if 'auto_fill_results' not in st.session_state:
        st.session_state.auto_fill_results = None
    if 'execution_logs' not in st.session_state:
        st.session_state.execution_logs = []
    
    # 如果已有執行結果，顯示它們
    if st.session_state.auto_fill_results is not None:
        results = st.session_state.auto_fill_results
        
        # 顯示執行結果
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if results['remaining_gaps']:
                st.warning(f"""
                ⚠️ **執行完成（部分成功）**
                - ✅ 直接填補：{len(results['direct_fills'])} 個
                - 🔄  交換解決：{len(results['swap_chains'])} 個
                - ↩️ 回溯次數：{len(results['backtracks'])}
                - ❌ 剩餘空缺：{len(results['remaining_gaps'])} 個
                """)
            else:
                st.success(f"""
                ✅ **完美執行！所有空缺已填補**
                - 直接填補：{len(results['direct_fills'])} 個
                - 交換解決：{len(results['swap_chains'])} 個
                - 回溯次數：{len(results['backtracks'])}
                """)
        
        with col2:
            st.metric("⏱️ 總耗時", f"{results.get('elapsed_time', 0):.2f} 秒")
            st.metric("🔍 探索路徑", f"{results.get('paths_explored', 0):,}")
        
        # 顯示剩餘空缺詳情
        if results['remaining_gaps']:
            with st.expander("❌ 無法解決的空缺", expanded=True):
                for gap in results['remaining_gaps']:
                    st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")
            
            st.info("💡 建議：可以嘗試調整醫師配額後重試，或手動處理剩餘空缺")
        
        # 顯示交換鏈詳情（如果有）
        if results['swap_chains']:
            with st.expander(f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)", expanded=False):
                for i, swap_info in enumerate(results['swap_chains']):
                    st.write(f"**交換 {i+1}**: {swap_info['gap']}")
                    for step in swap_info['chain']:
                        st.write(f"  - {step}")
        
        # 顯示執行日誌（簡化版）
        if st.session_state.execution_logs:
            with st.expander("📜 執行日誌", expanded=False):
                # 使用 text_area 顯示日誌
                log_text = "\n".join(st.session_state.execution_logs)
                st.text_area("系統日誌", value=log_text, height=400, disabled=True)
        
        # 提供清除結果的按鈕
        if st.button("🔄 清除結果並重新執行", use_container_width=True):
            st.session_state.auto_fill_results = None
            st.session_state.execution_logs = []
            st.rerun()
    
    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True, 
                 disabled=(st.session_state.auto_fill_results is not None)):
        
        # 固定參數
        max_backtracks = 20000
        
        # 清空之前的日誌
        st.session_state.execution_logs = []
        logs_collected = []
        
        # 開始時間
        start_time = time.time()
        
        # 使用 st.status 來顯示執行狀態
        with st.status("🚀 正在執行智慧填補...", expanded=True) as status:
            
            # 顯示系統參數
            st.write(f"""
            🔧 **系統參數**
            - 最大回溯次數：{max_backtracks:,} 次
            - 最長搜索時間：2 分鐘
            - 交換鏈深度：5 步
            """)
            
            # 創建日誌顯示區域
            log_area = st.empty()
            
            # 日誌收集列表
            log_messages = []
            
            def log_callback(message: str, level: str = "info"):
                """日誌回調函數"""
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_line = f"[{timestamp}] {message}"
                logs_collected.append(log_line)
                log_messages.append((timestamp, message, level))
                
                # 更新日誌顯示（只顯示最近的20條）
                display_logs = log_messages[-20:]
                log_text = "📟 **執行日誌**\n```\n"
                for ts, msg, lvl in display_logs:
                    emoji = {"success": "✅", "warning": "⚠️", "error": "❌", "info": "ℹ️"}.get(lvl, "▶️")
                    log_text += f"{emoji} [{ts}] {msg}\n"
                log_text += "```"
                log_area.markdown(log_text)
                
                # 更新狀態標題
                if "開始深度搜索" in message:
                    status.update(label="🔍 執行深度搜索中...", state="running")
                elif "找到" in message and "可行方案" in message:
                    status.update(label="✨ 評估交換方案中...", state="running")
                elif "直接填補" in message:
                    status.update(label="✅ 執行直接填補中...", state="running")
                elif "自動填補完成" in message:
                    status.update(label="🎉 處理完成！", state="complete")
            
            # 設定回調
            swapper.set_log_callback(log_callback)
            
            # 初始日誌
            log_callback("系統初始化完成", "info")
            log_callback(f"開始處理 {report['summary']['unfilled_slots']} 個空缺", "info")
            
            try:
                # 執行自動填補
                results = swapper.run_auto_fill_with_backtracking(max_backtracks)
                
                # 計算總耗時
                elapsed_time = time.time() - start_time
                results['elapsed_time'] = elapsed_time
                
                # 添加搜索統計
                if swapper.search_stats:
                    results['paths_explored'] = swapper.search_stats.get('chains_explored', 0)
                
                # 儲存日誌
                st.session_state.execution_logs = logs_collected
                
                # 更新 schedule 到 session state
                st.session_state.stage2_schedule = swapper.schedule
                
                # 儲存結果到 session state
                st.session_state.auto_fill_results = results
                
                # 顯示完成統計
                st.divider()
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("⏱️ 總耗時", f"{elapsed_time:.2f} 秒")
                with col2:
                    st.metric("✅ 已填補", f"{len(results['direct_fills']) + len(results['swap_chains'])} 個")
                with col3:
                    st.metric("❌ 剩餘", f"{len(results['remaining_gaps'])} 個")
                
                # 更新最終狀態
                if results['remaining_gaps']:
                    status.update(label=f"⚠️ 執行完成（還有 {len(results['remaining_gaps'])} 個空缺）", state="complete")
                else:
                    status.update(label="🎉 完美執行！所有空缺已填補", state="complete")
                
                # 短暫延遲後重新整理
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 執行失敗：{str(e)}")
                status.update(label="❌ 執行失敗", state="error")


def create_cli_log_html(logs: List[Dict]) -> str:
    """創建 CLI 風格的日誌 HTML"""
    html_lines = []
    
    for log in logs:
        timestamp = log['timestamp']
        message = log['message']
        level = log['level']
        
        # 根據級別設定顏色類別
        if level == 'success':
            level_class = 'terminal-success'
        elif level == 'warning':
            level_class = 'terminal-warning'
        elif level == 'error':
            level_class = 'terminal-error'
        else:
            level_class = 'terminal-info'
        
        # 特殊處理進度相關的訊息
        if '已探索' in message or '已找到' in message:
            level_class = 'terminal-progress'
        
        html_line = f'<div class="terminal-line"><span class="terminal-time">[{timestamp}]</span> <span class="{level_class}">{message}</span></div>'
        html_lines.append(html_line)
    
    return '\n'.join(html_lines)


def render_execution_report_tab(swapper):
    """執行報告標籤頁"""
    st.markdown("### 📈 執行報告")
    
    report = swapper.get_detailed_report()
    
    # 總體統計
    st.markdown("#### 📊 總體統計")
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
    st.markdown("#### 🎯 優化指標")
    metrics = report['optimization_metrics']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("平均優先級", f"{metrics['average_priority']:.1f}")
    with col2:
        st.metric("最大機會成本", f"{metrics['max_opportunity_cost']:.1f}")
    with col3:
        st.metric("總未來影響", f"{metrics['total_future_impact']:.1f}")
    
    # 搜索統計（如果有）
    if 'search_stats' in report and report['search_stats']['chains_explored'] > 0:
        st.markdown("#### 🔍 搜索統計")
        stats = report['search_stats']
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("探索路徑", f"{stats['chains_explored']:,}")
        with col2:
            st.metric("找到方案", stats['chains_found'])
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
        import json
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button(
            label="💾 下載 JSON 報告",
            data=report_json,
            file_name=f"stage2_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )