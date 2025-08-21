"""
Stage 1: Greedy + Beam Search 快速排班
優先值班日、不可值班日、連續值班限制為強制硬約束
改進版：增強方案多樣性與分數差異化
"""
import copy
import random
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
import hashlib
import time
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
        
        # 建立不可值班日映射表（硬約束1）
        self.unavailable_map = self._build_unavailable_map()
        
        # 建立優先值班日映射表（硬約束2）
        self.preferred_assignments = self._build_preferred_assignments()
        
        # 檢查優先值班日衝突
        self.preference_conflicts = self._check_preference_conflicts()
        
        # 驗證硬約束可行性
        self.constraint_issues = self._validate_all_hard_constraints()
        
        # 計算每個格子的靈活度（新增）
        self.slot_flexibility = self._calculate_slot_flexibility()
        
        # 用於追蹤已生成的方案（新增）
        self.generated_schedules = set()
        
        # 決策日誌
        self.decision_log = []
        
        # 診斷資訊
        self.diagnostic_info = {
            'constraint_violations': [],
            'fill_attempts': 0,
            'fill_successes': 0,
            'skip_reasons': defaultdict(int),
            'preferred_fulfillment': {},
            'hard_constraint_violations': [],
            'variant_strategies': []  # 新增：記錄每個變體使用的策略
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
        """計算每個格子的靈活度（約束越少，靈活度越高）"""
        flexibility = {}
        
        for date_str in self.weekdays + self.holidays:
            # 跳過優先值班日（這些是硬約束）
            if date_str in self.preferred_assignments:
                flexibility[date_str] = {
                    'attending': 0,  # 優先值班日靈活度為0
                    'resident': 0,
                    'overall': 0
                }
                continue
            
            # 計算可用醫師數
            available_attending = sum(1 for d in self.attending_doctors 
                                    if date_str not in d.unavailable_dates)
            available_resident = sum(1 for d in self.resident_doctors 
                                   if date_str not in d.unavailable_dates)
            
            # 平日通常有更多選擇（假日醫師配額少）
            date_type_bonus = 5 if date_str in self.weekdays else 0
            
            flexibility[date_str] = {
                'attending': available_attending + date_type_bonus,
                'resident': available_resident + date_type_bonus,
                'overall': available_attending + available_resident + date_type_bonus * 2
            }
        
        return flexibility
    
    def _build_unavailable_map(self) -> Dict[str, Dict[str, List[str]]]:
        """建立不可值班日映射：date -> role -> [unavailable_doctors]"""
        unavailable = defaultdict(lambda: {'主治': [], '總醫師': []})
        
        for doctor in self.doctors:
            role = doctor.role
            for date in doctor.unavailable_dates:
                unavailable[date][role].append(doctor.name)
        
        # 診斷資訊：記錄嚴重問題
        for date, roles in unavailable.items():
            for role, doctors in roles.items():
                # 如果某天某角色所有醫師都不可值班，這是個嚴重問題
                all_doctors = self.attending_doctors if role == "主治" else self.resident_doctors
                available_doctors = [d for d in all_doctors 
                                   if d.name not in doctors]
                if not available_doctors:
                    warning = f"嚴重警告：{date} 沒有可用的{role}醫師！"
                    self.diagnostic_info['constraint_violations'].append(warning)
        
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
                # 硬約束1: 不可值班日
                if date_str in doctor.unavailable_dates:
                    continue
                # 檢查配額
                quota_type = 'holiday' if is_holiday else 'weekday'
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
                quota_type = 'holiday' if is_holiday else 'weekday'
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
        
        # Stage 1.1: Greedy 初始化（嚴格遵守三個硬約束）
        initial_states = self._greedy_initialization_improved()
        
        # Stage 1.2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        return final_states
    
    def _greedy_initialization_improved(self) -> List[SchedulingState]:
        """改進的 Greedy 初始化：確保產生真正不同的方案"""
        
        states = []
        self.generated_schedules.clear()
        max_attempts = 20  # 最多嘗試20次
        
        for variant_idx in range(min(5, self.constraints.beam_width)):
            attempts = 0
            unique_state = None
            
            while attempts < max_attempts:
                # 產生基礎排班
                schedule = {}
                for date_str in self.weekdays + self.holidays:
                    schedule[date_str] = ScheduleSlot(date=date_str)
                
                # 記錄已使用配額
                used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
                
                # Phase 1: 處理所有優先值班日（硬約束2）
                self._process_preferred_dates_with_all_constraints(schedule, used_quota)
                
                # Phase 2: 使用不同策略產生變體
                strategy = self._select_variant_strategy(variant_idx, attempts)
                self._apply_variant_strategy(schedule, used_quota, strategy)
                
                # 計算排班的 hash
                schedule_hash = self._calculate_schedule_hash(schedule)
                
                # 確認是否為新的排班
                if schedule_hash not in self.generated_schedules:
                    self.generated_schedules.add(schedule_hash)
                    # 創建狀態，並給予獨特的ID以確保分數差異
                    unique_state = self._create_state(schedule, variant_idx)
                    break
                
                attempts += 1
            
            # 如果成功產生獨特方案，加入列表
            if unique_state:
                states.append(unique_state)
                self.diagnostic_info['variant_strategies'].append(
                    f"方案{variant_idx + 1}: 使用策略{strategy['name']}"
                )
            else:
                # 如果無法產生獨特方案，使用強制清空策略
                forced_state = self._create_forced_variant(variant_idx)
                if forced_state:
                    states.append(forced_state)
        
        return states
    
    def _select_variant_strategy(self, variant_idx: int, attempt: int) -> Dict:
        """選擇變體策略"""
        strategies = [
            {'name': '標準填充70%', 'fill_ratio': 0.7, 'clear_flexible': False},
            {'name': '保守填充60%', 'fill_ratio': 0.6, 'clear_flexible': False},
            {'name': '激進填充80%', 'fill_ratio': 0.8, 'clear_flexible': False},
            {'name': '清空靈活格子重填', 'fill_ratio': 0.65, 'clear_flexible': True},
            {'name': '隨機策略', 'fill_ratio': 0.5 + random.random() * 0.3, 'clear_flexible': random.random() > 0.5},
        ]
        
        # 根據變體索引和嘗試次數選擇策略
        strategy_idx = (variant_idx + attempt) % len(strategies)
        return strategies[strategy_idx]
    
    def _apply_variant_strategy(self, schedule: Dict, used_quota: Dict, strategy: Dict):
        """應用變體策略"""
        if strategy['clear_flexible']:
            # 清空靈活格子策略
            self._clear_and_refill_flexible_slots(schedule, used_quota, strategy['fill_ratio'])
        else:
            # 標準填充策略
            random_seed = int(time.time() * 1000) % 10000
            self._fill_remaining_slots_with_variation(
                schedule, used_quota, strategy['fill_ratio'], random_seed
            )
    
    def _clear_and_refill_flexible_slots(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """清空靈活格子並重新填充（新策略）"""
        # 找出靈活度高的格子
        flexible_slots = []
        
        for date_str, flexibility in self.slot_flexibility.items():
            # 跳過優先值班日
            if date_str in self.preferred_assignments:
                continue
            
            slot = schedule[date_str]
            
            # 收集已填充的靈活格子
            if slot.attending and flexibility['attending'] > 3:
                flexible_slots.append((date_str, 'attending', flexibility['attending']))
            if slot.resident and flexibility['resident'] > 3:
                flexible_slots.append((date_str, 'resident', flexibility['resident']))
        
        if flexible_slots:
            # 按靈活度排序（靈活度高的優先清空）
            flexible_slots.sort(key=lambda x: x[2], reverse=True)
            
            # 清空部分格子
            num_to_clear = min(len(flexible_slots) // 2, 10)
            slots_to_clear = flexible_slots[:num_to_clear]
            
            # 執行清空
            for date_str, position, _ in slots_to_clear:
                is_holiday = date_str in self.holidays
                quota_type = 'holiday' if is_holiday else 'weekday'
                
                if position == 'attending':
                    if schedule[date_str].attending:
                        used_quota[schedule[date_str].attending][quota_type] -= 1
                        schedule[date_str].attending = None
                else:
                    if schedule[date_str].resident:
                        used_quota[schedule[date_str].resident][quota_type] -= 1
                        schedule[date_str].resident = None
        
        # 用不同順序重新填充
        self._refill_with_random_order(schedule, used_quota, fill_ratio)
    
    def _refill_with_random_order(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """用隨機順序重新填充"""
        # 隨機打亂醫師順序
        attending_order = list(self.attending_doctors)
        resident_order = list(self.resident_doctors)
        random.shuffle(attending_order)
        random.shuffle(resident_order)
        
        # 排序日期：假日優先，但加入隨機性
        all_dates = self.holidays + self.weekdays
        random.shuffle(all_dates[len(self.holidays):])  # 打亂平日順序
        
        dates_to_fill = all_dates[:int(len(all_dates) * fill_ratio)]
        
        for date_str in dates_to_fill:
            is_holiday = date_str in self.holidays
            
            # 排主治醫師
            if not schedule[date_str].attending:
                for doctor in attending_order:
                    if self._check_hard_constraints(doctor, date_str, schedule, used_quota, is_holiday):
                        schedule[date_str].attending = doctor.name
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor.name][quota_type] += 1
                        break
            
            # 排總醫師
            if not schedule[date_str].resident:
                for doctor in resident_order:
                    if self._check_hard_constraints(doctor, date_str, schedule, used_quota, is_holiday):
                        schedule[date_str].resident = doctor.name
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor.name][quota_type] += 1
                        break
    
    def _fill_remaining_slots_with_variation(self, schedule: Dict, used_quota: Dict, 
                                            fill_ratio: float, seed: int):
        """填充剩餘格子（加入變化）"""
        random.seed(seed)
        
        # 排序日期：假日優先
        sorted_dates = self.holidays + self.weekdays
        
        # 只填充指定比例的格子
        dates_to_fill = sorted_dates[:int(len(sorted_dates) * fill_ratio)]
        
        for date_str in dates_to_fill:
            is_holiday = date_str in self.holidays
            
            # 排主治醫師（如果還沒排）
            if not schedule[date_str].attending:
                candidates = self._get_safe_candidates(
                    date_str, "主治", schedule, used_quota, is_holiday
                )
                if candidates:
                    # 大部分時候選最佳，偶爾選次佳（增加多樣性）
                    selection_idx = 0
                    if len(candidates) > 1 and random.random() < 0.2:
                        selection_idx = min(1, len(candidates) - 1)
                    
                    best_doctor = candidates[selection_idx]
                    schedule[date_str].attending = best_doctor
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[best_doctor][quota_type] += 1
            
            # 排總醫師（如果還沒排）
            if not schedule[date_str].resident:
                candidates = self._get_safe_candidates(
                    date_str, "總醫師", schedule, used_quota, is_holiday
                )
                if candidates:
                    # 大部分時候選最佳，偶爾選次佳（增加多樣性）
                    selection_idx = 0
                    if len(candidates) > 1 and random.random() < 0.2:
                        selection_idx = min(1, len(candidates) - 1)
                    
                    best_doctor = candidates[selection_idx]
                    schedule[date_str].resident = best_doctor
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[best_doctor][quota_type] += 1
    
    def _create_forced_variant(self, variant_idx: int) -> Optional[SchedulingState]:
        """強制創建不同的變體"""
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        # 處理優先值班日
        self._process_preferred_dates_with_all_constraints(schedule, used_quota)
        
        # 極端策略：只填充 40% + variant_idx * 5%
        fill_ratio = 0.4 + variant_idx * 0.05
        
        # 使用完全不同的醫師優先順序
        attending_order = sorted(self.attending_doctors, 
                               key=lambda d: self.doctor_scarcity[d.name]['overall'],
                               reverse=(variant_idx % 2 == 0))
        resident_order = sorted(self.resident_doctors,
                              key=lambda d: self.doctor_scarcity[d.name]['overall'],
                              reverse=(variant_idx % 2 == 0))
        
        sorted_dates = self.holidays + self.weekdays
        dates_to_fill = sorted_dates[:int(len(sorted_dates) * fill_ratio)]
        
        for date_str in dates_to_fill:
            is_holiday = date_str in self.holidays
            
            if not schedule[date_str].attending:
                for doctor in attending_order:
                    if self._check_hard_constraints(doctor, date_str, schedule, used_quota, is_holiday):
                        schedule[date_str].attending = doctor.name
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor.name][quota_type] += 1
                        break
            
            if not schedule[date_str].resident:
                for doctor in resident_order:
                    if self._check_hard_constraints(doctor, date_str, schedule, used_quota, is_holiday):
                        schedule[date_str].resident = doctor.name
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor.name][quota_type] += 1
                        break
        
        return self._create_state(schedule, variant_idx)

    
    def _calculate_score_with_variant(self, schedule: Dict, filled_count: int,
                                     unfilled_slots: List, variant_id: int) -> float:
        """計算分數（增強差異化）"""
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
            score += preference_rate * 500
        
        # 3. 連續值班懲罰（檢查是否有違反硬約束）
        consecutive_penalty = self._calculate_consecutive_penalty(schedule)
        score -= consecutive_penalty * 100
        
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
        
        # 6. 靈活格子利用率（新增）
        flexibility_utilization = self._calculate_flexibility_utilization(schedule)
        score += flexibility_utilization * 20
        
        # 7. 變體ID差異化（確保不同方案有不同分數）
        score += variant_id * 2.5  # 每個變體至少相差2.5分
        
        # 8. 微小隨機擾動（基於schedule hash，確保相同排班有相同分數）
        schedule_hash = self._calculate_schedule_hash(schedule)
        hash_value = int(schedule_hash[:8], 16)
        score += (hash_value % 100) * 0.01
        
        return score
    
    def _calculate_flexibility_utilization(self, schedule: Dict) -> float:
        """計算靈活格子利用率（優先填充約束多的格子）"""
        utilization_score = 0.0
        total_weight = 0.0
        
        for date_str, slot in schedule.items():
            if date_str in self.slot_flexibility:
                flexibility = self.slot_flexibility[date_str]
                
                # 靈活度低的格子如果被填充，給予更高分數
                if slot.attending:
                    weight = 1.0 / max(flexibility['attending'], 1)
                    utilization_score += weight
                    total_weight += weight
                
                if slot.resident:
                    weight = 1.0 / max(flexibility['resident'], 1)
                    utilization_score += weight
                    total_weight += weight
        
        return utilization_score / max(total_weight, 1)
    
    # 以下保留原有的方法，不需要修改...
    def _process_preferred_dates_with_all_constraints(self, schedule: Dict, used_quota: Dict):
        """處理優先值班日，同時檢查所有硬約束"""
        preferred_filled = 0
        preferred_failed = []
        
        for date_str, roles in self.preferred_assignments.items():
            if date_str not in schedule:
                continue
            
            is_holiday = date_str in self.holidays
            
            for role, doctor_names in roles.items():
                if not doctor_names:
                    continue
                
                selected_doctor = None
                
                if len(doctor_names) > 1:
                    # 多個醫師都設定了優先值班，需要選擇
                    selected_doctor = self._select_best_preferred_with_all_constraints(
                        doctor_names, date_str, is_holiday, used_quota, schedule
                    )
                else:
                    # 單一醫師，但仍需檢查所有硬約束
                    doctor_name = doctor_names[0]
                    doctor = self.doctor_map[doctor_name]
                    if self._check_hard_constraints(
                        doctor, date_str, schedule, used_quota, is_holiday
                    ):
                        selected_doctor = doctor_name
                    else:
                        # 記錄為什麼無法滿足
                        reason = self._get_constraint_violation_reason(
                            doctor, date_str, schedule, used_quota, is_holiday
                        )
                        preferred_failed.append(f"{date_str} {role} ({doctor_name}): {reason}")
                
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
                    
                    self.diagnostic_info['preferred_fulfillment'][f"{date_str}_{role}"] = selected_doctor
                else:
                    # 無法滿足優先值班
                    if len(doctor_names) == 1:
                        pass  # 已經記錄在上面
                    else:
                        preferred_failed.append(
                            f"{date_str} {role}: 所有設定優先值班的醫師都無法排班"
                        )
        
        if preferred_failed:
            self.diagnostic_info['constraint_violations'].extend(preferred_failed)
    
    def _select_best_preferred_with_all_constraints(self, doctor_names: List[str], 
                                                   date_str: str, is_holiday: bool,
                                                   used_quota: Dict, schedule: Dict) -> Optional[str]:
        """從多個優先值班醫師中選擇最佳的（考慮所有硬約束）"""
        candidates = []
        
        for name in doctor_names:
            doctor = self.doctor_map[name]
            
            # 檢查所有硬約束
            if not self._check_hard_constraints(
                doctor, date_str, schedule, used_quota, is_holiday
            ):
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
        
        return candidates[0][0]
    
    def _check_hard_constraints(self, doctor: Doctor, date_str: str,
                               schedule: Dict, used_quota: Dict,
                               is_holiday: bool) -> bool:
        """統一的硬約束檢查函數
        
        檢查五個硬約束：
        1. 不可值班日
        2. 配額限制
        3. 連續值班限制
        4. 同日不能擔任兩個角色
        5. 保留配額給優先值班日
        """
        # 硬約束1: 不可值班日
        if date_str in doctor.unavailable_dates:
            return False
        
        # 硬約束2: 配額限制
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        if used_quota[doctor.name][quota_type] >= max_quota:
            return False
        
        # 硬約束3: 連續值班限制
        max_consecutive = self.constraints.max_consecutive_days
        sorted_dates = sorted(schedule.keys())
        date_index = sorted_dates.index(date_str)
        
        # 計算連續天數
        consecutive_count = 1  # 當天
        
        # 向前檢查
        for i in range(date_index - 1, -1, -1):
            if doctor.name in [schedule[sorted_dates[i]].attending, 
                             schedule[sorted_dates[i]].resident]:
                consecutive_count += 1
            else:
                break
        
        # 向後檢查
        for i in range(date_index + 1, len(sorted_dates)):
            if doctor.name in [schedule[sorted_dates[i]].attending,
                             schedule[sorted_dates[i]].resident]:
                consecutive_count += 1
            else:
                break
        
        if consecutive_count > max_consecutive:
            return False
        
        # 硬約束4: 同日不能擔任兩個角色
        slot = schedule[date_str]
        if doctor.name in [slot.attending, slot.resident]:
            return False
        
        # 硬約束5: 保留配額給優先值班日
        unfulfilled = self._get_unfulfilled_preferred_dates(doctor, schedule, is_holiday)
        if unfulfilled and date_str not in doctor.preferred_dates:
            remaining = max_quota - used_quota[doctor.name][quota_type] - 1
            if remaining < len(unfulfilled):
                return False
        
        return True
    
    def _get_constraint_violation_reason(self, doctor: Doctor, date_str: str,
                                        schedule: Dict, used_quota: Dict,
                                        is_holiday: bool) -> str:
        """取得違反約束的原因（用於診斷）"""
        # 硬約束1: 不可值班日
        if date_str in doctor.unavailable_dates:
            return "不可值班日"
        
        # 硬約束2: 配額限制
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        if used_quota[doctor.name][quota_type] >= max_quota:
            return f"已達{quota_type}配額上限"
        
        # 硬約束3: 連續值班限制
        # 使用相同的邏輯檢查連續天數
        max_consecutive = self.constraints.max_consecutive_days
        sorted_dates = sorted(schedule.keys())
        date_index = sorted_dates.index(date_str)
        
        consecutive_count = 1
        # 向前檢查
        for i in range(date_index - 1, -1, -1):
            if doctor.name in [schedule[sorted_dates[i]].attending, 
                             schedule[sorted_dates[i]].resident]:
                consecutive_count += 1
            else:
                break
        # 向後檢查
        for i in range(date_index + 1, len(sorted_dates)):
            if doctor.name in [schedule[sorted_dates[i]].attending,
                             schedule[sorted_dates[i]].resident]:
                consecutive_count += 1
            else:
                break
        
        if consecutive_count > max_consecutive:
            return f"違反連續值班限制（最多{max_consecutive}天）"
        
        # 硬約束4: 同日重複角色
        slot = schedule[date_str]
        if doctor.name in [slot.attending, slot.resident]:
            return "同日已擔任其他角色"
        
        return "未知原因"
    
    def _get_safe_candidates(self, date_str: str, role: str,
                            schedule: Dict, used_quota: Dict,
                            is_holiday: bool) -> List[str]:
        """取得候選人（嚴格檢查所有硬約束）"""
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
            
            # 檢查所有硬約束
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
    
    def _check_all_hard_constraints(self, doctor: Doctor, date_str: str,
                                   schedule: Dict, used_quota: Dict,
                                   is_holiday: bool) -> bool:
        """檢查所有硬約束（完整版）
        這是為了向後兼容，直接調用 _check_hard_constraints
        """
        return self._check_hard_constraints(doctor, date_str, schedule, used_quota, is_holiday)
    
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
                        
                        new_state = self._create_state(new_schedule, len(new_beam) % 5)
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
        
        return self._get_safe_candidates(
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
    
    def _create_state(self, schedule: Dict, variant_id: int = 0) -> SchedulingState:
        """創建排班狀態（統一版本，支援 variant_id）"""
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
        
        # 計算分數（包含 variant_id 差異化）
        score = self._calculate_score_with_variant(schedule, filled_count, 
                                                   unfilled_slots, variant_id)
        
        # 創建狀態對象，fill_rate 會由 @property 自動計算
        state = SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
        
        return state

    
    def _calculate_consecutive_penalty(self, schedule: Dict) -> float:
        """計算連續值班懲罰（更嚴格的版本）"""
        penalty = 0
        max_consecutive = self.constraints.max_consecutive_days
        
        # 計算每個醫師的連續值班情況
        for doctor in self.doctors:
            doctor_name = doctor.name
            sorted_dates = sorted(schedule.keys())
            consecutive_count = 0
            
            for i, date_str in enumerate(sorted_dates):
                slot = schedule[date_str]
                
                if doctor_name in [slot.attending, slot.resident]:
                    consecutive_count += 1
                    
                    # 如果超過限制，給予重懲罰
                    if consecutive_count > max_consecutive:
                        penalty += (consecutive_count - max_consecutive) * 10
                else:
                    consecutive_count = 0
        
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