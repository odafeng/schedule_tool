"""
Stage 1: Greedy + Beam Search 快速排班
簡化版：確保硬約束絕對不被違反，產生5個不同方案
增加日期格式調試功能（改進版）
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
        
        # 儲存調試資訊
        self._collect_debug_info()
    
    def _collect_debug_info(self):
        """收集調試資訊（不立即顯示）"""
        self.debug_info = {
            'weekdays_sample': self.weekdays[:3] if self.weekdays else [],
            'holidays_all': self.holidays,
            'doctor_constraints': {},
            'format_issues': []
        }
        
        # 收集醫師約束樣本
        for doctor in self.doctors[:2]:  # 只取前2個醫師作為樣本
            self.debug_info['doctor_constraints'][doctor.name] = {
                'role': doctor.role,
                'unavailable': doctor.unavailable_dates[:3] if doctor.unavailable_dates else [],
                'preferred': doctor.preferred_dates[:3] if doctor.preferred_dates else []
            }
        
        # 檢查格式一致性
        all_schedule_dates = self.weekdays + self.holidays
        for date_str in all_schedule_dates:
            if not self._is_yyyy_mm_dd_format(date_str):
                self.debug_info['format_issues'].append(f"排班日期: {date_str}")
        
        for doctor in self.doctors:
            for date_str in doctor.unavailable_dates:
                if not self._is_yyyy_mm_dd_format(date_str):
                    self.debug_info['format_issues'].append(f"{doctor.name} 不可值班: {date_str}")
            for date_str in doctor.preferred_dates:
                if not self._is_yyyy_mm_dd_format(date_str):
                    self.debug_info['format_issues'].append(f"{doctor.name} 優先值班: {date_str}")
    
    def display_debug_info(self):
        """顯示調試資訊（在適當的時機呼叫）"""
        st.write("### 🔍 日期格式調試報告")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📅 排班日期範例**")
            st.write(f"平日範例: {self.debug_info['weekdays_sample']}")
            st.write(f"假日: {self.debug_info['holidays_all']}")
        
        with col2:
            st.write("**👨‍⚕️ 醫師約束範例**")
            for name, info in self.debug_info['doctor_constraints'].items():
                st.write(f"{name} ({info['role']}):")
                st.write(f"  不可: {info['unavailable']}")
                st.write(f"  優先: {info['preferred']}")
        
        # 顯示格式問題
        if self.debug_info['format_issues']:
            st.error(f"⚠️ 發現 {len(self.debug_info['format_issues'])} 個格式問題")
            with st.expander("查看詳細格式問題"):
                for issue in self.debug_info['format_issues'][:10]:
                    st.write(f"- {issue}")
        else:
            st.success("✅ 所有日期格式一致 (YYYY-MM-DD)")
        
        # 測試約束檢查
        self._test_constraint_checking()
    
    def _test_constraint_checking(self):
        """測試約束檢查是否正常工作"""
        st.write("**🧪 約束檢查測試**")
        
        # 找一個有不可值班日的醫師
        test_doctor = None
        test_date = None
        
        for doctor in self.doctors:
            if doctor.unavailable_dates:
                test_doctor = doctor.name
                test_date = doctor.unavailable_dates[0]
                break
        
        if test_doctor and test_date:
            # 測試不可值班日檢查
            is_unavail = self._is_unavailable(test_doctor, test_date)
            st.write(f"測試: {test_doctor} 在 {test_date} 不可值班？")
            st.write(f"結果: {'✅ 是' if is_unavail else '❌ 否'}")
            
            # 顯示詳細比對過程
            with st.expander("查看詳細比對過程"):
                doctor = self.doctor_map[test_doctor]
                st.write(f"醫師不可值班日列表: {doctor.unavailable_dates}")
                st.write(f"測試日期: '{test_date}'")
                st.write(f"直接比對結果: {test_date in doctor.unavailable_dates}")
                
                # 檢查每個不可值班日
                for unavail_date in doctor.unavailable_dates[:5]:
                    match = (unavail_date == test_date)
                    st.write(f"  '{unavail_date}' == '{test_date}' ? {match}")
    
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
        
        # 記錄違反的約束（用於後續報告）
        if is_unavailable and not hasattr(self, '_constraint_violations'):
            self._constraint_violations = []
        if is_unavailable:
            if not hasattr(self, '_constraint_violations'):
                self._constraint_violations = []
            self._constraint_violations.append(f"{doctor_name} 在 {date_str} 不可值班")
        
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
        
        # 清除之前的約束違反記錄
        self._constraint_violations = []
        
        # 顯示調試資訊（在 spinner 外面）
        self.display_debug_info()
        
        st.write("### 📊 排班執行")
        
        # 使用 Beam Search 產生多個方案
        all_solutions = []
        
        # 記錄詳細執行過程
        execution_log = []
        
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
                execution_log.append(f"方案 {len(all_solutions)}: 分數 {score:.0f}")
        
        # 顯示執行記錄
        with st.expander("📝 執行記錄", expanded=False):
            for log in execution_log:
                st.write(log)
        
        # 排序並取前5個
        all_solutions.sort(key=lambda x: x['score'], reverse=True)
        top_5_solutions = all_solutions[:5]
        
        # 轉換為 SchedulingState
        result = []
        violation_summary = []
        
        for idx, sol in enumerate(top_5_solutions):
            state = self._create_state(sol['schedule'])
            result.append(state)
            
            # 驗證硬約束
            violations = self._validate_hard_constraints(sol['schedule'])
            if violations:
                violation_summary.append(f"方案 {idx+1}: {len(violations)} 個違規")
                st.error(f"方案 {idx+1} 違反硬約束：")
                for v in violations[:3]:
                    st.write(f"  - {v}")
            else:
                st.success(f"方案 {idx+1}: 分數 {state.score:.2f}, 填充率 {state.fill_rate:.1%}, ✅ 無違規")
        
        # 顯示違規總結
        if violation_summary:
            st.error("⚠️ 違規總結:")
            for summary in violation_summary:
                st.write(f"  - {summary}")
        
        # 顯示約束違反詳情（如果有）
        if hasattr(self, '_constraint_violations') and self._constraint_violations:
            with st.expander(f"🚫 約束違反詳情 ({len(self._constraint_violations)} 個)", expanded=False):
                for violation in self._constraint_violations[:20]:
                    st.write(f"- {violation}")
        
        if len(result) < 5:
            st.warning(f"只產生了 {len(result)} 個不同的方案")
        
        # 打印到 console（保留原本的輸出）
        print(f"✅ Generated {len(result)} solutions")
        for i, state in enumerate(result):
            print(f"Solution {i+1}: Score={state.score:.2f}, Fill rate={state.fill_rate:.1%}")
        
        return result
    
    def _generate_solution(self, seed: int) -> Dict:
        """產生一個解（使用固定策略但加入變化）"""
        random.seed(seed * 42)
        
        # 初始化空白排班
        schedule = {}
        for date_str in self.weekdays + self.holidays:
            schedule[date_str] = ScheduleSlot(date=date_str)
        
        used_quota = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        # 記錄分配過程（僅第一個方案）
        assignment_log = [] if seed == 0 else None
        
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
                        if assignment_log is not None:
                            assignment_log.append(f"{date_str} 主治: {doctor_name} (優先)")
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
                        if assignment_log is not None:
                            assignment_log.append(f"{date_str} 總醫師: {doctor_name} (優先)")
                        break
        
        # Step 2: 填充其他日期（假日優先，不可值班日多的人優先）
        for date_str in self.holidays + self.weekdays:
            # 填充主治
            if not schedule[date_str].attending:
                # 取得候選人並排序
                candidates = []
                rejection_reasons = []
                
                for doctor in self.attending_doctors:
                    can_assign, reason = self._can_assign_strict(doctor.name, date_str, "主治", schedule, used_quota)
                    if can_assign:
                        candidates.append(doctor.name)
                    else:
                        rejection_reasons.append(f"{doctor.name}: {reason}")
                
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
                    if assignment_log is not None:
                        assignment_log.append(f"{date_str} 主治: {doctor_name} (從 {len(candidates)} 個候選人中選擇)")
                elif assignment_log is not None and rejection_reasons:
                    # 記錄為何沒有候選人
                    assignment_log.append(f"{date_str} 主治: 無法分配 - {rejection_reasons[:2]}")
            
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
                    if assignment_log is not None:
                        assignment_log.append(f"{date_str} 總醫師: {doctor_name}")
        
        # 顯示分配記錄（只顯示第一個方案）
        if assignment_log:
            with st.expander("🔍 方案1 分配過程（前20個）", expanded=False):
                for log in assignment_log[:20]:
                    st.write(f"  - {log}")
        
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