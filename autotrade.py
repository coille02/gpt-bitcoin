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
        response = slack_client.chat_postMessage(channel=channel, text=message)
        print(f"Message sent to {channel}: {message}")
    except SlackApiError as e:
        print(f"Failed to send message to Slack: {e.response['error']}")



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
            # model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": data_json},
                {"role": "user", "content": current_status}
            ],
            stop=["\n"],
            response_format={"type":"json_object"}
        )
        # Print the response content to console
        # print("OpenAI GPT-4 Response:")
        # print(response)
        advice = json.loads(response.choices[0].message.content)
        
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
        send_slack_message('#coinautotade', error_message)  # Ensure the correct channel name
        return {}, {}


def make_decision_and_execute():
    print("Making decision and executing...")
    coins = ["BTC", "SOL", "SHIB"]
    data_json = fetch_and_prepare_data()  # Assume this provides the required data for analysis
    decisions, buying_ratios = analyze_data_with_gpt4(data_json)

    # Calculate total investable amount as 10% of the KRW balance
    total_investment_amount = get_total_investment_amount()

    for coin in coins:
        decision = decisions.get(coin, {}).get('decision', 'hold')
        reason = decisions.get(coin, {}).get('reason', '')
        ratio = buying_ratios.get(coin, 0)
        amount_to_invest = total_investment_amount * ratio

        if decision == 'buy' and amount_to_invest > 0:
            execute_buy(coin, amount_to_invest, reason)
        elif decision == 'sell':
            execute_sell(coin, reason)
        else:
            print(f"Holding {coin}: {reason}")


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
    
    # Calculate total investment amount as 50% of the sum of KRW balance and total KRW value of coin holdings
    total_investment_amount = (krw_balance + total_krw_value_of_coins) * 0.50
    
    return total_investment_amount


def execute_buy(coin, amount, reason):
    if amount < 5000:
        print(f"Buy amount for {coin} is below the minimum transaction amount of 5000 KRW. Skipping.")
        return
    
    try:
        print(f"Attempting to buy {coin} for {amount} KRW. Reason: {reason}")
        result = upbit.buy_market_order(f"KRW-{coin}", amount)
        
        # Simplify the message to include relevant information
        message = f"Buy order for {coin} successful: KRW balance used: {result['price']}, Number of coins purchased (estimated): {amount / float(result['price'])}"
        print(message)
        send_slack_message('#coinautotade', message)
    except Exception as e:
        error_message = f"Failed to execute buy order for {coin}: {e}"
        print(error_message)
        send_slack_message('#coinautotade', error_message)


def execute_sell(coin, reason):
    coin_balance = upbit.get_balance(coin)
    current_price = pyupbit.get_current_price(f"KRW-{coin}")
    total_value = coin_balance * current_price
    
    if total_value < 5000:
        print(f"Sell value for {coin} is below the minimum transaction amount of 5000 KRW. Skipping.")
        return
    
    try:
        print(f"Attempting to sell all holdings of {coin}. Reason: {reason}")
        result = upbit.sell_market_order(f"KRW-{coin}", coin_balance)
        
        # Simplify the message to include relevant information
        message = f"Sell order for {coin} successful: Number of coins sold: {result['volume']}, Total KRW received (estimated): {float(result['volume']) * current_price}"
        print(message)
        send_slack_message('#coinautotade', message)
    except Exception as e:
        error_message = f"Failed to execute sell order for {coin}: {e}"
        print(error_message)
        send_slack_message('#coinautotade', error_message)


if __name__ == "__main__":
    make_decision_and_execute()  # Execute once immediately upon script start

    # Schedule every 6 hours at 01 minute past the hour
    # schedule.every().hour.at(":01").do(make_decision_and_execute)
    schedule.every(6).hours.at(":01").do(make_decision_and_execute)

    while True:
        schedule.run_pending()
        time.sleep(1)
