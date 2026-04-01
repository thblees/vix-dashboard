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
    if len(close) < 25: return {}
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = ma20 + 2 * bb_std
    bb_lower = ma20 - 2 * bb_std
    cv = float(close.iloc[-1])
    cm10 = float(ma10.iloc[-1])
    cm20 = float(ma20.iloc[-1])
    cbu = float(bb_upper.iloc[-1])
    cbl = float(bb_lower.iloc[-1])
    pct = ((cv - cm20) / cm20) * 100
    if cv < 15:   regime,label,eq = "KOMFORT","Komfort-Zone","80–100%"
    elif cv < 20: regime,label,eq = "NIEDRIG_NORMAL","Niedriger Normalbereich","70–85%"
    elif cv < 25: regime,label,eq = "NORMAL","Normalbereich","60–75%"
    elif cv < 30: regime,label,eq = "ERHOEHTE_SPANNUNG","Erhöhte Spannung","40–55%"
    elif cv < 35: regime,label,eq = "STRESS","Stress-Zone","20–40%"
    elif cv < 50: regime,label,eq = "KRISE","Krise","<20%"
    else:         regime,label,eq = "PANIK","Panik / Systemkrise","0–10%"
    vba = (close > ma10).astype(int)
    e1s = 0
    for i in range(len(vba)-1, max(len(vba)-10,-1), -1):
        if vba.iloc[i]==1: e1s+=1
        else: break
    abb = (close > bb_upper).astype(int)
    e3s = 0
    for i in range(len(abb)-1, max(len(abb)-5,-1), -1):
        if abb.iloc[i]==1: e3s+=1
        else: break
    vbm = (close < ma10).astype(int)
    r1s = 0
    for i in range(len(vbm)-1, max(len(vbm)-10,-1), -1):
        if vbm.iloc[i]==1: r1s+=1
        else: break
    w30 = close.iloc[-30:]; m30 = ma20.iloc[-30:]
    mpa = float(((w30-m30)/m30*100).max())
    r3a = mpa >= 30.0
    return {
        "current_vix":round(cv,2),"current_ma10":round(cm10,2),"current_ma20":round(cm20,2),
        "current_bb_upper":round(cbu,2),"current_bb_lower":round(cbl,2),
        "vix_pct_above_ma20":round(pct,1),"vix_30d_max":round(float(close.iloc[-30:].max()),2),
        "vix_30d_min":round(float(close.iloc[-30:].min()),2),
        "regime":regime,"regime_label":label,"equity_pct":eq,
        "r1_streak":r1s,"e1_streak":e1s,"r1_active":bool(r1s>=3),
        "e1_active":bool(e1s>=3),"e3_active":bool(e3s>=2),"r3_active":bool(r3a),
        "max_pct_above_ma20_30d":round(mpa,1),
        "chart_dates":[str(d.date()) for d in close.index[-90:]],
        "chart_vix":[round(float(x),2) for x in close.iloc[-90:]],
        "chart_ma10":[round(float(x),2) if not np.isnan(x) else None for x in ma10.iloc[-90:]],
        "chart_ma20":[round(float(x),2) if not np.isnan(x) else None for x in ma20.iloc[-90:]],
        "chart_bb_upper":[round(float(x),2) if not np.isnan(x) else None for x in bb_upper.iloc[-90:]],
        "chart_bb_lower":[round(float(x),2) if not np.isnan(x) else None for x in bb_lower.iloc[-90:]],
    }

def fetch_vvix():
    try:
        df = fetch_ticker("^VVIX","1mo")
        cur = float(df["^VVIX"].iloc[-1])
        p5  = float(df["^VVIX"].iloc[-6]) if len(df)>=6 else cur
        trend = "fällt" if cur < p5 else "steigt"
        return {"current_vvix":round(cur,2),"vvix_5d_ago":round(p5,2),"vvix_trend":trend,
                "r4_active":bool(cur<120 and trend=="fällt"),
                "vvix_hist_dates":[str(d.date()) for d in df.index[-30:]],
                "vvix_hist_vals":[round(float(x),2) for x in df["^VVIX"].iloc[-30:]]}
    except: return {"current_vvix":None,"r4_active":False,"vvix_hist_dates":[],"vvix_hist_vals":[]}

def fetch_spy():
    try:
        df = fetch_ticker("^GSPC","3mo"); close = df["^GSPC"].dropna()
        cs = float(close.iloc[-1]); ma50 = float(close.rolling(50).mean().iloc[-1])
        pct = ((cs-ma50)/ma50)*100
        mn = float(close.iloc[-30:].min()); idx = int(close.iloc[-30:].argmin())
        dsl = 30-idx
        return {"current_spy":round(cs,1),"spy_ma50":round(ma50,1),
                "spy_pct_from_ma50":round(pct,1),"spy_30d_min":round(mn,1),
                "days_since_30d_low":int(dsl),"r5_hint":bool(dsl>=5 and cs>mn and pct>-15)}
    except: return {"current_spy":None,"r5_hint":False,"days_since_30d_low":0,"spy_pct_from_ma50":0}

def count_reentry(v,vv,spy):
    cv   = v.get("current_vix", 99)
    r1   = v.get("r1_active", False)
    r3   = v.get("r3_active", False)
    r4   = vv.get("r4_active", False)
    r5   = spy.get("r5_hint", False)
    gate1 = cv < 30
    gate2 = r1
    if not gate1:
        s = "GATE1_BLOCKED"
        l = "🔴 Pflicht-Gate 1 nicht erfüllt — VIX noch über 30"
        a = f"VIX steht bei {cv} — über der 30er-Schwelle. Kein Wiedereinstieg möglich. Bedingung 2 gar nicht erst prüfen. Abwarten und Kapital schützen."
        n = 0
    elif not gate2:
        s = "GATE2_BLOCKED"
        l = "🟠 Pflicht-Gate 2 nicht erfüllt — VIX noch nicht 3 Tage unter MA10"
        streak = v.get("r1_streak", 0)
        a = f"VIX ist zwar unter 30, aber noch nicht lange genug unter dem 10-Tage-Durchschnitt ({streak} von 3 Tagen). Bedingungen 3–5 noch nicht relevant. Morgen wieder prüfen."
        n = 0
    else:
        n = sum([r3, r4, r5])
        if n == 0:   s,l,a = "WAIT","🟡 Beide Gates offen — Bestätigungen fehlen noch","VIX hat sich beruhigt. Prüfe jetzt Bedingungen 3, 4 und 5. Noch keine Bestätigung — abwarten."
        elif n == 1: s,l,a = "CAUTIOUS","🟡 Erste Bestätigung — vorsichtiger Einstieg möglich","Kleine Pilotposition möglich: 10–15% der Ziel-Aktienquote. Bedingungen 4 und 5 weiter beobachten."
        elif n == 2: s,l,a = "BUY","🟢 Klares Kaufsignal — Einstieg","Erste Kauftranche: 20–25%. Zweite Tranche in einer Woche wenn Signale stabil bleiben."
        else:        s,l,a = "STRONG_BUY","🟢 Starkes Kaufsignal — Aggressiver Einstieg","40–60% sofort kaufen. Rest in 2 Wochen aufbauen. Historisch beste Einstiegschancen."
    return {"gate1":gate1,"gate2":gate2,"r1":r1,"r3":r3,"r4":r4,"r5_hint":r5,
            "auto_conditions_met":n,"signal":s,"signal_label":l,"action":a,
            "current_vix":cv}

def build_html(data):
    v=data["vix"]; vv=data["vvix"]; spy=data["spy"]; re=data["reentry"]; meta=data["meta"]

    rmap = {
        "KOMFORT":           ("#4dd890","rgba(77,216,144,0.15)","rgba(77,216,144,0.5)"),
        "NIEDRIG_NORMAL":    ("#80e8b0","rgba(77,216,144,0.10)","rgba(77,216,144,0.35)"),
        "NORMAL":            ("#f0c060","rgba(240,192,96,0.12)","rgba(240,192,96,0.4)"),
        "ERHOEHTE_SPANNUNG": ("#ffaa55","rgba(255,170,85,0.12)","rgba(255,170,85,0.4)"),
        "STRESS":            ("#ff7070","rgba(255,112,112,0.12)","rgba(255,112,112,0.45)"),
        "KRISE":             ("#ff9090","rgba(255,112,112,0.15)","rgba(255,112,112,0.55)"),
        "PANIK":             ("#ffaaaa","rgba(220,60,60,0.18)","rgba(220,60,60,0.65)"),
    }
    rc = rmap.get(v.get("regime","NORMAL"), rmap["NORMAL"])
    smap = {"NONE":"#ff7070","WAIT":"#ffaa55","CAUTIOUS":"#f0c060","BUY":"#4dd890","STRONG_BUY":"#80ffb8",
            "GATE1_BLOCKED":"#ff7070","GATE2_BLOCKED":"#ffaa55"}
    sc = smap.get(re.get("signal","NONE"),"#ff7070")

    cv   = v.get("current_vix",0)
    cm10 = v.get("current_ma10",0)
    cm20 = v.get("current_ma20",0)
    cbu  = v.get("current_bb_upper",0)
    pct  = v.get("vix_pct_above_ma20",0)
    r1s  = v.get("r1_streak",0)
    r1a  = v.get("r1_active",False)
    r3a  = v.get("r3_active",False)
    mpa  = v.get("max_pct_above_ma20_30d",0)
    r4a  = vv.get("r4_active",False)
    vviv = vv.get("current_vvix","—")
    vvit = vv.get("vvix_trend","—")
    r5a  = spy.get("r5_hint",False)
    dsl  = spy.get("days_since_30d_low",0)
    n    = re.get("auto_conditions_met",0)
    gate1 = re.get("gate1", False)
    gate2 = re.get("gate2", False)
    gates_open = gate1 and gate2

    def ok_badge(ok, yes="✓ Erfüllt", no="✗ Nicht erfüllt"):
        c,t = ("#4dd890",yes) if ok else ("#ff7070",no)
        bg = "rgba(77,216,144,0.12)" if ok else "rgba(255,112,112,0.12)"
        return f'<span style="padding:4px 12px;border-radius:3px;font-size:13px;font-weight:700;background:{bg};color:{c}">{t}</span>'

    def step_card(num, icon, title, auto, what, check_html, result_ok, result_yes, result_no, detail="", is_manual=False):
        auto_lbl = ('<span style="font-size:11px;padding:2px 10px;border-radius:3px;background:rgba(77,216,144,0.12);color:#4dd890;border:1px solid rgba(77,216,144,0.3);font-weight:600">● Dashboard zeigt es automatisch</span>'
                    if auto else
                    '<span style="font-size:11px;padding:2px 10px;border-radius:3px;background:rgba(240,192,96,0.15);color:#f0c060;border:1px solid rgba(240,192,96,0.4);font-weight:600">⚠ Manuell auf externer Website prüfen</span>')
        return f'''<div style="background:#223058;border:1px solid #2e4070;border-radius:6px;overflow:hidden;margin-bottom:8px">
  <div style="display:flex;align-items:center;gap:10px;padding:13px 18px;background:rgba(255,255,255,0.03);border-bottom:1px solid #2e4070;flex-wrap:wrap">
    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
      <div style="width:28px;height:28px;border-radius:50%;background:rgba(112,184,255,0.15);color:#70b8ff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800">{num}</div>
      <span style="font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#7090b8;font-weight:600">Bestätigung</span>
    </div>
    <div style="font-size:18px;flex-shrink:0">{icon}</div>
    <div style="flex:1;min-width:200px">
      <div style="font-size:15px;font-weight:700;color:#e8f0ff">{title}</div>
    </div>
    {auto_lbl}
  </div>
  <div style="padding:16px 18px;display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div>
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:8px">Was bedeutet das?</div>
      <div style="font-size:13px;color:#c8d8f0;line-height:1.75">{what}</div>
    </div>
    <div>
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:8px">Was prüfe ich konkret?</div>
      <div style="font-size:13px;color:#c8d8f0;line-height:1.75;margin-bottom:12px">{check_html}</div>
      {ok_badge(result_ok, result_yes, result_no)}
      {f'<div style="font-size:12px;color:#7090b8;margin-top:6px">{detail}</div>' if detail else ''}
    </div>
  </div>
</div>'''

    def action_row(conditions, icon, title, action, color):
        return f'''<div style="display:grid;grid-template-columns:120px 1fr 2fr;border-bottom:1px solid #2e4070">
  <div style="padding:12px 14px;font-size:12px;font-weight:700;color:{color};display:flex;align-items:center">{conditions}</div>
  <div style="padding:12px 14px;border-left:1px solid #2e4070;display:flex;align-items:center;gap:8px">
    <span style="font-size:18px">{icon}</span>
    <span style="font-size:13px;font-weight:600;color:#e8f0ff">{title}</span>
  </div>
  <div style="padding:12px 14px;border-left:1px solid #2e4070;font-size:13px;color:#c8d8f0;display:flex;align-items:center;line-height:1.5">{action}</div>
</div>'''

    # Chart-Daten
    jd=json.dumps(v.get("chart_dates",[])); jv=json.dumps(v.get("chart_vix",[]))
    jm10=json.dumps(v.get("chart_ma10",[])); jm20=json.dumps(v.get("chart_ma20",[]))
    jbu=json.dumps(v.get("chart_bb_upper",[])); jbl=json.dumps(v.get("chart_bb_lower",[]))
    jvd=json.dumps(vv.get("vvix_hist_dates",[])); jvv=json.dumps(vv.get("vvix_hist_vals",[]))

    # Schritte 3-5
    s3 = step_card("3", "📈", "Beruhigt sich auch der Futures-Markt?", False,
        'VIX-Futures sind Wetten auf die künftige Angst. Im Normalfall sind <strong style="color:#e8f0ff">weiter entfernte Monate teurer</strong> (= Contango). '
        'Wenn der nächste Monat <strong style="color:#ff7070">teurer</strong> ist als der übernächste, hat der Markt jetzt mehr Angst als in der Zukunft (= Backwardation — Warnsignal).',
        'Öffne: <a href="https://www.cboe.com/tradable-products/vix/term-structure/" target="_blank" style="color:#70b8ff">cboe.com → VIX Term Structure</a><br><br>'
        '<strong style="color:#4dd890">Gut:</strong> Monat 1 &lt; Monat 2 &lt; Monat 3 (aufsteigend)<br>'
        '<strong style="color:#ff7070">Schlecht:</strong> Monat 1 &gt; Monat 2 (absteigend)',
        None, "", "", "Monat 1 = nächster Verfall (~30 Tage). Monat 2 = übernächster (~60 Tage).",
        is_manual=True)

    s4 = step_card("4", "🔍", "Beruhigt sich der Nerven-Index (VVIX)?", True,
        f'Der VVIX misst wie nervös der VIX <em>selbst</em> ist. Wenn er fällt, beruhigt sich der Markt von innen — oft <em>bevor</em> der VIX selbst stark fällt. Daher ein wertvolles Frühsignal.',
        f'Aktueller VVIX: <strong style="color:#e8f0ff">{vviv}</strong><br>'
        f'Trend der letzten 5 Tage: <strong style="color:{"#4dd890" if vvit=="fällt" else "#ffaa55"}">{vvit}</strong><br>'
        f'Schwelle: unter 120 UND fallend',
        r4a, "✓ VVIX unter 120 und fällt — Beruhigung sichtbar",
        f"✗ VVIX = {vviv} — noch zu hoch oder steigend",
        "Fällt der VVIX, obwohl der VIX noch hoch ist? → Das ist das früheste Signal überhaupt.")

    s5 = step_card("5", "📉", "Bestätigt der S&P 500 Chart die Erholung?", False,
        'Der Chart muss zeigen, dass der Markt einen Boden gefunden hat. Das erkennst du daran, dass der S&P 500 <strong style="color:#e8f0ff">keine neuen Tiefs mehr macht</strong>.',
        f'Öffne: <a href="https://www.tradingview.com/chart/?symbol=SPX" target="_blank" style="color:#70b8ff">TradingView → SPX Wochenchart</a><br><br>'
        f'Frage: Macht der S&P 500 noch neue Tiefs?<br>'
        f'<strong style="color:#4dd890">Gut:</strong> Kein neues Tief seit mind. 5 Tagen<br>'
        f'<strong style="color:#ff7070">Schlecht:</strong> Immer noch neue Tiefs',
        r5a, "✓ Schätzung: Boden wahrscheinlich gebildet",
        f"✗ S&P noch nicht stabil — Tief vor {dsl} Tagen",
        "Eigener Blick auf den Chart empfohlen — Dashboard-Schätzung nur grober Hinweis.",
        is_manual=True)

    # Aktions-Tabelle
    action_rows = (
        action_row("0–1 Bedingungen", "🔴", "Nicht kaufen",
            "Watchlist pflegen. Morgen erneut prüfen. Kapital schützen.", "#ff7070") +
        action_row("Bed. 1 + 1 weitere", "🟡", "Kleine Pilotposition",
            "10–15% der Ziel-Aktienquote kaufen. Täglich weiter beobachten.", "#ffaa55") +
        action_row("Bed. 1 + 2 weitere", "🟢", "Erster Einstieg",
            "20–25% kaufen. Zweite Tranche in 1 Woche wenn stabil.", "#4dd890") +
        action_row("Bed. 1 + 3–4 weitere", "🚀", "Aggressiver Einstieg",
            "40–60% sofort. Rest in 2 Wochen. Historisch beste Chancen.", "#80ffb8")
    )

    sig_label = re.get("signal_label","—")
    sig_action = re.get("action","—")

    # ── PFLICHT-GATE STATUS ──
    if not gate1:
        gate1_color = "#ff7070"
        gate1_bg = "rgba(255,112,112,0.10)"
        gate1_border = "rgba(255,112,112,0.45)"
        gate1_icon = "🔴"
        gate1_status = f"NICHT ERFÜLLT — VIX steht bei {cv} (muss unter 30 sein)"
        gate1_action = f"Solange der VIX über 30 liegt, ist der Markt im Stress-Modus. Kein Einstieg. Weiter warten. Bedingung 2 jetzt noch nicht relevant."
    else:
        gate1_color = "#4dd890"
        gate1_bg = "rgba(77,216,144,0.10)"
        gate1_border = "rgba(77,216,144,0.45)"
        gate1_icon = "🟢"
        gate1_status = f"✓ ERFÜLLT — VIX bei {cv} (unter 30)"
        gate1_action = "Gut — der Markt hat die Panik-Zone verlassen. Weiter zu Pflicht-Gate 2."

    if not gate2:
        gate2_color = "#ff7070"
        gate2_bg = "rgba(255,112,112,0.10)"
        gate2_border = "rgba(255,112,112,0.45)"
        gate2_icon = "🔴" if not gate1 else "🟠"
        gate2_status = f"NICHT ERFÜLLT — Erst {r1s} von 3 Tagen unter MA10" if gate1 else "NOCH NICHT PRÜFEN — erst Pflicht-Gate 1 abwarten"
        gate2_action = f"VIX muss 3 Tage in Folge unter seinem 10-Tage-Durchschnitt ({cm10}) schließen. Aktuell: Tag {r1s} von 3." if gate1 else "Erst wenn Gate 1 erfüllt ist, wird diese Bedingung relevant."
    else:
        gate2_color = "#4dd890"
        gate2_bg = "rgba(77,216,144,0.10)"
        gate2_border = "rgba(77,216,144,0.45)"
        gate2_icon = "🟢"
        gate2_status = f"✓ ERFÜLLT — VIX {r1s} Tage unter MA10 ({cm10})"
        gate2_action = "Beide Pflicht-Gates erfüllt! Jetzt weiter zu den Bestätigungs-Bedingungen 3, 4 und 5."

    # ═══ NEUE LOGIK: Bestätigungen immer lesbar, aber mit Hinweis wenn Gates noch nicht offen ═══
    if not gates_open:
        confirm_banner = '''<div style="padding:12px 16px;background:rgba(112,144,184,0.08);border:1px solid rgba(112,144,184,0.25);border-radius:4px;margin-bottom:12px;font-size:13px;color:#90a8c8;line-height:1.7;display:flex;align-items:center;gap:10px">
    <span style="font-size:18px">ℹ️</span>
    <span><strong style="color:#c8d8f0">Zur Info:</strong> Diese Bedingungen werden erst aktiv, wenn beide Pflicht-Gates oben erfüllt sind. Du kannst sie aber jetzt schon lesen und verstehen, was geprüft wird.</span>
</div>'''
        confirm_style = ''
    else:
        confirm_banner = '''<div style="padding:12px 16px;background:rgba(77,216,144,0.08);border:1px solid rgba(77,216,144,0.3);border-radius:4px;margin-bottom:12px;font-size:13px;color:#4dd890;line-height:1.7;display:flex;align-items:center;gap:10px">
    <span style="font-size:18px">✅</span>
    <span><strong>Beide Pflicht-Gates erfüllt!</strong> Prüfe jetzt die Bestätigungs-Bedingungen — je mehr grün, desto stärker das Einstiegssignal.</span>
</div>'''
        confirm_style = ''

    # Info-Tab HTML (unchanged from original)
    info_html = _build_info_html()

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIX Dashboard — meine-geldseite.de</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#1a2540;color:#c8d8f0;font-family:'Inter',sans-serif;font-size:15px;line-height:1.65}}
.topbar{{background:#1a2540;border-bottom:1px solid #2e4070;padding:0 28px;height:52px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,0.4)}}
.brand{{font-family:'Syne',sans-serif;font-size:15px;font-weight:800;color:#f0c060}}
.brand span{{color:#e8f0ff}}
.w{{max-width:1100px;margin:0 auto;padding:24px 24px}}
h2{{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:#e8f0ff;margin-bottom:4px}}
.section-intro{{font-size:13px;color:#7090b8;margin-bottom:16px;line-height:1.7}}
.divider{{border:none;border-top:1px solid #2e4070;margin:28px 0}}
.card{{background:#223058;border:1px solid #2e4070;border-radius:6px;padding:20px;margin-bottom:8px}}
.tab-panel{{display:none}}.tab-panel.active{{display:block}}
@media(max-width:700px){{
  [style*="grid-template-columns:1fr 1fr"],[style*="grid-template-columns:120px"]{{display:block!important}}
  [style*="grid-template-columns:220px"]{{display:block!important}}
}}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">meine-<span>geldseite</span>.de · VIX Dashboard</div>
  <div style="display:flex;align-items:center;gap:8px">
    <button onclick="showTab('daily')" id="tab-daily" style="background:rgba(240,192,96,0.2);border:1px solid rgba(240,192,96,0.5);color:#f0c060;padding:6px 16px;border-radius:3px;font-family:Inter,sans-serif;font-size:13px;font-weight:600;cursor:pointer">📋 Tägliches Check-up</button>
    <button onclick="showTab('info')" id="tab-info" style="background:transparent;border:1px solid #2e4070;color:#7090b8;padding:6px 16px;border-radius:3px;font-family:Inter,sans-serif;font-size:13px;font-weight:600;cursor:pointer">📖 Hintergrundwissen</button>
    <div style="font-size:11px;color:#7090b8;margin-left:8px">Aktualisiert: {meta.get("updated_at","—")}</div>
  </div>
</div>

<div class="w">
<div id="panel-daily" class="tab-panel active">

<h2>📋 Deine tägliche Checkliste</h2>
<p class="section-intro">Jeden Werktag nach 22:00 Uhr (nach US-Börsenschluss) diese 5 Punkte der Reihe nach abarbeiten. Dauert ca. 5 Minuten.</p>

<!-- PFLICHT-GATES -->
<div style="margin-bottom:6px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8">Pflicht-Gates — müssen BEIDE erfüllt sein, bevor du weiterschaust</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:20px">
  <div style="background:{gate1_bg};border:2px solid {gate1_border};border-radius:6px;padding:20px;position:relative">
    <div style="position:absolute;top:-12px;left:16px;background:#1a2540;padding:0 8px;font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{gate1_color}">Pflicht-Gate 1</div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:24px">{gate1_icon}</span>
      <div>
        <div style="font-size:15px;font-weight:700;color:#e8f0ff">VIX unter 30</div>
        <div style="font-size:12px;color:#7090b8">Markt hat Panik-Zone verlassen</div>
      </div>
    </div>
    <div style="padding:10px 14px;background:rgba(0,0,0,0.2);border-radius:4px;margin-bottom:10px">
      <div style="font-size:12px;font-weight:700;color:{gate1_color};margin-bottom:4px">{gate1_status}</div>
      <div style="font-size:12px;color:#c8d8f0;line-height:1.6">{gate1_action}</div>
    </div>
    <div style="font-size:12px;color:#7090b8;padding:8px 12px;background:rgba(255,255,255,0.04);border-radius:4px">
      💡 <strong style="color:#e8f0ff">Warum 30?</strong> Über 30 ist der Markt im Stress-Modus. Statistisch verlieren Aktien in solchen Phasen kurzfristig an Wert. Kein Einstieg sinnvoll.
    </div>
  </div>
  <div style="background:{gate2_bg};border:2px solid {gate2_border};border-radius:6px;padding:20px;position:relative">
    <div style="position:absolute;top:-12px;left:16px;background:#1a2540;padding:0 8px;font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{gate2_color}">Pflicht-Gate 2</div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:24px">{gate2_icon}</span>
      <div>
        <div style="font-size:15px;font-weight:700;color:#e8f0ff">VIX 3 Tage unter MA10</div>
        <div style="font-size:12px;color:#7090b8">Beruhigung nachhaltig bestätigt</div>
      </div>
    </div>
    <div style="padding:10px 14px;background:rgba(0,0,0,0.2);border-radius:4px;margin-bottom:10px">
      <div style="font-size:12px;font-weight:700;color:{gate2_color};margin-bottom:4px">{gate2_status}</div>
      <div style="font-size:12px;color:#c8d8f0;line-height:1.6">{gate2_action}</div>
    </div>
    <div style="font-size:12px;color:#7090b8;padding:8px 12px;background:rgba(255,255,255,0.04);border-radius:4px">
      💡 <strong style="color:#e8f0ff">Warum 3 Tage?</strong> Ein einzelner ruhiger Tag kann Zufall sein. Erst 3 Tage in Folge unter dem Durchschnitt zeigen eine echte Trendwende.
    </div>
  </div>
</div>

{'<div style="padding:14px 18px;background:rgba(255,112,112,0.10);border:1px solid rgba(255,112,112,0.4);border-radius:4px;margin-bottom:20px;font-size:13px;color:#ff9090;line-height:1.7"><strong>🛑 Stopp hier.</strong> Solange nicht beide Pflicht-Gates erfüllt sind, sind Bedingungen 3–5 noch nicht handlungsrelevant. Nicht kaufen — Kapital schützen und täglich wiederholen.</div>' if not gates_open else '<div style="padding:14px 18px;background:rgba(77,216,144,0.08);border:1px solid rgba(77,216,144,0.4);border-radius:4px;margin-bottom:20px;font-size:13px;color:#4dd890;line-height:1.7"><strong>✓ Beide Pflicht-Gates erfüllt.</strong> Weiter zu den Bestätigungs-Bedingungen unten.</div>'}

<!-- BESTÄTIGUNGS-BEDINGUNGEN — IMMER LESBAR -->
<div style="{confirm_style}">
<div style="margin-bottom:6px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8">Bestätigungs-Bedingungen — je mehr erfüllt, desto aggressiver der Einstieg</div>
{confirm_banner}
{s3}
{s4}
{s5}
</div>

<!-- ERGEBNIS -->
<div style="background:#223058;border:2px solid {sc}44;border-radius:6px;padding:20px 22px;margin-bottom:8px">
  <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:8px">Ergebnis heute — {re.get("auto_conditions_met",0)} von 4 automatischen Bedingungen erfüllt</div>
  <div style="font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:{sc};margin-bottom:8px">{sig_label}</div>
  <div style="font-size:14px;color:#c8d8f0;line-height:1.7;margin-bottom:16px">{sig_action}</div>
  <div style="background:#1a2540;border-radius:4px;overflow:hidden">
    <div style="padding:10px 14px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;border-bottom:1px solid #2e4070">Was tue ich jetzt konkret?</div>
    {action_rows}
  </div>
  <div style="margin-top:12px;font-size:12px;color:#7090b8;padding:10px 14px;background:rgba(240,192,96,0.06);border:1px solid rgba(240,192,96,0.25);border-radius:4px">
    ⚠ <strong style="color:#f0c060">Wichtig:</strong> Bedingung 3 (Futures-Kurve) und Bedingung 5 (S&P 500 Chart) musst du immer selbst kurz manuell prüfen — das Dashboard kann das nicht automatisch. Keine Anlageberatung.
  </div>
</div>

<hr class="divider">

<h2>📊 Aktuelle Zahlen im Überblick</h2>
<p class="section-intro">Alle Werte auf einen Blick. Werden täglich um 22:30 Uhr automatisch aktualisiert.</p>

<div style="display:grid;grid-template-columns:220px 1fr;gap:12px;margin-bottom:12px">
  <div class="card" style="display:flex;flex-direction:column;justify-content:space-between">
    <div>
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:8px">CBOE VIX — Aktuell</div>
      <div style="font-family:'Syne',sans-serif;font-size:52px;font-weight:800;line-height:1;color:{rc[0]}">{cv}</div>
      <div style="font-size:12px;color:#7090b8;margin-top:8px">10-Tage-Durchschnitt: {cm10}<br>20-Tage-Durchschnitt: {cm20}<br>Oberes Bollinger Band: {cbu}</div>
    </div>
    <div style="display:inline-block;padding:6px 14px;border-radius:3px;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-top:14px;background:{rc[1]};color:{rc[0]};border:1px solid {rc[2]}">{v.get("regime_label","—")}</div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:1fr 1fr;gap:6px">
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">10-Tage-Durchschnitt</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{cm10}</div>
      <div style="font-size:12px;margin-top:3px;color:{"#ff7070" if cv>cm10 else "#4dd890"}">{"▲ VIX darüber — Warnung" if cv>cm10 else "▼ VIX darunter — Beruhigung"}</div>
    </div>
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">20-Tage-Durchschnitt</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{cm20}</div>
      <div style="font-size:12px;margin-top:3px;color:{"#ff7070" if pct>0 else "#4dd890"}">{("+" if pct>=0 else "")}{pct}% {"über" if pct>=0 else "unter"} Durchschnitt</div>
    </div>
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">Bollinger Band oben</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{cbu}</div>
      <div style="font-size:12px;margin-top:3px;color:{"#ff7070" if cv>cbu else "#4dd890"}">{"⚠ VIX darüber — überhitzt" if cv>cbu else "✓ VIX darunter — normal"}</div>
    </div>
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">VVIX (Nervositäts-Index)</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{vviv}</div>
      <div style="font-size:12px;margin-top:3px;color:{"#4dd890" if vvit=="fällt" else "#ffaa55"}">Trend: {vvit} — {"gut" if vvit=="fällt" else "Vorsicht"}</div>
    </div>
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">S&amp;P 500</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{spy.get("current_spy","—")}</div>
      <div style="font-size:12px;margin-top:3px;color:#7090b8">{spy.get("spy_pct_from_ma50","?")}% vs. 50-Tage-Durchschnitt</div>
    </div>
    <div class="card" style="padding:14px 16px">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:6px">VIX 30-Tage-Maximum</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#e8f0ff">{v.get("vix_30d_max","—")}</div>
      <div style="font-size:12px;margin-top:3px;color:#7090b8">30d-Minimum: {v.get("vix_30d_min","—")}</div>
    </div>
  </div>
</div>

<div style="display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-bottom:12px">
  <div class="card">
    <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:10px;display:flex;justify-content:space-between"><span>VIX-Verlauf 90 Tage</span><span style="font-size:13px;font-weight:600;color:#e8f0ff;text-transform:none;letter-spacing:0">VIX: {cv}</span></div>
    <div style="position:relative;height:200px"><canvas id="cvix"></canvas></div>
  </div>
  <div class="card">
    <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:10px;display:flex;justify-content:space-between"><span>VVIX Nervositäts-Index</span><span style="font-size:13px;font-weight:600;color:#e8f0ff;text-transform:none;letter-spacing:0">{vviv}</span></div>
    <div style="position:relative;height:200px"><canvas id="cvvix"></canvas></div>
  </div>
</div>

<hr class="divider">

<h2>📖 Was bedeuten die Begriffe?</h2>
<p class="section-intro">Hier findest du alle Fachbegriffe einfach erklärt.</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">VIX — der Angst-Index</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">Der VIX misst, wie stark die Anleger erwarten, dass der S&amp;P 500 in den nächsten 30 Tagen schwankt. Er wird aus den Preisen von Optionen berechnet.<br><br><strong style="color:#e8f0ff">Faustregeln:</strong><br>Unter 15 = sehr ruhig, Bullenmarkt<br>15–20 = normal<br>20–30 = erhöht, Vorsicht<br>Über 30 = Stress / Krise<br>Über 50 = Panik</div>
  </div>
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">Durchschnitt (MA10 / MA20)</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">MA steht für "Moving Average" — gleitender Durchschnitt.<br><br><strong style="color:#e8f0ff">MA10</strong> = Durchschnitt der letzten 10 Handelstage<br><strong style="color:#e8f0ff">MA20</strong> = Durchschnitt der letzten 20 Handelstage<br><br>Wenn der VIX <em>unter</em> seinen Durchschnitt fällt, ist das ein Zeichen der Beruhigung.</div>
  </div>
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">Bollinger Bänder</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">Statistische Grenzwerte um den Durchschnitt. Das obere Band zeigt an, wie weit der VIX "normalerweise" steigen darf.<br><br>Wenn der VIX <em>über</em> das obere Band steigt, ist er überhitzt — eine Gegenbewegung nach unten ist dann statistisch wahrscheinlich.</div>
  </div>
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">VVIX — Nervosität der Nervosität</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">Der VVIX misst, wie stark der VIX <em>selbst</em> schwankt. Er ist ein Frühindikator:<br><br>Wenn der VVIX fällt, beruhigt sich der Markt von innen heraus — <em>bevor</em> es im VIX selbst sichtbar wird. Deshalb schauen wir ihn täglich an.</div>
  </div>
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">Futures-Kurve: Contango &amp; Backwardation</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">VIX-Futures sind Verträge, die auf die künftige Höhe des VIX wetten.<br><br><strong style="color:#4dd890">Contango (normal):</strong> Monat 2 teurer als Monat 1. Der Markt erwartet in Zukunft mehr Ruhe als jetzt.<br><br><strong style="color:#ff7070">Backwardation (Warnung):</strong> Monat 1 teurer als Monat 2. Der Markt hat <em>jetzt gerade</em> mehr Angst als in der Zukunft.</div>
  </div>
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">Mean Reversion — Rückkehr zum Mittelwert</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">Der VIX kehrt langfristig immer zu seinem Mittelwert (~19) zurück. Das ist statistisch belegt über 35 Jahre.<br><br>Wenn der VIX weit über seinen Durchschnitt gestiegen ist (Bedingung 3: 30%+), ist eine Rückkehr nach unten statistisch sehr wahrscheinlich — das ist die Grundlage unseres Einstiegs-Timings.</div>
  </div>
</div>

<div style="padding:14px 18px;background:rgba(240,192,96,0.07);border:1px solid rgba(240,192,96,0.28);border-radius:4px;font-size:12px;color:#7090b8;line-height:1.8;margin-bottom:8px">
  <strong style="color:#f0c060">Hinweis:</strong> Dieses Dashboard dient der Finanzbildung und stellt keine individuelle Anlageberatung dar. Historische Muster wiederholen sich nicht mit Sicherheit. Alle Entscheidungen liegen bei dir.
</div>

<div style="border-top:1px solid #2e4070;padding-top:16px;display:flex;justify-content:space-between;font-size:11px;color:#7090b8">
  <span style="font-family:'Syne',sans-serif;color:#f0c060;font-size:13px">meine-geldseite.de</span>
  <span>VIX Dashboard · {meta.get("updated_at","—")} · Yahoo Finance</span>
</div>

</div>

<div id="panel-info" class="tab-panel">
{info_html}
</div>

</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  var btns = {{'daily':'tab-daily','info':'tab-info'}};
  Object.entries(btns).forEach(([k,v]) => {{
    var btn = document.getElementById(v);
    if(k === name) {{
      btn.style.background='rgba(240,192,96,0.2)';
      btn.style.borderColor='rgba(240,192,96,0.5)';
      btn.style.color='#f0c060';
    }} else {{
      btn.style.background='transparent';
      btn.style.borderColor='#2e4070';
      btn.style.color='#7090b8';
    }}
  }});
  window.scrollTo({{top: 0, behavior: 'smooth'}});
}}
</script>

<script>
const gc='rgba(112,144,184,0.2)',tc='#7090b8';
const vixDates={jd},vixVals={jv},ma10={jm10},ma20={jm20},bbUp={jbu},bbLo={jbl};
const vvixDates={jvd},vvixVals={jvv};

if(vixVals&&vixVals.length>0){{
  new Chart(document.getElementById('cvix'),{{
    type:'line',
    data:{{labels:vixDates.map(d=>d.slice(5)),datasets:[
      {{label:'VIX',data:vixVals,borderColor:'#f0c060',borderWidth:2,pointRadius:0,tension:0.1,fill:false}},
      {{label:'MA10',data:ma10,borderColor:'#70b8ff',borderWidth:1.5,pointRadius:0,tension:0.1,fill:false}},
      {{label:'MA20',data:ma20,borderColor:'#7090b8',borderWidth:1,pointRadius:0,tension:0.1,fill:false}},
      {{label:'BB↑',data:bbUp,borderColor:'rgba(255,112,112,0.5)',borderWidth:1,borderDash:[4,3],pointRadius:0,tension:0.1,fill:'+1',backgroundColor:'rgba(255,112,112,0.04)'}},
      {{label:'BB↓',data:bbLo,borderColor:'rgba(77,216,144,0.35)',borderWidth:1,borderDash:[4,3],pointRadius:0,tension:0.1,fill:false}},
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
      plugins:{{legend:{{position:'top',labels:{{color:tc,font:{{size:10}},boxWidth:12,padding:10}}}},
        tooltip:{{backgroundColor:'#1a2540',borderColor:'#2e4070',borderWidth:1,titleColor:'#e8f0ff',bodyColor:'#c8d8f0',titleFont:{{size:11}},bodyFont:{{size:11}}}}}},
      scales:{{x:{{ticks:{{color:tc,font:{{size:9}},maxTicksLimit:8,maxRotation:0}},grid:{{color:gc}}}},
        y:{{ticks:{{color:tc,font:{{size:10}}}},grid:{{color:gc}}}}}}}}
  }});
}}

if(vvixVals&&vvixVals.length>0){{
  new Chart(document.getElementById('cvvix'),{{
    type:'line',
    data:{{labels:vvixDates.map(d=>d.slice(5)),datasets:[
      {{label:'VVIX',data:vvixVals,borderColor:'#ffaa55',borderWidth:2,pointRadius:0,tension:0.1,fill:true,backgroundColor:'rgba(255,170,85,0.08)'}},
      {{label:'Schwelle 120',data:Array(vvixVals.length).fill(120),borderColor:'rgba(77,216,144,0.4)',borderWidth:1,borderDash:[5,4],pointRadius:0,fill:false}}
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
      plugins:{{legend:{{position:'top',labels:{{color:tc,font:{{size:10}},boxWidth:12,padding:10}}}},
        tooltip:{{backgroundColor:'#1a2540',borderColor:'#2e4070',borderWidth:1,titleColor:'#e8f0ff',bodyColor:'#c8d8f0',titleFont:{{size:11}},bodyFont:{{size:11}}}}}},
      scales:{{x:{{ticks:{{color:tc,font:{{size:9}},maxRotation:45,maxTicksLimit:8}},grid:{{color:gc}}}},
        y:{{min:95,max:160,ticks:{{color:tc,font:{{size:10}}}},grid:{{color:gc}}}}}}}}
  }});
}}
</script>
</body>
</html>"""

def _build_info_html():
    """Returns the full Hintergrundwissen info tab HTML (unchanged)."""
    return '''<div style="background:#0a0d12;padding:24px;font-family:'Inter',sans-serif">
<style>
  .info-wrap { max-width:1060px; margin:0 auto; color:#d8dde8; font-family:'Inter',sans-serif; font-size:14px; line-height:1.7; }
  .info-wrap h1 { font-family:'Syne',sans-serif; font-size:clamp(28px,4vw,48px); font-weight:800; color:#fff; margin-bottom:14px; line-height:1.1; }
  .info-wrap h1 span { color:#f0c060; }
  .info-wrap h2 { font-family:'Syne',sans-serif; font-size:24px; font-weight:700; color:#fff; margin-bottom:8px; }
  .info-wrap p { color:#d8dde8; margin-bottom:12px; line-height:1.8; }
  .info-wrap section { padding:36px 0; border-bottom:1px solid #1e2535; }
  .info-wrap section:last-child { border-bottom:none; }
  .sec-label { font-size:10px; letter-spacing:3px; text-transform:uppercase; color:#f0c060; margin-bottom:20px; display:flex; align-items:center; gap:12px; }
  .sec-label::after { content:''; flex:1; height:1px; background:#1e2535; }
  .tag-pill { display:inline-block; background:rgba(240,192,64,0.12); color:#f0c060; border:1px solid rgba(240,192,64,0.3); padding:3px 12px; font-size:10px; letter-spacing:2px; text-transform:uppercase; margin-bottom:16px; }
  .regime-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:2px; margin:28px 0; }
  .regime-card { background:#111620; border:1px solid #1e2535; padding:24px; position:relative; }
  .regime-card::before { content:''; position:absolute; top:0; left:0; width:3px; height:100%; }
  .rc-green::before { background:#2ecc71; } .rc-yellow::before { background:#f39c12; } .rc-orange::before { background:#e05c3a; } .rc-red::before { background:#e74c3c; }
  .regime-range { font-family:'Syne',sans-serif; font-size:26px; font-weight:700; color:#fff; margin-bottom:4px; }
  .regime-name { font-size:10px; letter-spacing:2px; text-transform:uppercase; margin-bottom:18px; }
  .rc-green .regime-name{color:#2ecc71} .rc-yellow .regime-name{color:#f39c12} .rc-orange .regime-name{color:#e05c3a} .rc-red .regime-name{color:#e74c3c}
  .stat-row { display:flex; justify-content:space-between; padding:7px 0; border-top:1px solid #1e2535; font-size:13px; }
  .stat-label { color:#5a6478; } .stat-pos{color:#2ecc71} .stat-neg{color:#e74c3c} .stat-warn{color:#f39c12}
  .regime-verdict { margin-top:14px; padding:9px 11px; font-size:11px; line-height:1.5; border-radius:2px; }
  .rc-green .regime-verdict{background:rgba(46,204,113,0.08);color:#7de8a4;border:1px solid rgba(46,204,113,0.2)}
  .rc-yellow .regime-verdict{background:rgba(243,156,18,0.08);color:#f8c56b;border:1px solid rgba(243,156,18,0.2)}
  .rc-orange .regime-verdict{background:rgba(224,92,58,0.08);color:#f09070;border:1px solid rgba(224,92,58,0.2)}
  .rc-red .regime-verdict{background:rgba(231,76,60,0.08);color:#f08080;border:1px solid rgba(231,76,60,0.2)}
  .fw-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}
  .fw-box{background:#111620;border:1px solid #1e2535;padding:20px}
  .fw-box h3{font-family:'Syne',sans-serif;font-size:15px;color:#fff;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #1e2535}
  .rule-item{display:flex;gap:10px;margin-bottom:10px;align-items:flex-start}
  .rule-dot{width:5px;height:5px;border-radius:50%;margin-top:7px;flex-shrink:0}
  .rule-text{font-size:13px;line-height:1.6;color:#d8dde8}
  .disclaimer{background:rgba(224,92,58,0.06);border:1px solid rgba(224,92,58,0.2);padding:16px 20px;margin-top:24px;font-size:12px;color:#5a6478;line-height:1.7;border-radius:2px}
  .tl-bar { height:44px; background:#111620; border:1px solid #1e2535; border-radius:3px; overflow:hidden; display:flex; margin:10px 0 6px; }
  .tl-seg { display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:500; }
  .tl-labels { display:flex; justify-content:space-between; font-size:10px; color:#5a6478; margin-bottom:4px; }
  .slider-wrap { background:#111620; border:1px solid #1e2535; padding:28px; margin:28px 0; }
  .slider-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
  .slider-title { color:#fff; font-family:'Syne',sans-serif; font-size:17px; font-weight:700; }
  .slider-val { font-family:'Syne',sans-serif; font-size:30px; font-weight:700; color:#f0c060; }
  input[type=range]{-webkit-appearance:none;width:100%;height:4px;background:#1e2535;outline:none;border-radius:2px;cursor:pointer;margin:14px 0}
  input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;background:#f0c060;cursor:pointer;box-shadow:0 0 10px rgba(240,192,64,0.5)}
  .slider-ticks{display:flex;justify-content:space-between;font-size:10px;color:#5a6478;margin-bottom:20px}
  .signal-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
  .signal-box{background:#0a0d12;border:1px solid #1e2535;padding:18px;text-align:center}
  .signal-icon{font-size:24px;margin-bottom:7px}
  .signal-asset{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#5a6478;margin-bottom:5px}
  .signal-action{font-size:13px;font-weight:600;color:#fff;margin-bottom:3px}
  .signal-detail{font-size:11px;color:#5a6478}
  .data-table{width:100%;border-collapse:collapse;margin:20px 0;font-size:13px}
  .data-table th{text-align:left;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#5a6478;padding:10px 14px;border-bottom:1px solid #1e2535;font-weight:400}
  .data-table td{padding:12px 14px;border-bottom:1px solid rgba(30,37,53,0.5)}
  .data-table tr:hover td{background:rgba(240,192,64,0.02)}
  .crisis-pill{display:inline-block;padding:2px 8px;font-size:10px;letter-spacing:1px;border-radius:1px}
  .corr-row{display:flex;align-items:center;margin-bottom:10px;gap:10px}
  .corr-lbl{width:90px;font-size:11px;color:#5a6478;flex-shrink:0}
  .corr-wrap{flex:1;height:20px;background:#111620;border:1px solid #1e2535;position:relative;overflow:hidden}
  .corr-bar{height:100%;position:absolute;left:50%}
  .corr-val{width:55px;text-align:right;font-size:12px;font-weight:500}
  @media(max-width:600px){.regime-grid,.fw-grid,.signal-grid{grid-template-columns:1fr}}
</style>
<div class="info-wrap">
  <div class="tag-pill">Research-Report · meine-geldseite.de</div>
  <h1>Der <span>VIX</span> als<br>Investitionsfilter</h1>
  <p style="color:#5a6478;font-size:13px;max-width:580px">Statistische Analyse: Ab welchem VIX-Level solltest du nicht mehr in Aktien investiert sein? 35 Jahre Daten, vier Regimes, ein klares Regelwerk.</p>
  <section>
    <div class="sec-label">01 · Grundlagen</div>
    <h2>Was der VIX wirklich misst</h2>
    <p>Der VIX (CBOE Volatility Index) ist kein Kurs und kein Trend – er ist die <em>implizite Volatilität</em> des S&P 500, abgeleitet aus Optionspreisen. Ein VIX von 20 bedeutet: Der Markt erwartet im nächsten Jahr Schwankungen von ±20%.</p>
    <p>Entscheidend: Der VIX ist <strong style="color:#f0c060">mean-reverting</strong> – er kehrt immer zu seinem Langzeitmittelwert zurück (~19–20). Werte über 30 sind statistisch nicht stabil.</p>
    <div class="tl-labels"><span>VIX-Langzeitverlauf 1990–2026</span><span>Durchschnitt: ~19.5</span></div>
    <div class="tl-bar">
      <div class="tl-seg" style="width:38%;background:rgba(46,204,113,0.25);color:#7de8a4">VIX &lt;15</div>
      <div class="tl-seg" style="width:32%;background:rgba(243,156,18,0.25);color:#f8c56b">15–25</div>
      <div class="tl-seg" style="width:18%;background:rgba(224,92,58,0.3);color:#f09070">25–35</div>
      <div class="tl-seg" style="width:12%;background:rgba(231,76,60,0.35);color:#f08080">&gt;35</div>
    </div>
    <div class="tl-labels"><span style="color:#2ecc71">38% der Zeit</span><span style="color:#f39c12">32%</span><span style="color:#e05c3a">18%</span><span style="color:#e74c3c">12%</span></div>
  </section>
  <section>
    <div class="sec-label">02 · Regime-Analyse</div>
    <h2>Die vier VIX-Regimes &amp; ihre Statistiken</h2>
    <div class="regime-grid">
      <div class="regime-card rc-green"><div class="regime-range">&lt; 15</div><div class="regime-name">Komfort-Zone</div><div class="stat-row"><span class="stat-label">Ø 12M-Return</span><span class="stat-pos">+10.4%</span></div><div class="stat-row"><span class="stat-label">Win-Rate 3M</span><span class="stat-pos">74%</span></div><div class="regime-verdict">✓ Ideale Bedingungen. Aktienquote: 80–100%</div></div>
      <div class="regime-card rc-yellow"><div class="regime-range">15–25</div><div class="regime-name">Normalbereich</div><div class="stat-row"><span class="stat-label">Ø 12M-Return</span><span class="stat-pos">+9.1%</span></div><div class="stat-row"><span class="stat-label">Win-Rate 3M</span><span class="stat-warn">61%</span></div><div class="regime-verdict">⚠ Akzeptabel. Aktienquote: 60–80%</div></div>
      <div class="regime-card rc-orange"><div class="regime-range">25–35</div><div class="regime-name">Stress-Zone</div><div class="stat-row"><span class="stat-label">Ø 12M-Return</span><span class="stat-pos">+8.3%</span></div><div class="stat-row"><span class="stat-label">Win-Rate 3M</span><span class="stat-neg">48%</span></div><div class="regime-verdict">✗ Reduktion. Aktienquote: 20–40%</div></div>
      <div class="regime-card rc-red"><div class="regime-range">&gt; 35</div><div class="regime-name">Panik / Krise</div><div class="stat-row"><span class="stat-label">Ø 12M-Return</span><span class="stat-pos">+22.1%</span></div><div class="stat-row"><span class="stat-label">Win-Rate 3M</span><span class="stat-neg">44%</span></div><div class="regime-verdict">⚡ Paradox: Kurzfristig gefährlich, langfristig beste Chance</div></div>
    </div>
  </section>
  <section>
    <div class="sec-label">03 · Signal-Generator</div>
    <h2>Dein VIX-Level → Deine Allokation</h2>
    <div class="slider-wrap">
      <div class="slider-header"><span class="slider-title">VIX-Stand eingeben:</span><span class="slider-val" id="sVal">20</span></div>
      <input type="range" id="sSlider" min="8" max="80" value="20" step="1">
      <div class="slider-ticks"><span>8</span><span>15</span><span>20</span><span>25</span><span>35</span><span>80</span></div>
      <div id="sAlert" style="padding:12px 16px;background:rgba(243,156,18,0.1);border:1px solid rgba(243,156,18,0.3);margin-bottom:18px;font-size:13px;color:#f8c56b;border-radius:2px">Regime: NORMALBEREICH</div>
      <div class="signal-grid">
        <div class="signal-box"><div class="signal-icon">📈</div><div class="signal-asset">Aktien</div><div class="signal-action" id="sEq">60–80%</div><div class="signal-detail" id="sEqD">Selektiv</div></div>
        <div class="signal-box"><div class="signal-icon">💵</div><div class="signal-asset">Cash</div><div class="signal-action" id="sCa">20–30%</div><div class="signal-detail" id="sCaD">Geldmarkt</div></div>
        <div class="signal-box"><div class="signal-icon">🪙</div><div class="signal-asset">Gold/BTC</div><div class="signal-action" id="sAl">0–10%</div><div class="signal-detail" id="sAlD">Hedge</div></div>
      </div>
    </div>
  </section>
  <section>
    <div class="sec-label">04 · Historische Kalibrierung</div>
    <h2>VIX-Spitzen in historischen Krisen</h2>
    <table class="data-table">
      <thead><tr><th>Ereignis</th><th>VIX-Peak</th><th>S&P Drawdown</th><th>12M danach</th></tr></thead>
      <tbody>
        <tr><td>Gulf War 1990</td><td style="color:#f09070">36.5</td><td style="color:#e74c3c">-19.9%</td><td style="color:#2ecc71">+26.3%</td></tr>
        <tr><td>Finanzkrise 2008</td><td style="color:#e74c3c"><strong>89.5</strong></td><td style="color:#e74c3c">-56.8%</td><td style="color:#2ecc71">+26.5%</td></tr>
        <tr><td>COVID 2020</td><td style="color:#e74c3c"><strong>85.5</strong></td><td style="color:#e74c3c">-33.9%</td><td style="color:#2ecc71">+74.8%</td></tr>
        <tr><td>Trump-Zölle 2025</td><td style="color:#f09070">60.1</td><td style="color:#e74c3c">-19%</td><td style="color:#5a6478">TBD</td></tr>
      </tbody>
    </table>
  </section>
  <section>
    <div class="sec-label">05 · Regelwerk</div>
    <h2>Der VIX-gestützte Investitionsrahmen</h2>
    <div class="fw-grid">
      <div class="fw-box"><h3 style="color:#2ecc71">✓ VIX unter 20</h3><div class="rule-item"><div class="rule-dot" style="background:#2ecc71"></div><div class="rule-text">80–100% Aktien, Trend folgen</div></div></div>
      <div class="fw-box"><h3 style="color:#f39c12">⚠ VIX 20–25</h3><div class="rule-item"><div class="rule-dot" style="background:#f39c12"></div><div class="rule-text">60–70% Aktien, engere Stopps</div></div></div>
      <div class="fw-box"><h3 style="color:#e05c3a">✗ VIX 25–35</h3><div class="rule-item"><div class="rule-dot" style="background:#e05c3a"></div><div class="rule-text">20–40% Aktien, defensiv</div></div></div>
      <div class="fw-box"><h3 style="color:#e74c3c">⚡ VIX über 35</h3><div class="rule-item"><div class="rule-dot" style="background:#e74c3c"></div><div class="rule-text">&lt;20% Aktien, Watchlist bauen</div></div></div>
    </div>
    <div class="disclaimer"><strong style="color:#e05c3a">Wichtiger Hinweis:</strong> Diese Analyse dient der Finanzbildung und stellt keine individuelle Anlageberatung dar.</div>
  </section>
</div>
<script>
(function() {
  var s = document.getElementById('sSlider'), v = document.getElementById('sVal'), a = document.getElementById('sAlert');
  var R = [{max:15,l:'KOMFORT-ZONE',d:'Optimal.',c:'rgba(46,204,113,0.1)',b:'rgba(46,204,113,0.3)',t:'#7de8a4',eq:'80–100%',eqD:'Voll investiert',ca:'0–15%',caD:'Reserve',al:'0–5%',alD:'Optional Gold'},
    {max:20,l:'NIEDRIGER NORMAL',d:'Gut.',c:'rgba(46,204,113,0.08)',b:'rgba(46,204,113,0.2)',t:'#a8e8b4',eq:'70–85%',eqD:'Qualität',ca:'10–25%',caD:'Geldmarkt',al:'5–10%',alD:'Gold'},
    {max:25,l:'NORMAL',d:'Aufmerksam.',c:'rgba(243,156,18,0.1)',b:'rgba(243,156,18,0.3)',t:'#f8c56b',eq:'60–75%',eqD:'Enge Stopps',ca:'20–30%',caD:'Aufbauen',al:'5–15%',alD:'Gold+BTC'},
    {max:30,l:'ERHÖHTE SPANNUNG',d:'Vorsicht.',c:'rgba(243,156,18,0.12)',b:'rgba(243,156,18,0.4)',t:'#fad080',eq:'40–55%',eqD:'Nur Qualität',ca:'30–45%',caD:'Cash hoch',al:'10–20%',alD:'Gold hoch'},
    {max:35,l:'STRESS',d:'Defensiv.',c:'rgba(224,92,58,0.1)',b:'rgba(224,92,58,0.3)',t:'#f09070',eq:'20–40%',eqD:'Defensiv',ca:'40–60%',caD:'Treasuries',al:'15–25%',alD:'Gold'},
    {max:50,l:'KRISE',d:'Cash.',c:'rgba(231,76,60,0.12)',b:'rgba(231,76,60,0.35)',t:'#f08080',eq:'<20%',eqD:'Krisenresist.',ca:'50–70%',caD:'Staatsanleihen',al:'15–25%',alD:'Gold-Hedge'},
    {max:999,l:'PANIK',d:'Watchlist!',c:'rgba(231,76,60,0.15)',b:'rgba(231,76,60,0.5)',t:'#ff9090',eq:'0–10%',eqD:'Raus!',ca:'60–80%',caD:'Cash+Gold',al:'20–30%',alD:'Max Gold'}];
  function u() {
    var val=+s.value; v.textContent=val;
    var col=val<15?'#2ecc71':val<20?'#27ae60':val<25?'#f39c12':val<35?'#e05c3a':'#e74c3c'; v.style.color=col;
    var r=R.find(x=>val<=x.max); a.style.background=r.c; a.style.borderColor=r.b; a.style.color=r.t;
    a.textContent='Regime: '+r.l+' · '+r.d;
    document.getElementById('sEq').textContent=r.eq; document.getElementById('sEqD').textContent=r.eqD;
    document.getElementById('sCa').textContent=r.ca; document.getElementById('sCaD').textContent=r.caD;
    document.getElementById('sAl').textContent=r.al; document.getElementById('sAlD').textContent=r.alD;
    s.style.background='linear-gradient(to right,'+col+' '+((val-8)/72*100)+'%,#1e2535 '+((val-8)/72*100)+'%)';
  }
  s.addEventListener('input',u); u();
})();
</script>
</div>'''

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching VIX data...")
    try:
        df_vix = fetch_ticker("^VIX","3mo")
        vix_signals = compute_signals(df_vix)
    except Exception as e:
        print(f"  ERROR: {e}"); vix_signals = {}
    vvix_data = fetch_vvix()
    spy_data  = fetch_spy()
    reentry   = count_reentry(vix_signals, vvix_data, spy_data)
    output = {
        "meta":{"updated_at":datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "updated_date":str(date.today()),"data_source":"Yahoo Finance via yfinance"},
        "vix":vix_signals,"vvix":vvix_data,"spy":spy_data,"reentry":reentry,
    }
    import os
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json","w") as f:
        json.dump(output, f, indent=2, default=str)
    html = build_html(output)
    with open("docs/index.html","w",encoding="utf-8") as f:
        f.write(html)
    print("  VIX update done")

if __name__ == "__main__":
    main()
