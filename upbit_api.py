import pyupbit
import logging
import datetime
from config import UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY, EXCLUDE_COINS
from slack_bot import send_slack_message
from utils import log_trade

# PyUpbit 초기화
upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)

def get_balance(currency):
    balances = upbit.get_balances()
    for balance in balances:
        if balance['currency'] == currency:
            return float(balance['balance'])
    return 0

def get_current_price(ticker):
    try:
        return pyupbit.get_current_price(ticker)
    except pyupbit.errors.UpbitError as e:
        logging.error(f"Failed to get current price for {ticker}: {e}")
        send_slack_message("#ms-upbit", f"현재 가격 조회 실패: {ticker}")
        return None

def get_coin_value_in_krw(ticker):
    balance = get_balance(ticker.replace('KRW-', ''))
    current_price = get_current_price(ticker)
    return balance * current_price

def get_total_investment_amount():
    balances = upbit.get_balances()
    total_krw_value_of_coins = 0
    for balance in balances:
        ticker = f"KRW-{balance['currency']}"
        if balance['currency'] != 'KRW' and ticker not in EXCLUDE_COINS:
            current_price = get_current_price(ticker)
            if current_price is not None:
                total_krw_value_of_coins += float(balance['balance']) * current_price
    krw_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'KRW'), 0)
    total_investment_amount = (krw_balance + total_krw_value_of_coins) * 0.10 # 10% of total assets
    return total_investment_amount

def execute_trade(coin, action, investment_amount=None):
    krw_balance_before = get_balance("KRW")
    fee_krw = 0
    if action == "buy" and investment_amount is not None and investment_amount >= 5000:
        try:
            buy_response = upbit.buy_market_order(coin, investment_amount)
            if 'reserved_fee' in buy_response:
                fee_krw += float(buy_response['reserved_fee'])
            if buy_response is not None:
                krw_balance_after = krw_balance_before - investment_amount - fee_krw
                send_slack_message("#ms-upbit", f"{coin}에 대한 매수 주문 성공: 투자 금액 {investment_amount}, 매수 후 금액: {krw_balance_after}, 매수 진행 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                log_trade("매수", [coin], krw_balance_before, krw_balance_after)
            else:
                logging.error(f"{coin} 매수 주문 실패: {e}")
                send_slack_message("#ms-upbit", f"{coin} 매수 주문 실패: {e}")
        except Exception as e:
            logging.error(f"{coin} 매수 주문 실패: {e}")
            send_slack_message("#ms-upbit", f"{coin} 매수 주문 실패: {e}")
    elif action == "sell":
        coin_value_in_krw = get_coin_value_in_krw(coin)
        if coin_value_in_krw >= 5000:
            sell_response = upbit.sell_market_order(coin, get_balance(coin.replace('KRW-', '')))
            if 'reserved_fee' in sell_response:
                fee_krw = float(sell_response['reserved_fee'])
            if sell_response is not None:
                krw_balance_after = krw_balance_before + coin_value_in_krw - fee_krw
                send_slack_message("#ms-upbit", f"{coin}에 대한 매도 주문 성공: 매도 후 금액: {krw_balance_after}, 매도 진행 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                log_trade("매도", [coin], krw_balance_before, krw_balance_after)
            else:
                logging.error(f"{coin} 매도 주문 실패: {e}")
                send_slack_message("#ms-upbit", f"{coin} 매도 주문 실패: {e}")
        else:
            logging.warning(f"{coin} 매도 불가: 최소 거래 금액 미만. 현재 가치: {coin_value_in_krw} KRW")
            send_slack_message("#ms-upbit", f"{coin} 매도 불가: 보유 코인 원화 환산 가치 미달.")
    return fee_krw

def update_excluded_coins_and_notify():
    global EXCLUDE_COINS
    tickers = pyupbit.get_tickers(fiat="KRW", is_details=True)
    new_exclusions = []

    for ticker in tickers:
        if ticker['market_warning'] == 'CAUTION' and ticker['market'] not in EXCLUDE_COINS:
            new_exclusions.append(ticker['market'])
            EXCLUDE_COINS.append(ticker['market'])

    if new_exclusions:
        message = f"유의 종목 지정코인 투자 제외: {', '.join(new_exclusions)}"
        send_slack_message("#ms-upbit", message)
    else:
        print("새로운 유의 종목 없음")

def summarize_holdings():
    balances = upbit.get_balances()
    krw_balance = get_balance("KRW")
    holdings = {balance['currency']: float(balance['balance']) for balance in balances if balance['currency'] != 'KRW' and f"KRW-{balance['currency']}" not in EXCLUDE_COINS}
    holdings_summary = ", ".join([f"{coin}: {amount} 코인" for coin, amount in holdings.items()])
    return holdings_summary, krw_balance