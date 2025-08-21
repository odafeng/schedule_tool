"""
解池管理器
"""
import copy
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter
import pandas as pd
import numpy as np

from ..models import Doctor, ScheduleSlot, ScheduleConstraints, SolutionRecord
from ..analyzers import FeatureExtractor, GradingSystem

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
                     parent_id: Optional[str] = None) -> str:
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
                tuple(sorted(
                    (date, (slot.attending, slot.resident))
                    for date, slot in s.schedule.items()
                )) 
                for s in self.solution_pool
            ))
        }