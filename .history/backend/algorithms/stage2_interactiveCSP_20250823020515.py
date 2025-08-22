"""
Stage 2: 進階智慧交換補洞系統（完整版）
包含前瞻性評估、多步交換鏈、回溯機制
"""
import streamlit as st
import copy
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
import json

from backend.models import Doctor, ScheduleSlot
from backend.utils import check_consecutive_days

@dataclass
class GapInfo:
    """空缺詳細資訊"""
    date: str
    role: str
    is_holiday: bool
    is_weekend: bool = False
    
    # 候選醫師分類
    candidates_with_quota: List[str] = field(default_factory=list)  # B類醫師（有配額）
    candidates_over_quota: List[str] = field(default_factory=list)  # A類醫師（超額但可交換）
    
    # 評分指標
    severity: float = 0.0           # 嚴重度（0-100）
    opportunity_cost: float = 0.0   # 機會成本
    future_impact_score: float = 0.0  # 未來影響分數
    uniqueness_score: float = 0.0   # 唯一性分數
    priority_score: float = 0.0     # 綜合優先級

@dataclass 
class SwapStep:
    """交換步驟"""
    description: str
    from_date: str
    to_date: str
    doctor: str
    role: str
    impact_score: float = 0.0

@dataclass
class SwapChain:
    """交換鏈"""
    steps: List[SwapStep]
    total_score: float = 0.0
    feasible: bool = True
    validation_message: str = ""

@dataclass
class BacktrackState:
    """回溯狀態"""
    schedule: Dict[str, ScheduleSlot]
    current_duties: Dict[str, Dict]
    gaps: List[GapInfo]
    applied_swaps: List[SwapChain]

class Stage2AdvancedSwapper:
    """Stage 2: 進階智慧交換補洞系統"""
    
    def __init__(self, schedule: Dict[str, ScheduleSlot], 
                 doctors: List[Doctor], constraints,
                 weekdays: List[str], holidays: List[str]):
        self.schedule = copy.deepcopy(schedule)
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
        self.gaps = self._analyze_gaps_advanced()
        
        # 執行歷史
        self.applied_swaps = []
        self.state_history = []
        
        # 回溯堆疊
        self.backtrack_stack = []
    
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
    
    def _analyze_gaps_advanced(self) -> List[GapInfo]:
        """進階空缺分析（包含評分）"""
        gaps = []
        
        for date_str, slot in self.schedule.items():
            # 檢查主治醫師空缺
            if not slot.attending:
                gap = self._analyze_single_gap_advanced(date_str, "主治")
                if gap:
                    gaps.append(gap)
            
            # 檢查總醫師空缺
            if not slot.resident:
                gap = self._analyze_single_gap_advanced(date_str, "總醫師")
                if gap:
                    gaps.append(gap)
        
        # 計算優先級分數並排序
        for gap in gaps:
            gap.priority_score = self._calculate_priority_score(gap)
        
        gaps.sort(key=lambda x: -x.priority_score)
        
        return gaps
    
    def _analyze_single_gap_advanced(self, date: str, role: str) -> Optional[GapInfo]:
        """進階單個空缺分析"""
        is_holiday = date in self.holidays
        is_weekend = self._is_weekend(date)
        
        gap = GapInfo(
            date=date,
            role=role,
            is_holiday=is_holiday,
            is_weekend=is_weekend
        )
        
        # 分類候選醫師
        for doctor in self.doctors:
            if doctor.role != role:
                continue
            
            # 基本檢查
            if date in doctor.unavailable_dates:
                continue
            
            # 檢查是否已在同一天有班
            slot = self.schedule[date]
            if doctor.name in [slot.attending, slot.resident]:
                continue
            
            # 檢查連續值班
            if check_consecutive_days(self.schedule, doctor.name, date, 
                                     self.constraints.max_consecutive_days):
                continue
            
            # 檢查配額
            current = self.current_duties[doctor.name]
            
            if is_holiday:
                if current['holiday'] < doctor.holiday_quota:
                    gap.candidates_with_quota.append(doctor.name)  # B類
                else:
                    gap.candidates_over_quota.append(doctor.name)  # A類
            else:
                if current['weekday'] < doctor.weekday_quota:
                    gap.candidates_with_quota.append(doctor.name)  # B類
                else:
                    gap.candidates_over_quota.append(doctor.name)  # A類
        
        # 計算評分指標
        gap.severity = self._calculate_severity(gap)
        gap.opportunity_cost = self._calculate_opportunity_cost(gap)
        gap.future_impact_score = self._calculate_future_impact(gap)
        gap.uniqueness_score = self._calculate_uniqueness(gap)
        
        return gap
    
    def _is_weekend(self, date_str: str) -> bool:
        """判斷是否為週末"""
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.weekday() in [5, 6]  # 週六、週日
        except:
            return False
    
    def _calculate_severity(self, gap: GapInfo) -> float:
        """計算嚴重度（0-100）"""
        score = 50.0  # 基礎分數
        
        if gap.is_holiday:
            score += 20  # 假日更重要
        if gap.is_weekend:
            score += 10  # 週末更重要
        if len(gap.candidates_with_quota) == 0:
            score += 20  # 沒有B類醫師更嚴重
        if len(gap.candidates_over_quota) == 0:
            score += 30  # 完全無解最嚴重
        
        return min(100, score)
    
    def _calculate_opportunity_cost(self, gap: GapInfo) -> float:
        """計算機會成本"""
        # 如果有B類醫師，機會成本較低
        if gap.candidates_with_quota:
            return 10.0
        
        # 如果只有A類醫師，需要交換，成本較高
        if gap.candidates_over_quota:
            return 50.0
        
        # 無解，成本最高
        return 100.0
    
    def _calculate_future_impact(self, gap: GapInfo) -> float:
        """計算對未來排班的影響"""
        impact = 0.0
        
        # 計算該日期在月份中的位置
        try:
            dt = datetime.strptime(gap.date, "%Y-%m-%d")
            days_from_end = 31 - dt.day
            
            # 越接近月底，影響越小
            impact = days_from_end * 2
            
        except:
            impact = 50.0
        
        return min(100, impact)
    
    def _calculate_uniqueness(self, gap: GapInfo) -> float:
        """計算唯一性（候選人越少越唯一）"""
        total_candidates = len(gap.candidates_with_quota) + len(gap.candidates_over_quota)
        
        if total_candidates == 0:
            return 100.0
        elif total_candidates == 1:
            return 80.0
        elif total_candidates == 2:
            return 60.0
        elif total_candidates <= 4:
            return 40.0
        else:
            return 20.0
    
    def _calculate_priority_score(self, gap: GapInfo) -> float:
        """計算綜合優先級分數"""
        return (
            gap.severity * 0.3 +
            gap.opportunity_cost * 0.3 +
            gap.future_impact_score * 0.2 +
            gap.uniqueness_score * 0.2
        )
    
    def find_multi_step_swap_chains(self, gap: GapInfo, max_depth: int = 3) -> List[SwapChain]:
        """尋找多步交換鏈"""
        chains = []
        
        # 只考慮A類醫師（需要交換的）
        for doctor_name in gap.candidates_over_quota:
            doctor = self.doctor_map[doctor_name]
            
            # 找出該醫師可以被移除的班次
            removable_shifts = self._find_removable_shifts(doctor, gap)
            
            for shift_date, shift_role in removable_shifts:
                # 嘗試建立交換鏈
                chain = self._build_swap_chain(
                    gap, doctor, shift_date, shift_role, max_depth
                )
                
                if chain and chain.feasible:
                    chains.append(chain)
        
        # 按分數排序
        chains.sort(key=lambda x: -x.total_score)
        
        return chains[:10]  # 返回前10個最佳方案
    
    def _find_removable_shifts(self, doctor: Doctor, gap: GapInfo) -> List[Tuple[str, str]]:
        """找出醫師可以被移除的班次"""
        removable = []
        
        for date_str, slot in self.schedule.items():
            if date_str == gap.date:
                continue
            
            # 檢查是否為該醫師的班
            if slot.attending == doctor.name and doctor.role == "主治":
                # 檢查是否被鎖定
                if (date_str, "主治", doctor.name) not in self.locked_assignments:
                    # 檢查是否同類型（假日對假日，平日對平日）
                    is_holiday = date_str in self.holidays
                    if is_holiday == gap.is_holiday:
                        removable.append((date_str, "主治"))
            
            if slot.resident == doctor.name and doctor.role == "總醫師":
                if (date_str, "總醫師", doctor.name) not in self.locked_assignments:
                    is_holiday = date_str in self.holidays
                    if is_holiday == gap.is_holiday:
                        removable.append((date_str, "總醫師"))
        
        return removable
    
    def _build_swap_chain(self, gap: GapInfo, doctor: Doctor, 
                         shift_date: str, shift_role: str, max_depth: int) -> SwapChain:
        """建立交換鏈"""
        steps = []
        
        # 第一步：將醫師從原班次移到空缺
        step1 = SwapStep(
            description=f"{doctor.name} 從 {shift_date} 移至 {gap.date}",
            from_date=shift_date,
            to_date=gap.date,
            doctor=doctor.name,
            role=gap.role,
            impact_score=10.0
        )
        steps.append(step1)
        
        # 尋找接手原班次的醫師
        replacement_found = False
        for other_doctor in self.doctors:
            if other_doctor.role != doctor.role:
                continue
            if other_doctor.name == doctor.name:
                continue
            
            if self._can_take_over_safely(other_doctor, shift_date, shift_role):
                step2 = SwapStep(
                    description=f"{other_doctor.name} 接手 {shift_date} 的班",
                    from_date="",
                    to_date=shift_date,
                    doctor=other_doctor.name,
                    role=shift_role,
                    impact_score=5.0
                )
                steps.append(step2)
                replacement_found = True
                break
        
        if not replacement_found:
            return SwapChain(
                steps=steps,
                total_score=0,
                feasible=False,
                validation_message="找不到接手醫師"
            )
        
        # 計算總分
        total_score = 100 - gap.priority_score  # 優先級越高，分數越高
        
        return SwapChain(
            steps=steps,
            total_score=total_score,
            feasible=True,
            validation_message="可行的交換鏈"
        )
    
    def _can_take_over_safely(self, doctor: Doctor, date: str, role: str) -> bool:
        """安全檢查是否可以接手班次"""
        # 不可值班日
        if date in doctor.unavailable_dates:
            return False
        
        # 檢查是否已在同一天有班
        slot = self.schedule[date]
        if doctor.name in [slot.attending, slot.resident]:
            return False
        
        # 檢查配額
        current = self.current_duties[doctor.name]
        is_holiday = date in self.holidays
        
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
    
    def apply_swap_chain(self, chain: SwapChain) -> bool:
        """應用交換鏈"""
        if not chain.feasible:
            return False
        
        try:
            # 保存當前狀態（用於回溯）
            self._save_state()
            
            # 執行每個步驟
            for step in chain.steps:
                if step.from_date:  # 移除步驟
                    slot = self.schedule[step.from_date]
                    if step.role == "主治":
                        slot.attending = None
                    else:
                        slot.resident = None
                
                if step.to_date:  # 填入步驟
                    slot = self.schedule[step.to_date]
                    if step.role == "主治":
                        slot.attending = step.doctor
                    else:
                        slot.resident = step.doctor
            
            # 重新計算班數和空缺
            self.current_duties = self._count_all_duties()
            self.gaps = self._analyze_gaps_advanced()
            
            # 記錄應用的交換
            self.applied_swaps.append(chain)
            
            return True
            
        except Exception as e:
            st.error(f"應用交換鏈失敗：{str(e)}")
            self._restore_state()
            return False
    
    def run_auto_fill_with_backtracking(self, max_backtracks: int = 5) -> Dict:
        """執行自動填補（含回溯）"""
        results = {
            'direct_fills': [],
            'swap_chains': [],
            'backtracks': [],
            'remaining_gaps': []
        }
        
        backtrack_count = 0
        
        while self.gaps and backtrack_count < max_backtracks:
            progress_made = False
            
            # 第一階段：直接填補（B類醫師）
            for gap in self.gaps[:]:
                if gap.candidates_with_quota:
                    # 選擇最適合的B類醫師
                    best_doctor = self._select_best_candidate(gap.candidates_with_quota, gap)
                    
                    if self._apply_direct_fill(gap, best_doctor):
                        results['direct_fills'].append({
                            'date': gap.date,
                            'role': gap.role,
                            'doctor': best_doctor
                        })
                        progress_made = True
                        break
            
            if progress_made:
                continue
            
            # 第二階段：智慧交換（A類醫師）
            for gap in self.gaps[:]:
                if gap.candidates_over_quota and not gap.candidates_with_quota:
                    chains = self.find_multi_step_swap_chains(gap, max_depth=3)
                    
                    if chains:
                        # 應用最佳交換鏈
                        if self.apply_swap_chain(chains[0]):
                            results['swap_chains'].append({
                                'gap': f"{gap.date} {gap.role}",
                                'chain': chains[0].steps
                            })
                            progress_made = True
                            break
            
            if not progress_made:
                # 檢測死路
                if backtrack_count < max_backtracks:
                    # 執行回溯
                    if self._backtrack():
                        results['backtracks'].append({
                            'iteration': backtrack_count,
                            'reason': '無進展，嘗試回溯'
                        })
                        backtrack_count += 1
                    else:
                        break
                else:
                    break
        
        # 記錄剩餘空缺
        for gap in self.gaps:
            results['remaining_gaps'].append({
                'date': gap.date,
                'role': gap.role,
                'reason': self._get_gap_reason(gap)
            })
        
        return results
    
    def _select_best_candidate(self, candidates: List[str], gap: GapInfo) -> str:
        """選擇最適合的候選人"""
        # 簡單策略：選擇班數最少的
        min_duties = float('inf')
        best = candidates[0]
        
        for name in candidates:
            total = self.current_duties[name]['total']
            if total < min_duties:
                min_duties = total
                best = name
        
        return best
    
    def _apply_direct_fill(self, gap: GapInfo, doctor_name: str) -> bool:
        """直接填補空缺"""
        try:
            # 更新排班
            if gap.role == "主治":
                self.schedule[gap.date].attending = doctor_name
            else:
                self.schedule[gap.date].resident = doctor_name
            
            # 更新班數統計
            if gap.is_holiday:
                self.current_duties[doctor_name]['holiday'] += 1
            else:
                self.current_duties[doctor_name]['weekday'] += 1
            self.current_duties[doctor_name]['total'] += 1
            
            # 重新分析空缺
            self.gaps = self._analyze_gaps_advanced()
            
            return True
            
        except Exception:
            return False
    
    def _save_state(self):
        """保存當前狀態"""
        state = BacktrackState(
            schedule=copy.deepcopy(self.schedule),
            current_duties=copy.deepcopy(self.current_duties),
            gaps=copy.deepcopy(self.gaps),
            applied_swaps=copy.deepcopy(self.applied_swaps)
        )
        self.backtrack_stack.append(state)
        self.state_history.append(f"State saved at {datetime.now().strftime('%H:%M:%S')}")
    
    def _restore_state(self):
        """恢復上一個狀態"""
        if self.backtrack_stack:
            state = self.backtrack_stack.pop()
            self.schedule = state.schedule
            self.current_duties = state.current_duties
            self.gaps = state.gaps
            self.applied_swaps = state.applied_swaps
            self.state_history.append(f"State restored at {datetime.now().strftime('%H:%M:%S')}")
    
    def _backtrack(self) -> bool:
        """執行回溯"""
        if len(self.backtrack_stack) > 0:
            self._restore_state()
            return True
        return False
    
    def _get_gap_reason(self, gap: GapInfo) -> str:
        """取得空缺原因"""
        if not gap.candidates_with_quota and not gap.candidates_over_quota:
            return "無可用醫師"
        elif gap.candidates_over_quota and not gap.candidates_with_quota:
            return "所有候選人都已超額"
        else:
            return "未知原因"
    
    def get_detailed_report(self) -> Dict[str, Any]:
        """取得詳細報告"""
        total_slots = len(self.schedule) * 2
        filled_slots = sum(
            1 for slot in self.schedule.values()
            for attr in [slot.attending, slot.resident]
            if attr
        )
        
        # 空缺分類
        easy_gaps = [g for g in self.gaps if g.candidates_with_quota]
        medium_gaps = [g for g in self.gaps if g.candidates_over_quota and not g.candidates_with_quota]
        hard_gaps = [g for g in self.gaps if not g.candidates_with_quota and not g.candidates_over_quota]
        
        # 關鍵空缺（優先級最高的）
        critical_gaps = sorted(self.gaps, key=lambda x: -x.priority_score)[:5]
        
        return {
            'summary': {
                'total_slots': total_slots,
                'filled_slots': filled_slots,
                'unfilled_slots': total_slots - filled_slots,
                'fill_rate': filled_slots / total_slots if total_slots > 0 else 0
            },
            'gap_analysis': {
                'easy': easy_gaps,
                'medium': medium_gaps,
                'hard': hard_gaps,
                'critical': [
                    {
                        'date': g.date,
                        'role': g.role,
                        'priority': g.priority_score,
                        'severity': g.severity
                    }
                    for g in critical_gaps
                ]
            },
            'optimization_metrics': {
                'average_priority': sum(g.priority_score for g in self.gaps) / len(self.gaps) if self.gaps else 0,
                'max_opportunity_cost': max((g.opportunity_cost for g in self.gaps), default=0),
                'total_future_impact': sum(g.future_impact_score for g in self.gaps)
            },
            'applied_swaps': len(self.applied_swaps),
            'state_history': len(self.state_history)
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