"""
generate_dashboard.py
Liest CSVs aus dem /data Ordner und generiert index.html
"""

import csv, json, os, glob
from datetime import datetime, date
from collections import defaultdict

DATA_DIR = "data"

def find_csv(pattern):
    return sorted(glob.glob(os.path.join(DATA_DIR, f"*{pattern}*")))

def parse_sales_report(filepath):
    with open(filepath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}
    r = rows[0]
    return {
        "paid":    int(r.get("Number of paid tickets sold", 0) or 0),
        "free":    int(r.get("Number of free tickets sold", 0) or 0),
        "total":   int(r.get("Number of total tickets sold", 0) or 0),
        "revenue": float(r.get("Total ticket face value less discounts", 0) or 0),
        "net":     float(r.get("Your net sales", 0) or 0),
    }

def parse_host_report(filepath, event_date_str):
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
    orders = []
    with open(filepath, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("Order Status", "") in ("closed", "paid"):
                try:
                    od = datetime.strptime(row["Created at date"][:10], "%Y-%m-%d")
                    orders.append({
                        "days_before": (event_date - od).days,
                        "qty":   int(row.get("Ticket quantity", 0) or 0),
                        "gross": float(row.get("Gross sales", 0) or 0),
                        "types": row.get("Ticket types", ""),
                    })
                except Exception:
                    pass
    return orders

MAX_WEEKS = 33

def cum_line(orders, future_cutoff=None):
    result = []
    for w in range(MAX_WEEKS, -1, -1):
        thr = w * 7
        if future_cutoff is not None and w < future_cutoff:
            result.append(None)
        else:
            result.append(sum(o["qty"] for o in orders if o["days_before"] >= thr))
    # replace leading zeros with None
    started = False
    for i, v in enumerate(result):
        if v and v > 0:
            started = True
        if not started:
            result[i] = None
    return result

def ticket_mix(orders):
    e = j = k = 0.0
    for o in orders:
        types = [t.strip() for t in o["types"].split(",") if t.strip()]
        n = max(len(types), 1)
        per = o["qty"] / n
        for t in types:
            if "Kinder" in t or "Kind" in t: k += per
            elif "Jugend" in t or "Landjugend" in t: j += per
            else: e += per
    return [round(e), round(j), round(k)]

def early_bird(orders):
    eb = sum(o["qty"] for o in orders if "Early Bird" in o["types"] or "Oster" in o["types"])
    return [eb, sum(o["qty"] for o in orders) - eb]

YEARS = {
    "2024": {"sales": "sales_by_event_report_-_2023", "host": "host_report_-_2023", "event": "2024-07-12"},
    "2025": {"sales": "sales_by_event_report_-_2024", "host": "host_report_-_2024", "event": "2025-06-27"},
    "2026": {"sales": "sales_by_event_report_-_2025", "host": "host_report_-_2025", "event": "2026-06-05"},
}

data = {}
for year, cfg in YEARS.items():
    sf = find_csv(cfg["sales"])
    hf = find_csv(cfg["host"])
    sales  = parse_sales_report(sf[0]) if sf else {}
    orders = parse_host_report(hf[0], cfg["event"]) if hf else []
    days_left = (datetime.strptime(cfg["event"], "%Y-%m-%d") - datetime.now()).days
    cutoff = max(0, days_left // 7) if days_left > 0 else None
    data[year] = {
        "sales": sales, "orders": orders,
        "cum":   cum_line(orders, future_cutoff=cutoff),
        "mix":   ticket_mix(orders),
        "eb":    early_bird(orders),
        "cutoff": cutoff,
    }

labels = [str(w) for w in range(MAX_WEEKS, -1, -1)]

def val_at(cum, week):
    idx = MAX_WEEKS - week
    return cum[idx] if 0 <= idx < len(cum) else None

cutoff26 = data["2026"]["cutoff"] or 5
now26  = val_at(data["2026"]["cum"], cutoff26) or 0
now25  = val_at(data["2025"]["cum"], cutoff26) or 0
diff_pct = round((now26 - now25) / now25 * 100, 1) if now25 else 0
sign_str = ("+" if diff_pct >= 0 else "") + str(diff_pct) + " %"
sign_col = "#1D9E75" if diff_pct >= 0 else "#A32D2D"

def e(v): return f"{v:,.0f}".replace(",", ".") + " €"

s24, s25, s26 = data["2024"]["sales"], data["2025"]["sales"], data["2026"]["sales"]
m24, m25, m26 = data["2024"]["mix"], data["2025"]["mix"], data["2026"]["mix"]
b24, b25, b26 = data["2024"]["eb"],  data["2025"]["eb"],  data["2026"]["eb"]
t24, t25, t26 = s24.get("total",0), s25.get("total",0), s26.get("total",0)
r24, r25       = s24.get("revenue",0), s25.get("revenue",0)
g25t = f"+{round((t25-t24)/t24*100,1)} %" if t24 else ""
g25r = f"+{round((r25-r24)/r24*100,1)} %" if r24 else ""
ep  = lambda b: round(b[0]/(b[0]+b[1])*100) if (b[0]+b[1]) else 0
stand = date.today().strftime("%-d.%-m.%Y")

# ── JSON data for charts ─────────────────────────────────────────────────────
c24 = json.dumps(data["2024"]["cum"])
c25 = json.dumps(data["2025"]["cum"])
c26 = json.dumps(data["2026"]["cum"])
lbl = json.dumps(labels)

# ── Build HTML (no f-string for JS blocks) ───────────────────────────────────
HEAD = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TaF &amp; Draussen – Ticket Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#f5f5f3;color:#1a1a18;min-height:100vh;padding:2rem 1rem}
.container{max-width:960px;margin:0 auto}
.header{padding-bottom:1rem;border-bottom:1px solid #d3d1c7;margin-bottom:1.5rem}
.header h1{font-size:22px;font-weight:500}
.header p{font-size:13px;color:#5f5e5a;margin-top:4px}
.label{font-size:11px;color:#5f5e5a;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:1.5rem}
.kpi-card{background:#fff;border-radius:10px;padding:1rem 1.25rem;border:0.5px solid #d3d1c7}
.kpi-card.active{border:1.5px solid #1D9E75}
.kpi-year{font-size:11px;font-weight:500;color:#5f5e5a;margin-bottom:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.kpi-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.kpi-val{font-size:22px;font-weight:500;line-height:1.2}
.kpi-sub{font-size:12px;color:#5f5e5a;margin-top:2px}
.badge-live{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:500;background:#E1F5EE;color:#0F6E56}
.divider{border-top:0.5px solid #d3d1c7;margin-top:8px;padding-top:8px}
.section-title{font-size:15px;font-weight:500;margin:1.5rem 0 0.75rem}
.chart-wrap{position:relative;width:100%;margin-bottom:1.5rem}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;font-size:12px;color:#5f5e5a}
.legend span{display:flex;align-items:center;gap:5px}
.legend-dot{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:1.5rem}
.insight-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:2rem}
.insight-card{background:#fff;border-radius:8px;padding:.9rem 1rem;border-left:3px solid}
.insight-card.pos{border-color:#1D9E75}.insight-card.warn{border-color:#BA7517}.insight-card.info{border-color:#378ADD}
.insight-title{font-size:12px;font-weight:500;margin-bottom:3px}
.insight-text{font-size:11px;color:#5f5e5a;line-height:1.5}
footer{text-align:center;font-size:11px;color:#888;padding-top:1rem;border-top:0.5px solid #d3d1c7}
@media(max-width:600px){.kpi-grid,.charts-row,.insight-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">"""

BODY = f"""
  <div class="header">
    <h1>TaF &amp; Draussen – Ticket-Report</h1>
    <p>Vergleich 2024 &middot; 2025 &middot; 2026 (VVK laufend, Stand {stand})</p>
  </div>

  <div class="label">Gesamtübersicht</div>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-year"><span class="kpi-dot" style="background:#378ADD"></span>TaF 2024</div>
      <div class="kpi-val">{t24:,}</div>
      <div class="kpi-sub">Tickets &middot; {s24.get('paid',0)} bezahlt &middot; {s24.get('free',0)} frei</div>
      <div class="divider"><div style="font-size:13px;font-weight:500">{e(r24)}</div><div class="kpi-sub">Bruttoerlös &middot; Netto {e(s24.get('net',0))}</div></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-year"><span class="kpi-dot" style="background:#1D9E75"></span>TaF 2025</div>
      <div class="kpi-val">{t25:,} <span style="font-size:13px;color:#1D9E75;font-weight:400">{g25t}</span></div>
      <div class="kpi-sub">Tickets &middot; {s25.get('paid',0)} bezahlt &middot; {s25.get('free',0)} frei</div>
      <div class="divider"><div style="font-size:13px;font-weight:500">{e(r25)} <span style="font-size:11px;color:#1D9E75">{g25r}</span></div><div class="kpi-sub">Bruttoerlös &middot; Netto {e(s25.get('net',0))}</div></div>
    </div>
    <div class="kpi-card active">
      <div class="kpi-year"><span class="kpi-dot" style="background:#EF9F27"></span>TaF 2026 <span class="badge-live">VVK läuft</span></div>
      <div class="kpi-val">{t26:,}</div>
      <div class="kpi-sub">Tickets bisher &middot; {s26.get('paid',0)} bezahlt &middot; {s26.get('free',0)} frei</div>
      <div class="divider"><div style="font-size:13px;font-weight:500">{e(s26.get('revenue',0))}</div><div class="kpi-sub">Bruttoerlös bisher &middot; Netto {e(s26.get('net',0))}</div></div>
    </div>
  </div>

  <div class="section-title">VVK-Verlauf – kumulierte Ticketverkäufe (Wochen vor Event)</div>
  <div class="legend">
    <span><span class="legend-dot" style="background:#378ADD"></span>2024 – abgeschlossen</span>
    <span><span class="legend-dot" style="background:#1D9E75"></span>2025 – abgeschlossen</span>
    <span><span class="legend-dot" style="background:#EF9F27"></span>2026 – VVK aktiv</span>
  </div>
  <div class="chart-wrap" style="height:280px"><canvas id="cumChart"></canvas></div>

  <div class="charts-row">
    <div>
      <div class="section-title">Ticket-Mix nach Kategorie</div>
      <div class="legend">
        <span><span class="legend-dot" style="background:#378ADD"></span>Erwachsene</span>
        <span><span class="legend-dot" style="background:#1D9E75"></span>Jugendliche</span>
        <span><span class="legend-dot" style="background:#EF9F27"></span>Kinder</span>
      </div>
      <div class="chart-wrap" style="height:200px"><canvas id="mixChart"></canvas></div>
    </div>
    <div>
      <div class="section-title">Early Bird vs. Regulär</div>
      <div class="legend">
        <span><span class="legend-dot" style="background:#534AB7"></span>Early Bird / Aktionen</span>
        <span><span class="legend-dot" style="background:#B4B2A9"></span>Regulär</span>
      </div>
      <div class="chart-wrap" style="height:200px"><canvas id="ebChart"></canvas></div>
    </div>
  </div>

  <div class="section-title">Insights</div>
  <div class="insight-grid">
    <div class="insight-card pos">
      <div class="insight-title">2026 vs. 2025 (gleicher Zeitpunkt)</div>
      <div class="insight-text">{now26} Tickets (2026) vs. {now25} (2025) – <span style="color:{sign_col};font-weight:500">{sign_str}</span> zum gleichen Zeitpunkt im Vorjahr.</div>
    </div>
    <div class="insight-card warn">
      <div class="insight-title">Schlussphase entscheidend</div>
      <div class="insight-text">2024 &amp; 2025 verkauften je ~200 Tickets in den letzten 5 Wochen. Wie entwickelt sich 2026?</div>
    </div>
    <div class="insight-card info">
      <div class="insight-title">Early Bird Anteil 2026</div>
      <div class="insight-text">{ep(b26)} % Early Bird bisher – vs. {ep(b25)} % (2025) und {ep(b24)} % (2024).</div>
    </div>
  </div>

  <footer>TaF &amp; Draussen &middot; Daten: Universe Ticketing &middot; Stand {stand}</footer>
</div>"""

# JS with raw strings (no f-string) to avoid brace issues
SCRIPT = (
    "\n<script>\n"
    "const labels=" + lbl + ";\n"
    "const cum24=" + c24 + ";\n"
    "const cum25=" + c25 + ";\n"
    "const cum26=" + c26 + ";\n"
    "const mix24=" + json.dumps(m24) + ";\n"
    "const mix25=" + json.dumps(m25) + ";\n"
    "const mix26=" + json.dumps(m26) + ";\n"
    "const eb24=" + json.dumps(b24) + ";\n"
    "const eb25=" + json.dumps(b25) + ";\n"
    "const eb26=" + json.dumps(b26) + ";\n"
    "const g='rgba(0,0,0,0.06)',t='#888';\n"
    "new Chart(document.getElementById('cumChart'),{type:'line',data:{labels,datasets:["
    "{label:'2024',data:cum24,borderColor:'#378ADD',backgroundColor:'rgba(55,138,221,0.08)',tension:.3,pointRadius:2,borderWidth:2,spanGaps:false},"
    "{label:'2025',data:cum25,borderColor:'#1D9E75',backgroundColor:'rgba(29,158,117,0.08)',tension:.3,pointRadius:2,borderWidth:2,spanGaps:false},"
    "{label:'2026',data:cum26,borderColor:'#EF9F27',backgroundColor:'rgba(239,159,39,0.1)',tension:.3,pointRadius:3,borderWidth:2.5,borderDash:[5,3],spanGaps:false}"
    "]},options:{responsive:true,maintainAspectRatio:false,"
    "plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false,callbacks:{label:(c)=>c.raw!=null?`${c.dataset.label}: ${c.raw} Tickets`:`${c.dataset.label}: -`}}},"
    "scales:{x:{grid:{color:g},ticks:{color:t,font:{size:11},maxTicksLimit:12},title:{display:true,text:'Wochen vor Event',color:t,font:{size:11}}},"
    "y:{beginAtZero:true,grid:{color:g},ticks:{color:t,font:{size:11}},title:{display:true,text:'Kumulierte Tickets',color:t,font:{size:11}}}}}});\n"
    "new Chart(document.getElementById('mixChart'),{type:'bar',data:{labels:['2024','2025','2026'],datasets:["
    "{label:'Erwachsene',data:mix24,backgroundColor:'#378ADD'},"
    "{label:'Jugendliche',data:mix25,backgroundColor:'#1D9E75'},"
    "{label:'Kinder',data:mix26,backgroundColor:'#EF9F27'}"
    "]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},"
    "scales:{x:{stacked:true,grid:{color:g},ticks:{color:t,font:{size:11}}},y:{stacked:true,beginAtZero:true,grid:{color:g},ticks:{color:t,font:{size:11}}}}}});\n"
    "new Chart(document.getElementById('ebChart'),{type:'bar',data:{labels:['2024','2025','2026'],datasets:["
    "{label:'Early Bird',data:[eb24[0],eb25[0],eb26[0]],backgroundColor:'#534AB7'},"
    "{label:'Regulaer',data:[eb24[1],eb25[1],eb26[1]],backgroundColor:'#B4B2A9'}"
    "]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false}},"
    "scales:{x:{stacked:true,grid:{color:g},ticks:{color:t,font:{size:11}}},y:{stacked:true,grid:{display:false},ticks:{color:t,font:{size:11}}}}}});\n"
    "</script>\n</body>\n</html>"
)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(HEAD + BODY + SCRIPT)

print(f"index.html generiert – Stand {stand}")
print(f"  2024: {t24} Tickets, {e(r24)}")
print(f"  2025: {t25} Tickets, {e(r25)}")
print(f"  2026: {t26} Tickets bisher, {e(s26.get('revenue',0))}")
