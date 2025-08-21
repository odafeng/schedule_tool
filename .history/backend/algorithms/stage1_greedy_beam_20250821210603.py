"""
Stage 1: Greedy + Beam Search 快速排班
優先值班日、不可值班日為強制硬約束
"""
import copy
import random
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
from backend.models import Doctor, ScheduleSlot, ScheduleConstraints, SchedulingState
from backend.utils import check_consecutive_days

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
        
        # 計算醫師稀缺度
        self._calculate_scarcity()
        
        # 建立優先值班日映射表
        self.preferred_assignments = self._build_preferred_assignments()
        
        # 檢查優先值班日衝突
        self.preference_conflicts = self._check_preference_conflicts()
        
        # 決策日誌
        self.decision_log = []
        
        # 診斷資訊
        self.diagnostic_info = {
            'constraint_violations': [],
            'fill_attempts': 0,
            'fill_successes': 0,
            'skip_reasons': defaultdict(int),
            'preferred_fulfillment': {}
        }
    
    def _calculate_scarcity(self):
        """計算醫師稀缺度"""
        self.doctor_scarcity = {}
        
        for doctor in self.doctors:
            # 假日可用天數
            holiday_available = len([d for d in self.holidays 
                                    if d not in doctor.unavailable_dates])
            # 平日可用天數
            weekday_available = len([d for d in self.weekdays 
                                    if d not in doctor.unavailable_dates])
            
            # 稀缺度 = 配額 / 可用天數
            holiday_scarcity = doctor.holiday_quota / max(holiday_available, 1)
            weekday_scarcity = doctor.weekday_quota / max(weekday_available, 1)
            
            self.doctor_scarcity[doctor.name] = {
                'holiday': holiday_scarcity,
                'weekday': weekday_scarcity,
                'overall': (holiday_scarcity + weekday_scarcity) / 2
            }
    
    def _build_preferred_assignments(self) -> Dict[str, Dict[str, List[str]]]:
        """建立優先值班日映射：date -> role -> [doctors]"""
        assignments = defaultdict(lambda: {'主治': [], '總醫師': []})
        
        for doctor in self.doctors:
            role = doctor.role
            for date in doctor.preferred_dates:
                assignments[date][role].append(doctor.name)
        
        return dict(assignments)
    
    def _check_preference_conflicts(self) -> List[str]:
        """檢查優先值班日衝突"""
        conflicts = []
        
        for date, roles in self.preferred_assignments.items():
            for role, doctors in roles.items():
                if len(doctors) > 1:
                    conflicts.append({
                        'date': date,
                        'role': role,
                        'doctors': doctors,
                        'message': f"{date} {role}：{', '.join(doctors)} 都設為優先值班日"
                    })
        
        return conflicts
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """
        執行 Stage 1 排班
        
        Args:
            beam_width: 束搜索寬度
            progress_callback: 進度回調函數
            
        Returns:
            Top-K 排班方案列表
        """
        # Stage 1.1: Greedy 初始化（優先處理強制約束）
        initial_states = self._greedy_initialization()
        
        # Stage 1.2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        return final_states
    
    def _greedy_initialization(self) -> List[SchedulingState]:
        """Greedy 初始化：優先處理強制優先值班日"""
        
        # 初始化空白排班表
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        # 記錄已使用配額
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        # Phase 1: 處理所有優先值班日（強制約束）
        self._process_preferred_dates(schedule, used_quota)
        
        # Phase 2: 填充部分剩餘格子（留空間給 Beam Search）
        self._fill_remaining_slots(schedule, used_quota, fill_ratio=0.7)
        
        # 創建初始狀態
        base_state = self._create_state(schedule)
        
        
        # 產生多個變體
        states = [base_state]
        for i in range(min(4, self.constraints.beam_width - 1)):  # 產生 beam_width-1 個變體
            variant = self._create_smart_variant(schedule, used_quota, i)
            if variant:
                variant_state = self._create_state(variant)
                # 確保變體真的不同
                if variant_state.score != base_state.score or variant_state.filled_count != base_state.filled_count:
                    states.append(variant_state)
        
        return states
    
    def _process_preferred_dates(self, schedule: Dict, used_quota: Dict):
        """處理優先值班日（強制約束）"""
        preferred_filled = 0
        preferred_failed = []
        
        for date_str, roles in self.preferred_assignments.items():
            if date_str not in schedule:
                continue
            
            is_holiday = date_str in self.holidays
            
            for role, doctor_names in roles.items():
                if not doctor_names:
                    continue
                
                # 處理衝突：選擇最佳醫師
                if len(doctor_names) > 1:
                    selected_doctor = self._select_best_preferred_doctor(
                        doctor_names, date_str, is_holiday, used_quota, schedule
                    )
                else:
                    selected_doctor = self._check_single_preferred_doctor(
                        doctor_names[0], date_str, is_holiday, used_quota
                    )
                
                if selected_doctor:
                    # 分配排班
                    if role == "主治":
                        schedule[date_str].attending = selected_doctor
                    else:
                        schedule[date_str].resident = selected_doctor
                    
                    # 更新配額
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[selected_doctor][quota_type] += 1
                    preferred_filled += 1
                    
                    # 記錄成功
                    self.diagnostic_info['preferred_fulfillment'][f"{date_str}_{role}"] = selected_doctor
                else:
                    preferred_failed.append(f"{date_str} {role}: 無法滿足優先值班")
        
        # 記錄診斷資訊
        if preferred_failed:
            self.diagnostic_info['constraint_violations'].extend(preferred_failed)
    
    def _check_single_preferred_doctor(self, doctor_name: str, date_str: str,
                                      is_holiday: bool, used_quota: Dict) -> Optional[str]:
        """檢查單一優先值班醫師是否可行"""
        doctor = self.doctor_map[doctor_name]
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        
        if used_quota[doctor_name][quota_type] < max_quota:
            return doctor_name
        return None
    
    def _select_best_preferred_doctor(self, doctor_names: List[str], 
                                     date_str: str, is_holiday: bool,
                                     used_quota: Dict, schedule: Dict) -> Optional[str]:
        """
        從多個優先值班醫師中選擇最佳的
        
        選擇策略：
        1. 優先選擇優先天數最少的（公平性）
        2. 優先天數相同時，選擇對剩餘排班影響最小的
        """
        candidates = []
        
        for name in doctor_names:
            doctor = self.doctor_map[name]
            
            # 檢查基本約束
            quota_type = 'holiday' if is_holiday else 'weekday'
            max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
            
            # 如果超過配額，不能選
            if used_quota[name][quota_type] >= max_quota:
                continue
            
            # 計算評分指標
            score_metrics = self._calculate_preference_conflict_score(
                doctor, date_str, is_holiday, used_quota, schedule
            )
            
            candidates.append((name, score_metrics))
        
        if not candidates:
            return None
        
        # 多準則排序
        candidates.sort(key=lambda x: (
            x[1]['total_preferred_days'],      # 優先天數少的優先
            -x[1]['flexibility_score'],        # 靈活性高的優先
            -x[1]['remaining_quota_ratio']     # 剩餘配額多的優先
        ))
        
        best_candidate = candidates[0][0]
        
        # 記錄決策
        self.decision_log.append({
            'date': date_str,
            'conflict': doctor_names,
            'selected': best_candidate,
            'metrics': candidates[0][1]
        })
        
        return best_candidate
    
    def _calculate_preference_conflict_score(self, doctor: Doctor, 
                                            date_str: str, is_holiday: bool,
                                            used_quota: Dict, 
                                            schedule: Dict) -> Dict:
        """計算優先值班日衝突時的選擇分數"""
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        used = used_quota[doctor.name][quota_type]
        
        # 1. 總優先天數（公平性）
        total_preferred_days = len(doctor.preferred_dates)
        
        # 2. 剩餘配額比例
        remaining_quota = max_quota - used
        remaining_quota_ratio = remaining_quota / max(max_quota, 1)
        
        # 3. 靈活性分數（對剩餘排班的影響）
        flexibility_score = self._calculate_flexibility_score(
            doctor, is_holiday, used_quota, schedule
        )
        
        # 4. 已滿足的優先值班日比例
        fulfilled_preferred = self._count_fulfilled_preferred(doctor, schedule)
        fulfillment_ratio = fulfilled_preferred / max(total_preferred_days, 1)
        
        return {
            'total_preferred_days': total_preferred_days,
            'remaining_quota_ratio': remaining_quota_ratio,
            'flexibility_score': flexibility_score,
            'fulfillment_ratio': fulfillment_ratio,
            'remaining_quota': remaining_quota
        }
    
    def _calculate_flexibility_score(self, doctor: Doctor, is_holiday: bool,
                                    used_quota: Dict, schedule: Dict) -> float:
        """計算醫師的靈活性分數"""
        score = 0.0
        
        all_dates = self.holidays if is_holiday else self.weekdays
        future_available_days = 0
        
        for future_date in all_dates:
            if future_date not in schedule:
                continue
            
            slot = schedule[future_date]
            
            # 跳過已排定的
            if doctor.role == "主治" and slot.attending:
                continue
            elif doctor.role == "總醫師" and slot.resident:
                continue
            
            # 檢查是否可排班
            if future_date not in doctor.unavailable_dates:
                future_available_days += 1
        
        # 可用天數越多，靈活性越高
        score = future_available_days * 1.0
        
        # 考慮剩餘配額
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        remaining = max_quota - used_quota[doctor.name][quota_type]
        
        # 剩餘配額比例
        if future_available_days > 0:
            quota_flexibility = remaining / future_available_days
            score += quota_flexibility * 5
        
        return score
    
    def _count_fulfilled_preferred(self, doctor: Doctor, schedule: Dict) -> int:
        """計算已滿足的優先值班日數量"""
        fulfilled = 0
        
        for date in doctor.preferred_dates:
            if date in schedule:
                slot = schedule[date]
                if doctor.role == "主治" and slot.attending == doctor.name:
                    fulfilled += 1
                elif doctor.role == "總醫師" and slot.resident == doctor.name:
                    fulfilled += 1
        
        return fulfilled
    
    def _fill_remaining_slots(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """填充剩餘格子（避開優先值班日）"""
        # 排序日期：假日優先
        sorted_dates = self.holidays + self.weekdays
        
        # 只填充指定比例的格子
        dates_to_fill = sorted_dates[:int(len(sorted_dates) * fill_ratio)]
        
        for date_str in dates_to_fill:
            is_holiday = date_str in self.holidays
            
            # 排主治醫師（如果還沒排）
            if not schedule[date_str].attending:
                candidates = self._get_greedy_candidates(
                    date_str, "主治", schedule, used_quota, is_holiday
                )
                if candidates:
                    best_doctor = candidates[0]
                    schedule[date_str].attending = best_doctor
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[best_doctor][quota_type] += 1
            
            # 排總醫師（如果還沒排）
            if not schedule[date_str].resident:
                candidates = self._get_greedy_candidates(
                    date_str, "總醫師", schedule, used_quota, is_holiday
                )
                if candidates:
                    best_doctor = candidates[0]
                    schedule[date_str].resident = best_doctor
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[best_doctor][quota_type] += 1
    
    def _get_greedy_candidates(self, date_str: str, role: str,
                              schedule: Dict, used_quota: Dict,
                              is_holiday: bool) -> List[str]:
        """取得候選人（考慮優先值班日保護）"""
        candidates = []
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        
        # 檢查是否是他人的優先值班日
        reserved_for = None
        if date_str in self.preferred_assignments:
            if self.preferred_assignments[date_str][role]:
                reserved_for = self.preferred_assignments[date_str][role]
        
        for doctor in doctors:
            # 不能排到別人的優先值班日（除非是自己的）
            if reserved_for and doctor.name not in reserved_for:
                continue
            
            # 檢查硬約束
            if not self._check_hard_constraints(
                doctor, date_str, schedule, used_quota, is_holiday
            ):
                continue
            
            # 計算優先級
            priority_score = self._calculate_priority_score(
                doctor, date_str, is_holiday, used_quota
            )
            
            # 如果是自己的優先值班日，給極高分數
            if date_str in doctor.preferred_dates:
                priority_score += 1000
            
            candidates.append((doctor.name, priority_score))
        
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
        
        # 4. 同日不能擔任兩個角色
        slot = schedule[date_str]
        if slot.attending == doctor.name or slot.resident == doctor.name:
            return False
        
        # 5. 保留配額給優先值班日
        unfulfilled = self._get_unfulfilled_preferred_dates(doctor, schedule, is_holiday)
        if unfulfilled and date_str not in doctor.preferred_dates:
            remaining = max_quota - used_quota[doctor.name][quota_type] - 1
            if remaining < len(unfulfilled):
                return False
        
        return True
    
    def _get_unfulfilled_preferred_dates(self, doctor: Doctor,
                                        schedule: Dict,
                                        is_holiday: bool) -> List[str]:
        """取得尚未滿足的優先值班日"""
        unfulfilled = []
        
        for date in doctor.preferred_dates:
            if date not in schedule:
                continue
            
            date_is_holiday = date in self.holidays
            if date_is_holiday != is_holiday:
                continue
            
            slot = schedule[date]
            if doctor.role == "主治" and slot.attending != doctor.name:
                unfulfilled.append(date)
            elif doctor.role == "總醫師" and slot.resident != doctor.name:
                unfulfilled.append(date)
        
        return unfulfilled
    
    def _calculate_priority_score(self, doctor: Doctor, date_str: str,
                                 is_holiday: bool, used_quota: Dict) -> float:
        """計算優先級分數"""
        score = 0.0
        
        # 1. 稀缺度
        scarcity_type = 'holiday' if is_holiday else 'weekday'
        score += self.doctor_scarcity[doctor.name][scarcity_type] * 10
        
        # 2. 偏好日期（現在是強制的，所以給更高分數）
        if date_str in doctor.preferred_dates:
            score += 100  # 大幅提高分數
        
        # 3. 剩餘配額比例
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        used = used_quota[doctor.name][quota_type]
        remaining_ratio = (max_quota - used) / max(max_quota, 1)
        score += (1 - remaining_ratio) * 3
        
        return score
    
    def _create_variant(self, base_schedule: Dict) -> Optional[Dict]:
        """創建排班變體"""
        variant = copy.deepcopy(base_schedule)
        
        # 找出非優先值班的已填格子
        modifiable_slots = []
        for date_str, slot in variant.items():
            # 檢查主治位置
            if slot.attending:
                if date_str not in self.preferred_assignments or \
                   slot.attending not in self.preferred_assignments[date_str].get('主治', []):
                    modifiable_slots.append((date_str, '主治'))
            
            # 檢查總醫師位置
            if slot.resident:
                if date_str not in self.preferred_assignments or \
                   slot.resident not in self.preferred_assignments[date_str].get('總醫師', []):
                    modifiable_slots.append((date_str, '總醫師'))
        
        # 隨機清空一些非優先值班的格子
        if modifiable_slots:
            num_to_clear = min(5, len(modifiable_slots) // 4)
            to_clear = random.sample(modifiable_slots, num_to_clear)
            
            for date_str, role in to_clear:
                if role == '主治':
                    variant[date_str].attending = None
                else:
                    variant[date_str].resident = None
        
        return variant
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int,
                                  progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        beam = initial_states
        
        # 收集所有未填格（排除優先值班日）
        unfilled = []
        for state in initial_states:
            for date_str, slot in state.schedule.items():
                # 檢查主治
                if not slot.attending:
                    # 確認不是優先值班日
                    if date_str not in self.preferred_assignments or \
                       not self.preferred_assignments[date_str].get('主治'):
                        unfilled.append((date_str, "主治"))
                
                # 檢查總醫師
                if not slot.resident:
                    if date_str not in self.preferred_assignments or \
                       not self.preferred_assignments[date_str].get('總醫師'):
                        unfilled.append((date_str, "總醫師"))
        
        # 排序未填格（假日優先）
        unfilled = self._sort_unfilled_slots(unfilled)
        
        # Beam Search 主循環
        total_steps = min(30, len(unfilled))  # 最多處理30個格子
        
        for step, (date_str, role) in enumerate(unfilled[:total_steps]):
            new_beam = []
            
            for state in beam:
                # 取得候選醫師
                candidates = self._get_beam_candidates(
                    state.schedule, date_str, role
                )
                
                if not candidates:
                    new_beam.append(state)
                else:
                    # 嘗試每個候選人
                    for doctor_name in candidates[:3]:
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
        """排序未填格"""
        priority_list = []
        
        for date_str, role in unfilled:
            priority = 0
            
            # 假日優先
            if date_str in self.holidays:
                priority += 10
            
            # 主治優先
            if role == "主治":
                priority += 5
            
            priority_list.append((date_str, role, priority))
        
        priority_list.sort(key=lambda x: x[2], reverse=True)
        return [(d, r) for d, r, _ in priority_list]
    
    def _get_beam_candidates(self, schedule: Dict, date_str: str, role: str) -> List[str]:
        """取得 Beam Search 候選人"""
        used_quota = self._calculate_used_quota(schedule)
        is_holiday = date_str in self.holidays
        
        return self._get_greedy_candidates(
            date_str, role, schedule, used_quota, is_holiday
        )
    
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
        """計算排班分數"""
        score = 0.0
        
        # 1. 填充率（最重要）
        total_slots = len(schedule) * 2
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        score += fill_rate * 1000
        
        # 2. 優先值班日滿足度（強制約束，極高權重）
        preference_satisfied = 0
        preference_total = 0
        
        for doctor in self.doctors:
            for pref_date in doctor.preferred_dates:
                if pref_date in schedule:
                    preference_total += 1
                    slot = schedule[pref_date]
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        preference_satisfied += 1
        
        if preference_total > 0:
            preference_rate = preference_satisfied / preference_total
            score += preference_rate * 500  # 提高權重
        
        # 3. 連續值班懲罰
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
        
        sorted_dates = sorted(schedule.keys())
        
        for i, date_str in enumerate(sorted_dates):
            slot = schedule[date_str]
            
            for doctor_name in [slot.attending, slot.resident]:
                if not doctor_name:
                    continue
                
                if i > 0:
                    prev_slot = schedule[sorted_dates[i-1]]
                    if doctor_name in [prev_slot.attending, prev_slot.resident]:
                        doctor_consecutive[doctor_name] += 1
                    else:
                        doctor_consecutive[doctor_name] = 0
                
                if doctor_consecutive[doctor_name] >= 2:
                    penalty += (doctor_consecutive[doctor_name] - 1) * 0.5
        
        return penalty
    
    def _calculate_balance_score(self, schedule: Dict) -> float:
        """計算配額使用均衡度"""
        used_quota = self._calculate_used_quota(schedule)
        
        usage_rates = []
        for doctor in self.doctors:
            weekday_used = used_quota[doctor.name]['weekday']
            holiday_used = used_quota[doctor.name]['holiday']
            
            weekday_rate = weekday_used / max(doctor.weekday_quota, 1)
            holiday_rate = holiday_used / max(doctor.holiday_quota, 1)
            
            avg_rate = (weekday_rate + holiday_rate) / 2
            usage_rates.append(avg_rate)
        
        if usage_rates:
            std_dev = np.std(usage_rates)
            balance_score = max(0, 1 - std_dev)
        else:
            balance_score = 0
        
        return balance_score