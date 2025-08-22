"""
Stage 2: 安全的交換補洞系統（修正版）
確保不違反任何硬約束
"""
import streamlit as st
import copy
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime

from backend.models import Doctor, ScheduleSlot
from backend.utils import check_consecutive_days

@dataclass
class GapInfo:
    """未填格資訊"""
    date: str
    role: str
    is_holiday: bool
    fillable_doctors: List[str]      # 可以直接填入的醫師（還有配額）
    swappable_solutions: List['SwapSolution']  # 可行的交換方案

@dataclass
class SwapSolution:
    """交換方案"""
    gap_date: str
    gap_role: str
    doctor_to_fill: str           # 要填入空缺的醫師
    swap_from_date: str           # 該醫師原本的班（要被移除的）
    swap_to_doctor: str           # 接手原班的醫師
    is_valid: bool
    validation_message: str

class Stage2SafeSwapper:
    """Stage 2: 安全的交換補洞系統"""
    
    def __init__(self, schedule: Dict[str, ScheduleSlot], 
                 doctors: List[Doctor], constraints,
                 weekdays: List[str], holidays: List[str]):
        self.schedule = schedule
        self.doctors = doctors
        self.constraints = constraints
        self.weekdays = weekdays
        self.holidays = holidays
        
        # 建立醫師索引
        self.doctor_map = {d.name: d for d in doctors}
        
        # 計算每位醫師當前的班數
        self.current_duties = self._count_all_duties()
        
        # 識別被鎖定的班次（優先值班日）
        self.locked_assignments = self._identify_locked_assignments()
        
        # 分析空缺
        self.gaps = self._analyze_gaps()
    
    def _count_all_duties(self) -> Dict[str, Dict]:
        """計算所有醫師的當前班數"""
        duties = defaultdict(lambda: {'weekday': 0, 'holiday': 0, 'total': 0})
        
        for date_str, slot in self.schedule.items():
            is_holiday = date_str in self.holidays
            
            if slot.attending:
                if is_holiday:
                    duties[slot.attending]['holiday'] += 1
                else:
                    duties[slot.attending]['weekday'] += 1
                duties[slot.attending]['total'] += 1
            
            if slot.resident:
                if is_holiday:
                    duties[slot.resident]['holiday'] += 1
                else:
                    duties[slot.resident]['weekday'] += 1
                duties[slot.resident]['total'] += 1
        
        return duties
    
    def _identify_locked_assignments(self) -> Set[Tuple[str, str, str]]:
        """識別被鎖定的班次（優先值班日）"""
        locked = set()
        
        for date_str, slot in self.schedule.items():
            if slot.attending:
                doctor = self.doctor_map.get(slot.attending)
                if doctor and date_str in doctor.preferred_dates:
                    locked.add((date_str, "主治", slot.attending))
                    
            if slot.resident:
                doctor = self.doctor_map.get(slot.resident)
                if doctor and date_str in doctor.preferred_dates:
                    locked.add((date_str, "總醫師", slot.resident))
        
        return locked
    
    def _analyze_gaps(self) -> List[GapInfo]:
        """分析所有空缺"""
        gaps = []
        
        for date_str, slot in self.schedule.items():
            # 檢查主治醫師空缺
            if not slot.attending:
                gap = self._analyze_single_gap(date_str, "主治")
                if gap:
                    gaps.append(gap)
            
            # 檢查總醫師空缺
            if not slot.resident:
                gap = self._analyze_single_gap(date_str, "總醫師")
                if gap:
                    gaps.append(gap)
        
        # 按可填性排序（有直接可填醫師的優先）
        gaps.sort(key=lambda x: (len(x.fillable_doctors) == 0, -len(x.swappable_solutions)))
        
        return gaps
    
    def _analyze_single_gap(self, date: str, role: str) -> Optional[GapInfo]:
        """分析單個空缺"""
        is_holiday = date in self.holidays
        
        # 找出可以直接填入的醫師（還有配額）
        fillable_doctors = []
        
        # 找出可行的交換方案
        swappable_solutions = []
        
        for doctor in self.doctors:
            if doctor.role != role:
                continue
            
            # 檢查是否可以直接填入
            if self._can_directly_fill(doctor, date, is_holiday):
                fillable_doctors.append(doctor.name)
            
            # 檢查是否可以透過交換填入
            swap_solutions = self._find_swap_solutions(doctor, date, role, is_holiday)
            swappable_solutions.extend(swap_solutions)
        
        if not fillable_doctors and not swappable_solutions:
            # 完全無解的空缺
            return GapInfo(
                date=date,
                role=role,
                is_holiday=is_holiday,
                fillable_doctors=[],
                swappable_solutions=[]
            )
        
        return GapInfo(
            date=date,
            role=role,
            is_holiday=is_holiday,
            fillable_doctors=fillable_doctors,
            swappable_solutions=swappable_solutions
        )
    
    def _can_directly_fill(self, doctor: Doctor, date: str, is_holiday: bool) -> bool:
        """檢查醫師是否可以直接填入（不超過配額）"""
        # 基本檢查
        if date in doctor.unavailable_dates:
            return False
        
        # 檢查是否已在同一天有其他角色
        slot = self.schedule[date]
        if doctor.name in [slot.attending, slot.resident]:
            return False
        
        # 檢查連續值班
        if check_consecutive_days(self.schedule, doctor.name, date, 
                                 self.constraints.max_consecutive_days):
            return False
        
        # 檢查配額（最重要）
        current = self.current_duties[doctor.name]
        
        if is_holiday:
            if current['holiday'] >= doctor.holiday_quota:
                return False  # 假日配額已滿
        else:
            if current['weekday'] >= doctor.weekday_quota:
                return False  # 平日配額已滿
        
        return True
    
    def _find_swap_solutions(self, doctor: Doctor, gap_date: str, 
                            gap_role: str, gap_is_holiday: bool) -> List[SwapSolution]:
        """尋找醫師的交換方案"""
        solutions = []
        
        # 如果醫師配額已滿，嘗試找交換方案
        current = self.current_duties[doctor.name]
        
        # 檢查是否配額已滿
        if gap_is_holiday:
            if current['holiday'] < doctor.holiday_quota:
                return []  # 還有配額，應該直接填，不需要交換
        else:
            if current['weekday'] < doctor.weekday_quota:
                return []  # 還有配額，應該直接填，不需要交換
        
        # 配額已滿，需要找交換方案
        # 找出該醫師現有的班次（可以被移除的）
        for date_str, slot in self.schedule.items():
            # 跳過空缺日期本身
            if date_str == gap_date:
                continue
            
            # 檢查是否是該醫師的班
            is_doctor_shift = False
            shift_role = None
            
            if slot.attending == doctor.name and gap_role == "主治":
                is_doctor_shift = True
                shift_role = "主治"
            elif slot.resident == doctor.name and gap_role == "總醫師":
                is_doctor_shift = True
                shift_role = "總醫師"
            
            if not is_doctor_shift:
                continue
            
            # 檢查這個班是否被鎖定（優先值班日）
            if (date_str, shift_role, doctor.name) in self.locked_assignments:
                continue  # 優先值班日不能被交換
            
            # 檢查是否同類型（假日換假日，平日換平日）
            shift_is_holiday = date_str in self.holidays
            if shift_is_holiday != gap_is_holiday:
                continue  # 必須同類型才能交換
            
            # 找其他醫師來接手這個班
            for other_doctor in self.doctors:
                if other_doctor.role != doctor.role:
                    continue
                
                if other_doctor.name == doctor.name:
                    continue
                
                # 檢查其他醫師是否可以接手
                if self._can_take_over(other_doctor, date_str, shift_role, shift_is_holiday):
                    # 檢查交換後醫師是否可以填補空缺
                    if self._can_fill_after_swap(doctor, gap_date, date_str):
                        solutions.append(SwapSolution(
                            gap_date=gap_date,
                            gap_role=gap_role,
                            doctor_to_fill=doctor.name,
                            swap_from_date=date_str,
                            swap_to_doctor=other_doctor.name,
                            is_valid=True,
                            validation_message=f"{doctor.name} 從 {date_str} 移至 {gap_date}，{other_doctor.name} 接手 {date_str}"
                        ))
        
        return solutions
    
    def _can_take_over(self, doctor: Doctor, date: str, role: str, is_holiday: bool) -> bool:
        """檢查醫師是否可以接手某個班次"""
        # 不可值班日
        if date in doctor.unavailable_dates:
            return False
        
        # 檢查是否已在同一天有班
        slot = self.schedule[date]
        if doctor.name in [slot.attending, slot.resident]:
            return False
        
        # 檢查配額
        current = self.current_duties[doctor.name]
        
        if is_holiday:
            if current['holiday'] >= doctor.holiday_quota:
                return False
        else:
            if current['weekday'] >= doctor.weekday_quota:
                return False
        
        # 檢查連續值班
        if check_consecutive_days(self.schedule, doctor.name, date, 
                                 self.constraints.max_consecutive_days):
            return False
        
        return True
    
    def _can_fill_after_swap(self, doctor: Doctor, gap_date: str, remove_date: str) -> bool:
        """檢查交換後是否可以填補空缺（主要檢查連續值班）"""
        # 模擬移除原班次
        temp_schedule = copy.deepcopy(self.schedule)
        slot = temp_schedule[remove_date]
        
        if slot.attending == doctor.name:
            slot.attending = None
        if slot.resident == doctor.name:
            slot.resident = None
        
        # 檢查新位置的連續值班
        return not check_consecutive_days(
            temp_schedule, doctor.name, gap_date, 
            self.constraints.max_consecutive_days
        )
    
    def apply_direct_fill(self, gap: GapInfo, doctor_name: str) -> bool:
        """直接填補空缺（用於有配額的醫師）"""
        if doctor_name not in gap.fillable_doctors:
            st.error(f"錯誤：{doctor_name} 不能直接填入此空缺")
            return False
        
        doctor = self.doctor_map[doctor_name]
        is_holiday = gap.is_holiday
        
        # 更新排班
        if gap.role == "主治":
            self.schedule[gap.date].attending = doctor_name
        else:
            self.schedule[gap.date].resident = doctor_name
        
        # 更新班數統計
        if is_holiday:
            self.current_duties[doctor_name]['holiday'] += 1
        else:
            self.current_duties[doctor_name]['weekday'] += 1
        self.current_duties[doctor_name]['total'] += 1
        
        # 重新分析空缺
        self.gaps = self._analyze_gaps()
        
        st.success(f"✅ 成功：{doctor_name} 已排入 {gap.date} {gap.role}")
        return True
    
    def apply_swap(self, solution: SwapSolution) -> bool:
        """執行交換方案"""
        try:
            # 步驟1：從原班次移除醫師
            old_slot = self.schedule[solution.swap_from_date]
            if solution.gap_role == "主治":
                old_slot.attending = solution.swap_to_doctor
            else:
                old_slot.resident = solution.swap_to_doctor
            
            # 步驟2：將醫師填入空缺
            new_slot = self.schedule[solution.gap_date]
            if solution.gap_role == "主治":
                new_slot.attending = solution.doctor_to_fill
            else:
                new_slot.resident = solution.doctor_to_fill
            
            # 注意：總班數不變，只是交換了位置
            # 所以不需要更新 current_duties
            
            # 重新分析空缺
            self.gaps = self._analyze_gaps()
            
            st.success(f"✅ 交換成功：{solution.validation_message}")
            return True
            
        except Exception as e:
            st.error(f"交換失敗：{str(e)}")
            return False
    
    def get_status_report(self) -> Dict:
        """取得狀態報告"""
        total_slots = len(self.schedule) * 2
        filled_slots = sum(
            1 for slot in self.schedule.values()
            for attr in [slot.attending, slot.resident]
            if attr
        )
        
        return {
            'total_slots': total_slots,
            'filled_slots': filled_slots,
            'unfilled_slots': total_slots - filled_slots,
            'fill_rate': filled_slots / total_slots if total_slots > 0 else 0,
            'directly_fillable': sum(1 for g in self.gaps if g.fillable_doctors),
            'need_swap': sum(1 for g in self.gaps if not g.fillable_doctors and g.swappable_solutions),
            'no_solution': sum(1 for g in self.gaps if not g.fillable_doctors and not g.swappable_solutions)
        }
    
    def validate_all_constraints(self) -> List[str]:
        """驗證所有約束是否被滿足"""
        violations = []
        
        for doctor in self.doctors:
            current = self.current_duties[doctor.name]
            
            # 檢查配額
            if current['weekday'] > doctor.weekday_quota:
                violations.append(f"❌ {doctor.name} 平日班數 {current['weekday']} 超過配額 {doctor.weekday_quota}")
            
            if current['holiday'] > doctor.holiday_quota:
                violations.append(f"❌ {doctor.name} 假日班數 {current['holiday']} 超過配額 {doctor.holiday_quota}")
            
            # 檢查優先值班日
            for preferred_date in doctor.preferred_dates:
                if preferred_date in self.schedule:
                    slot = self.schedule[preferred_date]
                    if doctor.role == "主治" and slot.attending != doctor.name:
                        if not slot.attending:  # 空缺是可以接受的
                            continue
                        violations.append(f"⚠️ {doctor.name} 的優先值班日 {preferred_date} 被排給其他人")
                    elif doctor.role == "總醫師" and slot.resident != doctor.name:
                        if not slot.resident:  # 空缺是可以接受的
                            continue
                        violations.append(f"⚠️ {doctor.name} 的優先值班日 {preferred_date} 被排給其他人")
        
        return violations