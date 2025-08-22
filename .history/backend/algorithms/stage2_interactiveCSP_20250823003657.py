"""
Stage 2: 智慧交換補洞系統
採用三階段策略：
1. 優先使用還有配額的醫師（B類）
2. 當只有超額醫師（A類）時，嘗試與其他醫師交換
3. 系統性地解決所有空缺
"""
import streamlit as st
import copy
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta

from backend.models import Doctor, ScheduleSlot
from backend.utils import check_consecutive_days

@dataclass
class GapInfo:
    """未填格資訊"""
    date: str
    role: str
    is_holiday: bool
    is_weekend: bool
    severity: float
    candidates_with_quota: List[str]      # B類：還有配額的醫師
    candidates_over_quota: List[str]      # A類：配額已滿的醫師
    unavailable_doctors: List[str]        # C類：不可選醫師（含原因）

@dataclass
class DoctorAssignment:
    """醫師排班記錄"""
    doctor_name: str
    date: str
    role: str
    is_holiday: bool
    
@dataclass
class SwapSolution:
    """交換解決方案"""
    gap_date: str
    gap_role: str
    donor_doctor: str              # A類醫師（要填入空格的）
    donor_original_date: str       # A類醫師原本的班
    recipient_doctor: str          # C類醫師（接手A類醫師班的）
    is_feasible: bool
    reason: str
    score_delta: float

class Stage2SmartSwapper:
    """Stage 2: 智慧交換補洞系統"""
    
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
        
        # 建立醫師當前排班索引
        self.doctor_assignments = self._build_assignment_index()
        
        # 分析空缺
        self.gaps = []
        self.analyze_all_gaps()
    
    def _build_assignment_index(self) -> Dict[str, List[DoctorAssignment]]:
        """建立每個醫師的當前排班索引"""
        assignments = defaultdict(list)
        
        for date_str, slot in self.schedule.items():
            is_holiday = date_str in self.holidays
            
            if slot.attending:
                assignments[slot.attending].append(
                    DoctorAssignment(slot.attending, date_str, "主治", is_holiday)
                )
            
            if slot.resident:
                assignments[slot.resident].append(
                    DoctorAssignment(slot.resident, date_str, "總醫師", is_holiday)
                )
        
        return assignments
    
    def _count_doctor_duties(self, doctor_name: str) -> Dict:
        """計算醫師已值班次數"""
        counts = {'weekday': 0, 'holiday': 0}
        
        for assignment in self.doctor_assignments.get(doctor_name, []):
            if assignment.is_holiday:
                counts['holiday'] += 1
            else:
                counts['weekday'] += 1
        
        return counts
    
    def analyze_all_gaps(self):
        """分析所有空缺並分類候選醫師"""
        self.gaps = []
        
        for date_str, slot in self.schedule.items():
            # 檢查主治醫師空缺
            if not slot.attending:
                gap = self._analyze_single_gap(date_str, "主治")
                self.gaps.append(gap)
            
            # 檢查總醫師空缺
            if not slot.resident:
                gap = self._analyze_single_gap(date_str, "總醫師")
                self.gaps.append(gap)
        
        # 按嚴重度排序
        self.gaps.sort(key=lambda x: x.severity, reverse=True)
    
    def _analyze_single_gap(self, date: str, role: str) -> GapInfo:
        """分析單個空缺，將醫師分為三類"""
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        is_holiday = date in self.holidays
        is_weekend = date_obj.weekday() >= 5
        
        # 初始化三類醫師列表
        candidates_with_quota = []    # B類
        candidates_over_quota = []    # A類
        unavailable_doctors = []       # C類
        
        # 分類所有醫師
        doctors_in_role = [d for d in self.doctors if d.role == role]
        
        for doctor in doctors_in_role:
            classification = self._classify_doctor_for_gap(doctor, date, is_holiday)
            
            if classification == 'B':
                candidates_with_quota.append(doctor.name)
            elif classification == 'A':
                candidates_over_quota.append(doctor.name)
            else:  # 'C'
                unavailable_doctors.append(doctor.name)
        
        # 計算嚴重度
        severity = self._calculate_severity(
            len(candidates_with_quota),
            len(candidates_over_quota),
            is_holiday,
            is_weekend,
            role
        )
        
        return GapInfo(
            date=date,
            role=role,
            is_holiday=is_holiday,
            is_weekend=is_weekend,
            severity=severity,
            candidates_with_quota=candidates_with_quota,
            candidates_over_quota=candidates_over_quota,
            unavailable_doctors=unavailable_doctors
        )
    
    def _classify_doctor_for_gap(self, doctor: Doctor, date: str, is_holiday: bool) -> str:
        """
        分類醫師對於特定空缺的可用性
        Returns: 'A' (超額), 'B' (有配額), 'C' (不可用)
        """
        # 檢查不可值班日
        if date in doctor.unavailable_dates:
            return 'C'
        
        # 檢查同一天是否已有其他角色
        slot = self.schedule[date]
        if doctor.name in [slot.attending, slot.resident]:
            return 'C'
        
        # 檢查連續值班
        if self._would_violate_consecutive(doctor.name, date):
            return 'C'
        
        # 檢查配額
        counts = self._count_doctor_duties(doctor.name)
        
        if is_holiday:
            if counts['holiday'] >= doctor.holiday_quota:
                return 'A'  # 配額已滿但技術上可排（需要交換）
            else:
                return 'B'  # 還有配額
        else:
            if counts['weekday'] >= doctor.weekday_quota:
                return 'A'
            else:
                return 'B'
    
    def _would_violate_consecutive(self, doctor_name: str, date: str) -> bool:
        """檢查是否會違反連續值班限制"""
        return check_consecutive_days(
            self.schedule, 
            doctor_name, 
            date,
            self.constraints.max_consecutive_days
        )
    
    def _calculate_severity(self, b_count: int, a_count: int, 
                           is_holiday: bool, is_weekend: bool, role: str) -> float:
        """計算空缺嚴重度"""
        severity = 0.0
        
        # B類醫師存在時嚴重度很低（因為可以直接填）
        if b_count > 0:
            severity = 1.0 / (b_count + 1)  # 0-1之間
        # 只有A類醫師時
        elif a_count > 0:
            severity = 50 + (10 / a_count)  # 50-60之間
        # 完全沒有可用醫師
        else:
            severity = 100
        
        # 時間權重
        if is_holiday:
            severity += 20
        if is_weekend:
            severity += 10
        
        # 角色權重
        if role == "主治":
            severity += 5
        
        return severity
    
    def fill_gaps_with_quota(self) -> List[Tuple[str, str, str]]:
        """
        第一步：使用B類醫師（有配額的）直接填補空缺
        Returns: 填補的列表 [(date, role, doctor_name), ...]
        """
        filled = []
        
        for gap in self.gaps:
            if gap.candidates_with_quota:
                # 選擇最佳的B類醫師
                best_doctor = self._select_best_candidate(
                    gap.candidates_with_quota, 
                    gap.date, 
                    gap.role
                )
                
                if best_doctor:
                    # 直接填入
                    if gap.role == "主治":
                        self.schedule[gap.date].attending = best_doctor
                    else:
                        self.schedule[gap.date].resident = best_doctor
                    
                    # 更新索引
                    self.doctor_assignments[best_doctor].append(
                        DoctorAssignment(best_doctor, gap.date, gap.role, gap.is_holiday)
                    )
                    
                    filled.append((gap.date, gap.role, best_doctor))
                    
                    # 記錄日誌
                    st.success(f"✅ 直接填補：{gap.date} {gap.role} <- {best_doctor}")
        
        # 重新分析剩餘空缺
        if filled:
            self.analyze_all_gaps()
        
        return filled
    
    def _select_best_candidate(self, candidates: List[str], date: str, role: str) -> Optional[str]:
        """從候選人中選擇最佳人選"""
        if not candidates:
            return None
        
        best_score = -float('inf')
        best_doctor = None
        
        for doctor_name in candidates:
            score = self._score_candidate(doctor_name, date)
            if score > best_score:
                best_score = score
                best_doctor = doctor_name
        
        return best_doctor
    
    def _score_candidate(self, doctor_name: str, date: str) -> float:
        """評分候選人"""
        doctor = self.doctor_map[doctor_name]
        score = 0.0
        
        # 偏好日期加分
        if date in doctor.preferred_dates:
            score += 50
        
        # 負載平衡（使用率低的優先）
        counts = self._count_doctor_duties(doctor_name)
        total_used = counts['weekday'] + counts['holiday']
        total_quota = doctor.weekday_quota + doctor.holiday_quota
        
        if total_quota > 0:
            usage_rate = total_used / total_quota
            score += (1 - usage_rate) * 30
        
        return score
    
    def find_swap_solutions(self, gap: GapInfo) -> List[SwapSolution]:
        """
        第二步：為只有A類醫師的空缺尋找交換方案
        """
        solutions = []
        
        # 對每個A類醫師
        for a_doctor_name in gap.candidates_over_quota:
            a_doctor = self.doctor_map[a_doctor_name]
            
            # 取得A類醫師的所有現有排班
            a_assignments = self.doctor_assignments.get(a_doctor_name, [])
            
            # 只考慮相同角色的班次（主治只能換主治）
            relevant_assignments = [
                asn for asn in a_assignments 
                if asn.role == gap.role
            ]
            
            # 對每個現有班次，嘗試找C類醫師接手
            for assignment in relevant_assignments:
                swap_solution = self._try_swap(
                    gap, a_doctor_name, assignment
                )
                
                if swap_solution and swap_solution.is_feasible:
                    solutions.append(swap_solution)
        
        # 按分數排序
        solutions.sort(key=lambda x: x.score_delta, reverse=True)
        return solutions
    
    def _try_swap(self, gap: GapInfo, a_doctor_name: str, 
                  a_assignment: DoctorAssignment) -> Optional[SwapSolution]:
        """
        嘗試將A類醫師的某個班次與C類醫師交換
        """
        # 找出所有C類醫師
        c_doctors = gap.unavailable_doctors
        
        for c_doctor_name in c_doctors:
            c_doctor = self.doctor_map[c_doctor_name]
            
            # 檢查C類醫師是否可以接手A類醫師的班
            if self._can_take_over(c_doctor, a_assignment):
                # 檢查交換後A類醫師是否可以填補空缺
                if self._can_fill_after_swap(a_doctor_name, gap.date, a_assignment.date):
                    
                    # 計算交換的分數影響
                    score_delta = self._calculate_swap_score(
                        gap, a_doctor_name, a_assignment, c_doctor_name
                    )
                    
                    return SwapSolution(
                        gap_date=gap.date,
                        gap_role=gap.role,
                        donor_doctor=a_doctor_name,
                        donor_original_date=a_assignment.date,
                        recipient_doctor=c_doctor_name,
                        is_feasible=True,
                        reason=f"{c_doctor_name} 接手 {a_doctor_name} 在 {a_assignment.date} 的班",
                        score_delta=score_delta
                    )
        
        return None
    
    def _can_take_over(self, doctor: Doctor, assignment: DoctorAssignment) -> bool:
        """檢查醫師是否可以接手某個班次"""
        # 角色必須匹配
        if doctor.role != assignment.role:
            return False
        
        # 不能是不可值班日
        if assignment.date in doctor.unavailable_dates:
            return False
        
        # 檢查配額
        counts = self._count_doctor_duties(doctor.name)
        if assignment.is_holiday:
            if counts['holiday'] >= doctor.holiday_quota:
                return False
        else:
            if counts['weekday'] >= doctor.weekday_quota:
                return False
        
        # 檢查連續值班
        if self._would_violate_consecutive(doctor.name, assignment.date):
            return False
        
        # 檢查是否同一天已有其他角色
        slot = self.schedule[assignment.date]
        if doctor.name in [slot.attending, slot.resident]:
            return False
        
        return True
    
    def _can_fill_after_swap(self, doctor_name: str, gap_date: str, 
                             swap_out_date: str) -> bool:
        """檢查交換後醫師是否可以填補空缺"""
        # 模擬移除原班次後檢查連續值班
        temp_schedule = copy.deepcopy(self.schedule)
        
        # 移除原班次
        slot = temp_schedule[swap_out_date]
        if slot.attending == doctor_name:
            slot.attending = None
        if slot.resident == doctor_name:
            slot.resident = None
        
        # 檢查新位置的連續值班
        return not check_consecutive_days(
            temp_schedule, doctor_name, gap_date, 
            self.constraints.max_consecutive_days
        )
    
    def _calculate_swap_score(self, gap: GapInfo, a_doctor: str,
                             a_assignment: DoctorAssignment, c_doctor: str) -> float:
        """計算交換方案的分數"""
        score = 100.0  # 基礎填補分數
        
        a_doc = self.doctor_map[a_doctor]
        c_doc = self.doctor_map[c_doctor]
        
        # A醫師填補空缺的偏好
        if gap.date in a_doc.preferred_dates:
            score += 20
        
        # C醫師接手班次的偏好
        if a_assignment.date in c_doc.preferred_dates:
            score += 15
        
        # 負載平衡考量
        a_counts = self._count_doctor_duties(a_doctor)
        c_counts = self._count_doctor_duties(c_doctor)
        
        # C醫師負載較低更好
        c_usage = (c_counts['weekday'] + c_counts['holiday']) / \
                  (c_doc.weekday_quota + c_doc.holiday_quota + 1)
        score += (1 - c_usage) * 10
        
        return score
    
    def apply_swap(self, solution: SwapSolution) -> bool:
        """執行交換方案"""
        try:
            # 1. 從原班次移除A類醫師
            original_slot = self.schedule[solution.donor_original_date]
            if solution.gap_role == "主治":
                original_slot.attending = solution.recipient_doctor
            else:
                original_slot.resident = solution.recipient_doctor
            
            # 2. 將A類醫師填入空缺
            gap_slot = self.schedule[solution.gap_date]
            if solution.gap_role == "主治":
                gap_slot.attending = solution.donor_doctor
            else:
                gap_slot.resident = solution.donor_doctor
            
            # 3. 更新索引
            # 移除A醫師的原班次
            self.doctor_assignments[solution.donor_doctor] = [
                asn for asn in self.doctor_assignments[solution.donor_doctor]
                if asn.date != solution.donor_original_date or asn.role != solution.gap_role
            ]
            
            # 添加A醫師的新班次
            self.doctor_assignments[solution.donor_doctor].append(
                DoctorAssignment(
                    solution.donor_doctor, 
                    solution.gap_date, 
                    solution.gap_role,
                    solution.gap_date in self.holidays
                )
            )
            
            # 添加C醫師的新班次
            self.doctor_assignments[solution.recipient_doctor].append(
                DoctorAssignment(
                    solution.recipient_doctor,
                    solution.donor_original_date,
                    solution.gap_role,
                    solution.donor_original_date in self.holidays
                )
            )
            
            # 重新分析空缺
            self.analyze_all_gaps()
            
            return True
            
        except Exception as e:
            st.error(f"交換失敗：{str(e)}")
            return False
    
    def get_status_report(self) -> Dict:
        """取得當前狀態報告"""
        total_slots = len(self.schedule) * 2
        filled_slots = sum(
            1 for slot in self.schedule.values() 
            for attr in [slot.attending, slot.resident] 
            if attr
        )
        unfilled_slots = total_slots - filled_slots
        
        # 統計各類空缺
        gaps_with_b = sum(1 for g in self.gaps if g.candidates_with_quota)
        gaps_with_only_a = sum(1 for g in self.gaps 
                              if not g.candidates_with_quota and g.candidates_over_quota)
        gaps_impossible = sum(1 for g in self.gaps 
                            if not g.candidates_with_quota and not g.candidates_over_quota)
        
        return {
            'total_slots': total_slots,
            'filled_slots': filled_slots,
            'unfilled_slots': unfilled_slots,
            'fill_rate': filled_slots / total_slots if total_slots > 0 else 0,
            'gaps_easy': gaps_with_b,      # 可直接填補
            'gaps_swap': gaps_with_only_a,  # 需要交換
            'gaps_hard': gaps_impossible,   # 無解
            'is_complete': unfilled_slots == 0
        }
    
    def run_auto_fill(self) -> Dict:
        """執行自動填補流程"""
        results = {
            'direct_fills': [],
            'swaps': [],
            'remaining_gaps': []
        }
        
        # Step 1: 直接填補有配額的
        st.info("🔄 Step 1: 填補有配額餘額的醫師...")
        direct_fills = self.fill_gaps_with_quota()
        results['direct_fills'] = direct_fills
        
        # Step 2: 處理需要交換的空缺
        st.info("🔄 Step 2: 處理需要交換的空缺...")
        for gap in self.gaps:
            if not gap.candidates_with_quota and gap.candidates_over_quota:
                solutions = self.find_swap_solutions(gap)
                
                if solutions:
                    # 選擇最佳方案
                    best_solution = solutions[0]
                    
                    # 執行交換
                    if self.apply_swap(best_solution):
                        results['swaps'].append({
                            'gap': f"{gap.date} {gap.role}",
                            'solution': best_solution.reason,
                            'score': best_solution.score_delta
                        })
                        st.success(f"✅ 交換成功：{best_solution.reason}")
                else:
                    results['remaining_gaps'].append({
                        'date': gap.date,
                        'role': gap.role,
                        'reason': '無可行交換方案'
                    })
        
        # Step 3: 報告剩餘無解空缺
        final_gaps = [g for g in self.gaps if not g.candidates_with_quota and not g.candidates_over_quota]
        for gap in final_gaps:
            results['remaining_gaps'].append({
                'date': gap.date,
                'role': gap.role,
                'reason': '無任何可用醫師'
            })
        
        return results