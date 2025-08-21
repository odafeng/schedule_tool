"""
資料驗證工具函數
"""
from typing import List, Tuple, Set
from datetime import datetime

def validate_doctor_data(doctors: List) -> Tuple[bool, List[str]]:
    """
    驗證醫師資料的完整性和正確性
    
    Args:
        doctors: 醫師列表
    
    Returns:
        (是否有效, 錯誤訊息列表)
    """
    errors = []
    
    # 檢查是否有醫師
    if not doctors:
        errors.append("尚未新增任何醫師")
        return False, errors
    
    # 檢查是否有主治醫師
    attending_doctors = [d for d in doctors if d.role == "主治"]
    if not attending_doctors:
        errors.append("至少需要一位主治醫師")
    
    # 檢查是否有住院醫師
    resident_doctors = [d for d in doctors if d.role == "總醫師"]
    if not resident_doctors:
        errors.append("至少需要一位住院醫師")
    
    # 檢查重複姓名
    names = [d.name for d in doctors]
    duplicates = [name for name in set(names) if names.count(name) > 1]
    if duplicates:
        errors.append(f"發現重複的醫師姓名: {', '.join(duplicates)}")
    
    # 檢查每個醫師的資料
    for doctor in doctors:
        doctor_errors = validate_individual_doctor(doctor)
        errors.extend(doctor_errors)
    
    return len(errors) == 0, errors

def validate_individual_doctor(doctor) -> List[str]:
    """
    驗證單個醫師的資料
    
    Args:
        doctor: 醫師物件
    
    Returns:
        錯誤訊息列表
    """
    errors = []
    
    # 檢查姓名
    if not doctor.name or not doctor.name.strip():
        errors.append("醫師姓名不能為空")
    
    # 檢查角色
    if doctor.role not in ["主治", "總醫師"]:
        errors.append(f"醫師 {doctor.name} 的角色必須是「主治」或「總醫師」")

    # 檢查配額
    if doctor.weekday_quota < 0:
        errors.append(f"醫師 {doctor.name} 的平日配額不能為負數")
    
    if doctor.holiday_quota < 0:
        errors.append(f"醫師 {doctor.name} 的假日配額不能為負數")
    
    # 檢查配額合理性
    if doctor.weekday_quota > 20:
        errors.append(f"醫師 {doctor.name} 的平日配額 {doctor.weekday_quota} 可能過高")
    
    if doctor.holiday_quota > 10:
        errors.append(f"醫師 {doctor.name} 的假日配額 {doctor.holiday_quota} 可能過高")
    
    # 檢查日期格式和衝突
    date_errors = validate_doctor_dates(doctor)
    errors.extend(date_errors)
    
    return errors

def validate_doctor_dates(doctor) -> List[str]:
    """
    驗證醫師的日期設定
    
    Args:
        doctor: 醫師物件
    
    Returns:
        錯誤訊息列表
    """
    errors = []
    
    # 檢查不可值班日期格式
    for date_str in doctor.unavailable_dates:
        if not validate_date_format(date_str):
            errors.append(f"醫師 {doctor.name} 的不可值班日期格式錯誤: {date_str}")
    
    # 檢查偏好日期格式
    for date_str in doctor.preferred_dates:
        if not validate_date_format(date_str):
            errors.append(f"醫師 {doctor.name} 的偏好日期格式錯誤: {date_str}")
    
    # 檢查日期衝突
    conflicts = set(doctor.unavailable_dates) & set(doctor.preferred_dates)
    if conflicts:
        errors.append(f"醫師 {doctor.name} 有衝突的日期設定（同時為不可值班和偏好）: {', '.join(conflicts)}")
    
    return errors

def validate_date_format(date_str: str) -> bool:
    """
    驗證日期格式是否正確
    
    Args:
        date_str: 日期字串
    
    Returns:
        是否有效
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def validate_schedule_feasibility(doctors: List, weekdays: List[str], holidays: List[str]) -> Tuple[bool, List[str]]:
    """
    驗證排班問題的可行性
    
    Args:
        doctors: 醫師列表
        weekdays: 平日列表
        holidays: 假日列表
    
    Returns:
        (是否可行, 問題列表)
    """
    problems = []
    
    # 計算需求
    weekday_demand = len(weekdays) * 2  # 每天需要1主治+1總醫師
    holiday_demand = len(holidays) * 2
    total_demand = weekday_demand + holiday_demand
    
    # 計算供給
    attending_doctors = [d for d in doctors if d.role == "主治"]
    resident_doctors = [d for d in doctors if d.role == "總醫師"]
    
    weekday_attending_supply = sum(d.weekday_quota for d in attending_doctors)
    weekday_resident_supply = sum(d.weekday_quota for d in resident_doctors)
    holiday_attending_supply = sum(d.holiday_quota for d in attending_doctors)
    holiday_resident_supply = sum(d.holiday_quota for d in resident_doctors)
    
    # 檢查平日主治醫師
    if weekday_attending_supply < len(weekdays):
        problems.append(f"平日主治醫師供給不足：需要 {len(weekdays)}，可提供 {weekday_attending_supply}")
    
    # 檢查平日住院醫師
    if weekday_resident_supply < len(weekdays):
        problems.append(f"平日住院醫師供給不足：需要 {len(weekdays)}，可提供 {weekday_resident_supply}")
    
    # 檢查假日主治醫師
    if holiday_attending_supply < len(holidays):
        problems.append(f"假日主治醫師供給不足：需要 {len(holidays)}，可提供 {holiday_attending_supply}")
    
    # 檢查假日住院醫師
    if holiday_resident_supply < len(holidays):
        problems.append(f"假日住院醫師供給不足：需要 {len(holidays)}，可提供 {holiday_resident_supply}")
    
    # 檢查特定日期的可用性
    date_problems = check_date_availability(doctors, weekdays, holidays)
    problems.extend(date_problems)
    
    return len(problems) == 0, problems

def check_date_availability(doctors: List, weekdays: List[str], holidays: List[str]) -> List[str]:
    """
    檢查特定日期是否有足夠的可用醫師
    
    Args:
        doctors: 醫師列表
        weekdays: 平日列表
        holidays: 假日列表
    
    Returns:
        問題列表
    """
    problems = []
    all_dates = weekdays + holidays
    
    for date_str in all_dates:
        # 計算該日期可用的醫師
        available_attending = []
        available_resident = []
        
        for doctor in doctors:
            if date_str not in doctor.unavailable_dates:
                if doctor.role == "主治":
                    available_attending.append(doctor.name)
                else:
                    available_resident.append(doctor.name)
        
        # 檢查是否有足夠的醫師
        if len(available_attending) == 0:
            problems.append(f"{date_str} 沒有可用的主治醫師")
        
        if len(available_resident) == 0:
            problems.append(f"{date_str} 沒有可用的住院醫師")
    
    # 限制問題數量避免過多輸出
    if len(problems) > 10:
        problems = problems[:10]
        problems.append(f"...還有 {len(problems) - 10} 個類似問題")
    
    return problems

def validate_schedule_result(schedule_result) -> Tuple[bool, List[str]]:
    """
    驗證排班結果
    
    Args:
        schedule_result: 排班結果物件
    
    Returns:
        (是否有效, 問題列表)
    """
    problems = []
    
    if not schedule_result:
        problems.append("沒有排班結果")
        return False, problems
    
    # 檢查填充率
    if hasattr(schedule_result, 'statistics'):
        stats = schedule_result.statistics
        fill_rate = stats.get('filled_slots', 0) / stats.get('total_slots', 1)
        
        if fill_rate < 0.8:
            problems.append(f"填充率過低: {fill_rate*100:.1f}%")
    
    # 檢查未填格
    if hasattr(schedule_result, 'unfilled_slots'):
        if len(schedule_result.unfilled_slots) > 10:
            problems.append(f"未填格數過多: {len(schedule_result.unfilled_slots)}")
    
    # 檢查違規
    if hasattr(schedule_result, 'violations'):
        if schedule_result.violations:
            problems.append(f"存在排班違規: {len(schedule_result.violations)} 項")
    
    return len(problems) == 0, problems