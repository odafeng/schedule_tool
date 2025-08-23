"""階段進度顯示元件"""

import streamlit as st


def render_stage_progress():
    """顯示階段進度"""
    stages = ["Stage 1: 快速排班", "Stage 2: 智慧補洞", "Stage 3: 確認發佈"]
    current = st.session_state.current_stage - 1

    # 使用進度條顯示
    progress = (current + 1) / 3
    st.progress(progress)

    # 顯示階段標籤
    cols = st.columns(3)
    for i, (col, stage) in enumerate(zip(cols, stages)):
        with col:
            if i < current:
                st.success(f"✅ {stage}")
            elif i == current:
                st.info(f"🔄 {stage}")
            else:
                st.text(f"⏳ {stage}")