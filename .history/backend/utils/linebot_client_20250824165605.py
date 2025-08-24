"""
LINE Bot 客戶端模組
用於發送排班通知到 LINE 群組
"""

import os
import json
from typing import Optional, Dict, List
from datetime import datetime
import requests
from dataclasses import dataclass


@dataclass
class LineConfig:
    """LINE Bot 設定"""
    channel_access_token: str
    api_endpoint: str = "https://api.line.me/v2/bot"
    
    @classmethod
    def from_env(cls) -> Optional['LineConfig']:
        """從環境變數讀取設定"""
        token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
        if not token:
            # 如果環境變數沒有，使用硬編碼的 token（實際部署時應該用環境變數）
            token = "leiv7npdds1dj0xI2IOg4VJnUA6TownRppuW5w8mYmuGyn+qwh6K0ncQztrzOd+Gr75MpdRaWI1ZBWacN/NLIUPvAJyMskGZndToo/LSE+YMlIqt1hVcoMWFiTa2uTPxslbt6Rbur5uDgp7g6Ip87AdB04t89/1O/w1cDnyilFU="
        
        if token:
            return cls(channel_access_token=token)
        return None


class LineBotClient:
    """LINE Bot 客戶端"""
    
    def __init__(self, config: Optional[LineConfig] = None):
        """初始化 LINE Bot 客戶端"""
        self.config = config or LineConfig.from_env()
        if not self.config:
            raise ValueError("LINE Channel Access Token 未設定")
        
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.config.channel_access_token}'
        }
    
    def broadcast_message(self, message: str) -> Dict:
        """
        廣播訊息給所有追蹤者
        
        Args:
            message: 要發送的訊息
            
        Returns:
            API 回應
        """
        url = f"{self.config.api_endpoint}/message/broadcast"
        
        payload = {
            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return {
                "success": True,
                "message": "訊息已成功發送到 LINE",
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "message": f"發送失敗: {str(e)}",
                "error": str(e)
            }
    
    def send_flex_message(self, flex_content: Dict) -> Dict:
        """
        發送 Flex Message（更豐富的訊息格式）
        
        Args:
            flex_content: Flex Message 內容
            
        Returns:
            API 回應
        """
        url = f"{self.config.api_endpoint}/message/broadcast"
        
        payload = {
            "messages": [flex_content]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return {
                "success": True,
                "message": "Flex Message 已成功發送",
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "message": f"發送失敗: {str(e)}",
                "error": str(e)
            }
    
    def create_schedule_flex_message(self, 
                                    year: int, 
                                    month: int,
                                    statistics: Dict,
                                    download_url: Optional[str] = None) -> Dict:
        """
        建立排班通知的 Flex Message
        
        Args:
            year: 年份
            month: 月份
            statistics: 統計資料
            download_url: 下載連結
            
        Returns:
            Flex Message 內容
        """
        # 建立統計項目
        stat_contents = []
        
        # 總天數
        if 'total_days' in statistics:
            stat_contents.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": "總天數",
                        "size": "sm",
                        "color": "#555555",
                        "flex": 0
                    },
                    {
                        "type": "text",
                        "text": str(statistics['total_days']),
                        "size": "sm",
                        "color": "#111111",
                        "align": "end"
                    }
                ]
            })
        
        # 參與醫師數
        if 'doctor_count' in statistics:
            stat_contents.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": "參與醫師",
                        "size": "sm",
                        "color": "#555555",
                        "flex": 0
                    },
                    {
                        "type": "text",
                        "text": f"{statistics['doctor_count']} 位",
                        "size": "sm",
                        "color": "#111111",
                        "align": "end"
                    }
                ]
            })
        
        # 建立按鈕
        actions = []
        
        if download_url:
            actions.append({
                "type": "button",
                "style": "primary",
                "height": "sm",
                "action": {
                    "type": "uri",
                    "label": "📥 下載 PDF",
                    "uri": download_url
                }
            })
        
        # 建立 Flex Message
        flex_message = {
            "type": "flex",
            "altText": f"{year}年{month}月排班表已發佈",
            "contents": {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": "https://scdn.line-apps.com/n/channel_devcenter/img/fx/01_1_cafe.png",
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "排班通知",
                            "weight": "bold",
                            "size": "xl",
                            "color": "#1DB446"
                        },
                        {
                            "type": "text",
                            "text": f"{year}年{month}月",
                            "size": "md",
                            "color": "#666666",
                            "margin": "md"
                        },
                        {
                            "type": "separator",
                            "margin": "xxl"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "margin": "xxl",
                            "spacing": "sm",
                            "contents": stat_contents
                        },
                        {
                            "type": "separator",
                            "margin": "xxl"
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "md",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"發佈時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
                                    "size": "xs",
                                    "color": "#aaaaaa",
                                    "flex": 0
                                }
                            ]
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": actions,
                    "flex": 0
                } if actions else None
            }
        }
        
        # 如果沒有 footer，移除它
        if not flex_message["contents"].get("footer"):
            del flex_message["contents"]["footer"]
        
        return flex_message
    
    def test_connection(self) -> bool:
        """
        測試 LINE Bot 連線
        
        Returns:
            是否連線成功
        """
        url = f"{self.config.api_endpoint}/info"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return True
        except:
            return False


# Singleton instance
_line_bot_client: Optional[LineBotClient] = None


def get_line_bot_client() -> Optional[LineBotClient]:
    """取得 LINE Bot 客戶端實例"""
    global _line_bot_client
    
    if _line_bot_client is None:
        try:
            _line_bot_client = LineBotClient()
        except ValueError:
            return None
    
    return _line_bot_client


def format_schedule_message(year: int, 
                           month: int,
                           schedule: Dict,
                           doctors: List,
                           statistics: Dict,
                           download_url: Optional[str] = None) -> str:
    """
    格式化排班訊息（純文字版本）
    
    Args:
        year: 年份
        month: 月份
        schedule: 排班資料
        doctors: 醫師列表
        statistics: 統計資料
        download_url: 下載連結
        
    Returns:
        格式化的訊息文字
    """
    # 建立訊息
    lines = [
        f"📅 {year}年{month}月 排班表發佈通知",
        "",
        "=" * 30,
        ""
    ]
    
    # 加入統計資訊
    if statistics:
        lines.append("📊 排班統計")
        
        if 'doctor_duties' in statistics:
            total_doctors = len(statistics['doctor_duties'])
            lines.append(f"• 參與醫師：{total_doctors} 位")
        
        total_days = len(schedule)
        lines.append(f"• 總天數：{total_days} 天")
        
        # 計算平日和假日數
        weekday_count = sum(1 for date_str in schedule.keys() 
                          if datetime.strptime(date_str, "%Y-%m-%d").weekday() < 5)
        holiday_count = total_days - weekday_count
        
        lines.append(f"• 平日：{weekday_count} 天")
        lines.append(f"• 假日：{holiday_count} 天")
        lines.append("")
    
    # 加入醫師值班統計（前5名）
    if statistics and 'doctor_duties' in statistics:
        lines.append("👨‍⚕️ 醫師值班次數")
        
        # 排序醫師by總值班數
        sorted_doctors = sorted(
            statistics['doctor_duties'].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )[:5]  # 只顯示前5名
        
        for doc_name, duties in sorted_doctors:
            total = duties['total']
            weekday = duties.get('weekday', 0)
            holiday = duties.get('holiday', 0)
            lines.append(f"• {doc_name}: {total}次 (平{weekday}/假{holiday})")
        
        if len(statistics['doctor_duties']) > 5:
            lines.append(f"  ...還有{len(statistics['doctor_duties'])-5}位醫師")
        
        lines.append("")
    
    # 加入發佈資訊
    lines.append("=" * 30)
    lines.append("")
    lines.append(f"⏰ 發佈時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 加入下載連結
    if download_url:
        lines.append("")
        lines.append("📥 下載連結（30天有效）：")
        lines.append(download_url)
    
    lines.append("")
    lines.append("請各位醫師確認排班內容，如有問題請儘速反應。")
    
    return "\n".join(lines)