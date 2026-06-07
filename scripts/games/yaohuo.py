# -*- coding: utf-8 -*-
# ======================================
# 添加任务
"""
name: 妖火吹牛-π策略版
tag: 游戏,妖火
instance: single

"""
# 变量声明 （可设置在docker环境变量）
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
# π小数点后1000位（用于投注策略，奇数选1，偶数选2）
# ======================================
PI_1000_DIGITS = (
    "14159265358979323846264338327950288419716939937510"
    "58209749445923078164062862089986280348253421170679"
    "82148086513282306647093844609550582231725359408128"
    "48111745028410270193852110555964462294895493038196"
    "44288109756659334461284756482337867831652712019091"
    "45648566923460348610454326648213393607260249141273"
    "72458700660631558817488152092096282925409171536436"
    "78925903600113305305488204665213841469519415116094"
    "33057270365759591953092186117381932611793105118548"
    "07446237996274956735188575272489122793818301194912"
    "98336733624406566430860213949463952247371907021798"
    "60943702770539217176293176752384674818467669405132"
    "00056812714526356082778577134275778960917363717872"
    "14684409012249534301465495853710507922796892589235"
    "42019956112129021960864034418159813629774771309960"
    "51870721134999999837297804995105973173281609631859"
    "50244594553469083026425223082533446850352619311881"
    "71010003137838752886587533208381420617177669147303"
    "59825349042875546873115956286388235378759375195778"
    "18577805321712268066130019278766111959092164201989"
)

# ======================================
# 青龙环境变量
# ======================================
COOKIE = os.getenv("YH_COOKIE", "").strip()
PASSWORD = os.getenv("YH_PASSWORD", "").strip()

CONFIG = {
    "base_bet": 369,           # 基础投注
    "max_bet": 1000000,         # 单次最大投注
    "lose_multiple": 2.2,      # 连败倍率 2.2倍
    "max_network_errors": 10,  # 网络错误超限次数
    "request_retries": 5,      # 单接口请求重试次数
    "request_timeout": 20,    # 请求超时时间
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
        self.last_challenger = ""

        self.balance_low_notified = False
        
        # π策略：局数计数器
        self.round_counter = 0

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
# 挑衅话术
# ======================================
def get_win_provoke_words():
    return [f"🐮🐮🐮🐮🐮🐮🐮"]

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
# 【π策略】选择答案 - 唯一修改的地方！
# ======================================
def choose_bet_answer():
    """
    π策略：
    - 第N局 = π小数点后第N位数字
    - 奇数 → 选1
    - 偶数 → 选2
    - 超过1000局自动从头循环
    - 跨天自动从第1局重新开始
    """
    # 局数计数器自增
    state.round_counter += 1
    
    # 获取对应的π数字（超过1000则循环）
    pi_index = (state.round_counter - 1) % len(PI_1000_DIGITS)
    pi_digit = int(PI_1000_DIGITS[pi_index])
    
    # 奇数选1，偶数选2
    ans = 1 if pi_digit % 2 == 1 else 2
    
    cycle_info = f" (循环第{(state.round_counter - 1) // 1000 + 1}轮)" if state.round_counter > 1000 else ""
    ZLog.d(f"第{state.round_counter}局 | π第{pi_index + 1}位={pi_digit} | {'奇→选1' if pi_digit % 2 == 1 else '偶→选2'}{cycle_info}")
    
    state.last_choice = ans
    return ans

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
# 投注金额计算：上一局 * 2.2 + 随机加减
# ======================================
def calc_real_bet():
    # 基础计算：当前目标投注 = 上一局投注 * 2.2
    next_bet = state.real_bet * CONFIG["lose_multiple"]
    
    # 第三局以后，随机加减 0-500 * 倍数
    if state.round_counter >= 3:
        random_base = random.randint(0, 500)
        random_adjust = int(random_base * CONFIG["lose_multiple"])
        if random.choice([True, False]):
            next_bet += random_adjust
            ZLog.d(f"投注随机 +{random_adjust}")
        else:
            next_bet -= random_adjust
            ZLog.d(f"投注随机 -{random_adjust}")
    
    final_int = int(next_bet)
    final_int = max(min(final_int, CONFIG["max_bet"]), CONFIG["base_bet"])
    return final_int

# ======================================
# 胜负结算 - 使用实际金额判断
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
    
    is_max_bet_round = (amount >= CONFIG["max_bet"])
    
    if is_max_bet_round:
        ZLog.w(f"检测到大额投注: {format_money(amount)} >= 上限 {format_money(CONFIG['max_bet'])}")
        ZLog.w(f"无论输赢，下局都强制重置为基础投注 {format_money(CONFIG['base_bet'])}")

    if result == "win":
        state.win_count += 1
        state.consecutive_losses = 0
        state.total_profit += amount
        state.last_result = "win"
        state.balance_low_notified = False
        refresh_balance()
        ZLog.s(f"胜: {format_money(amount)} | 余: {format_money(state.current_balance)}")
        
        state.total_lose_sum = 0
        state.target_bet = state.base_bet
        state.real_bet = state.base_bet

    elif result == "lose":
        state.loss_count += 1
        state.consecutive_losses += 1
        state.total_profit -= amount
        state.last_result = "lose"
        
        if is_max_bet_round:
            ZLog.w(f"封顶投注输了：强制重置为基础投注")
            state.total_lose_sum = 0
            state.target_bet = state.base_bet
            state.real_bet = state.base_bet
        else:
            state.total_lose_sum += amount
            state.target_bet = calc_real_bet()
            state.real_bet = state.target_bet
            
        refresh_balance()
        ZLog.w(f"连败: {state.consecutive_losses} | 累计亏损总和: {format_money(state.total_lose_sum)}")
        ZLog.e(f"败: {format_money(amount)} | 余: {format_money(state.current_balance)}")

    else:
        state.last_bet_id = None
        return None

    state.last_bet_id = None
    save_game_state()
    refresh_balance()
    return result

# ======================================
# 配置校验
# ======================================
def check_config_valid():
    required_numeric = [
        "base_bet", "max_bet", "lose_multiple",
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
# 带重试请求 - 完全保留v2.1原版
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
    bet_amount = state.real_bet
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
    ZLog.d(f"投 {format_money(bet_amount)} 选 {str(choose)}")
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
# 状态保存/加载 - 新增round_counter
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
            "total_lose_sum": state.total_lose_sum,
            "last_challenger": state.last_challenger,
            "round_counter": state.round_counter
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
        state.last_challenger = data.get("last_challenger", "")
        state.round_counter = data.get("round_counter", 0)
        
        if state.save_date != today:
            state.total_bet_amount = 0
            state.total_lose_sum = 0
            state.save_date = today
            state.real_bet = CONFIG["base_bet"]
            state.target_bet = CONFIG["base_bet"]
            state.round_counter = 0  # 跨天重置π计数器
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
    ZLog.i("妖火吹牛 - π策略版 v4.1")
    ZLog.i("✓ 基于v2.1稳定版，网络代码100%兼容")
    ZLog.i("✓ 答案选择：π小数点后N位，奇选1偶选2")
    ZLog.i("✓ 内置π前1000位，1000局后自动循环")
    ZLog.i("✓ 每局输掉后下局投注 = 上局 × 2.2倍")
    ZLog.i("✓ 第3局起投注随机±(0-500×倍数)")
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

    ZLog.i(f"基础投注:{CONFIG['base_bet']} | 最大投注:{CONFIG['max_bet']} | 连败倍率:{CONFIG['lose_multiple']}")
    ZLog.i(f"当前已进行局数: {state.round_counter} | 对应π第{state.round_counter % 1000 + 1}位")

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
                    if state.real_bet >= CONFIG["max_bet"]:
                        ZLog.w(f"脚本自动投注已达上限{format_money(CONFIG['max_bet'])}，跳过等待直接下一局")
                        state.total_lose_sum = 0
                        state.target_bet = CONFIG["base_bet"]
                        state.real_bet = CONFIG["base_bet"]
                        state.last_bet_id = None
                        state.last_result = None
                        save_game_state()
                    else:
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
        ZLog.i(f"总盈亏:{state.total_profit} 今日投注:{state.total_bet_amount}")
        ZLog.d(f"最终余额:{state.current_balance}")
        ZLog.i("=" * 20)

if __name__ == "__main__":
    main()
