"""
Stage 1: Greedy + Beam Search 快速排班
"""
import copy
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict
from dataclasses import dataclass
import numpy as np

from backend.models import Doctor, ScheduleSlot, ScheduleConstraints
from backend.utils import check_consecutive_days

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

class Stage1Scheduler:
    """Stage 1: Greedy + Beam Search 排班器"""
    
    def __init__(self, doctors: List[Doctor], constraints: ScheduleConstraints,
                 weekdays: List[str], holidays: List[str]):
        self.doctors = doctors
        self.constraints = constraints
        self.weekdays = weekdays
        self.holidays = holidays
        
        # 分類醫師
        self.attending_doctors = [d for d in doctors if d.role == "主治"]
        self.resident_doctors = [d for d in doctors if d.role == "總醫師"]
        
        # 建立醫師索引
        self.doctor_map = {d.name: d for d in doctors}
        
        # 計算醫師稀缺度（用於優先排序）
        self._calculate_scarcity()
    
    def _calculate_scarcity(self):
        """計算醫師稀缺度"""
        self.doctor_scarcity = {}
        
        # 計算每個醫師的總可用天數
        for doctor in self.doctors:
            # 假日可用天數
            holiday_available = len([d for d in self.holidays 
                                    if d not in doctor.unavailable_dates])
            # 平日可用天數
            weekday_available = len([d for d in self.weekdays 
                                    if d not in doctor.unavailable_dates])
            
            # 稀缺度 = 配額 / 可用天數（越大越稀缺）
            holiday_scarcity = doctor.holiday_quota / max(holiday_available, 1)
            weekday_scarcity = doctor.weekday_quota / max(weekday_available, 1)
            
            self.doctor_scarcity[doctor.name] = {
                'holiday': holiday_scarcity,
                'weekday': weekday_scarcity,
                'overall': (holiday_scarcity + weekday_scarcity) / 2
            }
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """
        執行 Stage 1 排班
        
        Args:
            beam_width: 束搜索寬度
            progress_callback: 進度回調函數
            
        Returns:
            Top-K 排班方案列表
        """
        # Stage 1.1: Greedy 初始化
        initial_states = self._greedy_initialization()
        
        # Stage 1.2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        return final_states
    
    def _greedy_initialization(self) -> List[SchedulingState]:
        """Greedy 初始化：假日優先 + 稀缺醫師優先"""
        
        # 初始化空白排班表
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        # 排序日期：假日優先
        sorted_dates = self.holidays + self.weekdays
        
        # 記錄已使用配額
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        # Greedy 填充
        for date_str in sorted_dates:
            is_holiday = date_str in self.holidays
            
            # 排主治醫師
            candidates = self._get_greedy_candidates(
                date_str, "主治", schedule, used_quota, is_holiday
            )
            if candidates:
                best_doctor = candidates[0]  # 最稀缺的醫師
                schedule[date_str].attending = best_doctor
                if is_holiday:
                    used_quota[best_doctor]['holiday'] += 1
                else:
                    used_quota[best_doctor]['weekday'] += 1
            
            # 排總醫師
            candidates = self._get_greedy_candidates(
                date_str, "總醫師", schedule, used_quota, is_holiday
            )
            if candidates:
                best_doctor = candidates[0]
                schedule[date_str].resident = best_doctor
                if is_holiday:
                    used_quota[best_doctor]['holiday'] += 1
                else:
                    used_quota[best_doctor]['weekday'] += 1
        
        # 計算初始狀態
        state = self._create_state(schedule)
        return [state]
    
    def _get_greedy_candidates(self, date_str: str, role: str, 
                               schedule: Dict, used_quota: Dict,
                               is_holiday: bool) -> List[str]:
        """取得 Greedy 候選人（按稀缺度排序）"""
        candidates = []
        
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        
        for doctor in doctors:
            # 檢查硬約束
            if not self._check_hard_constraints(
                doctor, date_str, schedule, used_quota, is_holiday
            ):
                continue
            
            # 計算優先級分數
            priority_score = self._calculate_priority_score(
                doctor, date_str, is_holiday, used_quota
            )
            candidates.append((doctor.name, priority_score))
        
        # 按優先級排序（越高越優先）
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]
    
    def _check_hard_constraints(self, doctor: Doctor, date_str: str,
                                schedule: Dict, used_quota: Dict,
                                is_holiday: bool) -> bool:
        """檢查硬約束"""
        # 1. 不可值班日
        if date_str in doctor.unavailable_dates:
            return False
        
        # 2. 配額限制
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        if used_quota[doctor.name][quota_type] >= max_quota:
            return False
        
        # 3. 連續值班限制
        if check_consecutive_days(schedule, doctor.name, date_str, 
                                 self.constraints.max_consecutive_days):
            return False
        
        # 4. 同一天不能擔任兩個角色
        slot = schedule[date_str]
        if slot.attending == doctor.name or slot.resident == doctor.name:
            return False
        
        return True
    
    def _calculate_priority_score(self, doctor: Doctor, date_str: str,
                                  is_holiday: bool, used_quota: Dict) -> float:
        """計算優先級分數"""
        score = 0.0
        
        # 1. 稀缺度（越稀缺分數越高）
        scarcity_type = 'holiday' if is_holiday else 'weekday'
        score += self.doctor_scarcity[doctor.name][scarcity_type] * 10
        
        # 2. 偏好日期（優先值班日）
        if date_str in doctor.preferred_dates:
            score += 5
        
        # 3. 剩餘配額比例（剩餘越少越優先）
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        used = used_quota[doctor.name][quota_type]
        remaining_ratio = (max_quota - used) / max(max_quota, 1)
        score += (1 - remaining_ratio) * 3
        
        return score
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int,
                                  progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        beam = initial_states
        
        # 收集所有未填格
        unfilled = initial_states[0].unfilled_slots if initial_states else []
        
        # 按重要性排序未填格（假日優先，稀缺角色優先）
        unfilled = self._sort_unfilled_slots(unfilled)
        
        total_steps = len(unfilled)
        
        for step, (date_str, role) in enumerate(unfilled[:30]):  # 最多處理30個重要空格
            new_beam = []
            
            for state in beam:
                # 嘗試填充這個位置
                candidates = self._get_beam_candidates(
                    state.schedule, date_str, role
                )
                
                if not candidates:
                    # 保持未填
                    new_beam.append(state)
                else:
                    # 嘗試每個候選人
                    for doctor_name in candidates[:3]:  # 每個位置最多嘗試3個候選人
                        new_schedule = copy.deepcopy(state.schedule)
                        if role == "主治":
                            new_schedule[date_str].attending = doctor_name
                        else:
                            new_schedule[date_str].resident = doctor_name
                        
                        new_state = self._create_state(new_schedule)
                        new_beam.append(new_state)
            
            # 保留 Top-K
            new_beam.sort(key=lambda x: x.score, reverse=True)
            beam = new_beam[:beam_width]
            
            if progress_callback:
                progress_callback((step + 1) / total_steps)
        
        return beam
    
    def _sort_unfilled_slots(self, unfilled: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """排序未填格（重要性）"""
        priority_list = []
        
        for date_str, role in unfilled:
            priority = 0
            
            # 假日優先
            if date_str in self.holidays:
                priority += 10
            
            # 主治醫師優先
            if role == "主治":
                priority += 5
            
            # 週末優先
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if date_obj.weekday() >= 5:
                priority += 3
            
            priority_list.append((date_str, role, priority))
        
        priority_list.sort(key=lambda x: x[2], reverse=True)
        return [(d, r) for d, r, _ in priority_list]
    
    def _get_beam_candidates(self, schedule: Dict, date_str: str, role: str) -> List[str]:
        """取得 Beam Search 候選人"""
        candidates = []
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        
        # 計算當前使用的配額
        used_quota = self._calculate_used_quota(schedule)
        is_holiday = date_str in self.holidays
        
        for doctor in doctors:
            if self._check_hard_constraints(
                doctor, date_str, schedule, used_quota, is_holiday
            ):
                score = self._calculate_priority_score(
                    doctor, date_str, is_holiday, used_quota
                )
                candidates.append((doctor.name, score))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]
    
    def _calculate_used_quota(self, schedule: Dict) -> Dict:
        """計算已使用的配額"""
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            quota_type = 'holiday' if is_holiday else 'weekday'
            
            if slot.attending:
                used_quota[slot.attending][quota_type] += 1
            if slot.resident:
                used_quota[slot.resident][quota_type] += 1
        
        return used_quota
    
    def _create_state(self, schedule: Dict) -> SchedulingState:
        """創建排班狀態"""
        # 計算填充數和未填格
        filled_count = 0
        unfilled_slots = []
        
        for date_str, slot in schedule.items():
            if slot.attending:
                filled_count += 1
            else:
                unfilled_slots.append((date_str, "主治"))
            
            if slot.resident:
                filled_count += 1
            else:
                unfilled_slots.append((date_str, "總醫師"))
        
        # 計算分數
        score = self._calculate_score(schedule, filled_count, unfilled_slots)
        
        return SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
    
    def _calculate_score(self, schedule: Dict, filled_count: int,
                        unfilled_slots: List) -> float:
        """
        計算排班分數
        
        評分維度：
        1. 填充率（最重要，權重 1000）
        2. 優先值班日滿足度（權重 100）
        3. 連續值班合理性（權重 50）
        4. 配額使用均衡度（權重 30）
        5. 假日覆蓋完整度（權重 200）
        """
        score = 0.0
        
        # 1. 填充率
        total_slots = len(schedule) * 2
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        score += fill_rate * 1000
        
        # 2. 優先值班日滿足度
        preference_satisfied = 0
        preference_total = 0
        for doctor in self.doctors:
            for pref_date in doctor.preferred_dates:
                if pref_date in schedule:
                    preference_total += 1
                    slot = schedule[pref_date]
                    if slot.attending == doctor.name or slot.resident == doctor.name:
                        preference_satisfied += 1
        
        if preference_total > 0:
            score += (preference_satisfied / preference_total) * 100
        
        # 3. 連續值班合理性（避免過多連續值班）
        consecutive_penalty = self._calculate_consecutive_penalty(schedule)
        score -= consecutive_penalty * 50
        
        # 4. 配額使用均衡度
        balance_score = self._calculate_balance_score(schedule)
        score += balance_score * 30
        
        # 5. 假日覆蓋完整度
        holiday_filled = 0
        for date_str in self.holidays:
            if date_str in schedule:
                slot = schedule[date_str]
                if slot.attending:
                    holiday_filled += 1
                if slot.resident:
                    holiday_filled += 1
        
        holiday_fill_rate = holiday_filled / (len(self.holidays) * 2) if self.holidays else 0
        score += holiday_fill_rate * 200
        
        return score
    
    def _calculate_consecutive_penalty(self, schedule: Dict) -> float:
        """計算連續值班懲罰"""
        penalty = 0
        doctor_consecutive = defaultdict(int)
        
        # 按日期排序
        sorted_dates = sorted(schedule.keys())
        
        for i, date_str in enumerate(sorted_dates):
            slot = schedule[date_str]
            
            # 檢查每個醫師
            for doctor_name in [slot.attending, slot.resident]:
                if not doctor_name:
                    continue
                
                # 檢查是否連續值班
                is_consecutive = False
                if i > 0:
                    prev_slot = schedule[sorted_dates[i-1]]
                    if doctor_name in [prev_slot.attending, prev_slot.resident]:
                        is_consecutive = True
                        doctor_consecutive[doctor_name] += 1
                    else:
                        doctor_consecutive[doctor_name] = 0
                
                # 連續超過2天開始懲罰
                if doctor_consecutive[doctor_name] >= 2:
                    penalty += (doctor_consecutive[doctor_name] - 1) * 0.5
        
        return penalty
    
    def _calculate_balance_score(self, schedule: Dict) -> float:
        """計算配額使用均衡度"""
        used_quota = self._calculate_used_quota(schedule)
        
        # 計算每個醫師的配額使用率
        usage_rates = []
        for doctor in self.doctors:
            weekday_used = used_quota[doctor.name]['weekday']
            holiday_used = used_quota[doctor.name]['holiday']
            
            weekday_rate = weekday_used / max(doctor.weekday_quota, 1)
            holiday_rate = holiday_used / max(doctor.holiday_quota, 1)
            
            avg_rate = (weekday_rate + holiday_rate) / 2
            usage_rates.append(avg_rate)
        
        # 計算標準差（越小越均衡）
        if usage_rates:
            std_dev = np.std(usage_rates)
            # 轉換為分數（標準差越小分數越高）
            balance_score = max(0, 1 - std_dev)
        else:
            balance_score = 0
        
        return balance_score