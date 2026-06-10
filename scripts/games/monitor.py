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
@env YH_TIMEOUT=25       # 请求超时时间
@env HTTP_PROXY= 可选代理地址
@env HTTPS_PROXY= 可选代理地址
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
from urllib3.util.retry import Retry

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
    'grey': '#cecece'
}

# ======================================
# 全局配置
# ======================================
# 默认Cookie（已内置）
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
    REQ_TIMEOUT = int(os.getenv("YH_TIMEOUT", 25))
except ValueError:
    REQ_TIMEOUT = 25

BET_THRESHOLD = 20000
BAN_SEC = 8
DETAIL_CACHE_TTL = 3
JITTER_RANGE = 0.3

BASE_URL = 'https://yaohuo.me'
MONITOR_URL = f'{BASE_URL}/games/chuiniu/'
API_BET = f'{BASE_URL}/games/chuiniu/add.aspx'

# ======================================
# 请求会话（修复连接超时）
# ======================================
session = requests.Session()

retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
)
adapter = HTTPAdapter(
    pool_connections=5,
    pool_maxsize=10,
    max_retries=retry_strategy,
    pool_block=False
)
session.mount('http://', adapter)
session.mount('https://', adapter)

REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cookie': COOKIE,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Referer': BASE_URL,
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Upgrade-Insecure-Requests': '1'
}
session.headers.update(REQUEST_HEADERS)

# 自动支持代理
proxy_http = os.getenv('HTTP_PROXY', os.getenv('http_proxy', ''))
proxy_https = os.getenv('HTTPS_PROXY', os.getenv('https_proxy', ''))
if proxy_http or proxy_https:
    session.proxies = {'http': proxy_http, 'https': proxy_https}

# ======================================
# 工具函数
# ======================================
def format_money(num):
    try:
        n = int(num)
        return f"{n / 10000:.1f}万" if n >= 10000 else f"{n}"
    except:
        return str(num)

def request_with_retry(url, method="GET", data=None, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = session.get(url, timeout=REQ_TIMEOUT, allow_redirects=True)
            else:
                resp = session.post(url, data=data, timeout=REQ_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            if "请先登录" in resp.text:
                ZLog.e("Cookie失效，请更新")
                return None
            return resp
        except requests.exceptions.ReadTimeout:
            ZLog.w(f"请求超时: {url} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(random.uniform(0.5, 1.5) * attempt)
            continue
        except requests.exceptions.ConnectTimeout:
            ZLog.w(f"连接超时: {url} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(random.uniform(1, 2) * attempt)
            continue
        except requests.exceptions.ConnectionError as e:
            ZLog.w(f"连接错误: {url} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(random.uniform(1, 2) * attempt)
            continue
        except Exception as e:
            ZLog.e(f"请求异常 {url}：{str(e)[:80]}")
            if attempt < max_retries:
                time.sleep(random.uniform(0.5, 1))
    ZLog.e(f"请求最终失败: {url}")
    return None

def verify_password():
    if not PASSWORD:
        ZLog.w("未设置YH_PASSWORD，将跳过投注功能")
        return True
    request_with_retry(API_BET, "POST", {'needpassword': PASSWORD})
    resp = request_with_retry(API_BET, "GET")
    if resp and "请输入密码" in resp.text:
        ZLog.e("密码错误")
        return False
    return True

# ======================================
# 监控主类
# ======================================
class YaohuoMonitor:
    def __init__(self):
        self.notified: Set[str] = set()
        self.monitoring: Dict[str, Dict] = {}
        self.ban_ids: Dict[str, float] = {}
        self.cache: Dict[str, tuple] = {}
        self.request_success = 0
        self.request_fail = 0

    def clean_expire(self):
        now = time.time()
        self.ban_ids = {k: v for k, v in self.ban_ids.items() if v > now}
        del_keys = [k for k, (_, t) in self.cache.items() if t < now]
        for k in del_keys:
            self.cache.pop(k, None)

    def get_valid_ids(self) -> List[str]:
        resp = request_with_retry(MONITOR_URL)
        if not resp:
            self.request_fail += 1
            return []
        self.request_success += 1
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        target_ids = []
        
        for link in soup.find_all('a', href=re.compile(r'doit\.aspx\?id=\d+')):
            bid_match = re.search(r'id=(\d+)', link['href'])
            if not bid_match:
                continue
            bid = bid_match.group(1)
            
            if bid in self.notified or bid in self.ban_ids:
                continue

            link_text = link.get_text().strip()
            money_match = re.search(r'[（(](\d+)妖晶[）)]', link_text)
            
            if not money_match:
                continue
                
            money_val = int(money_match.group(1))
            if money_val >= BET_THRESHOLD:
                target_ids.append((bid, money_val))

        # 按金额降序，优先处理大额
        target_ids.sort(key=lambda x: x[1], reverse=True)
        return [bid for bid, _ in target_ids]

    def get_detail(self, bid: str) -> Optional[Dict]:
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
            self.request_fail += 1
            self.ban_ids[bid] = now + BAN_SEC
            self.cache.pop(bid, None)
            return None
        self.request_success += 1

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
            f"应: {ZLog.color_part(detail['应战者'], COLORS['grey'])} | "
            f"选: {ZLog.color_part(detail['选择'], COLORS['grey'])}\n"
            f"{ZLog.color_part(detail['结果'], color)}"
        )
        print(line)
        print("=" * 30 + "\n")

    def run(self):
        print("\n" + "="*30)
        print("妖火监控 - 最终修复版")
        print(f"请求超时: {REQ_TIMEOUT}秒 | 重试: 3次")
        print(f"监控阈值: {BET_THRESHOLD}妖晶")
        print("="*30 + "\n")

        ZLog.d("正在测试网站连通性...")
        test_resp = request_with_retry(BASE_URL)
        if test_resp:
            ZLog.s(f"连接成功! 状态码: {test_resp.status_code}")
        else:
            ZLog.e("连接测试失败!")
            return

        ZLog.d("测试提取对局ID...")
        test_ids = self.get_valid_ids()
        ZLog.s(f"成功提取到 {len(test_ids)} 个符合条件的对局ID")

        if not verify_password():
            return

        ZLog.d("开始监控...\n")
        loop_count = 0
        
        while True:
            try:
                loop_count += 1
                now_time = time.strftime('%Y-%m-%d %H:%M:%S')
                if time.strftime('%H:%M:%S') == "00:00:00":
                    print(f"{now_time}")
                self.clean_expire()
                all_ids = self.get_valid_ids()
                has_active = False
                for bid in all_ids:
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

                base_sleep = BASE_POLL if has_active else IDLE_SLEEP
                jitter = random.uniform(-JITTER_RANGE, JITTER_RANGE)
                actual_sleep = max(0.1, base_sleep + jitter)
                time.sleep(actual_sleep)

            except KeyboardInterrupt:
                ZLog.w("用户中断，退出程序")
                break
            except Exception as e:
                ZLog.e(f"主循环异常: {str(e)[:100]}")
                err_jitter = random.uniform(-JITTER_RANGE, JITTER_RANGE)
                time.sleep(max(1, BASE_POLL + err_jitter))

def main():
    m = YaohuoMonitor()
    m.run()

if __name__ == "__main__":
    main()
