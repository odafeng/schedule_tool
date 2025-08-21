"""
遷移腳本：將 doctors.json 從整數日期格式轉換為 YYYY-MM-DD 格式
請執行此腳本一次來修正您的現有資料
"""
import json
import os
from datetime import datetime, date

def migrate_doctors_json(filename='doctors.json', data_dir='data/configs', year=2025, month=8):
    """
    將 doctors.json 中的整數日期轉換為 YYYY-MM-DD 格式
    
    Args:
        filename: 檔案名稱
        data_dir: 資料目錄路徑
        year: 年份
        month: 月份
    """
    # 檢查不同可能的檔案位置
    possible_paths = [
        filename,  # 當前目錄
        os.path.join(data_dir, filename),  # data/configs 目錄
        os.path.join('data', filename),  # data 目錄
    ]
    
    file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            break
    
    if not file_path:
        print(f"❌ 找不到 {filename} 檔案")
        print(f"已檢查路徑: {possible_paths}")
        return None
    
    print(f"📂 找到檔案: {file_path}")
    
    # 讀取現有檔案
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 備份原始檔案
    backup_filename = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已建立備份: {backup_filename}")
    
    # 轉換每個醫師的日期
    converted_count = 0
    for doctor in data['doctors']:
        name = doctor['name']
        converted = False
        
        # 轉換 unavailable_dates
        new_unavailable = []
        for date_item in doctor.get('unavailable_dates', []):
            if isinstance(date_item, int):
                # 將整數日期轉換為 YYYY-MM-DD 格式
                if 1 <= date_item <= 31:
                    date_str = date(year, month, date_item).strftime('%Y-%m-%d')
                    new_unavailable.append(date_str)
                    converted = True
                else:
                    print(f"⚠️ {name}: 無效的日期數字 {date_item}")
            elif isinstance(date_item, str):
                if date_item.isdigit():
                    # 字串數字轉換為 YYYY-MM-DD 格式
                    day = int(date_item)
                    if 1 <= day <= 31:
                        date_str = date(year, month, day).strftime('%Y-%m-%d')
                        new_unavailable.append(date_str)
                        converted = True
                    else:
                        print(f"⚠️ {name}: 無效的日期數字 {date_item}")
                else:
                    # 保留已經是正確格式的日期
                    new_unavailable.append(date_item)
            else:
                print(f"⚠️ {name}: 未知的日期類型 {type(date_item)}: {date_item}")
        
        doctor['unavailable_dates'] = sorted(new_unavailable)
        
        # 轉換 preferred_dates
        new_preferred = []
        for date_item in doctor.get('preferred_dates', []):
            if isinstance(date_item, int):
                # 將整數日期轉換為 YYYY-MM-DD 格式
                if 1 <= date_item <= 31:
                    date_str = date(year, month, date_item).strftime('%Y-%m-%d')
                    new_preferred.append(date_str)
                    converted = True
                else:
                    print(f"⚠️ {name}: 無效的日期數字 {date_item}")
            elif isinstance(date_item, str):
                if date_item.isdigit():
                    # 字串數字轉換為 YYYY-MM-DD 格式
                    day = int(date_item)
                    if 1 <= day <= 31:
                        date_str = date(year, month, day).strftime('%Y-%m-%d')
                        new_preferred.append(date_str)
                        converted = True
                    else:
                        print(f"⚠️ {name}: 無效的日期數字 {date_item}")
                else:
                    # 保留已經是正確格式的日期
                    new_preferred.append(date_item)
            else:
                print(f"⚠️ {name}: 未知的日期類型 {type(date_item)}: {date_item}")
        
        doctor['preferred_dates'] = sorted(new_preferred)
        
        if converted:
            converted_count += 1
            print(f"✅ 已轉換 {name} 的日期格式")
            print(f"   不可值班: {len(doctor['unavailable_dates'])} 天")
            print(f"   優先值班: {len(doctor['preferred_dates'])} 天")
    
    # 更新元資料
    data['metadata']['migrated_at'] = datetime.now().isoformat()
    data['metadata']['format_version'] = '2.0'
    data['metadata']['date_format'] = 'YYYY-MM-DD'
    
    # 寫入更新後的檔案
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 遷移完成！已轉換 {converted_count} 位醫師的日期格式")
    print(f"📁 原始檔案已備份至: {backup_filename}")
    
    return data

def verify_migration(filename='doctors.json', data_dir='data/configs'):
    """
    驗證所有日期都是正確格式
    """
    # 檢查不同可能的檔案位置
    possible_paths = [
        filename,
        os.path.join(data_dir, filename),
        os.path.join('data', filename),
    ]
    
    file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            break
    
    if not file_path:
        print(f"❌ 找不到 {filename} 檔案")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues = []
    
    for doctor in data['doctors']:
        name = doctor['name']
        
        # 檢查 unavailable_dates
        for date_item in doctor.get('unavailable_dates', []):
            if isinstance(date_item, int):
                issues.append(f"{name}: unavailable_dates 包含整數 {date_item}")
            elif isinstance(date_item, str):
                if date_item.isdigit():
                    issues.append(f"{name}: unavailable_dates 包含數字字串 {date_item}")
                else:
                    try:
                        datetime.strptime(date_item, '%Y-%m-%d')
                    except ValueError:
                        issues.append(f"{name}: unavailable_dates 包含無效日期 {date_item}")
        
        # 檢查 preferred_dates
        for date_item in doctor.get('preferred_dates', []):
            if isinstance(date_item, int):
                issues.append(f"{name}: preferred_dates 包含整數 {date_item}")
            elif isinstance(date_item, str):
                if date_item.isdigit():
                    issues.append(f"{name}: preferred_dates 包含數字字串 {date_item}")
                else:
                    try:
                        datetime.strptime(date_item, '%Y-%m-%d')
                    except ValueError:
                        issues.append(f"{name}: preferred_dates 包含無效日期 {date_item}")
    
    if issues:
        print("❌ 發現問題:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ 所有日期都是正確的 YYYY-MM-DD 格式！")
        return True

def show_sample_data(data):
    """顯示範例資料"""
    if data and data.get('doctors'):
        print("\n" + "="*50)
        print("📊 轉換後的資料範例:")
        
        # 顯示第一位醫師的資料
        sample_doctor = data['doctors'][0]
        print(f"\n醫師: {sample_doctor['name']}")
        print(f"角色: {sample_doctor['role']}")
        print(f"平日配額: {sample_doctor['weekday_quota']}")
        print(f"假日配額: {sample_doctor['holiday_quota']}")
        
        # 顯示前5個不可值班日期
        unavail = sample_doctor.get('unavailable_dates', [])
        if unavail:
            print(f"不可值班日期 (前5個): {unavail[:5]}")
        
        # 顯示前5個優先值班日期
        pref = sample_doctor.get('preferred_dates', [])
        if pref:
            print(f"優先值班日期 (前5個): {pref[:5]}")

if __name__ == "__main__":
    print("🔄 開始遷移 doctors.json...")
    print("="*50)
    
    # 設定當前年月（請根據實際情況調整）
    YEAR = 2025
    MONTH = 8  # 8月
    
    try:
        # 執行遷移
        migrated_data = migrate_doctors_json(year=YEAR, month=MONTH)
        
        if migrated_data:
            # 驗證遷移結果
            print("\n" + "="*50)
            print("📋 驗證遷移結果:")
            verify_migration()
            
            # 顯示範例資料
            show_sample_data(migrated_data)
            
            print("\n" + "="*50)
            print("✅ 遷移成功完成！")
            print("📌 請重新啟動您的 Streamlit 應用程式")
        
    except Exception as e:
        print(f"❌ 遷移失敗: {e}")
        print("請檢查您的 doctors.json 檔案格式")
        import traceback
        traceback.print_exc()