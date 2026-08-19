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


# ---- 方向B：外部權威來源 MoneyDJ 補 link-only 基金的六期績效（只接受完全同名）----
MDJ_URL = "https://www.moneydj.com/FundSearchSVC/api/Data/SearchResult"
MDJ_FUND = "https://www.moneydj.com/funddj/ya/yp010000.djhtm?a="
ANNOT = ("本基金", "配息來源", "暫停", "停止", "原名稱", "適格", "交易所", "槓桿", "策略交易",
         "風險", "說明", "起暫", "本金", "適用", "持有", "環境", "治理")
CUR_KW = {"USD": "美元", "EUR": "歐元", "TWD": "台幣", "RMB": "人民幣", "JPY": "日圓",
          "GBP": "英鎊", "AUD": "澳幣", "ZAR": "南非幣"}


def _norm(s):
    s = (s or "").replace("（", "(").replace("）", ")").replace("－", "-").replace("—", "-").replace("　", "")
    def drop(m):
        inner = m.group(1)
        if any(k in inner for k in ANNOT) or len(inner) > 8 or re.search(r"\d{4}/\d", inner):
            return ""
        return m.group(0)
    s = re.sub(r"\(([^()]*)\)", drop, s)
    s = s.replace("累計", "累積").replace("累计", "累積")
    s = re.sub(r"-\s*JPM[^-(]*(\([^)]*\))", r"\1", s)
    s = re.sub(r"-\s*JPM[^-(]*", "", s)
    s = s.replace("股", "")
    return re.sub(r"[\-－\s]+", "", s).lower()


def _norm_nocur(s):
    return re.sub(r"\((?:美元|歐元|台幣|新臺幣|人民幣|日圓|英鎊|澳幣|南非幣|紐幣|港幣)[^)]*\)", "", _norm(s))


def enrich_with_moneydj(funds):
    from collections import defaultdict
    r = S.post(MDJ_URL, data=json.dumps({"pg": 0, "pc": 1, "rc": 10000, "dg": 0, "sa": 0, "z": 1}),
               headers={"Content-Type": "application/json", "Origin": "https://www.moneydj.com",
                        "Referer": "https://www.moneydj.com/funddjx/fundsearch.xdjhtm"}, timeout=60)
    data = r.json()["Data"]
    full = defaultdict(list); nocur = defaultdict(list)
    for d in data:
        full[_norm(d["V2"])].append(d); nocur[_norm_nocur(d["V2"])].append(d)
    fmap = {k: v[0] for k, v in full.items() if len({x["V1"] for x in v}) == 1}

    def to_f(x):
        try: return round(float(x), 2)
        except Exception: return None

    n = 0
    for f in funds:
        if f["ok"] or f["perf"]:
            continue
        d = fmap.get(_norm(f["name"]))
        if not d:  # 第二輪：去幣別 + 幣別確認
            cands = nocur.get(_norm_nocur(f["name"]), [])
            kw = CUR_KW.get(f.get("cur"))
            if kw:
                cands = [c for c in cands if kw in c["V2"]]
            if len({c["V1"] for c in cands}) == 1:
                d = cands[0]
        if d:
            perf = {"m1": to_f(d["V7"]), "m3": to_f(d["V8"]), "m6": to_f(d["V9"]),
                    "m12": to_f(d["V10"]), "m36": to_f(d["V12"]), "m60": to_f(d["V13"])}
            f["perf"] = {k: v for k, v in perf.items() if v is not None}
            f["date"] = d["V3"]; f["src"] = "moneydj"; f["link"] = MDJ_FUND + d["V1"]
            n += 1
    print(f"MoneyDJ 補進六期績效：{n} 檔")


def nav_fv(fid):
    """全委帳戶：BCDFVNavList 回傳長歷史序列，取最新淨值＋當日漲跌＋六期績效。"""
    t = datetime.now(TW); w = t - timedelta(days=2100)
    b = f"{w.year}-{w.month}-{w.day}"; e = f"{t.year}-{t.month}-{t.day}"
    r = S.get(f"{BASE}/w/bcd/BCDFVNavList.djbcd?fid={fid}&bDate={b}&eDate={e}", timeout=25).content.decode("big5", "replace")
    p = r.strip().split()
    if len(p) < 2:
        return None, None, None, {}
    ds = p[0].split(",")
    try:
        ns = [float(x) for x in p[1].split(",")]
    except Exception:
        return None, None, None, {}
    if not ns:
        return None, None, None, {}
    latest = ns[-1]; prev = ns[-2] if len(ns) >= 2 else latest
    pct = (latest - prev) / prev * 100 if prev else 0.0
    d = ds[-1]; date = f"{d[:4]}/{d[4:6]}/{d[6:]}"
    ld = datetime.strptime(ds[-1], "%Y%m%d")
    def pf(mm):
        tgt = ld - timedelta(days=30 * mm); best = None
        for dd, nn in zip(ds, ns):
            if datetime.strptime(dd, "%Y%m%d") <= tgt:
                best = nn
        return round((latest / best - 1) * 100, 2) if best else None
    perf = {k: pf(mm) for k, mm in [("m3", 3), ("m6", 6), ("m12", 12), ("m36", 36)]}
    try:
        perf["since"] = round((latest / ns[0] - 1) * 100, 2)
    except Exception:
        pass
    return latest, pct, date, {k: v for k, v in perf.items() if v is not None}


def add_since(funds):
    """從凱基基金快搜 SearchProductJSON 取「成立以來%」(V36)，依標的代碼(tf)加到 perf.since。"""
    url = "https://kgilife.moneydj.com/w/custom/djjson/SearchProductJSON.djjson?P1=chinalife&P2=False&P3=False&P4=False&"
    r = S.get(url, timeout=30).content.decode("big5", "replace")
    res = json.loads(r)["ResultSet"]["Result"]
    smap = {}
    for x in res:
        v40 = x.get("V40", ""); sep = "~" if "~" in v40 else "-"
        parts = v40.split(sep, 1)
        if len(parts) != 2:
            continue
        try:
            smap[parts[1]] = round(float(x.get("V36")), 2)
        except Exception:
            pass
    n = 0
    for f in funds:
        v = smap.get(f["tf"])
        if v is not None:
            f["perf"]["since"] = v; n += 1
    print(f"成立以來報酬：補 {n} 檔")


CURMAP = {"美元": "USD", "台幣": "TWD", "新臺幣": "TWD", "歐元": "EUR", "人民幣": "RMB",
          "日圓": "JPY", "澳幣": "AUD", "南非幣": "ZAR", "英鎊": "GBP"}


def fetch_sp():
    """凱基基金快搜 SearchProductJSON：淨值(V18)＋3/6/12/36月(V11-V15)＋成立以來(V36)＋幣別(V26)＋配息(V42)。"""
    url = "https://kgilife.moneydj.com/w/custom/djjson/SearchProductJSON.djjson?P1=chinalife&P2=False&P3=False&P4=False&"
    res = json.loads(S.get(url, timeout=30).content.decode("big5", "replace"))["ResultSet"]["Result"]
    def fn(v):
        try: return round(float(v), 2)
        except Exception: return None
    out = {}
    for x in res:
        v40 = x.get("V40", ""); sep = "~" if "~" in v40 else "-"; p = v40.split(sep, 1)
        if len(p) != 2:
            continue
        perf = {"m3": fn(x.get("V11")), "m6": fn(x.get("V12")), "m12": fn(x.get("V13")),
                "m36": fn(x.get("V15")), "since": fn(x.get("V36"))}
        out[p[1]] = {"nav": fn(x.get("V18")), "date": x.get("V1"),
                     "cur": CURMAP.get((x.get("V26") or "").strip()),
                     "dist": "配息" if (x.get("V42") or "").strip() not in ("", "無") else "未配息",
                     "perf": {k: v for k, v in perf.items() if v is not None}}
    return out


def main():
    master = json.load(open(MASTER, encoding="utf-8"))
    if LIMIT:
        master = master[:LIMIT]
    sp = fetch_sp()
    print("快搜標的數:", len(sp))

    funds = []; ok = 0
    for i, m in enumerate(master, 1):
        rec = {"tf": m["tf"], "name": m["name"], "cur": m.get("cur", "OTHER"),
               "rr": m.get("rr_csv"), "dist": dist_flag(m["name"]), "typ": None,
               "inception": m.get("inception"), "typ2": m.get("typ2"),
               "value": None, "pct": None, "date": None, "perf": {},
               "link": m["link"], "ok": False, "src": None, "prods": m.get("prods", [])}
        try:
            if m.get("navsrc") == "fv":   # 全委帳戶
                nav, pct, date, perf = nav_fv(m["code"])
                if nav is not None:
                    rec.update(value=nav, pct=pct, date=date, ok=True); ok += 1
                rec["perf"] = perf
            else:                          # 其餘：凱基基金快搜官方數字
                x = sp.get(m["tf"])
                if x:
                    if x["cur"]: rec["cur"] = x["cur"]
                    rec["dist"] = x["dist"]; rec["perf"] = x["perf"]
                    if x["nav"] is not None:
                        rec.update(value=x["nav"], date=x["date"], ok=True); ok += 1
        except Exception as ex:
            print(f"  err {m['tf']}: {ex}")
        funds.append(rec)
        time.sleep(0.02)

    perf_cnt = sum(1 for f in funds if f["perf"])
    products = sorted({p for f in funds for p in f.get("prods", [])})
    payload = {"updated_at": datetime.now(TW).strftime("%Y/%m/%d %H:%M"),
               "product": "凱基人壽 投資型保單", "products": products,
               "total": len(funds), "priced": ok, "perf_count": perf_cnt, "funds": funds}
    json.dump(payload, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"完成：{ok}/{len(funds)} 檔有淨值，已寫入 {OUTPUT}")


if __name__ == "__main__":
    main()
