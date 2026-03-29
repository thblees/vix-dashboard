"""
VIX Regime Dashboard – Daten-Fetcher
Holt täglich: ^VIX, ^VVIX, ^GSPC via yfinance
Berechnet: 10-Tage-MA, 20-Tage-MA, Bollinger Bands, alle 5 Re-Entry-Bedingungen
Schreibt: docs/data.json (wird von GitHub Pages Dashboard gelesen)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
from datetime import datetime, date
import warnings
warnings.filterwarnings('ignore')


def fetch_ticker(symbol: str, period: str = "3mo") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    df.index = df.index.tz_localize(None)
    return df[["Close"]].rename(columns={"Close": symbol})


def compute_signals(df_vix: pd.DataFrame) -> dict:
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
        regime,regime_color,regime_label,equity_pct = "KOMFORT","green","Komfort-Zone","80–100%"
    elif current_vix < 20:
        regime,regime_color,regime_label,equity_pct = "NIEDRIG_NORMAL","lime","Niedriger Normalbereich","70–85%"
    elif current_vix < 25:
        regime,regime_color,regime_label,equity_pct = "NORMAL","yellow","Normalbereich","60–75%"
    elif current_vix < 30:
        regime,regime_color,regime_label,equity_pct = "ERHOEHTE_SPANNUNG","orange","Erhöhte Spannung","40–55%"
    elif current_vix < 35:
        regime,regime_color,regime_label,equity_pct = "STRESS","darkorange","Stress-Zone","20–40%"
    elif current_vix < 50:
        regime,regime_color,regime_label,equity_pct = "KRISE","red","Krise","<20%"
    else:
        regime,regime_color,regime_label,equity_pct = "PANIK","darkred","Panik / Systemkrise","0–10%"
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
        "regime": regime, "regime_color": regime_color, "regime_label": regime_label,
        "equity_pct": equity_pct, "r1_streak": r1_streak, "e1_streak": e1_streak,
        "r1_active": bool(r1_active), "e1_active": bool(e1_streak>=3),
        "e3_active": bool(e3_streak>=2), "r3_active": bool(r3_active),
        "max_pct_above_ma20_30d": round(max_pct_above,1),
        "chart_dates": chart_dates, "chart_vix": chart_vix, "chart_ma10": chart_ma10,
        "chart_ma20": chart_ma20, "chart_bb_upper": chart_bb_up, "chart_bb_lower": chart_bb_lo,
    }


def fetch_vvix() -> dict:
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
        return {"current_vvix": None, "r4_active": False, "error_vvix": str(e)}


def fetch_spy() -> dict:
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
            "spy_chart_dates": [str(d.date()) for d in close.index[-60:]],
            "spy_chart_vals": [round(float(v),1) for v in close.iloc[-60:]],
        }
    except Exception as e:
        return {"current_spy": None, "r5_hint": False, "error_spy": str(e)}


def count_reentry_signals(vix_data, vvix_data, spy_data):
    r1 = vix_data.get("r1_active", False)
    r3 = vix_data.get("r3_active", False)
    r4 = vvix_data.get("r4_active", False)
    r5 = spy_data.get("r5_hint", False)
    auto_count = sum([r1, r3, r4, r5])
    if not r1:
        signal,label,color,action = "NONE","Kein Signal — R1 nicht erfüllt","red","Abwarten. VIX muss 3 Tage unter MA10 schließen."
    elif auto_count == 1:
        signal,label,color,action = "WAIT","Zu früh — weitere Bestätigung nötig","orange","R1 erfüllt, aber keine weiteren Bestätigungen. Beobachten."
    elif auto_count == 2:
        signal,label,color,action = "CAUTIOUS","Vorsichtiger Einstieg möglich","yellow","Erste kleine Tranche (10–15%). R2 (Futures) manuell prüfen."
    elif auto_count == 3:
        signal,label,color,action = "BUY","Klares Re-Entry-Signal","lime","Einstieg. Erste Tranche kaufen, zweite in 1 Woche."
    else:
        signal,label,color,action = "STRONG_BUY","Starkes Signal — Aggressiver Einstieg","green","Zwei Tranchen zügig aufbauen. Zielquote innerhalb 2–3 Wochen."
    return {"r1":r1,"r2_manual":None,"r3":r3,"r4":r4,"r5_hint":r5,
            "auto_conditions_met":auto_count,"signal":signal,"signal_label":label,
            "signal_color":color,"action":action}


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching VIX data...")
    try:
        df_vix = fetch_ticker("^VIX", period="3mo")
        vix_signals = compute_signals(df_vix)
    except Exception as e:
        vix_signals = {"error": str(e)}
    vvix_data = fetch_vvix()
    spy_data  = fetch_spy()
    reentry   = count_reentry_signals(vix_signals, vvix_data, spy_data)
    output = {
        "meta": {
            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "updated_date": str(date.today()),
            "data_source": "Yahoo Finance via yfinance",
            "note": "R2 (Futures-Kurve) und R5 (Chartstruktur) = manuelle Prüfung empfohlen."
        },
        "vix": vix_signals, "vvix": vvix_data, "spy": spy_data, "reentry": reentry,
    }
    with open("docs/data.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  VIX: {vix_signals.get('current_vix','?')} · Regime: {vix_signals.get('regime_label','?')}")
    print(f"  Signal: {reentry.get('signal_label','?')}")
    print(f"  ✓ docs/data.json geschrieben")

if __name__ == "__main__":
    main()
