# -*- coding: utf-8 -*-
"""Update broker branch trading data and export statistics.

每日更新券商分點交易數據，從富邦 e-Broker 網站抓取主力進出資料。
此腳本可獨立執行或由 GitHub Actions 調用。

功能更新：
1. 抓取熱門股票的券商分點買賣超數據
2. [NEW] 自動略過今日已爬過的股票
3. 統計各券商分點的績效
4. 識別名人堂贏家 (Hall of Fame)
5. 追蹤名人堂贏家今日動向
6. 提供全部分點的彈性搜尋數據
"""

import argparse
import os
import json
import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

# 引入分析模組
from track_broker_profit import analyze_history_for_winners

# 數據目錄
DATA_DIR = "data"
BROKER_DATA_DIR = os.path.join(DATA_DIR, "broker")
DOCS_DIR = os.path.join("docs", "data")

# 熱門股票清單（預設抓取）
HOT_STOCKS = [
    # 權值股
    "2330",  # 台積電
    "2317",  # 鴻海
    "2454",  # 聯發科
    "2308",  # 台達電
    "2382",  # 廣達
    "2891",  # 中信金
    "2881",  # 富邦金
    "2882",  # 國泰金
    "2303",  # 聯電
    "3711",  # 日月光投控
    # 熱門股
    "2603",  # 長榮
    "2609",  # 陽明
    "2615",  # 萬海
    "2618",  # 長榮航
    "3037",  # 欣興
    "2345",  # 智邦
    "3006",  # 晶豪科
    "2379",  # 瑞昱
    "3034",  # 聯詠
    "2412",  # 中華電
]

# 目標追蹤券商（部分匹配）
TARGET_BROKERS = [
    "凱基", "美林", "摩根", "高盛", "瑞銀", 
    "野村", "大和", "麥格理", "元大", "富邦",
]


def get_all_stock_codes(limit: Optional[int] = None) -> list[str]:
    """
    從現有的 flows CSV 中取得所有股票代碼。
    若無 CSV 檔案（初次執行），則回傳內建的 HOT_STOCKS 清單。
    """
    codes = set()
    
    # 嘗試讀取本地 CSV
    has_data = False
    for csv_file in ["twse_flows.csv", "tpex_flows.csv"]:
        csv_path = os.path.join(DATA_DIR, csv_file)
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                if "code" in df.columns:
                    codes.update(df["code"].astype(str).unique())
                    has_data = True
            except Exception as e:
                print(f"Warning: Could not read {csv_file}: {e}")
    
    valid_codes = [c for c in codes if c.isdigit() and len(c) == 4]
    valid_codes.sort()
    
    # 如果完全沒資料，就改用內建清單，避免回傳空陣列
    if not valid_codes:
        print("[INFO] No local history found. Falling back to HOT_STOCKS list.")
        valid_codes = sorted(HOT_STOCKS)

    if limit:
        return valid_codes[:limit]
    return valid_codes


def ensure_dirs():
    """確保必要目錄存在"""
    os.makedirs(BROKER_DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)


def fetch_all_broker_data(stock_codes: list[str], delay: float = 1.5) -> pd.DataFrame:
    """抓取多支股票的券商分點數據"""
    from fetch_broker_data import fetch_broker_trading, close_browser
    
    all_data = []
    total = len(stock_codes)
    
    if total == 0:
        return pd.DataFrame()

    for i, code in enumerate(stock_codes, 1):
        print(f"[{i}/{total}] Fetching broker data for {code}...")
        try:
            df = fetch_broker_trading(code)
            if not df.empty:
                all_data.append(df)
                print(f"  -> Got {len(df)} records")
            else:
                print(f"  -> No data")
        except Exception as e:
            print(f"  -> Error: {e}")
        
        if i < total:
            time.sleep(delay)
    
    close_browser()
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


def filter_target_brokers(df: pd.DataFrame) -> pd.DataFrame:
    """過濾出目標券商的交易"""
    if df.empty:
        return df
    mask = df["broker_name"].apply(
        lambda x: any(target in str(x) for target in TARGET_BROKERS)
    )
    return df[mask].copy()


def aggregate_broker_stats(df: pd.DataFrame) -> pd.DataFrame:
    """彙總券商分點統計"""
    if df.empty:
        return pd.DataFrame()
    
    stats = df.groupby("broker_name").agg({
        "net_vol": ["sum", "mean"],
        "side": lambda x: (x == "buy").sum(),
        "stock_code": "nunique"
    })
    
    stats.columns = ["total_net_vol", "avg_net_vol", "buy_count", "stocks_traded"]
    stats = stats.reset_index()
    stats["sell_count"] = df.groupby("broker_name").apply(
        lambda x: (x["side"] == "sell").sum(), include_groups=False
    ).values
    
    stats["abs_net_vol"] = stats["total_net_vol"].abs()
    stats = stats.sort_values("abs_net_vol", ascending=False)
    stats = stats.drop(columns=["abs_net_vol"])
    
    return stats


def export_broker_ranking(df: pd.DataFrame, output_path: str):
    """匯出券商排名 JSON"""
    if df.empty:
        return
    result = {
        "updated": datetime.now().isoformat(),
        "data": df.to_dict(orient="records")
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved broker ranking to {output_path}")


def export_broker_trades(df: pd.DataFrame, output_path: str):
    """匯出今日分點交易明細 JSON"""
    if df.empty:
        return
    records = df.to_dict(orient="records")
    result = {
        "updated": datetime.now().isoformat(),
        "count": len(records),
        "data": records
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(records)} trades to {output_path}")


def export_target_broker_trades(df: pd.DataFrame, output_path: str):
    """匯出目標券商交易 JSON"""
    target_df = filter_target_brokers(df)
    if target_df.empty:
        print("No target broker trades found")
        return
    
    grouped = target_df.groupby("broker_name").apply(
        lambda g: g[["stock_code", "net_vol", "side", "pct", "rank"]].to_dict(orient="records"),
        include_groups=False
    ).to_dict()
    
    result = {
        "updated": datetime.now().isoformat(),
        "brokers": grouped
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved target broker trades to {output_path}")


def build_broker_history(new_trades: pd.DataFrame, history_path: str) -> pd.DataFrame:
    """累積券商歷史交易數據"""
    today = date.today().isoformat()
    new_trades = new_trades.copy()
    new_trades["full_date"] = today
    
    if os.path.exists(history_path):
        history = pd.read_csv(history_path)
        history = history[history["full_date"] != today]
        combined = pd.concat([history, new_trades], ignore_index=True)
    else:
        combined = new_trades
    
    if "full_date" in combined.columns:
        combined["full_date"] = pd.to_datetime(combined["full_date"])
        cutoff = datetime.now() - timedelta(days=60)
        combined = combined[combined["full_date"] >= cutoff]
        combined["full_date"] = combined["full_date"].dt.strftime("%Y-%m-%d")
    
    combined.to_csv(history_path, index=False, encoding="utf-8-sig")
    return combined


def export_broker_trends(history_df: pd.DataFrame, output_path: str):
    """匯出券商買賣超趨勢數據供前端繪圖"""
    if history_df.empty:
        return
    
    target_df = filter_target_brokers(history_df)
    if target_df.empty:
        return
    
    daily = target_df.groupby(["broker_name", "full_date"]).agg({
        "net_vol": "sum"
    }).reset_index()
    daily = daily.sort_values(["broker_name", "full_date"])
    
    brokers_data = {}
    for broker_name in daily["broker_name"].unique():
        broker_df = daily[daily["broker_name"] == broker_name].copy()
        broker_df = broker_df.sort_values("full_date")
        broker_df["cumulative"] = broker_df["net_vol"].cumsum()
        
        brokers_data[broker_name] = broker_df[["full_date", "net_vol", "cumulative"]].rename(
            columns={"full_date": "date"}
        ).to_dict(orient="records")
    
    result = {
        "updated": datetime.now().isoformat(),
        "brokers": brokers_data
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved broker trends to {output_path}")


# ==========================================
# Hall of Fame & Daily Summary Export
# ==========================================

def export_hall_of_fame_actions(
    today_trades: pd.DataFrame, 
    winners_df: pd.DataFrame, 
    output_path: str
):
    """Export the trading actions of the Hall of Fame brokers for today."""
    if winners_df.empty or today_trades.empty:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.now().isoformat(), "data": []}, f)
        return

    winner_names = set(winners_df["broker_name"].values)
    winner_actions = today_trades[today_trades["broker_name"].isin(winner_names)].copy()
    
    result_data = []
    
    for _, winner_row in winners_df.iterrows():
        b_name = winner_row["broker_name"]
        trades = winner_actions[winner_actions["broker_name"] == b_name]
        
        if not trades.empty:
            trade_list = []
            for _, t in trades.iterrows():
                trade_list.append({
                    "stock_code": t["stock_code"],
                    "net_vol": int(t["net_vol"]),
                    "side": t["side"],
                    "rank": int(t["rank"])
                })
            
            result_data.append({
                "broker_name": b_name,
                "stats": {
                    "win_rate": float(winner_row["win_rate"]),
                    "total_profit": float(winner_row["total_profit"]),
                    "total_trades": int(winner_row["total_trades"])
                },
                "today_actions": trade_list
            })
            
    result_data.sort(key=lambda x: x["stats"]["total_profit"], reverse=True)

    output = {
        "updated": datetime.now().isoformat(),
        "count": len(result_data),
        "data": result_data
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved Hall of Fame actions to {output_path}")


def export_all_broker_daily_summary(df: pd.DataFrame, output_path: str):
    """Export a summary of all brokers' activity today."""
    if df.empty:
        return
        
    grouped = df.groupby("broker_name")
    
    broker_map = {}
    for name, group in grouped:
        trades = group[["stock_code", "net_vol", "side"]].sort_values("net_vol", key=abs, ascending=False).to_dict(orient="records")
        broker_map[name] = trades
        
    output = {
        "updated": datetime.now().isoformat(),
        "brokers": broker_map
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved All Broker Daily Summary to {output_path}")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(description="更新券商分點交易數據")
    parser.add_argument("--all", action="store_true", help="抓取所有上市櫃股票")
    parser.add_argument("--top50", action="store_true", help="抓取前 50 支熱門股")
    parser.add_argument("--top100", action="store_true", help="抓取前 100 支熱門股")
    parser.add_argument("--limit", type=int, help="限制抓取的股票數量 (例如: 10)")
    parser.add_argument("--delay", type=float, default=1.5, help="每次請求間隔秒數")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Update Broker Trading Data")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    ensure_dirs()
    
    # 決定要抓取的股票清單
    if args.all:
        stock_codes = get_all_stock_codes()
        print(f"\n[MODE] Full crawl: {len(stock_codes)} stocks")
    elif args.top100:
        stock_codes = get_all_stock_codes(limit=100)
        print(f"\n[MODE] Top 100 stocks")
    elif args.top50:
        stock_codes = get_all_stock_codes(limit=50)
        print(f"\n[MODE] Top 50 stocks")
    elif args.limit:
        stock_codes = get_all_stock_codes(limit=args.limit)
        print(f"\n[MODE] Limit check: {len(stock_codes)} stocks")
    else:
        stock_codes = HOT_STOCKS
        print(f"\n[MODE] Hot stocks: {len(stock_codes)} stocks")
    
    # ==========================================
    # [NEW] 檢查今日是否已經有爬過的數據
    # ==========================================
    today = date.today().isoformat()
    csv_path = os.path.join(BROKER_DATA_DIR, f"broker_trades_{today}.csv")
    existing_df = pd.DataFrame()

    if os.path.exists(csv_path):
        print(f"\n[INFO] Found existing data for today: {csv_path}")
        try:
            # 讀取現有檔案，確保 stock_code 是字串格式
            existing_df = pd.read_csv(csv_path, dtype={'stock_code': str})
            
            if not existing_df.empty and "stock_code" in existing_df.columns:
                existing_codes = set(existing_df["stock_code"].unique())
                original_count = len(stock_codes)
                
                # 過濾掉已經在檔案裡的股票代碼
                stock_codes = [c for c in stock_codes if c not in existing_codes]
                
                print(f"[INFO] Skipped {original_count - len(stock_codes)} stocks (already fetched).")
                print(f"[INFO] Remaining to fetch: {len(stock_codes)} stocks.")
        except Exception as e:
            print(f"[WARN] Failed to read existing file, will re-fetch all. Error: {e}")
            existing_df = pd.DataFrame()

    # 1. 抓取分點數據 (只抓還沒抓過的)
    print(f"\nFetching broker data for {len(stock_codes)} stocks...")
    new_trades = fetch_all_broker_data(stock_codes, delay=args.delay)
    
    # 合併舊資料與新資料 (如果原本是空的，pd.concat 會直接用 new_trades)
    all_trades = pd.concat([existing_df, new_trades], ignore_index=True)

    if all_trades.empty:
        print("[WARN] No broker trades fetched (and no existing data), aborting.")
        return
    
    print(f"\nTotal records (Combined): {len(all_trades)}")
    
    # 2. 儲存完整數據到 CSV (覆蓋寫入，因為已經包含舊的了)
    all_trades.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved combined data to {csv_path}")
    
    # 3. 統計券商排名 (Basic Stats)
    broker_stats = aggregate_broker_stats(all_trades)
    print(f"\nBroker stats: {len(broker_stats)} brokers")
    
    # 4. 匯出原有 JSON
    export_broker_ranking(broker_stats, os.path.join(DOCS_DIR, "broker_ranking.json"))
    export_broker_trades(all_trades, os.path.join(DOCS_DIR, "broker_trades_latest.json"))
    export_target_broker_trades(all_trades, os.path.join(DOCS_DIR, "target_broker_trades.json"))
    
    # 5. 更新歷史數據 & 趨勢
    history_path = os.path.join(BROKER_DATA_DIR, "broker_history.csv")
    history_df = build_broker_history(all_trades, history_path)
    print(f"Broker history: {len(history_df)} records from {history_df['full_date'].nunique()} days")
    
    export_broker_trends(history_df, os.path.join(DOCS_DIR, "broker_trends.json"))
    
    # 6. 名人堂分析 & 彈性搜尋
    print("\n[ANALYSIS] Running Hall of Fame Analysis...")
    
    # 6.1 分析歷史找出贏家
    perf_df, winners_df = analyze_history_for_winners(history_path)
    
    print(f"  -> Analyzed {len(perf_df)} brokers from history.")
    print(f"  -> Identified {len(winners_df)} Hall of Fame Winners!")
    
    if not winners_df.empty:
        top_winner = winners_df.iloc[0]
        print(f"  -> Top Winner: {top_winner['broker_name']} (Profit: {top_winner['total_profit']:,.0f})")

    # 6.2 匯出贏家列表
    hof_list_path = os.path.join(DOCS_DIR, "hall_of_fame_list.json")
    with open(hof_list_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now().isoformat(),
            "data": winners_df.to_dict(orient="records")
        }, f, ensure_ascii=False, indent=2)

    # 6.3 匯出贏家今日動向 (Block 3)
    hof_actions_path = os.path.join(DOCS_DIR, "hall_of_fame_today.json")
    export_hall_of_fame_actions(all_trades, winners_df, hof_actions_path)

    # 6.4 匯出全市場分點搜尋數據 (Block 4)
    all_summary_path = os.path.join(DOCS_DIR, "all_broker_daily_summary.json")
    export_all_broker_daily_summary(all_trades, all_summary_path)

    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    # print(f"Stocks crawled: {len(stock_codes)}") # 這裡的 stock_codes 已經變少，顯示總數比較有意義
    print(f"Stocks in dataset: {all_trades['stock_code'].nunique()}")
    print(f"Total trades: {len(all_trades)}")
    print(f"Unique brokers: {all_trades['broker_name'].nunique()}")
    print("\n[INFO] update_broker.py completed successfully.")


if __name__ == "__main__":
    main()