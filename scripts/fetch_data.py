"""
VIX Regime Dashboard – Daten-Fetcher
Holt täglich: ^VIX, ^VVIX, ^GSPC via yfinance
Schreibt: docs/data.json UND docs/index.html (Daten direkt eingebettet)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
from datetime import datetime, date
import warnings
warnings.filterwarnings('ignore')


def fetch_ticker(symbol, period="3mo"):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    df.index = df.index.tz_localize(None)
    return df[["Close"]].rename(columns={"Close": symbol})


def compute_signals(df_vix):
    close = df_vix["^VIX"].dropna()
    if len(close) < 25:
        return {}
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = ma20 + 2 * bb_std
    bb_lower = ma20 - 2 * bb_std
    current_vix   = float(close.iloc[-1])
    current_ma10  = float(ma10.iloc[-1])
    current_ma20  = float(ma20.iloc[-1])
    current_bb_up = float(bb_upper.iloc[-1])
    current_bb_low= float(bb_lower.iloc[-1])
    vix_pct_above_ma20 = ((current_vix - current_ma20) / current_ma20) * 100
    if current_vix < 15:
        regime,regime_label,equity_pct = "KOMFORT","Komfort-Zone","80–100%"
    elif current_vix < 20:
        regime,regime_label,equity_pct = "NIEDRIG_NORMAL","Niedriger Normalbereich","70–85%"
    elif current_vix < 25:
        regime,regime_label,equity_pct = "NORMAL","Normalbereich","60–75%"
    elif current_vix < 30:
        regime,regime_label,equity_pct = "ERHOEHTE_SPANNUNG","Erhöhte Spannung","40–55%"
    elif current_vix < 35:
        regime,regime_label,equity_pct = "STRESS","Stress-Zone","20–40%"
    elif current_vix < 50:
        regime,regime_label,equity_pct = "KRISE","Krise","<20%"
    else:
        regime,regime_label,equity_pct = "PANIK","Panik / Systemkrise","0–10%"
    vix_above_ma10 = (close > ma10).astype(int)
    e1_streak = 0
    for i in range(len(vix_above_ma10)-1, max(len(vix_above_ma10)-10,-1), -1):
        if vix_above_ma10.iloc[i]==1: e1_streak+=1
        else: break
    above_bb = (close > bb_upper).astype(int)
    e3_streak = 0
    for i in range(len(above_bb)-1, max(len(above_bb)-5,-1), -1):
        if above_bb.iloc[i]==1: e3_streak+=1
        else: break
    vix_below_ma10 = (close < ma10).astype(int)
    r1_streak = 0
    for i in range(len(vix_below_ma10)-1, max(len(vix_below_ma10)-10,-1), -1):
        if vix_below_ma10.iloc[i]==1: r1_streak+=1
        else: break
    r1_active = r1_streak >= 3
    window_30d = close.iloc[-30:]
    ma20_30d = ma20.iloc[-30:]
    max_pct_above = float(((window_30d - ma20_30d) / ma20_30d * 100).max())
    r3_active = max_pct_above >= 30.0
    vix_30d_max = float(close.iloc[-30:].max())
    vix_30d_min = float(close.iloc[-30:].min())
    chart_dates = [str(d.date()) for d in close.index[-90:]]
    chart_vix   = [round(float(v),2) for v in close.iloc[-90:]]
    chart_ma10  = [round(float(v),2) if not np.isnan(v) else None for v in ma10.iloc[-90:]]
    chart_ma20  = [round(float(v),2) if not np.isnan(v) else None for v in ma20.iloc[-90:]]
    chart_bb_up = [round(float(v),2) if not np.isnan(v) else None for v in bb_upper.iloc[-90:]]
    chart_bb_lo = [round(float(v),2) if not np.isnan(v) else None for v in bb_lower.iloc[-90:]]
    return {
        "current_vix": round(current_vix,2), "current_ma10": round(current_ma10,2),
        "current_ma20": round(current_ma20,2), "current_bb_upper": round(current_bb_up,2),
        "current_bb_lower": round(current_bb_low,2), "vix_pct_above_ma20": round(vix_pct_above_ma20,1),
        "vix_30d_max": round(vix_30d_max,2), "vix_30d_min": round(vix_30d_min,2),
        "regime": regime, "regime_label": regime_label, "equity_pct": equity_pct,
        "r1_streak": r1_streak, "e1_streak": e1_streak,
        "r1_active": bool(r1_active), "e1_active": bool(e1_streak>=3),
        "e3_active": bool(e3_streak>=2), "r3_active": bool(r3_active),
        "max_pct_above_ma20_30d": round(max_pct_above,1),
        "chart_dates": chart_dates, "chart_vix": chart_vix, "chart_ma10": chart_ma10,
        "chart_ma20": chart_ma20, "chart_bb_upper": chart_bb_up, "chart_bb_lower": chart_bb_lo,
    }


def fetch_vvix():
    try:
        df = fetch_ticker("^VVIX", period="1mo")
        current = float(df["^VVIX"].iloc[-1])
        prev5   = float(df["^VVIX"].iloc[-6]) if len(df)>=6 else current
        trend   = "fällt" if current < prev5 else "steigt"
        r4_active = current < 120 and trend == "fällt"
        return {
            "current_vvix": round(current,2), "vvix_5d_ago": round(prev5,2),
            "vvix_trend": trend, "r4_active": bool(r4_active),
            "vvix_hist_dates": [str(d.date()) for d in df.index[-30:]],
            "vvix_hist_vals": [round(float(v),2) for v in df["^VVIX"].iloc[-30:]],
        }
    except Exception as e:
        return {"current_vvix": None, "r4_active": False}


def fetch_spy():
    try:
        df = fetch_ticker("^GSPC", period="3mo")
        close = df["^GSPC"].dropna()
        current_spy = float(close.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        pct_from_ma50 = ((current_spy - ma50) / ma50) * 100
        min_30d = float(close.iloc[-30:].min())
        min_30d_idx = int(close.iloc[-30:].argmin())
        days_since_low = 30 - min_30d_idx
        r5_hint = (days_since_low >= 5) and (current_spy > min_30d) and (pct_from_ma50 > -15)
        return {
            "current_spy": round(current_spy,1), "spy_ma50": round(ma50,1),
            "spy_pct_from_ma50": round(pct_from_ma50,1), "spy_30d_min": round(min_30d,1),
            "days_since_30d_low": int(days_since_low), "r5_hint": bool(r5_hint),
        }
    except Exception as e:
        return {"current_spy": None, "r5_hint": False}


def count_reentry(vix_data, vvix_data, spy_data):
    r1 = vix_data.get("r1_active", False)
    r3 = vix_data.get("r3_active", False)
    r4 = vvix_data.get("r4_active", False)
    r5 = spy_data.get("r5_hint", False)
    auto_count = sum([r1, r3, r4, r5])
    if not r1:
        signal,label,action = "NONE","Kein Signal — R1 nicht erfüllt","Abwarten. VIX muss 3 Tage unter MA10 schließen."
    elif auto_count == 1:
        signal,label,action = "WAIT","Zu früh — weitere Bestätigung nötig","R1 erfüllt, aber keine weiteren Bestätigungen. Beobachten."
    elif auto_count == 2:
        signal,label,action = "CAUTIOUS","Vorsichtiger Einstieg möglich","Erste kleine Tranche (10–15%). R2 manuell prüfen."
    elif auto_count == 3:
        signal,label,action = "BUY","Klares Re-Entry-Signal","Einstieg. Erste Tranche kaufen, zweite in 1 Woche."
    else:
        signal,label,action = "STRONG_BUY","Starkes Signal — Aggressiver Einstieg","Zwei Tranchen zügig aufbauen."
    return {"r1":r1,"r3":r3,"r4":r4,"r5_hint":r5,
            "auto_conditions_met":auto_count,"signal":signal,"signal_label":label,"action":action}


def build_html(data):
    """Baut die komplette index.html mit eingebetteten Daten."""
    v   = data["vix"]
    vv  = data["vvix"]
    spy = data["spy"]
    re  = data["reentry"]
    meta= data["meta"]

    # Regime-Farben
    rc = {
        "KOMFORT":           ("rgba(77,216,144,0.12)","rgba(77,216,144,0.4)","#4dd890"),
        "NIEDRIG_NORMAL":    ("rgba(77,216,144,0.08)","rgba(77,216,144,0.3)","#80e8b0"),
        "NORMAL":            ("rgba(240,192,96,0.10)","rgba(240,192,96,0.35)","#f0c060"),
        "ERHOEHTE_SPANNUNG": ("rgba(255,170,85,0.10)","rgba(255,170,85,0.35)","#ffaa55"),
        "STRESS":            ("rgba(255,112,112,0.10)","rgba(255,112,112,0.4)","#ff7070"),
        "KRISE":             ("rgba(255,112,112,0.12)","rgba(255,112,112,0.5)","#ff9090"),
        "PANIK":             ("rgba(220,60,60,0.15)","rgba(220,60,60,0.6)","#ffaaaa"),
    }.get(v["regime"], ("rgba(240,192,96,0.10)","rgba(240,192,96,0.35)","#f0c060"))

    sig_colors = {"NONE":"#ff7070","WAIT":"#ffaa55","CAUTIOUS":"#f0c060","BUY":"#4dd890","STRONG_BUY":"#80ffb8"}
    sig_color = sig_colors.get(re["signal"], "#ff7070")

    # Signal-Karten
    def sig_card(id_, active, title, detail, badge_text, is_manual=False):
        if is_manual:
            border = "border-color:rgba(240,192,96,0.4)"
            dot_color = "#f0c060"
            badge = f'<div class="sig-badge" style="color:#f0c060;margin-top:8px;font-size:11px">⚠ Manuell prüfen</div>'
        elif active:
            border = "border-color:rgba(77,216,144,0.4);background:rgba(77,216,144,0.05)"
            dot_color = "#4dd890"
            badge = f'<div class="sig-badge" style="color:#4dd890">✓ Erfüllt</div>'
        else:
            border = "opacity:0.7"
            dot_color = "#ff7070"
            badge = f'<div class="sig-badge" style="color:#ff7070">✗ Nicht erfüllt</div>'
        return f'''<div class="sig-card" style="{border}">
  <div class="sig-id"><div class="sig-dot" style="background:{dot_color}"></div>{id_}</div>
  <div class="sig-title">{title}</div>
  <div class="sig-detail">{detail}</div>
  {badge}
  <div class="sig-detail" style="margin-top:4px">{badge_text}</div>
</div>'''

    # JSON für Charts
    jv  = json.dumps(v["chart_vix"])
    jd  = json.dumps(v["chart_dates"])
    jm10= json.dumps(v["chart_ma10"])
    jm20= json.dumps(v["chart_ma20"])
    jbu = json.dumps(v["chart_bb_upper"])
    jbl = json.dumps(v["chart_bb_lower"])
    jvd = json.dumps(vv.get("vvix_hist_dates",[]))
    jvv = json.dumps(vv.get("vvix_hist_vals",[]))

    vix_vs_ma10_color = "#ff7070" if v["current_vix"] > v["current_ma10"] else "#4dd890"
    vix_vs_ma10_text  = "▲ über MA10" if v["current_vix"] > v["current_ma10"] else "▼ unter MA10"
    pct_sign = "+" if v["vix_pct_above_ma20"] >= 0 else ""
    pct_color = "#ff7070" if v["vix_pct_above_ma20"] > 0 else "#4dd890"
    bb_ok = v["current_vix"] < v["current_bb_upper"]
    bb_text = "✓ Unter BB-Oben" if bb_ok else "⚠ Über BB-Oben"
    bb_color = "#4dd890" if bb_ok else "#ff7070"
    vvix_trend_color = "#4dd890" if vv.get("vvix_trend") == "fällt" else "#ffaa55"

    r1_card = sig_card("R1 · PFLICHT", v["r1_active"], "VIX 3 Tage unter MA10",
        f'Streak: {v["r1_streak"]} / 3 Tage', "Pflichtbedingung für Wiedereinstieg")
    r2_card = sig_card("R2 · MANUELL", None, "VIX Futures in Contango",
        '<a href="https://www.cboe.com/tradable-products/vix/term-structure/" target="_blank" style="color:#70b8ff">→ cboe.com/vix/term-structure</a>', "", is_manual=True)
    r3_card = sig_card("R3", v["r3_active"], "VIX 30%+ über MA20 gewesen",
        f'Max. Überdehnung (30d): {v["max_pct_above_ma20_30d"]}%', "≥30% = erfüllt")
    r4_card = sig_card("R4", vv.get("r4_active", False), "VVIX fällt &lt; 120",
        f'VVIX: {vv.get("current_vvix","?")} · Trend: {vv.get("vvix_trend","?")}', "Frühes Beruhigungssignal")
    r5_card = sig_card("R5 · HINWEIS", spy.get("r5_hint", False), "S&amp;P 500 technische Basis",
        f'Tage seit 30d-Tief: {spy.get("days_since_30d_low","?")}', "Schätzung — Chartanalyse empfohlen")

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIX Regime Dashboard — meine-geldseite.de</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#1a2540; --s1:#223058; --border:#2e4070; --border2:#3a5080;
  --gold:#f0c060; --green:#4dd890; --red:#ff7070; --orange:#ffaa55;
  --blue:#70b8ff; --text:#c8d8f0; --muted:#7090b8; --white:#e8f0ff;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;font-size:15px;line-height:1.65}}
.topbar{{background:#1a2540;border-bottom:1px solid var(--border);padding:0 28px;height:52px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 1px 8px rgba(0,0,0,0.3)}}
.brand{{font-family:'Syne',sans-serif;font-size:15px;font-weight:800;color:var(--gold)}}
.brand span{{color:var(--white)}}
.upd{{font-size:11px;color:var(--muted)}}
.container{{max-width:1180px;margin:0 auto;padding:0 24px}}
.pp{{padding:24px 0}}
.hero{{display:grid;grid-template-columns:220px 1fr;gap:12px;margin-bottom:12px}}
.vix-main{{background:var(--s1);border:1px solid var(--border);padding:20px 22px;display:flex;flex-direction:column;justify-content:space-between;border-radius:4px}}
.vix-lbl{{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}}
.vix-num{{font-family:'Syne',sans-serif;font-size:52px;font-weight:800;line-height:1;color:var(--white)}}
.vix-sub{{font-size:12px;color:var(--muted);margin-top:6px}}
.rpill{{display:inline-block;padding:5px 14px;border-radius:3px;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-top:14px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:1fr 1fr;gap:6px}}
.stat{{background:var(--s1);border:1px solid var(--border);padding:13px 15px;border-radius:4px}}
.stat-l{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:5px}}
.stat-v{{font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:var(--white)}}
.stat-d{{font-size:12px;margin-top:2px}}
.verdict{{display:flex;align-items:center;gap:16px;background:var(--s1);border:1px solid var(--border);border-radius:4px;padding:18px 22px;margin-bottom:12px}}
.v-score{{font-family:'Syne',sans-serif;font-size:44px;font-weight:800;min-width:70px;text-align:center}}
.v-div{{width:1px;height:50px;background:var(--border2);flex-shrink:0}}
.v-body{{flex:1}}
.v-title{{font-family:'Syne',sans-serif;font-size:17px;font-weight:700;margin-bottom:5px}}
.v-action{{font-size:13px;color:var(--text);line-height:1.6}}
.v-eq{{text-align:right;flex-shrink:0}}
.v-eq-l{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:3px}}
.v-eq-v{{font-family:'Syne',sans-serif;font-size:24px;font-weight:700}}
.sigs{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:12px}}
.sig-card{{background:var(--s1);border:1px solid var(--border);padding:13px;border-radius:4px}}
.sig-id{{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;display:flex;align-items:center;gap:6px;margin-bottom:6px;color:var(--muted)}}
.sig-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.sig-title{{font-size:13px;font-weight:600;color:var(--white);margin-bottom:4px;line-height:1.3}}
.sig-detail{{font-size:11px;color:var(--muted);line-height:1.5}}
.sig-badge{{font-size:12px;font-weight:600;margin-top:8px}}
.charts-row{{display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-bottom:12px}}
.cc{{background:var(--s1);border:1px solid var(--border);padding:16px;border-radius:4px}}
.cc-lbl{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}}
.cc-lbl span{{font-size:13px;font-weight:600;color:var(--white);text-transform:none;letter-spacing:0}}
.tbl-card{{background:var(--s1);border:1px solid var(--border);padding:16px;margin-bottom:12px;border-radius:4px}}
.tbl-lbl{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}}
table.mt{{width:100%;border-collapse:collapse;font-size:13px}}
table.mt th{{text-align:left;font-size:10px;color:var(--muted);padding:8px 12px;border-bottom:1px solid var(--border2);font-weight:400;letter-spacing:.04em;text-transform:uppercase}}
table.mt td{{padding:11px 12px;border-bottom:1px solid var(--border);color:var(--white);vertical-align:middle}}
table.mt tr:last-child td{{border-bottom:none}}
.pill{{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600}}
.interp-block{{border:1px solid var(--border2);border-radius:6px;margin-bottom:10px;overflow:hidden}}
.interp-header{{display:flex;align-items:center;gap:10px;padding:11px 16px;background:rgba(255,255,255,0.03);border-bottom:1px solid var(--border);flex-wrap:wrap}}
.interp-step{{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;background:rgba(112,184,255,0.15);color:var(--blue);padding:2px 8px;border-radius:3px;flex-shrink:0}}
.interp-title{{font-size:14px;font-weight:600;color:var(--white);flex:1}}
.interp-badge{{font-size:11px;font-weight:600;padding:2px 10px;border-radius:3px;border:1px solid;flex-shrink:0}}
.interp-body{{padding:14px 16px}}
.interp-text{{font-size:13px;color:var(--text);line-height:1.7;margin-bottom:12px}}
.interp-cases{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:7px}}
.icase{{padding:11px 13px;border-radius:4px;border:1px solid var(--border)}}
.ig{{background:rgba(77,216,144,0.07);border-color:rgba(77,216,144,0.35)}}
.io{{background:rgba(255,170,85,0.07);border-color:rgba(255,170,85,0.35)}}
.ir{{background:rgba(255,112,112,0.07);border-color:rgba(255,112,112,0.35)}}
.ib{{background:rgba(112,184,255,0.07);border-color:rgba(112,184,255,0.35)}}
.icase-l{{font-size:12px;font-weight:600;margin-bottom:4px}}
.ig .icase-l{{color:var(--green)}} .io .icase-l{{color:var(--orange)}} .ir .icase-l{{color:var(--red)}} .ib .icase-l{{color:var(--blue)}}
.icase-a{{font-size:12px;color:var(--text);line-height:1.6}}
footer{{border-top:1px solid var(--border);padding:16px 0;margin-top:12px;display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}}
.footer-brand{{font-family:'Syne',sans-serif;color:var(--gold);font-size:13px}}
@media(max-width:900px){{.hero{{grid-template-columns:1fr}}.sigs{{grid-template-columns:1fr 1fr}}.charts-row{{grid-template-columns:1fr}}.verdict{{flex-wrap:wrap}}}}
@media(max-width:580px){{.sigs{{grid-template-columns:1fr}}.stats{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">meine-<span>geldseite</span>.de · VIX Dashboard</div>
  <div class="upd">Update: {meta["updated_at"]}</div>
</div>
<div class="container"><div class="pp">

<div class="hero">
  <div class="vix-main">
    <div>
      <div class="vix-lbl">CBOE VIX — Aktuell</div>
      <div class="vix-num" style="color:{rc[2]}">{v["current_vix"]}</div>
      <div class="vix-sub">MA10: {v["current_ma10"]} · MA20: {v["current_ma20"]} · BB↑: {v["current_bb_upper"]}</div>
    </div>
    <div class="rpill" style="background:{rc[0]};color:{rc[2]};border:1px solid {rc[1]}">{v["regime_label"]}</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-l">MA10</div><div class="stat-v">{v["current_ma10"]}</div><div class="stat-d" style="color:{vix_vs_ma10_color}">{vix_vs_ma10_text}</div></div>
    <div class="stat"><div class="stat-l">MA20</div><div class="stat-v">{v["current_ma20"]}</div><div class="stat-d" style="color:{pct_color}">{pct_sign}{v["vix_pct_above_ma20"]}% vs. MA20</div></div>
    <div class="stat"><div class="stat-l">BB-Oben</div><div class="stat-v">{v["current_bb_upper"]}</div><div class="stat-d" style="color:{bb_color}">{bb_text}</div></div>
    <div class="stat"><div class="stat-l">VVIX</div><div class="stat-v">{vv.get("current_vvix","—")}</div><div class="stat-d" style="color:{vvix_trend_color}">Trend: {vv.get("vvix_trend","—")}</div></div>
    <div class="stat"><div class="stat-l">S&amp;P 500</div><div class="stat-v">{spy.get("current_spy","—")}</div><div class="stat-d" style="color:var(--muted)">{spy.get("spy_pct_from_ma50","?")}% vs. MA50</div></div>
    <div class="stat"><div class="stat-l">VIX 30d Max</div><div class="stat-v">{v["vix_30d_max"]}</div><div class="stat-d" style="color:var(--muted)">30d Min: {v["vix_30d_min"]}</div></div>
  </div>
</div>

<div class="verdict" style="border-color:{sig_color}44;background:{sig_color}08">
  <div class="v-score" style="color:{sig_color}">{re["auto_conditions_met"]}/4</div>
  <div class="v-div"></div>
  <div class="v-body">
    <div class="v-title" style="color:{sig_color}">{re["signal_label"]}</div>
    <div class="v-action">{re["action"]}</div>
  </div>
  <div class="v-eq">
    <div class="v-eq-l">Aktienquote</div>
    <div class="v-eq-v" style="color:{sig_color}">{v["equity_pct"]}</div>
  </div>
</div>

<div class="sigs">
{r1_card}
{r2_card}
{r3_card}
{r4_card}
{r5_card}
</div>

<div class="charts-row">
  <div class="cc">
    <div class="cc-lbl">VIX 90 Tage + MA10/MA20 + Bollinger Bands <span>VIX: {v["current_vix"]}</span></div>
    <div style="position:relative;height:200px"><canvas id="cvix"></canvas></div>
  </div>
  <div class="cc">
    <div class="cc-lbl">VVIX — 30 Tage <span>{vv.get("current_vvix","—")}</span></div>
    <div style="position:relative;height:200px"><canvas id="cvvix"></canvas></div>
  </div>
</div>

<div class="tbl-card">
  <div class="tbl-lbl">Alle Metriken</div>
  <table class="mt">
    <thead><tr><th>Metrik</th><th>Wert</th><th>Schwelle</th><th>Status</th><th>Bedeutung</th></tr></thead>
    <tbody>
      <tr><td>VIX aktuell</td><td style="color:{('#ff7070' if v['current_vix']>20 else '#4dd890')};font-weight:600">{v["current_vix"]}</td><td style="color:var(--muted)">&lt;20 gut / &gt;30 Stress</td><td><span class="pill" style="background:rgba({'255,112,112' if v['current_vix']>20 else '77,216,144'},0.15);color:{'#ff7070' if v['current_vix']>20 else '#4dd890'}">{'Prüfen' if v['current_vix']>20 else 'OK'}</span></td><td style="color:var(--muted);font-size:11px">Kern-Volatilitätsindikator</td></tr>
      <tr><td>R1: VIX vs. MA10</td><td style="color:{'#ff7070' if not v['r1_active'] else '#4dd890'};font-weight:600">{v["current_vix"]} / {v["current_ma10"]}</td><td style="color:var(--muted)">VIX &lt; MA10 für 3d</td><td><span class="pill" style="background:rgba({'77,216,144' if v['r1_active'] else '255,112,112'},0.15);color:{'#4dd890' if v['r1_active'] else '#ff7070'}">{'OK ✓' if v['r1_active'] else 'Prüfen'}</span></td><td style="color:var(--muted);font-size:11px">Streak: {v["r1_streak"]}/3 Tage</td></tr>
      <tr><td>VIX vs. MA20</td><td style="color:{pct_color};font-weight:600">{pct_sign}{v["vix_pct_above_ma20"]}%</td><td style="color:var(--muted)">&lt;0% ideal</td><td><span class="pill" style="background:rgba({'255,112,112' if v['vix_pct_above_ma20']>0 else '77,216,144'},0.15);color:{'#ff7070' if v['vix_pct_above_ma20']>0 else '#4dd890'}">{'Prüfen' if v['vix_pct_above_ma20']>0 else 'OK'}</span></td><td style="color:var(--muted);font-size:11px">VIX unter MA20 = normalisiert</td></tr>
      <tr><td>R3: Überdehnung 30d</td><td style="color:{'#4dd890' if v['r3_active'] else '#ff7070'};font-weight:600">{v["max_pct_above_ma20_30d"]}%</td><td style="color:var(--muted)">≥30%</td><td><span class="pill" style="background:rgba({'77,216,144' if v['r3_active'] else '255,112,112'},0.15);color:{'#4dd890' if v['r3_active'] else '#ff7070'}">{'OK ✓' if v['r3_active'] else 'Prüfen'}</span></td><td style="color:var(--muted);font-size:11px">Mean-Reversion-Basis</td></tr>
      <tr><td>R4: VVIX</td><td style="color:{'#4dd890' if vv.get('r4_active') else '#ff7070'};font-weight:600">{vv.get("current_vvix","—")}</td><td style="color:var(--muted)">&lt;120 &amp; fallend</td><td><span class="pill" style="background:rgba({'77,216,144' if vv.get('r4_active') else '255,112,112'},0.15);color:{'#4dd890' if vv.get('r4_active') else '#ff7070'}">{'OK ✓' if vv.get('r4_active') else 'Prüfen'}</span></td><td style="color:var(--muted);font-size:11px">Trend: {vv.get("vvix_trend","—")}</td></tr>
      <tr><td>S&amp;P vs. MA50</td><td style="color:var(--text);font-weight:600">{spy.get("spy_pct_from_ma50","?")}%</td><td style="color:var(--muted)">&gt;-15%</td><td><span class="pill" style="background:rgba({'77,216,144' if (spy.get('spy_pct_from_ma50') or -99)>-15 else '255,112,112'},0.15);color:{'#4dd890' if (spy.get('spy_pct_from_ma50') or -99)>-15 else '#ff7070'}">{'OK' if (spy.get('spy_pct_from_ma50') or -99)>-15 else 'Prüfen'}</span></td><td style="color:var(--muted);font-size:11px">Technische Marktstruktur</td></tr>
    </tbody>
  </table>
</div>

<div class="tbl-card">
  <div class="tbl-lbl">Tägliche Interpretationshilfe — Was tue ich mit den Daten?</div>
  <div style="font-size:13px;color:var(--muted);margin-bottom:16px;line-height:1.7">Jeden Werktag nach 22:00 Uhr (nach US-Börsenschluss) diese 5 Punkte prüfen.</div>

  <div class="interp-block">
    <div class="interp-header">
      <div class="interp-step">Schritt 1</div>
      <div class="interp-title">VIX-Regime ablesen</div>
      <div class="interp-badge" style="background:rgba(77,216,144,0.15);color:#4dd890;border-color:rgba(77,216,144,0.4)">● Automatisch</div>
    </div>
    <div class="interp-body">
      <div class="interp-text">Schau oben links auf die große VIX-Zahl und das farbige Regime-Badge.</div>
      <div class="interp-cases">
        <div class="icase ig"><div class="icase-l">VIX unter 20 — Grün</div><div class="icase-a">→ Nichts tun. Investiert bleiben. Trend folgen.</div></div>
        <div class="icase io"><div class="icase-l">VIX 20–30 — Orange</div><div class="icase-a">→ Wachsam sein. Stopps im Depot prüfen. Noch kein Verkauf.</div></div>
        <div class="icase ir"><div class="icase-l">VIX über 30 — Rot</div><div class="icase-a">→ Aktienquote reduzieren. Schritte 2–5 täglich prüfen.</div></div>
      </div>
    </div>
  </div>

  <div class="interp-block">
    <div class="interp-header">
      <div class="interp-step">Schritt 2</div>
      <div class="interp-title">R1 prüfen — VIX vs. MA10 (Pflicht für Wiedereinstieg)</div>
      <div class="interp-badge" style="background:rgba(77,216,144,0.15);color:#4dd890;border-color:rgba(77,216,144,0.4)">● Automatisch</div>
    </div>
    <div class="interp-body">
      <div class="interp-text">In der Metriken-Tabelle: Zeile "R1: VIX vs. MA10". Wie hoch ist der Streak?</div>
      <div class="interp-cases">
        <div class="icase ir"><div class="icase-l">Streak = 0 (VIX über MA10)</div><div class="icase-a">→ Kein Einstieg. Stopps halten. Weiter warten.</div></div>
        <div class="icase io"><div class="icase-l">Streak 1–2 Tage</div><div class="icase-a">→ Ermutigend aber noch nicht genug. Morgen wieder prüfen.</div></div>
        <div class="icase ig"><div class="icase-l">Streak ≥ 3 Tage ✓</div><div class="icase-a">→ R1 erfüllt! Weiter zu Schritt 3–5. Bei 2+ weiteren grün: kaufen.</div></div>
      </div>
    </div>
  </div>

  <div class="interp-block" style="border-color:rgba(240,192,96,0.4)">
    <div class="interp-header">
      <div class="interp-step">Schritt 3</div>
      <div class="interp-title">R2 manuell prüfen — VIX Futures Kurvenstruktur</div>
      <div class="interp-badge" style="background:rgba(240,192,96,0.2);color:#f0c060;border-color:rgba(240,192,96,0.5)">⚠ Manuell — 30 Sek.</div>
    </div>
    <div class="interp-body">
      <div class="interp-text">Öffne: <a href="https://www.cboe.com/tradable-products/vix/term-structure/" target="_blank" style="color:#70b8ff">cboe.com → VIX Term Structure</a><br>Ist der erste Monat (M1) günstiger als der zweite (M2)?</div>
      <div class="interp-cases">
        <div class="icase ig"><div class="icase-l">M1 &lt; M2 (Contango) ✓</div><div class="icase-a">→ R2 erfüllt. Markt erwartet künftig weniger Angst. Kaufsignal.</div></div>
        <div class="icase ir"><div class="icase-l">M1 &gt; M2 (Backwardation) ✗</div><div class="icase-a">→ R2 nicht erfüllt. Noch kein Einstieg — auch wenn andere Signale grün sind.</div></div>
      </div>
    </div>
  </div>

  <div class="interp-block">
    <div class="interp-header">
      <div class="interp-step">Schritt 4</div>
      <div class="interp-title">R4 prüfen — VVIX</div>
      <div class="interp-badge" style="background:rgba(77,216,144,0.15);color:#4dd890;border-color:rgba(77,216,144,0.4)">● Automatisch</div>
    </div>
    <div class="interp-body">
      <div class="interp-text">VVIX-Wert in der Stat-Box oben. Fällt er? Liegt er unter 120?</div>
      <div class="interp-cases">
        <div class="icase ir"><div class="icase-l">VVIX über 120 und steigt</div><div class="icase-a">→ Markt wird nervöser. Kein Einstieg. Risiko weiter reduzieren.</div></div>
        <div class="icase io"><div class="icase-l">VVIX über 120 aber fällt</div><div class="icase-a">→ Erste Beruhigung. Noch nicht kaufen, morgen wieder prüfen.</div></div>
        <div class="icase ig"><div class="icase-l">VVIX unter 120 und fällt ✓</div><div class="icase-a">→ R4 erfüllt. Starkes Normalisierungssignal.</div></div>
      </div>
    </div>
  </div>

  <div class="interp-block" style="border-color:rgba(240,192,96,0.4)">
    <div class="interp-header">
      <div class="interp-step">Schritt 5</div>
      <div class="interp-title">R5 manuell prüfen — S&amp;P 500 Chartstruktur</div>
      <div class="interp-badge" style="background:rgba(240,192,96,0.2);color:#f0c060;border-color:rgba(240,192,96,0.5)">⚠ Manuell — 2 Min.</div>
    </div>
    <div class="interp-body">
      <div class="interp-text">Öffne <a href="https://www.tradingview.com/chart/?symbol=SPX" target="_blank" style="color:#70b8ff">TradingView → SPX Wochenchart</a>. Macht der S&amp;P 500 noch neue Tiefs?</div>
      <div class="interp-cases">
        <div class="icase ir"><div class="icase-l">Immer neue Tiefs ✗</div><div class="icase-a">→ R5 nicht erfüllt. Noch kein Boden. Trotz anderer Signale: abwarten.</div></div>
        <div class="icase io"><div class="icase-l">Seitwärts, kein neues Tief seit &gt;5 Tagen</div><div class="icase-a">→ Mögliche Bodenbildung. Kleine Tranche möglich wenn R1+R2+R4 grün.</div></div>
        <div class="icase ig"><div class="icase-l">Höheres Tief sichtbar ✓</div><div class="icase-a">→ R5 erfüllt. Klassisches Umkehrmuster. Einstieg berechtigt.</div></div>
      </div>
    </div>
  </div>

  <div class="interp-block" style="border-color:rgba(112,184,255,0.4);background:rgba(112,184,255,0.04)">
    <div class="interp-header">
      <div class="interp-step" style="background:rgba(112,184,255,0.2);color:#70b8ff">Ergebnis</div>
      <div class="interp-title">Was kaufe ich konkret?</div>
    </div>
    <div class="interp-body">
      <div class="interp-cases">
        <div class="icase ir"><div class="icase-l">R1 fehlt oder 0–1 Signale</div><div class="icase-a">Nichts kaufen. Watchlist pflegen. Morgen wieder prüfen.</div></div>
        <div class="icase io"><div class="icase-l">R1 + 1 weiteres Signal</div><div class="icase-a">Pilotposition: 10–15% der Ziel-Aktienquote.</div></div>
        <div class="icase ig"><div class="icase-l">R1 + 2 weitere Signale ✓</div><div class="icase-a">Erste Tranche: 20–25%. Zweite Tranche in 1 Woche.</div></div>
        <div class="icase ig" style="border-color:rgba(77,216,144,0.6)"><div class="icase-l">R1 + 3–4 Signale ✓✓</div><div class="icase-a">Aggressiv: 40–60% sofort, Rest in 2 Wochen.</div></div>
      </div>
    </div>
  </div>

  <div style="margin-top:12px;padding:12px 16px;background:rgba(240,192,96,0.08);border:1px solid rgba(240,192,96,0.3);border-radius:4px;font-size:12px;color:var(--muted);line-height:1.7">
    <strong style="color:#f0c060">Wichtig:</strong> R2 und R5 immer manuell prüfen — das dauert ca. 3 Minuten. Kein Anlageberatung. Historische Muster garantieren keine zukünftigen Ergebnisse.
  </div>
</div>

<footer>
  <span class="footer-brand">meine-geldseite.de</span>
  <span>VIX Regime Dashboard · {meta["updated_at"]} · Yahoo Finance</span>
</footer>

</div></div>

<script>
const vixDates = {jd};
const vixVals  = {jv};
const ma10     = {jm10};
const ma20     = {jm20};
const bbUp     = {jbu};
const bbLo     = {jbl};
const vvixDates= {jvd};
const vvixVals = {jvv};

const gc = 'rgba(112,144,184,0.2)';
const tc = '#7090b8';

if(vixVals && vixVals.length > 0) {{
  new Chart(document.getElementById('cvix'), {{
    type:'line',
    data:{{
      labels: vixDates.map(d=>d.slice(5)),
      datasets:[
        {{label:'VIX',data:vixVals,borderColor:'#f0c060',borderWidth:2,pointRadius:0,tension:0.1,fill:false}},
        {{label:'MA10',data:ma10,borderColor:'#70b8ff',borderWidth:1.5,pointRadius:0,tension:0.1,fill:false}},
        {{label:'MA20',data:ma20,borderColor:'#7090b8',borderWidth:1,pointRadius:0,tension:0.1,fill:false}},
        {{label:'BB↑',data:bbUp,borderColor:'rgba(255,112,112,0.5)',borderWidth:1,borderDash:[4,3],pointRadius:0,tension:0.1,fill:'+1',backgroundColor:'rgba(255,112,112,0.04)'}},
        {{label:'BB↓',data:bbLo,borderColor:'rgba(77,216,144,0.35)',borderWidth:1,borderDash:[4,3],pointRadius:0,tension:0.1,fill:false}},
      ]
    }},
    options:{{
      responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
      plugins:{{legend:{{position:'top',labels:{{color:tc,font:{{size:10}},boxWidth:12,padding:10}}}},tooltip:{{backgroundColor:'#1a2540',borderColor:'#2e4070',borderWidth:1,titleColor:'#e8f0ff',bodyColor:'#c8d8f0',titleFont:{{size:11}},bodyFont:{{size:11}}}}}},
      scales:{{x:{{ticks:{{color:tc,font:{{size:9}},maxTicksLimit:8,maxRotation:0}},grid:{{color:gc}}}},y:{{ticks:{{color:tc,font:{{size:10}}}},grid:{{color:gc}}}}}}
    }}
  }});
}}

if(vvixVals && vvixVals.length > 0) {{
  new Chart(document.getElementById('cvvix'), {{
    type:'line',
    data:{{
      labels: vvixDates.map(d=>d.slice(5)),
      datasets:[
        {{label:'VVIX',data:vvixVals,borderColor:'#ffaa55',borderWidth:2,pointRadius:0,tension:0.1,fill:true,backgroundColor:'rgba(255,170,85,0.08)'}},
        {{label:'120',data:Array(vvixVals.length).fill(120),borderColor:'rgba(77,216,144,0.4)',borderWidth:1,borderDash:[5,4],pointRadius:0,fill:false}}
      ]
    }},
    options:{{
      responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
      plugins:{{legend:{{position:'top',labels:{{color:tc,font:{{size:10}},boxWidth:12,padding:10}}}},tooltip:{{backgroundColor:'#1a2540',borderColor:'#2e4070',borderWidth:1,titleColor:'#e8f0ff',bodyColor:'#c8d8f0',titleFont:{{size:11}},bodyFont:{{size:11}}}}}},
      scales:{{x:{{ticks:{{color:tc,font:{{size:9}},maxRotation:45,maxTicksLimit:8}},grid:{{color:gc}}}},y:{{min:95,max:155,ticks:{{color:tc,font:{{size:10}}}},grid:{{color:gc}}}}}}
    }}
  }});
}}
</script>
</body>
</html>"""
    return html


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching VIX data...")
    try:
        df_vix = fetch_ticker("^VIX", period="3mo")
        vix_signals = compute_signals(df_vix)
    except Exception as e:
        print(f"  ERROR VIX: {e}")
        vix_signals = {}
    vvix_data = fetch_vvix()
    spy_data  = fetch_spy()
    reentry   = count_reentry(vix_signals, vvix_data, spy_data)
    output = {
        "meta": {
            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "updated_date": str(date.today()),
            "data_source": "Yahoo Finance via yfinance",
        },
        "vix": vix_signals, "vvix": vvix_data, "spy": spy_data, "reentry": reentry,
    }
    # data.json speichern
    with open("docs/data.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    # index.html MIT eingebetteten Daten generieren
    html = build_html(output)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  VIX: {vix_signals.get('current_vix','?')} · {vix_signals.get('regime_label','?')}")
    print(f"  Signal: {reentry.get('signal_label','?')}")
    print(f"  ✓ data.json + index.html geschrieben")

if __name__ == "__main__":
    main()
