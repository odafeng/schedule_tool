"""
資料驗證工具
"""
from typing import List, Dict, Tuple
from ..models import Doctor, ScheduleSlot

def validate_doctor_data(doctors: List[Doctor]) -> Tuple[bool, List[str]]:
    """
    驗證醫師資料的完整性和合理性
    
    Returns:
        (是否有效, 錯誤訊息列表)
    """
    errors = []
    
    # 檢查是否有醫師
    if not doctors:
        errors.append("未設定任何醫師")
        return False, errors
    
    # 檢查是否有主治和住院醫師
    attending_count = sum(1 for d in doctors if d.role == "主治")
    resident_count = sum(1 for d in doctors if d.role == "住院")
    
    if attending_count == 0:
        errors.append("至少需要一位主治醫師")
    if resident_count == 0:
        errors.append("至少需要一位住院醫師")
    
    # 檢查醫師姓名是否重複
    names = [d.name for d in doctors]
    if len(names) != len(set(names)):
        errors.append("醫師姓名有重複")
    
    # 檢查配額合理性
    for doctor in doctors:
        if doctor.weekday_quota < 0:
            errors.append(f"{doctor.name}的平日配額不能為負數")
        if doctor.holiday_quota < 0:
            errors.append(f"{doctor.name}的假日配額不能為負數")
        if doctor.weekday_quota == 0 and doctor.holiday_quota == 0:
            errors.append(f"{doctor.name}的配額不能全為零")
    
    return len(errors) == 0, errors

def validate_schedule(schedule: Dict[str, ScheduleSlot], 
                     doctors: List[Doctor]) -> Tuple[bool, List[str]]:
    """
    驗證排班結果的合理性
    
    Returns:
        (是否有效, 警告訊息列表)
    """
    warnings = []
    doctor_names = {d.name for d in doctors}
    
    for date_str, slot in schedule.items():
        # 檢查醫師是否存在
        if slot.attending and slot.attending not in doctor_names:
            warnings.append(f"{date_str}的主治醫師{slot.attending}不在醫師名單中")
        if slot.resident and slot.resident not in doctor_names:
            warnings.append(f"{date_str}的住院醫師{slot.resident}不在醫師名單中")
        
        # 檢查同一天同一人不能擔任兩個角色
        if slot.attending and slot.resident and slot.attending == slot.resident:
            warnings.append(f"{date_str}的同一醫師不能同時擔任主治和住院")
    
    return len(warnings) == 0, warnings