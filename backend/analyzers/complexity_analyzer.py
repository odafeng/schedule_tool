"""
問題複雜度分析器 - 改進版
"""
from typing import List, Dict, Set, Tuple
import numpy as np
from collections import defaultdict

from ..models import Doctor

class ComplexityAnalyzer:
    """分析排班問題的複雜度"""
    
    def analyze(self, doctors: List[Doctor], weekdays: List[str], 
                holidays: List[str]) -> Dict:
        """
        分析排班問題的複雜度
        
        Returns:
            複雜度分析結果
        """
        # 基本統計
        total_days = len(weekdays) + len(holidays)
        all_dates = set(weekdays + holidays)
        
        # 分角色
        attending_doctors = [d for d in doctors if d.role == "主治"]
        resident_doctors = [d for d in doctors if d.role == "總醫師"]
        
        # 1. 計算分角色的供需比
        supply_demand = self._calculate_role_based_supply_demand(
            attending_doctors, resident_doctors, weekdays, holidays
        )
        
        # 2. 計算當月約束密度
        constraint_metrics = self._calculate_constraint_metrics(
            doctors, all_dates
        )
        
        # 3. 計算逐天搜索空間
        search_space = self._calculate_daily_search_space(
            attending_doctors, resident_doctors, weekdays, holidays, all_dates
        )
        
        # 4. 評估難度（相對化閾值）
        difficulty = self._assess_relative_difficulty(
            supply_demand, constraint_metrics, search_space
        )
        
        # 5. 精確可行性檢查
        feasibility = self._check_detailed_feasibility(
            attending_doctors, resident_doctors, weekdays, holidays, all_dates
        )
        
        # 6. 智慧瓶頸偵測
        bottlenecks = self._identify_smart_bottlenecks(
            attending_doctors, resident_doctors, weekdays, holidays, 
            all_dates, search_space
        )
        
        return {
            'total_days': total_days,
            'total_slots': total_days * 2,
            'attending_count': len(attending_doctors),
            'resident_count': len(resident_doctors),
            
            # 供需比（分角色）
            'weekday_attending_ratio': supply_demand['weekday_attending_ratio'],
            'weekday_resident_ratio': supply_demand['weekday_resident_ratio'],
            'holiday_attending_ratio': supply_demand['holiday_attending_ratio'],
            'holiday_resident_ratio': supply_demand['holiday_resident_ratio'],
            'min_supply_ratio': supply_demand['min_ratio'],  # 瓶頸指標
            
            # 約束密度
            'constraint_density': constraint_metrics['density'],
            'max_personal_conflict': constraint_metrics['max_personal_conflict'],
            
            # 搜索空間
            'search_space_log10': search_space['total_log_space'],
            'hardest_days_count': search_space['hardest_days_count'],
            'median_daily_options': search_space['median_options'],
            
            # 難度與可行性
            'difficulty': difficulty,
            'is_feasible': feasibility['overall'],
            'feasibility_details': feasibility,
            
            # 瓶頸
            'bottlenecks': bottlenecks
        }
    
    def _calculate_role_based_supply_demand(self, attending: List[Doctor], 
                                           resident: List[Doctor],
                                           weekdays: List[str], 
                                           holidays: List[str]) -> Dict:
        """計算分角色的供需比"""
        # 需求（每天每角色1人）
        weekday_demand_per_role = len(weekdays)
        holiday_demand_per_role = len(holidays)
        
        # 供給（分角色統計）
        weekday_attending_supply = sum(d.weekday_quota for d in attending)
        weekday_resident_supply = sum(d.weekday_quota for d in resident)
        holiday_attending_supply = sum(d.holiday_quota for d in attending)
        holiday_resident_supply = sum(d.holiday_quota for d in resident)
        
        # 計算比值（避免除以0）
        ratios = {
            'weekday_attending_ratio': (weekday_attending_supply / weekday_demand_per_role 
                                       if weekday_demand_per_role > 0 else 0),
            'weekday_resident_ratio': (weekday_resident_supply / weekday_demand_per_role 
                                      if weekday_demand_per_role > 0 else 0),
            'holiday_attending_ratio': (holiday_attending_supply / holiday_demand_per_role 
                                      if holiday_demand_per_role > 0 else 0),
            'holiday_resident_ratio': (holiday_resident_supply / holiday_demand_per_role 
                                     if holiday_demand_per_role > 0 else 0)
        }
        
        # 找出最小值（瓶頸）
        non_zero_ratios = [r for r in ratios.values() if r > 0]
        ratios['min_ratio'] = min(non_zero_ratios) if non_zero_ratios else 0
        
        return ratios
    
    def _calculate_constraint_metrics(self, doctors: List[Doctor], 
                                     all_dates: Set[str]) -> Dict:
        """計算當月約束密度"""
        if not doctors or not all_dates:
            return {'density': 0, 'max_personal_conflict': 0}
        
        # 只計算當月的不可值班日
        monthly_conflicts = []
        for doctor in doctors:
            # 交集：該醫師的不可值班日與當月日期
            doctor_monthly_unavailable = set(doctor.unavailable_dates) & all_dates
            conflict_ratio = len(doctor_monthly_unavailable) / len(all_dates)
            monthly_conflicts.append(conflict_ratio)
        
        # 整體密度
        total_unavailable = sum(
            len(set(d.unavailable_dates) & all_dates) 
            for d in doctors
        )
        density = total_unavailable / (len(doctors) * len(all_dates))
        
        return {
            'density': density,
            'max_personal_conflict': max(monthly_conflicts) if monthly_conflicts else 0,
            'conflict_distribution': monthly_conflicts
        }
    
    def _calculate_daily_search_space(self, attending: List[Doctor], 
                                     resident: List[Doctor],
                                     weekdays: List[str], 
                                     holidays: List[str],
                                     all_dates: Set[str]) -> Dict:
        """計算逐天搜索空間"""
        daily_options = []
        daily_log_space = []
        hardest_days = []
        
        for date in weekdays + holidays:
            # 計算當天可值班的醫師數（考慮不可值班日）
            available_attending = [
                d for d in attending 
                if date not in d.unavailable_dates
            ]
            available_resident = [
                d for d in resident 
                if date not in d.unavailable_dates
            ]
            
            a_count = len(available_attending)
            r_count = len(available_resident)
            
            # 當天的總選項數
            day_options = a_count * r_count if a_count > 0 and r_count > 0 else 0
            daily_options.append(day_options)
            
            # 當天的對數搜索空間
            day_log = (np.log10(max(a_count, 1)) + np.log10(max(r_count, 1)))
            daily_log_space.append(day_log)
            
            # 記錄困難日（選項少於3的日子）
            if day_options < 3:
                hardest_days.append({
                    'date': date,
                    'attending_available': a_count,
                    'resident_available': r_count,
                    'total_options': day_options
                })
        
        # 統計指標
        if daily_options:
            percentiles = np.percentile(daily_options, [10, 25, 50, 75, 90])
            median_options = np.median(daily_options)
        else:
            percentiles = [0, 0, 0, 0, 0]
            median_options = 0
        
        return {
            'total_log_space': sum(daily_log_space),
            'daily_options': daily_options,
            'hardest_days': hardest_days,
            'hardest_days_count': len(hardest_days),
            'percentiles': {
                'p10': percentiles[0],
                'p25': percentiles[1],
                'p50': percentiles[2],
                'p75': percentiles[3],
                'p90': percentiles[4]
            },
            'median_options': median_options
        }
    
    def _assess_relative_difficulty(self, supply_demand: Dict, 
                                   constraint_metrics: Dict,
                                   search_space: Dict) -> str:
        """評估相對難度（使用相對化閾值）"""
        score = 0
        
        # 1. 供需比評分（最小比值）
        min_ratio = supply_demand['min_ratio']
        if min_ratio < 1.0:
            score += 4  # 不可行
        elif min_ratio < 1.2:
            score += 3  # 極緊
        elif min_ratio < 1.5:
            score += 2  # 緊張
        elif min_ratio < 2.0:
            score += 1  # 略緊
        
        # 2. 最困難日數評分
        hardest_count = search_space['hardest_days_count']
        total_days = len(search_space['daily_options'])
        hardest_ratio = hardest_count / total_days if total_days > 0 else 0
        
        if hardest_ratio > 0.3:
            score += 3  # 很多困難日
        elif hardest_ratio > 0.2:
            score += 2
        elif hardest_ratio > 0.1:
            score += 1
        
        # 3. 選項中位數評分
        median_options = search_space['median_options']
        if median_options < 5:
            score += 3  # 選擇極少
        elif median_options < 10:
            score += 2
        elif median_options < 20:
            score += 1
        
        # 4. 約束密度評分
        if constraint_metrics['density'] > 0.3:
            score += 2
        elif constraint_metrics['density'] > 0.2:
            score += 1
        
        # 判定難度
        if score >= 10:
            return "極困難"
        elif score >= 7:
            return "困難"
        elif score >= 4:
            return "中等"
        else:
            return "簡單"
    
    def _check_detailed_feasibility(self, attending: List[Doctor], 
                                   resident: List[Doctor],
                                   weekdays: List[str], 
                                   holidays: List[str],
                                   all_dates: Set[str]) -> Dict:
        """精確可行性檢查"""
        results = {
            'overall': True,
            'weekday_attending': True,
            'weekday_resident': True,
            'holiday_attending': True,
            'holiday_resident': True,
            'daily_gaps': []
        }
        
        # 檢查總供給
        weekday_attending_supply = sum(d.weekday_quota for d in attending)
        weekday_resident_supply = sum(d.weekday_quota for d in resident)
        holiday_attending_supply = sum(d.holiday_quota for d in attending)
        holiday_resident_supply = sum(d.holiday_quota for d in resident)
        
        if weekday_attending_supply < len(weekdays):
            results['weekday_attending'] = False
            results['overall'] = False
        
        if weekday_resident_supply < len(weekdays):
            results['weekday_resident'] = False
            results['overall'] = False
        
        if holiday_attending_supply < len(holidays):
            results['holiday_attending'] = False
            results['overall'] = False
        
        if holiday_resident_supply < len(holidays):
            results['holiday_resident'] = False
            results['overall'] = False
        
        # 檢查逐天可行性
        for date in weekdays + holidays:
            available_attending = sum(
                1 for d in attending 
                if date not in d.unavailable_dates
            )
            available_resident = sum(
                1 for d in resident 
                if date not in d.unavailable_dates
            )
            
            if available_attending == 0 or available_resident == 0:
                results['daily_gaps'].append({
                    'date': date,
                    'type': '平日' if date in weekdays else '假日',
                    'attending': available_attending,
                    'resident': available_resident
                })
                results['overall'] = False
        
        return results
    
    def _identify_smart_bottlenecks(self, attending: List[Doctor], 
                                   resident: List[Doctor],
                                   weekdays: List[str], 
                                   holidays: List[str],
                                   all_dates: Set[str],
                                   search_space: Dict) -> List[str]:
        """智慧瓶頸偵測"""
        bottlenecks = []
        
        # 1. 角色人數瓶頸（基於p10）
        if search_space['percentiles']['p10'] < 3:
            bottlenecks.append(
                f"至少10%的日子只有不到3個排班選項（p10={search_space['percentiles']['p10']:.0f}）"
            )
        
        # 2. 特定角色短缺
        if len(attending) == 0:
            bottlenecks.append("無主治醫師")
        elif len(attending) < len(weekdays) / 7:  # 平均每人需值7天以上
            bottlenecks.append(f"主治醫師人數偏少（{len(attending)}人需覆蓋{len(weekdays)}個平日）")
        
        if len(resident) == 0:
            bottlenecks.append("無住院醫師")
        elif len(resident) < len(weekdays) / 7:
            bottlenecks.append(f"住院醫師人數偏少（{len(resident)}人需覆蓋{len(weekdays)}個平日）")
        
        # 3. 配額瓶頸（需求基準化）
        for role, doctors_list in [("主治", attending), ("住院", resident)]:
            if doctors_list:
                avg_weekday_quota = np.mean([d.weekday_quota for d in doctors_list])
                avg_holiday_quota = np.mean([d.holiday_quota for d in doctors_list])
                
                needed_weekday_avg = len(weekdays) / len(doctors_list)
                needed_holiday_avg = len(holidays) / len(doctors_list)
                
                if avg_weekday_quota < needed_weekday_avg * 0.8:
                    bottlenecks.append(
                        f"{role}醫師平均平日配額不足（平均{avg_weekday_quota:.1f}，需要{needed_weekday_avg:.1f}）"
                    )
                
                if holidays and avg_holiday_quota < needed_holiday_avg * 0.8:
                    bottlenecks.append(
                        f"{role}醫師平均假日配額不足（平均{avg_holiday_quota:.1f}，需要{needed_holiday_avg:.1f}）"
                    )
        
        # 4. 個人高衝突（在困難日的不可值班）
        if search_space['hardest_days']:
            hardest_dates = {d['date'] for d in search_space['hardest_days']}
            
            for doctor in attending + resident:
                conflicts_in_hard_days = set(doctor.unavailable_dates) & hardest_dates
                if len(conflicts_in_hard_days) > len(hardest_dates) * 0.5:
                    bottlenecks.append(
                        f"{doctor.name}在{len(hardest_dates)}個困難日中有{len(conflicts_in_hard_days)}天不可值班"
                    )
        
        # 5. 特定日期無人可排
        for gap in search_space['hardest_days']:
            if gap['total_options'] == 0:
                bottlenecks.append(
                    f"{gap['date']}無任何可行排班組合（主治:{gap['attending_available']}人，住院:{gap['resident_available']}人）"
                )
        
        return bottlenecks