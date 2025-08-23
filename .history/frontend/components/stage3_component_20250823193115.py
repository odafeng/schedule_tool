"""Stage 3 元件"""

import streamlit as st
from backend.algorithms.stage3_publish import Stage3Publisher


def render_stage3(weekdays: list, holidays: list):
    """渲染 Stage 3: 確認與發佈"""
    st.subheader("📤 Stage 3: 確認與發佈")

    if not st.session_state.stage2_schedule:
        st.error("請先完成 Stage 2")
        return

    # 初始化發佈器
    publisher = Stage3Publisher(
        schedule=st.session_state.stage2_schedule,
        doctors=st.session_state.doctors,
        weekdays=weekdays,
        holidays=holidays,
    )

    # 顯示品質報告
    report = publisher.quality_report

    # 接受度等級
    acceptance_colors = {
        "Ideal": "success",
        "Acceptable": "warning",
        "Needs discussion": "error",
    }

    st.markdown(f"### 📊 排班品質評估")

    col1, col2, col3 = st.columns(3)

    with col1:
        color = acceptance_colors.get(report.acceptance_level, "info")
        if color == "success":
            st.success(f"⭐ 接受度：{report.acceptance_level}")
        elif color == "warning":
            st.warning(f"⭐ 接受度：{report.acceptance_level}")
        else:
            st.error(f"⭐ 接受度：{report.acceptance_level}")

    with col2:
        st.metric("填充率", f"{report.fill_rate:.1%}")

    with col3:
        st.metric("總問題數", report.total_issues)

    # 顯示問題清單
    if report.critical_issues or report.minor_issues:
        st.markdown("### ⚠️ 問題清單")

        if report.critical_issues:
            with st.expander(
                f"🔴 重要問題 ({len(report.critical_issues)})", expanded=True
            ):
                for issue in report.critical_issues:
                    st.error(f"• {issue}")

        if report.minor_issues:
            with st.expander(
                f"🟡 次要問題 ({len(report.minor_issues)})", expanded=False
            ):
                for issue in report.minor_issues:
                    st.warning(f"• {issue}")

    # 預覽排班表
    st.markdown("### 📋 排班表預覽")
    df = publisher.export_to_dataframe()
    st.dataframe(df, use_container_width=True)

    # 統計資訊
    with st.expander("📊 詳細統計", expanded=False):
        stats_df = publisher._create_statistics_df()
        st.dataframe(stats_df, use_container_width=True)

    # 匯出選項
    st.markdown("### 📥 匯出與發佈")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 匯出 Excel", use_container_width=True):
            filename = publisher.export_to_excel()
            with open(filename, "rb") as f:
                st.download_button(
                    label="💾 下載 Excel",
                    data=f,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            st.success(f"✅ 已生成 Excel 檔案")

    with col2:
        if st.button("📄 匯出 PDF", use_container_width=True):
            st.info("PDF 匯出功能開發中...")

    with col3:
        if st.button("📤 發佈到 LINE", use_container_width=True):
            message = publisher.generate_summary_message()
            st.text_area("LINE 訊息預覽：", message, height=200)
            st.info("LINE 推播功能需要設定 LINE Notify Token")

    # 完成選項
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 返回 Stage 2 修改", use_container_width=True):
            st.session_state.current_stage = 2
            st.rerun()

    with col2:
        if st.button("✅ 確認並結束", type="primary", use_container_width=True):
            st.success("🎉 排班流程完成！")
            st.balloons()
            # 清除狀態，準備下次排班
            st.session_state.current_stage = 1
            st.session_state.stage1_results = None
            st.session_state.selected_solution = None
            st.session_state.stage2_schedule = None
            st.session_state.stage2_swapper = None