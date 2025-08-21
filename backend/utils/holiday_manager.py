"""
假日管理器 - 提供持久化的假日設定管理
"""
import json
import os
from datetime import datetime, date
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class Holiday:
    """假日資料模型"""
    date: str
    name: str
    type: str  # national, traditional, custom, makeup
    recurring: bool = False
    compensate_for: Optional[str] = None  # 補班對應的假日
    
    def to_dict(self):
        """轉換為字典"""
        return {k: v for k, v in asdict(self).items() if v is not None}

class HolidayManager:
    """假日管理器 - 處理所有假日相關的持久化操作"""
    
    def __init__(self, config_path: str = "data/configs/holidays_config.json"):
        """
        初始化假日管理器
        
        Args:
            config_path: 假日配置檔案路徑
        """
        self.config_path = config_path
        self.config = self._load_config()
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保必要的目錄存在"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
    
    def _load_config(self) -> dict:
        """載入假日配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"載入假日配置失敗: {e}")
                return self._get_default_config()
        return self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """取得預設配置"""
        return {
            "taiwan_holidays_2024": {
                "national_holidays": [],
                "makeup_workdays": []
            },
            "taiwan_holidays_2025": {
                "national_holidays": [],
                "makeup_workdays": []
            },
            "taiwan_holidays_2026": {
                "national_holidays": [],
                "makeup_workdays": []
            },
            "custom_holidays": {
                "hospital_specific": [],
                "temporary_closures": []
            },
            "user_defined": {
                "additional_holidays": [],
                "additional_workdays": []
            },
            "settings": {
                "auto_apply_national_holidays": True,
                "auto_apply_makeup_workdays": True,
                "allow_custom_modifications": True,
                "timezone": "Asia/Taipei"
            }
        }
    
    def save_config(self):
        """儲存配置到檔案"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"儲存假日配置失敗: {e}")
            return False
    
    def get_holidays_for_month(self, year: int, month: int) -> Tuple[Set[str], Set[str]]:
        """
        取得指定月份的假日和補班日
        
        Args:
            year: 年份
            month: 月份
            
        Returns:
            (假日集合, 補班日集合)
        """
        holidays = set()
        workdays = set()
        
        # 取得國定假日
        year_key = f"taiwan_holidays_{year}"
        if year_key in self.config:
            # 國定假日
            if self.config["settings"]["auto_apply_national_holidays"]:
                for holiday in self.config[year_key].get("national_holidays", []):
                    holiday_date = datetime.strptime(holiday["date"], "%Y-%m-%d")
                    if holiday_date.year == year and holiday_date.month == month:
                        holidays.add(holiday["date"])
            
            # 補班日
            if self.config["settings"]["auto_apply_makeup_workdays"]:
                for workday in self.config[year_key].get("makeup_workdays", []):
                    work_date = datetime.strptime(workday["date"], "%Y-%m-%d")
                    if work_date.year == year and work_date.month == month:
                        workdays.add(workday["date"])
        
        # 取得自訂假日
        for custom_holiday in self.config["custom_holidays"].get("hospital_specific", []):
            holiday_date = datetime.strptime(custom_holiday["date"], "%Y-%m-%d")
            
            # 處理循環假日（每年同一天）
            if custom_holiday.get("recurring", False):
                try:
                    recurring_date = date(year, holiday_date.month, holiday_date.day)
                    if recurring_date.month == month:
                        holidays.add(recurring_date.strftime("%Y-%m-%d"))
                except ValueError:
                    # 處理2月29日在非閏年的情況
                    pass
            elif holiday_date.year == year and holiday_date.month == month:
                holidays.add(custom_holiday["date"])
        
        # 取得使用者定義的額外假日和補班日
        for user_holiday in self.config.get("user_defined", {}).get("additional_holidays", []):
            holiday_date = datetime.strptime(user_holiday["date"], "%Y-%m-%d")
            if holiday_date.year == year and holiday_date.month == month:
                holidays.add(user_holiday["date"])
        
        for user_workday in self.config.get("user_defined", {}).get("additional_workdays", []):
            work_date = datetime.strptime(user_workday["date"], "%Y-%m-%d")
            if work_date.year == year and work_date.month == month:
                workdays.add(user_workday["date"])
        
        return holidays, workdays
    
    def add_custom_holiday(self, date_str: str, name: str = "自訂假日", 
                          recurring: bool = False) -> bool:
        """
        新增自訂假日
        
        Args:
            date_str: 日期字串 (YYYY-MM-DD)
            name: 假日名稱
            recurring: 是否為每年循環
        """
        try:
            # 驗證日期格式
            datetime.strptime(date_str, "%Y-%m-%d")
            
            # 確保 user_defined 結構存在
            if "user_defined" not in self.config:
                self.config["user_defined"] = {
                    "additional_holidays": [],
                    "additional_workdays": []
                }
            
            holiday_data = {
                "date": date_str,
                "name": name,
                "type": "custom",
                "recurring": recurring
            }
            
            # 檢查是否已存在
            existing_dates = [h["date"] for h in self.config["user_defined"]["additional_holidays"]]
            if date_str not in existing_dates:
                self.config["user_defined"]["additional_holidays"].append(holiday_data)
                self.save_config()
                return True
            return False
        except Exception as e:
            print(f"新增假日失敗: {e}")
            return False
    
    def add_makeup_workday(self, date_str: str, name: str = "補班日", 
                           compensate_for: str = None) -> bool:
        """
        新增補班日
        
        Args:
            date_str: 日期字串 (YYYY-MM-DD)
            name: 補班日名稱
            compensate_for: 補償的假日日期
        """
        try:
            # 驗證日期格式
            datetime.strptime(date_str, "%Y-%m-%d")
            
            # 確保 user_defined 結構存在
            if "user_defined" not in self.config:
                self.config["user_defined"] = {
                    "additional_holidays": [],
                    "additional_workdays": []
                }
            
            workday_data = {
                "date": date_str,
                "name": name,
                "type": "makeup"
            }
            
            if compensate_for:
                workday_data["compensate_for"] = compensate_for
            
            # 檢查是否已存在
            existing_dates = [w["date"] for w in self.config["user_defined"]["additional_workdays"]]
            if date_str not in existing_dates:
                self.config["user_defined"]["additional_workdays"].append(workday_data)
                self.save_config()
                return True
            return False
        except Exception as e:
            print(f"新增補班日失敗: {e}")
            return False
    
    def remove_custom_holiday(self, date_str: str) -> bool:
        """移除自訂假日"""
        try:
            if "user_defined" in self.config:
                self.config["user_defined"]["additional_holidays"] = [
                    h for h in self.config["user_defined"]["additional_holidays"]
                    if h["date"] != date_str
                ]
                self.save_config()
                return True
            return False
        except Exception as e:
            print(f"移除假日失敗: {e}")
            return False
    
    def remove_makeup_workday(self, date_str: str) -> bool:
        """移除補班日"""
        try:
            if "user_defined" in self.config:
                self.config["user_defined"]["additional_workdays"] = [
                    w for w in self.config["user_defined"]["additional_workdays"]
                    if w["date"] != date_str
                ]
                self.save_config()
                return True
            return False
        except Exception as e:
            print(f"移除補班日失敗: {e}")
            return False
    
    def get_holiday_info(self, date_str: str) -> Optional[Dict]:
        """
        取得特定日期的假日資訊
        
        Args:
            date_str: 日期字串 (YYYY-MM-DD)
            
        Returns:
            假日資訊字典，如果不是假日則返回 None
        """
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            year = target_date.year
            
            # 檢查國定假日
            year_key = f"taiwan_holidays_{year}"
            if year_key in self.config:
                for holiday in self.config[year_key].get("national_holidays", []):
                    if holiday["date"] == date_str:
                        return holiday
            
            # 檢查自訂假日
            for custom_holiday in self.config["custom_holidays"].get("hospital_specific", []):
                if custom_holiday["date"] == date_str:
                    return custom_holiday
                
                # 檢查循環假日
                if custom_holiday.get("recurring", False):
                    holiday_date = datetime.strptime(custom_holiday["date"], "%Y-%m-%d")
                    if (target_date.month == holiday_date.month and 
                        target_date.day == holiday_date.day):
                        return custom_holiday
            
            # 檢查使用者定義假日
            for user_holiday in self.config.get("user_defined", {}).get("additional_holidays", []):
                if user_holiday["date"] == date_str:
                    return user_holiday
            
            return None
        except Exception as e:
            print(f"取得假日資訊失敗: {e}")
            return None
    
    def is_holiday(self, date_str: str) -> bool:
        """檢查特定日期是否為假日"""
        return self.get_holiday_info(date_str) is not None
    
    def is_workday(self, date_str: str) -> bool:
        """檢查特定日期是否為補班日"""
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            year = target_date.year
            
            # 檢查補班日
            year_key = f"taiwan_holidays_{year}"
            if year_key in self.config:
                for workday in self.config[year_key].get("makeup_workdays", []):
                    if workday["date"] == date_str:
                        return True
            
            # 檢查使用者定義補班日
            for user_workday in self.config.get("user_defined", {}).get("additional_workdays", []):
                if user_workday["date"] == date_str:
                    return True
            
            return False
        except Exception as e:
            print(f"檢查補班日失敗: {e}")
            return False
    
    def get_all_holidays_in_year(self, year: int) -> List[Dict]:
        """取得指定年份的所有假日"""
        holidays = []
        
        # 國定假日
        year_key = f"taiwan_holidays_{year}"
        if year_key in self.config:
            holidays.extend(self.config[year_key].get("national_holidays", []))
        
        # 自訂假日
        for custom_holiday in self.config["custom_holidays"].get("hospital_specific", []):
            holiday_date = datetime.strptime(custom_holiday["date"], "%Y-%m-%d")
            
            if custom_holiday.get("recurring", False):
                # 循環假日
                try:
                    recurring_date = date(year, holiday_date.month, holiday_date.day)
                    holiday_copy = custom_holiday.copy()
                    holiday_copy["date"] = recurring_date.strftime("%Y-%m-%d")
                    holidays.append(holiday_copy)
                except ValueError:
                    # 處理2月29日在非閏年的情況
                    pass
            elif holiday_date.year == year:
                holidays.append(custom_holiday)
        
        # 使用者定義假日
        for user_holiday in self.config.get("user_defined", {}).get("additional_holidays", []):
            holiday_date = datetime.strptime(user_holiday["date"], "%Y-%m-%d")
            if holiday_date.year == year:
                holidays.append(user_holiday)
        
        # 按日期排序
        holidays.sort(key=lambda x: x["date"])
        return holidays
    
    def get_all_workdays_in_year(self, year: int) -> List[Dict]:
        """取得指定年份的所有補班日"""
        workdays = []
        
        # 國定補班日
        year_key = f"taiwan_holidays_{year}"
        if year_key in self.config:
            workdays.extend(self.config[year_key].get("makeup_workdays", []))
        
        # 使用者定義補班日
        for user_workday in self.config.get("user_defined", {}).get("additional_workdays", []):
            work_date = datetime.strptime(user_workday["date"], "%Y-%m-%d")
            if work_date.year == year:
                workdays.append(user_workday)
        
        # 按日期排序
        workdays.sort(key=lambda x: x["date"])
        return workdays
    
    def import_holidays_from_csv(self, csv_path: str) -> bool:
        """從 CSV 檔案匯入假日資料"""
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, encoding='utf-8')
            
            # 預期的欄位：date, name, type, recurring
            for _, row in df.iterrows():
                date_str = row['date']
                name = row.get('name', '自訂假日')
                holiday_type = row.get('type', 'custom')
                recurring = row.get('recurring', False)
                
                if holiday_type == 'makeup':
                    self.add_makeup_workday(date_str, name)
                else:
                    self.add_custom_holiday(date_str, name, recurring)
            
            return True
        except Exception as e:
            print(f"匯入 CSV 失敗: {e}")
            return False
    
    def export_holidays_to_csv(self, year: int, csv_path: str) -> bool:
        """匯出假日資料到 CSV 檔案"""
        try:
            import pandas as pd
            
            holidays = self.get_all_holidays_in_year(year)
            workdays = self.get_all_workdays_in_year(year)
            
            # 合併所有資料
            all_dates = []
            
            for holiday in holidays:
                all_dates.append({
                    'date': holiday['date'],
                    'name': holiday['name'],
                    'type': holiday['type'],
                    'category': '假日'
                })
            
            for workday in workdays:
                all_dates.append({
                    'date': workday['date'],
                    'name': workday['name'],
                    'type': 'makeup',
                    'category': '補班日'
                })
            
            # 建立 DataFrame 並排序
            df = pd.DataFrame(all_dates)
            if not df.empty:
                df = df.sort_values('date')
            
            # 匯出到 CSV
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            print(f"匯出 CSV 失敗: {e}")
            return False
    
    def clear_user_defined_holidays(self) -> bool:
        """清除所有使用者定義的假日和補班日"""
        try:
            if "user_defined" in self.config:
                self.config["user_defined"] = {
                    "additional_holidays": [],
                    "additional_workdays": []
                }
                self.save_config()
                return True
            return False
        except Exception as e:
            print(f"清除使用者定義假日失敗: {e}")
            return False
    
    def get_statistics(self, year: int) -> Dict:
        """取得指定年份的假日統計"""
        holidays = self.get_all_holidays_in_year(year)
        workdays = self.get_all_workdays_in_year(year)
        
        # 按類型統計假日
        holiday_types = {}
        for holiday in holidays:
            h_type = holiday.get('type', 'unknown')
            holiday_types[h_type] = holiday_types.get(h_type, 0) + 1
        
        return {
            'total_holidays': len(holidays),
            'total_workdays': len(workdays),
            'holiday_types': holiday_types,
            'net_holidays': len(holidays) - len(workdays)  # 淨假日數
        }


# 整合到現有的 calendar_utils.py 的輔助函數
def get_month_calendar_with_memory(year: int, month: int, 
                                  holiday_manager: Optional[HolidayManager] = None) -> Tuple[List[str], List[str]]:
    """
    使用假日管理器生成指定月份的平日和假日列表
    
    Args:
        year: 年份
        month: 月份
        holiday_manager: 假日管理器實例
    
    Returns:
        (平日列表, 假日列表)
    """
    import calendar
    from datetime import date
    
    if holiday_manager is None:
        holiday_manager = HolidayManager()
    
    # 從假日管理器取得假日和補班日
    custom_holidays, custom_workdays = holiday_manager.get_holidays_for_month(year, month)
    
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
        elif date_str in custom_holidays:
            # 自訂假日
            holidays.append(date_str)
        elif is_weekend and date_str not in custom_workdays:
            # 週末（非補班日）
            holidays.append(date_str)
        else:
            # 一般平日
            weekdays.append(date_str)
    
    return weekdays, holidays