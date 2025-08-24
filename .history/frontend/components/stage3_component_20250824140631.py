"""Stage 3 元件 - 增強版（含 Supabase 整合）"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar
import os
import json
from typing import Dict, List
from backend.algorithms.stage3_publish import Stage3Publisher
from backend.models import ScheduleSlot
from frontend.components.calendar_view import InteractiveCalendarView


def render_stage3(weekdays: list, holidays: list):
    """渲染 Stage 3: 確認與發佈"""
    st.subheader("📤 Stage 3: 確認與發佈")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 2")
        return

    # 初始化發佈器
    if "stage3_publisher" not in st.session_state:
        st.session_state.stage3_publisher = Stage3Publisher(
            schedule=st.session_state.stage2_schedule,
            doctors=st.session_state.doctors,
            weekdays=weekdays,
            holidays=holidays,
        )
    
    publisher = st.session_state.stage3_publisher

    # 顯示品質報告（移除未填格相關）
    report = publisher.quality_report

    # 品質評估卡片
    st.markdown("### 📊 排班品質評估")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 計算總班數
        total_shifts = sum(
            stats['total'] 
            for stats in report.statistics['doctor_duties'].values()
        )
        st.metric("總班數", total_shifts)
    
    with col2:
        # 計算公平性（標準差）
        import numpy as np
        duties = [stats['total'] for stats in report.statistics['doctor_duties'].values()]
        fairness = np.std(duties) if duties else 0
        st.metric("公平性指標", f"{fairness:.2f}", help="標準差越小越公平")
    
    with col3:
        # 偏好滿足率
        pref_stats = publisher._check_preference_satisfaction()
        satisfaction_rate = pref_stats.get('satisfaction_rate', 0)
        st.metric("偏好滿足率", f"{satisfaction_rate:.1%}")

    st.divider()

    # 班表預覽標籤
    st.markdown("### 📋 排班表預覽")
    
    preview_tabs = st.tabs(["📊 表格檢視", "📅 日曆檢視", "👥 依醫師檢視"])
    
    with preview_tabs[0]:
        render_table_view(publisher, weekdays, holidays)
    
    with preview_tabs[1]:
        render_calendar_view(publisher, weekdays, holidays)
    
    with preview_tabs[2]:
        render_doctor_view(publisher, weekdays, holidays)

    st.divider()

    # 詳細統計
    with st.expander("📈 詳細統計", expanded=False):
        render_statistics_charts(publisher)

    st.divider()

    # 匯出與發佈區
    st.markdown("### 📤 匯出與發佈")
    
    # 檢查 Supabase 連線（使用新的管理器）
    from backend.utils.supabase_client import get_supabase_manager
    
    manager = get_supabase_manager()
    if manager.get_status()['connected']:
        render_export_section(publisher, weekdays, holidays)
    else:
        st.warning("⚠️ Supabase 未設定，請在 .env 檔案中設定")
        with st.expander("查看設定說明", expanded=True):
            st.markdown("""
            ### 🔧 Supabase 設定步驟
            
            1. 在專案根目錄創建 `.env` 檔案
            2. 加入以下內容：
            ```
            SUPABASE_URL=https://ooxswwmexulfkgnnqsqb.supabase.co
            SUPABASE_ANON_KEY=您的_ANON_KEY
            SUPABASE_SERVICE_ROLE_KEY=您的_SERVICE_ROLE_KEY（選填）
            SUPABASE_BUCKET=schedules
            ```
            3. 重新啟動應用程式
            """)
            
            if st.button("重新檢查連線"):
                st.rerun()

    # 底部操作按鈕
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 返回 Stage 2", use_container_width=True):
            st.session_state.current_stage = 2
            st.rerun()
    
    with col2:
        if st.button("💾 儲存排班結果", use_container_width=True):
            save_schedule(publisher)
            st.success("✅ 排班結果已儲存")
    
    with col3:
        if st.button("✅ 確認完成", type="primary", use_container_width=True):
            st.success("🎉 排班流程完成！")
            st.balloons()
            # 清除狀態，準備下次排班
            if st.button("開始新的排班", use_container_width=True):
                reset_all_states()
                st.rerun()


def render_supabase_setup():
    """Supabase 設定介面"""
    st.markdown("""
    ### 🔧 Supabase 設定步驟
    
    1. 登入您的 [Supabase Dashboard](https://app.supabase.com)
    2. 選擇您的專案
    3. 在左側選單找到 **Settings** > **API**
    4. 複製以下資訊：
    """)
    
    # 輸入欄位
    url = st.text_input(
        "Project URL",
        placeholder="https://xxxxx.supabase.co",
        help="在 API Settings 中的 Project URL"
    )
    
    anon_key = st.text_input(
        "Anon/Public Key",
        type="password",
        placeholder="eyJhbGciOiJS...",
        help="在 API Settings 中的 anon public key"
    )
    
    service_key = st.text_input(
        "Service Role Key (選填)",
        type="password",
        placeholder="eyJhbGciOiJS...",
        help="如需更高權限操作，請提供 service_role key"
    )
    
    bucket_name = st.text_input(
        "Storage Bucket 名稱",
        value="schedules",
        help="用於儲存排班檔案的 bucket 名稱"
    )
    
    if st.button("連接 Supabase", type="primary"):
        if url and anon_key:
            try:
                from supabase import create_client, Client
                
                # 建立 Supabase client
                supabase: Client = create_client(url, anon_key)
                
                # 測試連線
                # 嘗試列出 buckets（可能需要權限）
                try:
                    buckets = supabase.storage.list_buckets()
                    st.success("✅ 成功連接到 Supabase！")
                    
                    # 檢查 bucket 是否存在
                    bucket_exists = any(b['name'] == bucket_name for b in buckets)
                    
                    if not bucket_exists:
                        st.info(f"📦 Bucket '{bucket_name}' 不存在，嘗試建立...")
                        # 建立 bucket
                        supabase.storage.create_bucket(
                            bucket_name,
                            options={
                                'public': False,  # 設為私有
                                'file_size_limit': 52428800,  # 50MB
                                'allowed_mime_types': ['application/pdf', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
                            }
                        )
                        st.success(f"✅ 成功建立 Bucket '{bucket_name}'")
                    else:
                        st.info(f"📦 使用現有的 Bucket '{bucket_name}'")
                    
                except Exception as e:
                    st.warning(f"無法列出 buckets（可能是權限問題）: {str(e)}")
                    st.info("將嘗試使用指定的 bucket 名稱")
                
                # 儲存到 session state
                st.session_state.supabase_client = supabase
                st.session_state.supabase_url = url
                st.session_state.supabase_bucket = bucket_name
                st.session_state.supabase_key = anon_key
                
                # 儲存設定到本地（選擇性）
                if st.checkbox("記住設定（儲存到本地）"):
                    save_supabase_config(url, anon_key, service_key, bucket_name)
                
                st.rerun()
                
            except Exception as e:
                st.error(f"連線失敗: {str(e)}")
                st.info("請確認您的 URL 和 API Key 是否正確")
        else:
            st.error("請填寫必要欄位")


def render_export_section(publisher, weekdays, holidays):
    """匯出與發佈區塊"""
    from backend.utils.supabase_client import get_supabase_manager
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Excel 匯出")
        if st.button("生成 Excel（日曆形式）", use_container_width=True):
            with st.spinner("生成中..."):
                filename = export_excel_calendar(publisher)
                
                with open(filename, "rb") as f:
                    st.download_button(
                        label="💾 下載 Excel",
                        data=f,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                st.success("✅ Excel 檔案已生成")
    
    with col2:
        st.markdown("#### 📄 PDF 發佈到雲端")
        if st.button("📤 生成並上傳 PDF", use_container_width=True, type="primary"):
            with st.spinner("生成 PDF 並上傳中..."):
                try:
                    # 生成 PDF
                    pdf_filename = generate_pdf_calendar(publisher)
                    
                    # 使用 Supabase Manager 上傳
                    manager = get_supabase_manager()
                    download_url = manager.upload_schedule_pdf(
                        pdf_filename,
                        st.session_state.selected_year,
                        st.session_state.selected_month
                    )
                    
                    if download_url:
                        st.success("✅ PDF 已上傳到雲端")
                        
                        # 顯示下載連結
                        st.markdown("### 📥 下載連結（30天有效）")
                        st.code(download_url)
                        
                        # 複製按鈕（使用 pyperclip 或瀏覽器 API）
                        st.markdown(f"""
                        <button onclick="navigator.clipboard.writeText('{download_url}')">
                        📋 複製連結到剪貼簿
                        </button>
                        """, unsafe_allow_html=True)
                        
                        # LINE 訊息
                        st.markdown("### 💬 LINE 訊息")
                        line_message = generate_line_message(publisher, download_url)
                        st.text_area(
                            "訊息內容（請手動複製）",
                            line_message,
                            height=200,
                            key="line_message"
                        )
                        
                        # 儲存紀錄
                        save_publish_record(download_url)
                    else:
                        st.error("PDF 上傳失敗，請檢查 Supabase 設定")
                        
                except Exception as e:
                    st.error(f"處理失敗: {str(e)}")


def upload_to_supabase(filename: str) -> str:
    """上傳檔案到 Supabase Storage 並返回簽名 URL"""
    try:
        supabase = st.session_state.supabase_client
        bucket = st.session_state.supabase_bucket
        
        # 生成儲存路徑
        year = st.session_state.selected_year
        month = st.session_state.selected_month
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        storage_path = f"{year}/{month:02d}/schedule_{year}{month:02d}_{timestamp}.pdf"
        
        # 讀取檔案
        with open(filename, 'rb') as f:
            file_data = f.read()
        
        # 上傳到 Supabase
        response = supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=file_data,
            file_options={"content-type": "application/pdf"}
        )
        
        # 生成簽名 URL（30天有效）
        expiry = 30 * 24 * 60 * 60  # 30天（秒）
        signed_url = supabase.storage.from_(bucket).create_signed_url(
            path=storage_path,
            expires_in=expiry
        )
        
        return signed_url['signedURL']
        
    except Exception as e:
        st.error(f"Supabase 上傳錯誤: {str(e)}")
        return None


def generate_pdf_calendar(publisher):
    """生成 PDF 日曆（使用 reportlab）"""
    from backend.utils.pdf_generator import PDFCalendarGenerator
    
    generator = PDFCalendarGenerator(
        schedule=publisher.schedule,
        doctors=publisher.doctors,
        weekdays=publisher.weekdays,
        holidays=publisher.holidays,
        year=st.session_state.selected_year,
        month=st.session_state.selected_month
    )
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"schedule_{timestamp}.pdf"
    
    generator.generate(filename)
    return filename


def generate_line_message(publisher, download_url):
    """生成 LINE 訊息"""
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 統計資訊
    stats = publisher.quality_report.statistics
    total_days = len(publisher.schedule)
    
    message = f"""📅 {year}年{month}月 排班表已完成

📊 排班統計：
• 總天數：{total_days} 天
• 平日：{len(publisher.weekdays)} 天  
• 假日：{len(publisher.holidays)} 天
• 參與醫師：{len(publisher.doctors)} 位

📥 下載連結（30天有效）：
{download_url}

⏰ 生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}

請各位醫師確認排班內容，如有問題請儘速反應。"""
    
    return message


def render_table_view(publisher, weekdays, holidays):
    """表格檢視"""
    df = publisher.export_to_dataframe()
    
    # 移除 (未排) 相關的處理，因為不會有未填格
    def highlight_schedule(row):
        styles = [''] * len(row)
        
        # 標記假日/平日
        if row['類型'] == '假日':
            styles[2] = 'background-color: #ffe4e1'
        else:
            styles[2] = 'background-color: #e6f2ff'
        
        # 主治醫師欄位
        styles[3] = 'background-color: #e8f5e9'
        
        # 總醫師欄位  
        styles[4] = 'background-color: #f3e5f5'
        
        return styles
    
    styled_df = df.style.apply(highlight_schedule, axis=1)
    
    # 顯示表格
    st.dataframe(
        styled_df,
        use_container_width=True,
        height=600
    )
    
    # 統計摘要
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"📅 總天數：{len(df)}")
    with col2:
        st.info(f"🏢 平日：{len([x for x in df['類型'] if x == '平日'])}")
    with col3:
        st.info(f"🎉 假日：{len([x for x in df['類型'] if x == '假日'])}")


def render_calendar_view(publisher, weekdays, holidays):
    """日曆檢視"""
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    
    # 創建互動式月曆（不需要 gap_details，因為沒有未填格）
    calendar_view = InteractiveCalendarView(year, month)
    
    calendar_view.render_interactive_calendar(
        schedule=publisher.schedule,
        doctors=publisher.doctors,
        weekdays=weekdays,
        holidays=holidays,
        gap_details={}  # 空的，因為沒有未填格
    )


def render_doctor_view(publisher, weekdays, holidays):
    """依醫師檢視"""
    
    # 選擇醫師
    doctor_names = [d.name for d in publisher.doctors]
    selected_doctor = st.selectbox(
        "選擇醫師",
        doctor_names,
        key="doctor_view_select"
    )
    
    if selected_doctor:
        doctor = next(d for d in publisher.doctors if d.name == selected_doctor)
        
        # 顯示醫師資訊
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("角色", doctor.role)
        with col2:
            st.metric("平日配額", doctor.weekday_quota)
        with col3:
            st.metric("假日配額", doctor.holiday_quota)
        
        # 統計該醫師的值班情況
        duty_dates = []
        weekday_count = 0
        holiday_count = 0
        
        for date_str, slot in publisher.schedule.items():
            if selected_doctor in [slot.attending, slot.resident]:
                duty_dates.append(date_str)
                if date_str in holidays:
                    holiday_count += 1
                else:
                    weekday_count += 1
        
        # 顯示統計
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總值班數", len(duty_dates))
        with col2:
            st.metric("平日值班", weekday_count)
        with col3:
            st.metric("假日值班", holiday_count)
        with col4:
            usage_rate = len(duty_dates) / max(doctor.weekday_quota + doctor.holiday_quota, 1) * 100
            st.metric("配額使用率", f"{usage_rate:.1f}%")
        
        # 顯示值班日期列表
        if duty_dates:
            st.markdown("#### 值班日期")
            
            # 創建值班日期表格
            duty_data = []
            for date_str in sorted(duty_dates):
                slot = publisher.schedule[date_str]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                weekday_names = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
                
                duty_data.append({
                    '日期': date_str,
                    '星期': weekday_names[date_obj.weekday()],
                    '類型': '假日' if date_str in holidays else '平日',
                    '職責': '主治' if slot.attending == selected_doctor else '總醫師',
                    '搭檔': slot.resident if slot.attending == selected_doctor else slot.attending
                })
            
            duty_df = pd.DataFrame(duty_data)
            st.dataframe(duty_df, use_container_width=True, height=400)
        else:
            st.info("該醫師本月無值班安排")


def render_statistics_charts(publisher):
    """渲染統計圖表"""
    
    # 準備資料
    stats = publisher.quality_report.statistics['doctor_duties']
    
    # 分離主治和總醫師
    attending_doctors = [d for d in publisher.doctors if d.role == "主治"]
    resident_doctors = [d for d in publisher.doctors if d.role == "總醫師"]
    
    # 創建兩個圖表
    col1, col2 = st.columns(2)
    
    with col1:
        # 主治醫師統計圖
        if attending_doctors:
            attending_data = []
            for doc in attending_doctors:
                if doc.name in stats:
                    attending_data.append({
                        '醫師': doc.name,
                        '平日班': stats[doc.name]['weekday'],
                        '假日班': stats[doc.name]['holiday']
                    })
            
            if attending_data:
                df_attending = pd.DataFrame(attending_data)
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='平日班',
                    x=df_attending['醫師'],
                    y=df_attending['平日班'],
                    marker_color='#3498db',
                    text=df_attending['平日班'],
                    textposition='auto',
                ))
                fig.add_trace(go.Bar(
                    name='假日班',
                    x=df_attending['醫師'],
                    y=df_attending['假日班'],
                    marker_color='#e74c3c',
                    text=df_attending['假日班'],
                    textposition='auto',
                ))
                
                fig.update_layout(
                    title='主治醫師值班統計',
                    xaxis_title='醫師',
                    yaxis_title='值班次數',
                    barmode='group',
                    height=400,
                    showlegend=True,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # 總醫師統計圖
        if resident_doctors:
            resident_data = []
            for doc in resident_doctors:
                if doc.name in stats:
                    resident_data.append({
                        '醫師': doc.name,
                        '平日班': stats[doc.name]['weekday'],
                        '假日班': stats[doc.name]['holiday']
                    })
            
            if resident_data:
                df_resident = pd.DataFrame(resident_data)
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='平日班',
                    x=df_resident['醫師'],
                    y=df_resident['平日班'],
                    marker_color='#2ecc71',
                    text=df_resident['平日班'],
                    textposition='auto',
                ))
                fig.add_trace(go.Bar(
                    name='假日班',
                    x=df_resident['醫師'],
                    y=df_resident['假日班'],
                    marker_color='#f39c12',
                    text=df_resident['假日班'],
                    textposition='auto',
                ))
                
                fig.update_layout(
                    title='總醫師值班統計',
                    xaxis_title='醫師',
                    yaxis_title='值班次數',
                    barmode='group',
                    height=400,
                    showlegend=True,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)


def export_excel_calendar(publisher):
    """匯出 Excel（日曆形式）"""
    from backend.utils.excel_exporter import ExcelCalendarExporter
    
    exporter = ExcelCalendarExporter(
        schedule=publisher.schedule,
        doctors=publisher.doctors,
        weekdays=publisher.weekdays,
        holidays=publisher.holidays,
        year=st.session_state.selected_year,
        month=st.session_state.selected_month
    )
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"schedule_calendar_{timestamp}.xlsx"
    
    exporter.export(filename)
    return filename


def save_schedule(publisher):
    """儲存排班結果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 儲存為 JSON
    save_data = {
        "metadata": {
            "created_at": timestamp,
            "year": st.session_state.selected_year,
            "month": st.session_state.selected_month,
            "fill_rate": publisher.quality_report.fill_rate
        },
        "schedule": {
            date: {
                "attending": slot.attending,
                "resident": slot.resident
            }
            for date, slot in publisher.schedule.items()
        },
        "statistics": publisher.quality_report.statistics
    }
    
    os.makedirs("data/schedules", exist_ok=True)
    filename = f"data/schedules/schedule_{st.session_state.selected_year}{st.session_state.selected_month:02d}_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    return filename


def save_supabase_config(url, anon_key, service_key, bucket):
    """儲存 Supabase 設定到本地"""
    config = {
        "url": url,
        "anon_key": anon_key,
        "service_key": service_key,
        "bucket": bucket
    }
    
    os.makedirs("data/configs", exist_ok=True)
    with open("data/configs/supabase_config.json", "w") as f:
        json.dump(config, f)


def save_publish_record(download_url):
    """儲存發佈紀錄"""
    record = {
        "published_at": datetime.now().isoformat(),
        "year": st.session_state.selected_year,
        "month": st.session_state.selected_month,
        "download_url": download_url,
        "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
    }
    
    os.makedirs("data/publish_history", exist_ok=True)
    filename = f"data/publish_history/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def reset_all_states():
    """重置所有狀態"""
    st.session_state.current_stage = 1
    st.session_state.stage1_results = None
    st.session_state.selected_solution = None
    st.session_state.stage2_schedule = None
    st.session_state.stage2_swapper = None
    st.session_state.stage3_publisher = None