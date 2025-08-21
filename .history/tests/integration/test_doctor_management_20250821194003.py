"""
醫師管理系統整合測試套件 - 修正版
包含日期解析、醫師模型、Session管理的完整測試
"""
import pytest
import json
import os
import tempfile
import shutil
import calendar
from datetime import datetime, date
from unittest.mock import Mock, patch, mock_open, MagicMock
from typing import List, Set
from dataclasses import dataclass, field, asdict
from typing import Literal
import sys

# ==================== 模型定義 ====================

@dataclass
class Doctor:
    """醫師資料模型"""
    name: str
    role: Literal["主治", "總醫師"]
    weekday_quota: int
    holiday_quota: int
    unavailable_dates: List[str] = field(default_factory=list)
    preferred_dates: List[str] = field(default_factory=list)
    
    def to_dict(self):
        """轉換為字典格式"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        """從字典建立實例"""
        return cls(**data)
    
    def is_available_on(self, date: str) -> bool:
        """檢查特定日期是否可值班"""
        return date not in self.unavailable_dates
    
    def prefers_date(self, date: str) -> bool:
        """檢查是否為偏好日期"""
        return date in self.preferred_dates

# ==================== 日期解析工具 ====================

def parse_date_range(input_str: str, year: int, month: int) -> List[str]:
    """解析日期範圍字串"""
    if not input_str.strip():
        return []
    
    _, max_day = calendar.monthrange(year, month)
    dates = set()
    parts = input_str.replace(" ", "").split(",")
    
    for part in parts:
        if not part:
            continue
            
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start_day = int(start_str)
                end_day = int(end_str)
                
                if start_day < 1 or end_day > max_day or start_day > end_day:
                    raise ValueError(f"無效的日期範圍: {part} (該月只有 {max_day} 天)")
                
                for day in range(start_day, end_day + 1):
                    dates.add(day)
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"日期範圍格式錯誤: {part} (應為數字)")
                else:
                    raise
        else:
            try:
                day = int(part)
                if day < 1 or day > max_day:
                    raise ValueError(f"無效的日期: {day} (該月只有 {max_day} 天)")
                dates.add(day)
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"日期格式錯誤: {part} (應為數字)")
                else:
                    raise
    
    date_strings = []
    for day in sorted(dates):
        date_strings.append(f"{year}-{month:02d}-{day:02d}")
    
    return date_strings

def validate_date_input(input_str: str) -> str:
    """驗證日期輸入格式"""
    if not input_str.strip():
        return ""
    
    import re
    if not re.match(r'^[0-9,\-\s]*$', input_str):
        return "只能包含數字、逗號、連字號和空格"
    
    cleaned = input_str.replace(" ", "")
    
    if ",," in cleaned or "--" in cleaned:
        return "不能有連續的分隔符"
    
    if cleaned.startswith(",") or cleaned.endswith(",") or cleaned.startswith("-") or cleaned.endswith("-"):
        return "不能以分隔符開頭或結尾"
    
    return ""

def format_dates_for_display(dates: List[str]) -> str:
    """格式化日期列表用於顯示"""
    if not dates:
        return "無"
    
    days = []
    for date_str in dates:
        try:
            day = int(date_str.split("-")[2])
            days.append(day)
        except (IndexError, ValueError):
            continue
    
    days.sort()
    
    if len(days) <= 5:
        return f"{', '.join(map(str, days))}"
    else:
        return f"{', '.join(map(str, days[:3]))} ... {', '.join(map(str, days[-2:]))} (共{len(days)}天)"

# ==================== Session管理器 ====================

class MockSessionState:
    """模擬 Streamlit Session State"""
    def __init__(self):
        self.doctors = []
        self.selected_year = 2024
        self.selected_month = 1

class SessionManager:
    """Session狀態管理器"""
    
    @staticmethod
    def save_doctors():
        """儲存醫師資料到獨立檔案"""
        # 這裡使用動態導入來避免測試時的問題
        try:
            import streamlit as st
        except ImportError:
            # 在測試環境中，使用全域的 mock
            st = sys.modules.get('streamlit')
            if not st:
                return False
        
        doctors_data = {
            'doctors': [doctor.to_dict() for doctor in st.session_state.doctors],
            'metadata': {
                'saved_at': datetime.now().isoformat(),
                'total_doctors': len(st.session_state.doctors),
                'attending_count': len([d for d in st.session_state.doctors if d.role == "主治"]),
                'resident_count': len([d for d in st.session_state.doctors if d.role == "總醫師"])
            }
        }
        
        try:
            os.makedirs('data/configs', exist_ok=True)
            with open('data/configs/doctors.json', 'w', encoding='utf-8') as f:
                json.dump(doctors_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    @staticmethod
    def load_doctors() -> bool:
        """從獨立檔案載入醫師資料"""
        try:
            import streamlit as st
        except ImportError:
            st = sys.modules.get('streamlit')
            if not st:
                return False
        
        doctors_file = 'data/configs/doctors.json'
        
        if not os.path.exists(doctors_file):
            return False
        
        try:
            with open(doctors_file, 'r', encoding='utf-8') as f:
                doctors_data = json.load(f)
            
            st.session_state.doctors = []
            
            if 'doctors' in doctors_data:
                st.session_state.doctors = [
                    Doctor.from_dict(doctor_dict) 
                    for doctor_dict in doctors_data['doctors']
                ]
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_doctors_summary() -> dict:
        """取得醫師資料摘要"""
        try:
            import streamlit as st
        except ImportError:
            st = sys.modules.get('streamlit')
            if not st:
                return {'total': 0, 'attending': 0, 'resident': 0, 'has_constraints': 0}
        
        doctors = st.session_state.doctors
        return {
            'total': len(doctors),
            'attending': len([d for d in doctors if d.role == "主治"]),
            'resident': len([d for d in doctors if d.role == "總醫師"]),
            'has_constraints': len([d for d in doctors if d.unavailable_dates or d.preferred_dates])
        }
    
    @staticmethod
    def validate_doctors_data() -> list:
        """驗證醫師資料並返回問題列表"""
        try:
            import streamlit as st
        except ImportError:
            st = sys.modules.get('streamlit')
            if not st:
                return ["無法取得醫師資料"]
        
        problems = []
        doctors = st.session_state.doctors
        
        if not doctors:
            problems.append("尚未新增任何醫師")
            return problems
        
        # 檢查重複姓名
        names = [d.name for d in doctors]
        duplicates = [name for name in set(names) if names.count(name) > 1]
        if duplicates:
            problems.append(f"發現重複的醫師姓名: {', '.join(duplicates)}")
        
        # 檢查每個醫師的資料
        for doctor in doctors:
            if doctor.weekday_quota < 0 or doctor.holiday_quota < 0:
                problems.append(f"醫師 {doctor.name} 的配額不能為負數")
            
            for date_str in doctor.unavailable_dates + doctor.preferred_dates:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    problems.append(f"醫師 {doctor.name} 的日期格式錯誤: {date_str}")
            
            conflicts = set(doctor.unavailable_dates) & set(doctor.preferred_dates)
            if conflicts:
                problems.append(f"醫師 {doctor.name} 有衝突的日期設定: {', '.join(conflicts)}")
        
        return problems

# ==================== 測試類別 ====================

class TestDateParser:
    """測試日期解析工具"""
    
    def test_empty_input(self):
        """測試空輸入"""
        assert parse_date_range("", 2024, 1) == []
        assert parse_date_range("   ", 2024, 1) == []
    
    def test_single_date(self):
        """測試單個日期"""
        assert parse_date_range("15", 2024, 1) == ["2024-01-15"]
        assert parse_date_range("1", 2024, 1) == ["2024-01-01"]
        assert parse_date_range("31", 2024, 1) == ["2024-01-31"]
    
    def test_multiple_dates(self):
        """測試多個日期"""
        result = parse_date_range("1,15,31", 2024, 1)
        assert result == ["2024-01-01", "2024-01-15", "2024-01-31"]
        
        # 測試亂序輸入，結果應該排序
        result = parse_date_range("31,1,15", 2024, 1)
        assert result == ["2024-01-01", "2024-01-15", "2024-01-31"]
    
    def test_date_range(self):
        """測試日期範圍"""
        result = parse_date_range("5-8", 2024, 1)
        assert result == ["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"]
        
        result = parse_date_range("1-3", 2024, 1)
        assert result == ["2024-01-01", "2024-01-02", "2024-01-03"]
    
    def test_mixed_input(self):
        """測試混合輸入"""
        result = parse_date_range("1,5-7,15,20-22", 2024, 1)
        expected = [
            "2024-01-01", "2024-01-05", "2024-01-06", "2024-01-07", 
            "2024-01-15", "2024-01-20", "2024-01-21", "2024-01-22"
        ]
        assert result == expected
    
    def test_duplicate_removal(self):
        """測試重複日期去除"""
        result = parse_date_range("1,1,2,2-4,3", 2024, 1)
        assert result == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
    
    def test_whitespace_handling(self):
        """測試空格處理"""
        result = parse_date_range(" 1 , 5 - 7 , 15 ", 2024, 1)
        expected = ["2024-01-01", "2024-01-05", "2024-01-06", "2024-01-07", "2024-01-15"]
        assert result == expected
    
    def test_february_leap_year(self):
        """測試閏年二月"""
        result = parse_date_range("28,29", 2024, 2)  # 2024是閏年
        assert result == ["2024-02-28", "2024-02-29"]
    
    def test_february_non_leap_year(self):
        """測試非閏年二月"""
        with pytest.raises(ValueError, match="無效的日期: 29"):
            parse_date_range("29", 2023, 2)  # 2023不是閏年
    
    def test_invalid_day_too_large(self):
        """測試日期過大"""
        with pytest.raises(ValueError, match="無效的日期: 32"):
            parse_date_range("32", 2024, 1)
    
    def test_invalid_day_too_small(self):
        """測試日期過小"""
        with pytest.raises(ValueError, match="無效的日期: 0"):
            parse_date_range("0", 2024, 1)
    
    def test_invalid_range_order(self):
        """測試無效的範圍順序"""
        with pytest.raises(ValueError, match="無效的日期範圍: 15-10"):
            parse_date_range("15-10", 2024, 1)
    
    def test_invalid_range_format(self):
        """測試無效的範圍格式"""
        with pytest.raises(ValueError, match="日期格式錯誤: abc"):
            parse_date_range("abc", 2024, 1)
        
        with pytest.raises(ValueError, match="日期範圍格式錯誤: 1-a"):
            parse_date_range("1-a", 2024, 1)
    
    def test_validate_date_input_valid(self):
        """測試有效輸入驗證"""
        assert validate_date_input("1,2,3") == ""
        assert validate_date_input("1-5") == ""
        assert validate_date_input("1,5-8,15") == ""
        assert validate_date_input("") == ""
    
    def test_validate_date_input_invalid(self):
        """測試無效輸入驗證"""
        assert "只能包含數字、逗號、連字號和空格" in validate_date_input("1,2,a")
        assert "不能有連續的分隔符" in validate_date_input("1,,2")
        assert "不能以分隔符開頭或結尾" in validate_date_input(",1,2")
    
    def test_format_dates_for_display(self):
        """測試日期格式化顯示"""
        assert format_dates_for_display([]) == "無"
        
        dates = ["2024-01-01", "2024-01-05", "2024-01-15"]
        assert format_dates_for_display(dates) == "1, 5, 15"
        
        # 測試大量日期
        many_dates = [f"2024-01-{i:02d}" for i in range(1, 11)]
        result = format_dates_for_display(many_dates)
        assert "1, 2, 3 ... 9, 10 (共10天)" == result


class TestDoctorModel:
    """測試醫師模型"""
    
    def test_doctor_creation_basic(self):
        """測試基本醫師建立"""
        doctor = Doctor(
            name="張醫師",
            role="主治",
            weekday_quota=5,
            holiday_quota=2
        )
        
        assert doctor.name == "張醫師"
        assert doctor.role == "主治"
        assert doctor.weekday_quota == 5
        assert doctor.holiday_quota == 2
        assert doctor.unavailable_dates == []
        assert doctor.preferred_dates == []
    
    def test_doctor_creation_with_dates(self):
        """測試帶日期的醫師建立"""
        unavailable = ["2024-01-01", "2024-01-15"]
        preferred = ["2024-01-10", "2024-01-20"]
        
        doctor = Doctor(
            name="李醫師",
            role="總醫師",
            weekday_quota=4,
            holiday_quota=1,
            unavailable_dates=unavailable,
            preferred_dates=preferred
        )
        
        assert doctor.unavailable_dates == unavailable
        assert doctor.preferred_dates == preferred
    
    def test_to_dict(self):
        """測試轉換為字典"""
        doctor = Doctor(
            name="王醫師",
            role="主治",
            weekday_quota=3,
            holiday_quota=2,
            unavailable_dates=["2024-01-01"],
            preferred_dates=["2024-01-15"]
        )
        
        result = doctor.to_dict()
        expected = {
            'name': '王醫師',
            'role': '主治',
            'weekday_quota': 3,
            'holiday_quota': 2,
            'unavailable_dates': ['2024-01-01'],
            'preferred_dates': ['2024-01-15']
        }
        
        assert result == expected
    
    def test_from_dict(self):
        """測試從字典建立"""
        data = {
            'name': '陳醫師',
            'role': '住院',
            'weekday_quota': 4,
            'holiday_quota': 1,
            'unavailable_dates': ['2024-01-05', '2024-01-10'],
            'preferred_dates': ['2024-01-20']
        }
        
        doctor = Doctor.from_dict(data)
        
        assert doctor.name == '陳醫師'
        assert doctor.role == '住院'
        assert doctor.weekday_quota == 4
        assert doctor.holiday_quota == 1
        assert doctor.unavailable_dates == ['2024-01-05', '2024-01-10']
        assert doctor.preferred_dates == ['2024-01-20']
    
    def test_is_available_on(self):
        """測試特定日期可用性檢查"""
        doctor = Doctor(
            name="劉醫師",
            role="主治",
            weekday_quota=5,
            holiday_quota=2,
            unavailable_dates=["2024-01-01", "2024-01-15"]
        )
        
        assert doctor.is_available_on("2024-01-01") == False
        assert doctor.is_available_on("2024-01-15") == False
        assert doctor.is_available_on("2024-01-02") == True
        assert doctor.is_available_on("2024-01-10") == True
    
    def test_prefers_date(self):
        """測試偏好日期檢查"""
        doctor = Doctor(
            name="黃醫師",
            role="總醫師",
            weekday_quota=4,
            holiday_quota=1,
            preferred_dates=["2024-01-10", "2024-01-20"]
        )
        
        assert doctor.prefers_date("2024-01-10") == True
        assert doctor.prefers_date("2024-01-20") == True
        assert doctor.prefers_date("2024-01-01") == False
        assert doctor.prefers_date("2024-01-15") == False
    
    def test_dict_roundtrip(self):
        """測試字典轉換的往返一致性"""
        original = Doctor(
            name="趙醫師",
            role="主治",
            weekday_quota=6,
            holiday_quota=3,
            unavailable_dates=["2024-01-01", "2024-01-05", "2024-01-10"],
            preferred_dates=["2024-01-15", "2024-01-20"]
        )
        
        dict_data = original.to_dict()
        restored = Doctor.from_dict(dict_data)
        
        assert restored.name == original.name
        assert restored.role == original.role
        assert restored.weekday_quota == original.weekday_quota
        assert restored.holiday_quota == original.holiday_quota
        assert restored.unavailable_dates == original.unavailable_dates
        assert restored.preferred_dates == original.preferred_dates
    
    def test_equality(self):
        """測試相等性"""
        doctor1 = Doctor(
            name="測試醫師",
            role="主治",
            weekday_quota=5,
            holiday_quota=2,
            unavailable_dates=["2024-01-01"],
            preferred_dates=["2024-01-15"]
        )
        
        doctor2 = Doctor(
            name="測試醫師",
            role="主治",
            weekday_quota=5,
            holiday_quota=2,
            unavailable_dates=["2024-01-01"],
            preferred_dates=["2024-01-15"]
        )
        
        assert doctor1 == doctor2
    
    def test_inequality(self):
        """測試不相等性"""
        doctor1 = Doctor(name="醫師A", role="主治", weekday_quota=5, holiday_quota=2)
        doctor2 = Doctor(name="醫師B", role="主治", weekday_quota=5, holiday_quota=2)
        
        assert doctor1 != doctor2


class TestSessionManager:
    """測試Session管理器"""
    
    def setup_method(self):
        """每個測試前的設置"""
        # 創建模擬的 streamlit 模組
        self.mock_streamlit = MagicMock()
        self.mock_streamlit.session_state = MagicMock()
        
        # 將模擬加入 sys.modules
        sys.modules['streamlit'] = self.mock_streamlit
        
        self.test_doctors = [
            Doctor(
                name="張醫師",
                role="主治",
                weekday_quota=5,
                holiday_quota=2,
                unavailable_dates=["2024-01-01"],
                preferred_dates=["2024-01-15"]
            ),
            Doctor(
                name="李醫師",
                role="總醫師",
                weekday_quota=4,
                holiday_quota=1,
                unavailable_dates=[],
                preferred_dates=["2024-01-10", "2024-01-20"]
            )
        ]
    
    def teardown_method(self):
        """每個測試後的清理"""
        if 'streamlit' in sys.modules:
            del sys.modules['streamlit']
    
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_save_doctors_success(self, mock_json_dump, mock_file, mock_makedirs):
        """測試成功儲存醫師資料"""
        self.mock_streamlit.session_state.doctors = self.test_doctors
        
        result = SessionManager.save_doctors()
        
        assert result == True
        mock_makedirs.assert_called_once_with('data/configs', exist_ok=True)
        mock_file.assert_called_once_with('data/configs/doctors.json', 'w', encoding='utf-8')
        
        call_args = mock_json_dump.call_args
        saved_data = call_args[0][0]
        
        assert 'doctors' in saved_data
        assert 'metadata' in saved_data
        assert len(saved_data['doctors']) == 2
        assert saved_data['metadata']['total_doctors'] == 2
        assert saved_data['metadata']['attending_count'] == 1
        assert saved_data['metadata']['resident_count'] == 1
    
    @patch('os.makedirs')
    @patch('builtins.open', side_effect=OSError("權限錯誤"))
    def test_save_doctors_failure(self, mock_file, mock_makedirs):
        """測試儲存醫師資料失敗"""
        self.mock_streamlit.session_state.doctors = self.test_doctors
        
        result = SessionManager.save_doctors()
        assert result == False
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.load')
    def test_load_doctors_success(self, mock_json_load, mock_file, mock_exists):
        """測試成功載入醫師資料"""
        mock_data = {
            'doctors': [
                {
                    'name': '王醫師',
                    'role': '主治',
                    'weekday_quota': 6,
                    'holiday_quota': 3,
                    'unavailable_dates': ['2024-01-05'],
                    'preferred_dates': []
                }
            ]
        }
        mock_json_load.return_value = mock_data
        self.mock_streamlit.session_state.doctors = []
        
        result = SessionManager.load_doctors()
        
        assert result == True
        mock_file.assert_called_once_with('data/configs/doctors.json', 'r', encoding='utf-8')
        assert len(self.mock_streamlit.session_state.doctors) == 1
        assert self.mock_streamlit.session_state.doctors[0].name == '王醫師'
    
    @patch('os.path.exists', return_value=False)
    def test_load_doctors_file_not_exists(self, mock_exists):
        """測試載入不存在的檔案"""
        result = SessionManager.load_doctors()
        assert result == False
    
    def test_get_doctors_summary_empty(self):
        """測試空醫師列表的摘要"""
        self.mock_streamlit.session_state.doctors = []
        
        summary = SessionManager.get_doctors_summary()
        
        assert summary['total'] == 0
        assert summary['attending'] == 0
        assert summary['resident'] == 0
        assert summary['has_constraints'] == 0
    
    def test_get_doctors_summary_with_data(self):
        """測試有資料的醫師摘要"""
        self.mock_streamlit.session_state.doctors = self.test_doctors
        
        summary = SessionManager.get_doctors_summary()
        
        assert summary['total'] == 2
        assert summary['attending'] == 1
        assert summary['resident'] == 1
        assert summary['has_constraints'] == 2
    
    def test_validate_doctors_data_empty(self):
        """測試驗證空醫師資料"""
        self.mock_streamlit.session_state.doctors = []
        
        problems = SessionManager.validate_doctors_data()
        
        assert len(problems) == 1
        assert "尚未新增任何醫師" in problems[0]
    
    def test_validate_doctors_data_duplicate_names(self):
        """測試驗證重複姓名"""
        duplicate_doctors = [
            Doctor(name="重複醫師", role="主治", weekday_quota=5, holiday_quota=2),
            Doctor(name="重複醫師", role="總醫師", weekday_quota=4, holiday_quota=1),
        ]
        self.mock_streamlit.session_state.doctors = duplicate_doctors
        
        problems = SessionManager.validate_doctors_data()
        
        duplicate_problem = [p for p in problems if "重複的醫師姓名" in p]
        assert len(duplicate_problem) == 1
        assert "重複醫師" in duplicate_problem[0]
    
    def test_validate_doctors_data_negative_quota(self):
        """測試驗證負數配額"""
        invalid_doctors = [
            Doctor(name="負配額醫師", role="主治", weekday_quota=-1, holiday_quota=2)
        ]
        self.mock_streamlit.session_state.doctors = invalid_doctors
        
        problems = SessionManager.validate_doctors_data()
        
        quota_problem = [p for p in problems if "配額不能為負數" in p]
        assert len(quota_problem) == 1
        assert "負配額醫師" in quota_problem[0]
    
    def test_validate_doctors_data_conflicting_dates(self):
        """測試驗證衝突日期"""
        conflict_doctors = [
            Doctor(
                name="衝突醫師",
                role="主治",
                weekday_quota=5,
                holiday_quota=2,
                unavailable_dates=["2024-01-01", "2024-01-15"],
                preferred_dates=["2024-01-01", "2024-01-10"]  # 2024-01-01 衝突
            )
        ]
        self.mock_streamlit.session_state.doctors = conflict_doctors
        
        problems = SessionManager.validate_doctors_data()
        
        conflict_problem = [p for p in problems if "衝突的日期設定" in p]
        assert len(conflict_problem) == 1
        assert "2024-01-01" in conflict_problem[0]
    
    def test_validate_doctors_data_valid(self):
        """測試驗證有效的醫師資料"""
        self.mock_streamlit.session_state.doctors = self.test_doctors
        
        problems = SessionManager.validate_doctors_data()
        
        assert len(problems) == 0


class TestIntegration:
    """整合測試"""
    
    def test_parse_and_format_workflow(self):
        """測試解析和格式化的完整流程"""
        input_str = "1,5-8,15,20-22"
        parsed = parse_date_range(input_str, 2024, 1)
        formatted = format_dates_for_display(parsed)
        
        # 修正：1(1個) + 5-8(4個) + 15(1個) + 20-22(3個) = 9個
        assert len(parsed) == 9  # 1, 5,6,7,8, 15, 20,21,22
        
        # 驗證格式化輸出
        assert "1, 5, 6" in formatted
        assert "共9天" in formatted
    
    def test_doctor_save_load_workflow(self):
        """測試醫師資料完整儲存載入流程"""
        # 設置模擬的 streamlit
        mock_streamlit = MagicMock()
        mock_streamlit.session_state = MagicMock()
        sys.modules['streamlit'] = mock_streamlit
        
        try:
            test_doctors = [
                Doctor(
                    name="完整測試醫師",
                    role="主治",
                    weekday_quota=7,
                    holiday_quota=3,
                    unavailable_dates=["2024-01-01", "2024-01-15"],
                    preferred_dates=["2024-01-10", "2024-01-20"]
                )
            ]
            
            mock_streamlit.session_state.doctors = test_doctors
            
            # 模擬儲存
            with patch('os.makedirs'):
                with patch('builtins.open', mock_open()) as mock_file:
                    with patch('json.dump') as mock_dump:
                        result = SessionManager.save_doctors()
                        assert result == True
                        saved_data = mock_dump.call_args[0][0]
            
            # 清空並載入
            mock_streamlit.session_state.doctors = []
            
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open()):
                    with patch('json.load', return_value=saved_data):
                        result = SessionManager.load_doctors()
            
            assert result == True
            assert len(mock_streamlit.session_state.doctors) == 1
            
            loaded_doctor = mock_streamlit.session_state.doctors[0]
            original_doctor = test_doctors[0]
            
            assert loaded_doctor.name == original_doctor.name
            assert loaded_doctor.role == original_doctor.role
            assert loaded_doctor.weekday_quota == original_doctor.weekday_quota
            assert loaded_doctor.holiday_quota == original_doctor.holiday_quota
            assert loaded_doctor.unavailable_dates == original_doctor.unavailable_dates
            assert loaded_doctor.preferred_dates == original_doctor.preferred_dates
        
        finally:
            # 清理
            if 'streamlit' in sys.modules:
                del sys.modules['streamlit']


# ==================== 測試執行器 ====================

def run_tests(test_type="all", verbose=True):
    """執行測試的主函數"""
    print("🧪 醫師管理系統測試開始...")
    
    args = [__file__]
    
    if verbose:
        args.append("-v")
    
    if test_type == "date":
        args.extend(["-k", "TestDateParser"])
    elif test_type == "doctor":
        args.extend(["-k", "TestDoctorModel"])
    elif test_type == "session":
        args.extend(["-k", "TestSessionManager"])
    elif test_type == "integration":
        args.extend(["-k", "TestIntegration"])
    
    # 添加測試統計
    args.extend(["--tb=short", "--durations=5"])
    
    exit_code = pytest.main(args)
    
    if exit_code == 0:
        print("✅ 所有測試通過！")
    else:
        print("❌ 測試失敗，請檢查錯誤訊息")
    
    return exit_code


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="醫師管理系統測試執行器")
    parser.add_argument(
        "--type", 
        choices=["all", "date", "doctor", "session", "integration"],
        default="all",
        help="測試類型：all(全部), date(日期解析), doctor(醫師模型), session(Session管理), integration(整合測試)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細輸出"
    )
    
    args = parser.parse_args()
    
    exit_code = run_tests(args.type, args.verbose)
    
    print(f"\n📊 測試統計:")
    print(f"   測試類型: {args.type}")
    print(f"   結果: {'✅ 通過' if exit_code == 0 else '❌ 失敗'}")
    
    # 顯示使用說明
    if exit_code == 0:
        print(f"\n💡 其他測試選項:")
        print(f"   python {__file__} --type date      # 只測試日期解析")
        print(f"   python {__file__} --type doctor    # 只測試醫師模型")
        print(f"   python {__file__} --type session   # 只測試Session管理")
        print(f"   python {__file__} --type integration # 只測試整合功能")
    
    exit(exit_code)