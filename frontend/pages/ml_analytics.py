"""
ML訓練資料分析頁面
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

from backend.analyzers import GradingSystem

def render():
    """渲染ML分析頁面"""
    st.header("🤖 機器學習訓練資料管理")
    
    if st.session_state.last_scheduler is None or st.session_state.last_scheduler.solution_pool is None:
        st.info("請先執行排班並勾選「收集所有候選解」選項")
        return
    
    solution_pool = st.session_state.last_scheduler.solution_pool
    pool_metrics = solution_pool.get_diversity_metrics()
    
    # 解池概覽
    render_pool_overview(pool_metrics)
    
    # 等級分布
    render_grade_distribution(pool_metrics, solution_pool)
    
    # 特徵分析
    render_feature_analysis(solution_pool)
    
    # Top解展示
    render_top_solutions(solution_pool)
    
    # 訓練資料匯出
    render_export_section(solution_pool)
    
    # 訓練建議
    render_training_suggestions()

def render_pool_overview(pool_metrics):
    """渲染解池概覽"""
    st.subheader("📊 解池概覽")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總解數量", pool_metrics.get('pool_size', 0))
    with col2:
        st.metric("唯一解數量", pool_metrics.get('unique_schedules', 0))
    with col3:
        st.metric("平均分數", f"{pool_metrics.get('avg_score', 0):.1f}")
    with col4:
        st.metric("分數標準差", f"{pool_metrics.get('score_std', 0):.1f}")

def render_grade_distribution(pool_metrics, solution_pool):
    """渲染等級分布"""
    st.subheader("📈 解的等級分布")
    
    grade_dist = pool_metrics.get('grade_distribution', {})
    
    if grade_dist:
        # 準備等級說明
        grading_system = GradingSystem()
        grade_descriptions = {
            grade: grading_system.get_grade_description(grade)
            for grade in ['S', 'A', 'B', 'C', 'D', 'F']
        }
        
        # 顯示等級分布圖表
        grades = list(grade_dist.keys())
        counts = list(grade_dist.values())
        
        fig_grades = px.bar(
            x=grades,
            y=counts,
            title="解的等級分布",
            labels={'x': '等級', 'y': '數量'},
            color=grades,
            color_discrete_map={
                'S': '#FFD700',  # 金色
                'A': '#00FF00',  # 綠色
                'B': '#87CEEB',  # 天藍色
                'C': '#FFA500',  # 橙色
                'D': '#FF6347',  # 番茄紅
                'F': '#FF0000'   # 紅色
            }
        )
        st.plotly_chart(fig_grades, use_container_width=True)
        
        # 等級說明
        with st.expander("📖 等級說明", expanded=False):
            for grade, desc in grade_descriptions.items():
                if grade in grade_dist:
                    st.write(f"**{grade}級** ({grade_dist[grade]}個): {desc}")

def render_feature_analysis(solution_pool):
    """渲染特徵分析"""
    st.subheader("🔬 特徵分析")
    
    # 選擇要分析的等級
    available_grades = list(set(s.grade for s in solution_pool.solution_pool))
    
    if available_grades:
        selected_grades = st.multiselect(
            "選擇要分析的等級",
            available_grades,
            default=available_grades[:2] if len(available_grades) >= 2 else available_grades
        )
        
        if selected_grades:
            # 收集選定等級的解
            selected_solutions = []
            for grade in selected_grades:
                selected_solutions.extend(solution_pool.get_solutions_by_grade(grade))
            
            if selected_solutions:
                # 提取特徵
                feature_data = []
                for sol in selected_solutions:
                    feature_dict = sol.features.to_dict()
                    feature_dict['grade'] = sol.grade
                    feature_dict['score'] = sol.score
                    feature_data.append(feature_dict)
                
                df_features = pd.DataFrame(feature_data)
                
                # 顯示關鍵特徵對比
                col1, col2 = st.columns(2)
                
                with col1:
                    # 填充率對比
                    fig_fill = px.box(
                        df_features,
                        x='grade',
                        y='fill_rate',
                        title='填充率分布',
                        labels={'fill_rate': '填充率', 'grade': '等級'}
                    )
                    st.plotly_chart(fig_fill, use_container_width=True)
                
                with col2:
                    # 違規數對比
                    fig_viol = px.box(
                        df_features,
                        x='grade',
                        y='hard_violations',
                        title='硬違規數分布',
                        labels={'hard_violations': '違規數', 'grade': '等級'}
                    )
                    st.plotly_chart(fig_viol, use_container_width=True)
                
                # 特徵相關性熱圖
                with st.expander("🔥 特徵相關性熱圖", expanded=False):
                    # 選擇數值特徵
                    numeric_features = [
                        'fill_rate', 'hard_violations', 'soft_violations',
                        'duty_variance', 'duty_std', 'gini_coefficient',
                        'preference_rate', 'weekend_coverage_rate',
                        'weekday_coverage_rate', 'avg_consecutive_days'
                    ]
                    
                    corr_matrix = df_features[numeric_features].corr()
                    
                    fig_corr = px.imshow(
                        corr_matrix,
                        labels=dict(color="相關係數"),
                        title="特徵相關性矩陣",
                        color_continuous_scale='RdBu',
                        zmin=-1, zmax=1
                    )
                    st.plotly_chart(fig_corr, use_container_width=True)

def render_top_solutions(solution_pool):
    """渲染最佳解展示"""
    st.subheader("🏆 最佳解展示")
    
    top_n = st.slider("顯示前N個最佳解", 1, 20, 5)
    top_solutions = solution_pool.get_top_solutions(top_n)
    
    if top_solutions:
        solution_display = []
        for i, sol in enumerate(top_solutions, 1):
            solution_display.append({
                '排名': i,
                '解ID': sol.solution_id[:20] + "...",
                '分數': f"{sol.score:.1f}",
                '等級': sol.grade,
                '填充率': f"{sol.features.fill_rate*100:.1f}%",
                '硬違規': sol.features.hard_violations,
                '軟違規': sol.features.soft_violations,
                '偏好滿足': f"{sol.features.preference_rate*100:.1f}%",
                '生成方法': sol.generation_method,
                '迭代': sol.iteration
            })
        
        df_top = pd.DataFrame(solution_display)
        st.dataframe(df_top, use_container_width=True)

def render_export_section(solution_pool):
    """渲染訓練資料匯出"""
    st.subheader("💾 訓練資料匯出")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # CSV格式匯出
        if st.button("📥 匯出CSV訓練資料", use_container_width=True):
            csv_data = solution_pool.export_training_data(format="csv")
            if csv_data:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="下載CSV檔案",
                    data=csv_data,
                    file_name=f"ml_training_data_{timestamp}.csv",
                    mime="text/csv"
                )
                st.success("CSV訓練資料已準備好下載！")
    
    with col2:
        # JSON格式匯出
        if st.button("📥 匯出JSON訓練資料", use_container_width=True):
            json_data = solution_pool.export_training_data(format="json")
            if json_data:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="下載JSON檔案",
                    data=json_data,
                    file_name=f"ml_training_data_{timestamp}.json",
                    mime="application/json"
                )
                st.success("JSON訓練資料已準備好下載！")
    
    with col3:
        # 匯出統計報告
        if st.button("📊 生成分析報告", use_container_width=True):
            report = generate_analysis_report(solution_pool)
            st.download_button(
                label="下載分析報告",
                data=report,
                file_name=f"ml_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown"
            )
            st.success("分析報告已生成！")

def render_training_suggestions():
    """渲染訓練建議"""
    st.subheader("🎯 機器學習訓練建議")
    
    with st.expander("📚 如何使用這些資料訓練AI", expanded=False):
        st.markdown("""
        ### 1. **監督式學習：排班品質預測**
        ```python
        # 使用隨機森林預測排班品質
        from sklearn.ensemble import RandomForestRegressor
        
        X = df[feature_columns]  # 特徵
        y = df['score']          # 目標
        model = RandomForestRegressor()
        model.fit(X, y)
        ```
        
        ### 2. **強化學習：序列決策優化**
        - State: 當前部分排班狀態
        - Action: 選擇下一個醫師-日期配對
        - Reward: 基於評分函數的即時回饋
        
        ### 3. **深度學習：端到端排班**
        ```python
        # 使用Transformer模型
        import torch.nn as nn
        
        class ScheduleTransformer(nn.Module):
            def __init__(self):
                self.encoder = nn.TransformerEncoder(...)
                self.decoder = nn.Linear(...)
        ```
        
        ### 4. **特徵工程建議**
        - **時序特徵**：星期幾、月份、是否月初/月末
        - **歷史特徵**：醫師過去的排班模式
        - **交互特徵**：醫師間的相容性
        - **約束編碼**：將硬約束轉為特徵向量
        
        ### 5. **評估指標**
        - **準確率**：預測分數與實際分數的MAE
        - **可行性**：生成解的違規率
        - **多樣性**：解的特徵空間覆蓋度
        - **效率**：達到目標品質的迭代次數
        """)
    
    # 資料品質檢查
    st.subheader("✅ 資料品質檢查")
    
    if st.session_state.last_scheduler and st.session_state.last_scheduler.solution_pool:
        pool_metrics = st.session_state.last_scheduler.solution_pool.get_diversity_metrics()
        grade_dist = pool_metrics.get('grade_distribution', {})
        
        quality_checks = {
            "解池大小充足（>100）": pool_metrics.get('pool_size', 0) > 100,
            "等級分布平衡": len(grade_dist) >= 3 if grade_dist else False,
            "特徵多樣性良好（>0.1）": pool_metrics.get('feature_diversity', 0) > 0.1,
            "包含優質解（S/A級）": any(g in ['S', 'A'] for g in grade_dist.keys()) if grade_dist else False,
            "包含失敗案例（D/F級）": any(g in ['D', 'F'] for g in grade_dist.keys()) if grade_dist else False
        }
        
        for check, passed in quality_checks.items():
            if passed:
                st.success(f"✅ {check}")
            else:
                st.warning(f"⚠️ {check}")
        
        overall_quality = sum(quality_checks.values()) / len(quality_checks)
        st.progress(overall_quality)
        st.write(f"整體資料品質：{overall_quality*100:.0f}%")

def generate_analysis_report(solution_pool):
    """生成分析報告"""
    pool_metrics = solution_pool.get_diversity_metrics()
    grade_dist = pool_metrics.get('grade_distribution', {})
    top_solutions = solution_pool.get_top_solutions(5)
    
    report = f"""
# 醫師排班ML訓練資料分析報告
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 解池統計
- 總解數量：{pool_metrics.get('pool_size', 0)}
- 唯一解數量：{pool_metrics.get('unique_schedules', 0)}
- 平均分數：{pool_metrics.get('avg_score', 0):.2f}
- 分數標準差：{pool_metrics.get('score_std', 0):.2f}
- 特徵多樣性：{pool_metrics.get('feature_diversity', 0):.4f}

## 等級分布
"""
    
    for grade, count in grade_dist.items():
        percentage = (count / pool_metrics['pool_size']) * 100
        report += f"- {grade}級：{count}個 ({percentage:.1f}%)\n"
    
    report += """
## 最佳解特徵
"""
    
    if top_solutions:
        best = top_solutions[0]
        report += f"""
- 分數：{best.score:.1f}
- 填充率：{best.features.fill_rate*100:.1f}%
- 硬違規：{best.features.hard_violations}
- 軟違規：{best.features.soft_violations}
- 偏好滿足率：{best.features.preference_rate*100:.1f}%
- 公平性（Gini係數）：{best.features.gini_coefficient:.3f}

## 建議
根據解池分析，建議：
1. 重點優化{'填充率' if pool_metrics['avg_score'] < -500 else '公平性'}
2. 考慮{'放寬約束' if grade_dist.get('F', 0) > pool_metrics['pool_size']*0.3 else '維持當前約束'}
3. {'增加醫師配額' if top_solutions[0].features.fill_rate < 0.9 else '當前配額合理'}
"""
    
    return report