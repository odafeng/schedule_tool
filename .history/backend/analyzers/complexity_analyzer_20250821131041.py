"""
問題複雜度分析器
"""
from typing import List, Dict, Tuple
import numpy as np

from ..models import Doctor

class ComplexityAnalyzer:
    """分析排班問題的複雜度"""
    
    def analyze(self, doctors: List[Doctor], weekdays: List[str], 
                holidays: List[str]) -> Dict:
        """
        分析排班問題的複雜度
        
        Returns:
            複雜度分析結果
        """
        total_days = len(weekdays) + len(holidays)
        total_slots = total_days * 2  # 每天2個角色
        
        attending_doctors = [d for d in doctors if d.role == "主治"]
        resident_doctors = [d for d in doctors if d.role == "總醫師"]
        
        # 計算供需比
        total_weekday_supply = sum(d.weekday_quota for d in doctors)
        total_holiday_supply = sum(d.holiday_quota for d in doctors)
        weekday_demand = len(weekdays) * 2
        holiday_demand = len(holidays) * 2
        
        weekday_ratio = total_weekday_supply / weekday_demand if weekday_demand > 0 else 0
        holiday_ratio = total_holiday_supply / holiday_demand if holiday_demand > 0 else 0
        
        # 計算約束密度
        total_unavailable = sum(len(d.unavailable_dates) for d in doctors)
        constraint_density = total_unavailable / (len(doctors) * total_days) if len(doctors) > 0 else 0
        
        # 計算搜索空間大小（對數值）
        search_space_size = np.log10(max(1, len(attending_doctors) ** len(weekdays + holidays) * 
                                         len(resident_doctors) ** len(weekdays + holidays)))
        
        # 評估難度等級
        difficulty = self._assess_difficulty(
            weekday_ratio, holiday_ratio, constraint_density, search_space_size
        )
        
        return {
            'total_days': total_days,
            'total_slots': total_slots,
            'attending_count': len(attending_doctors),
            'resident_count': len(resident_doctors),
            'weekday_supply_ratio': weekday_ratio,
            'holiday_supply_ratio': holiday_ratio,
            'constraint_density': constraint_density,
            'search_space_log10': search_space_size,
            'difficulty': difficulty,
            'is_feasible': self._check_feasibility(weekday_ratio, holiday_ratio),
            'bottlenecks': self._identify_bottlenecks(doctors, weekdays, holidays)
        }
    
    def _assess_difficulty(self, weekday_ratio: float, holiday_ratio: float,
                          constraint_density: float, search_space: float) -> str:
        """評估問題難度"""
        score = 0
        
        # 供需比評分
        if weekday_ratio < 1.2 or holiday_ratio < 1.2:
            score += 3  # 供給緊張
        elif weekday_ratio < 1.5 or holiday_ratio < 1.5:
            score += 2
        elif weekday_ratio < 2.0 or holiday_ratio < 2.0:
            score += 1
        
        # 約束密度評分
        if constraint_density > 0.3:
            score += 3  # 約束很多
        elif constraint_density > 0.2:
            score += 2
        elif constraint_density > 0.1:
            score += 1
        
        # 搜索空間評分
        if search_space > 50:
            score += 3  # 搜索空間巨大
        elif search_space > 30:
            score += 2
        elif search_space > 20:
            score += 1
        
        # 判定難度
        if score >= 7:
            return "極困難"
        elif score >= 5:
            return "困難"
        elif score >= 3:
            return "中等"
        else:
            return "簡單"
    
    def _check_feasibility(self, weekday_ratio: float, holiday_ratio: float) -> bool:
        """檢查問題是否可行"""
        return weekday_ratio >= 1.0 and holiday_ratio >= 1.0
    
    def _identify_bottlenecks(self, doctors: List[Doctor], 
                             weekdays: List[str], holidays: List[str]) -> List[str]:
        """識別瓶頸"""
        bottlenecks = []
        
        attending = [d for d in doctors if d.role == "主治"]
        resident = [d for d in doctors if d.role == "總醫師"]
        
        # 檢查角色平衡
        if len(attending) < len(weekdays + holidays) / 5:
            bottlenecks.append("主治醫師人數不足")
        if len(resident) < len(weekdays + holidays) / 5:
            bottlenecks.append("住院醫師人數不足")
        
        # 檢查配額
        avg_weekday_quota = np.mean([d.weekday_quota for d in doctors])
        avg_holiday_quota = np.mean([d.holiday_quota for d in doctors])
        
        if avg_weekday_quota < 3:
            bottlenecks.append("平日配額偏低")
        if avg_holiday_quota < 1:
            bottlenecks.append("假日配額偏低")
        
        # 檢查約束衝突
        for d in doctors:
            conflict_ratio = len(d.unavailable_dates) / len(weekdays + holidays)
            if conflict_ratio > 0.5:
                bottlenecks.append(f"{d.name}的不可值班日過多")
        
        return bottlenecks