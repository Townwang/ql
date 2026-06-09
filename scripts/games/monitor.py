# -*- coding: utf-8 -*-
# ======================================
# 添加任务
"""
name: 妖火监控
tag: 游戏,妖火
instance: single

"""
# 变量声明 （可设置在docker环境变量）
"""
@env YH_COOKIE= 妖火Cookie
@env YH_PASSWORD= 你的妖火密码
@env YH_POLL_SEC=2       # 轮询间隔秒数，建议2~3秒
@env YH_TIMEOUT=18       # 请求超时时间，增大到18秒
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
import traceback
import random
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Set
from requests.adapters import HTTPAdapter

# ======================================
# 精简彩色日志 - 使用脚本原定义的hex颜色
# ======================================
class ZLog:
    @staticmethod
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def color_part(text, hex_color):
        """返回带颜色的文本片段"""
        r, g, b = ZLog.hex_to_rgb(hex_color)
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        return f"{color}{text}{reset}"

    # 原定义的颜色
    @staticmethod
    def s(msg):
        r, g, b = ZLog.hex_to_rgb("#2ecc71")
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        print(f"{color}{msg}{reset}")
    @staticmethod
    def w(msg):
        r, g, b = ZLog.hex_to_rgb("#f39c12")
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        print(f"{color}{msg}{reset}")
    @staticmethod
    def e(msg):
        r, g, b = ZLog.hex_to_rgb("#e74c3c")
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        print(f"{color}{msg}{reset}")
    @staticmethod
    def d(msg):
        r, g, b = ZLog.hex_to_rgb("#3498db")
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        print(f"{color}{msg}{reset}")

# 颜色定义（使用脚本原定义的hex）
COLORS = {
    'blue': '#3498db',      # 蓝色 - 发起者、应战者、金额
    'green': '#2ecc71',     # 绿色 - 赢字
    'red': '#e74c3c',       # 红色 - 输字
    'black': '#000000',     # 黑色 - 结果
    'white': '#ffffff',     # 白色 - 分隔符
    'grey': '#efefef'       # 灰色
}

# ======================================
# 配置 (增大超时、默认轮询间隔放缓)
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()
try:
    POLL_INTERVAL = int(os.getenv("YH_POLL_SEC", 2))  # 默认改为2秒
except ValueError:
    POLL_INTERVAL = 2
try:
    REQ_TIMEOUT = int(os.getenv("YH_TIMEOUT", 18))     # 超时改为18秒
except ValueError:
    REQ_TIMEOUT = 18

BASE_URL = 'https://yaohuo.me'
MONITOR_URL = f'{BASE_URL}/games/chuiniu/'
API_BET = f'{BASE_URL}/games/chuiniu/add.aspx'

# ======================================
# 连接优化：禁用连接池、每次短连接，适配站点
# ======================================
session = requests.Session()
# 清空连接池，不复用连接，解决长连接超时问题
adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
session.mount('http://', adapter)
session.mount('https://', adapter)

REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'close',  # 强制短连接
    'Cookie': COOKIE,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
        except requests.exceptions.ReadTimeout:
            # 单独处理读取超时，精简日志，不打印堆栈
            ZLog.w(f"请求超时: {url} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(random.uniform(0.3, 0.8))
            continue
        except Exception as e:
            err_info = f"请求异常 地址:{url} 尝试次数:{attempt}/{max_retries} 错误:{str(e)}"
            ZLog.e(err_info)
            if attempt < max_retries:
                time.sleep(0.5)
    ZLog.e(f"请求最终失败: {url}")
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
# 监控类：增加超时ID屏蔽、串行限流、防高频请求
# ======================================
class YaohuoSpeedMonitor:
    def __init__(self):
        self.notified: Set[str] = set()          # 已开奖播报过的ID
        self.monitoring: Dict[str, Dict] = {}     # 正在监控的条目
        self.timeout_ids: Dict[str, float] = {}   # 临时超时ID + 下次可请求时间

    def get_all_ids(self) -> List[str]:
        try:
            resp = request_with_retry(MONITOR_URL)
            if not resp:
                return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            ids = []
            for link in soup.find_all('a', href=re.compile(r'doit\.aspx\?id=\d+')):
                bid = re.search(r'id=(\d+)', link['href']).group(1)
                if bid not in ids:
                    ids.append(bid)
            return sorted(ids, key=lambda x: int(x), reverse=True)
        except Exception as e:
            ZLog.e("获取列表ID解析异常")
            return []

    def get_detail(self, bid: str) -> Optional[Dict]:
        # 临时屏蔽短时间内连续超时的ID
        now = time.time()
        if bid in self.timeout_ids and now < self.timeout_ids[bid]:
            return None

        url = f'{BASE_URL}/games/chuiniu/book_view.aspx?type=0&touserid=24770&id={bid}'
        resp = request_with_retry(url)
        if not resp:
            # 标记该ID 3秒内不再请求
            self.timeout_ids[bid] = now + 3.0
            return None
        # 清除超时标记
        if bid in self.timeout_ids:
            del self.timeout_ids[bid]

        try:
            soup = BeautifulSoup(resp.text, 'html.parser')
            res = {'id': bid, '发起者': '未知', '应战者': '未知', '赌注': '0', '答案': '未知', '结果': '未知', '状态': '进行中', '选择': '未知'}

            for item in soup.find_all('div', class_='detail-item'):
                lb = item.find('span', class_='detail-label')
                val = item.find('span', class_='detail-value')
                if lb and val:
                    t = lb.get_text().strip()
                    v = val.get_text().strip()
                    if '发起者' in t:
                        res['发起者'] = v
                    elif '赌注金额' in t:
                        res['赌注'] = v

            text = soup.get_text()
            if m := re.search(r'应战者\s*(\S+?)\s*选择：(答案[一二])', text):
                res['应战者'] = m.group(1).strip()
                res['选择'] = m.group(2).strip()
            elif m := re.search(r'应战者\s*(\S+?)(?:\s|选择|$)', text):
                res['应战者'] = m.group(1).strip()

            if m := re.search(r'正确答案\s*(答案[一二])', text):
                res['答案'] = m.group(1)

            if m := re.search(r'结果\s*(应战者胜出|应战者失败|发起者胜出|发起者失败)', text):
                res['结果'] = m.group(1)

            if '结束时间' in text and res['结果'] != '未知':
                res['状态'] = '已结束'

            return res
        except Exception as e:
            ZLog.w(f"解析[{bid}]数据异常")
            return None

    def print_result(self, detail, is_win):
        win_lose_color = COLORS['green'] if is_win else COLORS['red']
        log_line = (
            f"[{detail['id']}] \n"
            f"发: {ZLog.color_part(detail['发起者'], COLORS['blue'])} | "
            f"注: {ZLog.color_part(format_money(detail['赌注']), COLORS['blue'])} | "
            f"{detail['答案']} \n"
            f"应: {ZLog.color_part(detail['应战者'], COLORS['blue'])} | "
            f"选: {ZLog.color_part(detail['选择'], COLORS['grey'])} \n"
            f"{ZLog.color_part(detail['结果'], win_lose_color)}"
        )
        print(log_line)

    def run(self):
        print("\n" + "="*30)
        print("妖火吹牛 - 极速静默监控（已优化超时）")
        print("="*30 + "\n")

        if not verify_password():
            return
        while True:
            try:
                # 清理过期的超时ID
                now = time.time()
                self.timeout_ids = {k: v for k, v in self.timeout_ids.items() if v > now}

                all_ids = self.get_all_ids()

                # 逐个拉取详情，增加随机休眠，限流防并发
                for bid in all_ids:
                    if bid in self.notified:
                        continue
                    if bid not in self.monitoring:
                        # 每个详情请求之间小幅休眠
                        time.sleep(random.uniform(0.2, 0.5))
                        detail = self.get_detail(bid)
                        if not detail:
                            continue
                        bet_amount = parse_money(detail['赌注'])
                        if bet_amount >= 20000:
                            self.monitoring[bid] = detail

                # 检查监控中条目
                completed = []
                for bid in list(self.monitoring.keys()):
                    time.sleep(random.uniform(0.1, 0.3))
                    detail = self.get_detail(bid)
                    if not detail:
                        continue
                    if detail['状态'] == '已结束':
                        result_text = detail['结果']
                        is_win = '应战者胜出' in result_text or '发起者失败' in result_text
                        self.print_result(detail, is_win)
                        completed.append(bid)
                        self.notified.add(bid)

                # 移除已完成任务
                for bid in completed:
                    print("="*30 + "\n")
                    del self.monitoring[bid]

                time.sleep(POLL_INTERVAL)
            except Exception as e:
                ZLog.e(f"主循环异常: {str(e)}")
                time.sleep(POLL_INTERVAL)


def main():
    m = YaohuoSpeedMonitor()
    m.run()

if __name__ == "__main__":
    main()
