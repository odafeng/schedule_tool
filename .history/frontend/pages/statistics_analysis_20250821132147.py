"""
統計分析頁面
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict

from backend.utils import get_month_calendar

def render():
    """渲染統計分析頁面"""
    st.header("統計分析")
    
    if st.session_state.schedule_result is None:
        st.info("請先執行排班")
        return
    
    result = st.session_state.schedule_result
    
    # 值班次數統計
    render_duty_distribution(result)
    
    # 分數細項
    render_score_breakdown(result)
    
    # 配額使用率
    render_quota_usage(result)
    
    # 未填格分析
    if result.unfilled_slots:
        render_unfilled_analysis(result)

def render_duty_distribution(result):
    """渲染值班次數分布"""
    st.subheader("📊 值班次數分布")
    
    duty_counts = result.statistics.get('duty_counts', {})
    
    if duty_counts:
        # 分離主治和住院醫師
        attending_duties = {}
        resident_duties = {}
        
        for name, count in duty_counts.items():
            doctor = next((d for d in st.session_state.doctors if d.name == name), None)
            if doctor:
                if doctor.role == "主治":
                    attending_duties[name] = count
                else:
                    resident_duties[name] = count
        
        col1, col2 = st.columns(2)
        
        with col1:
            if attending_duties:
                fig_attending = px.bar(
                    x=list(attending_duties.keys()),
                    y=list(attending_duties.values()),
                    title="主治醫師值班次數",
                    labels={'x': '醫師', 'y': '值班次數'},
                    color_discrete_sequence=['#1f77b4']
                )
                fig_attending.update_layout(showlegend=False)
                st.plotly_chart(fig_attending, use_container_width=True)
        
        with col2:
            if resident_duties:
                fig_resident = px.bar(
                    x=list(resident_duties.keys()),
                    y=list(resident_duties.values()),
                    title="住院醫師值班次數",
                    labels={'x': '醫師', 'y': '值班次數'},
                    color_discrete_sequence=['#ff7f0e']
                )
                fig_resident.update_layout(showlegend=False)
                st.plotly_chart(fig_resident, use_container_width=True)

def render_score_breakdown(result):
    """渲染評分細項"""
    st.subheader("📈 評分細項")
    
    breakdown = result.statistics.get('score_breakdown', {})
    
    if breakdown:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("未填格", breakdown.get('unfilled', 0), 
                     "權重: -1000", delta_color="inverse")
        with col2:
            st.metric("硬違規", breakdown.get('hard_violations', 0),
                     "權重: -100", delta_color="inverse")
        with col3:
            st.metric("軟違規", breakdown.get('soft_violations', 0),
                     "權重: -10", delta_color="inverse")
        with col4:
            st.metric("公平性", f"{breakdown.get('fairness', 0):.1f}",
                     "權重: +5")
        with col5:
            st.metric("偏好命中", breakdown.get('preference_hits', 0),
                     "權重: +2")
        
        # 視覺化分數組成
        components = []
        values = []
        colors = []
        
        if breakdown.get('unfilled', 0) > 0:
            components.append('未填格')
            values.append(-1000 * breakdown['unfilled'])
            colors.append('#ff4444')
        
        if breakdown.get('hard_violations', 0) > 0:
            components.append('硬違規')
            values.append(-100 * breakdown['hard_violations'])
            colors.append('#ff8800')
        
        if breakdown.get('soft_violations', 0) > 0:
            components.append('軟違規')
            values.append(-10 * breakdown['soft_violations'])
            colors.append('#ffaa00')
        
        if breakdown.get('fairness', 0) > 0:
            components.append('公平性')
            values.append(5 * breakdown['fairness'])
            colors.append('#00aa00')
        
        if breakdown.get('preference_hits', 0) > 0:
            components.append('偏好')
            values.append(2 * breakdown['preference_hits'])
            colors.append('#0088ff')
        
        if components:
            fig = go.Figure(data=[
                go.Bar(
                    x=components,
                    y=values,
                    marker_color=colors,
                    text=values,
                    textposition='auto',
                )
            ])
            fig.update_layout(
                title="分數組成",
                yaxis_title="分數貢獻",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

def render_quota_usage(result):
    """渲染配額使用率"""
    st.subheader("📊 配額使用率")
    
    # 獲取月份資料
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    
    # 計算每個醫師的平日/假日班數
    doctor_stats = []
    
    for doc in st.session_state.doctors:
        weekday_count = 0
        holiday_count = 0
        
        for date_str, slot in result.schedule.items():
            if slot.attending == doc.name or slot.resident == doc.name:
                if date_str in holidays:
                    holiday_count += 1
                else:
                    weekday_count += 1
        
        doctor_stats.append({
            '醫師': doc.name,
            '角色': doc.role,
            '平日值班': weekday_count,
            '平日配額': doc.weekday_quota,
            '平日使用率': f"{weekday_count/doc.weekday_quota*100:.0f}%" if doc.weekday_quota > 0 else "0%",
            '假日值班': holiday_count,
            '假日配額': doc.holiday_quota,
            '假日使用率': f"{holiday_count/doc.holiday_quota*100:.0f}%" if doc.holiday_quota > 0 else "0%"
        })
    
    df_stats = pd.DataFrame(doctor_stats)
    st.dataframe(df_stats, use_container_width=True)

def render_unfilled_analysis(result):
    """渲染未填格分析"""
    st.subheader("⚠️ 未填格分析")
    
    # 獲取月份資料
    weekdays, holidays = get_month_calendar(
        st.session_state.selected_year,
        st.session_state.selected_month,
        st.session_state.holidays,
        st.session_state.workdays
    )
    
    unfilled_by_date = defaultdict(list)
    for date_str, role in result.unfilled_slots:
        unfilled_by_date[date_str].append(role)
    
    unfilled_summary = []
    for date_str, roles in unfilled_by_date.items():
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        unfilled_summary.append({
            '日期': f"{dt.month}/{dt.day}",
            '星期': ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()],
            '未填角色': ', '.join(roles),
            '類型': '假日' if date_str in holidays else '平日'
        })
    
    df_unfilled = pd.DataFrame(unfilled_summary)
    st.dataframe(df_unfilled, use_container_width=True)
    
    # 統計圖表
    col1, col2 = st.columns(2)
    
    with col1:
        # 按角色統計
        role_counts = defaultdict(int)
        for _, role in result.unfilled_slots:
            role_counts[role] += 1
        
        if role_counts:
            fig_role = px.pie(
                values=list(role_counts.values()),
                names=list(role_counts.keys()),
                title="未填格角色分布"
            )
            st.plotly_chart(fig_role, use_container_width=True)
    
    with col2:
        # 按類型統計
        type_counts = {'平日': 0, '假日': 0}
        for date_str, _ in result.unfilled_slots:
            if date_str in holidays:
                type_counts['假日'] += 1
            else:
                type_counts['平日'] += 1
        
        if any(type_counts.values()):
            fig_type = px.pie(
                values=list(type_counts.values()),
                names=list(type_counts.keys()),
                title="未填格日期類型分布"
            )
            st.plotly_chart(fig_type, use_container_width=True)