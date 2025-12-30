# -*- coding: utf-8 -*-
"""
build_stock_three_inst_latest.py

功能：
1. 讀取 docs/data/timeseries/ 下所有個股的歷史資料。
2. 提取每檔股票「最後 14 個交易日」的法人買賣超數據。
3. 打包成 docs/data/stock_three_inst_latest.json 供網頁前端繪圖。
"""

import os
import json
from datetime import datetime

# 設定路徑
DOCS_DIR = os.path.join("docs", "data")
TIMESERIES_DIR = os.path.join(DOCS_DIR, "timeseries")

def ensure_dirs():
    os.makedirs(DOCS_DIR, exist_ok=True)

def main():
    ensure_dirs()
    
    if not os.path.exists(TIMESERIES_DIR):
        print(f"[WARN] 找不到歷史資料資料夾: {TIMESERIES_DIR}")
        print("請先執行 python update_all.py 抓取數據。")
        return

    # 取得所有 .json 檔案
    files = [f for f in os.listdir(TIMESERIES_DIR) if f.endswith(".json")]
    print(f"[INFO] 正在處理 {len(files)} 檔股票的歷史趨勢...")

    summary_records = []

    for filename in files:
        code = filename.replace(".json", "")
        path = os.path.join(TIMESERIES_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # 相容性處理：有些舊格式可能是 dict，新格式是 list
            series = data if isinstance(data, list) else data.get("data", [])
            
            if not series: continue

            # 1. 確保資料按日期排序 (舊->新)
            # (假設日期格式為 YYYY-MM-DD)
            series.sort(key=lambda x: x.get("date", ""))

            # 2. 取出最新的一筆資料 (用於顯示目前數值)
            last_day = series[-1]

            # 3. 取出最後 14 天的歷史資料 (用於畫趨勢圖)
            # [-14:] 代表倒數 14 筆到最後，若不足 14 筆則全取
            recent_days = series[-14:]
            
            # 精簡化歷史數據 (只存前端需要的欄位，節省檔案大小)
            trend_history = []
            for day in recent_days:
                trend_history.append({
                    "d": day.get("date", "")[5:],     # 日期只留 MM-DD
                    "f": day.get("foreign_net", 0),   # 外資買賣超
                    "t": day.get("trust_net", 0),      # 投信買賣超
                    "z": day.get("dealer_net", 0)
                })

            # 4. 建構匯總資料
            rec = {
                "code": str(last_day.get("code", code)),
                "name": last_day.get("name", ""),
                "close": last_day.get("close", 0),
                "date": last_day.get("date", ""),
                
                # 最新籌碼數據
                "foreign_net": last_day.get("foreign_net", 0),
                "foreign_ratio": last_day.get("foreign_ratio", 0),
                "trust_net": last_day.get("trust_net", 0),
                "trust_ratio": last_day.get("trust_ratio", 0),
                "dealer_net": last_day.get("dealer_net", 0),
                "dealer_ratio": last_day.get("dealer_ratio", 0),
                
                # 歷史趨勢 (塞進去!)
                "history": trend_history
            }
            
            summary_records.append(rec)

        except Exception as e:
            # print(f"Error processing {code}: {e}")
            continue

    # 存檔
    output_path = os.path.join(DOCS_DIR, "stock_three_inst_latest.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary_records, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] 已生成匯總檔 (含14日趨勢): {output_path}")

if __name__ == "__main__":
    main()