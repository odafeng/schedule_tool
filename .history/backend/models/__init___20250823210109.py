"""
資料模型模組
"""
# 先導入基礎模型（沒有相依性的）
from .doctor import Doctor

# 再導入 schedule 相關模型
from .schedule import (
    ScheduleSlot, 
    ScheduleResult, 
    ScheduleConstraints, 
    SchedulingState, 
    ScheduleQualityReport
)

# 最後導入依賴 schedule 的模型
from .solution import SolutionFeatures, SolutionRecord

__all__ = [
    'Doctor',
    'ScheduleSlot',
    'ScheduleResult', 
    'ScheduleConstraints',
    'SchedulingState',
    'ScheduleQualityReport',
    'SolutionFeatures',
    'SolutionRecord'
]