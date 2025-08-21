"""
訓練資料生成器
"""
from typing import List, Dict
import pandas as pd
import numpy as np

from ..models import SolutionRecord

class TrainingDataGenerator:
    """ML訓練資料生成器"""
    
    def __init__(self, solution_pool: List[SolutionRecord]):
        self.solution_pool = solution_pool
    
    def generate_supervised_dataset(self) -> pd.DataFrame:
        """生成監督式學習資料集"""
        if not self.solution_pool:
            return pd.DataFrame()
        
        records = []
        for solution in self.solution_pool:
            record = solution.to_training_record()
            records.append(record)
        
        df = pd.DataFrame(records)
        
        # 添加衍生特徵
        df = self._add_derived_features(df)
        
        return df
    
    def generate_reinforcement_dataset(self) -> Dict:
        """生成強化學習資料集"""
        trajectories = []
        
        # 按parent_id組織軌跡
        solution_map = {s.solution_id: s for s in self.solution_pool}
        
        for solution in self.solution_pool:
            if solution.parent_id is None:
                # 找到一條完整軌跡
                trajectory = self._build_trajectory(solution, solution_map)
                if len(trajectory) > 1:
                    trajectories.append(trajectory)
        
        return {
            'trajectories': trajectories,
            'state_dim': len(self.solution_pool[0].features.to_vector()) if self.solution_pool else 0,
            'num_trajectories': len(trajectories)
        }
    
    def _add_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加衍生特徵"""
        # 效率指標
        df['efficiency'] = df['fill_rate'] / (df['hard_violations'] + 1)
        
        # 平衡指標
        df['balance_score'] = 1 / (df['duty_std'] + 1)
        
        # 質量綜合指標
        df['quality_index'] = (
            df['fill_rate'] * 0.4 +
            (1 - df['hard_violations'] / df['hard_violations'].max()) * 0.3 +
            df['preference_rate'] * 0.2 +
            df['balance_score'] / df['balance_score'].max() * 0.1
        )
        
        # 分類特徵編碼
        df['grade_encoded'] = df['grade'].map({
            'S': 5, 'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0
        })
        
        return df
    
    def _build_trajectory(self, start_solution: SolutionRecord, 
                         solution_map: Dict[str, SolutionRecord]) -> List:
        """構建解的軌跡"""
        trajectory = []
        current = start_solution
        
        while current:
            trajectory.append({
                'state': current.features.to_vector(),
                'score': current.score,
                'iteration': current.iteration
            })
            
            # 找下一個
            next_solutions = [s for s in self.solution_pool 
                            if s.parent_id == current.solution_id]
            
            if next_solutions:
                # 選擇分數最高的繼續
                current = max(next_solutions, key=lambda x: x.score)
            else:
                current = None
        
        return trajectory