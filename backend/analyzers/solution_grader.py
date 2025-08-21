"""
解決方案分級系統
"""
from ..models import SolutionFeatures

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