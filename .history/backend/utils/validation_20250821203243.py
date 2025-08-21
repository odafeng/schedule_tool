"""
資料驗證工具函數 - 支援日期格式轉換版本
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
    
    # 檢查是否有總醫師
    resident_doctors = [d for d in doctors if d.role == "總醫師"]
    if not resident_doctors:
        errors.append("至少需要一位總醫師")
    
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
    
    # 檢查日期格式和衝突（處理整數和字串格式）
    date_errors = validate_doctor_dates(doctor)
    errors.extend(date_errors)
    
    return errors

def validate_doctor_dates(doctor) -> List[str]:
    """
    驗證醫師的日期設定（支援整數和字串格式）
    
    Args:
        doctor: 醫師物件
    
    Returns:
        錯誤訊息列表
    """
    errors = []
    
    # 處理不可值班日期
    validated_unavailable = []
    for date_item in doctor.unavailable_dates:
        if isinstance(date_item, int):
            # 整數格式（日期數字）- 發出警告但接受
            if 1 <= date_item <= 31:
                validated_unavailable.append(str(date_item))
                errors.append(f"警告：醫師 {doctor.name} 的不可值班日期使用舊格式（數字 {date_item}），請執行遷移腳本")
            else:
                errors.append(f"醫師 {doctor.name} 的不可值班日期數字無效: {date_item}")
        elif isinstance(date_item, str):
            if date_item.isdigit():
                # 字串數字格式
                day = int(date_item)
                if 1 <= day <= 31:
                    validated_unavailable.append(date_item)
                    errors.append(f"警告：醫師 {doctor.name} 的不可值班日期使用舊格式（'{date_item}'），請執行遷移腳本")
                else:
                    errors.append(f"醫師 {doctor.name} 的不可值班日期數字無效: {date_item}")
            else:
                # 檢查完整日期格式
                if validate_date_format(date_item):
                    validated_unavailable.append(date_item)
                else:
                    errors.append(f"醫師 {doctor.name} 的不可值班日期格式錯誤: {date_item}")
        else:
            errors.append(f"醫師 {doctor.name} 的不可值班日期類型錯誤: {type(date_item)}")
    
    # 處理優先值班日期
    validated_preferred = []
    for date_item in doctor.preferred_dates:
        if isinstance(date_item, int):
            # 整數格式（日期數字）- 發出警告但接受
            if 1 <= date_item <= 31:
                validated_preferred.append(str(date_item))
                errors.append(f"警告：醫師 {doctor.name} 的優先值班日期使用舊格式（數字 {date_item}），請執行遷移腳本")
            else:
                errors.append(f"醫師 {doctor.name} 的優先值班日期數字無效: {date_item}")
        elif isinstance(date_item, str):
            if date_item.isdigit():
                # 字串數字格式
                day = int(date_item)
                if 1 <= day <= 31:
                    validated_preferred.append(date_item)
                    errors.append(f"警告：醫師 {doctor.name} 的優先值班日期使用舊格式（'{date_item}'），請執行遷移腳本")
                else:
                    errors.append(f"醫師 {doctor.name} 的優先值班日期數字無效: {date_item}")
            else:
                # 檢查完整日期格式
                if validate_date_format(date_item):
                    validated_preferred.append(date_item)
                else:
                    errors.append(f"醫師 {doctor.name} 的優先值班日期格式錯誤: {date_item}")
        else:
            errors.append(f"醫師 {doctor.name} 的優先值班日期類型錯誤: {type(date_item)}")
    
    # 檢查日期衝突（需要轉換為相同格式比較）
    unavail_set = set(str(d) for d in validated_unavailable)
    pref_set = set(str(d) for d in validated_preferred)
    conflicts = unavail_set & pref_set
    
    if conflicts:
        errors.append(f"醫師 {doctor.name} 有衝突的日期設定（同時為不可值班和優先）: {', '.join(conflicts)}")
    
    return errors

def validate_date_format(date_input) -> bool:
    """
    驗證日期格式是否正確（支援多種格式）
    
    Args:
        date_input: 日期輸入（可能是字串或整數）
    
    Returns:
        是否有效
    """
    # 如果是整數（可能是日期數字）
    if isinstance(date_input, int):
        return 1 <= date_input <= 31
    
    # 如果是字串
    if isinstance(date_input, str):
        # 檢查是否只是數字（代表日期）
        if date_input.isdigit():
            day = int(date_input)
            return 1 <= day <= 31
        
        # 檢查完整日期格式 YYYY-MM-DD（標準格式）
        try:
            datetime.strptime(date_input, "%Y-%m-%d")
            return True
        except ValueError:
            pass
        
        # 嘗試其他常見格式
        for fmt in ["%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"]:
            try:
                datetime.strptime(date_input, fmt)
                return True
            except ValueError:
                continue
    
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
    
    # 檢查平日總醫師
    if weekday_resident_supply < len(weekdays):
        problems.append(f"平日總醫師供給不足：需要 {len(weekdays)}，可提供 {weekday_resident_supply}")
    
    # 檢查假日主治醫師
    if holiday_attending_supply < len(holidays):
        problems.append(f"假日主治醫師供給不足：需要 {len(holidays)}，可提供 {holiday_attending_supply}")
    
    # 檢查假日總醫師
    if holiday_resident_supply < len(holidays):
        problems.append(f"假日總醫師供給不足：需要 {len(holidays)}，可提供 {holiday_resident_supply}")
    
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
        # 從日期字串提取日期資訊
        try:
            if "-" in date_str:
                # YYYY-MM-DD 格式
                date_parts = date_str.split("-")
                year = int(date_parts[0])
                month = int(date_parts[1])
                day = int(date_parts[2])
            else:
                # 可能是純數字
                day = int(date_str) if date_str.isdigit() else None
                year = None
                month = None
        except:
            day = None
            year = None
            month = None
        
        # 計算該日期可用的醫師
        available_attending = []
        available_resident = []
        
        for doctor in doctors:
            is_available = True
            
            # 檢查不可值班日期（支援多種格式）
            for unavail_date in doctor.unavailable_dates:
                # 比較日期
                if isinstance(unavail_date, int):
                    # 如果不可值班日期是整數，比較日期數字
                    if day and unavail_date == day:
                        is_available = False
                        break
                elif isinstance(unavail_date, str):
                    # 如果是字串，可能是完整日期或數字
                    if unavail_date == date_str:
                        is_available = False
                        break
                    elif unavail_date.isdigit() and day:
                        if int(unavail_date) == day:
                            is_available = False
                            break
                    elif "-" in unavail_date and date_str == unavail_date:
                        is_available = False
                        break
            
            if is_available:
                if doctor.role == "主治":
                    available_attending.append(doctor.name)
                else:
                    available_resident.append(doctor.name)
        
        # 檢查是否有足夠的醫師
        if len(available_attending) == 0:
            problems.append(f"{date_str} 沒有可用的主治醫師")
        
        if len(available_resident) == 0:
            problems.append(f"{date_str} 沒有可用的總醫師")
    
    # 限制問題數量避免過多輸出
    if len(problems) > 10:
        remaining = len(problems) - 10
        problems = problems[:10]
        problems.append(f"...還有 {remaining} 個類似問題")
    
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
        filled_slots = stats.get('filled_slots', 0)
        total_slots = stats.get('total_slots', 1)
        
        if total_slots > 0:
            fill_rate = filled_slots / total_slots
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