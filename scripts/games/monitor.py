# -*- coding: utf-8 -*-
# ======================================
# 添加任务
"""
name: 妖火监控
tag: 游戏,妖火
instance: single

"""
# 变量声明
"""
@env YH_COOKIE= 妖火Cookie
@env YH_PASSWORD= 你的妖火密码
@env YH_POLL_SEC=1       # 轮询间隔秒数，默认1秒
@env YH_TIMEOUT=10       # 请求超时时间
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
# 精简彩色日志
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
# 配置
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()
try:
    POLL_INTERVAL = int(os.getenv("YH_POLL_SEC", 1))  # 默认1秒
except ValueError:
    POLL_INTERVAL = 1
try:
    REQ_TIMEOUT = int(os.getenv("YH_TIMEOUT", 10))
except ValueError:
    REQ_TIMEOUT = 10

BASE_URL = 'https://yaohuo.me'
MONITOR_URL = f'{BASE_URL}/games/chuiniu/'
API_BET = f'{BASE_URL}/games/chuiniu/add.aspx'

# ======================================
# TCP连接优化
# ======================================
class TCPOptimizedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['socket_options'] = [
            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        ]
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('http://', TCPOptimizedAdapter(pool_connections=30, pool_maxsize=100, pool_block=False))
session.mount('https://', TCPOptimizedAdapter(pool_connections=30, pool_maxsize=100, pool_block=False))

REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
    'Cookie': COOKIE,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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

def parse_money(s):
    try:
        s = str(s).strip()
        if '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        else:
            return int(s)
    except:
        return 0

def request_with_retry(url, method="GET", data=None, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = session.get(url, timeout=REQ_TIMEOUT)
            else:
                resp = session.post(url, data=data, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            if "请先登录" in resp.text:
                ZLog.e("Cookie失效，请更新")
                return None
            return resp
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.5)
    return None

def verify_password():
    if not PASSWORD:
        ZLog.e("未设置YH_PASSWORD")
        return False
    request_with_retry(API_BET, "POST", {'needpassword': PASSWORD})
    resp = request_with_retry(API_BET, "GET")
    if resp and "请输入密码" in resp.text:
        ZLog.e("密码错误")
        return False
    return True

# ======================================
# 极速静默监控类
# ======================================
class YaohuoSpeedMonitor:
    def __init__(self):
        self.notified: Set[str] = set()  # 已开奖播报过的ID
        self.monitoring: Dict[str, Dict] = {}  # 正在监控的条目
    
    def get_all_ids(self) -> List[str]:
        resp = request_with_retry(MONITOR_URL)
        if not resp:
            return []
        try:
            soup = BeautifulSoup(resp.text, 'html.parser')
            ids = []
            for link in soup.find_all('a', href=re.compile(r'doit\.aspx\?id=\d+')):
                bid = re.search(r'id=(\d+)', link['href']).group(1)
                if bid not in ids:
                    ids.append(bid)
            return sorted(ids, key=lambda x: int(x), reverse=True)
        except:
            return []
    
    def get_detail(self, bid: str) -> Optional[Dict]:
        url = f'{BASE_URL}/games/chuiniu/book_view.aspx?type=0&touserid=24770&id={bid}'
        resp = request_with_retry(url)
        if not resp:
            return None
        try:
            soup = BeautifulSoup(resp.text, 'html.parser')
            res = {'id': bid, '发起者': '未知', '应战者': '未知', '赌注': '0', '答案': '未知', '结果': '未知', '状态': '进行中'}
            
            for item in soup.find_all('div', class_='detail-item'):
                lb = item.find('span', class_='detail-label')
                val = item.find('span', class_='detail-value')
                if lb and val:
                    t = lb.get_text().strip()
                    v = val.get_text().strip()
                    if '发起者' in t:
                        res['发起者'] = v
                    elif '应战者' in t:
                        res['应战者'] = v
                    elif '赌注金额' in t:
                        res['赌注'] = v
            
            text = soup.get_text()
            if m := re.search(r'正确答案\s*(答案[一二])', text):
                res['答案'] = m.group(1)
            if m := re.search(r'结果\s*(.+?)(?:\n|发起时间)', text):
                res['结果'] = m.group(1)
            
            if '结束时间' in text and res['结果'] != '未知':
                res['状态'] = '已结束'
            return res
        except:
            return None
    
    def run(self):
        print("\n" + "="*20)
        print("🚀 妖火吹牛 - 极速静默监控")
        print("="*20 + "\n")
        
        if not verify_password():
            return
        while True:
            # 1. 获取所有ID
            all_ids = self.get_all_ids()
            
            # 2. 检查新ID，加入监控（只输出一次加入提示）
            for bid in all_ids:
                if bid in self.notified:
                    continue
                if bid not in self.monitoring:
                    detail = self.get_detail(bid)
                    if detail and detail['状态'] == '进行中':
                        bet_amount = parse_money(detail['赌注'])
                        if bet_amount >= 20000:
                            self.monitoring[bid] = detail
                            challenger = detail['应战者'] if detail['应战者'] != '未知' else '待应战'
                           # ZLog.d(f"新 [{bid}] {detail['发起者']} | 应战者:{challenger} | 赌注{format_money(detail['赌注'])}")
            
            # 3. 检查监控中的条目，开奖才输出
            completed = []
            for bid in list(self.monitoring.keys()):
                detail = self.get_detail(bid)
                if detail and detail['状态'] == '已结束':
                    result_text = detail['结果']
                    challenger = detail['应战者'] if detail['应战者'] != '未知' else '未知'
                    
                    # 判断结果：应战者失败红色e，应战者胜利绿色s
                    if '应战者胜利' in result_text or '发起者失败' in result_text:
                        # 应战者胜利 - 绿色s
                        ZLog.s(f"赢 [{bid}] 应:{challenger} | 发:{detail['发起者']} | {detail['答案']} | {detail['结果']} | 注{format_money(detail['赌注'])}")
                    else:
                        # 应战者失败 - 红色e
                        ZLog.e(f"输 [{bid}] 应:{challenger} | 发:{detail['发起者']} | {detail['答案']} | {detail['结果']} | 注{format_money(detail['赌注'])}")
                    
                    completed.append(bid)
                    self.notified.add(bid)
            
            # 4. 移除已开奖的
            for bid in completed:
                del self.monitoring[bid]
            
            # 5. 等待下一轮（进行中完全不输出）
            time.sleep(POLL_INTERVAL)


def main():
    m = YaohuoSpeedMonitor()
    m.run()

if __name__ == "__main__":
    main()
