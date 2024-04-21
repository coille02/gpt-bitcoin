import logging
from config import EXCLUDE_COINS
from data_analysis import get_average_noise_ratio, get_daily_data_based_on_10am

def select_coins(top_coins, n=3):
    filtered_coins = [coin for coin in top_coins if coin not in EXCLUDE_COINS]

    noise_ratios = [(ticker, get_average_noise_ratio(ticker)) for ticker in filtered_coins]
    noise_ratios = [nr for nr in noise_ratios if nr[1] is not None]
    sorted_by_noise = sorted(noise_ratios, key=lambda x: x[1])

    final_selection = []
    for coin, _ in sorted_by_noise:
        if is_price_above_ma(coin) and is_volume_above_ma(coin):
            final_selection.append(coin)
            if len(final_selection) == n:
                break

    return final_selection

def is_price_above_ma(ticker, days=5):
    df = get_daily_data_based_on_10am(ticker, days)
    if df is not None:
        ma = df['close'].rolling(window=days).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        return current_price > ma
    return False

def is_volume_above_ma(ticker, days=5):
    df = get_daily_data_based_on_10am(ticker, days+1)
    if df is not None:
        ma = df['volume'].rolling(window=days).mean().iloc[-2]
        previous_day_volume = df['volume'].iloc[-2]
        return previous_day_volume > ma
    return False

def calculate_coin_investment_amount(total_investment_amount, num_selected_coins, ama_score):
    if ama_score == 0 or num_selected_coins == 0:
        return 0
    base_investment_amount = total_investment_amount / num_selected_coins
    coin_investment_amount = base_investment_amount * ama_score
    return max(coin_investment_amount, 5000)

def calculate_investment_amount(coin, total_assets):
    ma_score = get_moving_average_score(coin)
    initial_allocation = total_assets / 3
    adjusted_allocation = initial_allocation * ma_score

    df = get_daily_data_based_on_10am(ticker, days=2)
    prev_day_range = (df['high'].iloc[-2] - df['low'].iloc[-2]) / df['close'].iloc[-2] * 100
    if prev_day_range == 0:
        management_rule_factor = 1
    else:
        management_rule_factor = 2 / prev_day_range

    final_investment = adjusted_allocation * min(management_rule_factor, 1)
    return final_investment