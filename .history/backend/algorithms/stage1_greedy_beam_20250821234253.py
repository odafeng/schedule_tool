"""
Stage 1: Greedy + Beam Search 快速排班
嚴格版本：絕對遵守所有硬約束，寧可留空也不違反
"""
import copy
import random
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable, Set
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
import hashlib
import time
from backend.models import Doctor, ScheduleSlot, ScheduleConstraints, SchedulingState
from backend.utils import check_consecutive_days

class Stage1Scheduler:
    """Stage 1: Greedy + Beam Search 排班器 - 嚴格硬約束版本"""
    
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
        
        # 建立不可值班日映射表（硬約束3）
        self.unavailable_map = self._build_unavailable_map()
        
        # 建立優先值班日映射表（硬約束4）
        self.preferred_assignments = self._build_preferred_assignments()
        
        # 檢查優先值班日衝突
        self.preference_conflicts = self._check_preference_conflicts()
        
        # 驗證硬約束可行性
        self.constraint_issues = self._validate_all_hard_constraints()
        
        # 計算每個格子的靈活度
        self.slot_flexibility = self._calculate_slot_flexibility()
        
        # 用於追蹤已生成的方案
        self.generated_schedules = set()
        
        # 診斷資訊
        self.diagnostic_info = {
            'constraint_violations': [],
            'fill_attempts': 0,
            'fill_successes': 0,
            'skip_reasons': defaultdict(int),
            'preferred_fulfillment': {},
            'hard_constraint_violations': [],
            'variant_strategies': []
        }
        
        # 如果有約束問題，記錄警告
        if self.constraint_issues:
            self.diagnostic_info['hard_constraint_violations'].extend(self.constraint_issues)
    
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
    
    def _calculate_slot_flexibility(self) -> Dict[str, Dict[str, float]]:
        """計算每個格子的靈活度"""
        flexibility = {}
        
        for date_str in self.weekdays + self.holidays:
            # 優先值班日靈活度為0
            if date_str in self.preferred_assignments:
                flexibility[date_str] = {
                    'attending': 0,
                    'resident': 0,
                    'overall': 0
                }
                continue
            
            # 計算可用醫師數
            available_attending = sum(1 for d in self.attending_doctors 
                                    if date_str not in d.unavailable_dates)
            available_resident = sum(1 for d in self.resident_doctors 
                                   if date_str not in d.unavailable_dates)
            
            # 平日通常有更多選擇
            date_type_bonus = 5 if date_str in self.weekdays else 0
            
            flexibility[date_str] = {
                'attending': available_attending + date_type_bonus,
                'resident': available_resident + date_type_bonus,
                'overall': available_attending + available_resident + date_type_bonus * 2
            }
        
        return flexibility
    
    def _build_unavailable_map(self) -> Dict[str, Set[str]]:
        """建立不可值班日映射：date -> Set[doctor_names]"""
        unavailable = defaultdict(set)
        
        for doctor in self.doctors:
            for date in doctor.unavailable_dates:
                unavailable[date].add(doctor.name)
        
        return dict(unavailable)
    
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
    
    def _validate_all_hard_constraints(self) -> List[str]:
        """驗證所有硬約束的可行性"""
        issues = []
        all_dates = self.weekdays + self.holidays
        
        for date_str in all_dates:
            is_holiday = date_str in self.holidays
            
            # 檢查主治醫師可用性
            available_attending = []
            for doctor in self.attending_doctors:
                # 硬約束3: 不可值班日
                if date_str in doctor.unavailable_dates:
                    continue
                # 檢查配額
                max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                if max_quota > 0:
                    available_attending.append(doctor.name)
            
            if not available_attending:
                issues.append(f"{date_str} 沒有可用的主治醫師")
            
            # 同樣檢查總醫師
            available_resident = []
            for doctor in self.resident_doctors:
                if date_str in doctor.unavailable_dates:
                    continue
                max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                if max_quota > 0:
                    available_resident.append(doctor.name)
            
            if not available_resident:
                issues.append(f"{date_str} 沒有可用的總醫師")
        
        return issues
    
    def _calculate_schedule_hash(self, schedule: Dict) -> str:
        """計算排班表的唯一識別碼"""
        schedule_str = ""
        for date_str in sorted(schedule.keys()):
            slot = schedule[date_str]
            schedule_str += f"{date_str}:{slot.attending or 'None'}:{slot.resident or 'None'}|"
        return hashlib.md5(schedule_str.encode()).hexdigest()
    
    def _is_hard_constraint_violated(self, doctor_name: str, date_str: str, 
                                    role: str, schedule: Dict, 
                                    used_quota: Dict) -> Tuple[bool, str]:
        """
        檢查是否違反硬約束
        
        Returns:
            (是否違反, 違反原因)
        """
        doctor = self.doctor_map[doctor_name]
        is_holiday = date_str in self.holidays
        
        # 硬約束1: 同一日內，同一角色，只能一個人值班
        slot = schedule[date_str]
        if role == "主治" and slot.attending is not None:
            return (True, "該日主治已有人值班")
        if role == "總醫師" and slot.resident is not None:
            return (True, "該日總醫師已有人值班")
        
        # 硬約束2: 配額不可超過
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        current_usage = used_quota[doctor_name][quota_type]
        if current_usage >= max_quota:
            return (True, f"已達{quota_type}配額上限 ({current_usage}/{max_quota})")
        
        # 硬約束3: 不可值班日絕對不能排班
        if date_str in doctor.unavailable_dates:
            return (True, f"這是{doctor_name}的不可值班日")
        
        # 硬約束4: 優先值班日必須給設定的醫師
        if date_str in self.preferred_assignments:
            preferred_doctors = self.preferred_assignments[date_str].get(role, [])
            if preferred_doctors and doctor_name not in preferred_doctors:
                return (True, f"該日是{', '.join(preferred_doctors)}的優先值班日")
        
        # 硬約束5: 連續值班天數限制
        consecutive = self._count_consecutive_days(doctor_name, date_str, schedule)
        if consecutive > self.constraints.max_consecutive_days:
            return (True, f"違反連續值班限制 (連續{consecutive}天，上限{self.constraints.max_consecutive_days}天)")
        
        # 額外檢查：同日不能擔任兩個角色
        if doctor_name in [slot.attending, slot.resident]:
            return (True, "同日已擔任其他角色")
        
        return (False, "")
    
    def _count_consecutive_days(self, doctor_name: str, target_date: str, 
                               schedule: Dict) -> int:
        """計算如果在target_date排班，會連續幾天"""
        sorted_dates = sorted(schedule.keys())
        date_index = sorted_dates.index(target_date)
        
        consecutive = 1  # 包含目標日
        
        # 向前檢查
        for i in range(date_index - 1, -1, -1):
            slot = schedule[sorted_dates[i]]
            if doctor_name in [slot.attending, slot.resident]:
                consecutive += 1
            else:
                break
        
        # 向後檢查
        for i in range(date_index + 1, len(sorted_dates)):
            slot = schedule[sorted_dates[i]]
            if doctor_name in [slot.attending, slot.resident]:
                consecutive += 1
            else:
                break
        
        return consecutive
    
    def _safe_assign(self, schedule: Dict, date_str: str, role: str, 
                    doctor_name: str, used_quota: Dict) -> bool:
        """
        安全地分配醫師到排班表
        
        Returns:
            是否成功分配
        """
        # 最終檢查硬約束
        violated, reason = self._is_hard_constraint_violated(
            doctor_name, date_str, role, schedule, used_quota
        )
        
        if violated:
            self.diagnostic_info['skip_reasons'][reason] += 1
            return False
        
        # 執行分配
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        
        if role == "主治":
            schedule[date_str].attending = doctor_name
        else:
            schedule[date_str].resident = doctor_name
        
        used_quota[doctor_name][quota_type] += 1
        
        self.diagnostic_info['fill_successes'] += 1
        return True
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """
        執行 Stage 1 排班
        
        Args:
            beam_width: 束搜索寬度
            progress_callback: 進度回調函數
            
        Returns:
            Top-K 排班方案列表
        """
        # 如果有嚴重的約束問題，顯示警告
        if self.constraint_issues:
            st.warning(f"發現約束問題：{'; '.join(self.constraint_issues[:3])}")
        
        # Stage 1.1: Greedy 初始化
        initial_states = self._greedy_initialization()
        
        # Stage 1.2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        # 最終驗證
        for state in final_states:
            violations = self._final_validation(state)
            if violations:
                st.error(f"發現硬約束違反：{violations[:3]}")
        
        return final_states
    
    def _greedy_initialization(self) -> List[SchedulingState]:
        """Greedy 初始化：產生多個不同的初始解"""
        states = []
        self.generated_schedules.clear()
        
        for variant_idx in range(min(5, self.constraints.beam_width)):
            # 創建空白排班表
            schedule = {}
            for date_str in self.weekdays + self.holidays:
                schedule[date_str] = ScheduleSlot(date=date_str)
            
            # 記錄已使用配額
            used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
            
            # Phase 1: 處理所有優先值班日（硬約束4）
            self._process_preferred_dates(schedule, used_quota)
            
            # Phase 2: 填充其他日期（使用不同策略）
            strategy = self._get_variant_strategy(variant_idx)
            self._fill_with_strategy(schedule, used_quota, strategy)
            
            # 創建狀態
            state = self._create_state(schedule, variant_idx)
            
            # 確保是唯一的方案
            schedule_hash = self._calculate_schedule_hash(schedule)
            if schedule_hash not in self.generated_schedules:
                self.generated_schedules.add(schedule_hash)
                states.append(state)
        
        return states if states else [self._create_empty_state()]
    
    def _process_preferred_dates(self, schedule: Dict, used_quota: Dict):
        """處理優先值班日（硬約束4）"""
        for date_str, roles in self.preferred_assignments.items():
            if date_str not in schedule:
                continue
            
            for role, doctor_names in roles.items():
                if not doctor_names:
                    continue
                
                # 選擇最佳的醫師
                selected = None
                if len(doctor_names) == 1:
                    # 單一醫師
                    doctor_name = doctor_names[0]
                    violated, reason = self._is_hard_constraint_violated(
                        doctor_name, date_str, role, schedule, used_quota
                    )
                    if not violated:
                        selected = doctor_name
                else:
                    # 多個醫師競爭，選擇最合適的
                    for doctor_name in doctor_names:
                        violated, reason = self._is_hard_constraint_violated(
                            doctor_name, date_str, role, schedule, used_quota
                        )
                        if not violated:
                            selected = doctor_name
                            break
                
                # 執行分配
                if selected:
                    self._safe_assign(schedule, date_str, role, selected, used_quota)
    
    def _get_variant_strategy(self, variant_idx: int) -> Dict:
        """取得變體策略"""
        strategies = [
            {'name': '保守策略', 'fill_ratio': 0.6, 'order': 'scarcity'},
            {'name': '標準策略', 'fill_ratio': 0.7, 'order': 'random'},
            {'name': '激進策略', 'fill_ratio': 0.8, 'order': 'balanced'},
            {'name': '最小策略', 'fill_ratio': 0.5, 'order': 'reverse'},
            {'name': '隨機策略', 'fill_ratio': 0.65, 'order': 'shuffle'},
        ]
        return strategies[variant_idx % len(strategies)]
    
    def _fill_with_strategy(self, schedule: Dict, used_quota: Dict, strategy: Dict):
        """根據策略填充排班"""
        # 收集需要填充的格子
        slots_to_fill = []
        for date_str in self.weekdays + self.holidays:
            # 跳過已經處理的優先值班日
            slot = schedule[date_str]
            
            if not slot.attending:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('主治'):
                    slots_to_fill.append((date_str, '主治'))
            
            if not slot.resident:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('總醫師'):
                    slots_to_fill.append((date_str, '總醫師'))
        
        # 根據策略排序
        if strategy['order'] == 'scarcity':
            # 假日優先
            slots_to_fill.sort(key=lambda x: (x[0] not in self.holidays, x[0]))
        elif strategy['order'] == 'random':
            random.shuffle(slots_to_fill)
        elif strategy['order'] == 'balanced':
            # 交替填充
            holidays = [s for s in slots_to_fill if s[0] in self.holidays]
            weekdays = [s for s in slots_to_fill if s[0] in self.weekdays]
            slots_to_fill = []
            while holidays or weekdays:
                if holidays:
                    slots_to_fill.append(holidays.pop(0))
                if weekdays:
                    slots_to_fill.append(weekdays.pop(0))
        elif strategy['order'] == 'shuffle':
            random.seed(strategy.get('seed', 42))
            random.shuffle(slots_to_fill)
        
        # 只填充指定比例
        max_fill = int(len(slots_to_fill) * strategy['fill_ratio'])
        slots_to_fill = slots_to_fill[:max_fill]
        
        # 執行填充
        for date_str, role in slots_to_fill:
            candidates = self._get_candidates(date_str, role, schedule, used_quota)
            if candidates:
                # 選擇最佳候選人
                best_doctor = candidates[0]
                self._safe_assign(schedule, date_str, role, best_doctor, used_quota)
    
    def _get_candidates(self, date_str: str, role: str, 
                       schedule: Dict, used_quota: Dict) -> List[str]:
        """取得可用的候選醫師列表（嚴格檢查硬約束）"""
        candidates = []
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        
        for doctor in doctors:
            violated, reason = self._is_hard_constraint_violated(
                doctor.name, date_str, role, schedule, used_quota
            )
            
            if not violated:
                # 計算優先分數
                is_holiday = date_str in self.holidays
                scarcity_type = 'holiday' if is_holiday else 'weekday'
                score = self.doctor_scarcity[doctor.name][scarcity_type]
                
                # 如果是自己的優先值班日，大幅提高分數
                if date_str in doctor.preferred_dates:
                    score += 100
                
                candidates.append((doctor.name, score))
        
        # 按分數排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int,
                                  progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        # 為每個狀態維護獨立的 used_quota
        beam = []
        for state in initial_states:
            used_quota = self._calculate_used_quota(state.schedule)
            beam.append({
                'state': state,
                'used_quota': used_quota
            })
        
        # 收集未填格子
        unfilled = self._collect_unfilled_slots(initial_states[0].schedule)
        
        # Beam Search 主循環
        total_steps = min(30, len(unfilled))
        
        for step, (date_str, role) in enumerate(unfilled[:total_steps]):
            new_beam = []
            
            for item in beam:
                current_state = item['state']
                current_used_quota = copy.deepcopy(item['used_quota'])
                
                # 取得候選人
                candidates = self._get_candidates(
                    date_str, role, 
                    current_state.schedule, 
                    current_used_quota
                )
                
                if not candidates:
                    # 無候選人，保持原狀
                    new_beam.append(item)
                else:
                    # 嘗試最佳的幾個候選人
                    for doctor_name in candidates[:3]:
                        # 深拷貝
                        new_schedule = copy.deepcopy(current_state.schedule)
                        new_used_quota = copy.deepcopy(current_used_quota)
                        
                        # 再次驗證並分配
                        if self._safe_assign(new_schedule, date_str, role, 
                                           doctor_name, new_used_quota):
                            new_state = self._create_state(new_schedule, step % 5)
                            new_beam.append({
                                'state': new_state,
                                'used_quota': new_used_quota
                            })
            
            # 保留 Top-K
            new_beam.sort(key=lambda x: x['state'].score, reverse=True)
            beam = new_beam[:beam_width]
            
            if progress_callback:
                progress_callback((step + 1) / total_steps)
        
        return [item['state'] for item in beam]
    
    def _collect_unfilled_slots(self, schedule: Dict) -> List[Tuple[str, str]]:
        """收集未填充的格子"""
        unfilled = []
        
        for date_str in self.holidays + self.weekdays:  # 假日優先
            slot = schedule[date_str]
            
            if not slot.attending:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('主治'):
                    unfilled.append((date_str, '主治'))
            
            if not slot.resident:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('總醫師'):
                    unfilled.append((date_str, '總醫師'))
        
        return unfilled
    
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
    
    def _create_state(self, schedule: Dict, variant_id: int = 0) -> SchedulingState:
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
        score = self._calculate_score(schedule, filled_count, unfilled_slots, variant_id)
        
        return SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
    
    def _create_empty_state(self) -> SchedulingState:
        """創建空白狀態（備用）"""
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        return self._create_state(schedule)
    
    def _calculate_score(self, schedule: Dict, filled_count: int,
                        unfilled_slots: List, variant_id: int) -> float:
        """計算分數"""
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
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        preference_satisfied += 1
        
        if preference_total > 0:
            preference_rate = preference_satisfied / preference_total
            score += preference_rate * 500
        
        # 3. 假日覆蓋率
        holiday_filled = 0
        for date_str in self.holidays:
            slot = schedule[date_str]
            if slot.attending:
                holiday_filled += 1
            if slot.resident:
                holiday_filled += 1
        
        holiday_fill_rate = holiday_filled / (len(self.holidays) * 2) if self.holidays else 0
        score += holiday_fill_rate * 200
        
        # 4. 配額使用均衡度
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
            score += balance_score * 30
        
        # 5. 變體差異化
        score += variant_id * 2.5
        
        return score
    
    def _final_validation(self, state: SchedulingState) -> List[str]:
        """最終驗證排班是否違反硬約束"""
        violations = []
        schedule = state.schedule
        used_quota = self._calculate_used_quota(schedule)
        
        for date_str, slot in schedule.items():
            # 檢查主治醫師
            if slot.attending:
                doctor = self.doctor_map[slot.attending]
                
                # 硬約束3: 不可值班日
                if date_str in doctor.unavailable_dates:
                    violations.append(f"{date_str}: {slot.attending} 被排在不可值班日")
                
                # 硬約束4: 優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('主治', [])
                    if preferred and slot.attending not in preferred:
                        violations.append(f"{date_str}: 主治應該是 {preferred}，但排了 {slot.attending}")
            
            # 檢查總醫師
            if slot.resident:
                doctor = self.doctor_map[slot.resident]
                
                # 硬約束3: 不可值班日
                if date_str in doctor.unavailable_dates:
                    violations.append(f"{date_str}: {slot.resident} 被排在不可值班日")
                
                # 硬約束4: 優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('總醫師', [])
                    if preferred and slot.resident not in preferred:
                        violations.append(f"{date_str}: 總醫師應該是 {preferred}，但排了 {slot.resident}")
        
        # 檢查配額
        for doctor_name, quotas in used_quota.items():
            doctor = self.doctor_map[doctor_name]
            if quotas['weekday'] > doctor.weekday_quota:
                violations.append(f"{doctor_name} 平日配額超過 ({quotas['weekday']}/{doctor.weekday_quota})")
            if quotas['holiday'] > doctor.holiday_quota:
                violations.append(f"{doctor_name} 假日配額超過 ({quotas['holiday']}/{doctor.holiday_quota})")
        
        return violations