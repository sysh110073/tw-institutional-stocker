# -*- coding: utf-8 -*-
"""Track broker branch trading performance and next-day profit.

追蹤特定券商分點的交易績效，計算其持倉隔日的獲利情況。
包含「名人堂」篩選邏輯：找出勝率高且獲利豐厚的分點。
"""

import os
import json
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

# Target broker branches to track (原有保留)
TARGET_BROKERS = [
    "凱基-台北",
    "凱基-虎尾",
    "美林",
    "摩根士丹利",  # Morgan Stanley
    "摩根大通",    # JP Morgan
    "高盛",        # Goldman Sachs
    "瑞銀",        # UBS
    "元大-台北",
    "富邦-台北",
]

# Data directories
DATA_DIR = "data"
BROKER_DATA_DIR = os.path.join(DATA_DIR, "broker")
DOCS_DIR = os.path.join("docs", "data")


def ensure_dirs():
    """Ensure required directories exist."""
    os.makedirs(BROKER_DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)


def load_stock_prices(stock_code: str) -> pd.DataFrame:
    """
    Load stock price data for calculating next-day returns.
    """
    timeseries_path = os.path.join(DOCS_DIR, "timeseries", f"{stock_code}.json")
    
    if os.path.exists(timeseries_path):
        try:
            with open(timeseries_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # [FIXED] Handle both list (direct) and dict (wrapper) formats
            target_list = []
            if isinstance(data, list):
                target_list = data
            elif isinstance(data, dict):
                target_list = data.get("data", [])
            
            # Convert to DataFrame
            records = []
            for item in target_list:
                if isinstance(item, dict):
                    records.append({
                        "date": item.get("date"),
                        "close": item.get("close", 0),
                        "change_pct": item.get("change_pct", 0),
                    })
            return pd.DataFrame(records)
        except Exception as e:
            print(f"[WARN] Failed to load prices for {stock_code}: {e}")
            return pd.DataFrame()
    
    return pd.DataFrame()


def calculate_next_day_profit(
    broker_trades: pd.DataFrame,
    prices: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Calculate next-day profit/loss for broker trades.
    """
    if broker_trades.empty:
        return pd.DataFrame()
    
    results = []
    
    # Group by stock code
    for stock_code, stock_df in broker_trades.groupby("stock_code"):
        # Load prices if not provided
        if prices is None or prices.empty:
            stock_prices = load_stock_prices(str(stock_code))
        else:
            stock_prices = prices[prices.get("stock_code", "") == stock_code]
        
        if stock_prices.empty:
            continue
        
        # Create price lookup by date
        price_lookup = {}
        prev_date = None
        for _, row in stock_prices.iterrows():
            d = row["date"]
            price_lookup[d] = {
                "close": row.get("close", 0),
                "change_pct": row.get("change_pct", 0),
                "prev_date": prev_date
            }
            prev_date = d
        
        # Process each broker trade
        for _, trade in stock_df.iterrows():
            trade_date = trade["date"]
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.strftime("%Y-%m-%d")

            broker_name = trade["broker_name"]
            net_vol = trade["net_vol"]
            
            # Find next trading day's change
            next_day_change = 0.0
            close_price = 0.0
            
            # Try to find the next day's data (Fuzzy match for date format differences)
            dates_list = sorted(price_lookup.keys())
            matched_date_key = None
            
            # Simple direct match first
            if trade_date in price_lookup:
                matched_date_key = trade_date
            else:
                # Fallback: substring match (e.g. "2023-12-01" vs "12/01")
                for d in dates_list:
                    if (trade_date in d) or (d in trade_date):
                        matched_date_key = d
                        break
            
            if matched_date_key:
                # Get index of matched date
                try:
                    curr_idx = dates_list.index(matched_date_key)
                    if curr_idx + 1 < len(dates_list):
                        next_d = dates_list[curr_idx + 1]
                        next_day_change = price_lookup[next_d].get("change_pct", 0)
                        close_price = price_lookup[matched_date_key].get("close", 0)
                except ValueError:
                    pass

            # Calculate direction match
            direction_match = False
            if net_vol > 0 and next_day_change > 0:
                direction_match = True
            elif net_vol < 0 and next_day_change < 0:
                direction_match = True
            
            # Estimate profit (張 * 1000股 * 價格 * 漲跌幅%)
            estimated_profit = net_vol * 1000 * close_price * (next_day_change / 100.0)
            
            results.append({
                "date": trade_date,
                "stock_code": stock_code,
                "broker_name": broker_name,
                "net_vol": net_vol,
                "close_price": close_price,
                "next_day_change": next_day_change,
                "direction_match": direction_match,
                "estimated_profit": estimated_profit
            })
    
    return pd.DataFrame(results)


def aggregate_broker_performance(profit_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate broker performance statistics.
    """
    if profit_df.empty:
        return pd.DataFrame()
    
    results = []
    
    for broker_name, broker_df in profit_df.groupby("broker_name"):
        total_trades = len(broker_df)
        win_count = broker_df["direction_match"].sum()
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        total_profit = broker_df["estimated_profit"].sum()
        avg_profit = broker_df["estimated_profit"].mean()
        stocks_traded = broker_df["stock_code"].nunique()
        
        results.append({
            "broker_name": broker_name,
            "total_trades": total_trades,
            "win_count": int(win_count),
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 0), # Round to integer for easier reading
            "avg_profit": round(avg_profit, 2),
            "stocks_traded": stocks_traded
        })
    
    return pd.DataFrame(results).sort_values("win_rate", ascending=False)


def filter_target_brokers(broker_df: pd.DataFrame) -> pd.DataFrame:
    """Filter broker trades to only include target brokers."""
    if broker_df.empty:
        return broker_df
    
    mask = broker_df["broker_name"].apply(
        lambda x: any(target in x or x in target for target in TARGET_BROKERS)
    )
    
    return broker_df[mask].copy()


# ==========================================
# NEW: Hall of Fame Logic
# ==========================================

def filter_hall_of_fame_brokers(
    performance_df: pd.DataFrame, 
    min_trades: int = 0, 
    min_profit: float = -999999, 
    min_win_rate: float = 0.0
) -> pd.DataFrame:
    """
    Filter brokers based on strict performance criteria (Hall of Fame).
    
    Criteria:
    1. Total trades > min_trades (e.g., 10)
    2. Total profit > min_profit (e.g., 1,000,000)
    3. Win rate > min_win_rate (e.g., 50%)
    """
    if performance_df.empty:
        return pd.DataFrame()
        
    mask = (
        (performance_df["total_trades"] >= min_trades) &
        (performance_df["total_profit"] >= min_profit) &
        (performance_df["win_rate"] >= min_win_rate)
    )
    
    winners = performance_df[mask].copy()
    
    # Sort by Total Profit descending (The biggest winners first)
    return winners.sort_values("total_profit", ascending=False)


def analyze_history_for_winners(history_csv_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load history CSV, calculate profit for all trades, and identify winners.
    
    Returns:
        (performance_df, winners_df)
    """
    if not os.path.exists(history_csv_path):
        print(f"[WARN] History file not found: {history_csv_path}")
        return pd.DataFrame(), pd.DataFrame()

    print(f"Loading historical data from {history_csv_path} for analysis...")
    try:
        df_hist = pd.read_csv(history_csv_path)
    except Exception as e:
        print(f"[ERR] Failed to read history CSV: {e}")
        return pd.DataFrame(), pd.DataFrame()
    
    if df_hist.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Calculate profit for historical trades
    # Note: This might take time if history is large
    print(f"Calculating profits for {len(df_hist)} historical trades...")
    profit_df = calculate_next_day_profit(df_hist)
    
    if profit_df.empty:
        print("[WARN] Could not calculate profits (missing price data?).")
        return pd.DataFrame(), pd.DataFrame()

    performance = aggregate_broker_performance(profit_df)
    winners = filter_hall_of_fame_brokers(performance)
    
    return performance, winners


def track_target_brokers(
    stock_codes: list[str],
    save_results: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Track target broker performance across multiple stocks.
    """
    from fetch_broker_data import fetch_multiple_stocks, close_browser
    
    ensure_dirs()
    
    print(f"Fetching broker data for {len(stock_codes)} stocks...")
    all_trades = fetch_multiple_stocks(stock_codes, delay=1.5)
    
    if all_trades.empty:
        print("No broker trading data fetched")
        return pd.DataFrame(), pd.DataFrame()
    
    print(f"Got {len(all_trades)} total trades")
    
    target_trades = filter_target_brokers(all_trades)
    print(f"Found {len(target_trades)} trades from target brokers")
    
    profit_df = calculate_next_day_profit(target_trades)
    performance = aggregate_broker_performance(profit_df)
    
    if save_results and not all_trades.empty:
        today = date.today().isoformat()
        
        trades_path = os.path.join(BROKER_DATA_DIR, f"broker_trades_{today}.csv")
        all_trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
        
        target_path = os.path.join(BROKER_DATA_DIR, f"target_broker_trades_{today}.csv")
        target_trades.to_csv(target_path, index=False, encoding="utf-8-sig")
        
        perf_path = os.path.join(BROKER_DATA_DIR, "broker_performance.json")
        if not performance.empty:
            performance.to_json(perf_path, orient="records", force_ascii=False, indent=2)
            print(f"Saved performance to {perf_path}")
    
    close_browser()
    return target_trades, performance


def export_broker_ranking(all_trades: pd.DataFrame, output_path: Optional[str] = None):
    """Export broker ranking for frontend display."""
    if all_trades.empty:
        return
    
    if output_path is None:
        output_path = os.path.join(DOCS_DIR, "broker_ranking.json")
    
    broker_stats = all_trades.groupby("broker_name").agg({
        "net_vol": "sum",
        "buy_vol": "sum",
        "sell_vol": "sum",
        "stock_code": "nunique",
    }).reset_index()
    
    broker_stats.columns = ["broker_name", "total_net_vol", "total_buy_vol", 
                            "total_sell_vol", "stocks_count"]
    
    broker_stats["abs_net_vol"] = broker_stats["total_net_vol"].abs()
    broker_stats = broker_stats.sort_values("abs_net_vol", ascending=False)
    
    result = {
        "updated": datetime.now().isoformat(),
        "data": broker_stats.drop(columns=["abs_net_vol"]).to_dict(orient="records")
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"Saved broker ranking to {output_path}")


if __name__ == "__main__":
    HOT_STOCKS = ["2330", "2454", "2317"]
    print("="*50)
    print("Tracking target broker performance...")
    print("="*50)
    trades, performance = track_target_brokers(HOT_STOCKS)
    if not trades.empty:
        print("\n--- Target Broker Trades ---")
        print(trades.to_string())
    if not performance.empty:
        print("\n--- Performance Summary ---")
        print(performance.to_string())