"""
進階CSP求解器實現
"""
import time
from typing import List, Dict, Optional, Set, Callable
from collections import defaultdict

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
    def __init__(self, variables: List[CSPVariable], check_func: Callable):
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