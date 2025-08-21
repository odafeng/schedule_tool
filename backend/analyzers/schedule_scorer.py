"""
排班評分系統
"""
from typing import Dict, Tuple, List
from collections import defaultdict
import numpy as np

from ..models import Doctor, ScheduleSlot

class ScheduleScorer:
    """排班方案評分器"""
    
    def __init__(self, doctors: List[Doctor], weekdays: List[str], holidays: List[str]):
        self.doctors = doctors
        self.weekdays = weekdays
        self.holidays = holidays
        self.doctor_map = {d.name: d for d in doctors}
    
    def calculate_score(self, schedule: Dict[str, ScheduleSlot]) -> float:
        """
        計算排班方案分數
        Score = -1000*U -100*HardViol -10*SoftViol + 5*Fairness + 2*PreferenceHits
        """
        stats = self.get_statistics(schedule)
        
        score = (-1000 * stats['unfilled'] 
                 -100 * stats['hard_violations'] 
                 -10 * stats['soft_violations'] 
                 + 5 * stats['fairness'] 
                 + 2 * stats['preference_hits'])
        
        return score
    
    def get_statistics(self, schedule: Dict[str, ScheduleSlot]) -> Dict:
        """計算詳細統計資料"""
        stats = {
            'unfilled': 0,
            'hard_violations': 0,
            'soft_violations': 0,
            'fairness': 0,
            'preference_hits': 0,
            'total_slots': len(schedule) * 2,
            'filled_slots': 0,
            'duty_counts': {}
        }
        
        # 計算未填格數
        for date_str in self.weekdays + self.holidays:
            if date_str in schedule:
                slot = schedule[date_str]
                if not slot.attending:
                    stats['unfilled'] += 1
                else:
                    stats['filled_slots'] += 1
                if not slot.resident:
                    stats['unfilled'] += 1
                else:
                    stats['filled_slots'] += 1
            else:
                stats['unfilled'] += 2
        
        # 計算違規數和偏好命中
        duty_counts = defaultdict(int)
        weekday_counts = defaultdict(int)
        holiday_counts = defaultdict(int)
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            
            # 統計值班次數
            if slot.attending:
                duty_counts[slot.attending] += 1
                if is_holiday:
                    holiday_counts[slot.attending] += 1
                else:
                    weekday_counts[slot.attending] += 1
                    
                # 檢查違規
                doc = self.doctor_map.get(slot.attending)
                if doc:
                    if date_str in doc.unavailable_dates:
                        stats['hard_violations'] += 1
                    if date_str in doc.preferred_dates:
                        stats['preference_hits'] += 1
                    
            if slot.resident:
                duty_counts[slot.resident] += 1
                if is_holiday:
                    holiday_counts[slot.resident] += 1
                else:
                    weekday_counts[slot.resident] += 1
                    
                doc = self.doctor_map.get(slot.resident)
                if doc:
                    if date_str in doc.unavailable_dates:
                        stats['hard_violations'] += 1
                    if date_str in doc.preferred_dates:
                        stats['preference_hits'] += 1
        
        # 檢查配額違規
        for name, doc in self.doctor_map.items():
            if weekday_counts[name] > doc.weekday_quota:
                stats['hard_violations'] += (weekday_counts[name] - doc.weekday_quota)
            if holiday_counts[name] > doc.holiday_quota:
                stats['hard_violations'] += (holiday_counts[name] - doc.holiday_quota)
        
        # 計算公平性（使用標準差的反向值）
        if duty_counts:
            values = list(duty_counts.values())
            mean_duty = np.mean(values)
            std_duty = np.std(values)
            stats['fairness'] = max(0, 10 - std_duty)  # 標準差越小，公平性越高
        
        stats['duty_counts'] = dict(duty_counts)
        stats['score_breakdown'] = {
            'unfilled': stats['unfilled'],
            'hard_violations': stats['hard_violations'],
            'soft_violations': stats['soft_violations'],
            'fairness': stats['fairness'],
            'preference_hits': stats['preference_hits']
        }
        
        return stats