"""
班表檢視與手動調整頁面 - 簡化版
無任何限制的手動調整 + 簡易LINE對應管理
"""
import streamlit as st
import pandas as pd
import json
import os
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from backend.utils import get_month_calendar
from backend.algorithms import Stage2AdvancedSwapper
from frontend.components import CalendarView, ScheduleTable
from backend.utils.excel_exporter import ExcelCalendarExporter
from backend.utils.pdf_generator import PDFCalendarGenerator
from backend.utils.linebot_client import get_line_bot_client

def render():
    """渲染班表檢視頁面"""
    st.header("📊 排班結果檢視與調整")
    
    # 使用 SessionManager 取得當前班表
    from frontend.utils.session_manager import SessionManager
    
    current_schedule = SessionManager.get_current_schedule()
    
    if current_schedule is None:
        st.warning("⚠️ 尚未產生排班結果")
        st.info("請先執行排班流程：")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🚀 開始排班", use_container_width=True):
                st.session_state.current_stage = 1
                st.rerun()
        with col2:
            if st.button("📂 載入既有排班", use_container_width=True):
                if SessionManager.load_settings():
                    st.success("設定已載入")
                    st.rerun()
        return
    
    # 取得月份資料
    weekdays, holidays = SessionManager.get_current_holidays_and_workdays()
    
    # 重建 scheduler 用於取得可用醫師資訊
    from backend.algorithms import Stage2AdvancedSwapper
    scheduler = Stage2AdvancedSwapper(
        schedule=current_schedule,  # ← 重要：加入 schedule 參數
        doctors=st.session_state.doctors,
        constraints=st.session_state.constraints,
        weekdays=weekdays,
        holidays=holidays
    )
    
    # 初始化調整後的班表（如果還沒有）
    if 'adjusted_schedule' not in st.session_state:
        st.session_state.adjusted_schedule = current_schedule.copy()
    
    # 建立一個相容的結果物件
    from types import SimpleNamespace
    result = SimpleNamespace()
    result.schedule = st.session_state.adjusted_schedule
    
    # 顯示班表來源資訊
    source_info = st.session_state.get('schedule_result')
    if source_info and hasattr(source_info, 'source'):
        stage_names = {
            'stage1': 'Stage 1 - 初始排班',
            'stage2': 'Stage 2 - 優化調整',
            'stage3': 'Stage 3 - 確認發佈',
            'manual_adjustment': '手動調整'
        }
        source_name = stage_names.get(source_info.source, '未知來源')
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.info(f"📌 班表來源：{source_name}")
        with col2:
            if hasattr(source_info, 'statistics') and 'fill_rate' in source_info.statistics:
                st.metric("填滿率", f"{source_info.statistics['fill_rate']:.1%}")
        with col3:
            if hasattr(source_info, 'updated_at'):
                update_time = datetime.fromisoformat(source_info.updated_at)
                st.caption(f"更新：{update_time.strftime('%m/%d %H:%M')}")
    
    # 建立分頁（保持原有邏輯）
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 月曆視圖", 
        "📋 列表視圖", 
        "🔄 手動調整",
        "📤 匯出功能",
        "📱 LINE設定"
    ])
    
    with tab1:
        render_calendar_view(result, scheduler, weekdays, holidays)
    
    with tab2:
        render_list_view(result, scheduler, weekdays, holidays)
    
    with tab3:
        render_manual_adjustment(scheduler, weekdays, holidays)
    
    with tab4:
        render_export_section(scheduler, weekdays, holidays)
    
    with tab5:
        render_line_settings()


def render_manual_adjustment(scheduler, weekdays, holidays):
    """渲染手動調整介面（無任何限制）"""
    st.subheader("🔄 手動調整班表")
    st.info("💡 手動調整模式：可自由調整所有班表，不受任何規則限制")
    
    # 選擇調整模式
    adjustment_mode = st.radio(
        "選擇調整模式",
        ["單日調整", "醫師互換", "快速清空"],
        horizontal=True
    )
    
    if adjustment_mode == "單日調整":
        render_single_day_adjustment()
    elif adjustment_mode == "醫師互換":
        render_doctor_swap()
    else:
        render_quick_clear()
    
    # 顯示調整歷史
    if 'adjustment_history' not in st.session_state:
        st.session_state.adjustment_history = []
    
    if st.session_state.adjustment_history:
        with st.expander("📝 調整歷史（最近10筆）", expanded=False):
            for idx, record in enumerate(reversed(st.session_state.adjustment_history[-10:])):
                st.write(f"{len(st.session_state.adjustment_history)-idx}. {record['timestamp']} - {record['description']}")


def render_single_day_adjustment():
    """單日調整介面（無限制版）"""
    st.markdown("### 📅 單日調整")
    
    # 獲取所有日期
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    all_dates = sorted(weekdays + holidays)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 選擇日期
        date_options = []
        for date_str in all_dates:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            date_type = "假日" if date_str in holidays else "平日"
            weekday = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
            date_options.append(f"{dt.month}/{dt.day} ({weekday}) {date_type}")
        
        selected_idx = st.selectbox(
            "選擇日期",
            range(len(date_options)),
            format_func=lambda x: date_options[x]
        )
        selected_date = all_dates[selected_idx]
    
    with col2:
        # 選擇職位
        role = st.selectbox("選擇職位", ["主治醫師", "住院醫師"])
    
    # 顯示當前值班醫師
    current_schedule = st.session_state.adjusted_schedule.get(selected_date)
    current_doctor = None
    if current_schedule:
        current_doctor = current_schedule.attending if role == "主治醫師" else current_schedule.resident
        if current_doctor:
            st.info(f"當前值班：**{current_doctor}**")
        else:
            st.warning("當前：未排班")
    
    with col3:
        # 獲取所有醫師（不檢查任何限制）
        all_doctors = [d.name for d in st.session_state.doctors]
        
        # 將當前醫師放在最前面
        if current_doctor and current_doctor in all_doctors:
            all_doctors = [current_doctor] + [d for d in all_doctors if d != current_doctor]
        
        new_doctor = st.selectbox(
            "更換為",
            ["不排班"] + all_doctors
        )
    
    # 調整按鈕
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ 確認調整", type="primary", use_container_width=True):
            new_doctor_value = None if new_doctor == "不排班" else new_doctor
            perform_single_adjustment(selected_date, role, new_doctor_value, current_doctor)
            st.success("✅ 調整成功！")
            st.rerun()
    
    with col2:
        if st.button("📱 調整並通知", type="secondary", use_container_width=True):
            new_doctor_value = None if new_doctor == "不排班" else new_doctor
            perform_single_adjustment(selected_date, role, new_doctor_value, current_doctor)
            
            # 發送LINE通知
            if send_change_notification(selected_date, role, current_doctor, new_doctor_value):
                st.success("✅ 調整成功並已發送通知！")
            else:
                st.warning("⚠️ 調整成功但通知發送失敗")
            st.rerun()


def render_doctor_swap():
    """醫師互換介面（無限制版）"""
    st.markdown("### 🔄 醫師互換")
    
    # 獲取所有日期
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    all_dates = sorted(weekdays + holidays)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 第一個班次")
        date1_idx = st.selectbox(
            "日期 1",
            range(len(all_dates)),
            format_func=lambda x: format_date_option(all_dates[x], holidays),
            key="swap_date1"
        )
        date1 = all_dates[date1_idx]
        
        role1 = st.selectbox("職位 1", ["主治醫師", "住院醫師"], key="swap_role1")
        
        current1 = get_current_doctor(date1, role1)
        if current1:
            st.info(f"當前值班：**{current1}**")
        else:
            st.warning("當前：未排班")
    
    with col2:
        st.markdown("#### 第二個班次")
        date2_idx = st.selectbox(
            "日期 2",
            range(len(all_dates)),
            format_func=lambda x: format_date_option(all_dates[x], holidays),
            key="swap_date2"
        )
        date2 = all_dates[date2_idx]
        
        role2 = st.selectbox("職位 2", ["主治醫師", "住院醫師"], key="swap_role2")
        
        current2 = get_current_doctor(date2, role2)
        if current2:
            st.info(f"當前值班：**{current2}**")
        else:
            st.warning("當前：未排班")
    
    # 互換按鈕（不檢查任何條件）
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 執行互換", type="primary", use_container_width=True):
            perform_swap(date1, role1, current1, date2, role2, current2)
            st.success("✅ 互換成功！")
            st.rerun()
    
    with col2:
        if st.button("📱 互換並通知雙方", type="secondary", use_container_width=True):
            perform_swap(date1, role1, current1, date2, role2, current2)
            
            # 發送通知
            if send_swap_notification(date1, role1, current1, date2, role2, current2):
                st.success("✅ 互換成功並已發送通知！")
            else:
                st.warning("⚠️ 互換成功但通知發送失敗")
            st.rerun()


def render_quick_clear():
    """快速清空功能"""
    st.markdown("### 🗑️ 快速清空")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 選擇醫師
        doctor_names = [d.name for d in st.session_state.doctors]
        selected_doctor = st.selectbox("選擇醫師", ["全部"] + doctor_names)
    
    with col2:
        # 選擇職位
        clear_role = st.selectbox("清空職位", ["全部", "主治醫師", "住院醫師"])
    
    # 顯示將被清空的班次數量
    count = count_shifts_to_clear(selected_doctor, clear_role)
    if count > 0:
        st.warning(f"⚠️ 將清空 {count} 個班次")
        
        if st.button("🗑️ 確認清空", type="primary", use_container_width=True):
            clear_shifts(selected_doctor, clear_role)
            st.success(f"✅ 已清空 {count} 個班次")
            st.rerun()
    else:
        st.info("沒有符合條件的班次")


def render_export_section(scheduler, weekdays, holidays):
    """渲染匯出區塊（只保留Excel和PDF）"""
    st.subheader("📤 匯出功能")
    
    # 使用調整後的班表
    final_schedule = st.session_state.get('adjusted_schedule', st.session_state.schedule_result.schedule)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 Excel 匯出")
        if st.button("產生 Excel 檔案", use_container_width=True):
            try:
                # 使用 ExcelCalendarExporter
                exporter = ExcelCalendarExporter(
                    schedule=final_schedule,
                    doctors=st.session_state.doctors,
                    weekdays=weekdays,
                    holidays=holidays,
                    year=st.session_state.selected_year,
                    month=st.session_state.selected_month
                )
                
                # 產生檔案
                output = io.BytesIO()
                filename = f"schedule_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.xlsx"
                
                # 直接寫入記憶體
                from openpyxl import Workbook
                wb = Workbook()
                exporter._create_calendar_sheet(wb)
                exporter._create_statistics_sheet(wb)
                exporter._create_doctors_sheet(wb)
                wb.save(output)
                output.seek(0)
                
                st.download_button(
                    label="📥 下載 Excel",
                    data=output.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                st.success("✅ Excel 檔案已產生")
            except Exception as e:
                st.error(f"產生 Excel 時發生錯誤：{str(e)}")
    
    with col2:
        st.markdown("### 📄 PDF 匯出")
        if st.button("產生 PDF 檔案", use_container_width=True):
            try:
                # 使用 PDFCalendarGenerator
                generator = PDFCalendarGenerator(
                    schedule=final_schedule,
                    doctors=st.session_state.doctors,
                    weekdays=weekdays,
                    holidays=holidays,
                    year=st.session_state.selected_year,
                    month=st.session_state.selected_month
                )
                
                # 產生檔案
                pdf_filename = f"schedule_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.pdf"
                generator.generate(pdf_filename)
                
                # 讀取並提供下載
                with open(pdf_filename, 'rb') as f:
                    pdf_data = f.read()
                
                st.download_button(
                    label="📥 下載 PDF",
                    data=pdf_data,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    use_container_width=True
                )
                st.success("✅ PDF 檔案已產生")
                
                # 清理暫存檔案
                if os.path.exists(pdf_filename):
                    os.remove(pdf_filename)
            except Exception as e:
                st.error(f"產生 PDF 時發生錯誤：{str(e)}")
    
    with col3:
        st.markdown("### 💾 儲存結果")
        if st.button("儲存排班結果", use_container_width=True):
            save_schedule_result(final_schedule)
            st.success("✅ 結果已儲存")


def render_line_settings():
    """LINE 對應設定（簡化版）"""
    st.subheader("📱 LINE 通知設定")
    
    # 初始化LINE對應管理
    if 'line_mappings' not in st.session_state:
        st.session_state.line_mappings = load_line_mappings()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 醫師 LINE 對應設定")
        st.info("💡 將醫師姓名對應到LINE群組中的顯示名稱，系統會自動標記(@)該用戶")
        
        # 建立對應表
        mappings_data = []
        for doctor in st.session_state.doctors:
            doctor_name = doctor.name
            current_line_name = st.session_state.line_mappings.get(doctor_name, "")
            mappings_data.append({
                '醫師姓名': doctor_name,
                'LINE顯示名稱': current_line_name
            })
        
        # 使用 data_editor 讓用戶編輯
        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "醫師姓名": st.column_config.TextColumn(
                    "醫師姓名",
                    disabled=True,
                    width="medium"
                ),
                "LINE顯示名稱": st.column_config.TextColumn(
                    "LINE顯示名稱 (@標記用)",
                    help="輸入該醫師在LINE群組中的顯示名稱",
                    width="large"
                )
            }
        )
        
        # 儲存按鈕
        if st.button("💾 儲存LINE對應設定", type="primary", use_container_width=True):
            # 更新對應
            new_mappings = {}
            for _, row in edited_df.iterrows():
                if row['LINE顯示名稱'].strip():
                    new_mappings[row['醫師姓名']] = row['LINE顯示名稱'].strip()
            
            st.session_state.line_mappings = new_mappings
            save_line_mappings(new_mappings)
            st.success("✅ LINE對應設定已儲存")
    
    with col2:
        st.markdown("### 快速操作")
        
        # 測試連線
        if st.button("🔌 測試LINE連線", use_container_width=True):
            client = get_line_bot_client()
            if client and client.test_connection():
                st.success("✅ LINE Bot 連線正常")
            else:
                st.error("❌ LINE Bot 連線失敗")
        
        # 發送測試訊息
        if st.button("📤 發送測試訊息", use_container_width=True):
            if send_test_message():
                st.success("✅ 測試訊息已發送")
            else:
                st.error("❌ 發送失敗")
        
        # 批次通知
        if st.button("📢 發送完整班表", use_container_width=True):
            if send_full_schedule():
                st.success("✅ 班表已發送到群組")
            else:
                st.error("❌ 發送失敗")
        
        st.divider()
        
        # 顯示對應統計
        mapped_count = sum(1 for v in st.session_state.line_mappings.values() if v)
        total_count = len(st.session_state.doctors)
        
        st.metric("對應完成度", f"{mapped_count}/{total_count}")
        
        if mapped_count < total_count:
            st.warning(f"⚠️ 尚有 {total_count - mapped_count} 位醫師未設定LINE名稱")


# === 輔助函數 ===

def format_date_option(date_str: str, holidays: List[str]) -> str:
    """格式化日期選項顯示"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_type = "假日" if date_str in holidays else "平日"
    weekday = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
    return f"{dt.month}/{dt.day} ({weekday}) {date_type}"

def get_current_doctor(date: str, role: str) -> Optional[str]:
    """獲取當前值班醫師"""
    schedule = st.session_state.adjusted_schedule.get(date)
    if schedule:
        return schedule.attending if role == "主治醫師" else schedule.resident
    return None

def perform_single_adjustment(date: str, role: str, new_doctor: Optional[str], old_doctor: Optional[str]):
    """執行單日調整（無限制）"""
    from backend.models import ScheduleSlot
    
    if date not in st.session_state.adjusted_schedule:
        st.session_state.adjusted_schedule[date] = ScheduleSlot(date=date)
    
    schedule = st.session_state.adjusted_schedule[date]
    
    if role == "主治醫師":
        schedule.attending = new_doctor
    else:
        schedule.resident = new_doctor
    
    # 記錄調整歷史
    if 'adjustment_history' not in st.session_state:
        st.session_state.adjustment_history = []
    
    st.session_state.adjustment_history.append({
        'timestamp': datetime.now().strftime("%m/%d %H:%M"),
        'type': 'single',
        'description': f"{date} {role}: {old_doctor or '空'} → {new_doctor or '空'}"
    })
    
    # 更新到 SessionManager
    from frontend.utils.session_manager import SessionManager
    SessionManager.update_final_schedule(
        st.session_state.adjusted_schedule,
        source_stage='manual_adjustment'
    )
    
def perform_swap(date1: str, role1: str, doctor1: Optional[str],
                date2: str, role2: str, doctor2: Optional[str]):
    """執行醫師互換（無限制）"""
    from backend.models import ScheduleSlot
    
    # 確保兩個日期都有排班記錄
    if date1 not in st.session_state.adjusted_schedule:
        st.session_state.adjusted_schedule[date1] = ScheduleSlot(date=date1)
    if date2 not in st.session_state.adjusted_schedule:
        st.session_state.adjusted_schedule[date2] = ScheduleSlot(date=date2)
    
    schedule1 = st.session_state.adjusted_schedule[date1]
    schedule2 = st.session_state.adjusted_schedule[date2]
    
    # 執行互換
    if role1 == "主治醫師":
        schedule1.attending = doctor2
    else:
        schedule1.resident = doctor2
    
    if role2 == "主治醫師":
        schedule2.attending = doctor1
    else:
        schedule2.resident = doctor1
    
    # 記錄調整歷史
    if 'adjustment_history' not in st.session_state:
        st.session_state.adjustment_history = []
    
    st.session_state.adjustment_history.append({
        'timestamp': datetime.now().strftime("%m/%d %H:%M"),
        'type': 'swap',
        'description': f"互換: {date1} {doctor1 or '空'} ↔ {date2} {doctor2 or '空'}"
    })

def count_shifts_to_clear(doctor_name: str, role: str) -> int:
    """計算將被清空的班次數量"""
    count = 0
    for slot in st.session_state.adjusted_schedule.values():
        if doctor_name == "全部" or doctor_name in [slot.attending, slot.resident]:
            if role == "全部":
                if slot.attending == doctor_name or doctor_name == "全部":
                    count += 1
                if slot.resident == doctor_name or doctor_name == "全部":
                    count += 1
            elif role == "主治醫師" and (slot.attending == doctor_name or doctor_name == "全部"):
                count += 1
            elif role == "住院醫師" and (slot.resident == doctor_name or doctor_name == "全部"):
                count += 1
    return count

def clear_shifts(doctor_name: str, role: str):
    """清空指定的班次"""
    for slot in st.session_state.adjusted_schedule.values():
        if doctor_name == "全部":
            if role in ["全部", "主治醫師"]:
                slot.attending = None
            if role in ["全部", "住院醫師"]:
                slot.resident = None
        else:
            if role in ["全部", "主治醫師"] and slot.attending == doctor_name:
                slot.attending = None
            if role in ["全部", "住院醫師"] and slot.resident == doctor_name:
                slot.resident = None
    
    # 記錄歷史
    if 'adjustment_history' not in st.session_state:
        st.session_state.adjustment_history = []
    
    st.session_state.adjustment_history.append({
        'timestamp': datetime.now().strftime("%m/%d %H:%M"),
        'type': 'clear',
        'description': f"清空 {doctor_name} 的 {role} 班次"
    })

def save_schedule_result(schedule: Dict):
    """儲存排班結果"""
    save_result = {
        'year': st.session_state.selected_year,
        'month': st.session_state.selected_month,
        'schedule': {k: {'date': v.date, 'attending': v.attending, 'resident': v.resident} 
                    for k, v in schedule.items()},
        'adjustment_history': st.session_state.get('adjustment_history', []),
        'saved_at': datetime.now().isoformat()
    }
    
    filename = f"data/schedules/schedule_result_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.json"
    
    os.makedirs("data/schedules", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(save_result, f, ensure_ascii=False, indent=2)

# === LINE 相關函數 ===

def load_line_mappings() -> Dict[str, str]:
    """載入LINE對應設定"""
    mapping_file = "data/configs/line_name_mappings.json"
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_line_mappings(mappings: Dict[str, str]):
    """儲存LINE對應設定"""
    os.makedirs("data/configs", exist_ok=True)
    mapping_file = "data/configs/line_name_mappings.json"
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)

def send_change_notification(date: str, role: str, old_doctor: Optional[str], new_doctor: Optional[str]) -> bool:
    """發送變更通知（使用@標記）"""
    client = get_line_bot_client()
    if not client:
        return False
    
    dt = datetime.strptime(date, "%Y-%m-%d")
    mappings = st.session_state.get('line_mappings', {})
    
    # 建立訊息
    message_lines = [
        f"📢 班表變更通知",
        f"日期：{dt.month}/{dt.day}",
        f"職位：{role}",
        f"變更：{old_doctor or '未排班'} → {new_doctor or '未排班'}",
        ""
    ]
    
    # 加入@標記
    mentions = []
    if old_doctor and old_doctor in mappings:
        mentions.append(f"@{mappings[old_doctor]}")
    if new_doctor and new_doctor in mappings:
        mentions.append(f"@{mappings[new_doctor]}")
    
    if mentions:
        message_lines.append("相關人員：" + " ".join(mentions))
    
    message = "\n".join(message_lines)
    
    try:
        response = client.broadcast_message(message)
        return response.get('success', False)
    except:
        return False

def send_swap_notification(date1: str, role1: str, doctor1: Optional[str],
                          date2: str, role2: str, doctor2: Optional[str]) -> bool:
    """發送互換通知（使用@標記）"""
    client = get_line_bot_client()
    if not client:
        return False
    
    dt1 = datetime.strptime(date1, "%Y-%m-%d")
    dt2 = datetime.strptime(date2, "%Y-%m-%d")
    mappings = st.session_state.get('line_mappings', {})
    
    # 建立訊息
    message_lines = [
        f"🔄 班次互換通知",
        f"",
        f"互換內容：",
        f"• {dt1.month}/{dt1.day} {role1}: {doctor1 or '空'} → {doctor2 or '空'}",
        f"• {dt2.month}/{dt2.day} {role2}: {doctor2 or '空'} → {doctor1 or '空'}",
        ""
    ]
    
    # 加入@標記
    mentions = []
    if doctor1 and doctor1 in mappings:
        mentions.append(f"@{mappings[doctor1]}")
    if doctor2 and doctor2 in mappings:
        mentions.append(f"@{mappings[doctor2]}")
    
    if mentions:
        message_lines.append("相關人員：" + " ".join(set(mentions)))
    
    message = "\n".join(message_lines)
    
    try:
        response = client.broadcast_message(message)
        return response.get('success', False)
    except:
        return False

def send_test_message() -> bool:
    """發送測試訊息"""
    client = get_line_bot_client()
    if not client:
        return False
    
    message = f"""
    🔔 LINE通知測試
    時間：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    系統：醫師智慧排班系統
    狀態：正常運作中
    """
    
    try:
        response = client.broadcast_message(message)
        return response.get('success', False)
    except:
        return False

def send_full_schedule() -> bool:
    """發送完整班表到群組"""
    client = get_line_bot_client()
    if not client:
        return False
    
    # 統計資訊
    schedule = st.session_state.adjusted_schedule
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 計算統計
    doctor_stats = {}
    for slot in schedule.values():
        if slot.attending:
            if slot.attending not in doctor_stats:
                doctor_stats[slot.attending] = 0
            doctor_stats[slot.attending] += 1
        if slot.resident:
            if slot.resident not in doctor_stats:
                doctor_stats[slot.resident] = 0
            doctor_stats[slot.resident] += 1
    
    # 建立訊息
    message_lines = [
        f"📅 {year}年{month}月 排班表發佈",
        f"",
        f"📊 統計摘要：",
        f"• 總天數：{len(schedule)}",
        f"• 參與醫師：{len(doctor_stats)}位",
        f"",
        f"👨‍⚕️ 值班次數排行："
    ]
    
    # 排序並顯示前5名
    sorted_doctors = sorted(doctor_stats.items(), key=lambda x: x[1], reverse=True)[:5]
    for i, (name, count) in enumerate(sorted_doctors, 1):
        message_lines.append(f"{i}. {name}: {count}次")
    
    message_lines.extend([
        "",
        "📥 詳細班表請至系統查看",
        f"🕐 發佈時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ])
    
    message = "\n".join(message_lines)
    
    try:
        response = client.broadcast_message(message)
        return response.get('success', False)
    except:
        return False

# 保留原有的視圖函數
def render_calendar_view(result, scheduler, weekdays, holidays):
    """渲染月曆視圖"""
    st.subheader("📅 月曆班表")
    
    # 使用調整後的班表
    display_schedule = st.session_state.get('adjusted_schedule', result.schedule)
    
    calendar_view = CalendarView(
        st.session_state.selected_year,
        st.session_state.selected_month
    )
    
    html_content = calendar_view.generate_html(
        display_schedule,
        scheduler,
        weekdays,
        holidays
    )
    
    st.markdown(html_content, unsafe_allow_html=True)
    
    # 顯示調整狀態
    if 'adjustment_history' in st.session_state and st.session_state.adjustment_history:
        st.info(f"📝 已有 {len(st.session_state.adjustment_history)} 項手動調整")

def render_list_view(result, scheduler, weekdays, holidays):
    """渲染列表視圖"""
    st.subheader("📋 列表班表")
    
    # 使用調整後的班表
    display_schedule = st.session_state.get('adjusted_schedule', result.schedule)
    
    schedule_table = ScheduleTable()
    df_schedule = schedule_table.create_dataframe(
        display_schedule,
        scheduler,
        weekdays,
        holidays
    )
    
    styled_df = schedule_table.apply_styles(df_schedule)
    st.dataframe(styled_df, use_container_width=True, height=600)