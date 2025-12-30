# -*- coding: utf-8 -*-
"""
reset_data.py
功能：一鍵清除所有生成的數據檔案 (CSV, JSON) 與 Python 快取，讓專案回到初始狀態。
"""

import os
import shutil
import glob

# 定義要清空的資料夾 (只刪檔案，保留資料夾本身)
DIRS_TO_CLEAN = [
    os.path.join("data", "broker"),
    os.path.join("docs", "data", "timeseries"),
]

# 定義要刪除的特定生成檔案 (位於 docs/data 下的匯總檔)
FILES_TO_DELETE = [
    os.path.join("docs", "data", "broker_performance.json"),
    os.path.join("docs", "data", "broker_ranking.json"),
    os.path.join("docs", "data", "broker_trades_latest.json"),
    os.path.join("docs", "data", "stock_three_inst_latest.json"),
]

def clean_directory(dir_path):
    """刪除資料夾內的所有檔案"""
    if not os.path.exists(dir_path):
        print(f"[SKIP] 資料夾不存在: {dir_path}")
        return
    
    print(f"[CLEAN] 清理資料夾: {dir_path} ...")
    for filename in os.listdir(dir_path):
        file_path = os.path.join(dir_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path) # 刪除檔案
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path) # 刪除子資料夾
        except Exception as e:
            print(f"  [ERROR] 無法刪除 {file_path}: {e}")

def clean_pycache():
    """遞迴刪除所有的 __pycache__ 資料夾 (這是 Python 跑過的痕跡，刪除無害)"""
    print("[CLEAN] 清除 Python 快取 (__pycache__)...")
    for root, dirs, files in os.walk("."):
        for d in dirs:
            if d == "__pycache__":
                path = os.path.join(root, d)
                try:
                    shutil.rmtree(path)
                except Exception as e:
                    print(f"  [ERROR] 無法刪除 {path}: {e}")

def main():
    print("=== 開始清理專案數據 ===")
    
    # 1. 清理指定資料夾內容
    for d in DIRS_TO_CLEAN:
        clean_directory(d)
        
    # 2. 刪除指定匯總檔案
    for f in FILES_TO_DELETE:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"[DELETE] 刪除檔案: {f}")
            except Exception as e:
                print(f"  [ERROR] 無法刪除 {f}: {e}")
                
    # 3. 清除快取
    clean_pycache()
    
    print("=== 清理完成！現在是一個乾淨的空專案 ===")
    print("請重新執行 daily_run.bat 來抓取新數據。")

if __name__ == "__main__":
    main()