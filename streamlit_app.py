import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import pyupbit
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "trading_decisions.sqlite")

def load_data(ticker):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, decision, percentage, reason, coin_balance, krw_balance, coin_avg_buy_price, coin_price FROM decisions WHERE ticker = ? ORDER BY timestamp", (ticker,))
        decisions = cursor.fetchall()
        df = pd.DataFrame(decisions, columns=['timestamp', 'decision', 'percentage', 'reason', 'coin_balance', 'krw_balance', 'coin_avg_buy_price', 'coin_price'])
        df['ticker'] = ticker
        return df

def get_latest_state(db_path):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, MAX(timestamp) AS max_timestamp FROM decisions GROUP BY ticker")
        latest_timestamps = cursor.fetchall()
        total_krw_balance = 0
        total_coin_balance = {'BTC': 0.0, 'SOL': 0.0, 'XRP': 0.0}
        for ticker, max_timestamp in latest_timestamps:
            cursor.execute("SELECT coin_balance, krw_balance FROM decisions WHERE ticker = ? AND timestamp = ? LIMIT 1", (ticker, max_timestamp))
            row = cursor.fetchone()
            coin_balance = row[0]
            krw_balance = row[1]
            total_krw_balance = krw_balance
            total_coin_balance[ticker.split('-')[1]] = coin_balance
        return total_krw_balance, total_coin_balance

def main():
    st.set_page_config(layout="wide")
    st.title("실시간 비트코인/솔라나/리플 GPT 자동매매 기록")
    st.write("---")

    tickers = ["KRW-BTC", "KRW-SOL", "KRW-XRP"]
    total_start_value = 638506.36888986  # 전체 시작 원금을 설정합니다.
    total_current_value = 0  # 전체 현재 가치를 계산할 변수

    all_dfs = []
    total_krw_balance, total_coin_balance = get_latest_state(DB_PATH)

    for ticker in tickers:
        df = load_data(ticker)
        if not df.empty:
            current_price = pyupbit.get_orderbook(ticker=ticker)['orderbook_units'][0]["ask_price"]
            latest_row = df.iloc[-1]
            coin_balance = latest_row['coin_balance']
            krw_balance = latest_row['krw_balance']
            coin_avg_buy_price = latest_row['coin_avg_buy_price']
            current_value = int(coin_balance * current_price + krw_balance)
            total_current_value += current_value  # 전체 현재 가치에 더합니다.

            time_diff = datetime.now() - pd.to_datetime(latest_row['timestamp'])
            days = time_diff.days
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60

            if coin_balance == 0:
                df['수익률'] = 0.0
            else:
                df['수익률'] = round((current_value - total_start_value) / total_start_value * 100, 2)

            df['현재 시각'] = datetime.now()
            df['투자기간'] = f"{days} 일 {hours} 시간 {minutes} 분"
            df['시작 원금'] = total_start_value
            df['현재 코인 가격'] = current_price
            df['현재 보유 현금'] = krw_balance
            df['현재 보유 코인'] = coin_balance
            df['매수 평균가격'] = coin_avg_buy_price
            df['현재 원화 가치 평가'] = current_value

            all_dfs.append(df)

    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.sort_values(by='timestamp')

    st.write("**거래 내역**")
    st.dataframe(combined_df)

    total_current_value = total_krw_balance
    for ticker, coin_balance in total_coin_balance.items():
        if coin_balance > 0:
            current_price = pyupbit.get_orderbook(f"KRW-{ticker}")['orderbook_units'][0]["ask_price"]
            total_current_value += coin_balance * current_price

    st.write(f"현재 보유 현금: {total_krw_balance} 원")
    st.write(f"현재 보유 BTC: {total_coin_balance['BTC']}")
    st.write(f"현재 보유 SOL: {total_coin_balance['SOL']}")
    st.write(f"현재 보유 XRP: {total_coin_balance['XRP']}")

    st.header(f"전체 수익률: {round((total_current_value - total_start_value) / total_start_value * 100, 2)}%")
    st.write(f"전체 현재 가치: {total_current_value} 원")

if __name__ == '__main__':
    main()