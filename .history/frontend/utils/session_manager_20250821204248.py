"""
Session狀態管理器 - 確保日期格式正確版本
"""
import streamlit as st
import json
import os
from datetime import datetime
from typing import List, Set

from backend.models import Doctor, ScheduleConstraints
from backend.utils.holiday_manager import HolidayManager
from backend.utils.date_parser import convert_dates_for_storage, normalize_dates_to_full_format

class SessionManager:
    """管理Streamlit Session State"""
    
    @staticmethod
    def initialize():
        """初始化Session State"""
        if 'doctors' not in st.session_state:
            st.session_state.doctors = []
        
        # 初始化假日管理器
        if 'holiday_manager' not in st.session_state:
            st.session_state.holiday_manager = HolidayManager()
        
        # 為了向後兼容，提供 holidays 和 workdays 屬性
        # 這些會從 holiday_manager 動態取得
        if 'holidays' not in st.session_state:
            st.session_state.holidays = set()
        
        if 'workdays' not in st.session_state:
            st.session_state.workdays = set()
        
        if 'schedule_result' not in st.session_state:
            st.session_state.schedule_result = None

        if 'selected_year' not in st.session_state:
            st.session_state.selected_year = datetime.now().year
            
        if 'selected_month' not in st.session_state:
            st.session_state.selected_month = datetime.now().month

        if 'csp_stats' not in st.session_state:
            st.session_state.csp_stats = None

        if 'use_ac3' not in st.session_state:
            st.session_state.use_ac3 = True

        if 'use_backjump' not in st.session_state:
            st.session_state.use_backjump = True

        if 'solution_pool' not in st.session_state:
            st.session_state.solution_pool = None

        if 'last_scheduler' not in st.session_state:
            st.session_state.last_scheduler = None
            
        if 'constraints' not in st.session_state:
            st.session_state.constraints = ScheduleConstraints()
        
        # 同步假日資料
        SessionManager.sync_holiday_data()
    
    @staticmethod
    def sync_holiday_data():
        """同步假日資料到 session state（向後兼容）"""
        holiday_manager = st.session_state.holiday_manager
        year = st.session_state.selected_year
        month = st.session_state.selected_month
        
        holidays, workdays = holiday_manager.get_holidays_for_month(year, month)
        st.session_state.holidays = holidays
        st.session_state.workdays = workdays
    
    @staticmethod
    def get_current_holidays_and_workdays():
        """從假日管理器取得當前月份的假日和補班日"""
        holiday_manager = st.session_state.holiday_manager
        year = st.session_state.selected_year
        month = st.session_state.selected_month
        
        holidays, workdays = holiday_manager.get_holidays_for_month(year, month)
        return holidays, workdays
    
    @staticmethod
    def render_sidebar_settings():
        """渲染側邊欄設定"""
        # 月份選擇
        st.subheader("📅 排班月份")
        col1, col2 = st.columns(2)
        with col1:
            year = st.number_input("年份", min_value=2024, max_value=2030, 
                                  value=st.session_state.selected_year)
            if year != st.session_state.selected_year:
                st.session_state.selected_year = year
                SessionManager.sync_holiday_data()  # 同步假日資料
        with col2:
            month = st.selectbox("月份", range(1, 13), 
                               index=st.session_state.selected_month - 1,
                               format_func=lambda x: f"{x}月")
            if month != st.session_state.selected_month:
                st.session_state.selected_month = month
                SessionManager.sync_holiday_data()  # 同步假日資料
        
        # 顯示當月假日資訊
        holidays, workdays = SessionManager.get_current_holidays_and_workdays()
        
        st.info(f"""
        📊 **{year}年{month}月**
        - 非週末假日數：{len(holidays)}
        - 補班日數：{len(workdays)}
        """)
        
        st.divider()
        
        # 演算法參數
        st.subheader("🔧 演算法參數")
        constraints = st.session_state.constraints
        
        constraints.max_consecutive_days = st.slider(
            "最大連續值班天數", 1, 5, 
            constraints.max_consecutive_days
        )
        constraints.beam_width = st.slider(
            "束搜索寬度", 3, 10, 
            constraints.beam_width
        )
        constraints.csp_timeout = st.slider(
            "CSP超時(秒)", 5, 30, 
            constraints.csp_timeout
        )
        
        # 進階CSP設定
        with st.expander("🎯 進階CSP設定", expanded=False):
            st.info("""
            **Arc Consistency (AC-3)**
            透過約束傳播提前偵測無解，大幅減少搜索空間
            
            **Conflict-Directed Backjumping**
            智慧回溯機制，直接跳回衝突源頭，避免無謂搜索
            """)
            
            st.session_state.use_ac3 = st.checkbox(
                "啟用 Arc Consistency", 
                value=st.session_state.use_ac3,
                help="使用AC-3演算法進行約束傳播"
            )
            st.session_state.use_backjump = st.checkbox(
                "啟用 Conflict-Directed Backjumping", 
                value=st.session_state.use_backjump,
                help="使用智慧回溯避免無謂搜索"
            )
            
            constraints.neighbor_expansion = st.slider(
                "鄰域展開上限", 5, 20, 
                constraints.neighbor_expansion,
                help="每個變數展開的最大候選數"
            )
        
        st.session_state.constraints = constraints
        st.divider()
        
        # 資料管理
        st.subheader("💾 資料管理")
        
        # 儲存按鈕
        if st.button("💾 儲存所有設定", use_container_width=True):
            SessionManager.save_settings()
            st.success("設定已儲存！")
        
        # 載入按鈕
        if st.button("📂 載入設定", use_container_width=True):
            if SessionManager.load_settings():
                st.success("設定已載入！")
                st.rerun()
            else:
                st.error("找不到儲存的設定檔案")
        
        # 重置假日設定
        if st.button("🔄 重置假日設定", use_container_width=True):
            if st.session_state.holiday_manager.clear_user_defined_holidays():
                st.success("已重置假日設定")
                st.rerun()
    
    @staticmethod
    def save_settings():
        """儲存設定到檔案"""
        # 確保日期格式正確
        year = st.session_state.selected_year
        month = st.session_state.selected_month
        
        # 準備醫師資料，確保日期格式正確
        doctors_data = []
        for doctor in st.session_state.doctors:
            doctor_dict = doctor.to_dict()
            # 確保日期格式為 YYYY-MM-DD
            doctor_dict['unavailable_dates'] = convert_dates_for_storage(
                doctor_dict.get('unavailable_dates', []), year, month
            )
            doctor_dict['preferred_dates'] = convert_dates_for_storage(
                doctor_dict.get('preferred_dates', []), year, month
            )
            doctors_data.append(doctor_dict)
        
        save_data = {
            'doctors': doctors_data,
            'year': year,
            'month': month,
            'use_ac3': st.session_state.get('use_ac3', True),
            'use_backjump': st.session_state.get('use_backjump', True),
            'constraints': {
                'max_consecutive_days': st.session_state.constraints.max_consecutive_days,
                'beam_width': st.session_state.constraints.beam_width,
                'csp_timeout': st.session_state.constraints.csp_timeout,
                'neighbor_expansion': st.session_state.constraints.neighbor_expansion
            }
        }
        
        # 確保目錄存在
        os.makedirs('data/configs', exist_ok=True)
        
        with open('data/configs/schedule_settings.json', 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        # 假日設定會自動儲存在 holiday_manager 中
        st.session_state.holiday_manager.save_config()
    
    @staticmethod
    def load_settings() -> bool:
        """從檔案載入設定"""
        settings_file = 'data/configs/schedule_settings.json'
        
        if not os.path.exists(settings_file):
            return False
        
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            year = save_data.get('year', datetime.now().year)
            month = save_data.get('month', datetime.now().month)
            
            # 載入醫師資料，確保日期格式正確
            doctors = []
            for doctor_dict in save_data.get('doctors', []):
                # 確保日期格式正確
                doctor_dict['unavailable_dates'] = normalize_dates_to_full_format(
                    doctor_dict.get('unavailable_dates', []), year, month
                )
                doctor_dict['preferred_dates'] = normalize_dates_to_full_format(
                    doctor_dict.get('preferred_dates', []), year, month
                )
                doctors.append(Doctor.from_dict(doctor_dict))
            
            st.session_state.doctors = doctors
            st.session_state.selected_year = year
            st.session_state.selected_month = month
            st.session_state.use_ac3 = save_data.get('use_ac3', True)
            st.session_state.use_backjump = save_data.get('use_backjump', True)
            
            if 'constraints' in save_data:
                c = save_data['constraints']
                st.session_state.constraints = ScheduleConstraints(
                    max_consecutive_days=c.get('max_consecutive_days', 2),
                    beam_width=c.get('beam_width', 5),
                    csp_timeout=c.get('csp_timeout', 10),
                    neighbor_expansion=c.get('neighbor_expansion', 10)
                )
            
            # 重新載入假日管理器
            st.session_state.holiday_manager = HolidayManager()
            
            return True
        except Exception as e:
            st.error(f"載入設定時發生錯誤: {str(e)}")
            return False
    
    @staticmethod
    def save_doctors():
        """儲存醫師資料到獨立檔案（確保日期格式正確）"""
        year = st.session_state.selected_year
        month = st.session_state.selected_month
        
        # 準備醫師資料，確保日期格式正確
        doctors_list = []
        for doctor in st.session_state.doctors:
            doctor_dict = doctor.to_dict()
            # 確保日期格式為 YYYY-MM-DD
            doctor_dict['unavailable_dates'] = convert_dates_for_storage(
                doctor_dict.get('unavailable_dates', []), year, month
            )
            doctor_dict['preferred_dates'] = convert_dates_for_storage(
                doctor_dict.get('preferred_dates', []), year, month
            )
            doctors_list.append(doctor_dict)
        
        doctors_data = {
            'doctors': doctors_list,
            'metadata': {
                'saved_at': datetime.now().isoformat(),
                'format_version': '2.0',
                'date_format': 'YYYY-MM-DD',
                'year': year,
                'month': month,
                'total_doctors': len(st.session_state.doctors),
                'attending_count': len([d for d in st.session_state.doctors if d.role == "主治"]),
                'resident_count': len([d for d in st.session_state.doctors if d.role == "總醫師"])
            }
        }
        
        # 確保目錄存在
        os.makedirs('data/configs', exist_ok=True)
        
        try:
            # 先儲存到臨時檔案
            temp_file = 'data/configs/doctors.json.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(doctors_data, f, ensure_ascii=False, indent=2)
            
            # 成功寫入後才覆蓋原檔案
            final_file = 'data/configs/doctors.json'
            if os.path.exists(temp_file):
                if os.path.exists(final_file):
                    # 備份原檔案
                    backup_file = f"{final_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    os.rename(final_file, backup_file)
                os.rename(temp_file, final_file)
            
            return True
        except Exception as e:
            st.error(f"儲存醫師資料時發生錯誤: {str(e)}")
            # 清理臨時檔案
            if os.path.exists('data/configs/doctors.json.tmp'):
                os.remove('data/configs/doctors.json.tmp')
            return False
    
    @staticmethod
    def load_doctors() -> bool:
        """從獨立檔案載入醫師資料（處理各種日期格式）"""
        doctors_file = 'data/configs/doctors.json'
        
        # 嘗試不同的檔案位置
        possible_files = [
            doctors_file,
            'doctors.json',
            'data/doctors.json'
        ]
        
        actual_file = None
        for file_path in possible_files:
            if os.path.exists(file_path):
                actual_file = file_path
                break
        
        if not actual_file:
            return False
        
        try:
            with open(actual_file, 'r', encoding='utf-8') as f:
                doctors_data = json.load(f)
            
            # 取得年月資訊（優先使用metadata中的，否則使用當前）
            metadata = doctors_data.get('metadata', {})
            year = metadata.get('year', st.session_state.selected_year)
            month = metadata.get('month', st.session_state.selected_month)
            
            # 清空現有醫師資料
            st.session_state.doctors = []
            
            # 載入醫師資料，確保日期格式正確
            if 'doctors' in doctors_data:
                for doctor_dict in doctors_data['doctors']:
                    # 標準化日期格式
                    doctor_dict['unavailable_dates'] = normalize_dates_to_full_format(
                        doctor_dict.get('unavailable_dates', []), year, month
                    )
                    doctor_dict['preferred_dates'] = normalize_dates_to_full_format(
                        doctor_dict.get('preferred_dates', []), year, month
                    )
                    
                    doctor = Doctor.from_dict(doctor_dict)
                    st.session_state.doctors.append(doctor)
            
            return True
            
        except Exception as e:
            st.error(f"載入醫師資料時發生錯誤: {str(e)}")
            return False
    
    @staticmethod
    def get_doctors_summary() -> dict:
        """取得醫師資料摘要"""
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
            # 檢查配額
            if doctor.weekday_quota < 0 or doctor.holiday_quota < 0:
                problems.append(f"醫師 {doctor.name} 的配額不能為負數")
            
            # 檢查日期格式（應該都是 YYYY-MM-DD 格式）
            for date_str in doctor.unavailable_dates + doctor.preferred_dates:
                if isinstance(date_str, str):
                    # 檢查是否為正確的 YYYY-MM-DD 格式
                    try:
                        datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        problems.append(f"醫師 {doctor.name} 的日期格式錯誤: {date_str}")
                else:
                    problems.append(f"醫師 {doctor.name} 的日期類型錯誤: {type(date_str)}")
            
            # 檢查衝突日期
            conflicts = set(doctor.unavailable_dates) & set(doctor.preferred_dates)
            if conflicts:
                conflicts_str = ', '.join(sorted(conflicts)[:5])
                if len(conflicts) > 5:
                    conflicts_str += f"... (共{len(conflicts)}個)"
                problems.append(f"醫師 {doctor.name} 有衝突的日期設定: {conflicts_str}")
        
        return problems