# -*- coding: utf-8 -*-
# ======================================
# 添加任务
"""
name: 妖火吹牛监控
tag: 游戏,妖火
instance: single

"""
# 变量声明
"""
@env YH_COOKIE= 妖火Cookie
@env YH_PASSWORD= 你的妖火密码
@env YH_POLL_SEC=10      # 轮询间隔秒数，默认10
@env YH_TIMEOUT=20       # 请求超时时间
"""
# 依赖声明
"""
@pip requests
@pip plyer
@pip beautifulsoup4
@pip Crypto
@pip pycryptodome
"""
# ======================================

import os
import requests
import socket
import time
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Set
from requests.adapters import HTTPAdapter

# ======================================
# 精简彩色日志系统
# ======================================
class ZLog:
    @staticmethod
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def log_color(msg, hex_color):
        timestamp = time.strftime('%H:%M:%S')
        r, g, b = ZLog.hex_to_rgb(hex_color)
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        print(f"[{timestamp}] {color}{msg}{reset}")

    @staticmethod
    def i(msg):
        ZLog.log_color(msg, "#888888")
    @staticmethod
    def s(msg):
        ZLog.log_color(msg, "#2ecc71")
    @staticmethod
    def w(msg):
        ZLog.log_color(msg, "#f39c12")
    @staticmethod
    def e(msg):
        ZLog.log_color(msg, "#e74c3c")
    @staticmethod
    def d(msg):
        ZLog.log_color(msg, "#3498db")

# ======================================
# 环境变量配置
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()
try:
    POLL_INTERVAL = int(os.getenv("YH_POLL_SEC", 10))
except ValueError:
    POLL_INTERVAL = 10
try:
    REQ_TIMEOUT = int(os.getenv("YH_TIMEOUT", 20))
except ValueError:
    REQ_TIMEOUT = 20

# 网站配置
BASE_URL = 'https://yaohuo.me'
MONITOR_URL = f'{BASE_URL}/games/chuiniu/'
API_BET = f'{BASE_URL}/games/chuiniu/add.aspx'

# ======================================
# TCP连接优化 - Session全局初始化
# ======================================
class TCPOptimizedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['socket_options'] = [
            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        ]
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('http://', TCPOptimizedAdapter(
    pool_connections=20,
    pool_maxsize=50,
    pool_block=False
))
session.mount('https://', TCPOptimizedAdapter(
    pool_connections=20,
    pool_maxsize=50,
    pool_block=False
))

# 全局请求头
REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': COOKIE,
    'Origin': BASE_URL,
    'Referer': API_BET,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
}
session.headers.update(REQUEST_HEADERS)

# ======================================
# 工具函数
# ======================================
def format_money(num):
    try:
        n = int(num)
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        else:
            return f"{n}"
    except:
        return str(num)

# ======================================
# 带重试请求
# ======================================
def request_with_retry(url, method="GET", data=None, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = session.get(url, timeout=REQ_TIMEOUT)
            else:
                resp = session.post(url, data=data, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            
            if "请先登录" in resp.text or "登录网站" in resp.text:
                ZLog.e("登录已失效，请更新Cookie")
                return None
            
            return resp
        except Exception as e:
            ZLog.w(f"请求重试 {attempt}/{max_retries}: {str(e)[:30]}")
            if attempt < max_retries:
                time.sleep(2)
    ZLog.e("请求失败，已达最大重试次数")
    return None

# ======================================
# 密码验证
# ======================================
def verify_password():
    if not PASSWORD:
        ZLog.e("未设置YH_PASSWORD环境变量")
        return False
    post_data = {'needpassword': PASSWORD}
    resp = request_with_retry(API_BET, "POST", post_data)
    if not resp:
        return False
    resp = request_with_retry(API_BET, "GET")
    if not resp:
        return False
    if "needpassword" in resp.text and "请输入密码" in resp.text:
        ZLog.e("密码错误，请检查YH_PASSWORD")
        return False
    ZLog.s("密码验证通过")
    return True

# ======================================
# 永久监控爬虫类
# ======================================
class YaohuoPermanentMonitor:
    """永久运行全量监控类"""
    
    def __init__(self):
        self.monitored_ids: Set[str] = set()  # 已完成的ID
        self.active_monitors: Dict[str, Dict] = {}  # 正在监控的条目
    
    def get_all_bull_ids(self) -> List[str]:
        """获取所有吹牛ID"""
        response = request_with_retry(MONITOR_URL)
        if not response:
            return []
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            id_pattern = re.compile(r'doit\.aspx\?id=(\d+)')
            all_ids = []
            
            for link in soup.find_all('a', href=True):
                match = id_pattern.search(link['href'])
                if match:
                    bull_id = match.group(1)
                    if bull_id not in all_ids:
                        all_ids.append(bull_id)
            
            all_ids.sort(key=lambda x: int(x), reverse=True)
            return all_ids
            
        except Exception as e:
            ZLog.e(f"解析列表失败: {str(e)[:30]}")
            return []
    
    def get_bull_detail(self, bull_id: str) -> Optional[Dict]:
        """获取吹牛详情"""
        detail_url = f'{BASE_URL}/games/chuiniu/book_view.aspx?type=0&touserid=24770&id={bull_id}'
        
        response = request_with_retry(detail_url)
        if not response:
            return None
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {
                'id': bull_id,
                '发起者': '未知',
                '赌注金额': '未知',
                '正确答案': '未知',
                '应战者': '未知',
                '结果': '未知',
                '状态': '进行中'
            }
            
            # 解析detail-item结构
            for item in soup.find_all('div', class_='detail-item'):
                label = item.find('span', class_='detail-label')
                value = item.find('span', class_='detail-value')
                if label and value:
                    label_text = label.get_text().strip()
                    value_text = value.get_text().strip()
                    if '发起者' in label_text:
                        result['发起者'] = value_text
                    elif '赌注金额' in label_text:
                        result['赌注金额'] = value_text
            
            # 解析答案和结果
            page_text = soup.get_text()
            
            ans_match = re.search(r'正确答案\s*(答案[一二])', page_text)
            if ans_match:
                result['正确答案'] = ans_match.group(1).strip()
            
            challenger_match = re.search(r'应战者\s*(.+?)\s*选择', page_text)
            if challenger_match:
                result['应战者'] = challenger_match.group(1).strip()
            
            result_match = re.search(r'结果\s*(.+?)(?:\n|发起时间|$)', page_text)
            if result_match:
                result['结果'] = result_match.group(1).strip()
            
            if '结束时间' in page_text and result['结果'] != '未知':
                result['状态'] = '已结束'
            
            return result
            
        except Exception as e:
            return None
    
    def run(self):
        """永久运行主循环"""
        print("\n" + "="*70)
        print("🐮 妖火吹牛永久监控工具")
        print("="*70 + "\n")
        
        if not verify_password():
            ZLog.e("启动失败")
            return
        
        ZLog.d("-"*60)
        
        try:
            while True:  # 永久循环，永不退出
                # 1. 获取所有吹牛ID
                all_ids = self.get_all_bull_ids()
                
                # 2. 处理新发现的吹牛
                new_ids = [bid for bid in all_ids if bid not in self.monitored_ids and bid not in self.active_monitors]
                for bull_id in new_ids:
                    detail = self.get_bull_detail(bull_id)
                    if detail:
                        if detail['状态'] == "进行中":
                            self.active_monitors[bull_id] = detail
                            ZLog.d(f"新 [{bull_id}] {detail['发起者']} 赌注{format_money(detail['赌注金额'])} 已加入监控")
                        else:
                            self.monitored_ids.add(bull_id)
                
                # 3. 检查所有进行中的吹牛是否开奖
                completed_ids = []
                for bull_id in list(self.active_monitors.keys()):
                    detail = self.get_bull_detail(bull_id)
                    if detail and detail['状态'] == "已结束":
                        # 开奖了，输出结果
                        ZLog.s(f"✅ 开奖 [{bull_id}] {detail['发起者']} 赌注{format_money(detail['赌注金额'])} | {detail['正确答案']} | {detail['结果']}")
                        completed_ids.append(bull_id)
                
                # 4. 移除已开奖的条目
                for bull_id in completed_ids:
                    self.monitored_ids.add(bull_id)
                    del self.active_monitors[bull_id]
                
                # 6. 等待下一轮
                time.sleep(100)
                
        except KeyboardInterrupt:
            ZLog.w("\n用户手动停止程序")
        except Exception as e:
            ZLog.e(f"运行异常: {str(e)[:50]}，10秒后自动恢复...")
            time.sleep(10)
            self.run()  # 异常自动重启
        finally:
            session.close()


def main():
    monitor = YaohuoPermanentMonitor()
    monitor.run()  # 永久运行，不退出

if __name__ == "__main__":
    main()
