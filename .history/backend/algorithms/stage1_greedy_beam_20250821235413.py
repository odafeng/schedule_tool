"""
Stage 1: Greedy + Beam Search 快速排班
診斷加強版：找出為什麼不可值班日會被違反
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
    """Stage 1: Greedy + Beam Search 排班器 - 診斷加強版"""
    
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
        
        # 診斷：列印醫師的不可值班日格式
        st.write("🔍 診斷：檢查不可值班日格式")
        for doctor in self.doctors[:2]:  # 只顯示前兩個醫師作為範例
            if doctor.unavailable_dates:
                st.write(f"  {doctor.name} 的不可值班日: {doctor.unavailable_dates[:3]}...")
        
        # 診斷：檢查日期格式
        if self.weekdays:
            st.write(f"  平日格式範例: {self.weekdays[0]}")
        if self.holidays:
            st.write(f"  假日格式範例: {self.holidays[0]}")
        
        # 建立不可值班日映射（使用集合加速查詢）
        self.doctor_unavailable = {}
        for doctor in self.doctors:
            # 確保不可值班日是集合，方便快速查詢
            self.doctor_unavailable[doctor.name] = set(doctor.unavailable_dates)
        
        # 建立優先值班日映射
        self.doctor_preferred = {}
        for doctor in self.doctors:
            self.doctor_preferred[doctor.name] = set(doctor.preferred_dates)
        
        # 建立優先值班日的反向映射：date -> role -> doctors
        self.preferred_assignments = self._build_preferred_assignments()
        
        # 診斷資訊
        self.diagnostic_info = {
            'constraint_violations': [],
            'hard_constraint_checks': [],
            'assignment_attempts': [],
            'final_violations': []
        }
    
    def _build_preferred_assignments(self) -> Dict[str, Dict[str, List[str]]]:
        """建立優先值班日映射：date -> role -> [doctors]"""
        assignments = defaultdict(lambda: {'主治': [], '總醫師': []})
        
        for doctor in self.doctors:
            for date in doctor.preferred_dates:
                assignments[date][doctor.role].append(doctor.name)
        
        return dict(assignments)
    
    def _can_assign(self, doctor_name: str, date_str: str, role: str,
                   schedule: Dict, used_quota: Dict) -> Tuple[bool, str]:
        """
        檢查是否可以分配醫師到特定日期和角色
        
        Returns:
            (是否可以分配, 如果不行的原因)
        """
        doctor = self.doctor_map[doctor_name]
        
        # === 硬約束1：同一日同一角色只能一人 ===
        slot = schedule[date_str]
        if role == "主治" and slot.attending is not None:
            return False, f"該日主治已有 {slot.attending}"
        if role == "總醫師" and slot.resident is not None:
            return False, f"該日總醫師已有 {slot.resident}"
        
        # === 硬約束2：配額限制 ===
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        current_used = used_quota.get(doctor_name, {}).get(quota_type, 0)
        
        if current_used >= max_quota:
            return False, f"{doctor_name} 的{quota_type}配額已滿 ({current_used}/{max_quota})"
        
        # === 硬約束3：不可值班日（最重要！）===
        # 使用預先建立的集合來檢查
        if date_str in self.doctor_unavailable[doctor_name]:
            self.diagnostic_info['hard_constraint_checks'].append(
                f"❌ {date_str}: {doctor_name} 不可值班但嘗試分配"
            )
            return False, f"{date_str} 是 {doctor_name} 的不可值班日"
        
        # === 硬約束4：優先值班日 ===
        if date_str in self.preferred_assignments:
            preferred_list = self.preferred_assignments[date_str].get(role, [])
            if preferred_list and doctor_name not in preferred_list:
                return False, f"{date_str} 是 {', '.join(preferred_list)} 的優先值班日"
        
        # === 硬約束5：連續值班限制 ===
        consecutive_days = self._calculate_consecutive_days(
            doctor_name, date_str, schedule
        )
        if consecutive_days > self.constraints.max_consecutive_days:
            return False, f"會造成連續值班 {consecutive_days} 天（上限 {self.constraints.max_consecutive_days}）"
        
        # === 額外檢查：同日不能擔任兩個角色 ===
        if doctor_name == slot.attending or doctor_name == slot.resident:
            return False, f"{doctor_name} 當日已擔任其他角色"
        
        return True, ""
    
    def _calculate_consecutive_days(self, doctor_name: str, target_date: str,
                                   schedule: Dict) -> int:
        """計算如果在 target_date 排班會連續幾天"""
        sorted_dates = sorted(schedule.keys())
        if target_date not in sorted_dates:
            return 1
        
        date_idx = sorted_dates.index(target_date)
        consecutive = 1  # 包含目標日
        
        # 向前檢查
        for i in range(date_idx - 1, -1, -1):
            slot = schedule[sorted_dates[i]]
            if doctor_name == slot.attending or doctor_name == slot.resident:
                consecutive += 1
            else:
                break
        
        # 向後檢查
        for i in range(date_idx + 1, len(sorted_dates)):
            slot = schedule[sorted_dates[i]]
            if doctor_name == slot.attending or doctor_name == slot.resident:
                consecutive += 1
            else:
                break
        
        return consecutive
    
    def _assign(self, schedule: Dict, date_str: str, role: str,
               doctor_name: str, used_quota: Dict) -> bool:
        """
        執行分配（先檢查再分配）
        """
        # 最終檢查
        can_assign, reason = self._can_assign(
            doctor_name, date_str, role, schedule, used_quota
        )
        
        if not can_assign:
            self.diagnostic_info['assignment_attempts'].append(
                f"✗ 無法分配 {doctor_name} 到 {date_str} {role}: {reason}"
            )
            return False
        
        # 執行分配
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        
        if role == "主治":
            schedule[date_str].attending = doctor_name
        else:
            schedule[date_str].resident = doctor_name
        
        # 更新配額使用
        if doctor_name not in used_quota:
            used_quota[doctor_name] = {'weekday': 0, 'holiday': 0}
        used_quota[doctor_name][quota_type] += 1
        
        self.diagnostic_info['assignment_attempts'].append(
            f"✓ 成功分配 {doctor_name} 到 {date_str} {role}"
        )
        
        return True
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """執行排班"""
        
        # 清空診斷資訊
        self.diagnostic_info['hard_constraint_checks'].clear()
        self.diagnostic_info['assignment_attempts'].clear()
        
        # Stage 1: 初始化
        initial_states = self._greedy_initialization()
        
        # Stage 2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        # 最終驗證並報告
        st.write("### 🔍 最終驗證結果")
        for idx, state in enumerate(final_states):
            violations = self._validate_schedule(state.schedule)
            if violations:
                st.error(f"方案 {idx+1} 違反硬約束：")
                for v in violations[:5]:  # 只顯示前5個
                    st.write(f"  - {v}")
            else:
                st.success(f"方案 {idx+1} 通過所有硬約束檢查")
        
        return final_states
    
    def _greedy_initialization(self) -> List[SchedulingState]:
        """初始化多個不同的排班方案"""
        states = []
        
        # 產生5個不同的初始方案
        for variant in range(5):
            schedule = {}
            for date_str in self.weekdays + self.holidays:
                schedule[date_str] = ScheduleSlot(date=date_str)
            
            used_quota = {}
            
            # Phase 1: 處理優先值班日
            self._handle_preferred_dates(schedule, used_quota)
            
            # Phase 2: 使用不同策略填充其他日期
            if variant == 0:
                # 策略1：假日優先，稀缺醫師優先
                self._fill_strategy_holiday_first(schedule, used_quota, 0.7)
            elif variant == 1:
                # 策略2：平日優先
                self._fill_strategy_weekday_first(schedule, used_quota, 0.6)
            elif variant == 2:
                # 策略3：隨機順序
                self._fill_strategy_random(schedule, used_quota, 0.65, seed=variant)
            elif variant == 3:
                # 策略4：最小填充
                self._fill_strategy_minimal(schedule, used_quota, 0.5)
            else:
                # 策略5：交替填充
                self._fill_strategy_alternating(schedule, used_quota, 0.75)
            
            # 創建狀態，確保每個都有不同的分數
            state = self._create_state(schedule, used_quota, variant)
            states.append(state)
        
        return states
    
    def _handle_preferred_dates(self, schedule: Dict, used_quota: Dict):
        """處理優先值班日（硬約束4）"""
        for date_str, roles in self.preferred_assignments.items():
            for role, doctors in roles.items():
                if not doctors:
                    continue
                
                # 嘗試分配給優先的醫師
                assigned = False
                for doctor_name in doctors:
                    can_assign, reason = self._can_assign(
                        doctor_name, date_str, role, schedule, used_quota
                    )
                    if can_assign:
                        self._assign(schedule, date_str, role, doctor_name, used_quota)
                        assigned = True
                        break
                
                if not assigned and doctors:
                    self.diagnostic_info['constraint_violations'].append(
                        f"無法滿足優先值班：{date_str} {role} ({', '.join(doctors)})"
                    )
    
    def _fill_strategy_holiday_first(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """策略1：假日優先填充"""
        slots = []
        
        # 先加入假日
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        # 再加入平日
        for date_str in self.weekdays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        # 只填充部分
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_strategy_weekday_first(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """策略2：平日優先填充"""
        slots = []
        
        # 先加入平日
        for date_str in self.weekdays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        # 再加入假日
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_strategy_random(self, schedule: Dict, used_quota: Dict, fill_ratio: float, seed: int):
        """策略3：隨機順序填充"""
        random.seed(seed)
        slots = []
        
        for date_str in self.weekdays + self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        random.shuffle(slots)
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_strategy_minimal(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """策略4：最小填充"""
        slots = []
        
        # 只填充假日
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_strategy_alternating(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """策略5：交替填充"""
        holiday_slots = []
        weekday_slots = []
        
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                holiday_slots.append((date_str, '主治'))
            if not slot.resident:
                holiday_slots.append((date_str, '總醫師'))
        
        for date_str in self.weekdays:
            slot = schedule[date_str]
            if not slot.attending:
                weekday_slots.append((date_str, '主治'))
            if not slot.resident:
                weekday_slots.append((date_str, '總醫師'))
        
        # 交替合併
        slots = []
        while holiday_slots or weekday_slots:
            if holiday_slots:
                slots.append(holiday_slots.pop(0))
            if weekday_slots:
                slots.append(weekday_slots.pop(0))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_slots(self, schedule: Dict, used_quota: Dict, slots: List[Tuple[str, str]]):
        """填充指定的格子"""
        for date_str, role in slots:
            # 跳過已經有優先值班的格子
            if date_str in self.preferred_assignments:
                if self.preferred_assignments[date_str].get(role):
                    continue
            
            # 取得候選醫師
            doctors = self.attending_doctors if role == "主治" else self.resident_doctors
            
            # 嘗試分配
            for doctor in doctors:
                can_assign, reason = self._can_assign(
                    doctor.name, date_str, role, schedule, used_quota
                )
                if can_assign:
                    self._assign(schedule, date_str, role, doctor.name, used_quota)
                    break
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int, progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        # 準備 beam
        beam = []
        for state in initial_states:
            beam.append({
                'state': state,
                'used_quota': self._recalculate_quota(state.schedule)
            })
        
        # 收集未填格子
        unfilled = []
        for date_str in self.holidays + self.weekdays:  # 假日優先
            slot = initial_states[0].schedule[date_str]
            
            if not slot.attending:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('主治'):
                    unfilled.append((date_str, '主治'))
            
            if not slot.resident:
                if date_str not in self.preferred_assignments or \
                   not self.preferred_assignments[date_str].get('總醫師'):
                    unfilled.append((date_str, '總醫師'))
        
        # 限制處理數量
        max_steps = min(20, len(unfilled))
        
        # Beam Search 主循環
        for step, (date_str, role) in enumerate(unfilled[:max_steps]):
            new_beam = []
            
            for item in beam:
                current_state = item['state']
                current_quota = copy.deepcopy(item['used_quota'])
                
                # 取得可用醫師
                doctors = self.attending_doctors if role == "主治" else self.resident_doctors
                candidates = []
                
                for doctor in doctors:
                    can_assign, _ = self._can_assign(
                        doctor.name, date_str, role,
                        current_state.schedule, current_quota
                    )
                    if can_assign:
                        candidates.append(doctor.name)
                
                if not candidates:
                    # 無人可用，保持原狀
                    new_beam.append(item)
                else:
                    # 嘗試前3個候選人
                    for doctor_name in candidates[:3]:
                        new_schedule = copy.deepcopy(current_state.schedule)
                        new_quota = copy.deepcopy(current_quota)
                        
                        if self._assign(new_schedule, date_str, role, doctor_name, new_quota):
                            new_state = self._create_state(new_schedule, new_quota, step % 5)
                            new_beam.append({
                                'state': new_state,
                                'used_quota': new_quota
                            })
            
            # 保留 Top-K
            new_beam.sort(key=lambda x: x['state'].score, reverse=True)
            beam = new_beam[:beam_width]
            
            if progress_callback:
                progress_callback((step + 1) / max_steps)
        
        return [item['state'] for item in beam]
    
    def _recalculate_quota(self, schedule: Dict) -> Dict:
        """重新計算配額使用"""
        used_quota = {}
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            quota_type = 'holiday' if is_holiday else 'weekday'
            
            if slot.attending:
                if slot.attending not in used_quota:
                    used_quota[slot.attending] = {'weekday': 0, 'holiday': 0}
                used_quota[slot.attending][quota_type] += 1
            
            if slot.resident:
                if slot.resident not in used_quota:
                    used_quota[slot.resident] = {'weekday': 0, 'holiday': 0}
                used_quota[slot.resident][quota_type] += 1
        
        return used_quota
    
    def _create_state(self, schedule: Dict, used_quota: Dict, variant_id: int) -> SchedulingState:
        """創建排班狀態"""
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
        
        # 計算分數（加入變化確保不同）
        total_slots = len(schedule) * 2
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        
        # 基礎分數
        score = fill_rate * 1000
        
        # 假日覆蓋
        holiday_filled = sum(1 for d in self.holidays 
                           if schedule[d].attending or schedule[d].resident)
        score += holiday_filled * 50
        
        # 優先值班滿足度
        pref_satisfied = 0
        for doctor in self.doctors:
            for pref_date in doctor.preferred_dates:
                if pref_date in schedule:
                    slot = schedule[pref_date]
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        pref_satisfied += 1
        score += pref_satisfied * 100
        
        # 確保每個方案分數不同
        score += variant_id * 10  # 每個變體差10分
        score += random.random()  # 加入小隨機數
        
        return SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
    
    def _validate_schedule(self, schedule: Dict) -> List[str]:
        """驗證排班是否違反硬約束"""
        violations = []
        used_quota = self._recalculate_quota(schedule)
        
        for date_str, slot in schedule.items():
            # 檢查主治醫師
            if slot.attending:
                doctor = self.doctor_map[slot.attending]
                
                # 檢查不可值班日
                if date_str in self.doctor_unavailable[slot.attending]:
                    violations.append(
                        f"❌ {date_str}: {slot.attending} 在不可值班日被排班"
                    )
                
                # 檢查優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('主治', [])
                    if preferred and slot.attending not in preferred:
                        violations.append(
                            f"❌ {date_str}: 主治應為 {preferred}，實際為 {slot.attending}"
                        )
            
            # 檢查總醫師
            if slot.resident:
                doctor = self.doctor_map[slot.resident]
                
                # 檢查不可值班日
                if date_str in self.doctor_unavailable[slot.resident]:
                    violations.append(
                        f"❌ {date_str}: {slot.resident} 在不可值班日被排班"
                    )
                
                # 檢查優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('總醫師', [])
                    if preferred and slot.resident not in preferred:
                        violations.append(
                            f"❌ {date_str}: 總醫師應為 {preferred}，實際為 {slot.resident}"
                        )
        
        # 檢查配額
        for doctor_name, quotas in used_quota.items():
            doctor = self.doctor_map[doctor_name]
            if quotas.get('weekday', 0) > doctor.weekday_quota:
                violations.append(
                    f"❌ {doctor_name} 平日配額超過 ({quotas['weekday']}/{doctor.weekday_quota})"
                )
            if quotas.get('holiday', 0) > doctor.holiday_quota:
                violations.append(
                    f"❌ {doctor_name} 假日配額超過 ({quotas['holiday']}/{doctor.holiday_quota})"
                )
        
        return violations