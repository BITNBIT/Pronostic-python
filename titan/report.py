"""Dashboard statica (docs/index.html) pubblicabile con GitHub Pages + riepilogo markdown."""
from __future__ import annotations

import json

from . import config as C


def build(state: dict) -> None:
    C.ensure_dirs()
    bt = {}
    f = C.OUTPUT_DIR / "backtest.json"
    if f.exists():
        bt = json.loads(f.read_text())
    payload = json.dumps({"state": state, "backtest": bt, "leagues": {k: v["name"] for k, v in C.LEAGUES.items()}},
                         ensure_ascii=False, default=str).replace("</", "<\\/")
    (C.DOCS_DIR / "index.html").write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    (C.DOCS_DIR / ".nojekyll").write_text("")
    _markdown(state, bt)


def _pct(x):
    return "-" if x is None else f"{x:.1%}"


def _markdown(state: dict, bt: dict) -> None:
    L = [f"# Pronostici TITAN v6 — aggiornato {state['generated'][:16].replace('T', ' ')}", ""]
    live = state.get("live", {})
    if live.get("n"):
        L += [f"**Storico live**: {live['n']} partite verificate · 1X2 {_pct(live['acc_1x2'])} · "
              f"O/U2.5 {_pct(live['acc_o25'])} · value bet {live['bets']} (ROI {_pct(live['bets_roi'])})", ""]
    L += ["| Data | Lega | Partita | 1 | X | 2 | Segno | O/U 2.5 | GG | Esatto | Value |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in state.get("predictions", []):
        vb = f"{p['vb_bet']} @{p['vb_odds']:.2f}" if p.get("vb_bet") else ""
        L.append(f"| {p['date']} {p['time']} | {C.LEAGUES[p['league']]['name']} | {p['home']} - {p['away']} | "
                 f"{p['p1']:.0%} | {p['px']:.0%} | {p['p2']:.0%} | **{p['pick']}** {'★' * int(p['stars'])} | "
                 f"{p['ou_pick']} {max(p['o25'], 1 - p['o25']):.0%} | {p['gg']:.0%} | {p['score']} | {vb} |")
    if bt.get("overall"):
        o = bt["overall"]
        L += ["", f"**Backtest walk-forward** ({o['n']} partite): accuratezza {_pct(o['acc'])} (mercato {_pct(o['acc_mk'])}), "
              f"log-loss {o['ll']} (mercato {o['ll_mk']})"]
    (C.OUTPUT_DIR / "PRONOSTICI.md").write_text("\n".join(L) + "\n", encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TITAN v6 Pronostici</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--mute:#5d6673;--line:#e3e6ea;--acc:#0b6bcb;--h:#1f8a5b;--d:#a07a12;--a:#c2410c;--good:#15803d;--bad:#b91c1c;--chip:#eef2f7}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1116;--card:#161a21;--ink:#e8ebef;--mute:#98a2b0;--line:#262c36;--acc:#5aa7ff;--h:#34c38f;--d:#e0b94a;--a:#ff8a5c;--good:#4ade80;--bad:#f87171;--chip:#1f2530}}
:root[data-theme=dark]{--bg:#0e1116;--card:#161a21;--ink:#e8ebef;--mute:#98a2b0;--line:#262c36;--acc:#5aa7ff;--h:#34c38f;--d:#e0b94a;--a:#ff8a5c;--good:#4ade80;--bad:#f87171;--chip:#1f2530}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:20px 56px 8px 16px;max-width:1200px;margin:auto;position:relative}h1{margin:0;font-size:22px;letter-spacing:-.01em}h1 span{color:var(--acc)}
.sub{color:var(--mute);font-size:13px;margin-top:4px}main{max-width:1200px;margin:auto;padding:0 16px 40px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi small{color:var(--mute)}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}nav button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 12px;border-radius:999px;cursor:pointer;font:inherit}
nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;color:var(--mute)}select,input{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{font-size:12px;color:var(--mute);font-weight:600;position:sticky;top:0;background:var(--card)}tr:last-child td{border-bottom:0}
.chip{display:inline-block;padding:1px 7px;border-radius:999px;background:var(--chip);font-size:12px}
.pb{display:flex;height:8px;border-radius:4px;overflow:hidden;width:130px;margin-top:4px}.pb i{display:block}
.m{font-weight:600}.mute{color:var(--mute)}.good{color:var(--good)}.bad{color:var(--bad)}.stars{color:var(--d);letter-spacing:1px}
.pick{display:inline-block;min-width:26px;text-align:center;border-radius:6px;padding:2px 6px;font-weight:700;color:#fff}
.vb{font-weight:700;color:var(--good)}section{display:none}section.on{display:block}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.note{color:var(--mute);font-size:12.5px;margin-top:14px}h3{margin:16px 0 8px;font-size:15px}
.tog{position:absolute;top:18px;right:16px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;width:32px;height:32px;cursor:pointer}
</style></head><body>
<header><h1>TITAN <span>v6</span> · pronostici Serie A / Serie B</h1><div class="sub" id="sub"></div>
<button class="tog" id="tg" title="tema">◐</button></header>
<main>
<div class="kpis" id="kpis"></div>
<nav id="nav"></nav>
<section id="s-next"><div class="bar">Lega <select id="fl"></select> Stelle min <select id="fs"><option value="1">1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
<label><input type="checkbox" id="fv"> solo value bet</label></div><div class="card"><table id="t-next"></table></div></section>
<section id="s-live"><div class="grid2"><div><h3>Ultime verifiche</h3><div class="card"><table id="t-live"></table></div></div>
<div><h3>Andamento value bet (unità)</h3><div class="card" id="c-pnl" style="padding:10px"></div><h3>Per mese</h3><div class="card"><table id="t-month"></table></div></div></div></section>
<section id="s-tab"><div class="grid2" id="tabs"></div></section>
<section id="s-bt"><div class="grid2"><div><h3>Stagioni (walk-forward, mai viste in training)</h3><div class="card"><table id="t-bt"></table></div>
<h3>Accuratezza per fascia di confidenza</h3><div class="card"><table id="t-conf"></table></div></div>
<div><h3>Calibrazione (prob. prevista vs frequenza reale)</h3><div class="card" id="c-cal" style="padding:10px"></div>
<h3>Value bet per soglia di edge</h3><div class="card"><table id="t-edge"></table></div></div></div></section>
<p class="note">Modello statistico (Elo + Poisson/Dixon-Coles + gradient boosting + logistica + mercato) aggiornato automaticamente. Nessuna garanzia di risultato: il gioco comporta perdite. Vietato ai minori di 18 anni. Gioca responsabilmente.</p>
</main>
<script>
const D=__DATA__;const S=D.state,B=D.backtest||{},L=D.leagues;
const $=s=>document.querySelector(s),pc=x=>x==null||isNaN(x)?'–':(x*100).toFixed(1)+'%',p0=x=>x==null||isNaN(x)?'–':Math.round(x*100)+'%',f2=x=>x==null||isNaN(x)?'–':(+x).toFixed(2);
try{const t=localStorage.getItem('titan-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}
$('#tg').onclick=()=>{const r=document.documentElement,d=matchMedia('(prefers-color-scheme: dark)').matches,cur=r.dataset.theme||(d?'dark':'light'),n=cur=='dark'?'light':'dark';r.dataset.theme=n;try{localStorage.setItem('titan-theme',n)}catch(e){}};
$('#sub').textContent=`Aggiornato ${S.generated.replace('T',' ').slice(0,16)} · ${S.data.matches.toLocaleString('it')} partite storiche (ultimo risultato ${S.data.last_result}) · ${S.predictions.length} partite in programma`;
const lv=S.live||{},o=B.overall||{},mv=(S.model||{}).valid_logloss||{};
const k=[["Pronostici verificati",lv.n||0,lv.pending?`${lv.pending} in attesa`:''],["Accuratezza 1X2 live",pc(lv.acc_1x2),`Over/Under ${pc(lv.acc_o25)}`],
["Value bet live",lv.bets||0,lv.bets?`ROI ${pc(lv.bets_roi)} · ${f2(lv.bets_units)} u`:'nessuna ancora'],
["Backtest 1X2",pc(o.acc),`mercato ${pc(o.acc_mk)} · ${o.n||0} partite`],["Log-loss backtest",o.ll==null?"–":(+o.ll).toFixed(4),`mercato ${o.ll_mk==null?"–":(+o.ll_mk).toFixed(4)} · più basso = meglio`]];
$('#kpis').innerHTML=k.map(x=>`<div class="kpi"><small>${x[0]}</small><b>${x[1]}</b><small>${x[2]}</small></div>`).join('');
const secs=[["next","Prossime partite"],["live","Storico live"],["tab","Classifiche"],["bt","Backtest"]];
$('#nav').innerHTML=secs.map((s,i)=>`<button data-s="${s[0]}" class="${i?'':'on'}">${s[1]}</button>`).join('');$('#s-next').classList.add('on');
$('#nav').onclick=e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x==b));document.querySelectorAll('section').forEach(x=>x.classList.toggle('on',x.id=='s-'+b.dataset.s))};
$('#fl').innerHTML='<option value="">Tutte</option>'+Object.entries(L).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
const col={'1':'var(--h)','X':'var(--d)','2':'var(--a)'};
function next(){const fl=$('#fl').value,fs=+$('#fs').value,fv=$('#fv').checked;
const r=S.predictions.filter(p=>(!fl||p.league==fl)&&p.stars>=fs&&(!fv||p.vb_bet));
$('#t-next').innerHTML='<tr><th>Data</th><th>Partita</th><th>1 · X · 2</th><th>Segno</th><th>Doppia</th><th>O/U 2.5</th><th>GG</th><th>xG</th><th>Esatto</th><th>Quote 1X2</th><th>Value bet</th></tr>'+
(r.length?r.map(p=>`<tr><td>${p.date.slice(5).split('-').reverse().join('/')} <span class="mute">${p.time||''}</span><br><span class="chip">${L[p.league]}</span> <span class="mute" style="font-size:11px">${p.model||''}</span></td>
<td><span class="m">${p.home}</span> <span class="mute">${p.form_h||''}</span><br><span class="m">${p.away}</span> <span class="mute">${p.form_a||''}</span></td>
<td>${p0(p.p1)} · ${p0(p.px)} · ${p0(p.p2)}<div class="pb"><i style="width:${p.p1*100}%;background:var(--h)"></i><i style="width:${p.px*100}%;background:var(--d)"></i><i style="width:${p.p2*100}%;background:var(--a)"></i></div></td>
<td><span class="pick" style="background:${col[p.pick]}">${p.pick}</span> <span class="stars">${'★'.repeat(p.stars)}</span><br><span class="mute">${p0(p.conf)}</span></td>
<td>${p.dc} <span class="mute">${p0(p.dc_p)}</span></td><td>${p.ou_pick.replace(' 2.5','')} <span class="mute">${p0(Math.max(p.o25,1-p.o25))}</span></td>
<td>${p.gg_pick} <span class="mute">${p0(p.gg_pick=='GG'?p.gg:1-p.gg)}</span></td><td>${f2(p.xg_h)} - ${f2(p.xg_a)}</td>
<td>${p.score}<br><span class="mute" style="font-size:11px">${(p.top_scores||'').split(', ').slice(1,3).join(' · ')}</span></td>
<td class="mute">${p.odds_1?f2(p.odds_1)+' · '+f2(p.odds_x)+' · '+f2(p.odds_2):'–'}</td>
<td>${p.vb_bet?`<span class="vb">${p.vb_bet} @${f2(p.vb_odds)}</span><br><span class="mute">edge ${pc(p.vb_edge)} · stake ${pc(p.vb_stake)}</span>`:'<span class="mute">–</span>'}</td></tr>`).join(''):'<tr><td colspan="11" class="mute">Nessuna partita con questi filtri.</td></tr>')}
['#fl','#fs','#fv'].forEach(s=>$(s).onchange=next);next();
const rec=lv.recent||[];$('#t-live').innerHTML='<tr><th>Data</th><th>Partita</th><th>Segno</th><th>Ris.</th><th>Value</th></tr>'+(rec.length?rec.map(r=>`<tr><td>${r.date}</td><td>${r.home} - ${r.away}</td><td>${r.pick} <span class="mute">${p0(r.conf)}</span></td><td class="${String(r.hit)=='true'||r.hit===true?'good':'bad'}">${r.fthg|0}-${r.ftag|0} (${r.result})</td><td>${r.vb_bet?`${r.vb_bet} @${f2(r.vb_odds)} <span class="${r.bet_pnl>0?'good':'bad'}">${r.bet_pnl>0?'+':''}${f2(r.bet_pnl)}</span>`:'–'}</td></tr>`).join(''):'<tr><td colspan="5" class="mute">Le verifiche compaiono dopo le prime partite giocate.</td></tr>');
$('#t-month').innerHTML='<tr><th>Mese</th><th>Partite</th><th>1X2</th><th>Unità value</th></tr>'+(lv.by_month||[]).map(m=>`<tr><td>${m.month}</td><td>${m.n}</td><td>${pc(m.acc)}</td><td class="${m.units>=0?'good':'bad'}">${f2(m.units)}</td></tr>`).join('');
function line(el,ys){if(!ys||!ys.length){el.innerHTML='<span class="mute">Nessuna value bet verificata.</span>';return}const W=520,H=160,mn=Math.min(0,...ys),mx=Math.max(0,...ys),sx=i=>i/(Math.max(ys.length-1,1))*W,sy=v=>H-(v-mn)/((mx-mn)||1)*H;
el.innerHTML=`<svg viewBox="-4 -4 ${W+8} ${H+8}" width="100%" height="170"><line x1="0" x2="${W}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line)"/><polyline fill="none" stroke="var(--acc)" stroke-width="2" points="${ys.map((y,i)=>sx(i)+','+sy(y)).join(' ')}"/></svg>`}
line($('#c-pnl'),lv.pnl_curve);
$('#tabs').innerHTML=Object.entries(S.tables||{}).map(([lg,t])=>`<div><h3>${L[lg]} · classifica calcolata dai risultati</h3><div class="card"><table><tr><th>#</th><th>Squadra</th><th>Pt</th><th>G</th><th>DR</th><th>Elo</th><th>Forma</th></tr>${t.map((r,i)=>`<tr><td>${i+1}</td><td class="m">${r.team}</td><td>${r.pts}</td><td>${r.g}</td><td>${r.gd>0?'+':''}${r.gd}</td><td>${r.elo}</td><td class="mute">${r.form}</td></tr>`).join('')}</table></div></div>`).join('');
$('#t-bt').innerHTML='<tr><th>Stagione</th><th>Partite</th><th>Acc.</th><th>Acc. mercato</th><th>Acc. senza quote</th><th>Log-loss</th><th>LL mercato</th><th>Value bet</th><th>ROI</th></tr>'+(B.seasons||[]).map(s=>`<tr><td>${s.season}</td><td>${s.n}</td><td>${pc(s.acc)}</td><td class="mute">${pc(s.acc_mk)}</td><td class="mute">${pc(s.acc_pure)}</td><td>${(+s.ll).toFixed(4)}</td><td class="mute">${s.ll_mk==null?'–':(+s.ll_mk).toFixed(4)}</td><td>${s.bets.n}</td><td class="${(s.bets.roi||0)>=0?'good':'bad'}">${pc(s.bets.roi)}</td></tr>`).join('');
$('#t-conf').innerHTML='<tr><th>Confidenza</th><th>Partite</th><th>Accuratezza</th></tr>'+(B.confidence||[]).map(c=>`<tr><td>${c.range}</td><td>${c.n}</td><td>${pc(c.acc)}</td></tr>`).join('');
$('#t-edge').innerHTML='<tr><th>Edge min</th><th>Giocate</th><th>Hit</th><th>ROI quote medie</th><th>ROI quote max</th></tr>'+(B.edge_sweep||[]).map(e=>`<tr><td>${pc(e.edge)}</td><td>${e.avg_odds.n}</td><td>${pc(e.avg_odds.hit)}</td><td class="${(e.avg_odds.roi||0)>=0?'good':'bad'}">${pc(e.avg_odds.roi)}</td><td class="mute">${pc(e.max_odds.roi)}</td></tr>`).join('');
(function(){const c=B.calibration||[],el=$('#c-cal');if(!c.length){el.innerHTML='<span class="mute">Esegui il backtest.</span>';return}const W=300,s=v=>v*W;
el.innerHTML=`<svg viewBox="-30 -10 ${W+40} ${W+40}" width="100%" style="max-width:380px"><rect x="0" y="0" width="${W}" height="${W}" fill="none" stroke="var(--line)"/><line x1="0" y1="${W}" x2="${W}" y2="0" stroke="var(--mute)" stroke-dasharray="4 4"/>${c.map(b=>`<circle cx="${s(b.pred)}" cy="${W-s(b.real)}" r="${3+Math.sqrt(b.n)/12}" fill="var(--acc)" fill-opacity=".75"><title>${b.bin}: prev ${pc(b.pred)} reale ${pc(b.real)} (${b.n})</title></circle>`).join('')}<text x="${W/2}" y="${W+26}" fill="var(--mute)" font-size="11" text-anchor="middle">probabilità prevista</text><text x="-18" y="${W/2}" fill="var(--mute)" font-size="11" text-anchor="middle" transform="rotate(-90 -18 ${W/2})">frequenza reale</text></svg>`})();
</script></body></html>
"""
