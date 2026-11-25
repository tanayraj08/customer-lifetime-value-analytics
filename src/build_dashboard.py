"""Step 8: build dashboard.html - one self-contained file (no external libraries, no internet).

Only small aggregated tables are embedded (never the 80 MB transaction table):
  monthly revenue by RFM segment, cohort activity by RFM segment, segment summary, KPIs.
Because every customer belongs to exactly one RFM segment, the "All" view is the exact sum of
the segment views. Segments are each customer's segment at the snapshot date (2011-12-09).
"""
import json

import pandas as pd

from common import OUTPUTS, RFM_ORDER, ROOT
from rfm_cohort import invoice_level, load_clean


def build_data():
    cust = pd.read_csv(OUTPUTS / "customer_model.csv")
    seg_of = cust.set_index("Customer ID")["RFM_Segment"]
    inv = invoice_level(load_clean())
    inv["seg"] = inv["Customer ID"].map(seg_of)
    inv["ym"] = inv["InvoiceDate"].dt.strftime("%Y-%m")
    monthly = (inv.groupby(["ym", "seg"])
                  .agg(revenue=("Revenue", "sum"), orders=("Invoice", "nunique"),
                       customers=("Customer ID", "nunique"))
                  .reset_index())
    monthly["revenue"] = monthly["revenue"].round(2)

    cohort_of = cust.set_index("Customer ID")["CohortMonth"]
    inv["cm"] = inv["Customer ID"].map(cohort_of)
    pm = inv["InvoiceDate"].dt.to_period("M")
    cmp_ = pd.PeriodIndex(inv["cm"], freq="M")
    inv["idx"] = (pm.dt.year - cmp_.year) * 12 + (pm.dt.month - cmp_.month) + 1
    act = inv.groupby(["seg", "cm", "idx"])["Customer ID"].nunique().rename("active").reset_index()
    size = cust.groupby(["RFM_Segment", "CohortMonth"]).size().rename("size").reset_index() \
        .rename(columns={"RFM_Segment": "seg", "CohortMonth": "cm"})
    cohort = act.merge(size, on=["seg", "cm"])

    kpi = (cust.groupby("RFM_Segment")
              .agg(customers=("Customer ID", "size"), revenue=("Monetary", "sum"),
                   orders=("Frequency", "sum"), clv=("PredictedCLV_26w", "sum"),
                   modeled=("PredictedCLV_26w", "count"))
              .reindex(RFM_ORDER).reset_index().rename(columns={"RFM_Segment": "seg"}))
    kpi["revenue"] = kpi["revenue"].round(2)
    kpi["clv"] = kpi["clv"].round(2)

    seg = pd.read_csv(OUTPUTS / "fact_segment_summary.csv")
    seg = seg.rename(columns={"RFM_Segment": "rfm", "CLV_Segment": "clv_seg",
                              "Customers": "customers", "HistoricalRevenue": "revenue",
                              "PredictedCLV26w": "clv"})[["rfm", "clv_seg", "customers",
                                                         "revenue", "clv"]]
    seg[["revenue", "clv"]] = seg[["revenue", "clv"]].round(2)

    mm = pd.read_csv(OUTPUTS / "fact_model_metrics.csv").set_index("Metric")["Value"]
    meta = {
        "snapshot": mm["RFM snapshot date"],
        "ret": [float(mm["Average month+1 retention"]), float(mm["Average month+3 retention"]),
                float(mm["Average month+6 retention"])],
        "totalClv": float(mm["Predicted 26-week CLV total"]),
    }
    return {"segments": RFM_ORDER, "monthly": monthly.to_dict("records"),
            "cohort": cohort.to_dict("records"), "kpi": kpi.to_dict("records"),
            "segSummary": seg.to_dict("records"), "meta": meta}


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Customer Lifetime Value &amp; Retention - Online Retail II</title>
<style>
.viz-root{color-scheme:light;--surface-0:#f4f3f0;--surface-1:#fcfcfb;--border:#e2e1dc;--text-primary:#0b0b0b;
 --text-secondary:#52514e;--text-muted:#7b7a74;--grid:#e7e6e2;--series-1:#2a78d6;--neutral-bar:#c4c3bc;
 --seq:#cde2fb,#9ec5f4,#6da7ec,#3987e5,#256abf,#184f95,#0d366b;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#121211;
 --surface-1:#1a1a19;--border:#2f2f2d;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--grid:#2c2c2a;
 --series-1:#3987e5;--neutral-bar:#4a4a46;--seq:#1f2a36,#1c3d66,#1c5cab,#2a78d6,#5598e7,#86b6ef,#b7d3f6;}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.viz-root{background:var(--surface-0);color:var(--text-primary);min-height:100vh;padding:24px}
.wrap{max-width:1200px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--text-secondary);font-size:13px;margin:0 0 16px}
.filters{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.filters label{font-size:13px;color:var(--text-secondary)}
select{font:inherit;font-size:14px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);
 background:var(--surface-1);color:var(--text-primary)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.kpi .label{font-size:12px;color:var(--text-secondary)}
.kpi .value{font-size:26px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .note{font-size:11px;color:var(--text-muted);margin-top:2px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
@media (max-width:900px){.grid2{grid-template-columns:1fr}}
.card h2{font-size:15px;margin:0 0 2px}
.card .desc{font-size:12px;color:var(--text-secondary);margin:0 0 8px}
svg text{fill:var(--text-secondary);font-size:11px}
.axis line,.axis path{stroke:var(--grid)}
#tip{position:fixed;pointer-events:none;background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);
 border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:9;line-height:1.45}
#tip b{font-variant-numeric:tabular-nums}
.foot{font-size:11.5px;color:var(--text-muted);margin-top:14px;line-height:1.5}
.heat-wrap{overflow-x:auto}
</style>
</head>
<body>
<div class="viz-root"><div class="wrap">
<h1>Customer Lifetime Value &amp; Retention</h1>
<p class="sub">UCI Online Retail II, 1 Dec 2009 - 9 Dec 2011 · 805,549 cleaned line items · snapshot __SNAPSHOT__ ·
amounts in dataset currency</p>
<div class="filters"><label for="seg">RFM segment</label><select id="seg"></select>
<span class="sub" style="margin:0">Filters every card and chart below.</span></div>
<div class="kpis" id="kpis"></div>
<div class="card" style="margin-bottom:12px"><h2>Monthly revenue</h2>
<p class="desc">Sum of Quantity x Price per month. Dec 2011 holds only 9 days of data.</p><div id="line"></div></div>
<div class="grid2">
 <div class="card"><h2>Predicted 26-week CLV by segment</h2>
 <p class="desc">RFM segment | CLV quartile. Repeat customers only; Champions | High CLV highlighted.</p><div id="bars"></div></div>
 <div class="card"><h2>Cohort retention</h2>
 <p class="desc">Share of each first-purchase cohort active N months later (months +1 to +12).</p>
 <div class="heat-wrap" id="heat"></div></div>
</div>
<p class="foot">Predicted CLV is a statistical forecast (BG/NBD purchase model x Gamma-Gamma spend model; lifetimes
customer_lifetime_value with time=26, freq="W", discount_rate=0.01 - lifetimes counts time in months, see README) for the
4,255 customers with at least one repeat purchase. It is not booked revenue or a guarantee:
a calibration/holdout test showed the model ranks customers well (r = 0.80) but over-predicts purchase volume.
The 2009-12 cohort contains every customer already active before the data starts, so its retention is inflated.
Segment = each customer's RFM segment at the snapshot date.</p>
<div id="tip"></div>
</div></div>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const fmtM = v => v === 0 ? '0' : Math.abs(v) >= 1e6 ? (v/1e6).toFixed(2).replace(/\.?0+$/,'')+'M' : Math.abs(v) >= 1e3 ? (v/1e3).toFixed(1)+'K' : v.toFixed(0);
const fmtN = v => v.toLocaleString('en-US', {maximumFractionDigits: 0});
const fmtP = v => (v*100).toFixed(1)+'%';
const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs={}, parent) => { const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const tip = $('#tip');
function showTip(html, ev){ tip.innerHTML = html; tip.style.display='block';
  const x = Math.min(ev.clientX+14, innerWidth - tip.offsetWidth - 8), y = Math.min(ev.clientY+14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x+'px'; tip.style.top = y+'px'; }
const hideTip = () => tip.style.display='none';

const sel = $('#seg');
['All customers', ...D.segments].forEach(s => { const o = document.createElement('option'); o.value=s; o.textContent=s; sel.appendChild(o); });
const inSeg = s => sel.value === 'All customers' || s === sel.value;

function kpis(){
  const k = D.kpi.filter(r => inSeg(r.seg));
  const sum = f => k.reduce((a,r)=>a+r[f],0);
  const cust = sum('customers'), rev = sum('revenue'), ord = sum('orders'), clv = sum('clv'), mod = sum('modeled');
  const c = D.cohort.filter(r => inSeg(r.seg) && r.idx === 2);
  const byCm = {}; c.forEach(r => { byCm[r.cm] = byCm[r.cm] || {a:0}; byCm[r.cm].a += r.active; });
  const sizes = {}; D.cohort.filter(r => inSeg(r.seg) && r.idx === 1).forEach(r => { sizes[r.cm] = (sizes[r.cm]||0) + r.size; });
  const rates = Object.keys(byCm).filter(cm => sizes[cm]).map(cm => byCm[cm].a / sizes[cm]);
  const m1 = rates.length ? rates.reduce((a,b)=>a+b,0)/rates.length : 0;
  const champ = D.segSummary.find(r => r.rfm==='Champions' && r.clv_seg==='High CLV');
  const cards = [
    ['Historical revenue', fmtM(rev), 'cleaned, Dec 2009 - Dec 2011'],
    ['Customers', fmtN(cust), fmtN(mod)+' repeat (CLV modelled)'],
    ['Orders (invoices)', fmtN(ord), 'AOV '+fmtN(rev/ord)],
    ['Predicted 26-week CLV', fmtM(clv), 'model forecast, not revenue'],
    ['Avg month+1 retention', fmtP(m1), 'unweighted mean across cohorts'],
    ['Champions | High CLV', inSeg('Champions') ? fmtN(champ.customers) : '-', inSeg('Champions') ? fmtM(champ.clv)+' predicted CLV' : 'not in this filter'],
  ];
  $('#kpis').innerHTML = cards.map(c => `<div class="card kpi"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="note">${c[2]}</div></div>`).join('');
}

function line(){
  const box = $('#line'); box.innerHTML='';
  const W = box.clientWidth || 1100, H = 260, m = {l:56,r:16,t:12,b:44};
  const months = [...new Set(D.monthly.map(r=>r.ym))].sort();
  const vals = months.map(ym => D.monthly.filter(r => r.ym===ym && inSeg(r.seg)));
  const rev = vals.map(a => a.reduce((s,r)=>s+r.revenue,0));
  const ords = vals.map(a => a.reduce((s,r)=>s+r.orders,0));
  const cus = vals.map(a => a.reduce((s,r)=>s+r.customers,0));
  const raw = Math.max(...rev)/4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1,2,2.5,5,10].map(k=>k*mag).find(v => v >= raw);
  const nT = Math.ceil(Math.max(...rev)*1.05/step), max = step*nT;
  const svg = el('svg', {width:W, height:H, viewBox:`0 0 ${W} ${H}`, role:'img', 'aria-label':'Monthly revenue line chart'}, box);
  const x = i => m.l + i*(W-m.l-m.r)/(months.length-1), y = v => H-m.b - v/max*(H-m.t-m.b);
  for (let i=0;i<=nT;i++){ const v=step*i; el('line',{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:'var(--grid)'},svg);
    const t=el('text',{x:m.l-6,y:y(v)+4,'text-anchor':'end'},svg); t.textContent=fmtM(v); }
  months.forEach((ym,i)=>{ if(i%2===0){ const t=el('text',{x:x(i),y:H-m.b+16,'text-anchor':'middle'},svg); t.textContent=ym; }});
  el('path',{d:rev.map((v,i)=>(i?'L':'M')+x(i)+' '+y(v)).join(''),fill:'none',stroke:'var(--series-1)','stroke-width':2},svg);
  rev.forEach((v,i)=>el('circle',{cx:x(i),cy:y(v),r:3,fill:'var(--series-1)'},svg));
  const guide = el('line',{y1:m.t,y2:H-m.b,stroke:'var(--text-muted)','stroke-dasharray':'3 3',visibility:'hidden'},svg);
  const dot = el('circle',{r:5,fill:'var(--series-1)',stroke:'var(--surface-1)','stroke-width':2,visibility:'hidden'},svg);
  const hit = el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent'},svg);
  hit.addEventListener('mousemove', ev => { const r = svg.getBoundingClientRect();
    const i = Math.max(0,Math.min(months.length-1,Math.round((ev.clientX-r.left-m.l)/((W-m.l-m.r)/(months.length-1)))));
    guide.setAttribute('x1',x(i)); guide.setAttribute('x2',x(i)); guide.setAttribute('visibility','visible');
    dot.setAttribute('cx',x(i)); dot.setAttribute('cy',y(rev[i])); dot.setAttribute('visibility','visible');
    const mom = i ? ((rev[i]-rev[i-1])/rev[i-1]*100).toFixed(1)+'%' : '-';
    showTip(`<div>${months[i]}</div>Revenue <b>${fmtN(rev[i])}</b><br>Orders <b>${fmtN(ords[i])}</b> · Customers <b>${fmtN(cus[i])}</b><br>MoM <b>${mom}</b>`, ev); });
  hit.addEventListener('mouseleave', ()=>{ hideTip(); guide.setAttribute('visibility','hidden'); dot.setAttribute('visibility','hidden'); });
}

function bars(){
  const box = $('#bars'); box.innerHTML='';
  const rows = D.segSummary.filter(r => r.clv > 0 && inSeg(r.rfm)).sort((a,b)=>b.clv-a.clv);
  const W = box.clientWidth || 540, bh = 18, gap = 6, m = {l:200,r:110,t:4,b:4};
  const H = m.t + m.b + rows.length*(bh+gap);
  const svg = el('svg',{width:W,height:H,viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Predicted CLV by segment bar chart'},box);
  const max = Math.max(...rows.map(r=>r.clv));
  rows.forEach((r,i)=>{ const y = m.t + i*(bh+gap), w = Math.max(2, r.clv/max*(W-m.l-m.r));
    const lab = el('text',{x:m.l-8,y:y+bh/2+4,'text-anchor':'end'},svg); lab.textContent = r.rfm+' | '+r.clv_seg.replace(' CLV','');
    const hi = r.rfm==='Champions' && r.clv_seg==='High CLV';
    const rect = el('rect',{x:m.l,y:y,width:w,height:bh,rx:4,fill: hi ? 'var(--series-1)' : 'var(--neutral-bar)'},svg);
    const v = el('text',{x:m.l+w+6,y:y+bh/2+4},svg); v.textContent = fmtM(r.clv)+' · '+fmtN(r.customers);
    const hit = el('rect',{x:0,y:y-gap/2,width:W,height:bh+gap,fill:'transparent'},svg);
    hit.addEventListener('mousemove', ev => showTip(`<div>${r.rfm} | ${r.clv_seg}</div>Customers <b>${fmtN(r.customers)}</b><br>Predicted 26w CLV <b>${fmtN(r.clv)}</b><br>Historical revenue <b>${fmtN(r.revenue)}</b><br>Share of total predicted CLV <b>${fmtP(r.clv/D.meta.totalClv)}</b>`, ev));
    hit.addEventListener('mouseleave', hideTip); });
  if (!rows.length) box.innerHTML = '<p class="desc">No modelled customers in this filter.</p>';
}

function heat(){
  const box = $('#heat'); box.innerHTML='';
  const rows = D.cohort.filter(r => inSeg(r.seg));
  const cms = [...new Set(D.cohort.map(r=>r.cm))].sort();
  const act = {}, size = {};
  rows.forEach(r => { act[r.cm+'|'+r.idx] = (act[r.cm+'|'+r.idx]||0) + r.active; if (r.idx===1) size[r.cm] = (size[r.cm]||0) + r.size; });
  const cols = [...Array(12).keys()].map(i=>i+2);
  const cw = 34, ch = 16, m = {l:110,t:18};
  const W = m.l + cols.length*cw + 4, H = m.t + cms.length*ch + 4;
  const svg = el('svg',{width:W,height:H,viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Cohort retention heatmap'},box);
  const css = getComputedStyle(document.querySelector('.viz-root'));
  const stops = css.getPropertyValue('--seq').split(',').map(h => h.trim()).map(h => [1,3,5].map(i=>parseInt(h.substr(i,2),16)));
  const mix = t => { const f = t*(stops.length-1), i = Math.min(Math.floor(f), stops.length-2), u = f-i;
    return 'rgb('+stops[i].map((v,k)=>Math.round(v+(stops[i+1][k]-v)*u)).join(',')+')'; };
  cols.forEach((c,j)=>{ const t=el('text',{x:m.l+j*cw+cw/2,y:12,'text-anchor':'middle'},svg); t.textContent='+'+(c-1); });
  cms.forEach((cm,i)=>{ if (!size[cm]) return;
    const t = el('text',{x:m.l-6,y:m.t+i*ch+ch/2+4,'text-anchor':'end'},svg); t.textContent = cm+' (n='+size[cm]+')';
    cols.forEach((c,j)=>{ const k = cm+'|'+c; if (!(k in act) && monthsAfter(cm) < c-1) return;
      const v = (act[k]||0)/size[cm];
      const r = el('rect',{x:m.l+j*cw+1,y:m.t+i*ch+1,width:cw-2,height:ch-2,rx:2,fill:mix(Math.min(v/0.45,1))},svg);
      r.addEventListener('mousemove', ev => showTip(`<div>Cohort ${cm}, month +${c-1}</div>Active <b>${fmtN(act[k]||0)}</b> of <b>${fmtN(size[cm])}</b><br>Retention <b>${fmtP(v)}</b>`, ev));
      r.addEventListener('mouseleave', hideTip); }); });
}
function monthsAfter(cm){ const [y,m] = cm.split('-').map(Number); const [sy,sm] = D.meta.snapshot.split('-').map(Number); return (sy-y)*12 + (sm-m); }

function render(){ kpis(); line(); bars(); heat(); }
sel.addEventListener('change', render);
addEventListener('resize', () => { line(); bars(); });
render();
</script>
</body>
</html>
"""


def main():
    data = build_data()
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"))) \
               .replace("__SNAPSHOT__", data["meta"]["snapshot"])
    out = ROOT / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
