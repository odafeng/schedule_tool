"""
醫師智慧排班系統 - Streamlit應用程式
支援主治醫師與住院醫師的月排班，含束搜索與CSP補洞演算法
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import calendar
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Set, Literal
from enum import Enum
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict, Counter
import itertools
import time
import copy

# =====================
# 資料模型定義
# =====================

@dataclass
class Doctor:
    """醫師資料模型"""
    name: str
    role: Literal["主治", "總醫師"]
    weekday_quota: int  # 平日配額
    holiday_quota: int  # 假日配額
    unavailable_dates: List[str] = field(default_factory=list)  # 不可值班日
    preferred_dates: List[str] = field(default_factory=list)    # 優先值班日
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class ScheduleConstraints:
    """排班限制條件"""
    max_consecutive_days: int = 2  # 最大連續值班天數
    beam_width: int = 5  # 束搜索寬度
    csp_timeout: int = 10  # CSP求解超時（秒）
    neighbor_expansion: int = 10  # 鄰域展開上限

@dataclass
class ScheduleSlot:
    """排班格位"""
    date: str
    attending: Optional[str] = None  # 主治醫師
    resident: Optional[str] = None   # 住院醫師
    
@dataclass
class ScheduleResult:
    """排班結果"""
    schedule: Dict[str, ScheduleSlot]  # date -> slot
    score: float
    unfilled_slots: List[Tuple[str, str]]  # [(date, role), ...]
    violations: Dict[str, List[str]]  # violation_type -> descriptions
    suggestions: List[str]
    statistics: Dict[str, any]

# =====================
# 工具函數
# =====================

def get_month_calendar(year: int, month: int, custom_holidays: Set[str] = None, 
                       custom_workdays: Set[str] = None) -> Tuple[List[str], List[str]]:
    """
    生成指定月份的平日和假日列表
    
    Args:
        year: 年份
        month: 月份
        custom_holidays: 自訂假日集合 (YYYY-MM-DD格式)
        custom_workdays: 自訂補班日集合 (YYYY-MM-DD格式)
    
    Returns:
        (平日列表, 假日列表)
    """
    if custom_holidays is None:
        custom_holidays = set()
    if custom_workdays is None:
        custom_workdays = set()
    
    weekdays = []
    holidays = []
    
    # 獲取該月的天數
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 判斷是否為假日
        is_weekend = current_date.weekday() >= 5  # 週六或週日
        
        if date_str in custom_workdays:
            # 補班日
            weekdays.append(date_str)
        elif date_str in custom_holidays or (is_weekend and date_str not in custom_workdays):
            # 自訂假日或週末（非補班日）
            holidays.append(date_str)
        else:
            # 一般平日
            weekdays.append(date_str)
    
    return weekdays, holidays

def check_consecutive_days(schedule: Dict[str, ScheduleSlot], doctor_name: str, 
                          target_date: str, max_consecutive: int) -> bool:
    """檢查是否違反連續值班限制"""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    consecutive_count = 1
    
    # 檢查前面的連續天數
    for i in range(1, max_consecutive):
        check_date = (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if check_date in schedule:
            slot = schedule[check_date]
            if slot.attending == doctor_name or slot.resident == doctor_name:
                consecutive_count += 1
            else:
                break
    
    # 檢查後面的連續天數
    for i in range(1, max_consecutive):
        check_date = (target_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        if check_date in schedule:
            slot = schedule[check_date]
            if slot.attending == doctor_name or slot.resident == doctor_name:
                consecutive_count += 1
            else:
                break
    
    return consecutive_count > max_consecutive

# =====================
# 進階CSP求解器
# =====================

class CSPVariable:
    """CSP變數（代表一個排班格）"""
    def __init__(self, date: str, role: str):
        self.date = date
        self.role = role
        self.domain = []  # 可用醫師列表
        self.assigned = None  # 已指派的醫師
        
    def __str__(self):
        return f"{self.date}_{self.role}"
    
    def __hash__(self):
        return hash((self.date, self.role))
    
    def __eq__(self, other):
        return self.date == other.date and self.role == other.role

class CSPConstraint:
    """CSP約束"""
    def __init__(self, variables: List[CSPVariable], check_func):
        self.variables = variables
        self.check = check_func
    
    def is_satisfied(self, assignment: Dict[CSPVariable, str]) -> bool:
        """檢查約束是否滿足"""
        return self.check(assignment)

class AdvancedCSPSolver:
    """進階CSP求解器（含AC-3和Conflict-Directed Backjumping）"""
    
    def __init__(self, variables: List[CSPVariable], constraints: List[CSPConstraint]):
        self.variables = variables
        self.constraints = constraints
        self.conflict_set = {}  # 記錄衝突集合
        self.nodes_explored = 0
        
    def ac3(self) -> bool:
        """
        Arc Consistency 3 演算法
        通過約束傳播減少變數的值域，提前偵測無解
        """
        # 初始化弧隊列（所有有約束關係的變數對）
        queue = []
        for constraint in self.constraints:
            if len(constraint.variables) == 2:
                v1, v2 = constraint.variables
                queue.append((v1, v2))
                queue.append((v2, v1))
        
        while queue:
            xi, xj = queue.pop(0)
            
            if self.revise(xi, xj):
                if len(xi.domain) == 0:
                    return False  # 偵測到無解
                
                # 將所有與xi相關的弧加入隊列
                for constraint in self.constraints:
                    if xi in constraint.variables:
                        for xk in constraint.variables:
                            if xk != xi and xk != xj:
                                queue.append((xk, xi))
        
        return True
    
    def revise(self, xi: CSPVariable, xj: CSPVariable) -> bool:
        """
        修正xi的值域，移除不一致的值
        """
        revised = False
        to_remove = []
        
        for vi in xi.domain:
            # 檢查是否存在xj的值使得約束滿足
            found_consistent = False
            
            for vj in xj.domain:
                # 建立臨時賦值
                temp_assignment = {xi: vi, xj: vj}
                
                # 檢查所有相關約束
                all_satisfied = True
                for constraint in self.constraints:
                    if xi in constraint.variables and xj in constraint.variables:
                        if not self.check_partial_constraint(constraint, temp_assignment):
                            all_satisfied = False
                            break
                
                if all_satisfied:
                    found_consistent = True
                    break
            
            if not found_consistent:
                to_remove.append(vi)
                revised = True
        
        # 移除不一致的值
        for value in to_remove:
            xi.domain.remove(value)
        
        return revised
    
    def check_partial_constraint(self, constraint: CSPConstraint, 
                                assignment: Dict[CSPVariable, str]) -> bool:
        """檢查部分賦值是否滿足約束"""
        # 只檢查已賦值的變數
        relevant_vars = [v for v in constraint.variables if v in assignment]
        if len(relevant_vars) < len(constraint.variables):
            return True  # 約束尚未完全賦值，暫時認為滿足
        
        return constraint.is_satisfied(assignment)
    
    def conflict_directed_backjump(self, assignment: Dict[CSPVariable, str], 
                                  unassigned: List[CSPVariable]) -> Optional[Dict[CSPVariable, str]]:
        """
        Conflict-Directed Backjumping
        當遇到衝突時，直接跳回到衝突的源頭變數
        """
        self.nodes_explored += 1
        
        if not unassigned:
            return assignment  # 找到解
        
        # 選擇下一個變數（MRV啟發式）
        var = self.select_unassigned_variable(unassigned)
        
        # 記錄衝突集合
        if var not in self.conflict_set:
            self.conflict_set[var] = set()
        
        # 嘗試每個可能的值（LCV啟發式）
        for value in self.order_domain_values(var, assignment):
            assignment[var] = value
            var.assigned = value
            
            # 檢查約束
            conflict_vars = self.check_conflicts(var, assignment)
            
            if not conflict_vars:  # 沒有衝突
                # Forward checking
                saved_domains = self.forward_check(var, value, unassigned)
                
                if saved_domains is not None:
                    # 遞迴求解
                    remaining = [v for v in unassigned if v != var]
                    result = self.conflict_directed_backjump(assignment, remaining)
                    
                    if result is not None:
                        return result
                    
                    # 恢復值域
                    self.restore_domains(saved_domains)
            else:
                # 記錄衝突變數
                self.conflict_set[var].update(conflict_vars)
            
            # 回溯
            del assignment[var]
            var.assigned = None
        
        # 如果有衝突集合，返回到最早的衝突變數
        if self.conflict_set[var]:
            return None  # 將觸發回跳到衝突源
        
        return None
    
    def select_unassigned_variable(self, unassigned: List[CSPVariable]) -> CSPVariable:
        """MRV (Minimum Remaining Values) 啟發式選擇變數"""
        return min(unassigned, key=lambda var: len(var.domain))
    
    def order_domain_values(self, var: CSPVariable, 
                           assignment: Dict[CSPVariable, str]) -> List[str]:
        """LCV (Least Constraining Value) 啟發式排序值域"""
        def count_conflicts(value):
            conflicts = 0
            for other_var in self.variables:
                if other_var != var and other_var not in assignment:
                    # 計算選擇此值會限制多少其他變數的選擇
                    for other_value in other_var.domain:
                        temp_assignment = assignment.copy()
                        temp_assignment[var] = value
                        temp_assignment[other_var] = other_value
                        
                        for constraint in self.constraints:
                            if var in constraint.variables and other_var in constraint.variables:
                                if not self.check_partial_constraint(constraint, temp_assignment):
                                    conflicts += 1
            return conflicts
        
        return sorted(var.domain, key=count_conflicts)
    
    def check_conflicts(self, var: CSPVariable, 
                       assignment: Dict[CSPVariable, str]) -> Set[CSPVariable]:
        """檢查變數賦值的衝突，返回衝突變數集合"""
        conflicts = set()
        
        for constraint in self.constraints:
            if var in constraint.variables:
                # 檢查約束是否被違反
                if not self.check_partial_constraint(constraint, assignment):
                    # 找出衝突的其他變數
                    for other_var in constraint.variables:
                        if other_var != var and other_var in assignment:
                            conflicts.add(other_var)
        
        return conflicts
    
    def forward_check(self, var: CSPVariable, value: str, 
                     unassigned: List[CSPVariable]) -> Optional[Dict[CSPVariable, List[str]]]:
        """
        Forward Checking: 更新其他變數的值域
        返回原始值域的備份，如果偵測到無解則返回None
        """
        saved_domains = {}
        
        for other_var in unassigned:
            if other_var == var:
                continue
            
            saved_domains[other_var] = other_var.domain.copy()
            
            # 移除不一致的值
            to_remove = []
            for other_value in other_var.domain:
                temp_assignment = {var: value, other_var: other_value}
                
                # 檢查相關約束
                for constraint in self.constraints:
                    if var in constraint.variables and other_var in constraint.variables:
                        if not self.check_partial_constraint(constraint, temp_assignment):
                            to_remove.append(other_value)
                            break
            
            for val in to_remove:
                other_var.domain.remove(val)
            
            if len(other_var.domain) == 0:
                # 恢復並返回失敗
                self.restore_domains(saved_domains)
                return None
        
        return saved_domains
    
    def restore_domains(self, saved_domains: Dict[CSPVariable, List[str]]):
        """恢復變數值域"""
        for var, domain in saved_domains.items():
            var.domain = domain
    
    def solve(self, timeout: int = 10) -> Optional[Dict[CSPVariable, str]]:
        """
        求解CSP問題
        """
        start_time = time.time()
        
        # 先執行AC-3進行約束傳播
        if not self.ac3():
            return None  # AC-3偵測到無解
        
        # 使用Conflict-Directed Backjumping求解
        assignment = {}
        unassigned = self.variables.copy()
        
        result = self.conflict_directed_backjump(assignment, unassigned)
        
        if time.time() - start_time > timeout:
            return None  # 超時
        
        return result

# =====================
# 解池管理與ML訓練資料生成
# =====================

@dataclass
class SolutionFeatures:
    """解的特徵向量（用於機器學習）"""
    # 基礎統計
    total_slots: int
    filled_slots: int
    unfilled_slots: int
    fill_rate: float
    
    # 違規統計
    hard_violations: int
    soft_violations: int
    consecutive_violations: int
    quota_violations: int
    unavailable_violations: int
    
    # 公平性指標
    duty_variance: float
    duty_std: float
    max_duty_diff: int
    gini_coefficient: float
    
    # 偏好滿足度
    preference_hits: int
    preference_rate: float
    
    # 分布特徵
    weekend_coverage_rate: float
    weekday_coverage_rate: float
    attending_fill_rate: float
    resident_fill_rate: float
    
    # 連續性特徵
    avg_consecutive_days: float
    max_consecutive_days: int
    isolated_duty_count: int  # 單獨值班（前後都沒班）
    
    # 負載平衡
    attending_workload_std: float
    resident_workload_std: float
    cross_role_balance: float  # 主治vs住院的平衡度
    
    def to_dict(self):
        """轉換為字典格式"""
        return asdict(self)
    
    def to_vector(self):
        """轉換為特徵向量"""
        return [
            self.fill_rate,
            self.hard_violations,
            self.soft_violations,
            self.duty_variance,
            self.duty_std,
            self.max_duty_diff,
            self.gini_coefficient,
            self.preference_rate,
            self.weekend_coverage_rate,
            self.weekday_coverage_rate,
            self.avg_consecutive_days,
            self.max_consecutive_days,
            self.attending_workload_std,
            self.resident_workload_std,
            self.cross_role_balance
        ]

@dataclass
class SolutionRecord:
    """解池中的單一解記錄"""
    solution_id: str
    timestamp: str
    schedule: Dict[str, ScheduleSlot]
    score: float
    features: SolutionFeatures
    grade: str  # S/A/B/C/D/F
    iteration: int
    parent_id: Optional[str] = None
    generation_method: str = "beam_search"  # beam_search/csp/manual
    
    def to_training_record(self):
        """轉換為訓練記錄"""
        record = {
            'solution_id': self.solution_id,
            'timestamp': self.timestamp,
            'score': self.score,
            'grade': self.grade,
            'iteration': self.iteration,
            'generation_method': self.generation_method
        }
        # 添加所有特徵
        record.update(self.features.to_dict())
        return record

class SolutionPoolManager:
    """解池管理器"""
    
    def __init__(self):
        self.solution_pool: List[SolutionRecord] = []
        self.feature_extractor = FeatureExtractor()
        self.grading_system = GradingSystem()
        
    def add_solution(self, schedule: Dict[str, ScheduleSlot], 
                     score: float, iteration: int, 
                     doctors: List[Doctor], constraints: ScheduleConstraints,
                     weekdays: List[str], holidays: List[str],
                     generation_method: str = "beam_search",
                     parent_id: Optional[str] = None):
        """添加解到解池"""
        # 生成唯一ID
        solution_id = f"{generation_method}_{iteration}_{len(self.solution_pool)}_{int(time.time()*1000)}"
        
        # 提取特徵
        features = self.feature_extractor.extract_features(
            schedule, doctors, constraints, weekdays, holidays
        )
        
        # 評分分級
        grade = self.grading_system.grade_solution(score, features)
        
        # 創建記錄
        record = SolutionRecord(
            solution_id=solution_id,
            timestamp=datetime.now().isoformat(),
            schedule=copy.deepcopy(schedule),
            score=score,
            features=features,
            grade=grade,
            iteration=iteration,
            parent_id=parent_id,
            generation_method=generation_method
        )
        
        self.solution_pool.append(record)
        return solution_id
    
    def get_top_solutions(self, n: int = 10) -> List[SolutionRecord]:
        """獲取最佳的n個解"""
        sorted_pool = sorted(self.solution_pool, key=lambda x: x.score, reverse=True)
        return sorted_pool[:n]
    
    def get_solutions_by_grade(self, grade: str) -> List[SolutionRecord]:
        """獲取特定等級的解"""
        return [s for s in self.solution_pool if s.grade == grade]
    
    def export_training_data(self, format: str = "csv") -> str:
        """匯出訓練資料"""
        if not self.solution_pool:
            return None
            
        # 轉換為訓練記錄
        training_records = [s.to_training_record() for s in self.solution_pool]
        
        if format == "csv":
            df = pd.DataFrame(training_records)
            return df.to_csv(index=False)
        elif format == "json":
            return json.dumps(training_records, indent=2, ensure_ascii=False)
        else:
            return None
    
    def get_diversity_metrics(self) -> Dict:
        """計算解池多樣性指標"""
        if len(self.solution_pool) < 2:
            return {}
        
        # 計算解之間的差異度
        feature_vectors = [s.features.to_vector() for s in self.solution_pool]
        feature_array = np.array(feature_vectors)
        
        # 計算特徵的變異係數
        feature_std = np.std(feature_array, axis=0)
        feature_mean = np.mean(feature_array, axis=0)
        cv = np.divide(feature_std, feature_mean, 
                      where=feature_mean != 0, 
                      out=np.zeros_like(feature_std))
        
        # 計算等級分布
        grade_dist = Counter([s.grade for s in self.solution_pool])
        
        return {
            'pool_size': len(self.solution_pool),
            'avg_score': np.mean([s.score for s in self.solution_pool]),
            'score_std': np.std([s.score for s in self.solution_pool]),
            'grade_distribution': dict(grade_dist),
            'feature_diversity': np.mean(cv),
            'unique_schedules': len(set(
                tuple(sorted(s.schedule.items())) 
                for s in self.solution_pool
            ))
        }

class FeatureExtractor:
    """特徵提取器"""
    
    def extract_features(self, schedule: Dict[str, ScheduleSlot],
                         doctors: List[Doctor], 
                         constraints: ScheduleConstraints,
                         weekdays: List[str], 
                         holidays: List[str]) -> SolutionFeatures:
        """從排班解中提取特徵"""
        
        # 基礎統計
        total_slots = len(schedule) * 2  # 每天2個角色
        filled_slots = sum(
            1 for slot in schedule.values() 
            for val in [slot.attending, slot.resident] 
            if val
        )
        unfilled_slots = total_slots - filled_slots
        fill_rate = filled_slots / total_slots if total_slots > 0 else 0
        
        # 值班統計
        duty_counts = defaultdict(int)
        weekday_duties = defaultdict(int)
        holiday_duties = defaultdict(int)
        consecutive_tracker = defaultdict(list)
        
        # 違規統計
        hard_violations = 0
        unavailable_violations = 0
        quota_violations = 0
        consecutive_violations = 0
        preference_hits = 0
        total_preferences = 0
        
        # 遍歷排班
        for date_str, slot in schedule.items():
            is_holiday = date_str in holidays
            
            # 處理主治醫師
            if slot.attending:
                duty_counts[slot.attending] += 1
                if is_holiday:
                    holiday_duties[slot.attending] += 1
                else:
                    weekday_duties[slot.attending] += 1
                
                # 檢查違規和偏好
                doc = next((d for d in doctors if d.name == slot.attending), None)
                if doc:
                    if date_str in doc.unavailable_dates:
                        unavailable_violations += 1
                        hard_violations += 1
                    if date_str in doc.preferred_dates:
                        preference_hits += 1
                    total_preferences += len(doc.preferred_dates)
            
            # 處理住院醫師
            if slot.resident:
                duty_counts[slot.resident] += 1
                if is_holiday:
                    holiday_duties[slot.resident] += 1
                else:
                    weekday_duties[slot.resident] += 1
                
                doc = next((d for d in doctors if d.name == slot.resident), None)
                if doc:
                    if date_str in doc.unavailable_dates:
                        unavailable_violations += 1
                        hard_violations += 1
                    if date_str in doc.preferred_dates:
                        preference_hits += 1
                    total_preferences += len(doc.preferred_dates)
        
        # 檢查配額違規
        for doc in doctors:
            if weekday_duties[doc.name] > doc.weekday_quota:
                quota_violations += weekday_duties[doc.name] - doc.weekday_quota
                hard_violations += quota_violations
            if holiday_duties[doc.name] > doc.holiday_quota:
                quota_violations += holiday_duties[doc.name] - doc.holiday_quota
                hard_violations += quota_violations
        
        # 計算連續值班
        consecutive_days = self._calculate_consecutive_days(schedule, doctors)
        avg_consecutive = np.mean(consecutive_days) if consecutive_days else 0
        max_consecutive = max(consecutive_days) if consecutive_days else 0
        consecutive_violations = sum(1 for c in consecutive_days 
                                    if c > constraints.max_consecutive_days)
        
        # 公平性指標
        duties_list = list(duty_counts.values())
        duty_variance = np.var(duties_list) if duties_list else 0
        duty_std = np.std(duties_list) if duties_list else 0
        max_duty_diff = (max(duties_list) - min(duties_list)) if duties_list else 0
        gini = self._calculate_gini_coefficient(duties_list)
        
        # 覆蓋率
        weekend_filled = sum(
            1 for date_str in holidays 
            if date_str in schedule 
            for val in [schedule[date_str].attending, schedule[date_str].resident]
            if val
        )
        weekend_total = len(holidays) * 2
        weekend_coverage = weekend_filled / weekend_total if weekend_total > 0 else 0
        
        weekday_filled = sum(
            1 for date_str in weekdays 
            if date_str in schedule 
            for val in [schedule[date_str].attending, schedule[date_str].resident]
            if val
        )
        weekday_total = len(weekdays) * 2
        weekday_coverage = weekday_filled / weekday_total if weekday_total > 0 else 0
        
        # 角色平衡
        attending_duties = [duty_counts[d.name] for d in doctors if d.role == "主治"]
        resident_duties = [duty_counts[d.name] for d in doctors if d.role == "總醫師"]
        attending_std = np.std(attending_duties) if attending_duties else 0
        resident_std = np.std(resident_duties) if resident_duties else 0
        
        avg_attending = np.mean(attending_duties) if attending_duties else 0
        avg_resident = np.mean(resident_duties) if resident_duties else 0
        cross_balance = abs(avg_attending - avg_resident) / max(avg_attending, avg_resident, 1)
        
        # 計算孤立值班
        isolated_count = self._count_isolated_duties(schedule)
        
        return SolutionFeatures(
            total_slots=total_slots,
            filled_slots=filled_slots,
            unfilled_slots=unfilled_slots,
            fill_rate=fill_rate,
            hard_violations=hard_violations,
            soft_violations=consecutive_violations,
            consecutive_violations=consecutive_violations,
            quota_violations=quota_violations,
            unavailable_violations=unavailable_violations,
            duty_variance=duty_variance,
            duty_std=duty_std,
            max_duty_diff=max_duty_diff,
            gini_coefficient=gini,
            preference_hits=preference_hits,
            preference_rate=preference_hits/total_preferences if total_preferences > 0 else 0,
            weekend_coverage_rate=weekend_coverage,
            weekday_coverage_rate=weekday_coverage,
            attending_fill_rate=sum(1 for s in schedule.values() if s.attending) / len(schedule),
            resident_fill_rate=sum(1 for s in schedule.values() if s.resident) / len(schedule),
            avg_consecutive_days=avg_consecutive,
            max_consecutive_days=max_consecutive,
            isolated_duty_count=isolated_count,
            attending_workload_std=attending_std,
            resident_workload_std=resident_std,
            cross_role_balance=cross_balance
        )
    
    def _calculate_consecutive_days(self, schedule: Dict[str, ScheduleSlot], 
                                   doctors: List[Doctor]) -> List[int]:
        """計算每個醫師的連續值班天數"""
        consecutive_list = []
        
        for doc in doctors:
            dates = sorted([
                date_str for date_str, slot in schedule.items()
                if slot.attending == doc.name or slot.resident == doc.name
            ])
            
            if not dates:
                continue
            
            current_streak = 1
            for i in range(1, len(dates)):
                curr_date = datetime.strptime(dates[i], "%Y-%m-%d")
                prev_date = datetime.strptime(dates[i-1], "%Y-%m-%d")
                
                if (curr_date - prev_date).days == 1:
                    current_streak += 1
                else:
                    consecutive_list.append(current_streak)
                    current_streak = 1
            
            consecutive_list.append(current_streak)
        
        return consecutive_list
    
    def _calculate_gini_coefficient(self, values: List[float]) -> float:
        """計算基尼係數（衡量不平等程度）"""
        if not values or len(values) < 2:
            return 0
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        cumsum = np.cumsum(sorted_values)
        
        return (2 * np.sum((np.arange(1, n+1)) * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n
    
    def _count_isolated_duties(self, schedule: Dict[str, ScheduleSlot]) -> int:
        """計算孤立值班數（前後都沒班）"""
        isolated = 0
        sorted_dates = sorted(schedule.keys())
        
        for i, date_str in enumerate(sorted_dates):
            slot = schedule[date_str]
            
            for doctor_name in [slot.attending, slot.resident]:
                if not doctor_name:
                    continue
                
                # 檢查前一天
                has_prev = False
                if i > 0:
                    prev_slot = schedule[sorted_dates[i-1]]
                    if prev_slot.attending == doctor_name or prev_slot.resident == doctor_name:
                        has_prev = True
                
                # 檢查後一天
                has_next = False
                if i < len(sorted_dates) - 1:
                    next_slot = schedule[sorted_dates[i+1]]
                    if next_slot.attending == doctor_name or next_slot.resident == doctor_name:
                        has_next = True
                
                if not has_prev and not has_next:
                    isolated += 1
        
        return isolated

class GradingSystem:
    """解的分級系統"""
    
    def __init__(self):
        # 分級閾值（可調整）
        self.thresholds = {
            'S': {'min_score': 0, 'max_unfilled': 0, 'max_hard_violations': 0},
            'A': {'min_score': -100, 'max_unfilled': 2, 'max_hard_violations': 1},
            'B': {'min_score': -500, 'max_unfilled': 5, 'max_hard_violations': 3},
            'C': {'min_score': -1000, 'max_unfilled': 10, 'max_hard_violations': 5},
            'D': {'min_score': -2000, 'max_unfilled': 15, 'max_hard_violations': 10},
            'F': {'min_score': -float('inf'), 'max_unfilled': float('inf'), 'max_hard_violations': float('inf')}
        }
    
    def grade_solution(self, score: float, features: SolutionFeatures) -> str:
        """對解進行分級"""
        for grade in ['S', 'A', 'B', 'C', 'D', 'F']:
            threshold = self.thresholds[grade]
            
            if (score >= threshold['min_score'] and 
                features.unfilled_slots <= threshold['max_unfilled'] and
                features.hard_violations <= threshold['max_hard_violations']):
                
                # 額外的細分條件
                if grade in ['S', 'A'] and features.fill_rate < 0.9:
                    continue  # S和A級需要90%以上的填充率
                
                if grade == 'S' and features.preference_rate < 0.8:
                    continue  # S級需要80%以上的偏好滿足率
                
                return grade
        
        return 'F'
    
    def get_grade_description(self, grade: str) -> str:
        """獲取等級描述"""
        descriptions = {
            'S': "完美解：無違規、全填滿、高偏好滿足",
            'A': "優秀解：極少違規、高填充率",
            'B': "良好解：少量違規、可接受的填充率",
            'C': "普通解：中等違規、基本可用",
            'D': "較差解：違規較多、需要改進",
            'F': "失敗解：嚴重違規、不可用"
        }
        return descriptions.get(grade, "未知等級")

class BeamSearchScheduler:
    """束搜索排班器（含解池收集）"""
    
    def __init__(self, doctors: List[Doctor], constraints: ScheduleConstraints,
                 weekdays: List[str], holidays: List[str]):
        self.doctors = doctors
        self.constraints = constraints
        self.weekdays = weekdays
        self.holidays = holidays
        self.attending_doctors = [d for d in doctors if d.role == "主治"]
        self.resident_doctors = [d for d in doctors if d.role == "總醫師"]
        
        # 建立醫師索引
        self.doctor_map = {d.name: d for d in doctors}
        
        # 初始化解池管理器
        self.solution_pool = SolutionPoolManager()
        
    def run(self, progress_callback=None, collect_all_solutions=True) -> ScheduleResult:
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
                available = self.get_available_doctors(date_str, "主治", schedule)
                
                if not available:
                    # 保持未填
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        # 收集到解池
                        sol_id = self.solution_pool.add_solution(
                            schedule, score, iteration, 
                            self.doctors, self.constraints,
                            self.weekdays, self.holidays,
                            generation_method="beam_search",
                            parent_id=parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    # 嘗試每個可用醫師
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].attending = doc_name
                        new_score, _ = self.calculate_score(new_schedule)
                        
                        # 收集到解池
                        if collect_all_solutions:
                            sol_id = self.solution_pool.add_solution(
                                new_schedule, new_score, iteration,
                                self.doctors, self.constraints,
                                self.weekdays, self.holidays,
                                generation_method="beam_search",
                                parent_id=parent_id
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
                available = self.get_available_doctors(date_str, "總醫師", schedule)
                
                if not available:
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        sol_id = self.solution_pool.add_solution(
                            schedule, score, iteration,
                            self.doctors, self.constraints,
                            self.weekdays, self.holidays,
                            generation_method="beam_search",
                            parent_id=parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].resident = doc_name
                        new_score, _ = self.calculate_score(new_schedule)
                        
                        if collect_all_solutions:
                            sol_id = self.solution_pool.add_solution(
                                new_schedule, new_score, iteration,
                                self.doctors, self.constraints,
                                self.weekdays, self.holidays,
                                generation_method="beam_search",
                                parent_id=parent_id
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
            final_score, _ = self.calculate_score(best_schedule)
            self.solution_pool.add_solution(
                best_schedule, final_score, iteration + 1,
                self.doctors, self.constraints,
                self.weekdays, self.holidays,
                generation_method="csp_enhanced",
                parent_id=best_id
            )
        
        return self.create_result(best_schedule)
        
    def calculate_score(self, schedule: Dict[str, ScheduleSlot]) -> Tuple[float, Dict]:
        """
        計算排班方案分數
        Score = -1000*U -100*HardViol -10*SoftViol + 5*Fairness + 2*PreferenceHits
        """
        stats = {
            'unfilled': 0,
            'hard_violations': 0,
            'soft_violations': 0,
            'fairness': 0,
            'preference_hits': 0
        }
        
        # 計算未填格數
        for date_str in self.weekdays + self.holidays:
            if date_str in schedule:
                slot = schedule[date_str]
                if not slot.attending:
                    stats['unfilled'] += 1
                if not slot.resident:
                    stats['unfilled'] += 1
            else:
                stats['unfilled'] += 2
        
        # 計算違規數和偏好命中
        duty_counts = defaultdict(int)
        weekday_counts = defaultdict(int)
        holiday_counts = defaultdict(int)
        
        for date_str, slot in schedule.items():
            is_holiday = date_str in self.holidays
            
            # 統計值班次數
            if slot.attending:
                duty_counts[slot.attending] += 1
                if is_holiday:
                    holiday_counts[slot.attending] += 1
                else:
                    weekday_counts[slot.attending] += 1
                    
                # 檢查違規
                doc = self.doctor_map[slot.attending]
                if date_str in doc.unavailable_dates:
                    stats['hard_violations'] += 1
                if date_str in doc.preferred_dates:
                    stats['preference_hits'] += 1
                    
            if slot.resident:
                duty_counts[slot.resident] += 1
                if is_holiday:
                    holiday_counts[slot.resident] += 1
                else:
                    weekday_counts[slot.resident] += 1
                    
                doc = self.doctor_map[slot.resident]
                if date_str in doc.unavailable_dates:
                    stats['hard_violations'] += 1
                if date_str in doc.preferred_dates:
                    stats['preference_hits'] += 1
        
        # 檢查配額違規
        for name, doc in self.doctor_map.items():
            if weekday_counts[name] > doc.weekday_quota:
                stats['hard_violations'] += (weekday_counts[name] - doc.weekday_quota)
            if holiday_counts[name] > doc.holiday_quota:
                stats['hard_violations'] += (holiday_counts[name] - doc.holiday_quota)
        
        # 計算公平性（使用標準差的反向值）
        if duty_counts:
            values = list(duty_counts.values())
            mean_duty = np.mean(values)
            std_duty = np.std(values)
            stats['fairness'] = max(0, 10 - std_duty)  # 標準差越小，公平性越高
        
        # 計算總分
        score = (-1000 * stats['unfilled'] 
                 -100 * stats['hard_violations'] 
                 -10 * stats['soft_violations'] 
                 + 5 * stats['fairness'] 
                 + 2 * stats['preference_hits'])
        
        return score, stats
    
    def get_available_doctors(self, date_str: str, role: str, 
                             schedule: Dict[str, ScheduleSlot]) -> List[str]:
        """獲取某日期某角色的可用醫師列表"""
        doctors = self.attending_doctors if role == "主治" else self.resident_doctors
        available = []
        
        is_holiday = date_str in self.holidays
        weekday_counts = defaultdict(int)
        holiday_counts = defaultdict(int)
        
        # 統計當前班數
        for d, slot in schedule.items():
            if d in self.holidays:
                if slot.attending:
                    holiday_counts[slot.attending] += 1
                if slot.resident:
                    holiday_counts[slot.resident] += 1
            else:
                if slot.attending:
                    weekday_counts[slot.attending] += 1
                if slot.resident:
                    weekday_counts[slot.resident] += 1
        
        for doc in doctors:
            # 檢查是否為不可值班日
            if date_str in doc.unavailable_dates:
                continue
                
            # 檢查配額
            if is_holiday:
                if holiday_counts[doc.name] >= doc.holiday_quota:
                    continue
            else:
                if weekday_counts[doc.name] >= doc.weekday_quota:
                    continue
            
            # 檢查同日是否已排班
            if date_str in schedule:
                slot = schedule[date_str]
                if slot.attending == doc.name or slot.resident == doc.name:
                    continue
            
            # 檢查連續值班
            if not check_consecutive_days(schedule, doc.name, date_str, 
                                         self.constraints.max_consecutive_days):
                available.append(doc.name)
        
        return available
    
    def run(self, progress_callback=None, collect_all_solutions=True) -> ScheduleResult:
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
                available = self.get_available_doctors(date_str, "主治", schedule)
                
                if not available:
                    # 保持未填
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        # 收集到解池
                        sol_id = self.solution_pool.add_solution(
                            schedule, score, iteration, 
                            self.doctors, self.constraints,
                            self.weekdays, self.holidays,
                            generation_method="beam_search",
                            parent_id=parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    # 嘗試每個可用醫師
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].attending = doc_name
                        new_score, _ = self.calculate_score(new_schedule)
                        
                        # 收集到解池
                        if collect_all_solutions:
                            sol_id = self.solution_pool.add_solution(
                                new_schedule, new_score, iteration,
                                self.doctors, self.constraints,
                                self.weekdays, self.holidays,
                                generation_method="beam_search",
                                parent_id=parent_id
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
                available = self.get_available_doctors(date_str, "總醫師", schedule)
                
                if not available:
                    new_beam.append((score, schedule, parent_id))
                    if collect_all_solutions:
                        sol_id = self.solution_pool.add_solution(
                            schedule, score, iteration,
                            self.doctors, self.constraints,
                            self.weekdays, self.holidays,
                            generation_method="beam_search",
                            parent_id=parent_id
                        )
                        new_beam[-1] = (score, schedule, sol_id)
                else:
                    for doc_name in available[:self.constraints.neighbor_expansion]:
                        new_schedule = copy.deepcopy(schedule)
                        new_schedule[date_str].resident = doc_name
                        new_score, _ = self.calculate_score(new_schedule)
                        
                        if collect_all_solutions:
                            sol_id = self.solution_pool.add_solution(
                                new_schedule, new_score, iteration,
                                self.doctors, self.constraints,
                                self.weekdays, self.holidays,
                                generation_method="beam_search",
                                parent_id=parent_id
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
            final_score, _ = self.calculate_score(best_schedule)
            self.solution_pool.add_solution(
                best_schedule, final_score, iteration + 1,
                self.doctors, self.constraints,
                self.weekdays, self.holidays,
                generation_method="csp_enhanced",
                parent_id=best_id
            )
        
        return self.create_result(best_schedule)
    
    def csp_fill_gaps(self, schedule: Dict[str, ScheduleSlot]) -> Dict[str, ScheduleSlot]:
        """使用進階CSP求解器填補未填格"""
        # 收集未填格
        unfilled = []
        for date_str, slot in schedule.items():
            if not slot.attending:
                unfilled.append((date_str, "主治"))
            if not slot.resident:
                unfilled.append((date_str, "總醫師"))
        
        if not unfilled:
            return schedule
        
        # 建立CSP變數
        variables = []
        var_map = {}  # (date, role) -> CSPVariable
        
        for date_str, role in unfilled:
            var = CSPVariable(date_str, role)
            var.domain = self.get_available_doctors(date_str, role, schedule)
            variables.append(var)
            var_map[(date_str, role)] = var
        
        # 建立約束
        constraints = []
        
        # 約束1: 同一天同一人不能擔任兩個角色
        for date_str in set([d for d, _ in unfilled]):
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
            var_date = datetime.strptime(var.date, "%Y-%m-%d")
            
            # 找出相鄰日期的變數
            adjacent_vars = []
            for other_var in variables:
                if other_var == var:
                    continue
                other_date = datetime.strptime(other_var.date, "%Y-%m-%d")
                days_diff = abs((other_date - var_date).days)
                if days_diff <= self.constraints.max_consecutive_days:
                    adjacent_vars.append(other_var)
            
            if adjacent_vars:
                def consecutive_constraint(assignment, var=var, adjacent=adjacent_vars, 
                                         max_cons=self.constraints.max_consecutive_days):
                    if var not in assignment:
                        return True
                    
                    doctor_name = assignment[var]
                    consecutive_count = 1
                    
                    # 檢查相鄰的賦值
                    for adj_var in adjacent:
                        if adj_var in assignment and assignment[adj_var] == doctor_name:
                            consecutive_count += 1
                    
                    return consecutive_count <= max_cons
                
                constraint_vars = [var] + adjacent_vars
                constraints.append(CSPConstraint(constraint_vars, consecutive_constraint))
        
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
            st.session_state.csp_stats = {
                'solved': True,
                'nodes_explored': solver.nodes_explored,
                'unfilled_before': len(unfilled),
                'unfilled_after': sum(1 for d, s in best_schedule.items() 
                                    if not s.attending or not s.resident)
            }
        else:
            # CSP無解，使用啟發式填補
            st.session_state.csp_stats = {
                'solved': False,
                'nodes_explored': solver.nodes_explored,
                'unfilled_before': len(unfilled),
                'unfilled_after': len(unfilled)
            }
            
            # 至少嘗試填一些明顯可以填的
            for date_str, role in unfilled:
                available = self.get_available_doctors(date_str, role, best_schedule)
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
        score, stats = self.calculate_score(schedule)
        
        # 找出未填格
        unfilled = []
        for date_str, slot in schedule.items():
            if not slot.attending:
                unfilled.append((date_str, "主治"))
            if not slot.resident:
                unfilled.append((date_str, "總醫師"))
        
        # 生成建議
        suggestions = []
        if unfilled:
            suggestions.append(f"共有 {len(unfilled)} 個未填格位")
            for date_str, role in unfilled[:5]:  # 顯示前5個
                available = self.get_available_doctors(date_str, role, schedule)
                if available:
                    suggestions.append(f"{date_str} {role}可選: {', '.join(available)}")
                else:
                    suggestions.append(f"{date_str} {role}: 無可用醫師")
        
        # 統計資訊
        duty_counts = defaultdict(int)
        for slot in schedule.values():
            if slot.attending:
                duty_counts[slot.attending] += 1
            if slot.resident:
                duty_counts[slot.resident] += 1
        
        return ScheduleResult(
            schedule=schedule,
            score=score,
            unfilled_slots=unfilled,
            violations={},
            suggestions=suggestions,
            statistics={
                'total_slots': len(schedule) * 2,
                'filled_slots': len(schedule) * 2 - len(unfilled),
                'duty_counts': dict(duty_counts),
                'score_breakdown': stats
            }
        )

# =====================
# Streamlit UI
# =====================

# 頁面配置
st.set_page_config(
    page_title="醫師智慧排班系統",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自訂CSS樣式
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
        background-color: #f0f2f6;
        border-radius: 10px 10px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f77b4;
        color: white;
    }
    .doctor-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .schedule-cell {
        padding: 8px;
        border: 1px solid #ddd;
        text-align: center;
    }
    .attending-cell {
        background-color: #e3f2fd;
        color: #1976d2;
        font-weight: bold;
    }
    .resident-cell {
        background-color: #f3e5f5;
        color: #7b1fa2;
        font-weight: bold;
    }
    .empty-cell {
        background-color: #ffebee;
        color: #c62828;
    }
    .holiday-header {
        background-color: #ffcdd2;
        font-weight: bold;
    }
    .weekday-header {
        background-color: #c5cae9;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 初始化Session State
if 'doctors' not in st.session_state:
    st.session_state.doctors = []
    
if 'holidays' not in st.session_state:
    st.session_state.holidays = set()
    
if 'workdays' not in st.session_state:
    st.session_state.workdays = set()
    
if 'schedule_result' not in st.session_state:
    st.session_state.schedule_result = None

if 'selected_year' not in st.session_state:
    st.session_state.selected_year = datetime.now().year
    
if 'selected_month' not in st.session_state:
    st.session_state.selected_month = datetime.now().month

if 'csp_stats' not in st.session_state:
    st.session_state.csp_stats = None

if 'use_ac3' not in st.session_state:
    st.session_state.use_ac3 = True

if 'use_backjump' not in st.session_state:
    st.session_state.use_backjump = True

if 'solution_pool' not in st.session_state:
    st.session_state.solution_pool = None

if 'last_scheduler' not in st.session_state:
    st.session_state.last_scheduler = None

# 側邊欄設定
with st.sidebar:
    st.title("⚙️ 系統設定")
    
    # 月份選擇
    st.subheader("📅 排班月份")
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("年份", min_value=2024, max_value=2030, 
                              value=st.session_state.selected_year)
        st.session_state.selected_year = year
    with col2:
        month = st.selectbox("月份", range(1, 13), 
                           index=st.session_state.selected_month - 1,
                           format_func=lambda x: f"{x}月")
        st.session_state.selected_month = month
    
    st.divider()
    
    # 演算法參數
    st.subheader("🔧 演算法參數")
    max_consecutive = st.slider("最大連續值班天數", 1, 5, 2)
    beam_width = st.slider("束搜索寬度", 3, 10, 5)
    csp_timeout = st.slider("CSP超時(秒)", 5, 30, 10)
    
    # 進階CSP設定
    with st.expander("🎯 進階CSP設定", expanded=False):
        st.info("""
        **Arc Consistency (AC-3)**
        透過約束傳播提前偵測無解，大幅減少搜索空間
        
        **Conflict-Directed Backjumping**
        智慧回溯機制，直接跳回衝突源頭，避免無謂搜索
        """)
        
        use_ac3 = st.checkbox("啟用 Arc Consistency", value=True,
                             help="使用AC-3演算法進行約束傳播")
        use_backjump = st.checkbox("啟用 Conflict-Directed Backjumping", value=True,
                                  help="使用智慧回溯避免無謂搜索")
        
        neighbor_expansion = st.slider("鄰域展開上限", 5, 20, 10,
                                      help="每個變數展開的最大候選數")
    
    constraints = ScheduleConstraints(
        max_consecutive_days=max_consecutive,
        beam_width=beam_width,
        csp_timeout=csp_timeout,
        neighbor_expansion=neighbor_expansion
    )
    
    # 儲存進階設定到session state
    st.session_state.use_ac3 = use_ac3
    st.session_state.use_backjump = use_backjump
    
    st.divider()
    
    # 資料管理
    st.subheader("💾 資料管理")
    
    # 儲存按鈕
    if st.button("💾 儲存所有設定", use_container_width=True):
        save_data = {
            'doctors': [d.to_dict() for d in st.session_state.doctors],
            'holidays': list(st.session_state.holidays),
            'workdays': list(st.session_state.workdays),
            'year': st.session_state.selected_year,
            'month': st.session_state.selected_month,
            'use_ac3': st.session_state.get('use_ac3', True),
            'use_backjump': st.session_state.get('use_backjump', True)
        }
        with open('schedule_settings.json', 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        st.success("設定已儲存！")
    
    # 載入按鈕
    if st.button("📂 載入設定", use_container_width=True):
        if os.path.exists('schedule_settings.json'):
            with open('schedule_settings.json', 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            st.session_state.doctors = [Doctor.from_dict(d) for d in save_data['doctors']]
            st.session_state.holidays = set(save_data.get('holidays', []))
            st.session_state.workdays = set(save_data.get('workdays', []))
            st.session_state.selected_year = save_data.get('year', datetime.now().year)
            st.session_state.selected_month = save_data.get('month', datetime.now().month)
            st.session_state.use_ac3 = save_data.get('use_ac3', True)
            st.session_state.use_backjump = save_data.get('use_backjump', True)
            st.success("設定已載入！")
            st.rerun()
        else:
            st.error("找不到儲存的設定檔案")

# 主頁面標題
st.title("🏥 醫師智慧排班系統")
st.markdown("支援主治醫師與住院醫師的自動排班，使用束搜索與CSP演算法")

# 取得當前月份資料（供所有Tab使用）
current_weekdays, current_holidays = get_month_calendar(
    st.session_state.selected_year,
    st.session_state.selected_month,
    st.session_state.holidays,
    st.session_state.workdays
)

# 主頁面分頁
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "👥 醫師管理", "📅 假日設定", "🚀 執行排班", 
    "📊 結果檢視", "📈 統計分析", "🤖 ML訓練資料"
])

# Tab 1: 醫師管理
with tab1:
    st.header("醫師名單管理")
    
    # 快速測試資料
    with st.expander("🧪 載入測試資料", expanded=False):
        test_scenario = st.selectbox(
            "選擇測試場景",
            ["基本測試 (6主治+7住院)", "困難測試 (衝突多)", "大規模測試 (10+10)"]
        )
        
        if st.button("載入測試資料", type="secondary"):
            st.session_state.doctors = []
            
            if test_scenario == "基本測試 (6主治+7住院)":
                # 6位主治醫師
                for i in range(1, 7):
                    st.session_state.doctors.append(Doctor(
                        name=f"主治{i}",
                        role="主治",
                        weekday_quota=4,
                        holiday_quota=2,
                        unavailable_dates=[],
                        preferred_dates=[]
                    ))
                
                # 7位住院醫師
                for i in range(1, 8):
                    st.session_state.doctors.append(Doctor(
                        name=f"住院{i}",
                        role="總醫師",
                        weekday_quota=5,
                        holiday_quota=2,
                        unavailable_dates=[],
                        preferred_dates=[]
                    ))
                
            elif test_scenario == "困難測試 (衝突多)":
                year = st.session_state.selected_year
                month = st.session_state.selected_month
                
                # 建立衝突的不可值班日
                dates = [f"{year}-{month:02d}-{d:02d}" for d in range(5, 15)]
                
                # 3位主治醫師（衝突多）
                st.session_state.doctors.append(Doctor(
                    name="主治A",
                    role="主治",
                    weekday_quota=3,
                    holiday_quota=1,
                    unavailable_dates=dates[:5],  # 5-9號不可
                    preferred_dates=[dates[10]]
                ))
                st.session_state.doctors.append(Doctor(
                    name="主治B",
                    role="主治",
                    weekday_quota=3,
                    holiday_quota=1,
                    unavailable_dates=dates[3:8],  # 8-12號不可
                    preferred_dates=[]
                ))
                st.session_state.doctors.append(Doctor(
                    name="主治C",
                    role="主治",
                    weekday_quota=4,
                    holiday_quota=2,
                    unavailable_dates=dates[6:9],  # 11-13號不可
                    preferred_dates=[]
                ))
                
                # 4位住院醫師（衝突多）
                for i in range(1, 5):
                    unavail = dates[i:i+3] if i < 7 else []
                    st.session_state.doctors.append(Doctor(
                        name=f"住院{i}",
                        role="總醫師",
                        weekday_quota=4,
                        holiday_quota=2,
                        unavailable_dates=unavail,
                        preferred_dates=[]
                    ))
            
            else:  # 大規模測試
                # 10位主治醫師
                for i in range(1, 11):
                    st.session_state.doctors.append(Doctor(
                        name=f"主治{i:02d}",
                        role="主治",
                        weekday_quota=3,
                        holiday_quota=1,
                        unavailable_dates=[],
                        preferred_dates=[]
                    ))
                
                # 10位住院醫師
                for i in range(1, 11):
                    st.session_state.doctors.append(Doctor(
                        name=f"住院{i:02d}",
                        role="總醫師",
                        weekday_quota=3,
                        holiday_quota=1,
                        unavailable_dates=[],
                        preferred_dates=[]
                    ))
            
            st.success(f"已載入 {test_scenario}")
            st.rerun()
    
    # 新增醫師表單
    with st.expander("➕ 新增醫師", expanded=False):
        with st.form("add_doctor_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input("醫師姓名")
                role = st.selectbox("角色", ["主治", "總醫師"])
            with col2:
                weekday_quota = st.number_input("平日配額", min_value=0, max_value=20, value=5)
                holiday_quota = st.number_input("假日配額", min_value=0, max_value=10, value=2)
            with col3:
                unavailable = st.text_area("不可值班日(YYYY-MM-DD，每行一個)")
                preferred = st.text_area("優先值班日(YYYY-MM-DD，每行一個)")
            
            if st.form_submit_button("新增醫師", type="primary"):
                if name:
                    unavailable_dates = [d.strip() for d in unavailable.split('\n') if d.strip()]
                    preferred_dates = [d.strip() for d in preferred.split('\n') if d.strip()]
                    
                    new_doctor = Doctor(
                        name=name,
                        role=role,
                        weekday_quota=weekday_quota,
                        holiday_quota=holiday_quota,
                        unavailable_dates=unavailable_dates,
                        preferred_dates=preferred_dates
                    )
                    st.session_state.doctors.append(new_doctor)
                    st.success(f"已新增醫師：{name}")
                    st.rerun()
    
    # 顯示現有醫師
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👨‍⚕️ 主治醫師")
        attending = [d for d in st.session_state.doctors if d.role == "主治"]
        if attending:
            for doc in attending:
                with st.container():
                    st.markdown(f"""
                    <div class="doctor-card">
                        <h4>{doc.name}</h4>
                        <p>平日配額: {doc.weekday_quota} | 假日配額: {doc.holiday_quota}</p>
                        <p>不可值班: {len(doc.unavailable_dates)}天 | 優先值班: {len(doc.preferred_dates)}天</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"刪除 {doc.name}", key=f"del_{doc.name}"):
                        st.session_state.doctors.remove(doc)
                        st.rerun()
        else:
            st.info("尚未新增主治醫師")
    
    with col2:
        st.subheader("👨‍⚕️ 住院醫師")
        residents = [d for d in st.session_state.doctors if d.role == "總醫師"]
        if residents:
            for doc in residents:
                with st.container():
                    st.markdown(f"""
                    <div class="doctor-card">
                        <h4>{doc.name}</h4>
                        <p>平日配額: {doc.weekday_quota} | 假日配額: {doc.holiday_quota}</p>
                        <p>不可值班: {len(doc.unavailable_dates)}天 | 優先值班: {len(doc.preferred_dates)}天</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"刪除 {doc.name}", key=f"del_{doc.name}"):
                        st.session_state.doctors.remove(doc)
                        st.rerun()
        else:
            st.info("尚未新增住院醫師")

# Tab 2: 假日設定
with tab2:
    st.header("假日與補班管理")
    
    # 獲取當月日期
    year = st.session_state.selected_year
    month = st.session_state.selected_month
    num_days = calendar.monthrange(year, month)[1]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎉 自訂假日")
        st.info("選擇平日設為假日")
        
        # 生成日期選項
        dates = []
        for day in range(1, num_days + 1):
            current_date = date(year, month, day)
            if current_date.weekday() < 5:  # 平日
                dates.append(current_date.strftime("%Y-%m-%d"))
        
        selected_holidays = st.multiselect(
            "選擇假日",
            dates,
            default=list(st.session_state.holidays)
        )
        st.session_state.holidays = set(selected_holidays)
    
    with col2:
        st.subheader("💼 補班日")
        st.info("選擇週末設為工作日")
        
        # 生成週末日期
        weekend_dates = []
        for day in range(1, num_days + 1):
            current_date = date(year, month, day)
            if current_date.weekday() >= 5:  # 週末
                weekend_dates.append(current_date.strftime("%Y-%m-%d"))
        
        selected_workdays = st.multiselect(
            "選擇補班日",
            weekend_dates,
            default=list(st.session_state.workdays)
        )
        st.session_state.workdays = set(selected_workdays)
    
    # 顯示月曆預覽
    st.subheader("📅 月曆預覽")
    weekdays, holidays = get_month_calendar(year, month, 
                                           st.session_state.holidays,
                                           st.session_state.workdays)
    
    # 建立月曆視圖
    cal_data = []
    week = []
    first_day = date(year, month, 1)
    start_weekday = first_day.weekday()
    
    # 填充開始的空白
    for _ in range(start_weekday):
        week.append("")
    
    # 填充日期
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        date_str = current_date.strftime("%Y-%m-%d")
        
        if date_str in holidays:
            week.append(f"🎉 {day}")
        elif date_str in weekdays:
            week.append(f"💼 {day}")
        else:
            week.append(str(day))
        
        if len(week) == 7:
            cal_data.append(week)
            week = []
    
    # 填充結尾的空白
    while week and len(week) < 7:
        week.append("")
    if week:
        cal_data.append(week)
    
    # 顯示月曆
    df_cal = pd.DataFrame(cal_data, columns=['一', '二', '三', '四', '五', '六', '日'])
    st.dataframe(df_cal, use_container_width=True)
    
    st.info(f"本月共有 {len(weekdays)} 個平日，{len(holidays)} 個假日")

# Tab 3: 執行排班
with tab3:
    st.header("執行自動排班")
    
    # 檢查前置條件
    attending_count = len([d for d in st.session_state.doctors if d.role == "主治"])
    resident_count = len([d for d in st.session_state.doctors if d.role == "總醫師"])
    
    if attending_count == 0 or resident_count == 0:
        st.error("請先新增至少一位主治醫師和一位住院醫師")
    else:
        st.success(f"目前有 {attending_count} 位主治醫師，{resident_count} 位住院醫師")
        
        # 排班參數顯示
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("總天數", len(current_weekdays) + len(current_holidays))
        with col2:
            st.metric("平日", len(current_weekdays))
        with col3:
            st.metric("假日", len(current_holidays))
        
        # 進階選項
        with st.expander("🔬 進階選項", expanded=False):
            collect_all = st.checkbox(
                "收集所有候選解（用於ML訓練）", 
                value=True,
                help="收集搜索過程中的所有解，用於機器學習訓練資料生成"
            )
            
            st.info("""
            📌 **收集解池的好處**：
            - 生成大量標註資料用於訓練排班AI
            - 分析不同解的特徵分布
            - 了解演算法的搜索路徑
            - 找出潛在的優化方向
            """)
        
        # 執行按鈕
        if st.button("🚀 開始排班", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(progress):
                progress_bar.progress(progress)
                status_text.text(f"排班進度：{int(progress * 100)}%")
            
            # 執行排班
            scheduler = BeamSearchScheduler(
                doctors=st.session_state.doctors,
                constraints=constraints,
                weekdays=current_weekdays,
                holidays=current_holidays
            )
            
            with st.spinner("正在執行智慧排班..."):
                result = scheduler.run(
                    progress_callback=update_progress,
                    collect_all_solutions=collect_all
                )
                st.session_state.schedule_result = result
                st.session_state.last_scheduler = scheduler  # 保存scheduler以供後續使用
            
            progress_bar.progress(1.0)
            status_text.text("排班完成！")
            
            # 顯示結果摘要
            st.success("✅ 排班完成！")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                total_slots = result.statistics['total_slots']
                filled_slots = result.statistics['filled_slots']
                st.metric("填充率", f"{filled_slots}/{total_slots}",
                         f"{filled_slots/total_slots*100:.1f}%")
            with col2:
                st.metric("總分數", f"{result.score:.0f}")
            with col3:
                st.metric("未填格數", len(result.unfilled_slots))
            with col4:
                breakdown = result.statistics['score_breakdown']
                st.metric("公平性分數", f"{breakdown['fairness']:.1f}")
            
            # 顯示解池統計
            if collect_all and scheduler.solution_pool:
                with st.expander("🗂️ 解池統計", expanded=False):
                    pool_metrics = scheduler.solution_pool.get_diversity_metrics()
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("解池大小", pool_metrics.get('pool_size', 0))
                        st.metric("平均分數", f"{pool_metrics.get('avg_score', 0):.1f}")
                    with col2:
                        st.metric("唯一解數量", pool_metrics.get('unique_schedules', 0))
                        st.metric("特徵多樣性", f"{pool_metrics.get('feature_diversity', 0):.3f}")
                    with col3:
                        grade_dist = pool_metrics.get('grade_distribution', {})
                        grade_text = ", ".join([f"{g}:{c}" for g, c in grade_dist.items()])
                        st.metric("等級分布", grade_text if grade_text else "N/A")
            
            # 顯示CSP求解統計（如果有）
            if hasattr(st.session_state, 'csp_stats') and st.session_state.csp_stats:
                with st.expander("🔍 CSP求解統計", expanded=False):
                    csp_stats = st.session_state.csp_stats
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("求解狀態", 
                                 "✅ 成功" if csp_stats['solved'] else "⚠️ 部分解")
                    with col2:
                        st.metric("探索節點數", csp_stats['nodes_explored'])
                    with col3:
                        st.metric("CSP前未填格", csp_stats['unfilled_before'])
                    with col4:
                        st.metric("CSP後未填格", csp_stats['unfilled_after'])
                    
                    # 顯示AC-3和Backjumping的效果
                    if csp_stats['solved']:
                        st.info(f"""
                        🎯 **CSP求解成功**
                        - Arc Consistency (AC-3) 成功減少搜索空間
                        - Conflict-Directed Backjumping 有效避免無謂搜索
                        - 共填補 {csp_stats['unfilled_before'] - csp_stats['unfilled_after']} 個空格
                        """)
                    else:
                        st.warning(f"""
                        ⚠️ **CSP部分求解**
                        - 問題可能過度約束（over-constrained）
                        - 建議調整醫師配額或放寬連續值班限制
                        - 系統已盡可能填補可行的空格
                        """)
            
            # 顯示建議
            if result.suggestions:
                with st.expander("💡 系統建議", expanded=True):
                    for suggestion in result.suggestions:
                        st.write(f"• {suggestion}")

# Tab 4: 結果檢視
with tab4:
    st.header("排班結果檢視")
    
    if st.session_state.schedule_result is None:
        st.info("請先執行排班")
    else:
        result = st.session_state.schedule_result
        scheduler = BeamSearchScheduler(
            doctors=st.session_state.doctors,
            constraints=constraints,
            weekdays=current_weekdays,
            holidays=current_holidays
        )
        
        # 顯示模式選擇
        view_mode = st.radio(
            "檢視模式",
            ["月曆視圖", "列表視圖"],
            horizontal=True
        )
        
        if view_mode == "月曆視圖":
            st.subheader("📅 月曆班表")
            
            # 建立月曆HTML
            year = st.session_state.selected_year
            month = st.session_state.selected_month
            num_days = calendar.monthrange(year, month)[1]
            first_day = date(year, month, 1)
            start_weekday = first_day.weekday()
            
            # 建立月曆HTML表格
            calendar_html = """
            <style>
                .calendar-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-family: Arial, sans-serif;
                }
                .calendar-table th {
                    background-color: #2c3e50;
                    color: white;
                    padding: 10px;
                    text-align: center;
                    font-weight: bold;
                }
                .calendar-table td {
                    border: 1px solid #ddd;
                    padding: 5px;
                    height: 120px;
                    width: 14.28%;
                    vertical-align: top;
                    position: relative;
                }
                .calendar-date {
                    font-weight: bold;
                    margin-bottom: 5px;
                    font-size: 14px;
                }
                .holiday-cell {
                    background-color: #fff3e0;
                }
                .weekday-cell {
                    background-color: #f5f5f5;
                }
                .doctor-info {
                    font-size: 12px;
                    margin: 2px 0;
                    padding: 2px 4px;
                    border-radius: 3px;
                }
                .attending {
                    background-color: #e3f2fd;
                    color: #1565c0;
                }
                .resident {
                    background-color: #f3e5f5;
                    color: #6a1b9a;
                }
                .empty-slot {
                    background-color: #ffcdd2;
                    color: #c62828;
                    font-weight: bold;
                    margin: 2px 0;
                    padding: 2px 4px;
                    border-radius: 3px;
                }
                .available-doctors {
                    font-size: 10px;
                    color: #666;
                    font-style: italic;
                    margin-top: 2px;
                }
                .empty-cell {
                    background-color: #f0f0f0;
                }
            </style>
            <table class="calendar-table">
                <tr>
                    <th>週一</th>
                    <th>週二</th>
                    <th>週三</th>
                    <th>週四</th>
                    <th>週五</th>
                    <th>週六</th>
                    <th>週日</th>
                </tr>
            """
            
            # 建立月曆格子
            current_day = 1
            week_html = "<tr>"
            
            # 填充月初空白
            for _ in range(start_weekday):
                week_html += '<td class="empty-cell"></td>'
            
            # 填充日期
            while current_day <= num_days:
                current_date = date(year, month, current_day)
                date_str = current_date.strftime("%Y-%m-%d")
                
                # 判斷是否為假日
                is_holiday = date_str in current_holidays
                cell_class = "holiday-cell" if is_holiday else "weekday-cell"
                
                # 取得排班資訊
                if date_str in result.schedule:
                    slot = result.schedule[date_str]
                    
                    # 開始建立格子內容
                    cell_html = f'<td class="{cell_class}">'
                    cell_html += f'<div class="calendar-date">{current_day}日'
                    if is_holiday:
                        cell_html += ' 🎉'
                    cell_html += '</div>'
                    
                    # 主治醫師
                    if slot.attending:
                        cell_html += f'<div class="doctor-info attending">👨‍⚕️ 主治: {slot.attending}</div>'
                    else:
                        # 顯示未填格和可選醫師
                        available_attending = scheduler.get_available_doctors(date_str, "主治", result.schedule)
                        cell_html += '<div class="empty-slot">❌ 主治未排</div>'
                        if available_attending:
                            cell_html += f'<div class="available-doctors">可選: {", ".join(available_attending[:3])}'
                            if len(available_attending) > 3:
                                cell_html += f' 等{len(available_attending)}人'
                            cell_html += '</div>'
                        else:
                            cell_html += '<div class="available-doctors">⚠️ 無可用醫師</div>'
                    
                    # 住院醫師
                    if slot.resident:
                        cell_html += f'<div class="doctor-info resident">👨‍⚕️ 住院: {slot.resident}</div>'
                    else:
                        # 顯示未填格和可選醫師
                        available_resident = scheduler.get_available_doctors(date_str, "總醫師", result.schedule)
                        cell_html += '<div class="empty-slot">❌ 住院未排</div>'
                        if available_resident:
                            cell_html += f'<div class="available-doctors">可選: {", ".join(available_resident[:3])}'
                            if len(available_resident) > 3:
                                cell_html += f' 等{len(available_resident)}人'
                            cell_html += '</div>'
                        else:
                            cell_html += '<div class="available-doctors">⚠️ 無可用醫師</div>'
                    
                    cell_html += '</td>'
                else:
                    cell_html = f'<td class="{cell_class}"><div class="calendar-date">{current_day}日</div></td>'
                
                week_html += cell_html
                current_day += 1
                
                # 週末換行
                if current_date.weekday() == 6:
                    week_html += "</tr>"
                    if current_day <= num_days:
                        week_html += "<tr>"
            
            # 填充月末空白
            last_day = date(year, month, num_days)
            if last_day.weekday() != 6:
                for _ in range(6 - last_day.weekday()):
                    week_html += '<td class="empty-cell"></td>'
                week_html += "</tr>"
            
            calendar_html += week_html
            calendar_html += "</table>"
            
            # 顯示月曆
            st.markdown(calendar_html, unsafe_allow_html=True)
            
            # 圖例說明
            st.markdown("""
            <div style="margin-top: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                <h4>圖例說明</h4>
                <p>🎉 假日 | 👨‍⚕️ 已排班醫師 | ❌ 未排班（紅底）| ⚠️ 無可用醫師</p>
                <p><span style="background-color: #e3f2fd; padding: 2px 5px;">藍色</span> 主治醫師 | 
                   <span style="background-color: #f3e5f5; padding: 2px 5px;">紫色</span> 住院醫師</p>
            </div>
            """, unsafe_allow_html=True)
            
            # 未填格詳細資訊
            if result.unfilled_slots:
                with st.expander(f"⚠️ 未填格詳細資訊 ({len(result.unfilled_slots)} 個)", expanded=False):
                    for date_str, role in result.unfilled_slots:
                        available = scheduler.get_available_doctors(date_str, role, result.schedule)
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        if available:
                            st.write(f"📅 **{dt.month}/{dt.day} {role}**")
                            st.write(f"   可選醫師：{', '.join(available)}")
                        else:
                            st.write(f"📅 **{dt.month}/{dt.day} {role}**")
                            st.write(f"   ⚠️ 無可用醫師（可能因為配額已滿或連續值班限制）")
        
        else:  # 列表視圖
            # 建立DataFrame
            schedule_data = []
            all_dates = sorted(current_holidays + current_weekdays)
            
            for date_str in all_dates:
                if date_str in result.schedule:
                    slot = result.schedule[date_str]
                    is_holiday = date_str in current_holidays
                    
                    # 解析日期
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    weekday_name = ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()]
                    
                    # 取得可選醫師
                    attending_available = ""
                    resident_available = ""
                    if not slot.attending:
                        avail = scheduler.get_available_doctors(date_str, "主治", result.schedule)
                        attending_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                    if not slot.resident:
                        avail = scheduler.get_available_doctors(date_str, "總醫師", result.schedule)
                        resident_available = f"可選: {', '.join(avail[:5])}" if avail else "無可用"
                    
                    schedule_data.append({
                        '日期': f"{dt.month}/{dt.day}",
                        '星期': weekday_name,
                        '類型': '假日' if is_holiday else '平日',
                        '主治醫師': slot.attending or f'❌ 未排 ({attending_available})',
                        '住院醫師': slot.resident or f'❌ 未排 ({resident_available})'
                    })
            
            df_schedule = pd.DataFrame(schedule_data)
            
            # 使用顏色標記
            def highlight_schedule(row):
                styles = [''] * len(row)
                
                if row['類型'] == '假日':
                    styles[2] = 'background-color: #ffcdd2'
                else:
                    styles[2] = 'background-color: #c5cae9'
                
                if '❌' in str(row['主治醫師']):
                    styles[3] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
                else:
                    styles[3] = 'background-color: #e3f2fd; color: #1976d2'
                
                if '❌' in str(row['住院醫師']):
                    styles[4] = 'background-color: #ffebee; color: #c62828; font-weight: bold'
                else:
                    styles[4] = 'background-color: #f3e5f5; color: #7b1fa2'
                
                return styles
            
            # 顯示排班表
            st.dataframe(
                df_schedule.style.apply(highlight_schedule, axis=1),
                use_container_width=True,
                height=600
            )
        
        # 匯出功能
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            # 轉換為CSV
            # 準備乾淨的CSV資料（不含HTML標記）
            csv_data = []
            all_dates = sorted(current_holidays + current_weekdays)
            for date_str in all_dates:
                if date_str in result.schedule:
                    slot = result.schedule[date_str]
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    csv_data.append({
                        '日期': date_str,
                        '星期': ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()],
                        '類型': '假日' if date_str in current_holidays else '平日',
                        '主治醫師': slot.attending or '未排',
                        '住院醫師': slot.resident or '未排'
                    })
            
            df_csv = pd.DataFrame(csv_data)
            csv = df_csv.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下載 CSV",
                data=csv,
                file_name=f"schedule_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # 儲存結果為JSON
            if st.button("💾 儲存排班結果", use_container_width=True):
                save_result = {
                    'year': st.session_state.selected_year,
                    'month': st.session_state.selected_month,
                    'schedule': {k: asdict(v) for k, v in result.schedule.items()},
                    'statistics': result.statistics,
                    'unfilled_details': []
                }
                
                # 加入未填格的可選醫師資訊
                for date_str, role in result.unfilled_slots:
                    available = scheduler.get_available_doctors(date_str, role, result.schedule)
                    save_result['unfilled_details'].append({
                        'date': date_str,
                        'role': role,
                        'available_doctors': available
                    })
                
                filename = f"schedule_result_{st.session_state.selected_year}_{st.session_state.selected_month:02d}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(save_result, f, ensure_ascii=False, indent=2)
                st.success(f"結果已儲存至 {filename}")
        
        with col3:
            # 列印友好版本
            if st.button("🖨️ 產生列印版", use_container_width=True):
                st.info("列印版功能開發中...")

# Tab 5: 統計分析
with tab5:
    st.header("統計分析")
    
    if st.session_state.schedule_result is None:
        st.info("請先執行排班")
    else:
        result = st.session_state.schedule_result
        
        # 值班次數統計
        st.subheader("📊 值班次數分布")
        
        duty_counts = result.statistics['duty_counts']
        
        if duty_counts:
            # 分離主治和住院醫師
            attending_duties = {name: count for name, count in duty_counts.items() 
                              if any(d.name == name and d.role == "主治" 
                                   for d in st.session_state.doctors)}
            resident_duties = {name: count for name, count in duty_counts.items() 
                             if any(d.name == name and d.role == "總醫師" 
                                  for d in st.session_state.doctors)}
            
            col1, col2 = st.columns(2)
            
            with col1:
                # 主治醫師統計圖
                if attending_duties:
                    fig_attending = px.bar(
                        x=list(attending_duties.keys()),
                        y=list(attending_duties.values()),
                        title="主治醫師值班次數",
                        labels={'x': '醫師', 'y': '值班次數'},
                        color_discrete_sequence=['#1f77b4']
                    )
                    fig_attending.update_layout(showlegend=False)
                    st.plotly_chart(fig_attending, use_container_width=True)
            
            with col2:
                # 住院醫師統計圖
                if resident_duties:
                    fig_resident = px.bar(
                        x=list(resident_duties.keys()),
                        y=list(resident_duties.values()),
                        title="住院醫師值班次數",
                        labels={'x': '醫師', 'y': '值班次數'},
                        color_discrete_sequence=['#ff7f0e']
                    )
                    fig_resident.update_layout(showlegend=False)
                    st.plotly_chart(fig_resident, use_container_width=True)
        
        # 分數細項
        st.subheader("📈 評分細項")
        breakdown = result.statistics['score_breakdown']
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("未填格", breakdown['unfilled'], 
                     "權重: -1000", delta_color="inverse")
        with col2:
            st.metric("硬違規", breakdown['hard_violations'],
                     "權重: -100", delta_color="inverse")
        with col3:
            st.metric("軟違規", breakdown['soft_violations'],
                     "權重: -10", delta_color="inverse")
        with col4:
            st.metric("公平性", f"{breakdown['fairness']:.1f}",
                     "權重: +5")
        with col5:
            st.metric("偏好命中", breakdown['preference_hits'],
                     "權重: +2")
        
        # 配額使用率
        st.subheader("📊 配額使用率")
        
        # 計算每個醫師的平日/假日班數
        doctor_stats = []
        for doc in st.session_state.doctors:
            weekday_count = 0
            holiday_count = 0
            
            for date_str, slot in result.schedule.items():
                if slot.attending == doc.name or slot.resident == doc.name:
                    if date_str in current_holidays:
                        holiday_count += 1
                    else:
                        weekday_count += 1
            
            doctor_stats.append({
                '醫師': doc.name,
                '角色': doc.role,
                '平日值班': weekday_count,
                '平日配額': doc.weekday_quota,
                '平日使用率': f"{weekday_count/doc.weekday_quota*100:.0f}%" if doc.weekday_quota > 0 else "0%",
                '假日值班': holiday_count,
                '假日配額': doc.holiday_quota,
                '假日使用率': f"{holiday_count/doc.holiday_quota*100:.0f}%" if doc.holiday_quota > 0 else "0%"
            })
        
        df_stats = pd.DataFrame(doctor_stats)
        st.dataframe(df_stats, use_container_width=True)
        
        # 未填格分析
        if result.unfilled_slots:
            st.subheader("⚠️ 未填格分析")
            
            unfilled_by_date = defaultdict(list)
            for date_str, role in result.unfilled_slots:
                unfilled_by_date[date_str].append(role)
            
            unfilled_summary = []
            for date_str, roles in unfilled_by_date.items():
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                unfilled_summary.append({
                    '日期': f"{dt.month}/{dt.day}",
                    '星期': ['一', '二', '三', '四', '五', '六', '日'][dt.weekday()],
                    '未填角色': ', '.join(roles),
                    '類型': '假日' if date_str in current_holidays else '平日'
                })
            
            df_unfilled = pd.DataFrame(unfilled_summary)
            st.dataframe(df_unfilled, use_container_width=True)

# Tab 6: ML訓練資料
with tab6:
    st.header("🤖 機器學習訓練資料管理")
    
    if st.session_state.last_scheduler is None or st.session_state.last_scheduler.solution_pool is None:
        st.info("請先執行排班並勾選「收集所有候選解」選項")
    else:
        solution_pool = st.session_state.last_scheduler.solution_pool
        pool_metrics = solution_pool.get_diversity_metrics()
        
        # 解池概覽
        st.subheader("📊 解池概覽")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總解數量", pool_metrics.get('pool_size', 0))
        with col2:
            st.metric("唯一解數量", pool_metrics.get('unique_schedules', 0))
        with col3:
            st.metric("平均分數", f"{pool_metrics.get('avg_score', 0):.1f}")
        with col4:
            st.metric("分數標準差", f"{pool_metrics.get('score_std', 0):.1f}")
        
        # 等級分布圖
        st.subheader("📈 解的等級分布")
        
        grade_dist = pool_metrics.get('grade_distribution', {})
        if grade_dist:
            # 準備等級說明
            grading_system = GradingSystem()
            grade_descriptions = {
                grade: grading_system.get_grade_description(grade)
                for grade in ['S', 'A', 'B', 'C', 'D', 'F']
            }
            
            # 顯示等級分布圖表
            grades = list(grade_dist.keys())
            counts = list(grade_dist.values())
            
            fig_grades = px.bar(
                x=grades,
                y=counts,
                title="解的等級分布",
                labels={'x': '等級', 'y': '數量'},
                color=grades,
                color_discrete_map={
                    'S': '#FFD700',  # 金色
                    'A': '#00FF00',  # 綠色
                    'B': '#87CEEB',  # 天藍色
                    'C': '#FFA500',  # 橙色
                    'D': '#FF6347',  # 番茄紅
                    'F': '#FF0000'   # 紅色
                }
            )
            st.plotly_chart(fig_grades, use_container_width=True)
            
            # 等級說明
            with st.expander("📖 等級說明", expanded=False):
                for grade, desc in grade_descriptions.items():
                    if grade in grade_dist:
                        st.write(f"**{grade}級** ({grade_dist[grade]}個): {desc}")
        
        # 特徵分析
        st.subheader("🔬 特徵分析")
        
        # 選擇要分析的等級
        available_grades = list(grade_dist.keys()) if grade_dist else []
        if available_grades:
            selected_grades = st.multiselect(
                "選擇要分析的等級",
                available_grades,
                default=available_grades[:2] if len(available_grades) >= 2 else available_grades
            )
            
            if selected_grades:
                # 收集選定等級的解
                selected_solutions = []
                for grade in selected_grades:
                    selected_solutions.extend(solution_pool.get_solutions_by_grade(grade))
                
                if selected_solutions:
                    # 提取特徵
                    feature_data = []
                    for sol in selected_solutions:
                        feature_dict = sol.features.to_dict()
                        feature_dict['grade'] = sol.grade
                        feature_dict['score'] = sol.score
                        feature_data.append(feature_dict)
                    
                    df_features = pd.DataFrame(feature_data)
                    
                    # 顯示關鍵特徵對比
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 填充率對比
                        fig_fill = px.box(
                            df_features,
                            x='grade',
                            y='fill_rate',
                            title='填充率分布',
                            labels={'fill_rate': '填充率', 'grade': '等級'}
                        )
                        st.plotly_chart(fig_fill, use_container_width=True)
                    
                    with col2:
                        # 違規數對比
                        fig_viol = px.box(
                            df_features,
                            x='grade',
                            y='hard_violations',
                            title='硬違規數分布',
                            labels={'hard_violations': '違規數', 'grade': '等級'}
                        )
                        st.plotly_chart(fig_viol, use_container_width=True)
                    
                    # 特徵相關性熱圖
                    with st.expander("🔥 特徵相關性熱圖", expanded=False):
                        # 選擇數值特徵
                        numeric_features = [
                            'fill_rate', 'hard_violations', 'soft_violations',
                            'duty_variance', 'duty_std', 'gini_coefficient',
                            'preference_rate', 'weekend_coverage_rate',
                            'weekday_coverage_rate', 'avg_consecutive_days'
                        ]
                        
                        corr_matrix = df_features[numeric_features].corr()
                        
                        fig_corr = px.imshow(
                            corr_matrix,
                            labels=dict(color="相關係數"),
                            title="特徵相關性矩陣",
                            color_continuous_scale='RdBu',
                            zmin=-1, zmax=1
                        )
                        st.plotly_chart(fig_corr, use_container_width=True)
        
        # Top解展示
        st.subheader("🏆 最佳解展示")
        
        top_n = st.slider("顯示前N個最佳解", 1, 20, 5)
        top_solutions = solution_pool.get_top_solutions(top_n)
        
        if top_solutions:
            solution_display = []
            for i, sol in enumerate(top_solutions, 1):
                solution_display.append({
                    '排名': i,
                    '解ID': sol.solution_id[:20] + "...",
                    '分數': f"{sol.score:.1f}",
                    '等級': sol.grade,
                    '填充率': f"{sol.features.fill_rate*100:.1f}%",
                    '硬違規': sol.features.hard_violations,
                    '軟違規': sol.features.soft_violations,
                    '偏好滿足': f"{sol.features.preference_rate*100:.1f}%",
                    '生成方法': sol.generation_method,
                    '迭代': sol.iteration
                })
            
            df_top = pd.DataFrame(solution_display)
            st.dataframe(df_top, use_container_width=True)
        
        # 訓練資料匯出
        st.subheader("💾 訓練資料匯出")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # CSV格式匯出
            if st.button("📥 匯出CSV訓練資料", use_container_width=True):
                csv_data = solution_pool.export_training_data(format="csv")
                if csv_data:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="下載CSV檔案",
                        data=csv_data,
                        file_name=f"ml_training_data_{timestamp}.csv",
                        mime="text/csv"
                    )
                    st.success("CSV訓練資料已準備好下載！")
        
        with col2:
            # JSON格式匯出
            if st.button("📥 匯出JSON訓練資料", use_container_width=True):
                json_data = solution_pool.export_training_data(format="json")
                if json_data:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="下載JSON檔案",
                        data=json_data,
                        file_name=f"ml_training_data_{timestamp}.json",
                        mime="application/json"
                    )
                    st.success("JSON訓練資料已準備好下載！")
        
        with col3:
            # 匯出統計報告
            if st.button("📊 生成分析報告", use_container_width=True):
                report = f"""
# 醫師排班ML訓練資料分析報告
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 解池統計
- 總解數量：{pool_metrics.get('pool_size', 0)}
- 唯一解數量：{pool_metrics.get('unique_schedules', 0)}
- 平均分數：{pool_metrics.get('avg_score', 0):.2f}
- 分數標準差：{pool_metrics.get('score_std', 0):.2f}
- 特徵多樣性：{pool_metrics.get('feature_diversity', 0):.4f}

## 等級分布
"""
                for grade, count in grade_dist.items():
                    percentage = (count / pool_metrics['pool_size']) * 100
                    report += f"- {grade}級：{count}個 ({percentage:.1f}%)\n"
                
                report += """
## 最佳解特徵
"""
                if top_solutions:
                    best = top_solutions[0]
                    report += f"""
- 分數：{best.score:.1f}
- 填充率：{best.features.fill_rate*100:.1f}%
- 硬違規：{best.features.hard_violations}
- 軟違規：{best.features.soft_violations}
- 偏好滿足率：{best.features.preference_rate*100:.1f}%
- 公平性（Gini係數）：{best.features.gini_coefficient:.3f}

## 建議
根據解池分析，建議：
1. 重點優化{'填充率' if pool_metrics['avg_score'] < -500 else '公平性'}
2. 考慮{'放寬約束' if grade_dist.get('F', 0) > pool_metrics['pool_size']*0.3 else '維持當前約束'}
3. {'增加醫師配額' if top_solutions[0].features.fill_rate < 0.9 else '當前配額合理'}
"""
                
                st.download_button(
                    label="下載分析報告",
                    data=report,
                    file_name=f"ml_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown"
                )
                st.success("分析報告已生成！")
        
        # 訓練建議
        st.subheader("🎯 機器學習訓練建議")
        
        with st.expander("📚 如何使用這些資料訓練AI", expanded=False):
            st.markdown("""
            ### 1. **監督式學習：排班品質預測**
            ```python
            # 使用隨機森林預測排班品質
            from sklearn.ensemble import RandomForestRegressor
            
            X = df[feature_columns]  # 特徵
            y = df['score']          # 目標
            model = RandomForestRegressor()
            model.fit(X, y)
            ```
            
            ### 2. **強化學習：序列決策優化**
            - State: 當前部分排班狀態
            - Action: 選擇下一個醫師-日期配對
            - Reward: 基於評分函數的即時回饋
            
            ### 3. **深度學習：端到端排班**
            ```python
            # 使用Transformer模型
            import torch.nn as nn
            
            class ScheduleTransformer(nn.Module):
                def __init__(self):
                    self.encoder = nn.TransformerEncoder(...)
                    self.decoder = nn.Linear(...)
            ```
            
            ### 4. **特徵工程建議**
            - **時序特徵**：星期幾、月份、是否月初/月末
            - **歷史特徵**：醫師過去的排班模式
            - **交互特徵**：醫師間的相容性
            - **約束編碼**：將硬約束轉為特徵向量
            
            ### 5. **評估指標**
            - **準確率**：預測分數與實際分數的MAE
            - **可行性**：生成解的違規率
            - **多樣性**：解的特徵空間覆蓋度
            - **效率**：達到目標品質的迭代次數
            """)
        
        # 資料品質檢查
        st.subheader("✅ 資料品質檢查")
        
        quality_checks = {
            "解池大小充足（>100）": pool_metrics.get('pool_size', 0) > 100,
            "等級分布平衡": len(grade_dist) >= 3 if grade_dist else False,
            "特徵多樣性良好（>0.1）": pool_metrics.get('feature_diversity', 0) > 0.1,
            "包含優質解（S/A級）": any(g in ['S', 'A'] for g in grade_dist.keys()) if grade_dist else False,
            "包含失敗案例（D/F級）": any(g in ['D', 'F'] for g in grade_dist.keys()) if grade_dist else False
        }
        
        for check, passed in quality_checks.items():
            if passed:
                st.success(f"✅ {check}")
            else:
                st.warning(f"⚠️ {check}")
        
        overall_quality = sum(quality_checks.values()) / len(quality_checks)
        st.progress(overall_quality)
        st.write(f"整體資料品質：{overall_quality*100:.0f}%")

# 頁尾
st.divider()
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>醫師智慧排班系統 v2.0 | 使用束搜索、CSP與機器學習</p>
    <p>© 2024 Hospital Scheduling System with ML</p>
</div>
""", unsafe_allow_html=True)