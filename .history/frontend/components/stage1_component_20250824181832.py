"""Stage 1 元件 - 使用者友善版"""

import streamlit as st
import pandas as pd
import copy
from backend.algorithms.stage1_greedy_beam import Stage1Scheduler
from frontend.utils.session_manager import SessionManager


def render_stage1(weekdays: list, holidays: list):
    """渲染 Stage 1: Greedy + Beam Search"""
    st.subheader("📋 Stage 1: 智慧快速排班")

    st.info(
        """
    **階段目標**：使用智慧演算法快速產生初步排班，預計可自動填充 85-95% 的班表。
    
    **自動優化策略**：
    - 🎯 假日優先安排（假日人力需求較緊）
    - 👥 約束較多的醫師優先處理
    - ✅ 嚴格遵守所有排班規則
    - 🔄 產生多個方案供選擇
    """
    )

    # 顯示預估資訊
    constraints = st.session_state.constraints
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("連續值班限制", f"{constraints.max_consecutive_days} 天")

    with col2:
        st.metric("預計填充率", "85-95%")

    with col3:
        total_days = len(weekdays + holidays)
        estimated_time = total_days * 0.2  # 簡化計算
        st.metric("預計執行時間", f"{estimated_time:.0f} 秒")

    # 檢查是否已有結果
    if "stage1_results" in st.session_state and st.session_state.stage1_results is not None:
        # 已有結果，直接顯示
        results = st.session_state.stage1_results
        st.success(f"✅ Stage 1 已完成！成功產生 {len(results)} 個排班方案")
        
        # 顯示結果表格
        display_stage1_results(results)
        
        # 提供重新執行的選項
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("🔄 重新執行", use_container_width=True):
                st.session_state.stage1_results = None
                st.rerun()
    else:
        # 沒有結果，顯示執行按鈕
        st.markdown("### 準備開始排班")
        
        # 顯示將要排班的資訊
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("排班天數", f"{len(weekdays + holidays)} 天")
        with col2:
            st.metric("醫師人數", f"{len(st.session_state.doctors)} 位")
        with col3:
            st.metric("需填格數", f"{len(weekdays + holidays) * 2} 格")
        
        if st.button("🚀 開始智慧排班", type="primary", use_container_width=True):
            execute_stage1(weekdays, holidays)
            st.rerun()


def display_stage1_results(results):
    """顯示 Stage 1 結果"""
    # 顯示每個方案
    st.subheader("📊 排班方案比較")
    
    # 準備比較資料
    comparison_data = []
    for i, state in enumerate(results):
        # 計算更友善的指標
        total_slots = len(state.schedule) * 2
        fill_rate = state.fill_rate
        
        # 判斷方案品質
        if fill_rate >= 0.95:
            quality = "🌟 優秀"
        elif fill_rate >= 0.90:
            quality = "✅ 良好"
        elif fill_rate >= 0.85:
            quality = "👍 合格"
        else:
            quality = "⚠️ 待改進"
        
        comparison_data.append(
            {
                "方案編號": f"方案 {i+1}",
                "品質評級": quality,
                "完成度": f"{fill_rate:.1%}",
                "已排班": f"{state.filled_count} 格",
                "待填補": f"{len(state.unfilled_slots)} 格",
                "綜合評分": f"{state.score:.0f}"
            }
        )

    df = pd.DataFrame(comparison_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 選擇方案
    st.subheader("🎯 選擇方案進入下一階段")
    
    # 保存選擇的索引到 session state
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0

    # 建議最佳方案
    best_index = max(range(len(results)), key=lambda i: results[i].score)
    if st.session_state.selected_index == 0:
        st.session_state.selected_index = best_index
    
    st.info(f"💡 建議選擇：方案 {best_index + 1}（綜合評分最高）")
    
    selected_index = st.radio(
        "請選擇一個方案：",
        range(len(results)),
        index=st.session_state.selected_index,
        format_func=lambda x: f"方案 {x+1}（完成度 {results[x].fill_rate:.1%}，評分 {results[x].score:.0f}）",
        key="solution_radio",
    )
    
    # 更新選擇的索引
    st.session_state.selected_index = selected_index

    col1, col2 = st.columns(2)

    with col1:
        if st.button("👁️ 預覽選中方案", use_container_width=True, key="preview_solution"):
            preview_schedule_inline(results[selected_index].schedule)

    with col2:
        if st.button("✅ 確認選擇，進入 Stage 2", type="primary", use_container_width=True, key="adopt_solution"):
            st.session_state.selected_solution = results[selected_index]
            st.session_state.stage2_schedule = copy.deepcopy(
                results[selected_index].schedule
            )
            st.session_state.current_stage = 2
            st.success("已選擇方案，即將進入 Stage 2...")
            st.rerun()


def execute_stage1(weekdays: list, holidays: list):
    """執行 Stage 1"""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress):
        progress_bar.progress(progress)
        percentage = int(progress * 100)
        status_text.text(f"排班進度：{percentage}%")
        
        # 顯示更友善的狀態訊息
        if percentage < 20:
            status_text.text(f"排班進度：{percentage}% - 正在初始化...")
        elif percentage < 40:
            status_text.text(f"排班進度：{percentage}% - 正在處理假日排班...")
        elif percentage < 60:
            status_text.text(f"排班進度：{percentage}% - 正在處理平日排班...")
        elif percentage < 80:
            status_text.text(f"排班進度：{percentage}% - 正在優化方案...")
        elif percentage < 100:
            status_text.text(f"排班進度：{percentage}% - 即將完成...")
        else:
            status_text.text("排班完成！")

    # 執行 Stage 1
    scheduler = Stage1Scheduler(
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays,
    )

    with st.spinner("🤖 智慧排班系統正在運作中，請稍候..."):
        results = scheduler.run(
            beam_width=10,  # 固定使用最佳參數
            progress_callback=update_progress
        )

    progress_bar.progress(1.0)
    status_text.text("✨ 排班完成！")

    # 儲存結果到 session state
    st.session_state.stage1_results = results
    
    # 顯示完成訊息
    st.balloons()  # 加入慶祝動畫
    st.success(f"🎉 恭喜！Stage 1 成功完成，已產生 {len(results)} 個優質排班方案供您選擇")


def preview_schedule_inline(schedule: dict):
    """內嵌預覽排班表"""
    with st.container():
        st.markdown("### 📅 排班預覽")
        
        # 準備資料
        data = []
        for date_str in sorted(schedule.keys()):
            slot = schedule[date_str]
            
            # 判斷是否為假日（簡單判斷）
            is_holiday = "假日" if any(keyword in str(date_str) for keyword in ["六", "日", "假"]) else "平日"
            
            data.append({
                '日期': date_str,
                '類型': is_holiday,
                '主治醫師': slot.attending or '❌ 待排',
                '總醫師': slot.resident or '❌ 待排'
            })
        
        df = pd.DataFrame(data)
        
        # 統計資訊
        filled_attending = len([d for d in data if not d['主治醫師'].startswith('❌')])
        filled_resident = len([d for d in data if not d['總醫師'].startswith('❌')])
        total = len(data)
        
        # 顯示統計
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總天數", f"{total} 天")
        with col2:
            st.metric("主治醫師已排", f"{filled_attending}/{total}")
        with col3:
            st.metric("總醫師已排", f"{filled_resident}/{total}")
        with col4:
            fill_rate = (filled_attending + filled_resident)/(total*2)
            st.metric("整體完成度", f"{fill_rate:.1%}")
        
        # 顯示表格
        st.dataframe(
            df, 
            use_container_width=True, 
            height=400,
            hide_index=True,
            column_config={
                "類型": st.column_config.TextColumn(width="small"),
                "主治醫師": st.column_config.TextColumn(width="medium"),
                "總醫師": st.column_config.TextColumn(width="medium"),
            }
        )
        
        # 顯示待處理項目
        if filled_attending < total or filled_resident < total:
            with st.expander("📝 待處理項目"):
                unfilled = []
                for d in data:
                    if d['主治醫師'].startswith('❌'):
                        unfilled.append(f"- {d['日期']} 需要主治醫師")
                    if d['總醫師'].startswith('❌'):
                        unfilled.append(f"- {d['日期']} 需要總醫師")
                
                if len(unfilled) > 10:
                    st.write("顯示前 10 個待處理項目：")
                    for item in unfilled[:10]:
                        st.write(item)
                    st.write(f"...還有 {len(unfilled) - 10} 個項目")
                else:
                    for item in unfilled:
                        st.write(item)