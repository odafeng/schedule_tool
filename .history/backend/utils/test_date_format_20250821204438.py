"""
測試日期格式處理是否正確
執行此腳本來驗證系統能正確處理各種日期輸入格式
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.date_parser import (
    parse_date_range, 
    validate_date_input,
    format_dates_for_display,
    normalize_dates_to_full_format,
    convert_dates_for_storage
)
from backend.models import Doctor
import json
from datetime import datetime

def test_date_parser():
    """測試日期解析功能"""
    print("="*60)
    print("測試 1: 日期解析器")
    print("="*60)
    
    test_cases = [
        ("1,3,5-7,10", 2025, 8, "單個日期和範圍混合"),
        ("15-20,25", 2025, 8, "多個範圍"),
        ("1", 2025, 8, "單個日期"),
        ("1-31", 2025, 2, "二月全月（應處理月份天數）"),
        ("10,11,12,15-17", 2025, 8, "使用者輸入範例"),
    ]
    
    for input_str, year, month, description in test_cases:
        print(f"\n測試: {description}")
        print(f"輸入: '{input_str}' ({year}年{month}月)")
        
        # 驗證輸入
        error = validate_date_input(input_str)
        if error:
            print(f"❌ 驗證錯誤: {error}")
            continue
        
        # 解析日期
        try:
            dates = parse_date_range(input_str, year, month)
            print(f"✅ 解析成功: {len(dates)} 個日期")
            
            # 顯示前幾個結果
            if len(dates) <= 5:
                print(f"   結果: {dates}")
            else:
                print(f"   結果: {dates[:3]} ... {dates[-2:]}")
            
            # 測試顯示格式
            display = format_dates_for_display(dates)
            print(f"   顯示: {display}")
            
            # 驗證格式
            for date_str in dates:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    print(f"   ❌ 格式錯誤: {date_str}")
                    
        except Exception as e:
            print(f"❌ 解析失敗: {e}")

def test_doctor_model():
    """測試 Doctor 模型的日期處理"""
    print("\n" + "="*60)
    print("測試 2: Doctor 模型")
    print("="*60)
    
    # 測試各種輸入格式
    test_data = [
        {
            'name': '測試醫師1',
            'role': '主治',
            'unavailable_dates': [5, 6, 7],  # 整數格式
            'preferred_dates': [10, 15]
        },
        {
            'name': '測試醫師2',
            'role': '總醫師',
            'unavailable_dates': ["8", "9", "10"],  # 字串數字格式
            'preferred_dates': ["20", "25"]
        },
        {
            'name': '測試醫師3',
            'role': '主治',
            'unavailable_dates': ["2025-08-11", "2025-08-12"],  # 正確格式
            'preferred_dates': ["2025-08-18", "2025-08-19"]
        }
    ]
    
    for data in test_data:
        print(f"\n測試醫師: {data['name']}")
        print(f"  原始不可值班: {data['unavailable_dates']}")
        print(f"  原始優先值班: {data['preferred_dates']}")
        
        # 創建 Doctor 物件
        doctor = Doctor.from_dict(data)
        
        print(f"  轉換後不可值班: {doctor.unavailable_dates}")
        print(f"  轉換後優先值班: {doctor.preferred_dates}")
        
        # 驗證格式
        all_dates = doctor.unavailable_dates + doctor.preferred_dates
        format_ok = True
        for date_str in all_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except:
                format_ok = False
                print(f"  ❌ 格式錯誤: {date_str}")
        
        if format_ok:
            print(f"  ✅ 所有日期格式正確")
        
        # 測試序列化
        doctor_dict = doctor.to_dict()
        print(f"  序列化結果: 不可值班 {len(doctor_dict['unavailable_dates'])}天, "
              f"優先值班 {len(doctor_dict['preferred_dates'])}天")

def test_storage_format():
    """測試儲存格式轉換"""
    print("\n" + "="*60)
    print("測試 3: 儲存格式轉換")
    print("="*60)
    
    # 測試混合格式轉換
    mixed_dates = [
        5,                    # 整數
        "7",                  # 字串數字
        "10-12",             # 範圍字串
        "2025-08-15",        # 已經是正確格式
        20                   # 整數
    ]
    
    print(f"混合輸入: {mixed_dates}")
    
    # 轉換為儲存格式
    converted = convert_dates_for_storage(mixed_dates, 2025, 8)
    print(f"轉換結果: {converted}")
    
    # 驗證所有結果都是 YYYY-MM-DD 格式
    all_valid = True
    for date_str in converted:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except:
            all_valid = False
            print(f"❌ 無效格式: {date_str}")
    
    if all_valid:
        print("✅ 所有日期都已轉換為正確格式")

def test_json_compatibility():
    """測試 JSON 序列化相容性"""
    print("\n" + "="*60)
    print("測試 4: JSON 相容性")
    print("="*60)
    
    # 創建測試資料
    test_doctor = Doctor(
        name="JSON測試醫師",
        role="主治",
        weekday_quota=5,
        holiday_quota=2,
        unavailable_dates=[1, 2, 3, "5-7"],  # 混合格式
        preferred_dates=["10", 15, "20-22"]  # 混合格式
    )
    
    # 轉換為字典
    doctor_dict = test_doctor.to_dict()
    
    # 序列化為 JSON
    try:
        json_str = json.dumps(doctor_dict, ensure_ascii=False, indent=2)
        print("✅ JSON 序列化成功")
        
        # 反序列化
        loaded_dict = json.loads(json_str)
        
        # 重新創建 Doctor 物件
        loaded_doctor = Doctor.from_dict(loaded_dict)
        
        print(f"原始物件: {test_doctor.name}")
        print(f"  不可值班: {test_doctor.unavailable_dates}")
        print(f"  優先值班: {test_doctor.preferred_dates}")
        
        print(f"載入物件: {loaded_doctor.name}")
        print(f"  不可值班: {loaded_doctor.unavailable_dates}")
        print(f"  優先值班: {loaded_doctor.preferred_dates}")
        
        # 驗證格式
        all_dates = loaded_doctor.unavailable_dates + loaded_doctor.preferred_dates
        all_valid = all(
            isinstance(d, str) and len(d.split("-")) == 3 
            for d in all_dates
        )
        
        if all_valid:
            print("✅ 所有日期都保持正確格式")
        else:
            print("❌ 日期格式有問題")
            
    except Exception as e:
        print(f"❌ JSON 處理失敗: {e}")

def main():
    """執行所有測試"""
    print("🔧 醫師排班系統 - 日期格式測試")
    print("="*60)
    
    try:
        test_date_parser()
        test_doctor_model()
        test_storage_format()
        test_json_compatibility()
        
        print("\n" + "="*60)
        print("✅ 測試完成！")
        print("\n重要提醒：")
        print("1. 使用者輸入 '11,12,13,15-17' 會自動轉換為完整日期格式")
        print("2. 儲存時所有日期都會是 'YYYY-MM-DD' 格式")
        print("3. 載入時會自動處理各種格式並標準化")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 測試過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
    input("\n按 Enter 鍵結束...")