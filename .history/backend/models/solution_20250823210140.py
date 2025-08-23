"""
解決方案相關資料模型
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, TYPE_CHECKING

# 使用 TYPE_CHECKING 避免循環導入
if TYPE_CHECKING:
    from backend.models.schedule import ScheduleSlot
else:
    # 運行時直接導入
    try:
        from backend.models.schedule import ScheduleSlot
    except ImportError:
        # 如果導入失敗，創建一個臨時的 ScheduleSlot 類
        @dataclass
        class ScheduleSlot:
            date: str
            attending: Optional[str] = None
            resident: Optional[str] = None

@dataclass
class SolutionFeatures:
    """解的特徵向量（用於機器學習）"""
    # 基礎統計
    total_slots: int
    filled_slots: int
    unfilled_slots: int
    fill_rate: float
    
    # 違規統計
    hard_violations: int
    soft_violations: int
    consecutive_violations: int
    quota_violations: int
    unavailable_violations: int
    
    # 公平性指標
    duty_variance: float
    duty_std: float
    max_duty_diff: int
    gini_coefficient: float
    
    # 偏好滿足度
    preference_hits: int
    preference_rate: float
    
    # 分布特徵
    weekend_coverage_rate: float
    weekday_coverage_rate: float
    attending_fill_rate: float
    resident_fill_rate: float
    
    # 連續性特徵
    avg_consecutive_days: float
    max_consecutive_days: int
    isolated_duty_count: int
    
    # 負載平衡
    attending_workload_std: float
    resident_workload_std: float
    cross_role_balance: float
    
    def to_dict(self):
        """轉換為字典格式"""
        return asdict(self)
    
    def to_vector(self):
        """轉換為特徵向量"""
        return [
            self.fill_rate,
            self.hard_violations,
            self.soft_violations,
            self.duty_variance,
            self.duty_std,
            self.max_duty_diff,
            self.gini_coefficient,
            self.preference_rate,
            self.weekend_coverage_rate,
            self.weekday_coverage_rate,
            self.avg_consecutive_days,
            self.max_consecutive_days,
            self.attending_workload_std,
            self.resident_workload_std,
            self.cross_role_balance
        ]

@dataclass
class SolutionRecord:
    """解池中的單一解記錄"""
    solution_id: str
    timestamp: str
    schedule: Dict[str, ScheduleSlot]
    score: float
    features: SolutionFeatures
    grade: str  # S/A/B/C/D/F
    iteration: int
    parent_id: Optional[str] = None
    generation_method: str = "beam_search"  # beam_search/csp/manual
    
    def to_training_record(self):
        """轉換為訓練記錄"""
        record = {
            'solution_id': self.solution_id,
            'timestamp': self.timestamp,
            'score': self.score,
            'grade': self.grade,
            'iteration': self.iteration,
            'generation_method': self.generation_method
        }
        # 添加所有特徵
        record.update(self.features.to_dict())
        return record