"""演算法參數設定元件"""

import streamlit as st
from backend.models import ScheduleConstraints


def render_algorithm_parameters():
    """渲染演算法參數設定區域"""
    st.subheader("⚙️ 演算法參數設定")

    # 取得或初始化 constraints
    if "constraints" not in st.session_state:
        st.session_state.constraints = ScheduleConstraints()

    constraints = st.session_state.constraints

    # 基本參數設定
    with st.expander("🔧 基本參數", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            constraints.max_consecutive_days = st.slider(
                "最大連續值班天數",
                min_value=1,
                max_value=5,
                value=constraints.max_consecutive_days,
                help="醫師最多可連續值班的天數限制",
            )

        with col2:
            constraints.beam_width = st.slider(
                "束搜索寬度",
                min_value=3,
                max_value=10,
                value=constraints.beam_width,
                help="Beam Search 保留的候選解數量，越大越精確但越慢",
            )

        with col3:
            constraints.csp_timeout = st.slider(
                "CSP超時(秒)",
                min_value=5,
                max_value=30,
                value=constraints.csp_timeout,
                help="CSP求解器的最大執行時間",
            )

    # 儲存更新的 constraints
    st.session_state.constraints = constraints

    # 顯示當前設定摘要
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("連續值班限制", f"{constraints.max_consecutive_days} 天")

    with col2:
        st.metric("束寬度", constraints.beam_width)

    with col3:
        st.metric("CSP超時", f"{constraints.csp_timeout} 秒")