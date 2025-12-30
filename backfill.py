# -*- coding: utf-8 -*-
"""
backfill.py (時光機腳本)
功能：自動補抓過去 N 天的歷史數據，修復因刪檔導致的空窗期。
"""
import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta, date

# --- 設定 ---
DATA_DIR = "data"
DOCS_DIR = os.path.join("docs", "data")
TIMESERIES_DIR = os.path.join(DOCS_DIR, "timeseries")
BACKFILL_DAYS = 14  # 要補抓幾天

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
}

def ensure_dirs():
    os.makedirs(TIMESERIES_DIR, exist_ok=True)

def clean_number(x) -> float:
    if x is None: return 0.0
    s = str(x).strip().replace(',', '')
    if s in ['--', '-', '', 'nan', 'null', 'None']: return 0.0
    try:
        return float(s)
    except:
        return 0.0

# ==================== 爬蟲核心 (與 update_all.py 相同) ====================

def fetch_twse_prices(date_obj: date) -> pd.DataFrame:
    date_str = date_obj.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_str}&type=ALLBUT0999&response=json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        target_table = None
        if 'tables' in data:
            for table in data['tables']:
                if '成交股數' in table['fields']:
                    target_table = table
                    break
        if not target_table: return pd.DataFrame()
        df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
        df = df.rename(columns={'證券代號': 'code', '證券名稱': 'name', '收盤價': 'close'})
        df['market'] = 'TWSE'
        df['close'] = df['close'].apply(clean_number)
        return df[['code', 'name', 'close', 'market']]
    except: return pd.DataFrame()

def fetch_tpex_prices(date_obj: date) -> pd.DataFrame:
    mingguo_year = date_obj.year - 1911
    date_str = f"{mingguo_year}/{date_obj.month:02d}/{date_obj.day:02d}"
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={date_str}&o=json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if 'aaData' not in data: return pd.DataFrame()
        df = pd.DataFrame(data['aaData'])
        if len(df.columns) < 3: return pd.DataFrame()
        df = df.rename(columns={0: 'code', 1: 'name', 2: 'close'})
        df['market'] = 'TPEX'
        df['close'] = df['close'].apply(clean_number)
        return df[['code', 'name', 'close', 'market']]
    except: return pd.DataFrame()

def fetch_twse_inst(date_obj: date) -> pd.DataFrame:
    date_str = date_obj.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get('stat') != 'OK': return pd.DataFrame()
        df = pd.DataFrame(data['data'], columns=data['fields'])
        df['code'] = df['證券代號']
        cols = df.columns
        foreign_col = next((c for c in cols if '外資' in c and '買賣超' in c), None)
        trust_col = next((c for c in cols if '投信' in c and '買賣超' in c), None)
        dealer_col = next((c for c in cols if '自營商' in c and '買賣超' in c and '避險' not in c), None)
        if foreign_col: df['foreign_net'] = df[foreign_col].apply(clean_number)
        if trust_col: df['trust_net'] = df[trust_col].apply(clean_number)
        if dealer_col: df['dealer_net'] = df[dealer_col].apply(clean_number)
        return df[['code', 'foreign_net', 'trust_net', 'dealer_net']].fillna(0)
    except: return pd.DataFrame()

def fetch_tpex_inst(date_obj: date) -> pd.DataFrame:
    mingguo_year = date_obj.year - 1911
    date_str = f"{mingguo_year}/{date_obj.month:02d}/{date_obj.day:02d}"
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&d={date_str}&o=json&se=EW&t=D"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if 'aaData' not in data: return pd.DataFrame()
        df = pd.DataFrame(data['aaData'])
        df = df.rename(columns={0: 'code', 10: 'foreign_net', 13: 'trust_net', 16: 'dealer_net'})
        for c in ['foreign_net', 'trust_net', 'dealer_net']:
            if c in df.columns: df[c] = df[c].apply(clean_number)
        return df[['code', 'foreign_net', 'trust_net', 'dealer_net']].fillna(0)
    except: return pd.DataFrame()

# ==================== 存檔邏輯 ====================

def update_timeseries(target_date, df_merged):
    ensure_dirs()
    date_str = target_date.strftime('%Y-%m-%d')
    print(f"[SAVE] 正在寫入 {date_str} 的數據...")
    
    for _, row in df_merged.iterrows():
        code = str(row['code']).strip()
        if len(code) != 4: continue
        
        file_path = os.path.join(TIMESERIES_DIR, f"{code}.json")
        records = []
        
        # 讀取舊檔
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    records = content if isinstance(content, list) else content.get('data', [])
            except: pass
        
        # 檢查重複 (若已存在該日資料則跳過)
        if records and records[-1].get('date') == date_str:
            continue
            
        # 插入新資料
        new_rec = {
            "date": date_str,
            "code": code,
            "name": row['name'],
            "market": row.get('market', ''),
            "close": clean_number(row.get('close', 0)),
            "foreign_net": clean_number(row.get('foreign_net', 0)),
            "trust_net": clean_number(row.get('trust_net', 0)),
            "dealer_net": clean_number(row.get('dealer_net', 0)),
            "foreign_ratio": 0.0, "trust_ratio": 0.0, "dealer_ratio": 0.0, "three_inst_ratio": 0.0
        }
        
        records.append(new_rec)
        # 按日期排序，確保歷史順序正確
        records.sort(key=lambda x: x['date'])
        
        # 寫入
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

def main():
    print(f"=== 啟動時光機：開始補抓過去 {BACKFILL_DAYS} 天數據 ===")
    
    # 產生日期清單 (由舊到新)
    today = date.today()
    date_list = []
    for i in range(BACKFILL_DAYS, -1, -1): # 包含今天
        d = today - timedelta(days=i)
        if d.weekday() <= 4: # 排除週末 (0=週一, 4=週五)
            date_list.append(d)
    
    print(f"預計補抓日期: {[d.strftime('%Y-%m-%d') for d in date_list]}")
    
    for d in date_list:
        print(f"\n[FETCH] 正在抓取 {d} ...")
        
        # 抓價格
        twse_price = fetch_twse_prices(d)
        tpex_price = fetch_tpex_prices(d)
        prices = pd.concat([twse_price, tpex_price], ignore_index=True)
        
        if prices.empty:
            print(f"[SKIP] {d} 可能是假日，無成交資料。")
            continue
            
        # 抓籌碼
        twse_inst = fetch_twse_inst(d)
        tpex_inst = fetch_tpex_inst(d)
        insts = pd.concat([twse_inst, tpex_inst], ignore_index=True)
        
        # 合併與存檔
        merged = pd.merge(prices, insts, on='code', how='left')
        update_timeseries(d, merged)
        
        # 休息一下，避免被證交所 Ban IP
        print("休息 5 秒...")
        time.sleep(5)
        
    print("\n=== 時光機任務完成！ ===")
    print("請務必執行 python build_stock_three_inst_latest.py 來更新網頁趨勢圖。")

if __name__ == "__main__":
    main()