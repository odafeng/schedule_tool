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

    # 初始化必要的 session state
    if "auto_fill_results" not in st.session_state:
        st.session_state.auto_fill_results = None
    if "auto_fill_logs" not in st.session_state:
        st.session_state.auto_fill_logs = []
    if "auto_fill_running" not in st.session_state:
        st.session_state.auto_fill_running = False
    if "stage2_mode" not in st.session_state:
        st.session_state.stage2_mode = "calendar"
    if "auto_fill_completed" not in st.session_state:
        st.session_state.auto_fill_completed = False
    if "auto_fill_executed" not in st.session_state:
        st.session_state.auto_fill_executed = False
    
    # 重要：保留原始排班的備份（只在第一次進入時建立）
    if "stage2_original_schedule" not in st.session_state:
        st.session_state.stage2_original_schedule = copy.deepcopy(st.session_state.stage2_schedule)
    
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

    # 根據當前模式顯示不同內容
    if st.session_state.stage2_mode == "filling":
        # 正在執行填補時，只顯示填補頁面
        render_auto_fill_page(swapper, weekdays, holidays)
    elif st.session_state.stage2_mode == "output":
        # 填補完成後，顯示輸出頁面
        render_output_page(swapper, weekdays, holidays)
    else:
        # 預設顯示標籤頁模式
        render_tabbed_interface(swapper, weekdays, holidays)


def render_tabbed_interface(swapper, weekdays, holidays):
    """渲染標籤頁介面"""
    # 如果剛完成填補，預設選擇最後一個標籤
    if st.session_state.auto_fill_completed:
        tabs = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📊 最終輸出 🔴"])
        st.session_state.auto_fill_completed = False
    else:
        tabs = st.tabs(["📅 日曆檢視", "🤖 智慧填補", "📊 最終輸出"])

    with tabs[0]:
        render_calendar_view_simplified(swapper, weekdays, holidays)

    with tabs[1]:
        render_auto_fill_tab(swapper)

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


def render_auto_fill_tab(swapper):
    """標籤頁模式下的智慧填補頁"""
    st.markdown("### 🤖 智慧自動填補")

    # 取得目前空缺概況
    report = swapper.get_detailed_report()
    if report["summary"]["unfilled_slots"] == 0:
        st.success("🎉 恭喜！所有空缺都已填補完成")
        return

    # 顯示簡單統計
    st.info(f"目前還有 **{report['summary']['unfilled_slots']}** 個空缺需要處理")

    # 執行按鈕
    if st.button("🚀 開始智慧填補", type="primary", use_container_width=True):
        st.session_state.stage2_mode = "filling"
        st.session_state.auto_fill_running = True
        st.session_state.auto_fill_logs = []
        # 重置執行標記
        if "auto_fill_executed" in st.session_state:
            del st.session_state.auto_fill_executed
        st.rerun()


def render_auto_fill_page(swapper, weekdays, holidays):
    """獨立的填補執行頁面"""
    st.markdown("### 🤖 正在執行智慧填補...")
    
    # 檢查是否需要執行（只在第一次進入時執行）
    if "auto_fill_executed" not in st.session_state:
        st.session_state.auto_fill_executed = False
    
    if not st.session_state.auto_fill_executed:
        # 創建日誌容器
        log_container = st.container()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 執行自動填補
        execute_auto_fill_simple(swapper, log_container, progress_bar, status_text)
        
        # 標記為已執行
        st.session_state.auto_fill_executed = True
    else:
        # 如果已經執行過，只顯示結果
        st.success("✅ 填補已完成！")
        
        # 顯示最後的日誌
        if st.session_state.auto_fill_logs:
            st.markdown("#### 執行日誌")
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
                <pre style="color: #f0f0f0; margin: 0; font-weight: 400; opacity: 1;">{"<br>".join(st.session_state.auto_fill_logs[-50:])}</pre>
            </div>
            """
            st.markdown(log_html, unsafe_allow_html=True)
    
    # 顯示按鈕
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 查看結果", type="primary", use_container_width=True):
            st.session_state.stage2_mode = "output"
            st.session_state.auto_fill_running = False
            st.session_state.auto_fill_completed = True
            st.rerun()
    
    with col2:
        if st.button("📅 返回日曆", use_container_width=True):
            st.session_state.stage2_mode = "calendar"
            st.session_state.auto_fill_running = False
            # 重置執行標記，下次可以重新執行
            st.session_state.auto_fill_executed = False
            st.rerun()


def render_output_page(swapper, weekdays, holidays):
    """獨立的輸出頁面"""
    st.markdown("### 📊 最終輸出")
    
    # 返回按鈕
    if st.button("← 返回主介面", use_container_width=True):
        st.session_state.stage2_mode = "calendar"
        st.rerun()
    
    # 顯示最終輸出內容
    render_final_output_content(swapper, weekdays, holidays)


def render_auto_fill_simplified(swapper):
    """簡化的智慧填補標籤頁（已棄用）"""
    render_auto_fill_tab(swapper)


def execute_auto_fill_simple(swapper, log_container, progress_bar, status_text):
    """簡化的自動填補執行函式（保留原本的即時日誌顯示）"""
    max_backtracks = 1000  # 減少回溯次數加快執行

    # 在日誌容器中創建顯示區域
    with log_container:
        log_display = st.empty()
        metrics_display = st.empty()

    def add_log(message: str, level: str = "INFO"):
        """添加日誌並更新顯示（保留原本的黑底白字風格）"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # 決定圖標和顏色
        level_styles = {
            "SUCCESS": ("✅", ""),
            "ERROR": ("❌", ""),
            "WARNING": ("⚠️", ""),
            "INFO": ("ℹ️", ""),
            "DEBUG": ("🔍", ""),
        }
        icon, _ = level_styles.get(level.upper(), ("▶", ""))
        
        # 格式化日誌
        log_line = f"[{timestamp}] {icon} {message}"
        st.session_state.auto_fill_logs.append(log_line)
        
        # 限制日誌數量避免記憶體問題
        if len(st.session_state.auto_fill_logs) > 500:
            st.session_state.auto_fill_logs = st.session_state.auto_fill_logs[-400:]
        
        # 決定是否更新顯示
        should_update = (
            len(st.session_state.auto_fill_logs) % 10 == 0  # 每 10 條更新
            or level in ["SUCCESS", "ERROR", "WARNING"]  # 重要訊息立即更新
            or "完成" in message or "失敗" in message  # 關鍵字立即更新
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

    # 設置日誌回調
    swapper.set_log_callback(add_log)
    swapper.set_log_level('normal')  # 使用 normal 模式以獲得適量的日誌輸出

    # 進度追蹤
    progress_data = {"filled": 0, "swapped": 0, "failed": 0}
    search_metrics = {
        "gaps_processed": 0,
        "chains_explored": 0,
        "backtracks": 0,
        "last_gap_count": len(swapper.gaps),
    }

    try:
        # 開始執行
        progress_bar.progress(0.05)
        status_text.text("開始執行智慧填補...")
        
        add_log("=" * 50, "INFO")
        add_log("開始執行智慧自動填補系統", "INFO")
        add_log(f"演算法配置:", "INFO")
        add_log(f"  - 最大回溯次數: {max_backtracks:,}", "INFO")
        add_log(f"  - 搜索深度: 5", "INFO")
        add_log("=" * 50, "INFO")

        initial_gaps = len(swapper.gaps)
        add_log(f"初始狀態分析:", "INFO")
        add_log(f"  - 總空缺數: {initial_gaps}", "INFO")

        # 分析空缺類型
        easy_gaps = len([g for g in swapper.gaps if g.candidates_with_quota])
        medium_gaps = len([g for g in swapper.gaps if g.candidates_over_quota and not g.candidates_with_quota])
        hard_gaps = len([g for g in swapper.gaps if not g.candidates_with_quota and not g.candidates_over_quota])
        
        add_log(f"  - 簡單空缺: {easy_gaps} (有配額餘額)", "INFO")
        add_log(f"  - 中等空缺: {medium_gaps} (需要交換)", "INFO")
        add_log(f"  - 困難空缺: {hard_gaps} (無可用醫師)", "INFO")
        add_log("=" * 50, "INFO")

        # 開始計時
        start_time = time.time()
        add_log("開始執行自動填補演算法...", "INFO")

        # 執行自動填補
        results = None
        try:
            results = swapper.run_auto_fill_with_backtracking(max_backtracks)
        except Exception as e:
            add_log(f"執行中斷: {str(e)}", "WARNING")
            results = {
                "direct_fills": [],
                "swap_chains": [],
                "backtracks": [],
                "remaining_gaps": [{"date": g.date, "role": g.role, "reason": "執行中斷"} for g in swapper.gaps]
            }

        # 計算耗時
        elapsed_time = time.time() - start_time
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
        add_log(f"  - 總回溯次數: {len(results.get('backtracks', []))}", "INFO")
        add_log("=" * 50, "INFO")

        # 更新結果到 session state
        st.session_state.auto_fill_results = {
            "total_backtracks": results.get("backtracks", []),
            "swap_attempts": len(results.get("swap_chains", [])),
            "remaining_gaps": final_gaps,
            "elapsed_time": elapsed_time,
            "actual_improvement": actual_improvement
        }

        # 同步更新 schedule
        st.session_state.stage2_schedule = copy.deepcopy(swapper.schedule)

        # 最終狀態
        progress_bar.progress(1.0)
        if results.get("remaining_gaps"):
            add_log(f"執行完成，還有 {len(results['remaining_gaps'])} 個空缺未解決", "WARNING")
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
        st.session_state.auto_fill_results = {
            "error": str(e),
            "total_backtracks": [],
            "swap_attempts": 0,
            "remaining_gaps": len(swapper.gaps),
            "elapsed_time": 0
        }


def render_final_output(swapper, weekdays: list, holidays: list):
    """最終輸出標籤頁（包裝函式）"""
    render_final_output_content(swapper, weekdays, holidays)


def render_final_output_content(swapper, weekdays: list, holidays: list):
    """最終輸出的實際內容"""
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

    # 可編輯的日曆形式班表
    st.markdown("### 📝 手動調整班表")
    
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 取得所有醫師名單
    attending_doctors = ["（空缺）"] + [doc.name for doc in st.session_state.doctors if doc.role == "主治"]
    resident_doctors = ["（空缺）"] + [doc.name for doc in st.session_state.doctors if doc.role == "總醫師"]
    
    # 建立月曆網格
    cal = calendar.monthcalendar(year, month)
    
    # 使用容器來顯示日曆
    st.markdown("""
    <style>
    .calendar-container {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .weekday-header {
        background: #4a5568;
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
    }
    .gap-warning {
        background: #ff4444;
        color: white;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
        margin: 2px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 顯示星期標題
    weekday_cols = st.columns(7)
    for i, day_name in enumerate(['一', '二', '三', '四', '五', '六', '日']):
        with weekday_cols[i]:
            st.markdown(f"<div class='weekday-header'>{day_name}</div>", unsafe_allow_html=True)
    
    # 顯示月曆格子
    for week_num, week in enumerate(cal):
        cols = st.columns(7)
        for day_num, day in enumerate(week):
            if day == 0:
                continue
                
            with cols[day_num]:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                is_holiday = date_str in holidays
                
                # 檢查是否有空缺
                has_gap = False
                if date_str in swapper.schedule:
                    slot = swapper.schedule[date_str]
                    has_gap = (not slot.attending) or (not slot.resident)
                
                # 格子樣式 - 如果有空缺，使用更醒目的紅色
                if has_gap:
                    bg_color = "#ffebee"  # 淡紅色背景
                    border_style = "border: 2px solid #ff4444;"  # 紅色邊框
                elif is_holiday:
                    bg_color = "#fee2e2"
                    border_style = "border: 1px solid #e0e0e0;"
                else:
                    bg_color = "#e0e7ff"
                    border_style = "border: 1px solid #e0e0e0;"
                
                with st.container():
                    # 日期標題
                    st.markdown(f"""
                    <div style='background: {bg_color}; padding: 5px; border-radius: 5px 5px 0 0; text-align: center; {border_style}'>
                        <b>{day}日</b> {'🎉' if is_holiday else ''} {' ⚠️' if has_gap else ''}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if date_str in swapper.schedule:
                        slot = swapper.schedule[date_str]
                        
                        # 主治醫師選擇器 - 如果空缺顯示警告
                        current_attending = slot.attending or "（空缺）"
                        if not slot.attending:
                            st.markdown("<span class='gap-warning'>❌ 主治空缺</span>", unsafe_allow_html=True)
                        
                        new_attending = st.selectbox(
                            "主治",
                            attending_doctors,
                            index=attending_doctors.index(current_attending),
                            key=f"att_{date_str}",
                            label_visibility="collapsed"
                        )
                        
                        # 總醫師選擇器 - 如果空缺顯示警告
                        current_resident = slot.resident or "（空缺）"
                        if not slot.resident:
                            st.markdown("<span class='gap-warning'>❌ 總醫空缺</span>", unsafe_allow_html=True)
                        
                        new_resident = st.selectbox(
                            "總醫",
                            resident_doctors,
                            index=resident_doctors.index(current_resident),
                            key=f"res_{date_str}",
                            label_visibility="collapsed"
                        )
                        
                        # 即時更新（如果有變更）
                        if new_attending != current_attending:
                            slot.attending = None if new_attending == "（空缺）" else new_attending
                        if new_resident != current_resident:
                            slot.resident = None if new_resident == "（空缺）" else new_resident
    
    # 顯示圖例
    st.markdown("""
    <div style='background: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 20px;'>
        <b>圖例說明：</b>
        <span style='background: #ffebee; padding: 3px 8px; margin: 0 5px; border: 2px solid #ff4444;'>有空缺</span>
        <span style='background: #fee2e2; padding: 3px 8px; margin: 0 5px;'>假日</span>
        <span style='background: #e0e7ff; padding: 3px 8px; margin: 0 5px;'>平日</span>
        <span class='gap-warning' style='margin: 0 5px;'>❌ 空缺警示</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 操作按鈕
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    
    with col1:
        if st.button("💾 儲存修改", use_container_width=True):
            # 同步到 session state（更新當前工作版本）
            st.session_state.stage2_schedule = copy.deepcopy(swapper.schedule)
            st.success("✅ 班表已更新")
            time.sleep(0.5)
            st.rerun()
    
    with col2:
        # 匯出 CSV - 修正編碼問題
        schedule_data = []
        num_days = calendar.monthrange(year, month)[1]
        for day in range(1, num_days + 1):
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            if date_str in swapper.schedule:
                slot = swapper.schedule[date_str]
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                weekday_name = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
                schedule_data.append({
                    '日期': f"{month}/{day}",
                    '星期': weekday_name,
                    '類型': '假日' if date_str in holidays else '平日',
                    '主治醫師': slot.attending or "（空缺）",
                    '總醫師': slot.resident or "（空缺）"
                })
    
    with col3:
        if st.button("🔄 重置至原始", use_container_width=True):
            # 清除所有 selectbox 的 session state
            keys_to_delete = []
            for key in st.session_state.keys():
                if key.startswith("att_") or key.startswith("res_"):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del st.session_state[key]
            
            # 從原始備份還原
            if "stage2_original_schedule" in st.session_state:
                # 還原到最初的版本
                st.session_state.stage2_schedule = copy.deepcopy(
                    st.session_state.stage2_original_schedule
                )
                
                # 重新初始化 swapper
                st.session_state.stage2_swapper = Stage2AdvancedSwapper(
                    schedule=st.session_state.stage2_schedule,
                    doctors=st.session_state.doctors,
                    constraints=st.session_state.constraints,
                    weekdays=weekdays,
                    holidays=holidays,
                )
                st.success("✅ 已重置至原始班表")
                time.sleep(0.5)
            else:
                st.error("找不到原始班表備份")
            
            st.rerun()
    
    with col4:
        # 計算剩餘空缺
        remaining_gaps = 0
        for date_str, slot in swapper.schedule.items():
            if not slot.attending:
                remaining_gaps += 1
            if not slot.resident:
                remaining_gaps += 1
        
        if remaining_gaps == 0:
            if st.button("➡️ 進入 Stage 3：確認發佈", type="primary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()
        else:
            if st.button(f"➡️ 接受並進入 Stage 3（還有 {remaining_gaps} 個空缺）", 
                        type="secondary", use_container_width=True):
                st.session_state.current_stage = 3
                st.rerun()