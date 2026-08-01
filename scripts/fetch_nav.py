#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金淨值日報 - 資料抓取腳本
由 GitHub Actions 每日排程執行，抓取後輸出 data.json 供 PWA 前端讀取。
爬蟲邏輯沿用自 fund_notify.py（已於 LINE Bot 驗證）。
"""
import requests
import urllib3
import json
import os
from datetime import datetime, timedelta, timezone

try:
    import yfinance as yf
except ImportError:
    yf = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "funds_config.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "data.json")

TW_TZ = timezone(timedelta(hours=8))


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_yf_price(ticker):
    """透過 yfinance 取得最新價格與漲跌幅（ETF、美股、匯率）"""
    if yf is None:
        return None, None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="7d").dropna(subset=["Close"])
        if hist.empty:
            return None, None
        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else close
        if close != close or prev != prev:
            return None, None
        pct = (close - prev) / prev * 100 if prev else 0.0
        return close, pct
    except Exception as e:
        print(f"  yf error {ticker}: {e}")
        return None, None


def get_taiex():
    """從 TWSE 官方 API 取得台灣加權指數"""
    for delta in range(0, 6):
        d = (datetime.now(TW_TZ) - timedelta(days=delta)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date={d}&type=IND"
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            tables = res.json().get("tables", [])
            for table in tables:
                for row in table.get("data", []):
                    if row[0] == "發行量加權股價指數":
                        price = float(row[1].replace(",", ""))
                        pct = float(row[4])
                        pct = -abs(pct) if "color:green" in row[2] else abs(pct)
                        return price, pct
        except Exception:
            pass
    return get_yf_price("^TWII")


def get_fund_nav(fid):
    """從凱基人壽 MoneyDJ 取得全委基金淨值"""
    today = datetime.now(TW_TZ)
    wk = today - timedelta(days=10)
    b = f"{wk.year}-{wk.month}-{wk.day}"
    e = f"{today.year}-{today.month}-{today.day}"
    url = f"https://kgilife.moneydj.com/w/bcd/BCDFVNavList.djbcd?fid={fid}&bDate={b}&eDate={e}"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12, verify=False)
        parts = res.text.strip().split()
        if len(parts) < 2:
            return None, None, None
        dates = parts[0].split(",")
        navs = parts[1].split(",")
        latest = float(navs[-1])
        prev = float(navs[-2]) if len(navs) >= 2 else latest
        pct = (latest - prev) / prev * 100 if prev else 0.0
        d = dates[-1]
        return latest, pct, f"{d[:4]}/{d[4:6]}/{d[6:]}"
    except Exception as e:
        print(f"  fund error {fid}: {e}")
        return None, None, None


def get_investment_fund_nav(plan_id):
    """從凱基人壽 MoneyDJ 取得投資型保單基金淨值"""
    today = datetime.now(TW_TZ)
    wk = today - timedelta(days=10)
    b = f"{wk.year}-{wk.month}-{wk.day}"
    e = f"{today.year}-{today.month}-{today.day}"
    url = f"https://kgilife.moneydj.com/w/bcd/tBCDNavList.djbcd?a={plan_id}&b=1&c={b}&d={e}"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12, verify=False)
        parts = res.text.strip().split()
        if len(parts) < 2:
            return None, None, None
        dates = parts[0].split(",")
        navs = parts[1].split(",")
        latest = float(navs[-1])
        prev = float(navs[-2]) if len(navs) >= 2 else latest
        pct = (latest - prev) / prev * 100 if prev else 0.0
        d = dates[-1]
        return latest, pct, f"{d[:4]}/{d[4:6]}/{d[6:]}"
    except Exception as e:
        print(f"  inv fund error {plan_id}: {e}")
        return None, None, None


def item(name, value, pct, url=None, date=None, unit=None, ok=True):
    return {
        "name": name,
        "value": value,      # 數值（None 表示抓取失敗）
        "pct": pct,          # 漲跌百分比
        "url": url,
        "date": date,        # 淨值日期（基金專用）
        "unit": unit,        # 單位（點 / 元 / USD ...）
        "ok": ok,
    }


def main():
    config = load_config()
    sections = []

    # 台股 ETF / 指數
    etf = config.get("etf", {})
    if etf:
        rows = []
        for name, d in etf.items():
            ticker = d.get("ticker")
            unit = d.get("unit", "元")
            price, pct = get_taiex() if ticker == "^TWII" else get_yf_price(ticker)
            rows.append(item(name, price, pct, d.get("url"), unit=unit, ok=price is not None))
        sections.append({"title": "台股 ETF / 指數", "icon": "📈", "items": rows})

    # 美國指數
    us = config.get("us_etf", {})
    if us:
        rows = []
        for name, d in us.items():
            unit = d.get("unit", "USD")
            price, pct = get_yf_price(d.get("ticker"))
            rows.append(item(name, price, pct, d.get("url"), unit=unit, ok=price is not None))
        sections.append({"title": "美國四大指數", "icon": "🌎", "items": rows})

    # 凱基全委基金
    fund = config.get("fund", {})
    if fund:
        rows = []
        for name, d in fund.items():
            nav, pct, date = get_fund_nav(d.get("fund_id"))
            rows.append(item(name, nav, pct, d.get("url"), date=date, unit="", ok=nav is not None))
        sections.append({"title": "凱基人壽全委基金", "icon": "🏦", "items": rows})

    # 凱基投資型保單基金
    inv = config.get("investment_fund", {})
    if inv:
        rows = []
        for name, d in inv.items():
            nav, pct, date = get_investment_fund_nav(d.get("plan_id"))
            rows.append(item(name, nav, pct, d.get("url"), date=date, unit="", ok=nav is not None))
        sections.append({"title": "凱基投資型保單基金", "icon": "📋", "items": rows})

    # 匯率
    fx = config.get("exchange_rate", {})
    if fx:
        rows = []
        for name, d in fx.items():
            rate, pct = get_yf_price(d.get("ticker"))
            rows.append(item(name, rate, pct, d.get("url"), unit="", ok=rate is not None))
        sections.append({"title": "美元匯率", "icon": "💵", "items": rows})

    payload = {
        "updated_at": datetime.now(TW_TZ).strftime("%Y/%m/%d %H:%M"),
        "sections": sections,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total = sum(len(s["items"]) for s in sections)
    ok = sum(1 for s in sections for it in s["items"] if it["ok"])
    print(f"完成：{ok}/{total} 筆成功，已寫入 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
