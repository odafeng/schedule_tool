"""
Stage 3: 確認與發佈
"""
import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import json

from backend.models import Doctor, ScheduleSlot

@dataclass 
class ScheduleQualityReport:
    """排班品質報告"""
    acceptance_level: str  # Ideal / Acceptable / Needs discussion
    fill_rate: float
    total_issues: int
    critical_issues: List[str]
    minor_issues: List[str]
    statistics: Dict
    
class Stage3Publisher:
    """Stage 3: 確認與發佈器"""
    
    def __init__(self, schedule: Dict[str, ScheduleSlot],
                 doctors: List[Doctor],
                 weekdays: List[str], holidays: List[str]):
        self.schedule = schedule
        self.doctors = doctors
        self.weekdays = weekdays
        self.holidays = holidays
        
        # 建立醫師索引
        self.doctor_map = {d.name: d for d in doctors}
        
        # 生成品質報告
        self.quality_report = self._generate_quality_report()
    
    def _generate_quality_report(self) -> ScheduleQualityReport:
        """生成排班品質報告"""
        
        # 計算填充率
        total_slots = len(self.schedule) * 2
        filled_slots = 0
        unfilled_list = []
        
        for date_str, slot in self.schedule.items():
            if slot.attending:
                filled_slots += 1
            else:
                unfilled_list.append((date_str, "主治"))
            
            if slot.resident:
                filled_slots += 1
            else:
                unfilled_list.append((date_str, "總醫師"))
        
        fill_rate = filled_slots / total_slots if total_slots > 0 else 0
        
        # 分析問題
        critical_issues = []
        minor_issues = []
        
        # 1. 檢查未填格
        if unfilled_list:
            if len(unfilled_list) > 5:
                critical_issues.append(f"有 {len(unfilled_list)} 個未填格位")
            else:
                for date, role in unfilled_list[:5]:
                    minor_issues.append(f"{date} 缺少{role}醫師")
        
        # 2. 檢查連續值班
        consecutive_issues = self._check_consecutive_duties()
        if consecutive_issues:
            minor_issues.extend(consecutive_issues)
        
        # 3. 檢查偏好滿足度
        preference_stats = self._check_preference_satisfaction()
        if preference_stats['unsatisfied_critical']:
            critical_issues.extend(preference_stats['unsatisfied_critical'])
        if preference_stats['unsatisfied_minor']:
            minor_issues.extend(preference_stats['unsatisfied_minor'])
        
        # 4. 檢查配額使用
        quota_issues = self._check_quota_usage()
        if quota_issues:
            minor_issues.extend(quota_issues)
        
        # 決定接受度等級
        if fill_rate >= 0.98 and len(critical_issues) == 0:
            acceptance_level = "Ideal"
        elif fill_rate >= 0.95 and len(critical_issues) <= 2:
            acceptance_level = "Acceptable"
        else:
            acceptance_level = "Needs discussion"
        
        # 統計資訊
        statistics = self._calculate_statistics()
        
        return ScheduleQualityReport(
            acceptance_level=acceptance_level,
            fill_rate=fill_rate,
            total_issues=len(critical_issues) + len(minor_issues),
            critical_issues=critical_issues,
            minor_issues=minor_issues,
            statistics=statistics
        )
    
    def _check_consecutive_duties(self) -> List[str]:
        """檢查連續值班問題"""
        issues = []
        doctor_consecutive = {}
        
        sorted_dates = sorted(self.schedule.keys())
        
        for i, date_str in enumerate(sorted_dates):
            slot = self.schedule[date_str]
            
            for doctor_name in [slot.attending, slot.resident]:
                if not doctor_name:
                    continue
                
                # 檢查連續值班
                if i > 0:
                    prev_slot = self.schedule[sorted_dates[i-1]]
                    if doctor_name in [prev_slot.attending, prev_slot.resident]:
                        if doctor_name not in doctor_consecutive:
                            doctor_consecutive[doctor_name] = 1
                        else:
                            doctor_consecutive[doctor_name] += 1
                        
                        if doctor_consecutive[doctor_name] >= 3:
                            issues.append(f"{doctor_name} 連續值班 {doctor_consecutive[doctor_name]+1} 天")
                    else:
                        doctor_consecutive[doctor_name] = 0
        
        return issues
    
    def _check_preference_satisfaction(self) -> Dict:
        """檢查偏好滿足度"""
        result = {
            'satisfied': [],
            'unsatisfied_critical': [],
            'unsatisfied_minor': [],
            'satisfaction_rate': 0
        }
        
        total_preferences = 0
        satisfied_preferences = 0
        
        for doctor in self.doctors:
            for pref_date in doctor.preferred_dates:
                if pref_date in self.schedule:
                    total_preferences += 1
                    slot = self.schedule[pref_date]
                    
                    if doctor.name in [slot.attending, slot.resident]:
                        satisfied_preferences += 1
                        result['satisfied'].append(f"{doctor.name} 在偏好日 {pref_date} 值班")
                    else:
                        # 檢查是否有其他人可以替代
                        if self._has_alternative(pref_date, doctor.role):
                            result['unsatisfied_minor'].append(
                                f"{doctor.name} 未能在偏好日 {pref_date} 值班"
                            )
                        else:
                            result['unsatisfied_critical'].append(
                                f"{doctor.name} 的重要偏好日 {pref_date} 未滿足"
                            )
        
        if total_preferences > 0:
            result['satisfaction_rate'] = satisfied_preferences / total_preferences
        
        return result
    
    def _has_alternative(self, date: str, role: str) -> bool:
        """檢查是否有其他醫師可以替代"""
        slot = self.schedule[date]
        current_doctor = slot.attending if role == "主治" else slot.resident
        
        if not current_doctor:
            return False
        
        # 檢查當前醫師是否也偏好這天
        current_doc_obj = self.doctor_map.get(current_doctor)
        if current_doc_obj and date in current_doc_obj.preferred_dates:
            return False
        
        return True
    
    def _check_quota_usage(self) -> List[str]:
        """檢查配額使用情況"""
        issues = []
        
        # 計算每個醫師的使用量
        doctor_usage = {}
        for doctor in self.doctors:
            doctor_usage[doctor.name] = {'weekday': 0, 'holiday': 0}
        
        for date_str, slot in self.schedule.items():
            is_holiday = date_str in self.holidays
            quota_type = 'holiday' if is_holiday else 'weekday'
            
            if slot.attending and slot.attending in doctor_usage:
                doctor_usage[slot.attending][quota_type] += 1
            
            if slot.resident and slot.resident in doctor_usage:
                doctor_usage[slot.resident][quota_type] += 1
        
        # 檢查配額使用
        for doctor in self.doctors:
            usage = doctor_usage[doctor.name]
            
            # 檢查是否未充分使用
            weekday_rate = usage['weekday'] / max(doctor.weekday_quota, 1)
            holiday_rate = usage['holiday'] / max(doctor.holiday_quota, 1)
            
            if weekday_rate < 0.5:
                issues.append(f"{doctor.name} 平日配額使用率過低 ({weekday_rate:.0%})")
            
            if holiday_rate < 0.5:
                issues.append(f"{doctor.name} 假日配額使用率過低 ({holiday_rate:.0%})")
        
        return issues
    
    def _calculate_statistics(self) -> Dict:
        """計算統計資訊"""
        stats = {
            'total_days': len(self.schedule),
            'weekdays': len(self.weekdays),
            'holidays': len(self.holidays),
            'doctor_duties': {},
            'role_distribution': {'主治': 0, '總醫師': 0}
        }
        
        # 計算每個醫師的值班統計
        for doctor in self.doctors:
            weekday_count = 0
            holiday_count = 0
            
            for date_str, slot in self.schedule.items():
                if doctor.name in [slot.attending, slot.resident]:
                    if date_str in self.holidays:
                        holiday_count += 1
                    else:
                        weekday_count += 1
                
                # 統計角色分布
                if slot.attending == doctor.name:
                    stats['role_distribution']['主治'] += 1
                if slot.resident == doctor.name:
                    stats['role_distribution']['總醫師'] += 1
            
            stats['doctor_duties'][doctor.name] = {
                'weekday': weekday_count,
                'holiday': holiday_count,
                'total': weekday_count + holiday_count,
                'weekday_quota': doctor.weekday_quota,
                'holiday_quota': doctor.holiday_quota
            }
        
        return stats
    
    def export_to_dataframe(self) -> pd.DataFrame:
        """匯出為 DataFrame"""
        data = []
        
        for date_str in sorted(self.schedule.keys()):
            slot = self.schedule[date_str]
            
            # 判斷是否為假日
            is_holiday = date_str in self.holidays
            
            # 取得星期幾
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            weekday_names = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
            weekday = weekday_names[date_obj.weekday()]
            
            data.append({
                '日期': date_str,
                '星期': weekday,
                '類型': '假日' if is_holiday else '平日',
                '主治醫師': slot.attending or '(未排)',
                '總醫師': slot.resident or '(未排)',
                '備註': self._get_date_notes(date_str, slot)
            })
        
        return pd.DataFrame(data)
    
    def _get_date_notes(self, date_str: str, slot: ScheduleSlot) -> str:
        """取得日期備註"""
        notes = []
        
        # 檢查是否有人在偏好日值班
        for doctor in self.doctors:
            if date_str in doctor.preferred_dates:
                if doctor.name in [slot.attending, slot.resident]:
                    notes.append(f"{doctor.name}偏好")
        
        # 檢查是否為重要假日
        if date_str in self.holidays:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if date_obj.weekday() in [5, 6]:  # 週末
                notes.append("週末假日")
        
        return "；".join(notes) if notes else ""
    
    def export_to_excel(self, filename: str = None) -> str:
        """匯出為 Excel 檔案"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"schedule_{timestamp}.xlsx"
        
        # 創建 DataFrame
        df = self.export_to_dataframe()
        
        # 寫入 Excel
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # 主要排班表
            df.to_excel(writer, sheet_name='排班表', index=False)
            
            # 統計資訊
            stats_df = self._create_statistics_df()
            stats_df.to_excel(writer, sheet_name='統計', index=False)
            
            # 問題清單
            issues_df = self._create_issues_df()
            issues_df.to_excel(writer, sheet_name='問題清單', index=False)
        
        return filename
    
    def _create_statistics_df(self) -> pd.DataFrame:
        """創建統計 DataFrame"""
        data = []
        
        for doctor_name, stats in self.quality_report.statistics['doctor_duties'].items():
            data.append({
                '醫師': doctor_name,
                '平日值班': stats['weekday'],
                '平日配額': stats['weekday_quota'],
                '平日使用率': f"{stats['weekday']/max(stats['weekday_quota'],1)*100:.0f}%",
                '假日值班': stats['holiday'],
                '假日配額': stats['holiday_quota'],
                '假日使用率': f"{stats['holiday']/max(stats['holiday_quota'],1)*100:.0f}%",
                '總值班數': stats['total']
            })
        
        return pd.DataFrame(data)
    
    def _create_issues_df(self) -> pd.DataFrame:
        """創建問題清單 DataFrame"""
        data = []
        
        for issue in self.quality_report.critical_issues:
            data.append({
                '類型': '重要',
                '問題描述': issue
            })
        
        for issue in self.quality_report.minor_issues:
            data.append({
                '類型': '次要',
                '問題描述': issue
            })
        
        return pd.DataFrame(data) if data else pd.DataFrame(columns=['類型', '問題描述'])
    
    def generate_summary_message(self) -> str:
        """生成摘要訊息（用於 LINE 推播）"""
        report = self.quality_report
        
        # 根據接受度等級選擇 emoji
        emoji_map = {
            'Ideal': '✅',
            'Acceptable': '⚠️',
            'Needs discussion': '🔴'
        }
        emoji = emoji_map.get(report.acceptance_level, '📋')
        
        message = f"{emoji} 排班完成通知\n"
        message += f"━━━━━━━━━━━━\n"
        message += f"📅 月份：{datetime.now().strftime('%Y年%m月')}\n"
        message += f"📊 填充率：{report.fill_rate:.1%}\n"
        message += f"⭐ 接受度：{report.acceptance_level}\n"
        
        if report.critical_issues:
            message += f"\n🔴 重要問題 ({len(report.critical_issues)})：\n"
            for issue in report.critical_issues[:3]:
                message += f"• {issue}\n"
        
        if report.minor_issues:
            message += f"\n⚠️ 次要問題 ({len(report.minor_issues)})：\n"
            for issue in report.minor_issues[:2]:
                message += f"• {issue}\n"
        
        message += f"\n📥 下載連結：[點此下載]\n"
        message += f"⏰ 連結有效期：24小時"
        
        return message