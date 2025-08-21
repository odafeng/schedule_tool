"""
Stage 1: Greedy + Beam Search 快速排班
使用單一策略：不可值班日最多的人先排、假日優先
透過 Beam Search 探索不同組合，產生 Top-5 方案
"""
import copy
import random
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable, Set
from collections import defaultdict
import numpy as np
from backend.models import Doctor, ScheduleSlot, ScheduleConstraints, SchedulingState
from backend.utils.date_parser import normalize_dates_to_full_format

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
        
        # 從日期格式推斷年月
        self.year, self.month = self._infer_year_month()
        
        # 統一所有日期格式
        self.doctor_unavailable = {}
        self.doctor_preferred = {}
        self.preferred_assignments = defaultdict(lambda: {'主治': [], '總醫師': []})
        
        for doctor in self.doctors:
            # 使用 date_parser 轉換不可值班日
            unavailable_normalized = normalize_dates_to_full_format(
                doctor.unavailable_dates, self.year, self.month
            )
            unavailable_converted = set()
            for date_str in unavailable_normalized:
                converted = self._convert_to_schedule_format(date_str)
                if converted:
                    unavailable_converted.add(converted)
            self.doctor_unavailable[doctor.name] = unavailable_converted
            
            # 使用 date_parser 轉換優先值班日
            preferred_normalized = normalize_dates_to_full_format(
                doctor.preferred_dates, self.year, self.month
            )
            preferred_converted = set()
            for date_str in preferred_normalized:
                converted = self._convert_to_schedule_format(date_str)
                if converted:
                    preferred_converted.add(converted)
                    self.preferred_assignments[converted][doctor.role].append(doctor.name)
            self.doctor_preferred[doctor.name] = preferred_converted
        
        # 計算醫師的不可值班日數量（用於排序）
        self.doctor_unavailable_count = {
            d.name: len(self.doctor_unavailable[d.name]) for d in self.doctors
        }
        
        # 診斷資訊
        self.diagnostic_info = {
            'perfect_solution': False,
            'violations': [],
            'beam_search_iterations': 0
        }
    
    def _infer_year_month(self) -> Tuple[int, int]:
        """從日期推斷年月"""
        for doctor in self.doctors:
            if doctor.unavailable_dates:
                date_str = doctor.unavailable_dates[0]
                if "-" in date_str and len(date_str.split("-")) == 3:
                    year, month, _ = date_str.split("-")
                    return int(year), int(month)
            if doctor.preferred_dates:
                date_str = doctor.preferred_dates[0]
                if "-" in date_str and len(date_str.split("-")) == 3:
                    year, month, _ = date_str.split("-")
                    return int(year), int(month)
        return 2025, 8
    
    def _convert_to_schedule_format(self, date_yyyy_mm_dd: str) -> Optional[str]:
        """將 YYYY-MM-DD 格式轉換為排班表使用的格式"""
        if not date_yyyy_mm_dd:
            return None
        
        if "-" in date_yyyy_mm_dd and len(date_yyyy_mm_dd.split("-")) == 3:
            year, month, day = date_yyyy_mm_dd.split("-")
            
            possible_formats = [
                f"{int(month)}/{int(day)}",
                f"{month}/{day}",
                f"{int(month):02d}/{int(day):02d}",
                date_yyyy_mm_dd
            ]
            
            for fmt in possible_formats:
                if fmt in self.weekdays or fmt in self.holidays:
                    return fmt
        
        if date_yyyy_mm_dd in self.weekdays or date_yyyy_mm_dd in self.holidays:
            return date_yyyy_mm_dd
        
        return None
    
    def _can_assign(self, doctor_name: str, date_str: str, role: str,
                   schedule: Dict, used_quota: Dict) -> Tuple[bool, str]:
        """檢查是否可以分配醫師（嚴格檢查所有硬約束）"""
        doctor = self.doctor_map[doctor_name]
        
        if date_str not in schedule:
            return False, f"日期 {date_str} 不在排班表中"
        
        slot = schedule[date_str]
        
        # 硬約束1：同一日同一角色只能一人
        if role == "主治" and slot.attending is not None:
            return False, f"該日主治已有 {slot.attending}"
        if role == "總醫師" and slot.resident is not None:
            return False, f"該日總醫師已有 {slot.resident}"
        
        # 硬約束2：配額限制
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        current_used = used_quota.get(doctor_name, {}).get(quota_type, 0)
        
        if current_used >= max_quota:
            return False, f"{doctor_name} 的{quota_type}配額已滿"
        
        # 硬約束3：不可值班日
        if date_str in self.doctor_unavailable[doctor_name]:
            return False, f"{date_str} 是 {doctor_name} 的不可值班日"
        
        # 硬約束4：優先值班日
        if date_str in self.preferred_assignments:
            preferred_list = self.preferred_assignments[date_str].get(role, [])
            if preferred_list and doctor_name not in preferred_list:
                return False, f"{date_str} 是他人的優先值班日"
        
        # 硬約束5：連續值班限制
        consecutive = self._check_consecutive_if_assigned(doctor_name, date_str, schedule)
        if consecutive > self.constraints.max_consecutive_days:
            return False, f"會造成連續值班 {consecutive} 天"
        
        # 同日不能擔任兩個角色
        if doctor_name == slot.attending or doctor_name == slot.resident:
            return False, f"{doctor_name} 當日已擔任其他角色"
        
        return True, ""
    
    def _check_consecutive_if_assigned(self, doctor_name: str, target_date: str,
                                       schedule: Dict) -> int:
        """檢查如果分配會造成連續幾天"""
        sorted_dates = sorted(schedule.keys())
        if target_date not in sorted_dates:
            return 1
        
        date_idx = sorted_dates.index(target_date)
        consecutive = 1
        
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
    
    def _assign_doctor(self, schedule: Dict, date_str: str, role: str,
                      doctor_name: str, used_quota: Dict) -> bool:
        """安全地分配醫師"""
        can_assign, reason = self._can_assign(doctor_name, date_str, role, schedule, used_quota)
        
        if not can_assign:
            return False
        
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        
        if role == "主治":
            schedule[date_str].attending = doctor_name
        else:
            schedule[date_str].resident = doctor_name
        
        if doctor_name not in used_quota:
            used_quota[doctor_name] = {'weekday': 0, 'holiday': 0}
        used_quota[doctor_name][quota_type] += 1
        
        return True
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """執行排班"""
        
        # Step 1: 嘗試產生完美解（完全滿足所有硬約束）
        perfect_solution = self._try_perfect_solution()
        
        if perfect_solution and self._is_complete(perfect_solution):
            # 如果找到完美解，直接返回
            st.success("🎉 找到完美解！所有硬約束都被滿足，且無空格！")
            self.diagnostic_info['perfect_solution'] = True
            state = self._create_state(perfect_solution)
            return [state]  # 返回完美解
        
        # Step 2: 使用 Beam Search 探索不同組合
        st.info("使用 Beam Search 探索最佳組合...")
        initial_states = self._greedy_initialization(beam_width)
        
        # Step 3: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        # Step 4: 取 Top-5
        final_states.sort(key=lambda x: x.score, reverse=True)
        top_5 = final_states[:5]
        
        # 顯示結果
        st.write("### 📊 Top-5 方案")
        for idx, state in enumerate(top_5):
            st.write(f"**方案 {idx+1}**: 分數 {state.score:.2f}, 填充率 {state.fill_rate:.1%}")
        
        return top_5
    
    def _try_perfect_solution(self) -> Optional[Dict]:
        """嘗試產生完美解（完全滿足所有硬約束且無空格）"""
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        used_quota = {}
        
        # 使用標準策略：不可值班日最多的人先排，假日優先
        
        # Step 1: 處理優先值班日
        for date_str in self.holidays + self.weekdays:
            if date_str not in self.preferred_assignments:
                continue
            
            for role, doctors in self.preferred_assignments[date_str].items():
                if doctors:
                    # 選擇不可值班日最多的
                    doctors_sorted = sorted(
                        doctors,
                        key=lambda d: self.doctor_unavailable_count[d],
                        reverse=True
                    )
                    for doctor_name in doctors_sorted:
                        if self._assign_doctor(schedule, date_str, role, doctor_name, used_quota):
                            break
        
        # Step 2: 填充剩餘格子（假日優先）
        for date_str in self.holidays + self.weekdays:
            slot = schedule[date_str]
            
            # 填充主治
            if not slot.attending:
                # 按不可值班日數量排序
                attending_sorted = sorted(
                    self.attending_doctors,
                    key=lambda d: self.doctor_unavailable_count[d.name],
                    reverse=True
                )
                for doctor in attending_sorted:
                    if self._assign_doctor(schedule, date_str, "主治", doctor.name, used_quota):
                        break
            
            # 填充總醫師
            if not slot.resident:
                resident_sorted = sorted(
                    self.resident_doctors,
                    key=lambda d: self.doctor_unavailable_count[d.name],
                    reverse=True
                )
                for doctor in resident_sorted:
                    if self._assign_doctor(schedule, date_str, "總醫師", doctor.name, used_quota):
                        break
        
        return schedule
    
    def _is_complete(self, schedule: Dict) -> bool:
        """檢查排班是否完整（無空格）"""
        for date_str, slot in schedule.items():
            if not slot.attending or not slot.resident:
                return False
        return True
    
    def _greedy_initialization(self, beam_width: int) -> List[SchedulingState]:
        """產生初始解（使用相同策略但加入隨機性）"""
        initial_states = []
        
        for i in range(beam_width):
            # 創建空白排班
            schedule = {}
            for date_str in self.weekdays + self.holidays:
                schedule[date_str] = ScheduleSlot(date=date_str)
            
            used_quota = {}
            
            # Phase 1: 處理優先值班日
            self._handle_preferred_dates(schedule, used_quota, i)
            
            # Phase 2: 填充其他日期（假日優先，不可值班日多的人優先）
            self._fill_remaining_slots(schedule, used_quota, i)
            
            # 創建狀態
            state = self._create_state(schedule)
            initial_states.append(state)
        
        return initial_states
    
    def _handle_preferred_dates(self, schedule: Dict, used_quota: Dict, variant: int):
        """處理優先值班日"""
        for date_str in self.holidays + self.weekdays:
            if date_str not in self.preferred_assignments:
                continue
            
            for role, doctors in self.preferred_assignments[date_str].items():
                if not doctors:
                    continue
                
                # 如果多個醫師競爭，根據不可值班日數量排序
                if len(doctors) > 1:
                    # 加入一點隨機性
                    if variant > 0 and random.random() < 0.3:
                        doctors_sorted = doctors.copy()
                        random.shuffle(doctors_sorted)
                    else:
                        doctors_sorted = sorted(
                            doctors,
                            key=lambda d: self.doctor_unavailable_count[d],
                            reverse=True
                        )
                else:
                    doctors_sorted = doctors
                
                for doctor_name in doctors_sorted:
                    if self._assign_doctor(schedule, date_str, role, doctor_name, used_quota):
                        break
    
    def _fill_remaining_slots(self, schedule: Dict, used_quota: Dict, variant: int):
        """填充剩餘格子（假日優先，不可值班日多的人優先）"""
        # 假日優先
        for date_str in self.holidays + self.weekdays:
            slot = schedule[date_str]
            
            # 填充主治
            if not slot.attending:
                candidates = self._get_sorted_candidates(
                    date_str, "主治", schedule, used_quota, variant
                )
                for doctor_name in candidates:
                    if self._assign_doctor(schedule, date_str, "主治", doctor_name, used_quota):
                        break
            
            # 填充總醫師
            if not slot.resident:
                candidates = self._get_sorted_candidates(
                    date_str, "總醫師", schedule, used_quota, variant
                )
                for doctor_name in candidates:
                    if self._assign_doctor(schedule, date_str, "總醫師", doctor_name, used_quota):
                        break
    
    def _get_sorted_candidates(self, date_str: str, role: str, 
                              schedule: Dict, used_quota: Dict, variant: int) -> List[str]:
        """取得排序後的候選醫師（不可值班日多的優先）"""
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        candidates = []
        
        for doctor in doctors:
            can_assign, _ = self._can_assign(doctor.name, date_str, role, schedule, used_quota)
            if can_assign:
                candidates.append(doctor.name)
        
        # 根據不可值班日數量排序（多的優先）
        if variant == 0:
            # 第一個方案：嚴格按照不可值班日排序
            candidates.sort(key=lambda d: self.doctor_unavailable_count[d], reverse=True)
        else:
            # 其他方案：加入一些隨機性
            if random.random() < 0.3:
                random.shuffle(candidates)
            else:
                candidates.sort(key=lambda d: (
                    self.doctor_unavailable_count[d] + random.random() * 2
                ), reverse=True)
        
        return candidates
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int, progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        beam = []
        for state in initial_states:
            used_quota = self._calculate_used_quota(state.schedule)
            beam.append({
                'state': state,
                'used_quota': used_quota
            })
        
        # 收集未填格子（假日優先）
        unfilled = []
        for date_str in self.holidays + self.weekdays:
            slot = initial_states[0].schedule[date_str]
            
            if not slot.attending:
                unfilled.append((date_str, '主治'))
            if not slot.resident:
                unfilled.append((date_str, '總醫師'))
        
        max_steps = min(30, len(unfilled))
        self.diagnostic_info['beam_search_iterations'] = max_steps
        
        for step, (date_str, role) in enumerate(unfilled[:max_steps]):
            new_beam = []
            
            for item in beam:
                current_state = item['state']
                current_quota = copy.deepcopy(item['used_quota'])
                
                # 取得候選醫師（不可值班日多的優先）
                candidates = self._get_beam_candidates(
                    date_str, role, current_state.schedule, current_quota
                )
                
                if not candidates:
                    new_beam.append(item)
                else:
                    # 探索多個候選
                    for i, doctor_name in enumerate(candidates[:3]):
                        new_schedule = copy.deepcopy(current_state.schedule)
                        new_quota = copy.deepcopy(current_quota)
                        
                        if self._assign_doctor(new_schedule, date_str, role, doctor_name, new_quota):
                            new_state = self._create_state(new_schedule)
                            new_beam.append({
                                'state': new_state,
                                'used_quota': new_quota
                            })
            
            # 保留 Top-K
            if new_beam:
                new_beam.sort(key=lambda x: x['state'].score, reverse=True)
                beam = new_beam[:beam_width * 2]  # 保留更多候選以增加多樣性
            
            if progress_callback:
                progress_callback((step + 1) / max_steps)
        
        # 返回所有探索到的狀態
        return [item['state'] for item in beam]
    
    def _get_beam_candidates(self, date_str: str, role: str,
                            schedule: Dict, used_quota: Dict) -> List[str]:
        """取得 Beam Search 的候選醫師"""
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        candidates = []
        
        is_holiday = date_str in self.holidays
        
        for doctor in doctors:
            can_assign, _ = self._can_assign(doctor.name, date_str, role, schedule, used_quota)
            
            if can_assign:
                # 計算優先分數
                score = 0
                
                # 1. 不可值班日多的優先（主要策略）
                score += self.doctor_unavailable_count[doctor.name] * 100
                
                # 2. 優先值班日加分
                if date_str in self.doctor_preferred[doctor.name]:
                    score += 500
                
                # 3. 配額使用率（次要考慮）
                quota_type = 'holiday' if is_holiday else 'weekday'
                max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                used = used_quota.get(doctor.name, {}).get(quota_type, 0)
                usage_rate = used / max(max_quota, 1)
                score += (1 - usage_rate) * 10
                
                candidates.append((doctor.name, score))
        
        # 排序並返回
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]
    
    def _calculate_used_quota(self, schedule: Dict) -> Dict:
        """計算已使用配額"""
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
    
    def _create_state(self, schedule: Dict) -> SchedulingState:
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
        
        # 計算基於品質的分數
        score = self._calculate_quality_score(schedule, filled_count)
        
        return SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
    
    def _calculate_quality_score(self, schedule: Dict, filled_count: int) -> float:
        """計算基於品質的分數（你說這個OK）"""
        score = 0.0
        used_quota = self._calculate_used_quota(schedule)
        
        # 1. 填充率（最重要，權重1000）
        total_slots = len(schedule) * 2
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        score += fill_rate * 1000
        
        # 2. 優先值班日滿足度（權重500）
        pref_satisfied = 0
        pref_total = 0
        for doctor in self.doctors:
            for pref_date in self.doctor_preferred[doctor.name]:
                if pref_date in schedule:
                    pref_total += 1
                    slot = schedule[pref_date]
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        pref_satisfied += 1
        
        if pref_total > 0:
            score += (pref_satisfied / pref_total) * 500
        
        # 3. 假日覆蓋率（權重200）
        holiday_filled = 0
        for d in self.holidays:
            if d in schedule:
                if schedule[d].attending:
                    holiday_filled += 1
                if schedule[d].resident:
                    holiday_filled += 1
        holiday_coverage = holiday_filled / (len(self.holidays) * 2) if self.holidays else 0
        score += holiday_coverage * 200
        
        # 4. 配額使用均衡度（權重100）
        usage_variance = []
        for doctor in self.doctors:
            weekday_used = used_quota.get(doctor.name, {}).get('weekday', 0)
            holiday_used = used_quota.get(doctor.name, {}).get('holiday', 0)
            
            weekday_rate = weekday_used / max(doctor.weekday_quota, 1)
            holiday_rate = holiday_used / max(doctor.holiday_quota, 1)
            
            usage_variance.append((weekday_rate + holiday_rate) / 2)
        
        if usage_variance:
            balance = 1 - np.std(usage_variance)
            score += balance * 100
        
        # 5. 連續值班懲罰
        consecutive_penalty = 0
        for doctor in self.doctors:
            max_consecutive = self._check_max_consecutive(doctor.name, schedule)
            if max_consecutive > self.constraints.max_consecutive_days:
                consecutive_penalty += (max_consecutive - self.constraints.max_consecutive_days) * 50
        score -= consecutive_penalty
        
        return score
    
    def _check_max_consecutive(self, doctor_name: str, schedule: Dict) -> int:
        """檢查最大連續值班天數"""
        max_consecutive = 0
        current_consecutive = 0
        
        for date_str in sorted(schedule.keys()):
            slot = schedule[date_str]
            if doctor_name == slot.attending or doctor_name == slot.resident:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive