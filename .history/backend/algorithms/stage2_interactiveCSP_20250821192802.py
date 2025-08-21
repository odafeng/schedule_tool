"""
Stage 2: 互動式補洞
"""
import streamlit as st
import copy
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

from backend.models import Doctor, ScheduleSlot
from backend.algorithms.csp_solver import CSPVariable, CSPConstraint, AdvancedCSPSolver
from backend.utils import check_consecutive_days

@dataclass
class GapInfo:
    """未填格資訊"""
    date: str
    role: str
    is_holiday: bool
    is_weekend: bool
    candidates: List[str]
    severity: float  # 嚴重度（越高越嚴重）
    
@dataclass
class CandidateInfo:
    """候選人資訊"""
    name: str
    score_delta: float  # 選擇此人對總分的影響
    feasibility: float  # 可行性（0-1）
    pros: List[str]  # 優點
    cons: List[str]  # 缺點
    
@dataclass
class SwapSuggestion:
    """交換建議"""
    date1: str
    role1: str
    doctor1: str
    date2: str
    role2: str
    doctor2: str
    score_improvement: float
    description: str

class Stage2InteractiveFiller:
    """Stage 2: 互動式補洞器"""
    
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
        
        # 分析未填格
        self.gaps = self._analyze_gaps()
    
    def _analyze_gaps(self) -> List[GapInfo]:
        """分析所有未填格"""
        gaps = []
        
        for date_str, slot in self.schedule.items():
            # 檢查主治醫師空缺
            if not slot.attending:
                gap = self._create_gap_info(date_str, "主治")
                gaps.append(gap)
            
            # 檢查總醫師空缺
            if not slot.resident:
                gap = self._create_gap_info(date_str, "總醫師")
                gaps.append(gap)
        
        # 按嚴重度排序
        gaps.sort(key=lambda x: x.severity, reverse=True)
        return gaps
    
    def _create_gap_info(self, date: str, role: str) -> GapInfo:
        """創建未填格資訊"""
        from datetime import datetime
        
        # 基本資訊
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        is_holiday = date in self.holidays
        is_weekend = date_obj.weekday() >= 5
        
        # 取得候選人
        candidates = self._get_candidates(date, role)
        
        # 計算嚴重度
        severity = 0.0
        
        # 候選人越少越嚴重
        if len(candidates) == 0:
            severity += 100
        elif len(candidates) == 1:
            severity += 50
        elif len(candidates) == 2:
            severity += 30
        else:
            severity += 10 / len(candidates)
        
        # 假日和週末更嚴重
        if is_holiday:
            severity += 20
        if is_weekend:
            severity += 10
        
        # 主治醫師比總醫師重要
        if role == "主治":
            severity += 5
        
        return GapInfo(
            date=date,
            role=role,
            is_holiday=is_holiday,
            is_weekend=is_weekend,
            candidates=candidates,
            severity=severity
        )
    
    def _get_candidates(self, date: str, role: str) -> List[str]:
        """取得某個位置的候選人"""
        candidates = []
        doctors = [d for d in self.doctors if d.role == role]
        
        for doctor in doctors:
            if self._check_feasibility(doctor, date):
                candidates.append(doctor.name)
        
        return candidates
    
    def _check_feasibility(self, doctor: Doctor, date: str) -> bool:
        """檢查醫師是否可以排在某天"""
        # 1. 不可值班日
        if date in doctor.unavailable_dates:
            return False
        
        # 2. 配額檢查
        used = self._count_doctor_duties(doctor.name)
        is_holiday = date in self.holidays
        
        if is_holiday:
            if used['holiday'] >= doctor.holiday_quota:
                return False
        else:
            if used['weekday'] >= doctor.weekday_quota:
                return False
        
        # 3. 連續值班檢查
        if check_consecutive_days(self.schedule, doctor.name, date,
                                 self.constraints.max_consecutive_days):
            return False
        
        # 4. 同一天不能擔任兩個角色
        slot = self.schedule[date]
        if slot.attending == doctor.name or slot.resident == doctor.name:
            return False
        
        return True
    
    def _count_doctor_duties(self, doctor_name: str) -> Dict:
        """計算醫師已值班次數"""
        counts = {'weekday': 0, 'holiday': 0}
        
        for date_str, slot in self.schedule.items():
            if slot.attending == doctor_name or slot.resident == doctor_name:
                if date_str in self.holidays:
                    counts['holiday'] += 1
                else:
                    counts['weekday'] += 1
        
        return counts
    
    def get_candidate_details(self, date: str, role: str) -> List[CandidateInfo]:
        """取得候選人詳細資訊"""
        candidates_info = []
        
        candidates = self._get_candidates(date, role)
        
        for doctor_name in candidates:
            doctor = self.doctor_map[doctor_name]
            
            # 計算選擇此人的影響
            score_delta = self._calculate_score_delta(date, role, doctor_name)
            
            # 計算可行性
            feasibility = self._calculate_feasibility(doctor, date)
            
            # 分析優缺點
            pros, cons = self._analyze_pros_cons(doctor, date)
            
            candidates_info.append(CandidateInfo(
                name=doctor_name,
                score_delta=score_delta,
                feasibility=feasibility,
                pros=pros,
                cons=cons
            ))
        
        # 按分數影響排序
        candidates_info.sort(key=lambda x: x.score_delta, reverse=True)
        
        return candidates_info
    
    def _calculate_score_delta(self, date: str, role: str, doctor_name: str) -> float:
        """計算選擇某醫師對分數的影響"""
        # 簡化版本：主要考慮填充和偏好
        score_delta = 100  # 基礎填充分
        
        doctor = self.doctor_map[doctor_name]
        
        # 偏好日期加分
        if date in doctor.preferred_dates:
            score_delta += 20
        
        # 配額使用均衡性
        used = self._count_doctor_duties(doctor_name)
        is_holiday = date in self.holidays
        
        if is_holiday:
            usage_rate = used['holiday'] / max(doctor.holiday_quota, 1)
        else:
            usage_rate = used['weekday'] / max(doctor.weekday_quota, 1)
        
        # 使用率越低越好（促進均衡）
        score_delta += (1 - usage_rate) * 10
        
        return score_delta
    
    def _calculate_feasibility(self, doctor: Doctor, date: str) -> float:
        """計算可行性分數（0-1）"""
        feasibility = 1.0
        
        # 檢查各項約束
        used = self._count_doctor_duties(doctor.name)
        is_holiday = date in self.holidays
        
        # 配額餘量
        if is_holiday:
            remaining = doctor.holiday_quota - used['holiday']
            feasibility *= min(remaining / max(doctor.holiday_quota, 1), 1.0)
        else:
            remaining = doctor.weekday_quota - used['weekday']
            feasibility *= min(remaining / max(doctor.weekday_quota, 1), 1.0)
        
        # 連續值班風險
        from datetime import datetime, timedelta
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        
        consecutive_risk = 0
        for i in range(-2, 3):
            check_date = (date_obj + timedelta(days=i)).strftime("%Y-%m-%d")
            if check_date in self.schedule and check_date != date:
                slot = self.schedule[check_date]
                if doctor.name in [slot.attending, slot.resident]:
                    consecutive_risk += 0.2
        
        feasibility *= max(0, 1 - consecutive_risk)
        
        return feasibility
    
    def _analyze_pros_cons(self, doctor: Doctor, date: str) -> Tuple[List[str], List[str]]:
        """分析選擇某醫師的優缺點"""
        pros = []
        cons = []
        
        # 優點
        if date in doctor.preferred_dates:
            pros.append("偏好值班日")
        
        used = self._count_doctor_duties(doctor.name)
        total_used = used['weekday'] + used['holiday']
        total_quota = doctor.weekday_quota + doctor.holiday_quota
        
        if total_used < total_quota * 0.5:
            pros.append("值班次數較少")
        
        # 缺點
        from datetime import datetime, timedelta
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        
        # 檢查前後是否有值班
        for i in [-1, 1]:
            check_date = (date_obj + timedelta(days=i)).strftime("%Y-%m-%d")
            if check_date in self.schedule:
                slot = self.schedule[check_date]
                if doctor.name in [slot.attending, slot.resident]:
                    if i == -1:
                        cons.append("前一天有值班")
                    else:
                        cons.append("後一天有值班")
        
        is_holiday = date in self.holidays
        if is_holiday:
            if used['holiday'] >= doctor.holiday_quota * 0.8:
                cons.append("假日配額將近用完")
        else:
            if used['weekday'] >= doctor.weekday_quota * 0.8:
                cons.append("平日配額將近用完")
        
        return pros, cons
    
    def apply_csp_local(self, date: str, role: str, 
                       neighborhood_size: int = 3) -> Optional[Dict]:
        """
        對局部區域應用 CSP 求解
        
        Args:
            date: 目標日期
            role: 目標角色
            neighborhood_size: 鄰域大小（前後幾天）
            
        Returns:
            CSP 解或 None
        """
        from datetime import datetime, timedelta
        
        # 收集鄰域內的未填格
        target_date = datetime.strptime(date, "%Y-%m-%d")
        variables = []
        
        for i in range(-neighborhood_size, neighborhood_size + 1):
            check_date = (target_date + timedelta(days=i)).strftime("%Y-%m-%d")
            
            if check_date in self.schedule:
                slot = self.schedule[check_date]
                
                # 檢查主治醫師
                if not slot.attending:
                    var = CSPVariable(check_date, "主治")
                    var.domain = self._get_candidates(check_date, "主治")
                    if var.domain:  # 只加入有候選人的變數
                        variables.append(var)
                
                # 檢查總醫師
                if not slot.resident:
                    var = CSPVariable(check_date, "總醫師")
                    var.domain = self._get_candidates(check_date, "總醫師")
                    if var.domain:
                        variables.append(var)
        
        if not variables:
            return None
        
        # 建立約束
        constraints = self._build_csp_constraints(variables)
        
        # 求解
        solver = AdvancedCSPSolver(variables, constraints, use_ac3=True, use_backjump=True)
        solution = solver.solve(timeout=5)  # 5秒超時
        
        return solution
    
    def _build_csp_constraints(self, variables: List[CSPVariable]) -> List[CSPConstraint]:
        """建立 CSP 約束"""
        constraints = []
        
        # 1. 同一天不同角色不能是同一人
        dates = set(v.date for v in variables)
        for date_str in dates:
            date_vars = [v for v in variables if v.date == date_str]
            if len(date_vars) > 1:
                def same_day_constraint(assignment, vars=date_vars):
                    values = [assignment.get(v) for v in vars if v in assignment]
                    return len(values) == len(set(values))
                constraints.append(CSPConstraint(date_vars, same_day_constraint))
        
        # 2. 配額約束
        def quota_constraint(assignment):
            duty_counts = defaultdict(lambda: {'weekday': 0, 'holiday': 0})
            
            # 計算現有排班
            for d, slot in self.schedule.items():
                is_holiday = d in self.holidays
                quota_type = 'holiday' if is_holiday else 'weekday'
                
                if slot.attending:
                    duty_counts[slot.attending][quota_type] += 1
                if slot.resident:
                    duty_counts[slot.resident][quota_type] += 1
            
            # 加上 CSP 賦值
            for var, doctor_name in assignment.items():
                is_holiday = var.date in self.holidays
                quota_type = 'holiday' if is_holiday else 'weekday'
                duty_counts[doctor_name][quota_type] += 1
            
            # 檢查是否超過配額
            for doctor_name, counts in duty_counts.items():
                if doctor_name in self.doctor_map:
                    doctor = self.doctor_map[doctor_name]
                    if counts['weekday'] > doctor.weekday_quota:
                        return False
                    if counts['holiday'] > doctor.holiday_quota:
                        return False
            
            return True
        
        constraints.append(CSPConstraint(variables, quota_constraint))
        
        return constraints
    
    def get_swap_suggestions(self, max_suggestions: int = 3) -> List[SwapSuggestion]:
        """取得交換建議"""
        suggestions = []
        
        # 找出所有已填和未填的位置
        filled_slots = []
        unfilled_slots = []
        
        for date_str, slot in self.schedule.items():
            if slot.attending:
                filled_slots.append((date_str, "主治", slot.attending))
            else:
                unfilled_slots.append((date_str, "主治"))
            
            if slot.resident:
                filled_slots.append((date_str, "總醫師", slot.resident))
            else:
                unfilled_slots.append((date_str, "總醫師"))
        
        # 嘗試找出有益的交換
        for date1, role1 in unfilled_slots[:10]:  # 只檢查前10個重要空格
            for date2, role2, doctor2 in filled_slots:
                # 檢查交換是否可行
                if self._check_swap_feasible(date1, role1, doctor2, date2, role2):
                    score_improvement = self._calculate_swap_improvement(
                        date1, role1, doctor2, date2, role2
                    )
                    
                    if score_improvement > 0:
                        suggestions.append(SwapSuggestion(
                            date1=date1,
                            role1=role1,
                            doctor1="(空)",
                            date2=date2,
                            role2=role2,
                            doctor2=doctor2,
                            score_improvement=score_improvement,
                            description=f"將 {doctor2} 從 {date2} 移至 {date1}"
                        ))
        
        # 排序並返回最佳建議
        suggestions.sort(key=lambda x: x.score_improvement, reverse=True)
        return suggestions[:max_suggestions]
    
    def _check_swap_feasible(self, date1: str, role1: str, 
                            doctor_name: str, date2: str, role2: str) -> bool:
        """檢查交換是否可行"""
        if role1 != role2:  # 只能同角色交換
            return False
        
        doctor = self.doctor_map.get(doctor_name)
        if not doctor:
            return False
        
        # 檢查新位置的可行性
        return self._check_feasibility(doctor, date1)
    
    def _calculate_swap_improvement(self, date1: str, role1: str,
                                   doctor_name: str, date2: str, role2: str) -> float:
        """計算交換帶來的分數改善"""
        # 簡化計算：主要考慮填充空格的收益
        improvement = 100  # 填充一個空格的基礎分
        
        doctor = self.doctor_map[doctor_name]
        
        # 如果新位置是偏好日期，加分
        if date1 in doctor.preferred_dates:
            improvement += 20
        
        # 如果原位置不是偏好日期，移走不扣分
        if date2 not in doctor.preferred_dates:
            improvement += 10
        
        return improvement
    
    def apply_assignment(self, date: str, role: str, doctor_name: str) -> bool:
        """應用一個賦值"""
        try:
            if role == "主治":
                self.schedule[date].attending = doctor_name
            else:
                self.schedule[date].resident = doctor_name
            
            # 重新分析未填格
            self.gaps = self._analyze_gaps()
            
            return True
        except Exception as e:
            st.error(f"賦值失敗：{str(e)}")
            return False
    
    def get_completion_status(self) -> Dict:
        """取得完成狀態"""
        total_slots = len(self.schedule) * 2
        filled_slots = total_slots - len(self.gaps)
        
        return {
            'total_slots': total_slots,
            'filled_slots': filled_slots,
            'unfilled_slots': len(self.gaps),
            'fill_rate': filled_slots / total_slots if total_slots > 0 else 0,
            'is_complete': len(self.gaps) == 0,
            'critical_gaps': [g for g in self.gaps if g.severity > 50]
        }