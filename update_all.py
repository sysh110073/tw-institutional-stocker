# -*- coding: utf-8 -*-
"""Update & export Taiwan institutional holdings AND daily prices.

功能升級：
1. [Fix] 新增 clean_number 函式，解決 ValueError: could not convert string to float: '--' 問題。
2. 整合每日收盤行情與三大法人籌碼。
"""
import json
import os
import time
import random
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import numpy as np

# --- 設定 ---
DATA_DIR = "data"
DOCS_DIR = os.path.join("docs", "data")
TIMESERIES_DIR = os.path.join(DOCS_DIR, "timeseries")
INST_BASELINE_PATH = os.path.join(DATA_DIR, "inst_baseline.csv")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
}

def ensure_dirs():
    for p in (DATA_DIR, DOCS_DIR, TIMESERIES_DIR):
        os.makedirs(p, exist_ok=True)

def get_taipei_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Taipei"))

def get_last_trading_date():
    """取得最近的交易日"""
    d = get_taipei_now()
    if d.hour < 15:
        d -= timedelta(days=1)
    while d.weekday() > 4: 
        d -= timedelta(days=1)
    return d.date()

# ==========================================
# 0. 核心工具：數據清洗 (關鍵修正)
# ==========================================

def clean_number(x) -> float:
    """
    強健的數值轉換函式。
    處理：'--', '1,234', None, '', 'nan'
    """
    if x is None:
        return 0.0
    
    # 轉字串並移除空白與逗號
    s = str(x).strip().replace(',', '')
    
    # 處理常見的髒數據符號
    if s in ['--', '-', '', 'nan', 'null', 'None']:
        return 0.0
    
    try:
        return float(s)
    except ValueError:
        # 如果真的遇到奇怪的字串 (如 'N/A')，回傳 0.0 避免程式崩潰
        return 0.0

# ==========================================
# 1. 抓取價格 (MI_INDEX / Daily Quotes)
# ==========================================

def fetch_twse_prices(date_obj: date) -> pd.DataFrame:
    """上市股價"""
    date_str = date_obj.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_str}&type=ALLBUT0999&response=json"
    print(f"[TWSE] Fetching prices for {date_str}...")
    
    try:
        time.sleep(1.5)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        
        target_table = None
        if 'tables' in data:
            for table in data['tables']:
                if '成交股數' in table['fields']:
                    target_table = table
                    break
        
        if not target_table:
            return pd.DataFrame()
            
        df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
        df = df.rename(columns={'證券代號': 'code', '證券名稱': 'name', '收盤價': 'close'})
        df['market'] = 'TWSE'
        
        # 使用 clean_number 清洗收盤價
        df['close'] = df['close'].apply(clean_number)
        
        return df[['code', 'name', 'close', 'market']]
    except Exception as e:
        print(f"[ERROR] TWSE Price: {e}")
        return pd.DataFrame()

def fetch_tpex_prices(date_obj: date) -> pd.DataFrame:
    """上櫃股價"""
    mingguo_year = date_obj.year - 1911
    date_str = f"{mingguo_year}/{date_obj.month:02d}/{date_obj.day:02d}"
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={date_str}&o=json"
    print(f"[TPEX] Fetching prices for {date_str}...")
    
    try:
        time.sleep(1.5)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if 'aaData' not in data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data['aaData'])
        if len(df.columns) < 3:
            return pd.DataFrame()
            
        df = df.rename(columns={0: 'code', 1: 'name', 2: 'close'})
        df['market'] = 'TPEX'
        
        # 使用 clean_number 清洗收盤價
        df['close'] = df['close'].apply(clean_number)
        
        return df[['code', 'name', 'close', 'market']]
    except Exception as e:
        print(f"[ERROR] TPEX Price: {e}")
        return pd.DataFrame()

# ==========================================
# 2. 抓取籌碼 (三大法人)
# ==========================================

def fetch_twse_inst(date_obj: date) -> pd.DataFrame:
    """上市三大法人"""
    date_str = date_obj.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json"
    
    try:
        time.sleep(1.5)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get('stat') != 'OK': return pd.DataFrame()
        
        df = pd.DataFrame(data['data'], columns=data['fields'])
        df['code'] = df['證券代號']
        
        # 動態尋找欄位
        cols = df.columns
        foreign_col = next((c for c in cols if '外資' in c and '買賣超' in c), None)
        trust_col = next((c for c in cols if '投信' in c and '買賣超' in c), None)
        dealer_col = next((c for c in cols if '自營商' in c and '買賣超' in c and '避險' not in c), None)

        if foreign_col: df['foreign_net'] = df[foreign_col].apply(clean_number)
        if trust_col: df['trust_net'] = df[trust_col].apply(clean_number)
        if dealer_col: df['dealer_net'] = df[dealer_col].apply(clean_number)
        
        return df[['code', 'foreign_net', 'trust_net', 'dealer_net']].fillna(0)
    except Exception:
        return pd.DataFrame()

def fetch_tpex_inst(date_obj: date) -> pd.DataFrame:
    """上櫃三大法人"""
    mingguo_year = date_obj.year - 1911
    date_str = f"{mingguo_year}/{date_obj.month:02d}/{date_obj.day:02d}"
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&d={date_str}&o=json&se=EW&t=D"
    
    try:
        time.sleep(1.5)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if 'aaData' not in data: return pd.DataFrame()
        
        df = pd.DataFrame(data['aaData'])
        df = df.rename(columns={0: 'code', 10: 'foreign_net', 13: 'trust_net', 16: 'dealer_net'})
        
        for c in ['foreign_net', 'trust_net', 'dealer_net']:
            if c in df.columns:
                df[c] = df[c].apply(clean_number)
                
        return df[['code', 'foreign_net', 'trust_net', 'dealer_net']].fillna(0)
    except Exception:
        return pd.DataFrame()

# ==========================================
# 3. 核心更新邏輯
# ==========================================

def update_timeseries(today_date, df_merged):
    ensure_dirs()
    date_str = today_date.strftime('%Y-%m-%d')
    print(f"[INFO] Updating timeseries for {date_str}...")
    
    count = 0
    for _, row in df_merged.iterrows():
        code = str(row['code']).strip()
        if len(code) != 4: continue 
        
        file_path = os.path.join(TIMESERIES_DIR, f"{code}.json")
        
        records = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    records = content if isinstance(content, list) else content.get('data', [])
            except:
                pass
        
        if records and records[-1].get('date') == date_str:
            continue
            
        # 安全取得數值 (再次確認，雙重保險)
        close_price = clean_number(row.get('close', 0))
        
        new_rec = {
            "date": date_str,
            "code": code,
            "name": row['name'],
            "market": row.get('market', ''),
            "close": close_price,
            "foreign_net": clean_number(row.get('foreign_net', 0)),
            "trust_net": clean_number(row.get('trust_net', 0)),
            "dealer_net": clean_number(row.get('dealer_net', 0)),
            "foreign_ratio": 0.0, 
            "trust_ratio": 0.0,
            "dealer_ratio": 0.0,
            "three_inst_ratio": 0.0
        }
        
        records.append(new_rec)
        if len(records) > 120:
            records = records[-120:]
            
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        count += 1
        
    print(f"[SUCCESS] Updated {count} stocks.")

def main():
    target_date = get_last_trading_date()
    print(f"Target Date: {target_date}")
    
    # 1. 抓價格
    twse_price = fetch_twse_prices(target_date)
    tpex_price = fetch_tpex_prices(target_date)
    prices = pd.concat([twse_price, tpex_price], ignore_index=True)
    
    if prices.empty:
        print("[ERROR] No price data found. Is it a holiday?")
        return

    # 2. 抓籌碼
    twse_inst = fetch_twse_inst(target_date)
    tpex_inst = fetch_tpex_inst(target_date)
    insts = pd.concat([twse_inst, tpex_inst], ignore_index=True)
    
    # 3. 合併
    merged = pd.merge(prices, insts, on='code', how='left')
    
    # 4. 更新 JSON
    update_timeseries(target_date, merged)

if __name__ == "__main__":
    main()