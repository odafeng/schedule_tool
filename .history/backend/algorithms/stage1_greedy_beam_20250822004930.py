"""
Stage 1: Greedy + Beam Search 快速排班
簡化版：確保硬約束絕對不被違反，產生5個不同方案
增加日期格式調試功能
"""
import copy
import random
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable, Set
from collections import defaultdict
import numpy as np
from backend.models import Doctor, ScheduleSlot, ScheduleConstraints, SchedulingState

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
        
        # 計算醫師的不可值班日數量（用於排序）
        self.doctor_unavailable_count = {}
        for doctor in self.doctors:
            self.doctor_unavailable_count[doctor.name] = len(doctor.unavailable_dates)
        
        # ========== 日期格式調試區域 ==========
        self._debug_date_formats()
    
    def _debug_date_formats(self):
        """調試日期格式，顯示實際收到的格式"""
        st.write("### 🔍 日期格式調試")
        
        # 顯示 weekdays 格式
        with st.expander("📅 平日日期格式", expanded=False):
            st.write(f"**平日數量**: {len(self.weekdays)}")
            if self.weekdays:
                st.write("**前5個平日**:")
                for date_str in self.weekdays[:5]:
                    st.code(f"'{date_str}' (類型: {type(date_str).__name__})")
        
        # 顯示 holidays 格式
        with st.expander("🎉 假日日期格式", expanded=False):
            st.write(f"**假日數量**: {len(self.holidays)}")
            if self.holidays:
                st.write("**所有假日**:")
                for date_str in self.holidays:
                    st.code(f"'{date_str}' (類型: {type(date_str).__name__})")
        
        # 顯示醫師的約束日期格式
        with st.expander("👨‍⚕️ 醫師約束日期格式", expanded=False):
            for doctor in self.doctors[:3]:  # 只顯示前3個醫師
                st.write(f"**{doctor.name} ({doctor.role})**")
                
                # 不可值班日
                if doctor.unavailable_dates:
                    st.write("  不可值班日:")
                    for date_str in doctor.unavailable_dates[:3]:
                        st.code(f"    '{date_str}' (類型: {type(date_str).__name__})")
                
                # 優先值班日
                if doctor.preferred_dates:
                    st.write("  優先值班日:")
                    for date_str in doctor.preferred_dates[:3]:
                        st.code(f"    '{date_str}' (類型: {type(date_str).__name__})")
        
        # 檢查格式一致性
        self._check_format_consistency()
    
    def _check_format_consistency(self):
        """檢查日期格式一致性"""
        format_issues = []
        
        # 檢查所有排班日期
        all_schedule_dates = self.weekdays + self.holidays
        for date_str in all_schedule_dates:
            if not self._is_yyyy_mm_dd_format(date_str):
                format_issues.append(f"排班日期格式異常: '{date_str}'")
        
        # 檢查醫師約束日期
        for doctor in self.doctors:
            for date_str in doctor.unavailable_dates:
                if not self._is_yyyy_mm_dd_format(date_str):
                    format_issues.append(f"{doctor.name} 不可值班日格式異常: '{date_str}'")
            
            for date_str in doctor.preferred_dates:
                if not self._is_yyyy_mm_dd_format(date_str):
                    format_issues.append(f"{doctor.name} 優先值班日格式異常: '{date_str}'")
        
        # 顯示格式問題
        if format_issues:
            st.error("⚠️ 發現日期格式問題：")
            for issue in format_issues[:10]:  # 最多顯示10個
                st.write(f"  - {issue}")
        else:
            st.success("✅ 所有日期格式一致 (YYYY-MM-DD)")
        
        # 顯示診斷策略
        st.info("""
        **診斷結果與策略**:
        - 排班日期格式：統一使用 YYYY-MM-DD
        - 醫師約束格式：統一使用 YYYY-MM-DD
        - 比對方式：直接字串比對
        """)
    
    def _is_yyyy_mm_dd_format(self, date_str: str) -> bool:
        """檢查是否為 YYYY-MM-DD 格式"""
        if not isinstance(date_str, str):
            return False
        
        parts = date_str.split("-")
        if len(parts) != 3:
            return False
        
        try:
            year, month, day = parts
            if len(year) == 4 and len(month) == 2 and len(day) == 2:
                int(year)
                int(month)
                int(day)
                return True
        except:
            pass
        
        return False
    
    def _is_unavailable(self, doctor_name: str, date_str: str) -> bool:
        """檢查醫師在某日是否不可值班（簡化版：直接比對）"""
        doctor = self.doctor_map[doctor_name]
        
        # 直接檢查是否在不可值班日列表中
        is_unavailable = date_str in doctor.unavailable_dates
        
        # 調試輸出（只在前幾次檢查時輸出）
        if hasattr(self, '_debug_count'):
            self._debug_count += 1
        else:
            self._debug_count = 1
        
        if self._debug_count <= 5 and is_unavailable:
            st.write(f"🔍 DEBUG: {doctor_name} 在 {date_str} 不可值班")
        
        return is_unavailable
    
    def _is_preferred(self, doctor_name: str, date_str: str) -> bool:
        """檢查某日是否是醫師的優先值班日（簡化版：直接比對）"""
        doctor = self.doctor_map[doctor_name]
        return date_str in doctor.preferred_dates
    
    def _get_preferred_doctors(self, date_str: str, role: str) -> List[str]:
        """取得某日某角色的優先值班醫師"""
        preferred = []
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        
        for doctor in doctors:
            if self._is_preferred(doctor.name, date_str):
                preferred.append(doctor.name)
        
        return preferred
    
    def _check_consecutive_days(self, doctor_name: str, date_str: str, schedule: Dict) -> int:
        """檢查連續值班天數"""
        sorted_dates = sorted(schedule.keys())
        if date_str not in sorted_dates:
            return 1
        
        date_idx = sorted_dates.index(date_str)
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
    
    def _can_assign_strict(self, doctor_name: str, date_str: str, role: str,
                          schedule: Dict, used_quota: Dict) -> Tuple[bool, str]:
        """
        嚴格檢查是否可以分配（所有硬約束）
        返回 (是否可分配, 原因說明)
        """
        doctor = self.doctor_map[doctor_name]
        slot = schedule[date_str]
        
        # 硬約束1：同一日同一角色只能一人
        if role == "主治" and slot.attending is not None:
            return False, "該日主治已有人"
        if role == "總醫師" and slot.resident is not None:
            return False, "該日總醫師已有人"
        
        # 硬約束2：配額限制
        is_holiday = date_str in self.holidays
        quota_type = 'holiday' if is_holiday else 'weekday'
        max_quota = doctor.holiday_quota if is_holiday else doctor.weekday_quota
        current_used = used_quota.get(doctor_name, {}).get(quota_type, 0)
        if current_used >= max_quota:
            return False, f"配額已滿 ({current_used}/{max_quota})"
        
        # 硬約束3：不可值班日（最重要！）
        if self._is_unavailable(doctor_name, date_str):
            return False, "不可值班日"
        
        # 硬約束4：優先值班日限制（如果有人優先，其他人不能排）
        preferred_doctors = self._get_preferred_doctors(date_str, role)
        if preferred_doctors and doctor_name not in preferred_doctors:
            return False, f"該日有優先值班者: {', '.join(preferred_doctors)}"
        
        # 硬約束5：連續值班限制
        consecutive = self._check_consecutive_days(doctor_name, date_str, schedule)
        if consecutive > self.constraints.max_consecutive_days:
            return False, f"超過連續值班限制 ({consecutive}/{self.constraints.max_consecutive_days})"
        
        # 硬約束6：同日不能擔任兩角色
        if doctor_name == slot.attending or doctor_name == slot.resident:
            return False, "同日已擔任其他角色"
        
        return True, "OK"
    
    def run(self, beam_width: int = 5, progress_callback: Callable = None) -> List[SchedulingState]:
        """執行排班"""
        
        # 在執行前顯示統計
        st.write("### 📊 排班策略")
        st.write("- 不可值班日最多的醫師優先排班")
        st.write("- 假日優先填充")
        st.write("- 嚴格遵守所有硬約束")
        
        # 使用 Beam Search 產生多個方案
        all_solutions = []
        
        # 產生多個初始解
        for attempt in range(beam_width * 3):  # 多嘗試幾次
            solution = self._generate_solution(attempt)
            
            # 檢查是否是新的解
            is_unique = True
            for existing in all_solutions:
                if self._is_same_solution(solution, existing['schedule']):
                    is_unique = False
                    break
            
            if is_unique:
                score = self._calculate_score(solution)
                all_solutions.append({
                    'schedule': solution,
                    'score': score
                })
        
        # 排序並取前5個
        all_solutions.sort(key=lambda x: x['score'], reverse=True)
        top_5_solutions = all_solutions[:5]
        
        # 轉換為 SchedulingState
        result = []
        for idx, sol in enumerate(top_5_solutions):
            state = self._create_state(sol['schedule'])
            result.append(state)
            
            # 驗證硬約束
            violations = self._validate_hard_constraints(sol['schedule'])
            if violations:
                st.error(f"方案 {idx+1} 違反硬約束：")
                for v in violations[:3]:
                    st.write(f"  - {v}")
            else:
                st.success(f"方案 {idx+1}: 分數 {state.score:.2f}, 填充率 {state.fill_rate:.1%}")
        
        if len(result) < 5:
            st.warning(f"只產生了 {len(result)} 個不同的方案")
        
        return result
    
    def _generate_solution(self, seed: int) -> Dict:
        """產生一個解（使用固定策略但加入變化）"""
        random.seed(seed * 42)
        
        # 初始化空白排班
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        # 調試計數器
        debug_assignments = []
        
        # Step 1: 處理優先值班日
        for date_str in self.holidays + self.weekdays:  # 假日優先
            # 主治醫師
            preferred_attending = self._get_preferred_doctors(date_str, "主治")
            if preferred_attending:
                # 從優先的醫師中選擇（不可值班日多的優先）
                preferred_attending.sort(key=lambda d: self.doctor_unavailable_count[d], reverse=True)
                for doctor_name in preferred_attending:
                    can_assign, reason = self._can_assign_strict(doctor_name, date_str, "主治", schedule, used_quota)
                    if can_assign:
                        schedule[date_str].attending = doctor_name
                        is_holiday = date_str in self.holidays
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor_name][quota_type] += 1
                        debug_assignments.append(f"{date_str} 主治: {doctor_name} (優先)")
                        break
            
            # 總醫師
            preferred_resident = self._get_preferred_doctors(date_str, "總醫師")
            if preferred_resident:
                preferred_resident.sort(key=lambda d: self.doctor_unavailable_count[d], reverse=True)
                for doctor_name in preferred_resident:
                    can_assign, reason = self._can_assign_strict(doctor_name, date_str, "總醫師", schedule, used_quota)
                    if can_assign:
                        schedule[date_str].resident = doctor_name
                        is_holiday = date_str in self.holidays
                        quota_type = 'holiday' if is_holiday else 'weekday'
                        used_quota[doctor_name][quota_type] += 1
                        debug_assignments.append(f"{date_str} 總醫師: {doctor_name} (優先)")
                        break
        
        # Step 2: 填充其他日期（假日優先，不可值班日多的人優先）
        for date_str in self.holidays + self.weekdays:
            # 填充主治
            if not schedule[date_str].attending:
                # 取得候選人並排序
                candidates = []
                for doctor in self.attending_doctors:
                    can_assign, reason = self._can_assign_strict(doctor.name, date_str, "主治", schedule, used_quota)
                    if can_assign:
                        candidates.append(doctor.name)
                
                # 排序（不可值班日多的優先，加入一點隨機性）
                if candidates:
                    if seed == 0:
                        # 第一個方案：嚴格按照策略
                        candidates.sort(key=lambda d: self.doctor_unavailable_count[d], reverse=True)
                    else:
                        # 其他方案：加入隨機性
                        if random.random() < 0.3:
                            random.shuffle(candidates)
                        else:
                            candidates.sort(key=lambda d: (
                                self.doctor_unavailable_count[d] + random.random() * 3
                            ), reverse=True)
                    
                    # 分配第一個候選人
                    doctor_name = candidates[0]
                    schedule[date_str].attending = doctor_name
                    is_holiday = date_str in self.holidays
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[doctor_name][quota_type] += 1
                    debug_assignments.append(f"{date_str} 主治: {doctor_name}")
            
            # 填充總醫師
            if not schedule[date_str].resident:
                candidates = []
                for doctor in self.resident_doctors:
                    can_assign, reason = self._can_assign_strict(doctor.name, date_str, "總醫師", schedule, used_quota)
                    if can_assign:
                        candidates.append(doctor.name)
                
                if candidates:
                    if seed == 0:
                        candidates.sort(key=lambda d: self.doctor_unavailable_count[d], reverse=True)
                    else:
                        if random.random() < 0.3:
                            random.shuffle(candidates)
                        else:
                            candidates.sort(key=lambda d: (
                                self.doctor_unavailable_count[d] + random.random() * 3
                            ), reverse=True)
                    
                    doctor_name = candidates[0]
                    schedule[date_str].resident = doctor_name
                    is_holiday = date_str in self.holidays
                    quota_type = 'holiday' if is_holiday else 'weekday'
                    used_quota[doctor_name][quota_type] += 1
                    debug_assignments.append(f"{date_str} 總醫師: {doctor_name}")
        
        # 顯示前幾個分配（調試用）
        if seed == 0 and debug_assignments:
            with st.expander("🔍 分配過程（前10個）", expanded=False):
                for assignment in debug_assignments[:10]:
                    st.write(f"  - {assignment}")
        
        return schedule
    
    def _is_same_solution(self, schedule1: Dict, schedule2: Dict) -> bool:
        """檢查兩個解是否相同"""
        for date_str in schedule1.keys():
            slot1 = schedule1[date_str]
            slot2 = schedule2[date_str]
            if slot1.attending != slot2.attending or slot1.resident != slot2.resident:
                return False
        return True
    
    def _calculate_score(self, schedule: Dict) -> float:
        """計算分數"""
        score = 0.0
        filled_count = 0
        total_slots = len(schedule) * 2
        
        # 統計填充數
        for date_str, slot in schedule.items():
            if slot.attending:
                filled_count += 1
            if slot.resident:
                filled_count += 1
        
        # 1. 填充率（最重要）
        fill_rate = filled_count / total_slots if total_slots > 0 else 0
        score += fill_rate * 1000
        
        # 2. 假日覆蓋
        holiday_filled = 0
        for date_str in self.holidays:
            if schedule[date_str].attending:
                holiday_filled += 1
            if schedule[date_str].resident:
                holiday_filled += 1
        
        if self.holidays:
            holiday_rate = holiday_filled / (len(self.holidays) * 2)
            score += holiday_rate * 200
        
        # 3. 優先值班日滿足
        pref_satisfied = 0
        for doctor in self.doctors:
            for date_str in self.weekdays + self.holidays:
                if self._is_preferred(doctor.name, date_str):
                    slot = schedule[date_str]
                    if (doctor.role == "主治" and slot.attending == doctor.name) or \
                       (doctor.role == "總醫師" and slot.resident == doctor.name):
                        pref_satisfied += 1
        
        score += pref_satisfied * 50
        
        return score
    
    def _create_state(self, schedule: Dict) -> SchedulingState:
        """創建狀態"""
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
        
        score = self._calculate_score(schedule)
        
        return SchedulingState(
            schedule=schedule,
            score=score,
            filled_count=filled_count,
            unfilled_slots=unfilled_slots
        )
    
    def _validate_hard_constraints(self, schedule: Dict) -> List[str]:
        """驗證硬約束"""
        violations = []
        
        # 重新計算配額
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            quota_type = 'holiday' if is_holiday else 'weekday'
            
            # 檢查主治
            if slot.attending:
                # 不可值班日
                if self._is_unavailable(slot.attending, date_str):
                    violations.append(f"{date_str}: {slot.attending} 在不可值班日被排班")
                
                # 優先值班日
                preferred = self._get_preferred_doctors(date_str, "主治")
                if preferred and slot.attending not in preferred:
                    violations.append(f"{date_str}: 主治應為 {preferred} 之一")
                
                # 更新配額
                used_quota[slot.attending][quota_type] += 1
            
            # 檢查總醫師
            if slot.resident:
                # 不可值班日
                if self._is_unavailable(slot.resident, date_str):
                    violations.append(f"{date_str}: {slot.resident} 在不可值班日被排班")
                
                # 優先值班日
                preferred = self._get_preferred_doctors(date_str, "總醫師")
                if preferred and slot.resident not in preferred:
                    violations.append(f"{date_str}: 總醫師應為 {preferred} 之一")
                
                # 更新配額
                used_quota[slot.resident][quota_type] += 1
        
        # 檢查配額
        for doctor_name, quotas in used_quota.items():
            doctor = self.doctor_map[doctor_name]
            if quotas['weekday'] > doctor.weekday_quota:
                violations.append(f"{doctor_name} 平日配額超過 ({quotas['weekday']}/{doctor.weekday_quota})")
            if quotas['holiday'] > doctor.holiday_quota:
                violations.append(f"{doctor_name} 假日配額超過 ({quotas['holiday']}/{doctor.holiday_quota})")
        
        return violations