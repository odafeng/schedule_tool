"""Stage 2 各個標籤頁元件"""

import streamlit as st
import pandas as pd
from datetime import datetime
from backend.algorithms.stage2_interactiveCSP import Stage2AdvancedSwapper


def render_stage2_status(swapper: Stage2AdvancedSwapper):
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
    
    # 空缺分類摘要
    with st.expander("📊 空缺分類摘要", expanded=False):
        gap_col1, gap_col2, gap_col3 = st.columns(3)
        
        with gap_col1:
            st.info(f"""
            **🟢 簡單空缺**
            - 數量：{len(report['gap_analysis']['easy'])}
            - 特徵：有醫師可直接填補
            """)
        
        with gap_col2:
            st.warning(f"""
            **🟡 中等空缺**
            - 數量：{len(report['gap_analysis']['medium'])}
            - 特徵：需要交換才能填補
            """)
        
        with gap_col3:
            st.error(f"""
            **🔴 困難空缺**
            - 數量：{len(report['gap_analysis']['hard'])}
            - 特徵：無可用醫師
            """)
    
    # 搜索統計（如果有的話）
    if 'search_stats' in report and report['search_stats']['chains_explored'] > 0:
        with st.expander("🔍 搜索統計", expanded=False):
            stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
            
            with stats_col1:
                st.metric("探索路徑", report['search_stats']['chains_explored'])
            
            with stats_col2:
                st.metric("找到方案", report['search_stats']['chains_found'])
            
            with stats_col3:
                st.metric("搜索時間", f"{report['search_stats']['search_time']:.1f}秒")
            
            with stats_col4:
                st.metric("最大深度", report['search_stats']['max_depth_reached'])


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
        
        **快速操作：**
        - 使用下方按鈕可快速填補所有簡單空缺
        - 點擊「重新分析」更新空缺資訊
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
                    # 更新 session state
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
def render_auto_fill_tab(swapper: Stage2AdvancedSwapper):
    """自動填補標籤頁"""
    st.markdown("### 🤖 智慧自動填補系統")
    
    st.info("""
    **深度搜索引擎 v2.0 - 優化版**
    
    系統將自動執行以下步驟：
    1. **直接填補**：使用有配額餘額的醫師填補簡單空缺
    2. **深度搜索**：探索多達 3-5 步的複雜交換鏈
    3. **激進策略**：當標準方法無效時，嘗試跨類型交換
    4. **智能回溯**：最多執行 20 次回溯，確保找到最佳解
    
    搜索時間最長 2 分鐘，回溯次數最多 20 次，以確保充分探索所有可能性。
    """)
    
    # 顯示當前空缺狀況
    report = swapper.get_detailed_report()
    if report['summary']['unfilled_slots'] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return
    
    st.warning(f"🔍 當前有 **{report['summary']['unfilled_slots']}** 個空缺需要處理")
    
    # 顯示空缺難度分佈
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🟢 簡單", len(report['gap_analysis']['easy']))
    with col2:
        st.metric("🟡 中等", len(report['gap_analysis']['medium']))
    with col3:
        st.metric("🔴 困難", len(report['gap_analysis']['hard']))
    
    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
        # 創建一個容器來顯示執行日誌
        log_container = st.container()
        
        # 創建一個狀態容器用於動態更新
        status_placeholder = st.empty()
        log_placeholder = st.empty()
        
        with log_container:
            # 固定參數：20次回溯
            max_backtracks = 20
            
            st.info(f"""
            🔧 **系統參數**
            - 最大回溯次數：{max_backtracks} 次
            - 最長搜索時間：2 分鐘
            - 交換鏈深度：3-5 步
            """)
            
            # 設定日誌回調
            log_messages = []
            
            def log_callback(message: str, level: str = "info"):
                """日誌回調函數"""
                log_messages.append((message, level))
                
                # 更新日誌顯示
                with log_placeholder.container():
                    for msg, lvl in log_messages[-10:]:  # 只顯示最近10條
                        if lvl == "success":
                            st.success(msg)
                        elif lvl == "warning":
                            st.warning(msg)
                        elif lvl == "error":
                            st.error(msg)
                        else:
                            st.info(msg)
            
            # 設定回調
            swapper.set_log_callback(log_callback)
            
            # 執行自動填補
            with st.spinner("正在執行智慧填補..."):
                results = swapper.run_auto_fill_with_backtracking(max_backtracks)
            
            # 更新 schedule
            st.session_state.stage2_schedule = swapper.schedule
            
            # 顯示執行結果
            if results['remaining_gaps']:
                st.warning(f"""
                ⚠️ **執行完成（部分成功）**
                - ✅ 直接填補：{len(results['direct_fills'])} 個
                - 🔄 交換解決：{len(results['swap_chains'])} 個
                - ↩️ 回溯次數：{len(results['backtracks'])}
                - ❌ 剩餘空缺：{len(results['remaining_gaps'])} 個
                """)
                
                # 顯示剩餘空缺詳情
                with st.expander("❌ 無法解決的空缺", expanded=True):
                    for gap in results['remaining_gaps']:
                        st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")
                
                st.info("💡 建議：可以嘗試「交換鏈探索」手動處理剩餘空缺，或調整醫師配額後重試")
            else:
                st.success(f"""
                ✅ **完美執行！所有空缺已填補**
                - 直接填補：{len(results['direct_fills'])} 個
                - 交換解決：{len(results['swap_chains'])} 個
                - 回溯次數：{len(results['backtracks'])}
                """)
            
            # 顯示交換鏈詳情（如果有）
            if results['swap_chains']:
                with st.expander(f"🔄 執行的交換鏈 ({len(results['swap_chains'])} 個)", expanded=False):
                    for i, swap_info in enumerate(results['swap_chains']):
                        st.write(f"**交換 {i+1}**: {swap_info['gap']}")
                        for step in swap_info['chain']:
                            st.write(f"  - {step}")
            
            st.rerun()

def render_gap_analysis_tab(swapper: Stage2AdvancedSwapper):
    """空缺分析標籤頁"""
    st.markdown("### 📊 空缺詳細分析")
    
    if not swapper.gaps:
        st.success("🎉 所有空缺已填補完成！")
        return
    
    # 顯示前 20 個空缺
    gaps_to_show = swapper.gaps[:20]
    
    # 創建表格資料
    gap_data = []
    for gap in gaps_to_show:
        gap_data.append({
            "日期": gap.date,
            "角色": gap.role,
            "類型": "假日" if gap.is_holiday else "平日",
            "優先級": f"{gap.priority_score:.1f}",
            "可直接安排": len(gap.candidates_with_quota),
            "需調整安排": len(gap.candidates_over_quota),
            "機會成本": f"{gap.opportunity_cost:.1f}",
            "未來影響": f"{gap.future_impact_score:.1f}"
        })
    
    df = pd.DataFrame(gap_data)
    
    # 使用顏色標記
    def color_priority(val):
        if float(val) > 70:
            return 'background-color: #ffcdd2'  # 紅色
        elif float(val) > 40:
            return 'background-color: #fff9c4'  # 黃色
        else:
            return 'background-color: #c8e6c9'  # 綠色
    
    styled_df = df.style.applymap(color_priority, subset=['優先級'])
    st.dataframe(styled_df, use_container_width=True)
    
    # 詳細檢視
    st.markdown("### 🔍 空缺詳細檢視")
    
    selected_gap_idx = st.selectbox(
        "選擇要檢視的空缺",
        range(len(gaps_to_show)),
        format_func=lambda x: f"{gaps_to_show[x].date} {gaps_to_show[x].role} (優先級: {gaps_to_show[x].priority_score:.1f})"
    )
    
    if selected_gap_idx is not None:
        gap = gaps_to_show[selected_gap_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"""
            **基本資訊**
            - 日期：{gap.date}
            - 角色：{gap.role}
            - 假日：{'是' if gap.is_holiday else '否'}
            - 週末：{'是' if gap.is_weekend else '否'}
            """)
            
            st.success(f"""
            **可直接安排醫師**
            {', '.join(gap.candidates_with_quota) if gap.candidates_with_quota else '無'}
            """)
        
        with col2:
            st.warning(f"""
            **評分指標**
            - 嚴重度：{gap.severity:.1f}
            - 機會成本：{gap.opportunity_cost:.1f}
            - 未來影響：{gap.future_impact_score:.1f}
            - 唯一性：{gap.uniqueness_score:.1f}
            - 綜合優先級：{gap.priority_score:.1f}
            """)
            
            st.warning(f"""
            **需調整安排醫師**
            {', '.join(gap.candidates_over_quota) if gap.candidates_over_quota else '無'}
            """)


def render_swap_exploration_tab(swapper: Stage2AdvancedSwapper):
    """交換鏈探索標籤頁"""
    st.markdown("### 🔄 深度交換鏈探索")
    
    # 選擇目標空缺
    gaps_with_a = [g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota]
    
    if not gaps_with_a:
        st.info("沒有需要交換的空缺")
        return
    
    st.info("""
    **深度搜索參數**
    - 搜索深度：4 層（固定）
    - 最長搜索時間：2 分鐘
    - 探索策略：標準交換 + 激進策略
    
    系統將自動探索所有可能的 4 步交換鏈，找出最佳解決方案。
    """)
    
    selected_gap_idx = st.selectbox(
        "選擇要探索交換鏈的空缺",
        range(len(gaps_with_a)),
        format_func=lambda x: f"{gaps_with_a[x].date} {gaps_with_a[x].role} (優先級: {gaps_with_a[x].priority_score:.1f})"
    )
    
    if selected_gap_idx is not None:
        gap = gaps_with_a[selected_gap_idx]
        
        # 顯示空缺詳情
        col1, col2 = st.columns(2)
        with col1:
            st.metric("需要交換的醫師數", len(gap.candidates_over_quota))
        with col2:
            st.metric("空缺優先級", f"{gap.priority_score:.1f}")
        
        if st.button("🔍 開始深度搜索（深度=4）", use_container_width=True, type="primary"):
            # 創建容器顯示搜索進度
            search_container = st.container()
            
            with search_container:
                # 固定搜索深度為 4
                max_depth = 4
                
                st.info(f"🔄 正在執行深度 {max_depth} 的交換鏈搜索...")
                
                # 執行搜索
                chains = swapper.find_multi_step_swap_chains(gap, max_depth)
                
                if chains:
                    st.success(f"✅ 搜索完成！找到 {len(chains)} 個可行交換鏈")
                    
                    # 顯示前 10 個方案
                    for i, chain in enumerate(chains[:10]):
                        complexity_badge = "🟢 簡單" if chain.complexity <= 2 else "🟡 中等" if chain.complexity <= 3 else "🔴 複雜"
                        score_color = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
                        
                        with st.expander(f"{score_color} 方案 {i+1} | 分數: {chain.total_score:.1f} | {complexity_badge} ({chain.complexity} 步)"):
                            # 顯示步驟
                            for j, step in enumerate(chain.steps):
                                if j == 0:
                                    st.success(f"步驟 {j+1}: {step.description}")
                                else:
                                    st.info(f"步驟 {j+1}: {step.description}")
                            
                            st.write(f"**驗證訊息**: {chain.validation_message}")
                            
                            # 顯示影響分析
                            st.write("**影響分析**")
                            total_impact = sum(step.impact_score for step in chain.steps)
                            st.metric("總影響分數", f"{total_impact:.1f}", 
                                     help="分數越低表示對現有排班的影響越小")
                            
                            # 應用按鈕
                            if st.button(f"✅ 應用此方案", key=f"apply_chain_{i}"):
                                if swapper.apply_swap_chain(chain):
                                    st.success("✅ 交換鏈應用成功！")
                                    st.session_state.stage2_schedule = swapper.schedule
                                    st.rerun()
                                else:
                                    st.error("❌ 交換鏈應用失敗")
                else:
                    st.warning(f"""
                    ⚠️ 未找到可行的交換鏈（深度 {max_depth}）
                    
                    **可能的原因：**
                    - 所有候選醫師都已達到配額上限
                    - 沒有可以安全移動的班次
                    - 約束條件過於嚴格
                    - 深度 {max_depth} 不足以找到解決方案
                    
                    **建議：**
                    - 考慮調整醫師配額
                    - 檢查是否有過多的不可值班日限制
                    - 嘗試使用「自動填補」功能（包含更多策略）
                    """)


def render_execution_report_tab(swapper: Stage2AdvancedSwapper):
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
    
    # 關鍵空缺列表
    if report['gap_analysis']['critical']:
        st.markdown("#### ⚠️ 關鍵空缺 (Top 5)")
        critical_df = pd.DataFrame(report['gap_analysis']['critical'])
        st.dataframe(critical_df, use_container_width=True)
    
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