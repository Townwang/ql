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
@env YH_POLL_SEC=2       # 基础轮询间隔
@env YH_IDLE_SLEEP=5     # 空闲时加长休眠
@env YH_TIMEOUT=18       # 请求超时时间
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
import time
import re
import random
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
    def color_part(text, hex_color):
        r, g, b = ZLog.hex_to_rgb(hex_color)
        color = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        return f"{color}{text}{reset}"

    @staticmethod
    def s(msg):
        r, g, b = ZLog.hex_to_rgb("#2ecc71")
        print(f"\033[38;2;{r};{g};{b}m{msg}\033[0m")
    @staticmethod
    def w(msg):
        r, g, b = ZLog.hex_to_rgb("#f39c12")
        print(f"\033[38;2;{r};{g};{b}m{msg}\033[0m")
    @staticmethod
    def e(msg):
        r, g, b = ZLog.hex_to_rgb("#e74c3c")
        print(f"\033[38;2;{r};{g};{b}m{msg}\033[0m")
    @staticmethod
    def d(msg):
        r, g, b = ZLog.hex_to_rgb("#3498db")
        print(f"\033[38;2;{r};{g};{b}m{msg}\033[0m")

COLORS = {
    'blue': '#3498db',
    'green': '#2ecc71',
    'red': '#e74c3c',
    'grey': '#efefef'
}

# ======================================
# 全局配置
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()

try:
    BASE_POLL = int(os.getenv("YH_POLL_SEC", 2))
except ValueError:
    BASE_POLL = 2

try:
    IDLE_SLEEP = int(os.getenv("YH_IDLE_SLEEP", 5))
except ValueError:
    IDLE_SLEEP = 5

try:
    REQ_TIMEOUT = int(os.getenv("YH_TIMEOUT", 18))
except ValueError:
    REQ_TIMEOUT = 18

# 投注金额阈值
BET_THRESHOLD = 5000
# 异常ID屏蔽时长(秒)
BAN_SEC = 8
# 详情缓存有效期(秒)
DETAIL_CACHE_TTL = 3
# 随机抖动范围 ±0.3 秒
JITTER_RANGE = 0.3

BASE_URL = 'https://yaohuo.me'
MONITOR_URL = f'{BASE_URL}/games/chuiniu/'
API_BET = f'{BASE_URL}/games/chuiniu/add.aspx'

# ======================================
# 请求会话优化
# ======================================
session = requests.Session()
adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
session.mount('http://', adapter)
session.mount('https://', adapter)

REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'close',
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
        return f"{n / 10000:.1f}万" if n >= 10000 else f"{n}"
    except:
        return str(num)

def request_with_retry(url, method="GET", data=None, max_retries=2):
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
            ZLog.w(f"请求超时: {url} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(random.uniform(0.2, 0.4))
            continue
        except Exception as e:
            ZLog.e(f"请求异常 {url}：{str(e)}")
            if attempt < max_retries:
                time.sleep(random.uniform(0.2, 0.4))
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
# 监控主类（带随机抖动 + 全量请求优化）
# ======================================
class YaohuoMonitor:
    def __init__(self):
        self.notified: Set[str] = set()               # 已结束并播报，永久不再处理
        self.monitoring: Dict[str, Dict] = {}         # 正在监控的对局
        self.ban_ids: Dict[str, float] = {}          # 异常/超时ID 屏蔽列表
        self.cache: Dict[str, (Dict, float)] = {}     # 详情缓存 {id: (数据, 过期时间)}

    def clean_expire(self):
        """统一清理所有过期数据"""
        now = time.time()
        self.ban_ids = {k: v for k, v in self.ban_ids.items() if v > now}
        del_keys = [k for k, (_, t) in self.cache.items() if t < now]
        for k in del_keys:
            self.cache.pop(k, None)

    def get_valid_ids(self) -> List[str]:
        """大厅页提取ID + 金额前置过滤"""
        resp = request_with_retry(MONITOR_URL)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        target_ids = []
        for link in soup.find_all('a', href=re.compile(r'doit\.aspx\?id=\d+')):
            bid_match = re.search(r'id=(\d+)', link['href'])
            if not bid_match:
                continue
            bid = bid_match.group(1)
            if bid in self.notified or bid in self.ban_ids:
                continue

            title = link.get("title", "")
            money_match = re.search(r'（(\d+)妖晶）', title)
            if not money_match:
                continue
            money_val = int(money_match.group(1))
            if money_val >= BET_THRESHOLD:
                target_ids.append(bid)
        return sorted(list(set(target_ids)), key=lambda x: int(x), reverse=True)

    def get_detail(self, bid: str) -> Optional[Dict]:
        """优先读缓存，缓存失效再请求"""
        now = time.time()
        if bid in self.ban_ids and now < self.ban_ids[bid]:
            return None
        if bid in self.cache:
            data, expire = self.cache[bid]
            if now < expire:
                return data

        url = f'{BASE_URL}/games/chuiniu/book_view.aspx?type=0&id={bid}'
        resp = request_with_retry(url)
        if not resp:
            self.ban_ids[bid] = now + BAN_SEC
            self.cache.pop(bid, None)
            return None

        res = {
            'id': bid, '发起者': '未知', '应战者': '未知',
            '赌注': '0', '答案': '未知', '结果': '未知',
            '状态': '进行中', '选择': '未知'
        }
        soup = BeautifulSoup(resp.text, 'html.parser')
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
        m = re.search(r'应战者\s*(\S+?)\s*选择：(答案[一二])', text)
        if m:
            res['应战者'] = m.group(1).strip()
            res['选择'] = m.group(2).strip()
        else:
            m = re.search(r'应战者\s*(\S+?)(?:\s|选择|$)', text)
            if m:
                res['应战者'] = m.group(1).strip()

        m = re.search(r'正确答案\s*(答案[一二])', text)
        if m:
            res['答案'] = m.group(1)
        m = re.search(r'结果\s*(应战者胜出|应战者失败|发起者胜出|发起者失败)', text)
        if m:
            res['结果'] = m.group(1)

        if '结束时间' in text and res['结果'] != '未知':
            res['状态'] = '已结束'

        self.cache[bid] = (res, now + DETAIL_CACHE_TTL)
        self.ban_ids.pop(bid, None)
        return res

    def print_result(self, detail, is_win):
        color = COLORS['green'] if is_win else COLORS['red']
        line = (
            f"[{detail['id']}]\n"
            f"发: {ZLog.color_part(detail['发起者'], COLORS['blue'])} | "
            f"注: {ZLog.color_part(format_money(detail['赌注']), COLORS['blue'])} | {detail['答案']}\n"
            f"应: {ZLog.color_part(detail['应战者'], COLORS['blue'])} | "
            f"选: {ZLog.color_part(detail['选择'], COLORS['grey'])}\n"
            f"{ZLog.color_part(detail['结果'], color)}"
        )
        print(line)
        print("=" * 30 + "\n")

    def run(self):
        print("\n" + "="*30)
        print("妖火监控 - 带随机抖动防风控版")
        print("="*30 + "\n")

        if not verify_password():
            return

        while True:
            try:
                self.clean_expire()
                all_ids = self.get_valid_ids()
                has_active = False

                for bid in all_ids:
                    # ID 之间小幅随机间隔，打散请求节奏
                    time.sleep(random.uniform(0.1, 0.3))
                    detail = self.get_detail(bid)
                    if not detail:
                        continue

                    if detail['状态'] == '已结束':
                        is_win = '应战者胜出' in detail['结果'] or '发起者失败' in detail['结果']
                        self.print_result(detail, is_win)
                        self.notified.add(bid)
                        self.monitoring.pop(bid, None)
                        self.cache.pop(bid, None)
                    else:
                        self.monitoring[bid] = detail
                        has_active = True

                # 主轮询间隔 + ±0.3s 随机抖动
                base_sleep = BASE_POLL if has_active else IDLE_SLEEP
                jitter = random.uniform(-JITTER_RANGE, JITTER_RANGE)
                actual_sleep = max(0.1, base_sleep + jitter)  # 保证最小休眠0.1秒，不出现负数
                time.sleep(actual_sleep)

            except Exception as e:
                ZLog.e(f"主循环异常: {str(e)}")
                # 异常时也加抖动，保持随机性
                err_jitter = random.uniform(-JITTER_RANGE, JITTER_RANGE)
                time.sleep(max(0.1, BASE_POLL + err_jitter))

def main():
    m = YaohuoMonitor()
    m.run()

if __name__ == "__main__":
    main()
