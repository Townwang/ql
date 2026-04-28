# -*- coding: utf-8 -*-
# ======================================
# 添加任务
"""
name: 妖火吹牛
tag: 游戏,妖火
instance: single

"""
# 变量声明
"""
@env YH_COOKIE= 妖火Cookie
@env YH_PASSWORD= 你的妖火密码
@env YH_TEST= 测试
"""
# 依赖声明
"""
@pip requests
@pip plyer
@pip bs4
@pip beautifulsoup4
@pip Crypto
@pip pycryptodome
"""
# ======================================

import secrets
import requests
import time
import json
import os
import re
import atexit
import random
from bs4 import BeautifulSoup

# ======================================
# 青龙环境变量
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()

CONFIG = {
    "base_bet": 5000,           # 基础投注
    "max_bet": 5000000,        # 单次最大投注
    "max_network_errors": 10,  # 网络错误超限次数
    "request_retries": 5,      # 单接口请求重试次数
    "request_timeout": 20,     # 请求超时时间
}

# 路径常量
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(SCRIPT_PATH, "yaohuo_bet.lock")
STATE_FILE = os.path.join(SCRIPT_PATH, "yaohuo_bet_state.json")

# 请求基础域名
BASE_HOST = "https://yaohuo.me"
API_BALANCE = f"{BASE_HOST}/games/chuiniu/index.aspx"
API_RECORDS = f"{BASE_HOST}/games/chuiniu/book_list.aspx?type=0"
API_BET = f"{BASE_HOST}/games/chuiniu/add.aspx"

# ======================================
# 全局状态
# ======================================
class GameState:
    def __init__(self):
        self.is_running = True
        self.network_error_count = 0

        self.base_bet = CONFIG["base_bet"]
        self.total_lose_sum = 0
        self.target_bet = self.base_bet
        self.real_bet = self.base_bet
        self.consecutive_losses = 0

        self.win_count = 0
        self.loss_count = 0
        self.total_profit = 0
        self.total_bet_amount = 0
        self.total_runs = 0

        self.last_bet_id = None
        self.last_ongoing_ids = None
        self.last_result = None
        self.current_balance = 0
        self.user_id = ""

        self.last_choice = None
        self.save_date = self.get_today()
        
        self.current_challenger = ""

    @staticmethod
    def get_today():
        return time.strftime("%Y-%m-%d")

state = GameState()

# ======================================
# 请求头
# ======================================
REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'max-age=0',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': COOKIE,
    'Origin': BASE_HOST,
    'Referer': API_BET,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
}

# ======================================
# 金额格式化
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
# 日志
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
# 配置校验
# ======================================
def check_config_valid():
    required_numeric = [
        "base_bet", "max_bet",
        "max_network_errors", "request_retries", "request_timeout",
    ]
    for key in required_numeric:
        val = CONFIG.get(key)
        if not isinstance(val, (int, float)) or val < 0:
            ZLog.e(f"配置项 {key} 不合法")
            return False
    if not PASSWORD:
        ZLog.w("警告：未设置 YH_PASSWORD 环境变量，投注可能需要密码")
    return True

# ======================================
# 带重试请求 + 每错一次递增1分钟延迟
# ======================================
def request_with_retry(url, method="GET", data=None):
    retry_max = CONFIG["request_retries"]
    timeout = CONFIG["request_timeout"]
    
    for attempt in range(1, retry_max + 1):
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
            else:
                resp = requests.post(url, headers=REQUEST_HEADERS, data=data, timeout=timeout)
            resp.raise_for_status()
            
            if "请先登录" in resp.text or "登录网站" in resp.text:
                ZLog.e("登录已失效")
                state.is_running = False
                return None
            
            # 请求成功 重置错误计数
            state.network_error_count = 0
            return resp

        except Exception as e:
            state.network_error_count += 1
            # 每出错一次 延迟 = 错误次数 * 60秒
            delay_sec = state.network_error_count * 60
            ZLog.w(f"第{attempt}次请求失败 | 累计网络错误{state.network_error_count}次 → 延迟{delay_sec//60}分钟后重试")
            
            # 错误超限 直接停止
            if state.network_error_count >= CONFIG["max_network_errors"]:
                ZLog.e("网络错误次数超限，脚本停止运行")
                state.is_running = False
                return None
            
            time.sleep(delay_sec)

# ======================================
# 题库
# ======================================
def get_question_pool():
    return [
        ["🐮 我的公众号有哪些？", "开源人", "软件学"],
        ["🐶 我的公众号有哪些？", "软件学", "软件人"],
        ["🐯 我的公众号有哪些？", "软件学", "开源人"],
        ["🐼 我的公众号有哪些？", "开源人", "软件人"],
        ["🐹 我的公众号有哪些？", "软件人", "开源人"],
        ["🐓 我的公众号有哪些？", "软件人", "软件学"],
        ["🐷 我的个人站有哪些？", "https://hunter.wang", "https://townwang.com"],
        ["🐸 我的个人站有哪些？", "https://hunter.wang", "https://townwang.cn"],
        ["🐢 我的个人站有哪些？", "https://townwang.com", "https://hunter.wang"],
        ["🦆 我的个人站有哪些？", "https://townwang.com", "https://townwang.cn"],
        ["🦉 我的个人站有哪些？", "https://townwang.cn", "https://townwang.com"],
        ["️️🕷️️ 我的个人站有哪些？", "https://townwang.cn", "https://hunter.wang"],
        ["🦕 公众号: 『开源人』、『软件人』、『软件学』", "🌏", "🌏"],
        ["🦜 个人站: [hunter.wang],[townwang.com],[townwang.cn]", "🌍", "🌍"]
    ]

# ======================================
# 安全随机
# ======================================
def secure_coin_flip():
    return 1 if secrets.randbelow(2) == 0 else 2

# ======================================
# 用户ID & 余额
# ======================================
def init_user_id():
    if not COOKIE:
        ZLog.e("Cookie 为空")
        return False
    user_match = re.search(r'userid=(\d+)', COOKIE)
    if user_match:
        state.user_id = user_match.group(1)
        return True
    user_match = re.search(r'GET(\d+)=', COOKIE)
    if user_match:
        state.user_id = user_match.group(1)
        return True
    resp = request_with_retry(API_RECORDS)
    if not resp:
        return False
    user_match = re.search(r'touserid=(\d+)', resp.url)
    if user_match:
        state.user_id = user_match.group(1)
        return True
    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.find_all("a", href=re.compile(r"touserid=")):
        uid_match = re.search(r'touserid=(\d+)', link.get("href", ""))
        if uid_match:
            state.user_id = uid_match.group(1)
            return True
    ZLog.e("无法获取用户ID")
    return False

def refresh_balance():
    resp = request_with_retry(API_BALANCE)
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    stats_items = soup.find_all("div", class_="stats-item")
    for item in stats_items:
        label = item.find("span", class_="stats-label")
        if label and "我的妖晶余额" in label.text:
            value_span = item.find("span", class_="stats-value")
            if value_span:
                try:
                    state.current_balance = int(value_span.text.strip().replace(",", ""))
                    return state.current_balance
                except:
                    pass
    values = soup.find_all("span", class_="stats-value")
    if len(values) >= 2:
        try:
            state.current_balance = int(values[1].text.strip().replace(",", ""))
            return state.current_balance
        except:
            pass
    return None

# ======================================
# 记录解析
# ======================================
def get_game_record_html():
    if not state.user_id:
        return None
    url = f"{API_RECORDS}&touserid={state.user_id}"
    resp = request_with_retry(url)
    return resp.text if resp else None

def parse_game_records(html):
    try:
        soup = BeautifulSoup(html, "html.parser")
        records = []
        for item in soup.find_all("div", class_="record-item"):
            record = {"id": None, "status": "unknown", "amount": 0, "challenger": ""}
            id_div = item.find("div", class_="record-id")
            if id_div:
                link = id_div.find("a")
                if link:
                    id_match = re.search(r'(\d+)', link.text)
                    if id_match:
                        record["id"] = id_match.group(1)
                else:
                    id_match = re.search(r'(\d+)', id_div.text)
                    if id_match:
                        record["id"] = id_match.group(1)
                id_classes = id_div.get("class", [])
                if "status-win" in id_classes:
                    record["status"] = "win"
                elif "status-lose" in id_classes:
                    record["status"] = "lose"
            status_div = item.find("div", class_="record-status")
            if status_div:
                status_text = status_div.text
                challenger_match = re.search(r'被(.+?)应战|应战(.+?)(?:，|"|\s|$)', status_text)
                if challenger_match:
                    record["challenger"] = (challenger_match.group(1) or challenger_match.group(2) or "").strip()
                win_match = re.search(r'赢了.*?(\d+).*?妖晶', status_text)
                lose_match = re.search(r'输了.*?(\d+).*?妖晶', status_text)
                if win_match:
                    record["amount"] = int(win_match.group(1).replace(",", ""))
                    record["status"] = "win"
                elif lose_match:
                    record["amount"] = int(lose_match.group(1).replace(",", ""))
                    record["status"] = "lose"
            if record["id"]:
                records.append(record)
        return records
    except Exception as e:
        ZLog.e(f"解析记录出错: {e}")
        return []

# ======================================
# 投注金额计算
# 规则：输局下局 = 前面总输掉总和 + 基础投注
# ======================================
def calc_real_bet():
    next_bet = state.total_lose_sum + state.base_bet
    final_int = int(next_bet)
    final_int = max(min(final_int, CONFIG["max_bet"]), CONFIG["base_bet"])
    return final_int

# ======================================
# 选择答案
# ======================================
def choose_bet_answer():
    import datetime
    current_hour = datetime.datetime.now().hour
    if current_hour % 2 == 1:
        ans = secure_coin_flip()
    else:
        if state.last_choice is None or state.last_result is None:
            ans = secure_coin_flip()
        elif state.last_result == "win":
            ans = state.last_choice
        else:
            if state.consecutive_losses in (2, 5):
                ans = 2 if state.last_choice == 1 else 1
            else:
                ans = secure_coin_flip()
    state.last_choice = ans
    return ans

# ======================================
# 胜负结算
# ======================================
def check_bet_result():
    html = get_game_record_html()
    if not html:
        return None
    records = parse_game_records(html)
    if not records:
        return None

    ongoing = [r for r in records if r["status"] == "unknown"]
    if ongoing:
        state.last_ongoing_ids = [r["id"] for r in ongoing]
        if not state.last_bet_id:
            state.last_bet_id = ongoing[0]["id"]
        return None

    state.last_ongoing_ids = None
    target = None
    if state.last_bet_id:
        target = next((r for r in records if r["id"] == state.last_bet_id), None)
    if not target and records:
        target = records[0]
    if not target:
        state.last_bet_id = None
        return None

    result = target["status"]
    amount = target["amount"]
    challenger = target.get("challenger", "").strip()
    state.current_challenger = challenger

    ZLog.i(f"挑战者: {challenger}")
    if result == "win":
        state.win_count += 1
        state.consecutive_losses = 0
        state.total_profit += amount
        state.last_result = "win"
        # 赢局重置
        state.total_lose_sum = 0
        state.target_bet = state.base_bet
        refresh_balance()
        ZLog.s(f"胜: {format_money(amount)} | 余: {format_money(state.current_balance)}")

    elif result == "lose":
        state.loss_count += 1
        state.consecutive_losses += 1
        state.total_profit -= amount
        state.last_result = "lose"
        # 累加本局输掉金额到总亏损
        state.total_lose_sum += amount
        refresh_balance()
        ZLog.w(f"连败: {state.consecutive_losses} | 累计亏损总和: {format_money(state.total_lose_sum)}")
        ZLog.e(f"败: {format_money(amount)} | 余: {format_money(state.current_balance)}")
        
        if challenger == "应战" and state.real_bet > 30000:
            ZLog.w("本局挑战者为「应战」，不执行累进规则，保持原投注")
            state.target_bet = state.real_bet
        else:
            state.target_bet = calc_real_bet()

    else:
        state.last_bet_id = None
        return None

    state.real_bet = state.target_bet
    state.last_bet_id = None
    save_game_state()
    refresh_balance()
    return result

# ======================================
# 密码验证
# ======================================
def verify_password():
    if not PASSWORD:
        ZLog.e("需要密码才能投注")
        return False
    post_data = {'needpassword': PASSWORD}
    resp = request_with_retry(API_BET, "POST", post_data)
    if not resp:
        return False
    resp = request_with_retry(API_BET, "GET")
    if not resp:
        return False
    if "needpassword" in resp.text and "请输入密码" in resp.text:
        ZLog.e("密码错误")
        return False
    return True

# ======================================
# 投注发起
# ======================================
def send_bet():
    if not state.user_id:
        return False
    bet_amount = state.real_bet
    refresh_balance()
    if state.current_balance < bet_amount:
        ZLog.e(f"余额不足 {format_money(state.current_balance)} < {format_money(bet_amount)}")
        time.sleep(10)
        return False
    if not verify_password():
        return False
    questions = random.choice(get_question_pool())
    title, opt1, opt2 = questions
    choose = choose_bet_answer()
    post_data = {
        'mymoney': str(bet_amount),
        'question': title,
        'answer1': opt1,
        'myanswer': str(choose),
        'answer2': opt2,
        'action': 'gomod',
        'classid': '0',
        'siteid': '1000',
        'bt': '确 认'
    }
    resp = request_with_retry(API_BET, "POST", post_data)
    if not resp:
        return False
    records = parse_game_records(get_game_record_html() or "")
    if records:
        state.last_bet_id = records[0]["id"]
    state.total_bet_amount += bet_amount
    ZLog.d(f"投 {format_money(bet_amount)} 选 {str(choose)}")
    return True

# ======================================
# 等待结果
# ======================================
def wait_result():
    while state.is_running:
        res = check_bet_result()
        if res is not None:
            return True
        time.sleep(5)

# ======================================
# 延迟
# ======================================
def round_delay():
    if state.last_result == "win":
        return
    if state.consecutive_losses < 6:
        return
    minutes = state.consecutive_losses
    seconds = minutes * 60
    ZLog.d(f"{minutes} 分后开始...")
    time.sleep(seconds)

# ======================================
# 进程锁
# ======================================
def is_pid_alive(pid):
    try:
        pid = int(pid)
        if os.name == "nt":
            return os.system(f'tasklist /FI "PID eq {pid}" > nul 2>&1') == 0
        else:
            os.kill(pid, 0)
            return True
    except:
        return False

def lock_script():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = f.read().strip()
            if is_pid_alive(pid):
                ZLog.e(f"脚本已运行(PID:{pid})，退出")
                exit(0)
            else:
                os.remove(LOCK_FILE)
        except:
            os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(unlock_script)

def unlock_script():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass

# ======================================
# 状态保存/加载
# ======================================
def save_game_state():
    try:
        data = {
            "target_bet": state.target_bet,
            "real_bet": state.real_bet,
            "consecutive_losses": state.consecutive_losses,
            "win_count": state.win_count,
            "loss_count": state.loss_count,
            "total_profit": state.total_profit,
            "total_bet_amount": state.total_bet_amount,
            "total_runs": state.total_runs,
            "last_result": state.last_result,
            "last_choice": state.last_choice,
            "save_date": state.save_date,
            "current_challenger": state.current_challenger,
            "total_lose_sum": state.total_lose_sum
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

def load_game_state():
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        today = state.get_today()
        state.target_bet = data.get("target_bet", CONFIG["base_bet"])
        state.real_bet = data.get("real_bet", CONFIG["base_bet"])
        state.consecutive_losses = data.get("consecutive_losses", 0)
        state.win_count = data.get("win_count", 0)
        state.loss_count = data.get("loss_count", 0)
        state.total_profit = data.get("total_profit", 0)
        state.last_result = data.get("last_result")
        state.last_choice = data.get("last_choice")
        state.save_date = data.get("save_date", today)
        state.current_challenger = data.get("current_challenger", "")
        state.total_lose_sum = data.get("total_lose_sum", 0)
        if state.save_date != today:
            state.total_bet_amount = 0
            state.total_lose_sum = 0
            state.save_date = today
        else:
            state.total_bet_amount = data.get("total_bet_amount", 0)
    except:
        pass

# ======================================
# 安全退出
# ======================================
def safe_exit():
    state.is_running = False

# ======================================
# 主入口
# ======================================
def main():
    ZLog.i("=" * 20)
    ZLog.i("妖火吹牛")
    ZLog.i("=" * 20)

    lock_script()
    if not check_config_valid() or not COOKIE or not init_user_id() or not refresh_balance():
        safe_exit()
        return

    load_game_state()
    state.last_bet_id = None
    state.last_ongoing_ids = None
    state.is_running = True
    state.base_bet = CONFIG["base_bet"]

    ZLog.i(f"基础投注:{CONFIG['base_bet']} | 最大投注:{CONFIG['max_bet']}")

    try:
        while state.is_running:
            html = get_game_record_html()
            records = parse_game_records(html) if html else []
            ongoing = any(r["status"] == "unknown" for r in records)

            if ongoing:
                wait_result()
                round_delay()
            else:
                if send_bet():
                    wait_result()
                    round_delay()
                state.total_runs += 1
            
            if not ongoing and not state.last_bet_id:
                time.sleep(1)

    except KeyboardInterrupt:
        ZLog.w("用户手动停止")
    except Exception as e:
        ZLog.e(f"异常: {str(e)[:50]}")
    finally:
        safe_exit()
        save_game_state()
        total = state.win_count + state.loss_count
        win_rate = f"{state.win_count / total * 100:.1f}%" if total > 0 else "0.0%"
        ZLog.i("=" * 20)
        ZLog.i(f"总轮次:{total} 胜:{state.win_count} 负:{state.loss_count} 胜率:{win_rate}")
        ZLog.i(f"总盈亏:{state.total_profit} 今日投注:{state.total_bet_amount}")
        ZLog.d(f"最终余额:{state.current_balance}")
        ZLog.i("=" * 20)

if __name__ == "__main__":
    main()
