"""演算法參數設定元件 - 極簡版"""

import streamlit as st
from backend.models import ScheduleConstraints


def render_algorithm_parameters():
    """渲染演算法參數設定區域（只有連續值班限制）"""
    st.subheader("⚙️ 排班規則設定")

    # 取得或初始化 constraints
    if "constraints" not in st.session_state:
        # 初始化時就設定固定值
        st.session_state.constraints = ScheduleConstraints(
            max_consecutive_days=2,
            beam_width=10,  # 固定為 10（內部使用）
            csp_timeout=30  # 固定為 30（內部使用）
        )

    constraints = st.session_state.constraints

    # 只顯示連續值班天數設定
    st.info("📌 設定醫師連續值班的限制，避免過度疲勞")
    
    constraints.max_consecutive_days = st.slider(
        "**最大連續值班天數**",
        min_value=1,
        max_value=5,
        value=constraints.max_consecutive_days,
        help="醫師最多可連續值班的天數。建議設定為 2-3 天以維持工作品質。",
        format_func=lambda x: f"{x} 天"
    )
    
    # 確保固定值不被改變（內部使用）
    constraints.beam_width = 10
    constraints.csp_timeout = 30

    # 儲存更新的 constraints
    st.session_state.constraints = constraints

    # 顯示當前設定的影響說明
    if constraints.max_consecutive_days == 1:
        st.warning("⚠️ 設定為 1 天表示醫師不能連續值班，這可能會讓排班變得困難")
    elif constraints.max_consecutive_days >= 4:
        st.warning("⚠️ 允許連續值班 4 天以上可能會造成醫師過度疲勞")
    else:
        st.success(f"✅ 醫師最多可連續值班 {constraints.max_consecutive_days} 天")