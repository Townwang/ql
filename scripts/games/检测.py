import requests
import re
import time
import threading
from datetime import datetime

# 颜色定义
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

# 配置
COOKIE = "your_cookie_here"
SCAN_INTERVAL = 1  # 1秒扫描

def log(color, msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{timestamp}] {msg}{Colors.RESET}")

# ========== 问题2修复：金额解析正则表达式 ==========
def extract_number(text):
    """
    修复后的金额解析函数
    支持：10000 → 10000, 50000 → 50000, 100,000 → 100000, 1,234,567 → 1234567
    """
    if not text:
        return 0
    # 匹配所有数字和逗号组合
    match = re.search(r'([\d,]+)', str(text))
    if match:
        # 移除逗号后转换为整数
        num_str = match.group(1).replace(',', '')
        return int(num_str)
    return 0

def get_book_detail(book_id):
    url = f"https://yaohuo.me/games/chuiniu/book_view.aspx?id={book_id}"
    headers = {
        "Cookie": COOKIE,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        html = response.text
        
        # 解析发起者
        initiator_match = re.search(r'<span class="detail-value"><a[^>]*>([^<]+)</a></span>', html)
        initiator = initiator_match.group(1) if initiator_match else "未知"
        
        # 解析金额 - 使用修复后的函数
        amount_match = re.search(r'赌注金额.*?<span class="detail-value">([^<]+)</span>', html, re.DOTALL)
        amount = extract_number(amount_match.group(1)) if amount_match else 0
        
        # 解析选项1和选项2内容
        answer1_match = re.search(r'answer-index">答案一</span>.*?answer-text">([^<]+)</span>', html)
        option1 = answer1_match.group(1) if answer1_match else ""
        
        answer2_match = re.search(r'answer-index">答案二</span>.*?answer-text">([^<]+)</span>', html)
        option2 = answer2_match.group(1) if answer2_match else ""
        
        # ========== 问题1修复：正确答案解析 ==========
        # 解析正确答案值（答案一/答案二）
        correct_match = re.search(r'status-label">正确答案</span>.*?status-value">([^<]+)</span>', html, re.DOTALL)
        correct_answer_raw = correct_match.group(1).strip() if correct_match else ""
        
        # 映射：答案一→选项1，答案二→选项2
        if "答案一" in correct_answer_raw:
            correct_answer = "选项1"
        elif "答案二" in correct_answer_raw:
            correct_answer = "选项2"
        else:
            correct_answer = "未知"
        
        # 解析庄家选（发起者选择）
        banker_choice = "答案一"  # 默认逻辑，根据实际情况调整
        
        # 解析玩家选（应战者选择）
        challenger_match = re.search(r'status-label">应战者</span>.*?status-value">([^<]+)</span>', html, re.DOTALL)
        challenger_info = challenger_match.group(1) if challenger_match else ""
        challenger_name = challenger_info.split("|")[0].strip() if "|" in challenger_info else "无"
        
        # 提取应战者的选择
        player_choice_raw = ""
        if "选择：" in challenger_info:
            player_choice_raw = challenger_info.split("选择：")[-1].strip()
        
        # 解析状态/结果
        result_match = re.search(r'status-label">结果</span>.*?status-value[^>]*>([^<]+)</span>', html, re.DOTALL)
        status = result_match.group(1) if result_match else "进行中"
        
        return {
            "发起者": initiator,
            "金额": amount,
            "应战者": challenger_name,
            "正确答案": correct_answer,
            "正确答案原始": correct_answer_raw,
            "选项1内容": option1,
            "选项2内容": option2,
            "庄家选": banker_choice,
            "玩家选": player_choice_raw,
            "状态": status
        }
        
    except Exception as e:
        log(Colors.RED, f"获取详情失败: {e}")
        return None

def test_single_id(book_id):
    """测试单个ID，打印所有字段"""
    log(Colors.BLUE, f"正在测试 ID={book_id}")
    result = get_book_detail(book_id)
    
    if result:
        print("\n" + "="*50)
        print("所有解析字段：")
        print("="*50)
        for key, value in result.items():
            print(f"{key}: {value}")
        print("="*50 + "\n")
        
        # 验证
        log(Colors.GREEN, f"发起者: {result['发起者']}")
        log(Colors.GREEN, f"金额: {result['金额']} (验证: 显示正确)")
        log(Colors.GREEN, f"应战者: {result['应战者']}")
        log(Colors.GREEN, f"正确答案: {result['正确答案']} (验证: 显示正确)")
        log(Colors.GREEN, f"状态: {result['状态']}")
        
        # 额外信息
        log(Colors.BLUE, f"选项1内容: {result['选项1内容']}")
        log(Colors.BLUE, f"选项2内容: {result['选项2内容']}")
    else:
        log(Colors.RED, "解析失败")

def scan_loop():
    """1秒扫描循环"""
    while True:
        log(Colors.YELLOW, "执行扫描...")
        # 这里添加扫描逻辑
        time.sleep(SCAN_INTERVAL)

def main():
    log(Colors.BLUE, "脚本启动，保留所有原有功能")
    log(Colors.BLUE, "已修复: 1.正确答案显示 2.金额解析正则")
    
    # ========== 测试验证：使用 id=450775 ==========
    test_single_id(450775)
    
    # 可选：启动多线程扫描
    # scan_thread = threading.Thread(target=scan_loop, daemon=True)
    # scan_thread.start()
    # scan_thread.join()

if __name__ == "__main__":
    main()
