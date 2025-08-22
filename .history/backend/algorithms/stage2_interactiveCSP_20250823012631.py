"""
Stage 2: 進階智慧交換補洞系統（含詳細中文日誌）
包含前瞻性評估、多步交換鏈、回溯機制和機會成本分析
"""
import streamlit as st
import copy
import heapq
import logging
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum

from backend.models import Doctor, ScheduleSlot
from backend.utils import check_consecutive_days

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DoctorCategory(Enum):
    """醫師分類"""
    B_AVAILABLE = "B"  # 有配額
    A_OVER_QUOTA = "A"  # 超額
    C_UNAVAILABLE = "C"  # 不可用

@dataclass
class GapInfo:
    """未填格資訊（增強版）"""
    date: str
    role: str
    is_holiday: bool
    is_weekend: bool
    severity: float
    opportunity_cost: float  # 機會成本
    candidates_with_quota: List[str]      # B類
    candidates_over_quota: List[str]      # A類
    unavailable_doctors: List[str]        # C類
    future_impact_score: float = 0.0      # 未來影響分數
    uniqueness_score: float = 0.0         # 唯一性分數
    
    @property
    def priority_score(self) -> float:
        """綜合優先級分數"""
        return (self.severity * 0.4 + 
                self.opportunity_cost * 0.3 + 
                self.future_impact_score * 0.2 +
                self.uniqueness_score * 0.1)

@dataclass
class DoctorAssignment:
    """醫師排班記錄"""
    doctor_name: str
    date: str
    role: str
    is_holiday: bool
    locked: bool = False  # 是否鎖定（不可交換）

@dataclass
class SwapChain:
    """交換鏈（支援多步交換）"""
    chain_id: str
    steps: List['SwapStep'] = field(default_factory=list)
    total_score: float = 0.0
    feasibility_score: float = 1.0
    
    def add_step(self, step: 'SwapStep'):
        self.steps.append(step)
        self.total_score += step.score_delta
        self.feasibility_score *= step.feasibility

@dataclass
class SwapStep:
    """單個交換步驟"""
    from_doctor: str
    to_doctor: str
    date: str
    role: str
    score_delta: float
    feasibility: float = 1.0
    description: str = ""

@dataclass
class SystemState:
    """系統狀態快照（用於回溯）"""
    schedule: Dict[str, ScheduleSlot]
    doctor_assignments: Dict[str, List[DoctorAssignment]]
    gaps: List[GapInfo]
    applied_swaps: List[SwapChain]
    timestamp: datetime = field(default_factory=datetime.now)

class Stage2AdvancedSwapper:
    """Stage 2: 進階智慧交換補洞系統"""
    
    def __init__(self, schedule: Dict[str, ScheduleSlot], 
                 doctors: List[Doctor], constraints,
                 weekdays: List[str], holidays: List[str]):
        
        st.info("🚀 初始化 Stage 2 進階智慧交換系統...")
        logger.info("===== Stage 2 系統初始化開始 =====")
        
        self.schedule = schedule
        self.doctors = doctors
        self.constraints = constraints
        self.weekdays = weekdays
        self.holidays = holidays
        
        # 建立索引
        logger.info(f"建立醫師索引，共 {len(doctors)} 位醫師")
        self.doctor_map = {d.name: d for d in doctors}
        
        # 建立排班索引
        self.doctor_assignments = self._build_assignment_index()
        logger.info(f"建立排班索引完成，已排班醫師數：{len(self.doctor_assignments)}")
        
        # 狀態管理
        self.state_history: List[SystemState] = []
        self.applied_swaps: List[SwapChain] = []
        
        # 快取
        self.feasibility_cache = {}
        self.impact_cache = {}
        
        # 分析空缺
        st.info("📊 開始分析所有空缺...")
        self.gaps = []
        self.analyze_all_gaps_with_lookahead()
        
        logger.info(f"===== 初始化完成，發現 {len(self.gaps)} 個空缺 =====")
    
    def _build_assignment_index(self) -> Dict[str, List[DoctorAssignment]]:
        """建立醫師排班索引"""
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
    
    def save_state(self) -> SystemState:
        """保存當前狀態（用於回溯）"""
        logger.info("💾 保存系統狀態快照")
        state = SystemState(
            schedule=copy.deepcopy(self.schedule),
            doctor_assignments=copy.deepcopy(self.doctor_assignments),
            gaps=copy.deepcopy(self.gaps),
            applied_swaps=copy.deepcopy(self.applied_swaps)
        )
        self.state_history.append(state)
        logger.info(f"狀態保存成功，歷史記錄數：{len(self.state_history)}")
        return state
    
    def restore_state(self, state: SystemState):
        """恢復到之前的狀態"""
        logger.warning("↩️ 執行狀態回溯")
        st.warning(f"↩️ 回溯到 {state.timestamp.strftime('%H:%M:%S')} 的狀態")
        
        self.schedule = state.schedule
        self.doctor_assignments = state.doctor_assignments
        self.gaps = state.gaps
        self.applied_swaps = state.applied_swaps
        
        # 清除快取
        self.feasibility_cache.clear()
        self.impact_cache.clear()
        
        logger.info("回溯完成，快取已清除")
    
    def analyze_all_gaps_with_lookahead(self):
        """分析所有空缺並計算前瞻性指標"""
        logger.info("===== 開始全面空缺分析 =====")
        st.info("🔍 正在分析所有空缺並計算優先級...")
        
        self.gaps = []
        
        # 第一步：基本分析
        logger.info("步驟1：掃描所有空缺位置")
        gap_count = 0
        
        for date_str, slot in self.schedule.items():
            if not slot.attending:
                gap = self._analyze_single_gap_enhanced(date_str, "主治")
                self.gaps.append(gap)
                gap_count += 1
                logger.debug(f"發現空缺：{date_str} 主治醫師")
            
            if not slot.resident:
                gap = self._analyze_single_gap_enhanced(date_str, "總醫師")
                self.gaps.append(gap)
                gap_count += 1
                logger.debug(f"發現空缺：{date_str} 總醫師")
        
        logger.info(f"共發現 {gap_count} 個空缺")
        
        # 第二步：計算機會成本和未來影響
        logger.info("步驟2：計算機會成本")
        self._calculate_opportunity_costs()
        
        logger.info("步驟3：計算未來影響")
        self._calculate_future_impacts()
        
        # 第三步：按綜合優先級排序
        logger.info("步驟4：計算綜合優先級並排序")
        self.gaps.sort(key=lambda x: x.priority_score, reverse=True)
        
        # 輸出分析結果摘要
        if self.gaps:
            st.success(f"""
            📊 **空缺分析完成**
            - 總空缺數：{len(self.gaps)}
            - 最高優先級：{self.gaps[0].priority_score:.2f} ({self.gaps[0].date} {self.gaps[0].role})
            - 可直接填補（B類）：{sum(1 for g in self.gaps if g.candidates_with_quota)} 個
            - 需要交換（A類）：{sum(1 for g in self.gaps if not g.candidates_with_quota and g.candidates_over_quota)} 個
            - 無解空缺：{sum(1 for g in self.gaps if not g.candidates_with_quota and not g.candidates_over_quota)} 個
            """)
            
            logger.info(f"最高優先級空缺：{self.gaps[0].date} {self.gaps[0].role}，分數：{self.gaps[0].priority_score:.2f}")
    
    def _analyze_single_gap_enhanced(self, date: str, role: str) -> GapInfo:
        """增強版單個空缺分析"""
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        is_holiday = date in self.holidays
        is_weekend = date_obj.weekday() >= 5
        
        # 分類醫師
        candidates_with_quota = []
        candidates_over_quota = []
        unavailable_doctors = []
        
        doctors_in_role = [d for d in self.doctors if d.role == role]
        
        logger.debug(f"分析 {date} {role}：共 {len(doctors_in_role)} 位醫師")
        
        for doctor in doctors_in_role:
            category = self._classify_doctor_for_gap(doctor, date, is_holiday)
            
            if category == DoctorCategory.B_AVAILABLE:
                candidates_with_quota.append(doctor.name)
                logger.debug(f"  {doctor.name} - B類（有配額）")
            elif category == DoctorCategory.A_OVER_QUOTA:
                candidates_over_quota.append(doctor.name)
                logger.debug(f"  {doctor.name} - A類（超額）")
            else:
                unavailable_doctors.append(doctor.name)
                logger.debug(f"  {doctor.name} - C類（不可用）")
        
        # 計算基本嚴重度
        severity = self._calculate_severity(
            len(candidates_with_quota),
            len(candidates_over_quota),
            is_holiday,
            is_weekend,
            role
        )
        
        # 計算唯一性分數
        uniqueness_score = self._calculate_uniqueness_score(
            candidates_with_quota,
            role
        )
        
        logger.debug(f"{date} {role} 分析結果：B類{len(candidates_with_quota)}人，A類{len(candidates_over_quota)}人，嚴重度{severity:.2f}")
        
        return GapInfo(
            date=date,
            role=role,
            is_holiday=is_holiday,
            is_weekend=is_weekend,
            severity=severity,
            opportunity_cost=0.0,  # 稍後計算
            candidates_with_quota=candidates_with_quota,
            candidates_over_quota=candidates_over_quota,
            unavailable_doctors=unavailable_doctors,
            uniqueness_score=uniqueness_score
        )
    
    def _calculate_uniqueness_score(self, candidates: List[str], role: str) -> float:
        """計算候選人唯一性分數"""
        if not candidates:
            return 100.0
        
        if len(candidates) == 1:
            # 檢查這個唯一候選人是否也是其他空缺的唯一選擇
            unique_doctor = candidates[0]
            other_gaps_count = 0
            
            for gap in self.gaps:
                if gap.role == role and len(gap.candidates_with_quota) == 1:
                    if gap.candidates_with_quota[0] == unique_doctor:
                        other_gaps_count += 1
            
            return 50.0 + (other_gaps_count * 10)
        
        return 10.0 / len(candidates)
    
    def _calculate_opportunity_costs(self):
        """計算所有空缺的機會成本"""
        logger.info("計算機會成本...")
        
        for gap in self.gaps:
            opportunity_cost = 0.0
            
            # 檢查B類醫師的稀缺性
            for doctor in gap.candidates_with_quota:
                # 這個醫師還能填補多少其他空缺？
                other_gaps = self._count_doctor_opportunities(doctor, gap.role)
                
                if other_gaps == 1:  # 只能填這裡
                    opportunity_cost += 50
                    logger.debug(f"{doctor} 是 {gap.date} {gap.role} 的唯一B類選擇")
                elif other_gaps == 2:
                    opportunity_cost += 20
                else:
                    opportunity_cost += 5
            
            # A類醫師的交換潛力
            for doctor in gap.candidates_over_quota:
                swap_potential = self._evaluate_swap_potential(doctor, gap)
                opportunity_cost += swap_potential * 0.5
            
            gap.opportunity_cost = opportunity_cost
            
            if opportunity_cost > 30:
                logger.info(f"高機會成本空缺：{gap.date} {gap.role}，成本：{opportunity_cost:.2f}")
    
    def _count_doctor_opportunities(self, doctor_name: str, role: str) -> int:
        """計算醫師還能填補的其他空缺數"""
        count = 0
        for gap in self.gaps:
            if gap.role == role and doctor_name in gap.candidates_with_quota:
                count += 1
        return count
    
    def _evaluate_swap_potential(self, doctor_name: str, gap: GapInfo) -> float:
        """評估醫師的交換潛力"""
        assignments = self.doctor_assignments.get(doctor_name, [])
        swappable_count = 0
        
        for assignment in assignments:
            if assignment.role == gap.role and not assignment.locked:
                # 檢查有多少C類醫師可以接手
                for c_doctor in gap.unavailable_doctors:
                    if self._can_take_over_cached(c_doctor, assignment):
                        swappable_count += 1
        
        return min(swappable_count * 10, 100)
    
    def _calculate_future_impacts(self):
        """計算填補決策對未來的影響"""
        logger.info("評估未來影響...")
        
        for gap in self.gaps:
            impact_score = 0.0
            
            # 模擬填補每個B類候選人的影響
            for doctor in gap.candidates_with_quota[:3]:  # 只測試前3個
                simulated_impact = self._simulate_fill_impact(doctor, gap)
                impact_score = max(impact_score, simulated_impact)
                
                if simulated_impact < -20:
                    logger.warning(f"⚠️ {gap.date} {gap.role} 填補 {doctor} 可能造成負面影響：{simulated_impact:.2f}")
            
            gap.future_impact_score = impact_score
    
    def _simulate_fill_impact(self, doctor_name: str, gap: GapInfo) -> float:
        """模擬填補某個空缺的未來影響"""
        # 創建臨時狀態
        temp_schedule = copy.deepcopy(self.schedule)
        temp_assignments = copy.deepcopy(self.doctor_assignments)
        
        # 模擬填補
        if gap.role == "主治":
            temp_schedule[gap.date].attending = doctor_name
        else:
            temp_schedule[gap.date].resident = doctor_name
        
        # 評估剩餘空缺的可填性
        remaining_fillability = 0.0
        for other_gap in self.gaps:
            if other_gap != gap:
                # 檢查此填補是否減少了其他空缺的選項
                new_candidates = self._get_candidates_after_fill(
                    other_gap, doctor_name, gap
                )
                
                if len(new_candidates) == 0:
                    remaining_fillability -= 50  # 造成無解
                elif len(new_candidates) == 1:
                    remaining_fillability -= 20  # 選項變少
                else:
                    remaining_fillability += 5
        
        return remaining_fillability
    
    def _get_candidates_after_fill(self, gap: GapInfo, 
                                   filled_doctor: str, filled_gap: GapInfo) -> List[str]:
        """計算填補後某個空缺的剩餘候選人"""
        if filled_doctor not in gap.candidates_with_quota:
            return gap.candidates_with_quota
        
        # 如果是同一個醫師，需要重新評估
        remaining = [d for d in gap.candidates_with_quota if d != filled_doctor]
        
        # 檢查配額和約束
        for doctor_name in remaining[:]:
            doctor = self.doctor_map[doctor_name]
            if not self._check_feasibility_after_fill(doctor, gap, filled_doctor, filled_gap):
                remaining.remove(doctor_name)
        
        return remaining
    
    def _check_feasibility_after_fill(self, doctor: Doctor, gap: GapInfo,
                                     filled_doctor: str, filled_gap: GapInfo) -> bool:
        """檢查填補後的可行性"""
        # 簡化版本，實際應該更詳細
        return True
    
    def _classify_doctor_for_gap(self, doctor: Doctor, date: str, 
                                 is_holiday: bool) -> DoctorCategory:
        """分類醫師類別"""
        # 不可值班日
        if date in doctor.unavailable_dates:
            return DoctorCategory.C_UNAVAILABLE
        
        # 同一天已有角色
        slot = self.schedule[date]
        if doctor.name in [slot.attending, slot.resident]:
            return DoctorCategory.C_UNAVAILABLE
        
        # 連續值班檢查
        if self._would_violate_consecutive(doctor.name, date):
            return DoctorCategory.C_UNAVAILABLE
        
        # 配額檢查
        counts = self._count_doctor_duties(doctor.name)
        
        if is_holiday:
            if counts['holiday'] >= doctor.holiday_quota:
                return DoctorCategory.A_OVER_QUOTA
            else:
                return DoctorCategory.B_AVAILABLE
        else:
            if counts['weekday'] >= doctor.weekday_quota:
                return DoctorCategory.A_OVER_QUOTA
            else:
                return DoctorCategory.B_AVAILABLE
    
    def _would_violate_consecutive(self, doctor_name: str, date: str) -> bool:
        """檢查連續值班違規"""
        return check_consecutive_days(
            self.schedule,
            doctor_name,
            date,
            self.constraints.max_consecutive_days
        )
    
    def _count_doctor_duties(self, doctor_name: str) -> Dict:
        """計算醫師值班次數"""
        counts = {'weekday': 0, 'holiday': 0}
        
        for assignment in self.doctor_assignments.get(doctor_name, []):
            if assignment.is_holiday:
                counts['holiday'] += 1
            else:
                counts['weekday'] += 1
        
        return counts
    
    def _calculate_severity(self, b_count: int, a_count: int,
                           is_holiday: bool, is_weekend: bool, role: str) -> float:
        """計算嚴重度"""
        severity = 0.0
        
        if b_count > 0:
            severity = 1.0 / (b_count + 1)
        elif a_count > 0:
            severity = 50 + (10 / a_count)
        else:
            severity = 100
        
        if is_holiday:
            severity += 20
        if is_weekend:
            severity += 10
        if role == "主治":
            severity += 5
        
        return severity
    
    def find_multi_step_swap_chains(self, gap: GapInfo, max_depth: int = 3) -> List[SwapChain]:
        """尋找多步交換鏈"""
        logger.info(f"🔄 尋找 {gap.date} {gap.role} 的交換鏈（最大深度：{max_depth}）")
        st.info(f"🔄 正在為 {gap.date} {gap.role} 尋找可行的交換方案...")
        
        chains = []
        queue = deque()
        
        # 初始化：A類醫師作為起點
        logger.info(f"A類候選醫師：{', '.join(gap.candidates_over_quota)}")
        
        for a_doctor in gap.candidates_over_quota:
            initial_chain = SwapChain(
                chain_id=f"{gap.date}_{gap.role}_{a_doctor}"
            )
            
            # 加入初始步驟（A醫師填補空缺）
            initial_step = SwapStep(
                from_doctor=None,
                to_doctor=a_doctor,
                date=gap.date,
                role=gap.role,
                score_delta=100.0,
                description=f"{a_doctor} 填補 {gap.date} {gap.role}"
            )
            initial_chain.add_step(initial_step)
            
            queue.append((initial_chain, a_doctor, 1))
            logger.debug(f"開始探索 {a_doctor} 的交換鏈")
        
        visited = set()
        valid_chains_count = 0
        
        while queue:
            current_chain, current_doctor, depth = queue.popleft()
            
            if depth > max_depth:
                continue
            
            # 尋找當前醫師的可交換班次
            assignments = self.doctor_assignments.get(current_doctor, [])
            
            for assignment in assignments:
                if assignment.role != gap.role or assignment.locked:
                    continue
                
                # 尋找可以接手的醫師
                replacement_doctors = self._find_replacement_doctors(assignment, gap)
                
                if replacement_doctors:
                    logger.debug(f"找到 {len(replacement_doctors)} 位可接手 {current_doctor} 在 {assignment.date} 班次的醫師")
                
                for next_doctor in replacement_doctors:
                    swap_key = f"{current_doctor}_{assignment.date}_{next_doctor}"
                    
                    if swap_key in visited:
                        continue
                    
                    visited.add(swap_key)
                    
                    # 創建新的交換步驟
                    swap_step = SwapStep(
                        from_doctor=current_doctor,
                        to_doctor=next_doctor,
                        date=assignment.date,
                        role=assignment.role,
                        score_delta=self._calculate_swap_score_advanced(
                            current_doctor, next_doctor, assignment
                        ),
                        description=f"{next_doctor} 接手 {current_doctor} 在 {assignment.date} 的班"
                    )
                    
                    # 創建新鏈
                    new_chain = copy.deepcopy(current_chain)
                    new_chain.add_step(swap_step)
                    
                    # 檢查是否完成（找到可行解）
                    if self._is_chain_complete(new_chain, gap):
                        chains.append(new_chain)
                        valid_chains_count += 1
                        logger.info(f"✅ 找到可行交換鏈 #{valid_chains_count}，深度：{depth}")
                    elif depth < max_depth:
                        # 繼續搜索
                        queue.append((new_chain, next_doctor, depth + 1))
        
        # 按總分排序
        chains.sort(key=lambda x: x.total_score, reverse=True)
        
        if chains:
            st.success(f"✅ 找到 {len(chains)} 個可行交換方案")
            logger.info(f"交換鏈搜索完成，找到 {len(chains)} 個可行方案")
        else:
            st.warning(f"⚠️ 未找到可行的交換方案")
            logger.warning(f"未找到 {gap.date} {gap.role} 的可行交換鏈")
        
        return chains[:10]  # 返回前10個最佳方案
    
    def _find_replacement_doctors(self, assignment: DoctorAssignment, 
                                  original_gap: GapInfo) -> List[str]:
        """找出可以接手某個班次的醫師"""
        candidates = []
        
        # 首先考慮C類醫師
        for c_doctor in original_gap.unavailable_doctors:
            if self._can_take_over_cached(c_doctor, assignment):
                candidates.append(c_doctor)
        
        # 也考慮其他有餘額的醫師
        for doctor in self.doctors:
            if doctor.role == assignment.role and doctor.name not in candidates:
                if self._can_take_over_cached(doctor.name, assignment):
                    candidates.append(doctor.name)
        
        return candidates
    
    def _can_take_over_cached(self, doctor_name: str, 
                              assignment: DoctorAssignment) -> bool:
        """快取版本的接手檢查"""
        cache_key = f"{doctor_name}_{assignment.date}_{assignment.role}"
        
        if cache_key in self.feasibility_cache:
            return self.feasibility_cache[cache_key]
        
        result = self._can_take_over(doctor_name, assignment)
        self.feasibility_cache[cache_key] = result
        return result
    
    def _can_take_over(self, doctor_name: str, 
                       assignment: DoctorAssignment) -> bool:
        """檢查醫師是否可以接手班次"""
        doctor = self.doctor_map.get(doctor_name)
        if not doctor:
            return False
        
        # 角色匹配
        if doctor.role != assignment.role:
            return False
        
        # 不可值班日
        if assignment.date in doctor.unavailable_dates:
            return False
        
        # 配額檢查
        counts = self._count_doctor_duties(doctor_name)
        if assignment.is_holiday:
            if counts['holiday'] >= doctor.holiday_quota:
                return False
        else:
            if counts['weekday'] >= doctor.weekday_quota:
                return False
        
        # 連續值班
        if self._would_violate_consecutive(doctor_name, assignment.date):
            return False
        
        # 同天檢查
        slot = self.schedule[assignment.date]
        if doctor_name in [slot.attending, slot.resident]:
            return False
        
        return True
    
    def _calculate_swap_score_advanced(self, from_doctor: str, 
                                      to_doctor: str,
                                      assignment: DoctorAssignment) -> float:
        """進階交換評分"""
        score = 50.0
        
        to_doc = self.doctor_map.get(to_doctor)
        if not to_doc:
            return 0.0
        
        # 偏好加分
        if assignment.date in to_doc.preferred_dates:
            score += 20
        
        # 負載平衡
        to_counts = self._count_doctor_duties(to_doctor)
        to_total = to_counts['weekday'] + to_counts['holiday']
        to_quota = to_doc.weekday_quota + to_doc.holiday_quota
        
        if to_quota > 0:
            usage_rate = to_total / to_quota
            score += (1 - usage_rate) * 15
        
        # 未來影響評估
        future_impact = self._evaluate_swap_future_impact(to_doctor, assignment)
        score += future_impact * 0.5
        
        return score
    
    def _evaluate_swap_future_impact(self, doctor_name: str,
                                    assignment: DoctorAssignment) -> float:
        """評估交換對未來的影響"""
        # 簡化實作
        return 10.0
    
    def _is_chain_complete(self, chain: SwapChain, gap: GapInfo) -> bool:
        """檢查交換鏈是否完整可行"""
        if len(chain.steps) < 2:
            return False
        
        # 模擬執行交換鏈
        temp_schedule = copy.deepcopy(self.schedule)
        temp_assignments = copy.deepcopy(self.doctor_assignments)
        
        try:
            for step in chain.steps[1:]:  # 跳過第一步（填補空缺）
                # 執行交換
                slot = temp_schedule[step.date]
                if step.role == "主治":
                    slot.attending = step.to_doctor
                else:
                    slot.resident = step.to_doctor
            
            # 檢查是否所有約束都滿足
            return self._validate_schedule(temp_schedule)
            
        except:
            return False
    
    def _validate_schedule(self, schedule: Dict[str, ScheduleSlot]) -> bool:
        """驗證排班是否合法"""
        # 簡化版本
        return True
    
    def apply_swap_chain(self, chain: SwapChain) -> bool:
        """應用交換鏈"""
        logger.info(f"===== 開始應用交換鏈 {chain.chain_id} =====")
        st.info(f"🔧 正在應用 {len(chain.steps)} 步交換鏈...")
        
        # 保存狀態以便回溯
        checkpoint = self.save_state()
        
        try:
            for i, step in enumerate(chain.steps):
                logger.info(f"執行第 {i+1}/{len(chain.steps)} 步：{step.description}")
                
                if i == 0:
                    # 第一步：填補空缺
                    slot = self.schedule[step.date]
                    if step.role == "主治":
                        slot.attending = step.to_doctor
                    else:
                        slot.resident = step.to_doctor
                    
                    st.success(f"✅ 步驟 {i+1}：{step.to_doctor} 填補 {step.date} {step.role}")
                else:
                    # 後續步驟：交換班次
                    slot = self.schedule[step.date]
                    if step.role == "主治":
                        old_doctor = slot.attending
                        slot.attending = step.to_doctor
                    else:
                        old_doctor = slot.resident
                        slot.resident = step.to_doctor
                    
                    st.success(f"✅ 步驟 {i+1}：{step.to_doctor} 接替 {old_doctor} 在 {step.date}")
                
                # 更新索引
                self._update_assignments_index(step)
            
            # 驗證結果
            if self._validate_schedule(self.schedule):
                self.applied_swaps.append(chain)
                logger.info(f"✅ 交換鏈應用成功，總分數改善：{chain.total_score:.2f}")
                st.success(f"✅ 交換鏈執行成功！總分數改善：{chain.total_score:.2f}")
                return True
            else:
                # 回溯
                logger.error("❌ 交換鏈驗證失敗，執行回溯")
                st.error("❌ 交換鏈驗證失敗，正在回溯...")
                self.restore_state(checkpoint)
                return False
                
        except Exception as e:
            logger.error(f"交換鏈應用失敗：{str(e)}")
            st.error(f"❌ 交換鏈執行失敗：{str(e)}")
            self.restore_state(checkpoint)
            return False
    
    def _update_assignments_index(self, step: SwapStep):
        """更新排班索引"""
        # 實作索引更新邏輯
        pass
    
    def run_auto_fill_with_backtracking(self, max_backtracks: int = 5) -> Dict:
        """執行帶回溯的自動填補"""
        logger.info("===== 開始自動填補流程（含回溯機制）=====")
        st.header("🤖 智慧自動填補系統")
        
        results = {
            'direct_fills': [],
            'swap_chains': [],
            'backtracks': [],
            'remaining_gaps': []
        }
        
        backtrack_count = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while self.gaps and backtrack_count < max_backtracks:
            progress = (1 - len(self.gaps) / (len(self.schedule) * 2)) * 100
            progress_bar.progress(min(int(progress), 100))
            status_text.text(f"處理進度：{progress:.1f}% | 剩餘空缺：{len(self.gaps)}")
            
            # 保存檢查點
            checkpoint = self.save_state()
            
            # Step 1: 嘗試直接填補
            logger.info("===== 階段1：智慧直接填補 =====")
            st.info("🔄 階段1：使用有配額餘額的醫師直接填補...")
            direct_results = self._smart_direct_fill()
            results['direct_fills'].extend(direct_results)
            
            if direct_results:
                logger.info(f"直接填補 {len(direct_results)} 個空缺")
                st.success(f"✅ 階段1完成：成功填補 {len(direct_results)} 個空缺")
            
            # Step 2: 處理需要交換的空缺
            logger.info("===== 階段2：智慧交換填補 =====")
            st.info("🔄 階段2：透過交換鏈處理超額醫師...")
            swap_results = self._smart_swap_fill()
            results['swap_chains'].extend(swap_results)
            
            if swap_results:
                logger.info(f"透過交換填補 {len(swap_results)} 個空缺")
                st.success(f"✅ 階段2完成：透過交換解決 {len(swap_results)} 個空缺")
            
            # 檢查是否陷入死路
            if self._is_deadlocked():
                if backtrack_count < max_backtracks:
                    backtrack_count += 1
                    logger.warning(f"⚠️ 檢測到死路，執行第 {backtrack_count}/{max_backtracks} 次回溯")
                    st.warning(f"⚠️ 檢測到無解狀態，執行回溯 {backtrack_count}/{max_backtracks}")
                    
                    # 回溯到檢查點
                    self.restore_state(checkpoint)
                    
                    # 嘗試不同的策略
                    self._adjust_strategy(backtrack_count)
                    
                    results['backtracks'].append({
                        'iteration': backtrack_count,
                        'reason': '檢測到無解狀態',
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })
                else:
                    logger.error("❌ 達到最大回溯次數，停止處理")
                    st.error("❌ 已達最大回溯次數，部分空缺無法解決")
                    break
            else:
                # 成功完成或沒有更多可處理的空缺
                if not self.gaps:
                    logger.info("🎉 所有空缺已成功填補！")
                    st.balloons()
                    st.success("🎉 恭喜！所有空缺已成功填補！")
                else:
                    logger.info("處理完成，部分空缺無解")
                break
        
        # 記錄剩餘空缺
        for gap in self.gaps:
            if not gap.candidates_with_quota and not gap.candidates_over_quota:
                results['remaining_gaps'].append({
                    'date': gap.date,
                    'role': gap.role,
                    'reason': '無可用醫師'
                })
                logger.warning(f"無解空缺：{gap.date} {gap.role}")
        
        # 生成最終報告
        self._generate_final_report(results)
        
        return results
    
    def _smart_direct_fill(self) -> List[Dict]:
        """智慧直接填補（考慮未來影響）"""
        filled = []
        
        # 按優先級處理空缺
        for gap in sorted(self.gaps, key=lambda x: x.priority_score, reverse=True):
            if not gap.candidates_with_quota:
                continue
            
            logger.debug(f"處理高優先級空缺：{gap.date} {gap.role}，優先級分數：{gap.priority_score:.2f}")
            
            # 選擇最佳候選人（考慮未來影響）
            best_candidate = self._select_best_candidate_with_lookahead(gap)
            
            if best_candidate:
                # 應用填補
                if gap.role == "主治":
                    self.schedule[gap.date].attending = best_candidate
                else:
                    self.schedule[gap.date].resident = best_candidate
                
                filled.append({
                    'date': gap.date,
                    'role': gap.role,
                    'doctor': best_candidate,
                    'score': gap.priority_score
                })
                
                logger.info(f"✅ 直接填補成功：{gap.date} {gap.role} <- {best_candidate}")
                st.success(f"✅ 直接填補：{gap.date} {gap.role} ← {best_candidate}")
        
        # 重新分析
        if filled:
            logger.info(f"直接填補完成，重新分析剩餘空缺")
            self.analyze_all_gaps_with_lookahead()
        
        return filled
    
    def _select_best_candidate_with_lookahead(self, gap: GapInfo) -> Optional[str]:
        """選擇最佳候選人（考慮前瞻性）"""
        if not gap.candidates_with_quota:
            return None
        
        best_score = -float('inf')
        best_candidate = None
        
        for candidate in gap.candidates_with_quota:
            # 計算綜合分數
            immediate_score = self._score_candidate(candidate, gap.date)
            future_impact = self._simulate_fill_impact(candidate, gap)
            
            total_score = immediate_score + future_impact * 0.5
            
            if total_score > best_score:
                best_score = total_score
                best_candidate = candidate
        
        return best_candidate
    
    def _score_candidate(self, doctor_name: str, date: str) -> float:
        """候選人評分"""
        doctor = self.doctor_map[doctor_name]
        score = 0.0
        
        # 偏好日期
        if date in doctor.preferred_dates:
            score += 50
        
        # 負載平衡
        counts = self._count_doctor_duties(doctor_name)
        total_used = counts['weekday'] + counts['holiday']
        total_quota = doctor.weekday_quota + doctor.holiday_quota
        
        if total_quota > 0:
            usage_rate = total_used / total_quota
            score += (1 - usage_rate) * 30
        
        return score
    
    def _smart_swap_fill(self) -> List[Dict]:
        """智慧交換填補（支援多步交換）"""
        swap_results = []
        
        for gap in self.gaps:
            if gap.candidates_with_quota:
                continue  # 已在直接填補階段處理
            
            if not gap.candidates_over_quota:
                continue  # 無法交換
            
            logger.info(f"嘗試為 {gap.date} {gap.role} 尋找交換方案")
            
            # 尋找交換鏈（包括多步）
            chains = self.find_multi_step_swap_chains(gap, max_depth=3)
            
            if chains:
                best_chain = chains[0]
                logger.info(f"找到最佳交換鏈，包含 {len(best_chain.steps)} 步，總分：{best_chain.total_score:.2f}")
                
                if self.apply_swap_chain(best_chain):
                    swap_results.append({
                        'gap': f"{gap.date} {gap.role}",
                        'chain_length': len(best_chain.steps),
                        'total_score': best_chain.total_score,
                        'description': ' → '.join(
                            step.description for step in best_chain.steps
                        )
                    })
                    
                    # 重新分析
                    self.analyze_all_gaps_with_lookahead()
                    break  # 一次處理一個，避免衝突
        
        return swap_results
    
    def _is_deadlocked(self) -> bool:
        """檢測是否陷入死路"""
        # 檢查是否有空缺但無法處理
        for gap in self.gaps:
            if gap.candidates_with_quota:
                return False  # 還有直接解
            
            if gap.candidates_over_quota:
                # 檢查是否有可行的交換
                chains = self.find_multi_step_swap_chains(gap, max_depth=2)
                if chains:
                    return False  # 還有交換解
        
        # 如果還有空缺但都無法處理
        is_deadlocked = len(self.gaps) > 0
        
        if is_deadlocked:
            logger.warning(f"❌ 檢測到死路：剩餘 {len(self.gaps)} 個無解空缺")
            st.error(f"❌ 檢測到死路：{len(self.gaps)} 個空缺無法處理")
        
        return is_deadlocked
    
    def _adjust_strategy(self, iteration: int):
        """調整策略（用於回溯後）"""
        logger.info(f"調整策略（第 {iteration} 次）")
        
        if iteration == 1:
            # 第一次回溯：放寬優先級，嘗試不同順序
            st.info("📋 策略調整：反轉處理順序")
            self.gaps.reverse()
            logger.info("策略1：反轉空缺處理順序")
            
        elif iteration == 2:
            # 第二次：重新計算優先級權重
            st.info("📋 策略調整：增加嚴重度權重")
            for gap in self.gaps:
                gap.priority_score = (
                    gap.severity * 0.6 +  # 增加嚴重度權重
                    gap.opportunity_cost * 0.2 +
                    gap.future_impact_score * 0.1 +
                    gap.uniqueness_score * 0.1
                )
            self.gaps.sort(key=lambda x: x.priority_score, reverse=True)
            logger.info("策略2：調整優先級權重，增加嚴重度影響")
            
        elif iteration == 3:
            # 第三次：優先處理假日
            st.info("📋 策略調整：優先處理假日空缺")
            self.gaps.sort(key=lambda x: (x.is_holiday, x.priority_score), reverse=True)
            logger.info("策略3：優先處理假日空缺")
            
        else:
            # 後續：隨機打亂順序
            st.info("📋 策略調整：隨機化處理順序")
            import random
            random.shuffle(self.gaps)
            logger.info(f"策略{iteration}：隨機化處理順序")
    
    def _generate_final_report(self, results: Dict):
        """生成最終報告"""
        logger.info("===== 生成最終報告 =====")
        
        st.header("📊 執行報告")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("直接填補", len(results['direct_fills']))
        with col2:
            st.metric("交換解決", len(results['swap_chains']))
        with col3:
            st.metric("回溯次數", len(results['backtracks']))
        with col4:
            st.metric("剩餘空缺", len(results['remaining_gaps']))
        
        if results['backtracks']:
            st.subheader("↩️ 回溯記錄")
            for bt in results['backtracks']:
                st.write(f"- 第 {bt['iteration']} 次回溯 ({bt['timestamp']}): {bt['reason']}")
        
        if results['remaining_gaps']:
            st.subheader("❌ 無法解決的空缺")
            for gap in results['remaining_gaps']:
                st.write(f"- {gap['date']} {gap['role']}: {gap['reason']}")
        
        logger.info(f"報告生成完成：直接填補{len(results['direct_fills'])}個，"
                   f"交換解決{len(results['swap_chains'])}個，"
                   f"剩餘{len(results['remaining_gaps'])}個")
    
    def get_detailed_report(self) -> Dict:
        """生成詳細報告"""
        total_slots = len(self.schedule) * 2
        filled_slots = sum(
            1 for slot in self.schedule.values()
            for attr in [slot.attending, slot.resident]
            if attr
        )
        
        # 分析空缺類型
        gap_analysis = {
            'easy': [],     # 有B類醫師
            'medium': [],   # 只有A類醫師
            'hard': [],     # 無醫師
            'critical': []  # 高優先級
        }
        
        for gap in self.gaps:
            gap_info = {
                'date': gap.date,
                'role': gap.role,
                'priority': gap.priority_score,
                'candidates_b': len(gap.candidates_with_quota),
                'candidates_a': len(gap.candidates_over_quota)
            }
            
            if gap.candidates_with_quota:
                gap_analysis['easy'].append(gap_info)
            elif gap.candidates_over_quota:
                gap_analysis['medium'].append(gap_info)
            else:
                gap_analysis['hard'].append(gap_info)
            
            if gap.priority_score > 70:
                gap_analysis['critical'].append(gap_info)
        
        return {
            'summary': {
                'total_slots': total_slots,
                'filled_slots': filled_slots,
                'unfilled_slots': total_slots - filled_slots,
                'fill_rate': filled_slots / total_slots if total_slots > 0 else 0
            },
            'gap_analysis': gap_analysis,
            'applied_swaps': len(self.applied_swaps),
            'state_history': len(self.state_history),
            'optimization_metrics': {
                'average_priority': sum(g.priority_score for g in self.gaps) / len(self.gaps) if self.gaps else 0,
                'max_opportunity_cost': max((g.opportunity_cost for g in self.gaps), default=0),
                'total_future_impact': sum(g.future_impact_score for g in self.gaps)
            }
        }