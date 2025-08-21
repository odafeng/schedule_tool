"""
排班相關資料模型
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any



@dataclass
class ScheduleConstraints:
    """排班限制條件"""
    max_consecutive_days: int = 2  # 最大連續值班天數
    beam_width: int = 5  # 束搜索寬度
    csp_timeout: int = 10  # CSP求解超時（秒）
    neighbor_expansion: int = 10  # 鄰域展開上限

@dataclass
class ScheduleSlot:
    """排班格位"""
    date: str
    attending: Optional[str] = None  # 主治醫師
    resident: Optional[str] = None   # 住院醫師
    
    def is_fully_filled(self) -> bool:
        """檢查是否完全填滿"""
        return self.attending is not None and self.resident is not None
    
    def is_empty(self) -> bool:
        """檢查是否完全空白"""
        return self.attending is None and self.resident is None
    
@dataclass
class SchedulingState:
    """排班狀態"""
    schedule: Dict[str, ScheduleSlot]
    score: float
    filled_count: int
    unfilled_slots: List[Tuple[str, str]]  # (date, role)
    parent_id: Optional[str] = None
    generation_method: str = "greedy_beam"
    
    @property
    def fill_rate(self) -> float:
        total = len(self.schedule) * 2  # 每天2個位置
        return self.filled_count / total if total > 0 else 0
    
@dataclass
class ScheduleResult:
    """排班結果"""
    schedule: Dict[str, ScheduleSlot]  # date -> slot
    score: float
    unfilled_slots: List[Tuple[str, str]]  # [(date, role), ...]
    violations: Dict[str, List[str]]  # violation_type -> descriptions
    suggestions: List[str]
    statistics: Dict[str, Any]
    
    def get_fill_rate(self) -> float:
        """計算填充率"""
        total = self.statistics.get('total_slots', 0)
        filled = self.statistics.get('filled_slots', 0)
        return filled / total if total > 0 else 0