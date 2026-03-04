import ccxt
import time
import pandas as pd
from datetime import datetime
import os

# ========== 配置区 ==========
API_KEY = 'kIz8gf0CWt2YD21Z8oa4vunoY4Kyb3Ye73dJRvfedM7f0KZHPVlG7dse2lM7eifZ'
API_SECRET = 'lYHb2QJtz3VZimZvjJdF6Dv5ZyZceyBHAMkMZXId2s2HtOyTl5sCK7SJifJzu9Vt'
REFRESH_INTERVAL = 60  # 刷新间隔（秒）
MIN_VALUE_USDT = 1.0    # 最小显示价值（USDT）
HISTORY_FILE = 'balance_history.csv'  # 历史记录文件
# ===========================

def get_prices():
    """获取所有交易对的最新价格"""
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        # 提取 symbol -> price 的字典，只保留 USDT 交易对
        prices = {}
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT'):
                base = symbol.split('/')[0]
                prices[base] = ticker['last']
        return prices
    except Exception as e:
        print(f"获取价格失败: {e}")
        return {}

def get_binance_data():
    """获取现货和合约数据"""
    # 现货
    spot = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'options': {'defaultType': 'spot'},
    })
    
    # U本位合约（如果不需要合约可以注释掉）
    future = ccxt.binanceusdm({
        'apiKey': API_KEY,
        'secret': API_SECRET,
    })
    
    # 获取现货余额
    spot_balance = spot.fetch_balance()
    spot_balances = {}
    for currency, data in spot_balance['total'].items():
        if data > 0:
            free = spot_balance['free'].get(currency, 0)
            used = spot_balance['used'].get(currency, 0)
            spot_balances[currency] = {
                'free': free,
                'used': used,
                'total': data
            }
    
    # 获取合约持仓
    try:
        positions = future.fetch_positions()
        future_positions = []
        for pos in positions:
            if float(pos['contracts']) != 0:
                future_positions.append({
                    'symbol': pos['symbol'],
                    'side': '多' if float(pos['side']) > 0 else '空',
                    'contracts': abs(float(pos['contracts'])),
                    'entry_price': float(pos['entryPrice']),
                    'mark_price': float(pos['markPrice']),
                    'pnl': float(pos['unrealizedPnl']),
                    'percentage': float(pos['percentage']),
                })
    except Exception as e:
        print(f"获取合约持仓失败: {e}")
        future_positions = []
    
    return spot_balances, future_positions

def save_history(spot_balances, total_value):
    """保存历史余额到 CSV"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 将余额数据展平为一维记录
    record = {'timestamp': timestamp, 'total_usdt': total_value}
    for currency, data in spot_balances.items():
        record[f'{currency}_total'] = data['total']
        record[f'{currency}_free'] = data['free']
    
    # 如果文件不存在，创建并写入表头
    if not os.path.isfile(HISTORY_FILE):
        df = pd.DataFrame([record])
        df.to_csv(HISTORY_FILE, index=False)
    else:
        df = pd.read_csv(HISTORY_FILE)
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        df.to_csv(HISTORY_FILE, index=False)
    print(f"历史记录已保存到 {HISTORY_FILE}")

def display_data(spot_balances, future_positions, prices):
    """格式化显示数据"""
    # 清屏（可选）
    print("\033c", end="")
    
    print("=" * 80)
    print(f"币安账户监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 计算每项资产的价值（USDT）
    valued_balances = []
    total_value = 0.0
    for currency, data in spot_balances.items():
        price = prices.get(currency, 0)
        value = data['total'] * price
        if value > MIN_VALUE_USDT:  # 过滤小额
            valued_balances.append({
                '币种': currency,
                '可用': data['free'],
                '冻结': data['used'],
                '总计': data['total'],
                '价格(USDT)': price,
                '价值(USDT)': value
            })
            total_value += value
    
    # 按价值排序（从高到低）
    valued_balances.sort(key=lambda x: x['价值(USDT)'], reverse=True)
    
    print("\n【现货余额】（价值 > 1 USDT）")
    if valued_balances:
        # 打印表格
        print(f"{'币种':<8} {'可用':<15} {'冻结':<15} {'总计':<15} {'价格(USDT)':<12} {'价值(USDT)':<12}")
        print("-" * 80)
        for item in valued_balances:
            print(f"{item['币种']:<8} {item['可用']:<15.8f} {item['冻结']:<15.8f} {item['总计']:<15.8f} {item['价格(USDT)']:<12.2f} {item['价值(USDT)']:<12.2f}")
    else:
        print("无符合条件的资产")
    
    print(f"\n💰 总资产价值: {total_value:.2f} USDT")
    
    print("\n【合约持仓】")
    if future_positions:
        print(f"{'币种':<10} {'方向':<4} {'持仓数':<10} {'开仓价':<10} {'标记价':<10} {'未实现盈亏':<12} {'盈亏%':<8}")
        print("-" * 70)
        for pos in future_positions:
            print(f"{pos['symbol']:<10} {pos['side']:<4} {pos['contracts']:<10.4f} {pos['entry_price']:<10.2f} {pos['mark_price']:<10.2f} {pos['pnl']:<12.2f} {pos['percentage']:<8.2f}%")
    else:
        print("无合约持仓")
    
    print("\n" + "=" * 80)
    print(f"每 {REFRESH_INTERVAL} 秒刷新一次 (按 Ctrl+C 停止)")
    
    return total_value

def main():
    print("正在连接币安获取数据...")
    while True:
        try:
            # 获取价格（每次刷新都重新获取，确保最新）
            prices = get_prices()
            if not prices:
                print("警告：未能获取价格数据，资产价值将显示为0")
            
            # 获取账户数据
            spot_balances, future_positions = get_binance_data()
            
            # 显示并获取总价值
            total_value = display_data(spot_balances, future_positions, prices)
            
            # 保存历史记录
            save_history(spot_balances, total_value)
            
            # 等待下次刷新
            time.sleep(REFRESH_INTERVAL)
        except KeyboardInterrupt:
            print("\n监控已停止")
            break
        except Exception as e:
            print(f"发生错误: {e}，将在 {REFRESH_INTERVAL} 秒后重试")
            time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    main()
