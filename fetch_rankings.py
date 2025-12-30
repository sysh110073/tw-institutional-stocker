# -*- coding: utf-8 -*-
"""Fetch daily top active stocks (Volume/Turnover) from TWSE & TPEX.

自動抓取台股當日「成交重心」，用於動態生成爬蟲目標清單。
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time

def get_last_trading_date():
    """取得最近的一個交易日 (簡單推算，若週末則往前推)"""
    d = datetime.now()
    # 如果是週末 (5=Sat, 6=Sun) 或 早上 14:00 前 (盤後資料未出)，則往前推
    if d.hour < 14: 
        d -= timedelta(days=1)
    
    while d.weekday() > 4: # 週末
        d -= timedelta(days=1)
    
    return d

def fetch_twse_rankings(rank_type='value', limit=50) -> pd.DataFrame:
    """
    抓取上市股票排行
    rank_type: 'volume' (成交量) or 'value' (成交值/金額)
    """
    date_str = get_last_trading_date().strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_str}&type=ALLBUT0999&response=json"
    
    try:
        # 加上 Headers 避免被擋
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if 'tables' not in data:
            print("[WARN] TWSE data empty or holiday.")
            return pd.DataFrame()
            
        # 通常 table[8] 或 table[9] 是個股行情，尋找包含 "成交股數" 的表
        target_table = None
        for table in data['tables']:
            if '成交股數' in table['fields']:
                target_table = table
                break
        
        if not target_table:
            return pd.DataFrame()
            
        df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
        
        # 清理數據
        df['code'] = df['證券代號'].astype(str)
        # 排除權證 (6碼) 與 特別股 (非數字或長度不對)
        df = df[df['code'].apply(lambda x: len(x) == 4 and x.isdigit())]
        
        # 轉換數值 (移除逗號)
        df['volume'] = df['成交股數'].str.replace(',', '').astype(float)
        df['turnover'] = df['成交金額'].str.replace(',', '').astype(float)
        
        return df[['code', 'volume', 'turnover']]
        
    except Exception as e:
        print(f"[ERROR] Fetch TWSE rankings failed: {e}")
        return pd.DataFrame()

def fetch_tpex_rankings(rank_type='value', limit=50) -> pd.DataFrame:
    """抓取上櫃股票排行"""
    date_str = get_last_trading_date().strftime('%Y/%m/%d')
    # 這是民國年，需轉換? TPEX API 其實接受西元
    # TPEX 盤後行情表
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={date_str}&o=json"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if 'aaData' not in data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data['aaData'])
        # TPEX 欄位通常是 index 0=代號, 8=成交股數, 9=成交金額 (需視 API 變動調整)
        # 這裡假設它是標準格式
        if len(df.columns) < 10:
            return pd.DataFrame()

        df = df.rename(columns={0: 'code', 8: 'volume', 9: 'turnover'})
        
        # 清理
        df['code'] = df['code'].astype(str)
        df = df[df['code'].apply(lambda x: len(x) == 4 and x.isdigit())]
        
        df['volume'] = df['volume'].astype(str).str.replace(',', '').astype(float)
        df['turnover'] = df['turnover'].astype(str).str.replace(',', '').astype(float)
        
        return df[['code', 'volume', 'turnover']]
        
    except Exception as e:
        print(f"[ERROR] Fetch TPEX rankings failed: {e}")
        return pd.DataFrame()

def get_daily_top_stocks(limit=30, criterion='turnover') -> list[str]:
    """
    取得當日熱門股票清單 (上市+上櫃)
    Args:
        limit: 返回數量
        criterion: 'turnover' (成交金額-推薦) 或 'volume' (成交量)
    """
    print("Fetching daily market rankings from TWSE & TPEX...")
    twse = fetch_twse_rankings()
    tpex = fetch_tpex_rankings()
    
    if twse.empty and tpex.empty:
        print("[WARN] No ranking data found. Using empty list.")
        return []
        
    # 合併上市櫃
    df = pd.concat([twse, tpex], ignore_index=True)
    
    # 排序
    if criterion == 'turnover':
        # 成交金額大代表資金都在這 (通常是權值股、飆股)
        df = df.sort_values('turnover', ascending=False)
    else:
        # 成交量大 (可能是低價股)
        df = df.sort_values('volume', ascending=False)
    
    top_list = df.head(limit)['code'].tolist()
    print(f"Top {limit} stocks by {criterion}: {top_list[:5]}...")
    return top_list

if __name__ == "__main__":
    # Test
    stocks = get_daily_top_stocks(20, 'turnover')
    print("Result:", stocks)