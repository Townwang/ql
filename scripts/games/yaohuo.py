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

import secrets
import requests
import socket
import time
import json
import os
import re
import atexit
import random
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

# ======================================
# 青龙环境变量
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()

CONFIG = {
    "base_bet_phase1": 1000,      # 第一阶段(前十局)基础投注
    "base_bet_phase2": 10000,     # 第二阶段基础投注
    "phase1_rounds": 10,          # 第一阶段局数
    "phase1_loss_threshold": 5000,# 第一阶段累计输阈值
    "global_loss_threshold": 200000, # 全局累计输阈值(20万)
    "multiplier": 2.1,            # 连败倍数
    "random_deduct_max": 1000,    # 第二阶段随机减去的最大金额
    "max_network_errors": 10,     # 网络错误超限次数
    "request_retries": 5,         # 单接口请求重试次数
    "request_timeout": 20,        # 请求超时时间
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
# TCP连接优化 - Session全局初始化
# ======================================
session = requests.Session()

class TCPOptimizedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['socket_options'] = [
            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        ]
        return super().init_poolmanager(*args, **kwargs)

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

# ======================================
# 全局状态
# ======================================
class GameState:
    def __init__(self):
        self.is_running = True
        self.network_error_count = 0

        # 核心规则状态
        self.current_phase = 1  # 1: 前十局阶段 2: 高倍投注阶段
        self.phase1_round_count = 0  # 第一阶段已进行局数
        self.phase1_total_loss = 0   # 第一阶段累计输
        self.global_total_loss = 0   # 全局累计输
        self.consecutive_losses = 0  # 连续输次数
        self.current_bet = CONFIG["base_bet_phase1"]  # 当前投注金额

        # 第二阶段状态
        self.phase2_fixed_choice = None  # 第二阶段固定选择的结果(1/2)

        # 全局强制状态(累计输>20万时触发)
        self.is_global_force_mode = False  # 是否处于全局强制模式
        self.global_force_choice = None    # 全局强制模式下的选择
        self.global_force_rounds = 0       # 全局强制模式下已进行的局数

        # 统计信息
        self.win_count = 0
        self.loss_count = 0
        self.total_profit = 0
        self.total_bet_amount = 0
        self.total_runs = 0

        # 游戏状态
        self.last_bet_id = None
        self.last_ongoing_ids = None
        self.last_result = None
        self.current_balance = 0
        self.user_id = ""

        self.last_choice = None
        self.save_date = self.get_today()
        
        self.current_challenger = ""
        self.last_challenger = ""

        self.balance_low_notified = False

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
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': COOKIE,
    'Origin': BASE_HOST,
    'Referer': API_BET,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
}

session.headers.update(REQUEST_HEADERS)

# ======================================
# 金额格式化
# ======================================
def format_money(num):
    try:
        n = int(num)
        if n >= 100000000:
            return f"{n / 100000000:.2f}亿"
        elif n >= 10000:
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
# 挑衅话术
# ======================================
def get_win_provoke_words():
    return [f"🐮🐮🐮🐮🐮🐮"]

def get_lose_provoke_words():
    return [f"🐶🐶🐶🐶🐶🐶"]

def get_default_provoke_words():
    return ["🥺🥺🥺🥺🥺🥺"]

def get_provoke_words_by_result():
    if state.last_result == "win":
        return get_win_provoke_words()
    elif state.last_result == "lose":
        return get_lose_provoke_words()
    else:
        return get_default_provoke_words()

def gen_dynamic_question():
    nick = state.last_challenger if state.last_challenger else "神秘玩家"
    provoke = random.choice(get_provoke_words_by_result())
    title = f"{provoke}"
    opt1 = "ᅟ"
    opt2 = "ᅟ"
    return [title, opt1, opt2]

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
# 重置第一阶段(所有状态清零)
# ======================================
def reset_phase1():
    state.current_phase = 1
    state.phase1_round_count = 0
    state.phase1_total_loss = 0
    state.consecutive_losses = 0
    state.current_bet = CONFIG["base_bet_phase1"]
    state.phase2_fixed_choice = None
    state.is_global_force_mode = False
    state.global_force_choice = None
    state.global_force_rounds = 0
    ZLog.i("✅ 重置为第一阶段")

# ======================================
# 投注金额计算 - 已移除所有最大投注限制
# ======================================
def calc_real_bet():
    if state.current_phase == 1:
        # 第一阶段固定1000
        return CONFIG["base_bet_phase1"]
    else:
        # 第二阶段：第一局1万，后续每输一局×2.1倍，减去0-1000随机数
        # 无任何最大投注限制
        if state.consecutive_losses == 0:
            bet = CONFIG["base_bet_phase2"]
        else:
            bet = state.current_bet * CONFIG["multiplier"]
            # 减去0-1000的随机整数
            deduct = random.randint(0, CONFIG["random_deduct_max"])
            bet = max(bet - deduct, CONFIG["base_bet_phase2"])  # 不低于基础投注
        
        bet = int(bet)
        return bet

# ======================================
# 选择答案 - 新规则
# ======================================
def choose_bet_answer():
    # 全局强制模式优先级最高
    if state.is_global_force_mode:
        if state.global_force_choice is None:
            # 进入全局强制模式时重新随机一次结果
            state.global_force_choice = secure_coin_flip()
            ZLog.w(f"🔥 强制模式 {state.global_force_choice}")
        ans = state.global_force_choice
    elif state.current_phase == 2:
        # 第二阶段：进入时随机一次，后续固定使用
        if state.phase2_fixed_choice is None:
            state.phase2_fixed_choice = secure_coin_flip()
            ZLog.w(f"②：固定结果 {state.phase2_fixed_choice}")
        ans = state.phase2_fixed_choice
    else:
        # 第一阶段：完全随机
        ans = secure_coin_flip()
    
    state.last_choice = ans
    return ans

# ======================================
# 胜负结算 - 【核心规则修正】
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
    
    state.last_challenger = challenger
    state.current_challenger = challenger

    ZLog.i(f"挑战者: {challenger}")
    
    # 触发全局强制模式(累计输>20万且未进入该模式)
    if state.global_total_loss > CONFIG["global_loss_threshold"] and not state.is_global_force_mode:
        state.is_global_force_mode = True
        state.global_force_rounds = 0
        state.global_force_choice = None  # 下次选择时自动重新随机
    
    if result == "win":
        state.win_count += 1
        state.total_profit += amount
        state.last_result = "win"
        state.balance_low_notified = False
        refresh_balance()
        ZLog.s(f"✅ 胜: {format_money(amount)} | 余: {format_money(state.current_balance)}")
        
        # ======================================
        # 【规则修正】第一阶段赢了不重置！
        # ======================================
        if state.is_global_force_mode:
            # 全局强制模式赢了，立即重置
            reset_phase1()
        elif state.current_phase == 2:
            # 第二阶段赢了，立即重置回第一阶段
            reset_phase1()
        else:
            # 第一阶段赢了：不重置！继续进行第一阶段，只增加局数计数
            state.phase1_round_count += 1
    elif result == "lose":
        state.loss_count += 1
        state.total_profit -= amount
        state.last_result = "lose"
        state.consecutive_losses += 1
        
        # 更新全局累计输
        state.global_total_loss += amount
        
        # 处理全局强制模式逻辑
        if state.is_global_force_mode:
            state.global_force_rounds += 1
            ZLog.w(f"🔥 强制模式第{state.global_force_rounds}局 | 连败: {state.consecutive_losses} | 累计输: {format_money(state.global_total_loss)}")
            
            # 连续输3局，强制重置回第一阶段
            if state.global_force_rounds >= 3:
                ZLog.w(f"⚠️ 强制重置回第一阶段")
                reset_phase1()
        else:
            # 处理正常阶段逻辑
            if state.current_phase == 1:
                state.phase1_total_loss += amount
                state.phase1_round_count += 1
                ZLog.w(f"①第{state.phase1_round_count}局 | 阶段累计输: {format_money(state.phase1_total_loss)}")
                
                # ======================================
                # 【规则修正】只有10局全部完成后才判断
                # ======================================
                if state.phase1_round_count >= CONFIG["phase1_rounds"]:
                    ZLog.i(f"①10局已完成，开始统计结果...")
                    if state.phase1_total_loss > CONFIG["phase1_loss_threshold"]:
                        # 累计输>5000，进入第二阶段
                        state.current_phase = 2
                        state.consecutive_losses = 0  # 第二阶段重新计算连败
                        state.phase2_fixed_choice = None  # 下次选择时自动随机
                        ZLog.w(f"①累计输{format_money(state.phase1_total_loss)} > 5000")
                    else:
                        # 累计输≤5000，完全重置第一阶段
                        ZLog.i(f"①累计输{format_money(state.phase1_total_loss)} ≤ 5000，完全重置")
                        reset_phase1()
            else:
                # 第二阶段正常连败
                ZLog.w(f"②连败: {state.consecutive_losses} | 累计输: {format_money(state.global_total_loss)}")
        
        refresh_balance()
        ZLog.e(f"❌ 败: {format_money(amount)} | 余: {format_money(state.current_balance)}")

    else:
        state.last_bet_id = None
        return None

    # 计算下一局投注金额
    state.current_bet = calc_real_bet()
    state.last_bet_id = None
    save_game_state()
    refresh_balance()
    return result

# ======================================
# 配置校验
# ======================================
def check_config_valid():
    required_numeric = [
        "base_bet_phase1", "base_bet_phase2", "phase1_rounds",
        "phase1_loss_threshold", "global_loss_threshold", "multiplier",
        "random_deduct_max", "max_network_errors",
        "request_retries", "request_timeout",
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
# 带重试请求
# ======================================
def request_with_retry(url, method="GET", data=None):
    retry_max = CONFIG["request_retries"]
    timeout = CONFIG["request_timeout"]
    
    for attempt in range(1, retry_max + 1):
        try:
            if method.upper() == "GET":
                resp = session.get(url, timeout=timeout)
            else:
                resp = session.post(url, data=data, timeout=timeout)
            resp.raise_for_status()
            
            if "请先登录" in resp.text or "登录网站" in resp.text:
                ZLog.e("登录已失效")
                state.is_running = False
                return None
            
            state.network_error_count = 0
            return resp

        except Exception as e:
            state.network_error_count += 1
            delay_sec = state.network_error_count * 60
            ZLog.w(f"第{attempt}次请求失败 | 累计网络错误{state.network_error_count}次 → 延迟{delay_sec//60}分钟后重试")
            
            if state.network_error_count >= CONFIG["max_network_errors"]:
                ZLog.e("网络错误次数超限，脚本停止运行")
                state.is_running = False
                return None
            
            time.sleep(delay_sec)

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
    bet_amount = state.current_bet
    refresh_balance()
    if state.current_balance < bet_amount:
        if not state.balance_low_notified:
            ZLog.e(f"余额不足 {format_money(state.current_balance)} < {format_money(bet_amount)}")
            state.balance_low_notified = True
        time.sleep(10)
        return False
    state.balance_low_notified = False
    if not verify_password():
        return False
    questions = gen_dynamic_question()
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
    
    # 显示当前阶段和选择信息
    if state.is_global_force_mode:
        phase_info = f"🔥 强制模式(第{state.global_force_rounds+1}/3局，固定选{state.global_force_choice})"
    elif state.current_phase == 2:
        phase_info = f"②(固定选{state.phase2_fixed_choice}，2.1倍递增，无上限)"
    else:
        phase_info = f"①(第{state.phase1_round_count+1}/10局)"
    ZLog.d(f"[{phase_info}] 投 {format_money(bet_amount)} 选 {str(choose)}")
    return True

# ======================================
# 等待结果 - 无限等待直到开奖
# ======================================
def wait_result():
    poll_delay = 0
    max_delay = 2
    while state.is_running:
        if poll_delay > 0:
            time.sleep(poll_delay)
        
        res = check_bet_result()
        if res is not None:
            return True
        poll_delay = min(poll_delay + 0.01, max_delay)

# ======================================
# 延迟
# ======================================
def round_delay():
    # 保留原有的连败延迟逻辑
    if state.last_result == "win":
        return
    if state.consecutive_losses < 10:
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
            "current_phase": state.current_phase,
            "phase1_round_count": state.phase1_round_count,
            "phase1_total_loss": state.phase1_total_loss,
            "global_total_loss": state.global_total_loss,
            "consecutive_losses": state.consecutive_losses,
            "current_bet": state.current_bet,
            "phase2_fixed_choice": state.phase2_fixed_choice,
            "is_global_force_mode": state.is_global_force_mode,
            "global_force_choice": state.global_force_choice,
            "global_force_rounds": state.global_force_rounds,
            "win_count": state.win_count,
            "loss_count": state.loss_count,
            "total_profit": state.total_profit,
            "total_bet_amount": state.total_bet_amount,
            "total_runs": state.total_runs,
            "last_result": state.last_result,
            "last_choice": state.last_choice,
            "save_date": state.save_date,
            "current_challenger": state.current_challenger,
            "last_challenger": state.last_challenger
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
        state.current_phase = data.get("current_phase", 1)
        state.phase1_round_count = data.get("phase1_round_count", 0)
        state.phase1_total_loss = data.get("phase1_total_loss", 0)
        state.global_total_loss = data.get("global_total_loss", 0)
        state.consecutive_losses = data.get("consecutive_losses", 0)
        state.current_bet = data.get("current_bet", CONFIG["base_bet_phase1"])
        state.phase2_fixed_choice = data.get("phase2_fixed_choice", None)
        state.is_global_force_mode = data.get("is_global_force_mode", False)
        state.global_force_choice = data.get("global_force_choice", None)
        state.global_force_rounds = data.get("global_force_rounds", 0)
        state.win_count = data.get("win_count", 0)
        state.loss_count = data.get("loss_count", 0)
        state.total_profit = data.get("total_profit", 0)
        state.last_result = data.get("last_result")
        state.last_choice = data.get("last_choice")
        state.save_date = data.get("save_date", today)
        state.current_challenger = data.get("current_challenger", "")
        state.last_challenger = data.get("last_challenger", "")
        
        if state.save_date != today:
            state.total_bet_amount = 0
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
    session.close()

# ======================================
# 主入口
# ======================================
def main():
    ZLog.i("=" * 20)
    ZLog.i("妖火吹牛 - 规则修正版 v2.6")
    ZLog.i("✓ 第一阶段：10局固定1000，中途输赢都不重置")
    ZLog.i("✓ 10局完成后统计：输>5000进第二阶段，否则重置")
    ZLog.i("✓ 第二阶段：随机固定结果，1万起投2.1倍递增")
    ZLog.i("✓ 第二阶段每局随机减0-1000，赢了立即重置")
    ZLog.i("✓ 全局输>20万：强制重随结果，最多3局")
    ZLog.i("✓ 全局模式赢一局或连输3局都重置回第一阶段")
    ZLog.i("✓ 已移除所有最大投注限制，金额无限递增")
    ZLog.i("=" * 20)

    lock_script()
    if not check_config_valid() or not COOKIE or not init_user_id() or not refresh_balance():
        safe_exit()
        return

    load_game_state()
    state.last_bet_id = None
    state.last_ongoing_ids = None
    state.is_running = True

    # 显示启动时的当前状态
    ZLog.i(f"全局累计输: {format_money(state.global_total_loss)}")
    if state.is_global_force_mode:
        phase_info = f"🔥 强制模式(第{state.global_force_rounds}/3局，固定选{state.global_force_choice})"
        ZLog.i(f"当前状态: {phase_info}")
        ZLog.i(f"当前连败: {state.consecutive_losses} | 当前投注: {format_money(state.current_bet)}")
    elif state.current_phase == 2:
        phase_info = f"②(固定选{state.phase2_fixed_choice}，2.1倍递增，无上限)"
        ZLog.i(f"当前状态: {phase_info}")
        ZLog.i(f"②连败: {state.consecutive_losses} | 当前投注: {format_money(state.current_bet)}")
    else:
        phase_info = f"①(第{state.phase1_round_count+1}/10局)"
        ZLog.i(f"当前状态: {phase_info}")
        ZLog.i(f"①累计输: {format_money(state.phase1_total_loss)}")

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
                time.sleep(0.5)

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
        ZLog.i(f"总盈亏:{format_money(state.total_profit)} 今日投注:{format_money(state.total_bet_amount)}")
        ZLog.i(f"全局累计输:{format_money(state.global_total_loss)}")
        ZLog.d(f"最终余额:{format_money(state.current_balance)}")
        ZLog.i("=" * 20)

if __name__ == "__main__":
    main()
