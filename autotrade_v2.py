import os
from dotenv import load_dotenv
load_dotenv()
import pyupbit
import pandas as pd
import pandas_ta as ta
import json
from openai import OpenAI
import schedule
import time
import requests
from datetime import datetime
import sqlite3
import argparse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))
slack_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'))


def send_slack_message(channel, message, order_info=None, coin=None, is_buy=True):
    try:
        if order_info and coin:
            if is_buy:
                message_str = f"{coin} 매수 주문 성공: 사용된 KRW 잔액: {str(order_info['price'])}, 매수한 코인 수량: {str(order_info['executed_volume'])}, 수수료: {str(order_info['reserved_fee'])}"
            else:
                message_str = f"{coin} 매도 주문 성공: 매도한 코인 수량: {str(order_info['executed_volume'])}, 받은 총 KRW: {str(order_info['price'])}, 수수료: {str(order_info['reserved_fee'])}"
        else:
            message_str = str(message)
        slack_client.chat_postMessage(channel=channel, text=message_str)
        print(f"{channel}에 메시지 전송 완료: {message_str}")
    except SlackApiError as e:
        print(f"슬랙 메시지 전송 실패: {e.response['error']}")


def initialize_db(db_path='trading_decisions.sqlite'):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                ticker TEXT,
                decision TEXT,
                percentage REAL,
                reason TEXT,
                coin_balance REAL,
                krw_balance REAL,
                coin_avg_buy_price REAL,
                coin_price REAL
            );
        ''')
        conn.commit()

def save_decision_to_db(ticker, decision, current_status):
    db_path = 'trading_decisions.sqlite'
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
    
        # Parsing current_status from JSON to Python dict
        status_dict = json.loads(current_status)
        current_price = pyupbit.get_orderbook(ticker)['orderbook_units'][0]["ask_price"]
        
        # Preparing data for insertion
        data_to_insert = (
            ticker,
            decision.get('decision'),
            decision.get('percentage', 100),  # Defaulting to 100 if not provided
            decision.get('reason', ''),  # Defaulting to an empty string if not provided
            status_dict.get('coin_balance'),
            status_dict.get('krw_balance'),
            status_dict.get('coin_avg_buy_price'),
            current_price
        )
        
        # Inserting data into the database
        cursor.execute('''
            INSERT INTO decisions (timestamp, ticker, decision, percentage, reason, coin_balance, krw_balance, coin_avg_buy_price, coin_price)
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_to_insert)
    
        conn.commit()

def fetch_last_decisions(ticker, db_path='trading_decisions.sqlite', num_decisions=10):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, decision, percentage, reason, coin_balance, krw_balance, coin_avg_buy_price FROM decisions
            WHERE ticker = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (ticker, num_decisions))
        decisions = cursor.fetchall()

        if decisions:
            formatted_decisions = []
            for decision in decisions:
                # Converting timestamp to milliseconds since the Unix epoch
                ts = datetime.strptime(decision[0], "%Y-%m-%d %H:%M:%S")
                ts_millis = int(ts.timestamp() * 1000)
                
                formatted_decision = {
                    "timestamp": ts_millis,
                    "decision": decision[1],
                    "percentage": decision[2],
                    "reason": decision[3],
                    "coin_balance": decision[4],
                    "krw_balance": decision[5],
                    "coin_avg_buy_price": decision[6]
                }
                formatted_decisions.append(str(formatted_decision))
            return "\n".join(formatted_decisions)
        else:
            return "No decisions found."

def get_current_status(ticker):
    orderbook = pyupbit.get_orderbook(ticker)
    current_time = orderbook['timestamp']
    coin_balance = 0
    krw_balance = 0
    coin_avg_buy_price = 0
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker.split('-')[1]:
            coin_balance = b['balance']
            coin_avg_buy_price = b['avg_buy_price']
        if b['currency'] == "KRW":
            krw_balance = b['balance']

    current_status = {'current_time': current_time, 'orderbook': orderbook, 'coin_balance': coin_balance, 'krw_balance': krw_balance, 'coin_avg_buy_price': coin_avg_buy_price}
    return json.dumps(current_status)


def fetch_and_prepare_data(ticker):
    # Fetch data
    df_daily = pyupbit.get_ohlcv(ticker, "day", count=30)
    df_hourly = pyupbit.get_ohlcv(ticker, interval="minute60", count=24)

    # Define a helper function to add indicators
    def add_indicators(df):
        # Moving Averages
        df['SMA_3'] = ta.sma(df['close'], length=3)
        df['SMA_5'] = ta.sma(df['close'], length=5)
        df['SMA_10'] = ta.sma(df['close'], length=10)
        df['SMA_20'] = ta.sma(df['close'], length=20)

        # Calculate and add EMAs for 3, 5, 10, and 20-day periods
        df['EMA_3'] = ta.ema(df['close'], length=3)
        df['EMA_5'] = ta.ema(df['close'], length=5)
        df['EMA_10'] = ta.ema(df['close'], length=10)
        df['EMA_20'] = ta.ema(df['close'], length=20)

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

    return json.dumps(combined_data)

def get_news_data():
    ### Get news data from SERPAPI
    url = "https://serpapi.com/search.json?engine=google_news&q=btc+or+sol+or+xrp&api_key=" + os.getenv("SERPAPI_API_KEY")

    result = "No news data available."

    try:
        response = requests.get(url)
        news_results = response.json()['news_results']

        simplified_news = []
        
        for news_item in news_results:
            # Check if this news item contains 'stories'
            if 'stories' in news_item:
                for story in news_item['stories']:
                    timestamp = int(datetime.strptime(story['date'], '%m/%d/%Y, %H:%M %p, %z %Z').timestamp() * 1000)
                    simplified_news.append((story['title'], story.get('source', {}).get('name', 'Unknown source'), timestamp))
            else:
                # Process news items that are not categorized under stories but check date first
                if news_item.get('date'):
                    timestamp = int(datetime.strptime(news_item['date'], '%m/%d/%Y, %H:%M %p, %z %Z').timestamp() * 1000)
                    simplified_news.append((news_item['title'], news_item.get('source', {}).get('name', 'Unknown source'), timestamp))
                else:
                    simplified_news.append((news_item['title'], news_item.get('source', {}).get('name', 'Unknown source'), 'No timestamp provided'))
        result = str(simplified_news)
    except Exception as e:
        print(f"Error fetching news data: {e}")

    return result

def fetch_fear_and_greed_index(limit=1, date_format=''):
    """
    Fetches the latest Fear and Greed Index data.
    Parameters:
    - limit (int): Number of results to return. Default is 1.
    - date_format (str): Date format ('us', 'cn', 'kr', 'world'). Default is '' (unixtime).
    Returns:
    - dict or str: The Fear and Greed Index data in the specified format.
    """
    base_url = "https://api.alternative.me/fng/"
    params = {
        'limit': limit,
        'format': 'json',
        'date_format': date_format
    }
    response = requests.get(base_url, params=params)
    myData = response.json()['data']
    resStr = ""
    for data in myData:
        resStr += str(data)
    return resStr

def get_instructions(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            instructions = file.read()
        return instructions
    except FileNotFoundError:
        print("File not found.")
    except Exception as e:
        print("An error occurred while reading the file:", e)

def analyze_data_with_gpt4(news_data, data_json, last_decisions, fear_and_greed, current_status):
    instructions_path = "instructions_v2.md"
    try:
        instructions = get_instructions(instructions_path)
        if not instructions:
            print("No instructions found.")
            return None

        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": news_data},
                {"role": "user", "content": data_json},
                {"role": "user", "content": last_decisions},
                {"role": "user", "content": fear_and_greed},
                {"role": "user", "content": current_status}
            ],
            response_format={"type":"json_object"}
        )
        advice = response.choices[0].message.content
        return advice
    except Exception as e:
        print(f"Error in analyzing data with GPT-4: {e}")
        return None

def execute_buy(ticker, percentage):
    print(f"Attempting to buy {ticker.split('-')[1]} with a percentage of KRW balance...")
    try:
        krw_balance = upbit.get_balance("KRW")
        amount_to_invest = krw_balance * (percentage / 100)
        if amount_to_invest > 5000:  # Ensure the order is above the minimum threshold
            result = upbit.buy_market_order(ticker, amount_to_invest * 0.9995)  # Adjust for fees
            print("Buy order successful:", result)
            send_slack_message('#coinautotade', "", order_info=result, coin=ticker.split('-')[1], is_buy=True)
    except Exception as e:
        print(f"Failed to execute buy order: {e}")
        send_slack_message('#coinautotade', str(e))

def execute_sell(ticker, percentage):
    print(f"Attempting to sell a percentage of {ticker.split('-')[1]}...")
    try:
        coin_balance = upbit.get_balance(ticker.split('-')[1])
        amount_to_sell = coin_balance * (percentage / 100)
        current_price = pyupbit.get_orderbook(ticker=ticker)['orderbook_units'][0]["ask_price"]
        if current_price * amount_to_sell > 5000:  # Ensure the order is above the minimum threshold
            result = upbit.sell_market_order(ticker, amount_to_sell)
            print("Sell order successful:", result)
            send_slack_message('#coinautotade', "", order_info=result, coin=ticker.split('-')[1], is_buy=False)
    except Exception as e:
        print(f"Failed to execute sell order: {e}")
        send_slack_message('#coinautotade', str(e))

def make_decision_and_execute():
    print("Making decisions and executing for all tickers...")
    try:
        news_data = get_news_data()
        data_json = {
            "KRW-BTC": fetch_and_prepare_data("KRW-BTC"),
            "KRW-SOL": fetch_and_prepare_data("KRW-SOL"),
            "KRW-XRP": fetch_and_prepare_data("KRW-XRP")
        }
        last_decisions = {
            "KRW-BTC": fetch_last_decisions("KRW-BTC"),
            "KRW-SOL": fetch_last_decisions("KRW-SOL"),
            "KRW-XRP": fetch_last_decisions("KRW-XRP")
        }
        fear_and_greed = fetch_fear_and_greed_index(limit=30)
        current_status = {
            "KRW-BTC": get_current_status("KRW-BTC"),
            "KRW-SOL": get_current_status("KRW-SOL"),
            "KRW-XRP": get_current_status("KRW-XRP")
        }
    except Exception as e:
        print(f"Error: {e}")
    else:
        max_retries = 5
        retry_delay_seconds = 5
        decision = None
        for attempt in range(max_retries):
            try:
                advice = analyze_data_with_gpt4(news_data, json.dumps(data_json), json.dumps(last_decisions), fear_and_greed, json.dumps(current_status))
                decision = json.loads(advice)
                break
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}. Retrying in {retry_delay_seconds} seconds...")
                time.sleep(retry_delay_seconds)
                print(f"Attempt {attempt + 2} of {max_retries}")
        if not decision:
            print("Failed to make a decision after maximum retries.")
            return
        else:
            try:
                for ticker, decision_data in decision.items():
                    percentage = decision_data.get('percentage', 100)

                    if decision_data.get('decision') == "buy":
                        execute_buy(ticker, percentage)
                    elif decision_data.get('decision') == "sell":
                        execute_sell(ticker, percentage)

                    save_decision_to_db(ticker, decision_data, current_status[ticker])
            except Exception as e:
                print(f"Failed to execute the decision or save to DB: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='GPT 자동매매 프로그램')
    parser.add_argument('--mode', type=str, default='normal', choices=['test', 'normal'], help='실행 모드 (test: 테스트 모드, normal: 일반 모드)')
    args = parser.parse_args()

    initialize_db()

    if args.mode == 'test':
        print("테스트 모드로 실행합니다.")
        schedule.every().minute.do(make_decision_and_execute)
    else:
        print("일반 모드로 실행합니다.")
        schedule.every().day.at("23:01").do(make_decision_and_execute)
        schedule.every().day.at("07:01").do(make_decision_and_execute)
        schedule.every().day.at("15:01").do(make_decision_and_execute)

    while True:
        schedule.run_pending()
        time.sleep(1)