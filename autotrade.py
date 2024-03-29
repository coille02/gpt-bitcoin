import os
from dotenv import load_dotenv
import pyupbit
import pandas as pd
import pandas_ta as ta
import json
from openai import OpenAI
import schedule
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# Load environment variables
load_dotenv()


# Setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))
slack_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'))


def send_slack_message(channel, message):
    try:
        slack_client.chat_postMessage(channel=channel, text=message)
        print(f"{channel}에 메시지 전송 완료: {message}")
    except SlackApiError as e:
        print(f"슬랙 메시지 전송 실패: {e.response['error']}")



def get_current_status(coins):
    statuses = {}
    balances = upbit.get_balances()
    for coin in coins:
        orderbook = pyupbit.get_orderbook(ticker=f"KRW-{coin}")
        current_time = orderbook['timestamp']
        balance_info = next((item for item in balances if item['currency'] == coin), None)
        coin_balance = balance_info['balance'] if balance_info else 0
        avg_buy_price = balance_info['avg_buy_price'] if balance_info else 0
        statuses[coin] = {
            'current_time': current_time,
            'orderbook': orderbook,
            'balance': coin_balance,
            'avg_buy_price': avg_buy_price
        }
    return json.dumps(statuses)


def fetch_and_prepare_data():
    # Fetch data
    df_daily = pyupbit.get_ohlcv("KRW-BTC", "day", count=30)
    df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=24)

    # Define a helper function to add indicators
    def add_indicators(df):
        # Moving Averages
        # Calculate and add SMAs for 3, 5, 10, and 20-day periods
        df['SMA_3'] = ta.sma(df['close'], length=3)
        df['SMA_5'] = ta.sma(df['close'], length=5)
        df['SMA_10'] = ta.sma(df['close'], length=10)
        df['SMA_20'] = ta.sma(df['close'], length=20)

        # Calculate and add EMAs for 3, 5, 10, and 20-day periods
        df['EMA_3'] = ta.ema(df['close'], length=3)
        df['EMA_5'] = ta.ema(df['close'], length=5)
        df['EMA_10'] = ta.ema(df['close'], length=10)
        df['EMA_20'] = ta.ema(df['close'], length=20)

        # df['SMA_10'] = ta.sma(df['close'], length=10)
        # df['EMA_10'] = ta.ema(df['close'], length=10)

        # RSI
        df['RSI_14'] = ta.rsi(df['close'], length=14)

        # Stochastic Oscillator
        stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
        df = df.join(stoch)

        # MACD
        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema_fast - ema_slow
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD'] - df['Signal_Line']

        # Bollinger Bands
        df['Middle_Band'] = df['close'].rolling(window=20).mean()
        # Calculate the standard deviation of closing prices over the last 20 days
        std_dev = df['close'].rolling(window=20).std()
        # Calculate the upper band (Middle Band + 2 * Standard Deviation)
        df['Upper_Band'] = df['Middle_Band'] + (std_dev * 2)
        # Calculate the lower band (Middle Band - 2 * Standard Deviation)
        df['Lower_Band'] = df['Middle_Band'] - (std_dev * 2)

        return df

    # Add indicators to both dataframes
    df_daily = add_indicators(df_daily)
    df_hourly = add_indicators(df_hourly)

    combined_df = pd.concat([df_daily, df_hourly], keys=['daily', 'hourly'])
    combined_data = combined_df.to_json(orient='split')

    # make combined data as string and print length
    print(len(combined_data))

    return json.dumps(combined_data)


def get_instructions(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            instructions = file.read()
        return instructions
    except FileNotFoundError:
        print("File not found.")
    except Exception as e:
        print("An error occurred while reading the file:", e)


def analyze_data_with_gpt4(data_json):
    instructions_path = "./instructions.md"  # Ensure correct path
    try:
        instructions = get_instructions(instructions_path)
        if not instructions:
            print("No instructions found.")
            return None

        coins = ["BTC", "SOL", "SHIB"]
        current_status = get_current_status(coins)  # Now passing coins list
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": data_json},
                {"role": "user", "content": current_status}
            ],
            response_format={"type":"json_object"}
        )
        # Print the response content to console
        # print("OpenAI GPT-4 Response:")
        # print(response)
        advice = json.loads(response.choices[0].message.content)
        print(advice)
        # Assuming advice structure is as provided in your example
        decisions = advice.get("decisions", {})
        investment_strategy = advice.get("investment_strategy", {})
        buying_ratios = investment_strategy.get("buying_ratios", {})
        
        # Normalize buying_ratios from percentages to decimals for computation
        for coin, ratio in buying_ratios.items():
            buying_ratios[coin] = float(ratio.strip('%')) / 100
        return decisions, buying_ratios
    except Exception as e:
        error_message = f"Error in analyzing data with GPT-4: {e}"
        print(error_message)
        print(f"Response content: {response.content}")
        send_slack_message('#coinautotade', error_message)  # Ensure the correct channel name
        return {}, {}


def calculate_total_krw_value(coins):
    total_krw_value = 0
    for coin in coins:
        coin_balance = upbit.get_balance(coin)
        current_price = pyupbit.get_current_price(f"KRW-{coin}")
        krw_value = coin_balance * current_price
        total_krw_value += krw_value
    return total_krw_value

def make_decision_and_execute():
    print("의사 결정을 내리고 실행 중...")
    coins = ["BTC", "SOL", "SHIB"]
    data_json = fetch_and_prepare_data()  # 분석에 필요한 데이터를 제공한다고 가정합니다.
    decisions, buying_ratios = analyze_data_with_gpt4(data_json)

    # 총 투자 가능 금액 계산
    total_investment_amount = get_total_investment_amount()

    # 거래 전 KRW 잔액과 총 가치 기록
    krw_balance_before_trading = upbit.get_balance("KRW")
    coin_value_before_trading = calculate_total_krw_value(coins)
    total_value_before_trading = krw_balance_before_trading + coin_value_before_trading

    total_fees = 0  # 총 수수료 초기화

    for coin in coins:
        decision = decisions.get(coin, {}).get('decision', 'hold')
        reason = decisions.get(coin, {}).get('reason', '')
        ratio = buying_ratios.get(coin, 0)
        
        # 현재 잔액 확인 및 목표 잔액 계산
        coin_balance = upbit.get_balance(coin)
        current_price = pyupbit.get_current_price(f"KRW-{coin}")
        
        target_balance_krw = total_investment_amount * ratio
        target_balance = target_balance_krw / current_price
        
        if decision == 'buy':
            if coin_balance < target_balance:
                amount_to_invest = (target_balance - coin_balance) * current_price
                result = execute_buy(coin, amount_to_invest, reason)
                if result:
                    total_fees += result['reserved_fee']  # 수수료 누적
            else:
                print(f"{coin}의 잔액이 충분하므로 매수를 건너뜁니다.")
        elif decision == 'sell' and coin_balance > 0:
            result = execute_sell(coin, reason)
            if result:
                total_fees += result['reserved_fee']  # 수수료 누적
        else:
            print(f"{coin} 보유 중: {reason}")

    # 거래 후 KRW 잔액과 총 가치 기록
    krw_balance_after_trading = upbit.get_balance("KRW")
    coin_value_after_trading = calculate_total_krw_value(coins)
    total_value_after_trading = krw_balance_after_trading + coin_value_after_trading

    # 수익금과 수익률 계산
    profit = total_value_after_trading - total_value_before_trading - total_fees
    profit_ratio = (profit / total_value_before_trading) * 100

    # 계산된 값을 슬랙 메시지로 전송
    settlement_msg = f"거래 전 총 자산 가치(KRW): {total_value_before_trading:,.0f}, 거래 후 총 자산 가치(KRW): {total_value_after_trading:,.0f}, 총 수수료(KRW): {total_fees:,.0f}, 수익금(KRW): {profit:,.0f}, 수익률(%): {profit_ratio:.2f}"
    send_slack_message('#coinautotade', settlement_msg)


def get_total_investment_amount():
    # Fetch current KRW balance
    krw_balance = upbit.get_balance("KRW")
    
    # List of coins to include in the total valuation
    coins = ["BTC", "SOL", "SHIB"]
    
    # Initialize total KRW value of coin holdings
    total_krw_value_of_coins = 0
    
    # Loop through each coin to calculate its KRW value and add it to the total
    for coin in coins:
        coin_balance = upbit.get_balance(coin)  # Get coin balance
        current_price = pyupbit.get_current_price(f"KRW-{coin}")  # Get current KRW price of the coin
        krw_value = coin_balance * current_price  # Calculate KRW value of holdings
        total_krw_value_of_coins += krw_value  # Add to total KRW value of coin holdings
    
    # Calculate total investment amount as 100% of the sum of KRW balance and total KRW value of coin holdings
    total_investment_amount = (krw_balance + total_krw_value_of_coins) * 1.00  # 100% of total value
    
    return total_investment_amount


def execute_buy(coin, amount, reason):
    if amount < 5000:
        print(f"{coin} 매수 금액이 최소 거래 금액인 5000 KRW 미만입니다. 건너뜁니다.")
        return None
    
    try:
        print(f"{amount:,.0f} KRW 만큼 {coin} 매수 시도 중. 이유: {reason}")
        result = upbit.buy_market_order(f"KRW-{coin}", amount)
        
        # 주문 결과 확인
        order_id = result['uuid']
        order_info = upbit.get_order(order_id)
        if order_info is not None and order_info['state'] == 'done':
            message = f"{coin} 매수 주문 성공: 사용된 KRW 잔액: {order_info['price']:,.0f}, 매수한 코인 수량: {order_info['executed_volume']:.6f}, 수수료: {order_info['paid_fee']:,.0f}"
            print(message)
            send_slack_message('#coinautotade', message)
        else:
            error_message = f"{coin} 매수 주문이 완료되지 않았습니다. 주문 상태: {order_info['state'] if order_info is not None else 'Unknown'}"
            print(error_message)
            send_slack_message('#coinautotade', error_message)
        
        return order_info
    except Exception as e:
        error_message = f"{coin} 매수 주문 실패: {str(e)}"
        print(error_message)
        send_slack_message('#coinautotade', error_message)
        return None

def execute_sell(coin, reason):
    coin_balance = upbit.get_balance(coin)
    current_price = pyupbit.get_current_price(f"KRW-{coin}")
    total_value = coin_balance * current_price
    
    if total_value < 5000:
        print(f"{coin} 매도 금액이 최소 거래 금액인 5000 KRW 미만입니다. 건너뜁니다.")
        return None
    
    try:
        print(f"{coin} 보유량 전량 매도 시도 중. 이유: {reason}")
        result = upbit.sell_market_order(f"KRW-{coin}", coin_balance)
        
        # 주문 결과 확인
        order_id = result['uuid']
        order_info = upbit.get_order(order_id)
        if order_info is not None and order_info['state'] == 'done':
            message = f"{coin} 매도 주문 성공: 매도한 코인 수량: {order_info['executed_volume']:.6f}, 받은 총 KRW: {order_info['price']:,.0f}, 수수료: {order_info['paid_fee']:,.0f}"
            print(message)
            send_slack_message('#coinautotade', message)
        else:
            error_message = f"{coin} 매도 주문이 완료되지 않았습니다. 주문 상태: {order_info['state'] if order_info is not None else 'Unknown'}"
            print(error_message)
            send_slack_message('#coinautotade', error_message)
        
        return order_info
    except Exception as e:
        error_message = f"{coin} 매도 주문 실패: {str(e)}"
        print(error_message)
        send_slack_message('#coinautotade', error_message)
        return None


if __name__ == "__main__":
    make_decision_and_execute()  # Execute once immediately upon script start

    # Schedule every 6 hours at 01 minute past the hour
    # schedule.every().hour.at(":01").do(make_decision_and_execute)
    schedule.every(6).hours.at(":01").do(make_decision_and_execute)

    while True:
        schedule.run_pending()
        time.sleep(1)
