#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客戶版基金淨值 + 風險等級 + 配息 + 六期績效抓取。
讀 funds_master.json，輸出 funds_client.json。由 GitHub Actions 每日執行。
資料來源：wb01/wr01 頁（淨值、RR、幣別、類型），wb03/wr03 頁（1/3/6/12/36/60月績效），
wr01 類的當日漲跌用 tBCDNavList。抓法見 reference_kgi_fund_scraping。"""
import re, json, os, time
import requests, urllib3
from datetime import datetime, timedelta, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
BASE = "https://kgilife.moneydj.com"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(BASE_DIR, "funds_master.json")
OUTPUT = os.path.join(BASE_DIR, "funds_client.json")
TW = timezone(timedelta(hours=8))
LIMIT = int(os.environ.get("LIMIT", "0"))  # 測試用：只跑前 N 檔

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": BASE + "/"})
S.verify = False

# 想要的六個期別 -> 頁面標題關鍵字
WANT = [("m1", "一個月"), ("m3", "三個月"), ("m6", "六個月"),
        ("m12", "一年"), ("m36", "三年"), ("m60", "五年")]
ALL_LABELS = ["一個月", "本月", "本季", "三個月", "六個月", "九個月", "一年", "二年", "三年", "五年"]


def text(url):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", S.get(url, timeout=25).content.decode("big5", errors="replace")))


def dist_flag(name):
    if re.search(r"累積|不配息|累计", name) or re.search(r"acc", name, re.I):
        return "未配息"
    if re.search(r"配息|月配|季配|雙月配|年配|分派|收益分配|月退|dist", name, re.I):
        return "配息"
    return "未配息"


def parse_meta(sec, code, tf):
    """meta 頁：RR、類型、（wb01 另含當日淨值/漲跌/日期）。"""
    t = text(f"{BASE}/{sec}?a={code}-{tf}")
    rr = (re.search(r"風險報酬等級\s*(RR\d)", t) or [0, None])[1]
    typ = (re.search(r"投資標的\s*(\S+)", t) or [0, None])[1]
    m = re.search(r"(\d{4}/\d{2}/\d{2})\s+([\d,]+\.\d+)\s+(-?\d+\.\d+)", t)  # wb01 直出
    nav = pct = date = None
    if m:
        nav, pct, date = float(m.group(2).replace(",", "")), float(m.group(3)), m.group(1)
    return rr, typ, nav, pct, date


def parse_perf(sec, code, tf):
    """perf 頁（wb03/wr03）：動態對應標題，取 1/3/6/12/36/60 月。"""
    perf_sec = sec.replace("01.djhtm", "03.djhtm")
    t = text(f"{BASE}/{perf_sec}?a={code}-{tf}")
    # 取連續期別標題
    hm = re.search(r"(一個月(?:\s+(?:" + "|".join(ALL_LABELS[1:]) + r"))+)", t)
    if not hm:
        return {}
    labels = hm.group(1).split()
    seg = t[hm.end():]
    nums = re.findall(r"-?\d+\.\d+", seg)[:len(labels)]
    if len(nums) < len(labels):
        return {}
    label_val = {lab: float(n) for lab, n in zip(labels, nums)}
    out = {}
    for key, lab in WANT:
        if lab in label_val:
            out[key] = label_val[lab]
    return out


def nav_tbcd(code):
    t = datetime.now(TW); w = t - timedelta(days=25)
    b = f"{w.year}-{w.month}-{w.day}"; e = f"{t.year}-{t.month}-{t.day}"
    r = S.get(f"{BASE}/w/bcd/tBCDNavList.djbcd?a={code}&b=1&c={b}&d={e}", timeout=25).content.decode("big5", "replace")
    p = r.strip().split()
    if len(p) < 2:
        return None, None, None
    ds, ns = p[0].split(","), p[1].split(",")
    try:
        latest = float(ns[-1]); prev = float(ns[-2]) if len(ns) >= 2 else latest
        pct = (latest - prev) / prev * 100 if prev else 0.0
        d = ds[-1]
        return latest, pct, f"{d[:4]}/{d[4:6]}/{d[6:]}"
    except Exception:
        return None, None, None


def main():
    master = json.load(open(MASTER, encoding="utf-8"))
    if LIMIT:
        master = [m for m in master if m.get("navsrc")][:LIMIT]

    funds = []; ok = 0
    for i, m in enumerate(master, 1):
        rec = {"tf": m["tf"], "name": m["name"], "cur": m.get("cur", "OTHER"),
               "rr": None, "dist": dist_flag(m["name"]), "typ": None,
               "value": None, "pct": None, "date": None, "perf": {},
               "link": m["link"], "ok": False}
        src = m.get("navsrc")
        try:
            if src in ("wb01", "tbcd"):
                rr, typ, nav, pct, date = parse_meta(m["sec"], m["code"], m["tf"])
                rec["rr"] = rr; rec["typ"] = typ
                if src == "tbcd" and nav is None:
                    nav, pct, date = nav_tbcd(m["code"])
                if nav is not None:
                    rec.update(value=nav, pct=pct, date=date, ok=True); ok += 1
                rec["perf"] = parse_perf(m["sec"], m["code"], m["tf"])
        except Exception as ex:
            print(f"  err {m['tf']}: {ex}")
        funds.append(rec)
        if i % 30 == 0:
            print(f"  {i}/{len(master)} 已抓 {ok}")
        time.sleep(0.05)

    payload = {"updated_at": datetime.now(TW).strftime("%Y/%m/%d %H:%M"),
               "product": "凱基人壽 鑫鑫向榮", "total": len(funds), "priced": ok, "funds": funds}
    json.dump(payload, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"完成：{ok}/{len(funds)} 檔有淨值，已寫入 {OUTPUT}")


if __name__ == "__main__":
    main()
