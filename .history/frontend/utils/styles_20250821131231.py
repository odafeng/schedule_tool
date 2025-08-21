"""
樣式管理模組
"""
import streamlit as st

def load_custom_css():
    """載入自訂CSS樣式"""
    st.markdown("""
    <style>
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            padding-left: 20px;
            padding-right: 20px;
            background-color: #f0f2f6;
            border-radius: 10px 10px 0 0;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1f77b4;
            color: white;
        }
        .doctor-card {
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .schedule-cell {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: center;
        }
        .attending-cell {
            background-color: #e3f2fd;
            color: #1976d2;
            font-weight: bold;
        }
        .resident-cell {
            background-color: #f3e5f5;
            color: #7b1fa2;
            font-weight: bold;
        }
        .empty-cell {
            background-color: #ffebee;
            color: #c62828;
        }
        .holiday-header {
            background-color: #ffcdd2;
            font-weight: bold;
        }
        .weekday-header {
            background-color: #c5cae9;
            font-weight: bold;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 10px 0;
        }
        .warning-box {
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            padding: 10px;
            margin: 10px 0;
        }
        .success-box {
            background-color: #d4edda;
            border: 1px solid #28a745;
            border-radius: 5px;
            padding: 10px;
            margin: 10px 0;
        }
    </style>
    """, unsafe_allow_html=True)

def get_calendar_css():
    """獲取月曆專用CSS"""
    return """
    <style>
        .calendar-table {
            width: 100%;
            border-collapse: collapse;
            font-family: Arial, sans-serif;
        }
        .calendar-table th {
            background-color: #2c3e50;
            color: white;
            padding: 10px;
            text-align: center;
            font-weight: bold;
        }
        .calendar-table td {
            border: 1px solid #ddd;
            padding: 5px;
            height: 120px;
            width: 14.28%;
            vertical-align: top;
            position: relative;
        }
        .calendar-date {
            font-weight: bold;
            margin-bottom: 5px;
            font-size: 14px;
        }
        .holiday-cell {
            background-color: #fff3e0;
        }
        .weekday-cell {
            background-color: #f5f5f5;
        }
        .doctor-info {
            font-size: 12px;
            margin: 2px 0;
            padding: 2px 4px;
            border-radius: 3px;
        }
        .attending {
            background-color: #e3f2fd;
            color: #1565c0;
        }
        .resident {
            background-color: #f3e5f5;
            color: #6a1b9a;
        }
        .empty-slot {
            background-color: #ffcdd2;
            color: #c62828;
            font-weight: bold;
            margin: 2px 0;
            padding: 2px 4px;
            border-radius: 3px;
        }
        .available-doctors {
            font-size: 10px;
            color: #666;
            font-style: italic;
            margin-top: 2px;
        }
        .empty-cell {
            background-color: #f0f0f0;
        }
    </style>
    """