#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客戶版基金淨值抓取：讀 funds_master.json，更新可抓的基金，輸出 funds_client.json。
由 GitHub Actions 每日執行。抓法見 reference：wb01 頁面直出 / wr01 用 tBCDNavList。"""
import re, json, os, time
import requests, urllib3
from datetime import datetime, timedelta, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
BASE = "https://kgilife.moneydj.com"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(BASE_DIR, "funds_master.json")
OUTPUT = os.path.join(BASE_DIR, "funds_client.json")
TW = timezone(timedelta(hours=8))

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": BASE + "/"})
S.verify = False


def get(url):
    return S.get(url, timeout=20).content.decode("big5", errors="replace")


def nav_wb01(sec, code, tf):
    """wb01 頁面伺服器直出最新淨值。"""
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(f"{BASE}/{sec}?a={code}-{tf}")))
    m = re.search(r"(\d{4}/\d{2}/\d{2})\s+([\d,]+\.\d+)\s+(-?\d+\.\d+)", txt)
    if not m:
        return None, None, None
    return float(m.group(2).replace(",", "")), float(m.group(3)), m.group(1)


def nav_tbcd(code):
    """wr01 類：tBCDNavList 回傳日期串+淨值串，取最後兩筆算漲跌。"""
    t = datetime.now(TW); w = t - timedelta(days=20)
    b = f"{w.year}-{w.month}-{w.day}"; e = f"{t.year}-{t.month}-{t.day}"
    r = get(f"{BASE}/w/bcd/tBCDNavList.djbcd?a={code}&b=1&c={b}&d={e}")
    parts = r.strip().split()
    if len(parts) < 2:
        return None, None, None
    ds = parts[0].split(","); ns = parts[1].split(",")
    try:
        latest = float(ns[-1]); prev = float(ns[-2]) if len(ns) >= 2 else latest
        pct = (latest - prev) / prev * 100 if prev else 0.0
        d = ds[-1]
        return latest, pct, f"{d[:4]}/{d[4:6]}/{d[6:]}"
    except Exception:
        return None, None, None


def main():
    with open(MASTER, "r", encoding="utf-8") as f:
        master = json.load(f)

    funds = []
    ok = 0
    for i, m in enumerate(master, 1):
        rec = {"tf": m["tf"], "name": m["name"], "cur": m.get("cur", "OTHER"),
               "value": None, "pct": None, "date": None, "link": m["link"], "ok": False}
        src = m.get("navsrc")
        try:
            if src == "wb01":
                v, p, d = nav_wb01(m["sec"], m["code"], m["tf"])
            elif src == "tbcd":
                v, p, d = nav_tbcd(m["code"])
            else:
                v = p = d = None
            if v is not None:
                rec.update(value=v, pct=p, date=d, ok=True); ok += 1
        except Exception as ex:
            print(f"  err {m['tf']}: {ex}")
        funds.append(rec)
        if i % 40 == 0:
            print(f"  {i}/{len(master)} 已抓 {ok}")
        time.sleep(0.05)

    payload = {
        "updated_at": datetime.now(TW).strftime("%Y/%m/%d %H:%M"),
        "product": "凱基人壽 鑫鑫向榮",
        "total": len(funds),
        "priced": ok,
        "funds": funds,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"完成：{ok}/{len(funds)} 檔有淨值，已寫入 {OUTPUT}")


if __name__ == "__main__":
    main()
