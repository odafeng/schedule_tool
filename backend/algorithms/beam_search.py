"""
束搜索排班演算法
"""
import copy
import streamlit as st
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict
import numpy as np

from ..models import Doctor, ScheduleSlot, ScheduleResult, ScheduleConstraints
from ..utils import check_consecutive_days
from ..analyzers import ScheduleScorer
from ..ml import SolutionPoolManager
from .csp_solver import CSPVariable, CSPConstraint, AdvancedCSPSolver
from .heuristics import get_available_doctors

class BeamSearchScheduler:
    """束搜索排班器（含解池收集）"""
    
    def __init__(self, doctors: List[Doctor], constraints: ScheduleConstraints,
                 weekdays: List[str], holidays: List[str]):
        self.doctors = doctors
        self.constraints = constraints
        self.weekdays = weekdays
        self.holidays = holidays
        self.attending_doctors = [d for d in doctors if d.role == "主治"]
        self.resident_doctors = [d for d in doctors if d.role == "住院"]
        
        # 建立醫師索引
        self.doctor_map = {d.name: d for d in doctors}
        
        # 初始化解池管理器
        self.solution_pool = SolutionPoolManager()
        
        # 初始化評分器
        self.scorer = ScheduleScorer(doctors, weekdays, holidays)
        
    def run(self, progress_callback: Callable = None, 
            collect_all_solutions: bool = True) -> ScheduleResult:
        """
        執行束搜索排班
        
        Args:
            progress_callback: 進度回調函數
            collect_all_solutions: 是否收集所有探索過的解
        """
        # 初始化排班表
        initial_schedule = {}
        for date_str in self.weekdays + self.holidays:
            initial_schedule[date_str] = ScheduleSlot(date=date_str)
        
        # 束搜索
        beam = [(0, initial_schedule, None)]  # (score, schedule, parent_id)
        all_dates = self.holidays + self.weekdays  # 假日優先
        
        total_steps = len(all_dates) * 2  # 每天要排兩個角色
        current_step = 0
        iteration = 0
        
        for date_str in all_dates:
            iteration += 1
            
            # 排主治醫師
            new_beam = []
            for score, schedule, parent_id in beam:
                available = get_available_doctors(
                    date_str, "主治", schedule, 
                    self.doctor_map, self.constraints, 
                    self.weekdays, self.holidays
                )
                
                if not available:
                    # 保持未填
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        sol_id = self._add_to_pool(
                            schedule, score, iteration, parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    # 嘗試每個可用醫師
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].attending = doc_name
                        new_score = self.scorer.calculate_score(new_schedule)
                        
                        if collect_all_solutions:
                            sol_id = self._add_to_pool(
                                new_schedule, new_score, iteration, parent_id
                            )
                            new_beam.append((new_score, new_schedule, sol_id))
                        else:
                            new_beam.append((new_score, new_schedule, parent_id))
            
            # 保留Top-K
            new_beam.sort(key=lambda x: x[0], reverse=True)
            beam = new_beam[:self.constraints.beam_width]
            
            current_step += 1
            if progress_callback:
                progress_callback(current_step / total_steps)
            
            # 排住院醫師
            iteration += 1
            new_beam = []
            for score, schedule, parent_id in beam:
                available = get_available_doctors(
                    date_str, "住院", schedule,
                    self.doctor_map, self.constraints,
                    self.weekdays, self.holidays
                )
                
                if not available:
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        sol_id = self._add_to_pool(
                            schedule, score, iteration, parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].resident = doc_name
                        new_score = self.scorer.calculate_score(new_schedule)
                        
                        if collect_all_solutions:
                            sol_id = self._add_to_pool(
                                new_schedule, new_score, iteration, parent_id
                            )
                            new_beam.append((new_score, new_schedule, sol_id))
                        else:
                            new_beam.append((new_score, new_schedule, parent_id))
            
            new_beam.sort(key=lambda x: x[0], reverse=True)
            beam = new_beam[:self.constraints.beam_width]
            
            current_step += 1
            if progress_callback:
                progress_callback(current_step / total_steps)
        
        # 返回最佳結果
        best_score, best_schedule, best_id = beam[0] if beam else (-float('inf'), initial_schedule, None)
        
        # CSP補洞
        best_schedule = self.csp_fill_gaps(best_schedule)
        
        # 將CSP改進後的解也加入解池
        if collect_all_solutions:
            final_score = self.scorer.calculate_score(best_schedule)
            self._add_to_pool(
                best_schedule, final_score, iteration + 1, best_id,
                generation_method="csp_enhanced"
            )
        
        return self.create_result(best_schedule)
    
    def _add_to_pool(self, schedule: Dict[str, ScheduleSlot], score: float,
                    iteration: int, parent_id: Optional[str],
                    generation_method: str = "beam_search") -> str:
        """添加解到解池"""
        return self.solution_pool.add_solution(
            schedule, score, iteration,
            self.doctors, self.constraints,
            self.weekdays, self.holidays,
            generation_method=generation_method,
            parent_id=parent_id
        )
    
    def csp_fill_gaps(self, schedule: Dict[str, ScheduleSlot]) -> Dict[str, ScheduleSlot]:
        """使用進階CSP求解器填補未填格"""
        # 收集未填格
        unfilled = []
        for date_str, slot in schedule.items():
            if not slot.attending:
                unfilled.append((date_str, "主治"))
            if not slot.resident:
                unfilled.append((date_str, "住院"))
        
        if not unfilled:
            return schedule
        
        # 建立CSP變數
        variables = []
        var_map = {}
        
        for date_str, role in unfilled:
            var = CSPVariable(date_str, role)
            var.domain = get_available_doctors(
                date_str, role, schedule,
                self.doctor_map, self.constraints,
                self.weekdays, self.holidays
            )
            variables.append(var)
            var_map[(date_str, role)] = var
        
        # 建立約束
        constraints = self._build_csp_constraints(variables, schedule)
        
        # 使用進階CSP求解器
        solver = AdvancedCSPSolver(variables, constraints)
        solution = solver.solve(timeout=self.constraints.csp_timeout)
        
        # 將解套用到排班表
        best_schedule = copy.deepcopy(schedule)
        if solution:
            for var, doctor_name in solution.items():
                if var.role == "主治":
                    best_schedule[var.date].attending = doctor_name
                else:
                    best_schedule[var.date].resident = doctor_name
            
            # 記錄CSP求解統計
            if hasattr(st, 'session_state'):
                st.session_state.csp_stats = {
                    'solved': True,
                    'nodes_explored': solver.nodes_explored,
                    'unfilled_before': len(unfilled),
                    'unfilled_after': sum(1 for d, s in best_schedule.items() 
                                        if not s.attending or not s.resident)
                }
        else:
            # CSP無解，使用啟發式填補
            if hasattr(st, 'session_state'):
                st.session_state.csp_stats = {
                    'solved': False,
                    'nodes_explored': solver.nodes_explored,
                    'unfilled_before': len(unfilled),
                    'unfilled_after': len(unfilled)
                }
            
            # 至少嘗試填一些明顯可以填的
            best_schedule = self._heuristic_fill(best_schedule, unfilled)
        
        return best_schedule
    
    def _build_csp_constraints(self, variables: List[CSPVariable],
                              schedule: Dict[str, ScheduleSlot]) -> List[CSPConstraint]:
        """建立CSP約束"""
        constraints = []
        
        # 約束1: 同一天同一人不能擔任兩個角色
        for date_str in set([v.date for v in variables]):
            date_vars = [v for v in variables if v.date == date_str]
            if len(date_vars) > 1:
                def same_day_constraint(assignment, date_vars=date_vars):
                    assigned_values = []
                    for var in date_vars:
                        if var in assignment:
                            assigned_values.append(assignment[var])
                    return len(assigned_values) == len(set(assigned_values))
                
                constraints.append(CSPConstraint(date_vars, same_day_constraint))
        
        # 約束2: 連續值班限制
        for var in variables:
            def consecutive_constraint(assignment, var=var):
                if var not in assignment:
                    return True
                doctor_name = assignment[var]
                # 簡化檢查邏輯
                return not check_consecutive_days(
                    schedule, doctor_name, var.date, 
                    self.constraints.max_consecutive_days
                )
            constraints.append(CSPConstraint([var], consecutive_constraint))
        
        # 約束3: 配額限制
        def quota_constraint(assignment):
            weekday_counts = defaultdict(int)
            holiday_counts = defaultdict(int)
            
            # 統計已排班的
            for d, slot in schedule.items():
                if slot.attending:
                    if d in self.holidays:
                        holiday_counts[slot.attending] += 1
                    else:
                        weekday_counts[slot.attending] += 1
                if slot.resident:
                    if d in self.holidays:
                        holiday_counts[slot.resident] += 1
                    else:
                        weekday_counts[slot.resident] += 1
            
            # 統計CSP賦值的
            for var, doctor_name in assignment.items():
                if var.date in self.holidays:
                    holiday_counts[doctor_name] += 1
                else:
                    weekday_counts[doctor_name] += 1
            
            # 檢查配額
            for name, doc in self.doctor_map.items():
                if weekday_counts[name] > doc.weekday_quota:
                    return False
                if holiday_counts[name] > doc.holiday_quota:
                    return False
            
            return True
        
        constraints.append(CSPConstraint(variables, quota_constraint))
        
        return constraints
    
    def _heuristic_fill(self, schedule: Dict[str, ScheduleSlot],
                       unfilled: List[Tuple[str, str]]) -> Dict[str, ScheduleSlot]:
        """啟發式填補未填格"""
        best_schedule = copy.deepcopy(schedule)
        
        for date_str, role in unfilled:
            available = get_available_doctors(
                date_str, role, best_schedule,
                self.doctor_map, self.constraints,
                self.weekdays, self.holidays
            )
            
            if available:
                # 選擇負擔最輕的醫師
                duty_counts = defaultdict(int)
                for d, slot in best_schedule.items():
                    if slot.attending:
                        duty_counts[slot.attending] += 1
                    if slot.resident:
                        duty_counts[slot.resident] += 1
                
                available.sort(key=lambda x: duty_counts[x])
                
                if role == "主治":
                    best_schedule[date_str].attending = available[0]
                else:
                    best_schedule[date_str].resident = available[0]
        
        return best_schedule
    
    def create_result(self, schedule: Dict[str, ScheduleSlot]) -> ScheduleResult:
        """創建排班結果"""
        score = self.scorer.calculate_score(schedule)
        stats = self.scorer.get_statistics(schedule)
        
        # 找出未填格
        unfilled = []
        for date_str, slot in schedule.items():
            if not slot.attending:
                unfilled.append((date_str, "主治"))
            if not slot.resident:
                unfilled.append((date_str, "住院"))
        
        # 生成建議
        suggestions = []
        if unfilled:
            suggestions.append(f"共有 {len(unfilled)} 個未填格位")
            for date_str, role in unfilled[:5]:  # 顯示前5個
                available = get_available_doctors(
                    date_str, role, schedule,
                    self.doctor_map, self.constraints,
                    self.weekdays, self.holidays
                )
                if available:
                    suggestions.append(f"{date_str} {role}可選: {', '.join(available)}")
                else:
                    suggestions.append(f"{date_str} {role}: 無可用醫師")
        
        return ScheduleResult(
            schedule=schedule,
            score=score,
            unfilled_slots=unfilled,
            violations={},
            suggestions=suggestions,
            statistics=stats
        )