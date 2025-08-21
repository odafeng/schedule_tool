"""
Stage 1: Greedy + Beam Search 快速排班
修正版：統一處理日期格式問題
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
from datetime import datetime
from backend.models import Doctor, ScheduleSlot, ScheduleConstraints, SchedulingState
from backend.utils import check_consecutive_days

class Stage1Scheduler:
    """Stage 1: Greedy + Beam Search 排班器 - 日期格式統一版"""
    
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
        
        # 建立所有日期的集合（用於快速查詢）
        self.all_dates_set = set(weekdays + holidays)
        
        # 診斷：顯示日期格式
        st.write("### 📅 日期格式檢查")
        if weekdays:
            st.write(f"平日格式範例: `{weekdays[0]}`")
        if holidays:
            st.write(f"假日格式範例: `{holidays[0]}`")
        if doctors and doctors[0].unavailable_dates:
            st.write(f"醫師不可值班日格式範例: `{doctors[0].unavailable_dates[0]}`")
        if doctors and doctors[0].preferred_dates:
            st.write(f"醫師優先值班日格式範例: `{doctors[0].preferred_dates[0]}`")
        
        # 建立日期格式轉換映射
        self.date_format_map = self._build_date_format_map()
        
        # 建立醫師約束映射（使用統一格式）
        self.doctor_unavailable = {}
        self.doctor_preferred = {}
        
        for doctor in self.doctors:
            # 轉換不可值班日到統一格式
            unavailable_normalized = set()
            for date in doctor.unavailable_dates:
                normalized = self._normalize_date(date)
                if normalized:
                    unavailable_normalized.add(normalized)
            self.doctor_unavailable[doctor.name] = unavailable_normalized
            
            # 轉換優先值班日到統一格式
            preferred_normalized = set()
            for date in doctor.preferred_dates:
                normalized = self._normalize_date(date)
                if normalized:
                    preferred_normalized.add(normalized)
            self.doctor_preferred[doctor.name] = preferred_normalized
        
        # 建立優先值班日的反向映射（使用統一格式）
        self.preferred_assignments = self._build_preferred_assignments()
        
        # 檢查約束衝突
        self.constraint_issues = self._validate_constraints()
        
        # 診斷資訊
        self.diagnostic_info = {
            'constraint_violations': [],
            'hard_constraint_checks': [],
            'assignment_attempts': [],
            'final_violations': []
        }
    
    def _build_date_format_map(self) -> Dict[str, str]:
        """建立日期格式映射表，將各種格式映射到統一格式"""
        format_map = {}
        
        # 將所有排班日期作為標準格式
        for date in self.weekdays + self.holidays:
            format_map[date] = date  # 自己映射到自己
            
            # 嘗試解析並建立其他格式的映射
            try:
                # 如果是 "08/01" 格式，也建立 "2025-08-01" 的映射
                if "/" in date and len(date.split("/")[0]) == 2:
                    month, day = date.split("/")
                    year = 2025  # 假設年份
                    long_format = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    format_map[long_format] = date
                
                # 如果是 "2025-08-01" 格式，也建立 "08/01" 的映射
                elif "-" in date and len(date.split("-")) == 3:
                    year, month, day = date.split("-")
                    short_format = f"{month}/{day}"
                    format_map[short_format] = date
            except:
                pass
        
        return format_map
    
    def _normalize_date(self, date: str) -> Optional[str]:
        """將日期轉換為統一格式（使用 weekdays/holidays 的格式）"""
        if date in self.all_dates_set:
            return date
        
        if date in self.date_format_map:
            return self.date_format_map[date]
        
        # 嘗試手動轉換
        try:
            # 嘗試解析 "2025-08-01" 格式
            if "-" in date and len(date.split("-")) == 3:
                year, month, day = date.split("-")
                # 嘗試兩種短格式
                short_format1 = f"{month}/{day}"
                short_format2 = f"{int(month)}/{int(day)}"
                
                if short_format1 in self.all_dates_set:
                    return short_format1
                if short_format2 in self.all_dates_set:
                    return short_format2
            
            # 嘗試解析 "08/01" 格式
            elif "/" in date:
                month, day = date.split("/")
                # 嘗試補零
                formatted = f"{month.zfill(2)}/{day.zfill(2)}"
                if formatted in self.all_dates_set:
                    return formatted
                # 嘗試不補零
                formatted2 = f"{int(month)}/{int(day)}"
                if formatted2 in self.all_dates_set:
                    return formatted2
        except:
            pass
        
        # 如果都失敗，返回 None
        st.warning(f"無法轉換日期格式: {date}")
        return None
    
    def _build_preferred_assignments(self) -> Dict[str, Dict[str, List[str]]]:
        """建立優先值班日映射（使用統一格式）"""
        assignments = defaultdict(lambda: {'主治': [], '總醫師': []})
        
        for doctor in self.doctors:
            for date in self.doctor_preferred[doctor.name]:
                if date:  # 確保日期有效
                    assignments[date][doctor.role].append(doctor.name)
        
        return dict(assignments)
    
    def _validate_constraints(self) -> List[str]:
        """驗證約束可行性"""
        issues = []
        
        # 檢查每個日期是否有可用醫師
        for date_str in self.weekdays + self.holidays:
            is_holiday = date_str in self.holidays
            
            # 檢查主治醫師
            available_attending = []
            for doctor in self.attending_doctors:
                if date_str not in self.doctor_unavailable[doctor.name]:
                    max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                    if max_quota > 0:
                        available_attending.append(doctor.name)
            
            if not available_attending:
                issues.append(f"{date_str} 沒有可用的主治醫師")
            
            # 檢查總醫師
            available_resident = []
            for doctor in self.resident_doctors:
                if date_str not in self.doctor_unavailable[doctor.name]:
                    max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                    if max_quota > 0:
                        available_resident.append(doctor.name)
            
            if not available_resident:
                issues.append(f"{date_str} 沒有可用的總醫師")
        
        return issues
    
    def _can_assign(self, doctor_name: str, date_str: str, role: str,
                   schedule: Dict, used_quota: Dict) -> Tuple[bool, str]:
        """檢查是否可以分配醫師到特定日期和角色"""
        doctor = self.doctor_map[doctor_name]
        
        # === 硬約束1：同一日同一角色只能一人 ===
        if date_str not in schedule:
            return False, f"日期 {date_str} 不在排班表中"
        
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
        
        # === 硬約束3：不可值班日（最重要！使用統一格式）===
        if date_str in self.doctor_unavailable[doctor_name]:
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
        """執行分配（先檢查再分配）"""
        # 最終檢查
        can_assign, reason = self._can_assign(
            doctor_name, date_str, role, schedule, used_quota
        )
        
        if not can_assign:
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
        
        return True
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """執行排班"""
        
        # 如果有約束問題，顯示警告
        if self.constraint_issues:
            st.warning(f"發現約束問題：{'; '.join(self.constraint_issues[:3])}")
        
        # Stage 1: 初始化
        initial_states = self._greedy_initialization()
        
        # Stage 2: Beam Search 優化
        final_states = self._beam_search_optimization(
            initial_states, beam_width, progress_callback
        )
        
        # 最終驗證
        st.write("### ✅ 硬約束檢查結果")
        all_valid = True
        for idx, state in enumerate(final_states):
            violations = self._validate_schedule(state.schedule)
            if violations:
                st.error(f"方案 {idx+1} 違反 {len(violations)} 個硬約束")
                for v in violations[:3]:
                    st.write(f"  - {v}")
                all_valid = False
        
        if all_valid:
            st.success("所有方案都通過硬約束檢查！")
        
        return final_states
    
    def _greedy_initialization(self) -> List[SchedulingState]:
        """初始化多個不同的排班方案"""
        states = []
        strategies = [
            {'name': '假日優先', 'fill_ratio': 0.7},
            {'name': '平日優先', 'fill_ratio': 0.65},
            {'name': '隨機順序', 'fill_ratio': 0.6},
            {'name': '最小填充', 'fill_ratio': 0.5},
            {'name': '交替填充', 'fill_ratio': 0.75}
        ]
        
        for variant, strategy in enumerate(strategies):
            schedule = {}
            for date_str in self.weekdays + self.holidays:
                schedule[date_str] = ScheduleSlot(date=date_str)
            
            used_quota = {}
            
            # Phase 1: 處理優先值班日
            self._handle_preferred_dates(schedule, used_quota)
            
            # Phase 2: 根據策略填充
            if strategy['name'] == '假日優先':
                self._fill_holiday_first(schedule, used_quota, strategy['fill_ratio'])
            elif strategy['name'] == '平日優先':
                self._fill_weekday_first(schedule, used_quota, strategy['fill_ratio'])
            elif strategy['name'] == '隨機順序':
                self._fill_random(schedule, used_quota, strategy['fill_ratio'], variant)
            elif strategy['name'] == '最小填充':
                self._fill_minimal(schedule, used_quota, strategy['fill_ratio'])
            else:
                self._fill_alternating(schedule, used_quota, strategy['fill_ratio'])
            
            state = self._create_state(schedule, used_quota, variant)
            states.append(state)
        
        return states
    
    def _handle_preferred_dates(self, schedule: Dict, used_quota: Dict):
        """處理優先值班日（硬約束4）"""
        for date_str in self.weekdays + self.holidays:
            if date_str not in self.preferred_assignments:
                continue
            
            roles_data = self.preferred_assignments[date_str]
            for role, doctors in roles_data.items():
                if not doctors:
                    continue
                
                # 嘗試分配給優先的醫師
                for doctor_name in doctors:
                    can_assign, reason = self._can_assign(
                        doctor_name, date_str, role, schedule, used_quota
                    )
                    if can_assign:
                        self._assign(schedule, date_str, role, doctor_name, used_quota)
                        break
    
    def _fill_holiday_first(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """假日優先填充策略"""
        slots = []
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        for date_str in self.weekdays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_weekday_first(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """平日優先填充策略"""
        slots = []
        for date_str in self.weekdays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_random(self, schedule: Dict, used_quota: Dict, fill_ratio: float, seed: int):
        """隨機順序填充"""
        random.seed(seed * 42)
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
    
    def _fill_minimal(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """最小填充策略"""
        slots = []
        for date_str in self.holidays:
            slot = schedule[date_str]
            if not slot.attending:
                slots.append((date_str, '主治'))
            if not slot.resident:
                slots.append((date_str, '總醫師'))
        
        max_fill = int(len(slots) * fill_ratio)
        self._fill_slots(schedule, used_quota, slots[:max_fill])
    
    def _fill_alternating(self, schedule: Dict, used_quota: Dict, fill_ratio: float):
        """交替填充策略"""
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
            # 跳過已填充的格子
            slot = schedule[date_str]
            if (role == "主治" and slot.attending) or (role == "總醫師" and slot.resident):
                continue
            
            # 取得候選醫師
            doctors = self.attending_doctors if role == "主治" else self.resident_doctors
            
            # 按優先級排序醫師
            candidates = []
            for doctor in doctors:
                can_assign, _ = self._can_assign(
                    doctor.name, date_str, role, schedule, used_quota
                )
                if can_assign:
                    # 計算優先分數
                    score = 0
                    if date_str in self.doctor_preferred[doctor.name]:
                        score += 100  # 自己的優先值班日
                    is_holiday = date_str in self.holidays
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
                    used = used_quota.get(doctor.name, {}).get(quota_type, 0)
                    score += (max_quota - used) * 10  # 剩餘配額越多越好
                    candidates.append((doctor.name, score))
            
            # 選擇最佳候選人
            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                self._assign(schedule, date_str, role, candidates[0][0], used_quota)
    
    def _beam_search_optimization(self, initial_states: List[SchedulingState],
                                  beam_width: int, progress_callback: Callable) -> List[SchedulingState]:
        """Beam Search 優化"""
        beam = []
        for state in initial_states:
            beam.append({
                'state': state,
                'used_quota': self._recalculate_quota(state.schedule)
            })
        
        # 收集未填格子
        unfilled = []
        for date_str in self.holidays + self.weekdays:
            slot = initial_states[0].schedule[date_str]
            
            if not slot.attending and date_str not in self.preferred_assignments:
                unfilled.append((date_str, '主治'))
            elif not slot.attending and '主治' not in self.preferred_assignments.get(date_str, {}):
                unfilled.append((date_str, '主治'))
            
            if not slot.resident and date_str not in self.preferred_assignments:
                unfilled.append((date_str, '總醫師'))
            elif not slot.resident and '總醫師' not in self.preferred_assignments.get(date_str, {}):
                unfilled.append((date_str, '總醫師'))
        
        max_steps = min(20, len(unfilled))
        
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
                    new_beam.append(item)
                else:
                    for doctor_name in candidates[:2]:  # 只試前2個
                        new_schedule = copy.deepcopy(current_state.schedule)
                        new_quota = copy.deepcopy(current_quota)
                        
                        if self._assign(new_schedule, date_str, role, doctor_name, new_quota):
                            new_state = self._create_state(new_schedule, new_quota, len(new_beam))
                            new_beam.append({
                                'state': new_state,
                                'used_quota': new_quota
                            })
            
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
        
        # 計算分數
        total_slots = len(schedule) * 2
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        score = fill_rate * 1000
        
        # 假日覆蓋
        holiday_filled = sum(1 for d in self.holidays 
                           if schedule[d].attending or schedule[d].resident)
        score += holiday_filled * 50
        
        # 優先值班滿足度
        pref_satisfied = 0
        for doctor in self.doctors:
            for pref_date in self.doctor_preferred[doctor.name]:
                if pref_date in schedule:
                    slot = schedule[pref_date]
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        pref_satisfied += 1
        score += pref_satisfied * 100
        
        # 確保每個方案分數不同
        score += variant_id * 15  # 每個變體差15分
        score += (hash(str(schedule)) % 100) * 0.01  # 基於內容的微小差異
        
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
                # 檢查不可值班日
                if date_str in self.doctor_unavailable[slot.attending]:
                    violations.append(f"{date_str}: {slot.attending} 在不可值班日被排班")
                
                # 檢查優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('主治', [])
                    if preferred and slot.attending not in preferred:
                        violations.append(f"{date_str}: 主治應為 {preferred}，實際為 {slot.attending}")
            
            # 檢查總醫師
            if slot.resident:
                # 檢查不可值班日
                if date_str in self.doctor_unavailable[slot.resident]:
                    violations.append(f"{date_str}: {slot.resident} 在不可值班日被排班")
                
                # 檢查優先值班日
                if date_str in self.preferred_assignments:
                    preferred = self.preferred_assignments[date_str].get('總醫師', [])
                    if preferred and slot.resident not in preferred:
                        violations.append(f"{date_str}: 總醫師應為 {preferred}，實際為 {slot.resident}")
        
        # 檢查配額
        for doctor_name, quotas in used_quota.items():
            doctor = self.doctor_map[doctor_name]
            if quotas.get('weekday', 0) > doctor.weekday_quota:
                violations.append(f"{doctor_name} 平日配額超過 ({quotas['weekday']}/{doctor.weekday_quota})")
            if quotas.get('holiday', 0) > doctor.holiday_quota:
                violations.append(f"{doctor_name} 假日配額超過 ({quotas['holiday']}/{doctor.holiday_quota})")
        
        return violations