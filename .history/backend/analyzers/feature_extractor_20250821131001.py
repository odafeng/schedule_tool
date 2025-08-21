"""
特徵提取器
"""
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
import numpy as np

from ..models import Doctor, ScheduleSlot, ScheduleConstraints, SolutionFeatures

class FeatureExtractor:
    """特徵提取器"""
    
    def extract_features(self, schedule: Dict[str, ScheduleSlot],
                         doctors: List[Doctor], 
                         constraints: ScheduleConstraints,
                         weekdays: List[str], 
                         holidays: List[str]) -> SolutionFeatures:
        """從排班解中提取特徵"""
        
        # 基礎統計
        total_slots = len(schedule) * 2  # 每天2個角色
        filled_slots = sum(
            1 for slot in schedule.values() 
            for val in [slot.attending, slot.resident] 
            if val
        )
        unfilled_slots = total_slots - filled_slots
        fill_rate = filled_slots / total_slots if total_slots > 0 else 0
        
        # 值班統計
        duty_counts = defaultdict(int)
        weekday_duties = defaultdict(int)
        holiday_duties = defaultdict(int)
        
        # 違規統計
        hard_violations = 0
        unavailable_violations = 0
        quota_violations = 0
        consecutive_violations = 0
        preference_hits = 0
        total_preferences = 0
        
        # 遍歷排班
        for date_str, slot in schedule.items():
            is_holiday = date_str in holidays
            
            # 處理主治醫師
            if slot.attending:
                duty_counts[slot.attending] += 1
                if is_holiday:
                    holiday_duties[slot.attending] += 1
                else:
                    weekday_duties[slot.attending] += 1
                
                # 檢查違規和偏好
                doc = next((d for d in doctors if d.name == slot.attending), None)
                if doc:
                    if date_str in doc.unavailable_dates:
                        unavailable_violations += 1
                        hard_violations += 1
                    if date_str in doc.preferred_dates:
                        preference_hits += 1
                    total_preferences += len(doc.preferred_dates)
            
            # 處理住院醫師
            if slot.resident:
                duty_counts[slot.resident] += 1
                if is_holiday:
                    holiday_duties[slot.resident] += 1
                else:
                    weekday_duties[slot.resident] += 1
                
                doc = next((d for d in doctors if d.name == slot.resident), None)
                if doc:
                    if date_str in doc.unavailable_dates:
                        unavailable_violations += 1
                        hard_violations += 1
                    if date_str in doc.preferred_dates:
                        preference_hits += 1
                    total_preferences += len(doc.preferred_dates)
        
        # 檢查配額違規
        for doc in doctors:
            if weekday_duties[doc.name] > doc.weekday_quota:
                quota_violations += weekday_duties[doc.name] - doc.weekday_quota
                hard_violations += quota_violations
            if holiday_duties[doc.name] > doc.holiday_quota:
                quota_violations += holiday_duties[doc.name] - doc.holiday_quota
                hard_violations += quota_violations
        
        # 計算連續值班
        consecutive_days = self._calculate_consecutive_days(schedule, doctors)
        avg_consecutive = np.mean(consecutive_days) if consecutive_days else 0
        max_consecutive = max(consecutive_days) if consecutive_days else 0
        consecutive_violations = sum(1 for c in consecutive_days 
                                    if c > constraints.max_consecutive_days)
        
        # 公平性指標
        duties_list = list(duty_counts.values())
        duty_variance = np.var(duties_list) if duties_list else 0
        duty_std = np.std(duties_list) if duties_list else 0
        max_duty_diff = (max(duties_list) - min(duties_list)) if duties_list else 0
        gini = self._calculate_gini_coefficient(duties_list)
        
        # 覆蓋率
        weekend_filled = sum(
            1 for date_str in holidays 
            if date_str in schedule 
            for val in [schedule[date_str].attending, schedule[date_str].resident]
            if val
        )
        weekend_total = len(holidays) * 2
        weekend_coverage = weekend_filled / weekend_total if weekend_total > 0 else 0
        
        weekday_filled = sum(
            1 for date_str in weekdays 
            if date_str in schedule 
            for val in [schedule[date_str].attending, schedule[date_str].resident]
            if val
        )
        weekday_total = len(weekdays) * 2
        weekday_coverage = weekday_filled / weekday_total if weekday_total > 0 else 0
        
        # 角色平衡
        attending_duties = [duty_counts[d.name] for d in doctors if d.role == "主治"]
        resident_duties = [duty_counts[d.name] for d in doctors if d.role == "總醫師"]
        attending_std = np.std(attending_duties) if attending_duties else 0
        resident_std = np.std(resident_duties) if resident_duties else 0
        
        avg_attending = np.mean(attending_duties) if attending_duties else 0
        avg_resident = np.mean(resident_duties) if resident_duties else 0
        cross_balance = abs(avg_attending - avg_resident) / max(avg_attending, avg_resident, 1)
        
        # 計算孤立值班
        isolated_count = self._count_isolated_duties(schedule)
        
        return SolutionFeatures(
            total_slots=total_slots,
            filled_slots=filled_slots,
            unfilled_slots=unfilled_slots,
            fill_rate=fill_rate,
            hard_violations=hard_violations,
            soft_violations=consecutive_violations,
            consecutive_violations=consecutive_violations,
            quota_violations=quota_violations,
            unavailable_violations=unavailable_violations,
            duty_variance=duty_variance,
            duty_std=duty_std,
            max_duty_diff=max_duty_diff,
            gini_coefficient=gini,
            preference_hits=preference_hits,
            preference_rate=preference_hits/total_preferences if total_preferences > 0 else 0,
            weekend_coverage_rate=weekend_coverage,
            weekday_coverage_rate=weekday_coverage,
            attending_fill_rate=sum(1 for s in schedule.values() if s.attending) / len(schedule),
            resident_fill_rate=sum(1 for s in schedule.values() if s.resident) / len(schedule),
            avg_consecutive_days=avg_consecutive,
            max_consecutive_days=max_consecutive,
            isolated_duty_count=isolated_count,
            attending_workload_std=attending_std,
            resident_workload_std=resident_std,
            cross_role_balance=cross_balance
        )
    
    def _calculate_consecutive_days(self, schedule: Dict[str, ScheduleSlot], 
                                   doctors: List[Doctor]) -> List[int]:
        """計算每個醫師的連續值班天數"""
        consecutive_list = []
        
        for doc in doctors:
            dates = sorted([
                date_str for date_str, slot in schedule.items()
                if slot.attending == doc.name or slot.resident == doc.name
            ])
            
            if not dates:
                continue
            
            current_streak = 1
            for i in range(1, len(dates)):
                curr_date = datetime.strptime(dates[i], "%Y-%m-%d")
                prev_date = datetime.strptime(dates[i-1], "%Y-%m-%d")
                
                if (curr_date - prev_date).days == 1:
                    current_streak += 1
                else:
                    consecutive_list.append(current_streak)
                    current_streak = 1
            
            consecutive_list.append(current_streak)
        
        return consecutive_list
    
    def _calculate_gini_coefficient(self, values: List[float]) -> float:
        """計算基尼係數（衡量不平等程度）"""
        if not values or len(values) < 2:
            return 0
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        cumsum = np.cumsum(sorted_values)
        
        return (2 * np.sum((np.arange(1, n+1)) * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n
    
    def _count_isolated_duties(self, schedule: Dict[str, ScheduleSlot]) -> int:
        """計算孤立值班數（前後都沒班）"""
        isolated = 0
        sorted_dates = sorted(schedule.keys())
        
        for i, date_str in enumerate(sorted_dates):
            slot = schedule[date_str]
            
            for doctor_name in [slot.attending, slot.resident]:
                if not doctor_name:
                    continue
                
                # 檢查前一天
                has_prev = False
                if i > 0:
                    prev_slot = schedule[sorted_dates[i-1]]
                    if prev_slot.attending == doctor_name or prev_slot.resident == doctor_name:
                        has_prev = True
                
                # 檢查後一天
                has_next = False
                if i < len(sorted_dates) - 1:
                    next_slot = schedule[sorted_dates[i+1]]
                    if next_slot.attending == doctor_name or next_slot.resident == doctor_name:
                        has_next = True
                
                if not has_prev and not has_next:
                    isolated += 1
        
        return isolated