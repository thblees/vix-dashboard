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
    r1=v.get("r1_active",False); r3=v.get("r3_active",False)
    r4=vv.get("r4_active",False); r5=spy.get("r5_hint",False)
    n=sum([r1,r3,r4,r5])
    if not r1:   s,l,a="NONE","Kein Wiedereinstieg — Bedingung 1 nicht erfüllt","Der VIX ist noch zu hoch. Warte bis er 3 Tage unter seinem 10-Tage-Durchschnitt liegt."
    elif n==1:   s,l,a="WAIT","Zu früh — weitere Bestätigungen fehlen noch","Bedingung 1 erfüllt, aber noch keine weiteren Bestätigungen. Morgen wieder prüfen."
    elif n==2:   s,l,a="CAUTIOUS","Vorsichtiger Einstieg möglich","Erste kleine Tranche kaufen (10–15% der Ziel-Aktienquote). Bedingung 2 auf CBOE manuell prüfen."
    elif n==3:   s,l,a="BUY","Klares Kaufsignal","Erste Kauftranche (20–25%). Zweite Tranche in einer Woche wenn Signale stabil bleiben."
    else:        s,l,a="STRONG_BUY","Starkes Kaufsignal — Aggressiver Einstieg","40–60% sofort kaufen. Rest in 2 Wochen aufbauen. Historisch beste Einstiegschancen."
    return {"r1":r1,"r3":r3,"r4":r4,"r5_hint":r5,"auto_conditions_met":n,
            "signal":s,"signal_label":l,"action":a}

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
    smap = {"NONE":"#ff7070","WAIT":"#ffaa55","CAUTIOUS":"#f0c060","BUY":"#4dd890","STRONG_BUY":"#80ffb8"}
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

    def ok_badge(ok, yes="✓ Erfüllt", no="✗ Nicht erfüllt"):
        c,t = ("#4dd890",yes) if ok else ("#ff7070",no)
        bg = "rgba(77,216,144,0.12)" if ok else "rgba(255,112,112,0.12)"
        return f'<span style="padding:4px 12px;border-radius:3px;font-size:13px;font-weight:700;background:{bg};color:{c}">{t}</span>'

    def step_card(num, icon, title, auto, what, check_html, result_ok, result_yes, result_no, detail="", is_manual=False):
        auto_lbl = ('<span style="font-size:11px;padding:2px 10px;border-radius:3px;background:rgba(77,216,144,0.12);color:#4dd890;border:1px solid rgba(77,216,144,0.3);font-weight:600">● Dashboard zeigt es automatisch</span>'
                    if auto else
                    '<span style="font-size:11px;padding:2px 10px;border-radius:3px;background:rgba(240,192,96,0.15);color:#f0c060;border:1px solid rgba(240,192,96,0.4);font-weight:600">⚠ Manuell auf externer Website prüfen</span>')
        return f'''<div style="background:#223058;border:1px solid #2e4070;border-radius:6px;overflow:hidden;margin-bottom:8px">
  <div style="display:flex;align-items:center;gap:12px;padding:13px 18px;background:rgba(255,255,255,0.03);border-bottom:1px solid #2e4070;flex-wrap:wrap">
    <div style="width:32px;height:32px;border-radius:50%;background:rgba(112,184,255,0.15);color:#70b8ff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;flex-shrink:0">{num}</div>
    <div style="font-size:20px;flex-shrink:0">{icon}</div>
    <div style="flex:1">
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

    # Schritte
    s1 = step_card("1","📊","Wie ist das aktuelle Markt-Klima?", True,
        f'Der <strong style="color:#e8f0ff">VIX (Volatilitätsindex)</strong> misst die Angst am Aktienmarkt. Je höher der VIX, desto nervöser ist der Markt.<br><br>'
        f'<strong style="color:#e8f0ff">Aktuell: VIX = {cv}</strong><br>'
        f'Unter 20 = ruhig. 20–30 = erhöht. Über 30 = Stress.',
        f'Schau auf das farbige Badge oben links.<br><br>'
        f'<strong style="color:{rc[0]}">{v.get("regime_label","—")}</strong><br>'
        f'Empfohlene Aktienquote: <strong style="color:{rc[0]}">{v.get("equity_pct","—")}</strong>',
        cv < 25, "VIX im grünen Bereich", f"VIX = {cv} — erhöht, Vorsicht geboten",
        f'Regime wird täglich um 22:30 Uhr automatisch aktualisiert.')

    r1_what = (f'Der VIX muss <strong style="color:#e8f0ff">3 Tage hintereinander</strong> unter seinem '
               f'10-Tage-Durchschnitt liegen. Das zeigt: die Angst beruhigt sich <em>nachhaltig</em>, '
               f'nicht nur kurz. Ein einzelner ruhiger Tag reicht nicht.')
    r1_over = '<strong style="color:#ff7070">ÜBER</strong>' if cv>cm10 else '<strong style="color:#4dd890">UNTER</strong>'
    r1_check = (f'Aktueller VIX: <strong style="color:#e8f0ff">{cv}</strong><br>'
                f'10-Tage-Durchschnitt: <strong style="color:#e8f0ff">{cm10}</strong><br>'
                f'VIX liegt {r1_over} dem Durchschnitt<br>'
                f'Bisheriger Streak: <strong style="color:#e8f0ff">{r1s} von 3 Tagen</strong>')
    s2 = step_card("2","📉","Beruhigt sich der VIX nachhaltig? (Pflichtbedingung)", True,
        r1_what, r1_check, r1a,
        "✓ Bedingung erfüllt — VIX 3 Tage unter Durchschnitt",
        f"✗ Noch nicht — erst {r1s} von 3 Tagen",
        "⚠ Ohne diese Bedingung kein Wiedereinstieg — egal wie andere aussehen.")

    s3 = step_card("3","📈","Beruhigt sich auch der Futures-Markt? (Manuell)", False,
        'VIX-Futures sind Wetten auf die künftige Angst. Im Normalfall sind <strong style="color:#e8f0ff">weiter entfernte Monate teurer</strong> als nahe — weil die Zukunft unsicherer ist (= <em>Contango</em>).<br><br>'
        'Wenn der nächste Monat <strong style="color:#ff7070">teurer</strong> ist als übernächste — Alarm! Der Markt hat jetzt mehr Angst als in Zukunft (= <em>Backwardation</em>).',
        'Öffne: <a href="https://www.cboe.com/tradable-products/vix/term-structure/" target="_blank" style="color:#70b8ff">cboe.com → VIX Term Structure</a><br><br>'
        'Schau auf die Tabelle mit den Monatswerten:<br>'
        '<strong style="color:#4dd890">Gut (Contango):</strong> Monat 1 &lt; Monat 2 &lt; Monat 3<br>'
        '<strong style="color:#ff7070">Schlecht (Backwardation):</strong> Monat 1 &gt; Monat 2',
        None, "", "", "Monat 1 = nächster Verfallstermin (~30 Tage). Monat 2 = übernächster (~60 Tage).",
        is_manual=True)

    r4_what = ('Der <strong style="color:#e8f0ff">VVIX</strong> ist die "Volatilität der Volatilität" — '
               'er misst wie nervös der VIX <em>selbst</em> gerade ist. Wenn der VVIX fällt, '
               'beruhigt sich der Markt von innen heraus — oft <em>bevor</em> der VIX selbst deutlich fällt. '
               'Ein frühes Warnsignal.')
    r4_check = (f'Aktueller VVIX: <strong style="color:#e8f0ff">{vviv}</strong><br>'
                f'Trend der letzten 5 Tage: <strong style="color:{"#4dd890" if vvit=="fällt" else "#ffaa55"}">{vvit}</strong><br>'
                f'Schwelle: unter 120 UND fallend')
    s4 = step_card("4","🔍","Beruhigt sich die Nervosität von innen? (VVIX)", True,
        r4_what, r4_check, r4a,
        "✓ VVIX unter 120 und fällt — Beruhigung sichtbar",
        f"✗ VVIX = {vviv} — noch zu hoch oder steigend",
        "Tipp: VVIX fällt oft als erstes — beobachte ihn täglich.")

    r5_what = ('Der Chart des S&P 500 muss bestätigen, dass der Markt einen Boden gefunden hat. '
               'Das erkennst du daran, dass er <strong style="color:#e8f0ff">keine neuen Tiefs mehr macht</strong> — '
               'sondern sich seitwärts bewegt oder ein höheres Tief bildet. '
               'Ohne Chartbestätigung kann ein Einstieg zu früh sein.')
    r5_check = (f'Öffne: <a href="https://www.tradingview.com/chart/?symbol=SPX" target="_blank" style="color:#70b8ff">TradingView → SPX Wochenchart</a><br><br>'
                f'Frage: Hat der S&P 500 in den letzten Tagen ein <em>neues Tief</em> gemacht?<br>'
                f'<strong style="color:#4dd890">Gut:</strong> Kein neues Tief seit mehreren Tagen<br>'
                f'<strong style="color:#ff7070">Schlecht:</strong> Immer neue Tiefs')
    s5 = step_card("5","📉","Bestätigt der S&P 500 Chart die Erholung? (Manuell)", False,
        r5_what, r5_check, r5a,
        "✓ Schätzung: Boden wahrscheinlich gebildet",
        f"✗ S&P noch nicht stabil — Tief vor {dsl} Tagen",
        "Schätzung des Dashboards — eigener Blick auf den Chart empfohlen.",
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

    # Aktuelles Signal hervorheben
    sig_label = re.get("signal_label","—")
    sig_action = re.get("action","—")

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
@media(max-width:700px){{
  [style*="grid-template-columns:1fr 1fr"],[style*="grid-template-columns:120px"]{{display:block!important}}
  [style*="grid-template-columns:220px"]{{display:block!important}}
}}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">meine-<span>geldseite</span>.de · VIX Dashboard</div>
  <div style="font-size:11px;color:#7090b8">Aktualisiert: {meta.get("updated_at","—")}</div>
</div>

<div class="w">

<!-- ══════════════════════════════════════════════
     BLOCK 1: TÄGLICHE CHECKLISTE — GANZ OBEN
═══════════════════════════════════════════════ -->
<h2>📋 Deine tägliche Checkliste</h2>
<p class="section-intro">Jeden Werktag nach 22:00 Uhr (nach US-Börsenschluss) diese 5 Punkte der Reihe nach abarbeiten. Dauert ca. 5 Minuten.</p>

{s1}
{s2}
{s3}
{s4}
{s5}

<!-- ══════ ERGEBNIS ══════ -->
<div style="background:#223058;border:2px solid {sc}44;border-radius:6px;padding:20px 22px;margin-bottom:8px">
  <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;margin-bottom:8px">Ergebnis heute — {re.get("auto_conditions_met",0)} von 4 automatischen Bedingungen erfüllt</div>
  <div style="font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:{sc};margin-bottom:8px">{sig_label}</div>
  <div style="font-size:14px;color:#c8d8f0;line-height:1.7;margin-bottom:16px">{sig_action}</div>
  <div style="background:#1a2540;border-radius:4px;overflow:hidden">
    <div style="padding:10px 14px;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7090b8;border-bottom:1px solid #2e4070">Was tue ich jetzt konkret?</div>
    {action_rows}
  </div>
  <div style="margin-top:12px;font-size:12px;color:#7090b8;padding:10px 14px;background:rgba(240,192,96,0.06);border:1px solid rgba(240,192,96,0.25);border-radius:4px">
    ⚠ <strong style="color:#f0c060">Wichtig:</strong> Bedingung 3 (Futures-Kurve) und Bedingung 5 (S&P 500 Chart) musst du immer selbst kurz manuell prüfen — das Dashboard kann das nicht automatisch. Kein Anlageberatung.
  </div>
</div>

<hr class="divider">

<!-- ══════════════════════════════════════════════
     BLOCK 2: AKTUELLE ZAHLEN IM ÜBERBLICK
═══════════════════════════════════════════════ -->
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

<!-- Charts -->
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

<!-- ══════════════════════════════════════════════
     BLOCK 3: ERKLÄRUNGEN & GLOSSAR
═══════════════════════════════════════════════ -->
<h2>📖 Was bedeuten die Begriffe?</h2>
<p class="section-intro">Hier findest du alle Fachbegriffe einfach erklärt.</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
  <div class="card">
    <div style="font-size:13px;font-weight:700;color:#f0c060;margin-bottom:8px">VIX — der Angst-Index</div>
    <div style="font-size:13px;color:#c8d8f0;line-height:1.75">Der VIX misst, wie stark die Anleger erwarten, dass der S&P 500 in den nächsten 30 Tagen schwankt. Er wird aus den Preisen von Optionen berechnet.<br><br><strong style="color:#e8f0ff">Faustregeln:</strong><br>Unter 15 = sehr ruhig, Bullenmarkt<br>15–20 = normal<br>20–30 = erhöht, Vorsicht<br>Über 30 = Stress / Krise<br>Über 50 = Panik</div>
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

def main():
    from datetime import datetime, date
    import warnings; warnings.filterwarnings('ignore')
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
    with open("docs/data.json","w") as f:
        json.dump(output, f, indent=2, default=str)
    html = build_html(output)
    with open("docs/index.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"  VIX: {vix_signals.get('current_vix','?')} · {vix_signals.get('regime_label','?')}")
    print(f"  Signal: {reentry.get('signal_label','?')}")
    print(f"  ✓ data.json + index.html geschrieben")

if __name__ == "__main__":
    main()
