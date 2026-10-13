"""정류장 혼잡도 분석 및 HTML 시각화 스크립트.

- 혼잡도 = 정류장·시간대별 이용량(승차 + 하차 건수). 하차는 태그된 통행만 집계한다(stop_od.py와 동일 기준).
- 정류장 위치 지도형 산점도(시간대 선택), 혼잡 순위, 정류장×시간대 히트맵을 담은 단일 HTML 생성.
  외부 라이브러리·네트워크 없이 브라우저에서 바로 열린다.

실행: PYTHONIOENCODING=utf-8 python bus_data/analysis/stop_congestion.py
산출: bus_data/analysis/output/stop_congestion/{stop_hour_congestion.csv, stop_congestion.html}
"""

import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent
OUT_DIR = BASE_DIR / "output" / "stop_congestion"

sys.path.insert(0, str(DATA_DIR))
sys.path.insert(0, str(BASE_DIR))
from read_bus_data import load_alighting, load_routes  # noqa: E402
from stop_od import build_stop_master, stop_volume  # noqa: E402


def stop_hour_congestion(trips: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    """정류장×시간(0~23) 이용량 long 테이블: 정류장ID, 시, 승차, 하차, 이용량."""
    board = (trips.assign(시=trips["승차일시"].dt.hour).groupby(["승차정류장ID", "시"]).size()
             .rename("승차").rename_axis(["정류장ID", "시"]))
    alight_t = trips.dropna(subset=["하차정류장ID", "하차일시"])
    alight = (alight_t.assign(시=alight_t["하차일시"].dt.hour).groupby(["하차정류장ID", "시"]).size()
              .rename("하차").rename_axis(["정류장ID", "시"]))
    df = pd.concat([board, alight], axis=1).fillna(0).astype(int)
    df["이용량"] = df["승차"] + df["하차"]
    # 데이터에 나타난 시간 범위 전체를 모든 정류장에 채운다(빈 시간대 = 0)
    hours = range(int(df.index.get_level_values("시").min()), int(df.index.get_level_values("시").max()) + 1)
    full = pd.MultiIndex.from_product([stops["정류장ID"], hours], names=["정류장ID", "시"])
    df = df.reindex(full, fill_value=0).reset_index()
    return df.merge(stops[["정류장ID", "정류장명"]], on="정류장ID")


HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>정류장 혼잡도</title>
<style>
:root{--bg:#fff;--fg:#1f2430;--muted:#6b7280;--line:#e5e7eb;--card:#f8fafc;--accent:#2563eb;
--c0:#eef2ff;--c1:#c7d2fe;--c2:#818cf8;--c3:#4f46e5;--c4:#312e81}
@media(prefers-color-scheme:dark){:root{--bg:#12141a;--fg:#e6e8ee;--muted:#9aa3b2;--line:#2a2f3a;--card:#1a1d26;--accent:#60a5fa;
--c0:#1e2235;--c1:#2f3a6b;--c2:#4c5bb0;--c3:#7c8cf0;--c4:#c7d0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Malgun Gothic",sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.kpi b{display:block;font-size:20px}.kpi span{color:var(--muted);font-size:12px}
.ctrl{display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.ctrl input[type=range]{flex:1;min-width:180px}.ctrl output{font-weight:600;min-width:90px}
.grid{display:grid;grid-template-columns:3fr 2fr;gap:14px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card h2{font-size:14px;margin:0 0 8px}svg{width:100%;height:auto;display:block}
text{fill:var(--fg);font-size:11px}.mut{fill:var(--muted)}
.rank{display:grid;grid-template-columns:90px 1fr 36px;gap:6px;align-items:center;margin:3px 0;cursor:pointer}
.rank i{display:block;height:10px;border-radius:3px;background:var(--c3)}.rank.sel{font-weight:700}
.legend{display:flex;gap:4px;align-items:center;color:var(--muted);font-size:12px;margin-top:8px}
.legend s{width:22px;height:10px;display:inline-block;border-radius:2px}
#tip{position:fixed;pointer-events:none;background:var(--fg);color:var(--bg);padding:4px 8px;border-radius:6px;font-size:12px;display:none;z-index:9}
</style></head><body><main>
<h1>정류장 혼잡도</h1>
<p class="sub">혼잡도 = 정류장·시간대별 이용량(승차 + 하차). 하차는 태그된 통행만 집계. 기준: __SRC__</p>
<div class="kpis" id="kpis"></div>
<div class="ctrl"><label for="hour">시간대</label><input id="hour" type="range" min="0" max="0" value="0"><output id="hourOut"></output></div>
<div class="grid">
 <div class="card"><h2>정류장 위치별 혼잡 <span class="mut" style="font-weight:400">(원 크기·색 = 이용량)</span></h2><svg id="map" viewBox="0 0 560 420" role="img" aria-label="정류장 위치별 혼잡도"></svg>
  <div class="legend" id="legend"></div></div>
 <div class="card"><h2>혼잡 순위</h2><div id="rank"></div></div>
</div>
<div class="card" style="margin-top:14px"><h2>정류장 × 시간대 히트맵 <span class="mut" style="font-weight:400">(행 클릭 = 정류장 선택)</span></h2><svg id="heat" role="img" aria-label="정류장 시간대 히트맵"></svg></div>
</main><div id="tip"></div>
<script>
const D=__DATA__;
const hours=D.hours,stops=D.stops;let hi=0,selId=null;
const $=s=>document.querySelector(s),NS="http://www.w3.org/2000/svg";
const el=(t,a,p)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const maxAll=Math.max(...stops.flatMap(s=>s.v));
const colors=['--c0','--c1','--c2','--c3','--c4'];
const cls=v=>v<=0?0:Math.min(4,1+Math.floor(3.999*v/maxAll));
const css=n=>`var(${colors[n]})`;
const tip=$('#tip');
function showTip(e,t){tip.textContent=t;tip.style.display='block';tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY+12+'px'}
function hideTip(){tip.style.display='none'}
const fmt=h=>String(h).padStart(2,'0')+':00~'+String(h).padStart(2,'0')+':59';
const sl=$('#hour');sl.max=hours.length-1;
sl.addEventListener('input',()=>{hi=+sl.value;render()});
// KPI
const tot=stops.map(s=>s.v.reduce((a,b)=>a+b,0));
const hourTot=hours.map((_,i)=>stops.reduce((a,s)=>a+s.v[i],0));
const pk=hourTot.indexOf(Math.max(...hourTot));
const topStop=stops[tot.indexOf(Math.max(...tot))];
$('#kpis').innerHTML=[['정류장 수',stops.length],['전체 이용량',tot.reduce((a,b)=>a+b,0).toLocaleString()],
 ['가장 붐비는 시간대',fmt(hours[pk])],["종일 최다 정류장",topStop.name]].map(([k,v])=>`<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join('');
// legend
$('#legend').innerHTML='낮음 '+[0,1,2,3,4].map(n=>`<s style="background:${css(n)}"></s>`).join('')+' 높음 (최대 '+maxAll+'건)';
// map
const lats=stops.map(s=>s.lat),lons=stops.map(s=>s.lon);
const [la0,la1,lo0,lo1]=[Math.min(...lats),Math.max(...lats),Math.min(...lons),Math.max(...lons)];
const X=lo=>40+(lo-lo0)/(lo1-lo0||1)*480,Y=la=>380-(la-la0)/(la1-la0||1)*340;
function render(){
 hideTip();$('#hourOut').textContent=fmt(hours[hi]);sl.value=hi;
 const m=$('#map');m.innerHTML='';
 stops.forEach(s=>{const v=s.v[hi],g=el('g',{style:'cursor:pointer'},m);
  const c=el('circle',{cx:X(s.lon),cy:Y(s.lat),r:6+14*Math.sqrt(v/maxAll),fill:css(cls(v)),stroke:s.id===selId?'var(--accent)':'var(--muted)','stroke-width':s.id===selId?3:1,'fill-opacity':.85},g);
  el('text',{x:X(s.lon),y:Y(s.lat)-10-14*Math.sqrt(v/maxAll),'text-anchor':'middle'},g).textContent=s.name;
  g.onmousemove=e=>showTip(e,`${s.name} · ${v}건`);g.onmouseleave=hideTip;g.onclick=()=>{selId=selId===s.id?null:s.id;render()}});
 el('text',{x:40,y:410,class:'mut'},m).textContent='← 서쪽   동쪽 →  (위도·경도 기준 배치)';
 const r=[...stops].sort((a,b)=>b.v[hi]-a.v[hi]).slice(0,10);
 $('#rank').innerHTML=r.map(s=>`<div class="rank${s.id===selId?' sel':''}" data-id="${s.id}"><span>${s.name}</span><i style="width:${100*s.v[hi]/(r[0].v[hi]||1)}%"></i><span>${s.v[hi]}</span></div>`).join('');
 document.querySelectorAll('.rank').forEach(n=>n.onclick=()=>{selId=selId===n.dataset.id?null:n.dataset.id;render()});
 heat();
}
function heat(){
 const h=$('#heat'),rowH=18,lw=100,cw=Math.max(18,Math.floor(900/hours.length)),W=lw+cw*hours.length+10,H=24+rowH*stops.length;
 h.setAttribute('viewBox',`0 0 ${W} ${H}`);h.innerHTML='';
 hours.forEach((hr,i)=>{el('text',{x:lw+cw*i+cw/2,y:12,'text-anchor':'middle',class:i===hi?'':'mut'},h).textContent=hr});
 const order=[...stops].sort((a,b)=>b.v.reduce((x,y)=>x+y,0)-a.v.reduce((x,y)=>x+y,0));
 order.forEach((s,r)=>{const y=24+r*rowH;
  el('text',{x:lw-6,y:y+13,'text-anchor':'end',style:s.id===selId?'font-weight:700':''},h).textContent=s.name;
  s.v.forEach((v,i)=>{const c=el('rect',{x:lw+cw*i+1,y:y+1,width:cw-2,height:rowH-2,rx:2,fill:css(cls(v)),stroke:i===hi?'var(--accent)':(s.id===selId?'var(--muted)':'none')},h);
   c.onmousemove=e=>showTip(e,`${s.name} ${fmt(hours[i])} · ${v}건`);c.onmouseleave=hideTip;
   c.onclick=()=>{hi=i;selId=s.id;render()}})});
}
render();
</script></body></html>
"""


def build_html(cong: pd.DataFrame, stops: pd.DataFrame, source: str) -> str:
    hours = sorted(cong["시"].unique().tolist())
    pivot = cong.pivot(index="정류장ID", columns="시", values="이용량")[hours]
    data = {
        "hours": hours,
        "stops": [
            {"id": r.정류장ID, "name": r.정류장명, "lat": r.위도, "lon": r.경도, "v": pivot.loc[r.정류장ID].astype(int).tolist()}
            for r in stops.itertuples()
        ],
    }
    return HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__SRC__", source)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _, route_stops = load_routes()
    trips = load_alighting()
    stops = build_stop_master(route_stops)

    cong = stop_hour_congestion(trips, stops)

    # 정합성: 정류장별 합계가 stop_od.py의 stop_volume 합계와 같아야 한다
    vol = stop_volume(trips, stops).set_index("정류장ID")["합계"]
    mine = cong.groupby("정류장ID")["이용량"].sum()
    mism = (mine.reindex(vol.index).fillna(0).astype(int) != vol).sum()
    print(f"정류장 {len(stops)}개, 시간대 {cong['시'].nunique()}개, 정류장별 합계 불일치 {mism}건")
    if mism:
        sys.exit("stop_volume과 정류장별 합계가 일치하지 않습니다.")

    cong.sort_values(["정류장ID", "시"]).to_csv(OUT_DIR / "stop_hour_congestion.csv", index=False, encoding="utf-8-sig")
    source = f"통행 {len(trips):,}건, {trips['승차일시'].min():%Y-%m-%d} ~ {trips['승차일시'].max():%Y-%m-%d}"
    (OUT_DIR / "stop_congestion.html").write_text(build_html(cong, stops, source), encoding="utf-8")

    top = cong.groupby("정류장명")["이용량"].sum().nlargest(5)
    print("종일 이용량 상위 5:", ", ".join(f"{k}({v})" for k, v in top.items()))
    print(f"저장: {OUT_DIR}")


if __name__ == "__main__":
    main()
