"""
Stage 2: 進階智慧交換補洞系統（完整優化版）
包含深度搜索、多步交換鏈、回溯機制
增強版：詳細繁體中文日誌（簡化版）
"""
import copy
import time
from typing import List, Dict, Tuple, Optional, Set, Any, Callable
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
    complexity: int = 0  # 複雜度評分

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
        
        # 日誌回調（供前端使用） - 必須先初始化
        self.log_callback: Optional[Callable[[str, str], None]] = None
        
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
        
        # 搜索統計
        self.search_stats = {
            'chains_explored': 0,
            'chains_found': 0,
            'search_time': 0,
            'max_depth_reached': 0
        }
        
        # 日誌控制
        self.log_level = 'normal'  # 'verbose', 'normal', 'quiet'
        self.log_stats = {
            'last_milestone': 0,
            'milestone_interval': 100  # 每100次搜索輸出一次
        }
    
    def set_log_callback(self, callback: Callable[[str, str], None]):
        """設定日誌回調函數"""
        self.log_callback = callback
    
    def set_log_level(self, level: str):
        """設定日誌級別"""
        self.log_level = level
    
    def _log(self, message: str, level: str = "info", force: bool = False):
        """記錄日誌"""
        if not self.log_callback:
            return
        
        # 強制輸出或根據日誌級別決定
        if force:
            self.log_callback(message, level)
        elif self.log_level == 'verbose':
            self.log_callback(message, level)
        elif self.log_level == 'normal':
            # 只輸出重要資訊
            if level in ['error', 'warning', 'success'] or 'summary' in message.lower():
                self.log_callback(message, level)
        # quiet模式下只輸出錯誤
        elif self.log_level == 'quiet' and level == 'error':
            self.log_callback(message, level)
    
    def _log_search_progress(self):
        """輸出搜索進度（有節制地）"""
        if self.search_stats['chains_explored'] - self.log_stats['last_milestone'] >= self.log_stats['milestone_interval']:
            self.log_stats['last_milestone'] = self.search_stats['chains_explored']
            self._log(f"   📊 搜索進度：已探索 {self.search_stats['chains_explored']:,} 條路徑，找到 {self.search_stats['chains_found']} 個方案", "info", force=True)
    
    def _count_all_duties(self) -> Dict[str, Dict]:
        """計算所有醫師的當前班數"""
        self._log("📊 正在計算所有醫師的當前班數...", "info")
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
        
        self._log(f"✅ 已計算 {len(duties)} 位醫師的班數統計", "success")
        return duties
    
    def _identify_locked_assignments(self) -> Set[Tuple[str, str, str]]:
        """識別被鎖定的班次（優先值班日）"""
        self._log("🔒 正在識別優先值班日（鎖定班次）...", "info")
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
        
        self._log(f"🔍 找到 {len(locked)} 個鎖定班次（優先值班日）", "info")
        return locked
    
    def _analyze_gaps_advanced(self) -> List[GapInfo]:
        """進階空缺分析（包含評分）"""
        self._log("🔍 開始進階空缺分析...", "info")
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
        
        self._log(f"✅ 分析完成：找到 {len(gaps)} 個空缺", "success", force=True)
        if gaps and self.log_level != 'quiet':
            self._log(f"🎯 最高優先級空缺：{gaps[0].date} {gaps[0].role}（分數：{gaps[0].priority_score:.1f}）", "warning")
        
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
        if gap.candidates_with_quota:
            return 10.0  # B類醫師，機會成本較低
        
        if gap.candidates_over_quota:
            return 50.0  # A類醫師，需要交換，成本較高
        
        return 100.0  # 無解，成本最高
    
    def _calculate_future_impact(self, gap: GapInfo) -> float:
        """計算對未來排班的影響"""
        impact = 0.0
        
        try:
            dt = datetime.strptime(gap.date, "%Y-%m-%d")
            days_from_end = 31 - dt.day
            impact = days_from_end * 2  # 越接近月底，影響越小
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
    
    def find_deep_swap_chains(self, gap: GapInfo, max_depth: int = 5) -> List[SwapChain]:
        """尋找深度交換鏈 - 固定深度5"""
        self._log(f"🔄 開始深度搜索 {gap.date} {gap.role} 的交換鏈（深度={max_depth}）...", "info", force=True)
        
        chains = []
        visited_states = set()  # 避免重複搜索
        
        # 設定搜索時間限制
        start_time = time.time()
        max_search_time = 120  # 最多搜索2分鐘
        
        # 重置搜索統計
        self.search_stats = {
            'chains_explored': 0,
            'chains_found': 0,
            'search_time': 0,
            'max_depth_reached': 0
        }
        
        # 對每個需要交換的醫師進行搜索
        self._log(f"🎯 A類醫師（需交換）：{len(gap.candidates_over_quota)} 位", "info")
        for doctor_name in gap.candidates_over_quota:
            if time.time() - start_time > max_search_time:
                self._log(f"⏰ 搜索時間已達上限（{max_search_time}秒），停止搜索", "warning", force=True)
                break
            
            doctor = self.doctor_map[doctor_name]
            
            # 使用遞迴深度搜索
            initial_chain = SwapChain(steps=[], total_score=0, feasible=True, complexity=0)
            
            self._recursive_search_swap_chains(
                gap, doctor, initial_chain, chains, 
                visited_states, max_depth, 0, start_time, max_search_time
            )
        
        # 如果找到的交換鏈太少，嘗試更激進的策略
        if len(chains) < 5:
            self._log("⚡ 找到的方案太少，嘗試激進搜索策略...", "warning")
            chains.extend(self._find_aggressive_swap_chains(gap, max_depth))
        
        # 去重並排序
        chains = self._deduplicate_chains(chains)
        chains.sort(key=lambda x: (-x.total_score, x.complexity))
        
        # 更新統計
        self.search_stats['search_time'] = time.time() - start_time
        self.search_stats['chains_found'] = len(chains)
        
        # 輸出搜索摘要
        self._log(f"✅ 搜索完成：時間：{self.search_stats['search_time']:.2f} 秒，"
                 f"找到方案：{self.search_stats['chains_found']} 個", "success", force=True)
        
        return chains[:20]  # 返回前20個方案
    
    def _recursive_search_swap_chains(self, gap: GapInfo, doctor: Doctor, 
                                     current_chain: SwapChain, all_chains: List[SwapChain],
                                     visited: Set, max_depth: int, current_depth: int,
                                     start_time: float, max_search_time: float):
        """遞迴搜索交換鏈"""
        
        # 更新統計
        self.search_stats['chains_explored'] += 1
        if current_depth > self.search_stats['max_depth_reached']:
            self.search_stats['max_depth_reached'] = current_depth
        
        # 定期輸出進度
        self._log_search_progress()
        
        # 終止條件
        if current_depth >= max_depth:
            return
        if time.time() - start_time > max_search_time:
            return
        
        # 生成狀態簽名避免重複
        state_sig = self._generate_state_signature(current_chain)
        if state_sig in visited:
            return
        visited.add(state_sig)
        
        if current_depth == 0:
            # 第一層：找出該醫師所有可移除的班次
            removable_shifts = self._find_removable_shifts(doctor, gap)
            
            for shift_date, shift_role in removable_shifts:
                # 創建第一步：移動醫師到空缺
                step1 = SwapStep(
                    description=f"{doctor.name} 從 {shift_date} 移至 {gap.date}",
                    from_date=shift_date,
                    to_date=gap.date,
                    doctor=doctor.name,
                    role=gap.role,
                    impact_score=self._calculate_step_impact(shift_date, gap.date)
                )
                
                new_chain = SwapChain(
                    steps=[step1],
                    total_score=0,
                    feasible=True,
                    complexity=1
                )
                
                # 搜索誰可以接手 shift_date
                self._search_replacement_for_shift(
                    shift_date, shift_role, doctor.role, new_chain, 
                    all_chains, visited, max_depth, current_depth + 1,
                    start_time, max_search_time
                )
    
    def _search_replacement_for_shift(self, shift_date: str, shift_role: str, 
                                     original_role: str, current_chain: SwapChain,
                                     all_chains: List[SwapChain], visited: Set,
                                     max_depth: int, current_depth: int,
                                     start_time: float, max_search_time: float):
        """搜索誰可以接手某個班次"""
        
        # 終止條件檢查
        if time.time() - start_time > max_search_time:
            return
        
        # 找出所有可能接手的醫師
        candidates = self._find_all_replacement_candidates(shift_date, shift_role, original_role)
        
        # 按優先級排序候選人
        candidates = self._prioritize_candidates(candidates, shift_date)
        
        for candidate in candidates[:15]:  # 考慮前15個候選人
            if candidate['type'] == 'direct':
                # 可以直接接手（有配額）
                step = SwapStep(
                    description=f"{candidate['name']} 直接接手 {shift_date} 的班",
                    from_date="",
                    to_date=shift_date,
                    doctor=candidate['name'],
                    role=shift_role,
                    impact_score=5.0
                )
                
                final_chain = SwapChain(
                    steps=current_chain.steps + [step],
                    total_score=self._evaluate_chain(current_chain.steps + [step]),
                    feasible=True,
                    validation_message="可行的交換鏈",
                    complexity=len(current_chain.steps) + 1
                )
                
                all_chains.append(final_chain)
                self.search_stats['chains_found'] += 1
                
            elif candidate['type'] == 'needs_swap' and current_depth < max_depth:
                # 需要進一步交換
                step = SwapStep(
                    description=f"{candidate['name']} 從 {candidate['from_date']} 換到 {shift_date}",
                    from_date=candidate['from_date'],
                    to_date=shift_date,
                    doctor=candidate['name'],
                    role=shift_role,
                    impact_score=8.0
                )
                
                new_chain = SwapChain(
                    steps=current_chain.steps + [step],
                    total_score=current_chain.total_score,
                    feasible=True,
                    complexity=len(current_chain.steps) + 1
                )
                
                # 遞迴：現在需要填補 candidate['from_date'] 的空缺
                self._search_replacement_for_shift(
                    candidate['from_date'], candidate['from_role'], candidate['role'],
                    new_chain, all_chains, visited, max_depth, current_depth + 1,
                    start_time, max_search_time
                )
    
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
    
    def _find_all_replacement_candidates(self, date: str, role: str, 
                                        original_role: str) -> List[Dict]:
        """找出所有可能接手班次的候選人"""
        candidates = []
        is_holiday = date in self.holidays
        
        for doctor in self.doctors:
            if doctor.role != original_role:
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
                    # 可以直接接手
                    candidates.append({
                        'name': doctor.name,
                        'type': 'direct',
                        'priority': 1,
                        'score': 100 - current['total']  # 班數越少優先級越高
                    })
                else:
                    # 需要交換其他班次
                    swappable_dates = self._find_swappable_dates_for_doctor(doctor, is_holiday)
                    for swap_date, swap_role in swappable_dates:
                        candidates.append({
                            'name': doctor.name,
                            'type': 'needs_swap',
                            'from_date': swap_date,
                            'from_role': swap_role,
                            'role': doctor.role,
                            'priority': 2,
                            'score': 50 - current['total']
                        })
            else:
                # 平日邏輯
                if current['weekday'] < doctor.weekday_quota:
                    candidates.append({
                        'name': doctor.name,
                        'type': 'direct',
                        'priority': 1,
                        'score': 100 - current['total']
                    })
                else:
                    swappable_dates = self._find_swappable_dates_for_doctor(doctor, is_holiday)
                    for swap_date, swap_role in swappable_dates:
                        candidates.append({
                            'name': doctor.name,
                            'type': 'needs_swap',
                            'from_date': swap_date,
                            'from_role': swap_role,
                            'role': doctor.role,
                            'priority': 2,
                            'score': 50 - current['total']
                        })
        
        return candidates
    
    def _find_swappable_dates_for_doctor(self, doctor: Doctor, is_holiday: bool) -> List[Tuple[str, str]]:
        """找出醫師可以交換的班次"""
        swappable = []
        
        for date_str, slot in self.schedule.items():
            # 只找同類型的班次
            date_is_holiday = date_str in self.holidays
            if date_is_holiday != is_holiday:
                continue
            
            # 檢查是否為該醫師的班
            if slot.attending == doctor.name and doctor.role == "主治":
                # 檢查是否被鎖定
                if (date_str, "主治", doctor.name) not in self.locked_assignments:
                    swappable.append((date_str, "主治"))
            
            if slot.resident == doctor.name and doctor.role == "總醫師":
                if (date_str, "總醫師", doctor.name) not in self.locked_assignments:
                    swappable.append((date_str, "總醫師"))
        
        return swappable
    
    def _prioritize_candidates(self, candidates: List[Dict], date: str) -> List[Dict]:
        """按優先級排序候選人"""
        # 先按類型排序（direct優先），再按分數排序
        return sorted(candidates, key=lambda x: (x['priority'], -x['score']))
    
    def _find_aggressive_swap_chains(self, gap: GapInfo, max_depth: int) -> List[SwapChain]:
        """更激進的搜索策略"""
        chains = []
        
        self._log("💪 嘗試跨類型交換（假日↔平日）...", "info")
        
        # 策略1：考慮跨類型交換（假日換平日）
        for doctor_name in gap.candidates_over_quota:
            doctor = self.doctor_map[doctor_name]
            
            # 找出所有班次（不限同類型）
            all_shifts = []
            for date_str, slot in self.schedule.items():
                if date_str == gap.date:
                    continue
                
                if slot.attending == doctor.name and doctor.role == "主治":
                    if (date_str, "主治", doctor.name) not in self.locked_assignments:
                        all_shifts.append((date_str, "主治"))
                
                if slot.resident == doctor.name and doctor.role == "總醫師":
                    if (date_str, "總醫師", doctor.name) not in self.locked_assignments:
                        all_shifts.append((date_str, "總醫師"))
            
            # 嘗試每個班次
            for shift_date, shift_role in all_shifts[:3]:  # 只試前3個
                chain = self._try_forced_swap(gap, doctor, shift_date, shift_role)
                if chain and chain.feasible:
                    chains.append(chain)
        
        # 策略2：多醫師聯合交換
        if len(gap.candidates_over_quota) >= 2:
            self._log("🤝 嘗試多醫師聯合交換...", "info")
            multi_chains = self._try_multi_doctor_swap(gap, max_depth)
            chains.extend(multi_chains)
        
        return chains
    
    def _try_forced_swap(self, gap: GapInfo, doctor: Doctor, 
                        shift_date: str, shift_role: str) -> Optional[SwapChain]:
        """嘗試強制交換"""
        steps = []
        
        # 第一步：強制移動
        step1 = SwapStep(
            description=f"[強制] {doctor.name} 從 {shift_date} 移至 {gap.date}",
            from_date=shift_date,
            to_date=gap.date,
            doctor=doctor.name,
            role=gap.role,
            impact_score=15.0  # 強制交換懲罰更高
        )
        steps.append(step1)
        
        # 尋找任何可以接手的人
        for other_doctor in self.doctors:
            if other_doctor.role != doctor.role:
                continue
            if other_doctor.name == doctor.name:
                continue
            
            # 放寬條件檢查
            if shift_date not in other_doctor.unavailable_dates:
                slot = self.schedule[shift_date]
                if other_doctor.name not in [slot.attending, slot.resident]:
                    step2 = SwapStep(
                        description=f"[強制] {other_doctor.name} 接手 {shift_date}",
                        from_date="",
                        to_date=shift_date,
                        doctor=other_doctor.name,
                        role=shift_role,
                        impact_score=10.0
                    )
                    
                    return SwapChain(
                        steps=[step1, step2],
                        total_score=self._evaluate_chain([step1, step2]),
                        feasible=True,
                        validation_message="強制交換方案",
                        complexity=2
                    )
        
        return None
    
    def _try_multi_doctor_swap(self, gap: GapInfo, max_depth: int) -> List[SwapChain]:
        """嘗試多醫師聯合交換"""
        chains = []
        
        if len(gap.candidates_over_quota) < 2:
            return chains
        
        # 取前兩個醫師
        doctor1_name = gap.candidates_over_quota[0]
        doctor2_name = gap.candidates_over_quota[1]
        
        doctor1 = self.doctor_map[doctor1_name]
        doctor2 = self.doctor_map[doctor2_name]
        
        # 找出兩個醫師的可交換班次
        shifts1 = self._find_removable_shifts(doctor1, gap)
        shifts2 = self._find_removable_shifts(doctor2, gap)
        
        if shifts1 and shifts2:
            # 嘗試創建聯合交換鏈
            steps = [
                SwapStep(
                    description=f"{doctor1_name} 從 {shifts1[0][0]} 移至 {gap.date}",
                    from_date=shifts1[0][0],
                    to_date=gap.date,
                    doctor=doctor1_name,
                    role=gap.role,
                    impact_score=8.0
                ),
                SwapStep(
                    description=f"{doctor2_name} 接手 {shifts1[0][0]}",
                    from_date=shifts2[0][0],
                    to_date=shifts1[0][0],
                    doctor=doctor2_name,
                    role=shifts1[0][1],
                    impact_score=8.0
                )
            ]
            
            chain = SwapChain(
                steps=steps,
                total_score=self._evaluate_chain(steps),
                feasible=True,
                validation_message="多醫師聯合交換",
                complexity=len(steps)
            )
            
            chains.append(chain)
        
        return chains
    
    def _calculate_step_impact(self, from_date: str, to_date: str) -> float:
        """計算單步交換的影響分數"""
        impact = 5.0
        
        # 如果跨類型（假日換平日），增加影響
        from_is_holiday = from_date in self.holidays
        to_is_holiday = to_date in self.holidays
        
        if from_is_holiday != to_is_holiday:
            impact += 10.0
        
        return impact
    
    def _evaluate_chain(self, steps: List[SwapStep]) -> float:
        """評估交換鏈的品質"""
        score = 100.0
        
        # 步數懲罰
        score -= len(steps) * 5
        
        # 每步影響累計
        for step in steps:
            score -= step.impact_score
        
        # 模擬執行並檢查違規
        temp_schedule = self._simulate_chain(steps)
        violations = self._count_violations(temp_schedule)
        score -= violations * 20
        
        return max(0, score)
    
    def _simulate_chain(self, steps: List[SwapStep]) -> Dict[str, ScheduleSlot]:
        """模擬執行交換鏈"""
        temp_schedule = copy.deepcopy(self.schedule)
        
        for step in steps:
            if step.from_date:
                slot = temp_schedule[step.from_date]
                if step.role == "主治":
                    slot.attending = None
                else:
                    slot.resident = None
            
            if step.to_date:
                slot = temp_schedule[step.to_date]
                if step.role == "主治":
                    slot.attending = step.doctor
                else:
                    slot.resident = step.doctor
        
        return temp_schedule
    
    def _count_violations(self, schedule: Dict[str, ScheduleSlot]) -> int:
        """計算排班違規數"""
        violations = 0
        
        # 重新計算班數
        duties = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            
            if slot.attending:
                if is_holiday:
                    duties[slot.attending]['holiday'] += 1
                else:
                    duties[slot.attending]['weekday'] += 1
            
            if slot.resident:
                if is_holiday:
                    duties[slot.resident]['holiday'] += 1
                else:
                    duties[slot.resident]['weekday'] += 1
        
        # 檢查配額違規
        for doctor in self.doctors:
            if duties[doctor.name]['weekday'] > doctor.weekday_quota:
                violations += 1
            if duties[doctor.name]['holiday'] > doctor.holiday_quota:
                violations += 1
        
        return violations
    
    def _generate_state_signature(self, chain: SwapChain) -> str:
        """生成狀態簽名用於去重"""
        sig_parts = []
        for step in chain.steps:
            sig_parts.append(f"{step.doctor}:{step.from_date}→{step.to_date}")
        return "|".join(sorted(sig_parts))
    
    def _deduplicate_chains(self, chains: List[SwapChain]) -> List[SwapChain]:
        """去除重複的交換鏈"""
        seen = set()
        unique_chains = []
        
        for chain in chains:
            sig = self._generate_state_signature(chain)
            if sig not in seen:
                seen.add(sig)
                unique_chains.append(chain)
        
        return unique_chains
    
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
            self._log("❌ 交換鏈不可行，無法應用", "error", force=True)
            return False
        
        try:
            # 保存當前狀態（用於回溯）
            self._save_state()
            
            self._log(f"🔄 應用交換鏈：{len(chain.steps)} 步", "info")
            
            # 執行每個步驟
            for i, step in enumerate(chain.steps):
                if self.log_level == 'verbose':
                    self._log(f"   步驟 {i+1}: {step.description}", "info")
                
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
            
            self._log("✅ 交換鏈應用成功", "success")
            return True
            
        except Exception as e:
            self._log(f"❌ 應用交換鏈失敗：{str(e)}", "error", force=True)
            self._restore_state()
            return False
    
    def run_auto_fill_with_backtracking(self, max_backtracks: int = 20) -> Dict:
        """執行自動填補（含回溯）"""
        # 設定日誌級別為正常模式
        self.set_log_level('normal')
        
        self._log("🚀 開始自動填補流程...", "info", force=True)
        self._log(f"   📊 初始狀態：{len(self.gaps)} 個空缺待處理", "info", force=True)
        self._log(f"   ⚙️ 參數設定：最大回溯次數 = {max_backtracks:,}", "info", force=True)
        
        results = {
            'direct_fills': [],
            'swap_chains': [],
            'backtracks': [],
            'remaining_gaps': []
        }
        
        backtrack_count = 0
        iteration = 0
        start_time = time.time()
        last_progress_report = 0
        progress_report_interval = 10  # 每10輪報告一次
        
        while self.gaps and backtrack_count < max_backtracks:
            iteration += 1
            
            # 定期報告進度
            if iteration - last_progress_report >= progress_report_interval:
                elapsed = time.time() - start_time
                self._log(f"\n📈 進度報告：第 {iteration} 輪，剩餘 {len(self.gaps)} 個空缺，"
                         f"已耗時 {elapsed:.1f} 秒", "info", force=True)
                last_progress_report = iteration
            
            progress_made = False
            
            # 第一階段：直接填補（B類醫師）
            for gap in self.gaps[:]:
                if gap.candidates_with_quota:
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
            
            # 第二階段：深度5交換鏈（A類醫師）
            for gap in self.gaps[:]:
                if gap.candidates_over_quota and not gap.candidates_with_quota:
                    chains = self.find_deep_swap_chains(gap, max_depth=5)
                    
                    if chains:
                        # 應用最佳交換鏈
                        if self.apply_swap_chain(chains[0]):
                            results['swap_chains'].append({
                                'gap': f"{gap.date} {gap.role}",
                                'chain': [step.description for step in chains[0].steps]
                            })
                            progress_made = True
                            break
            
            if not progress_made:
                # 檢測死路
                if backtrack_count < max_backtracks:
                    backtrack_count += 1
                    
                    # 只在重要時刻輸出回溯資訊
                    if backtrack_count == 1 or backtrack_count % 10 == 0 or backtrack_count == max_backtracks:
                        self._log(f"🔙 執行回溯 ({backtrack_count}/{max_backtracks})", "warning", force=True)
                    
                    if self._backtrack():
                        results['backtracks'].append({
                            'iteration': iteration,
                            'reason': '無進展，嘗試回溯'
                        })
                    else:
                        self._log("⚠️ 無法回溯，停止處理", "warning", force=True)
                        break
                else:
                    self._log("❌ 達到最大回溯次數，停止處理", "error", force=True)
                    break
        
        # 記錄剩餘空缺
        for gap in self.gaps:
            results['remaining_gaps'].append({
                'date': gap.date,
                'role': gap.role,
                'reason': self._get_gap_reason(gap)
            })
        
        elapsed_time = time.time() - start_time
        
        # 輸出最終統計
        self._log(f"\n✅ 自動填補完成！總耗時：{elapsed_time:.2f} 秒", "success", force=True)
        self._log(f"📊 成果統計：", "info", force=True)
        self._log(f"   - 直接填補：{len(results['direct_fills'])} 個", "info", force=True)
        self._log(f"   - 交換解決：{len(results['swap_chains'])} 個", "info", force=True)
        self._log(f"   - 回溯次數：{backtrack_count}", "info", force=True)
        self._log(f"   - 剩餘空缺：{len(results['remaining_gaps'])} 個", 
                 "warning" if results['remaining_gaps'] else "info", force=True)
        
        return results
    
    def _select_best_candidate(self, candidates: List[str], gap: GapInfo) -> str:
        """選擇最適合的候選人"""
        # 選擇班數最少的
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
        self.state_history.append(f"狀態保存於 {datetime.now().strftime('%H:%M:%S')}")
    
    def _restore_state(self):
        """恢復上一個狀態"""
        if self.backtrack_stack:
            state = self.backtrack_stack.pop()
            self.schedule = state.schedule
            self.current_duties = state.current_duties
            self.gaps = state.gaps
            self.applied_swaps = state.applied_swaps
            self.state_history.append(f"狀態恢復於 {datetime.now().strftime('%H:%M:%S')}")
    
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
            'state_history': len(self.state_history),
            'search_stats': self.search_stats
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
    
    def get_gap_details_for_calendar(self) -> Dict:
        """為日曆視圖生成詳細的空缺資訊"""
        gap_details = {}
        
        for gap in self.gaps:
            if gap.date not in gap_details:
                gap_details[gap.date] = {}
            
            # 可直接安排的醫師（有配額餘額）
            available_doctors = gap.candidates_with_quota
            
            # 需要調整的醫師（超額但可交換）
            restricted_doctors = []
            for doctor_name in gap.candidates_over_quota:
                doctor = self.doctor_map[doctor_name]
                reason = self._get_restriction_reason(doctor, gap.date, gap.role)
                restricted_doctors.append({
                    "name": doctor_name,
                    "reason": reason
                })
            
            # 統計完全不可用的醫師數量
            unavailable_count = 0
            for doctor in self.doctors:
                if doctor.role != gap.role:
                    continue
                if doctor.name not in gap.candidates_with_quota and \
                   doctor.name not in gap.candidates_over_quota:
                    unavailable_count += 1
            
            gap_details[gap.date][gap.role] = {
                "available_doctors": available_doctors,
                "restricted_doctors": restricted_doctors,
                "unavailable_count": unavailable_count,
                "priority": gap.priority_score,
                "severity": gap.severity
            }
        
        return gap_details

    def _get_restriction_reason(self, doctor: Doctor, date: str, role: str) -> str:
        """取得醫師不能直接排班的原因"""
        reasons = []
        
        # 檢查配額
        current = self.current_duties[doctor.name]
        is_holiday = date in self.holidays
        
        if is_holiday:
            if current['holiday'] >= doctor.holiday_quota:
                reasons.append(f"假日配額已滿({current['holiday']}/{doctor.holiday_quota})")
        else:
            if current['weekday'] >= doctor.weekday_quota:
                reasons.append(f"平日配額已滿({current['weekday']}/{doctor.weekday_quota})")
        
        # 檢查連續值班
        if self._would_violate_consecutive(doctor.name, date):
            reasons.append(f"超過連續值班上限({self.constraints.max_consecutive_days}天)")
        
        # 檢查不可值班日
        if date in doctor.unavailable_dates:
            reasons.append("不可值班日")
        
        # 檢查是否已在同一天有班
        slot = self.schedule.get(date)
        if slot and doctor.name in [slot.attending, slot.resident]:
            reasons.append("同日已有其他班次")
        
        return " / ".join(reasons) if reasons else "未知原因"

    def _would_violate_consecutive(self, doctor_name: str, date: str) -> bool:
        """檢查是否會違反連續值班限制"""
        return check_consecutive_days(
            self.schedule, doctor_name, date, 
            self.constraints.max_consecutive_days
        )