/* Live game tracking for open picks. Polls ESPN's public scoreboard + box score feeds in the browser
   (no server) and fills window.LIVE[pickId] = {phase, line, text}. Never changes a pick's saved status;
   grading still comes from data/picks.json. Needs page globals: state, render, fam, isOpen. */
(function(root){
const API="https://site.api.espn.com/apis/site/v2/sports/";
const PATH={nfl:"football/nfl",cfb:"football/college-football",mlb:"baseball/mlb",nhl:"hockey/nhl",wnba:"basketball/wnba"};
const ALIAS={nhl:{SJ:"SJS",NJ:"NJD",LA:"LAK",TB:"TBL",UTAH:"UTA"},mlb:{CHW:"CWS",AZ:"ARI",ATH:"OAK"},
  cfb:{ALA:"BAMA",IU:"IND",BOIS:"BSU",MISSST:"MSST"},nfl:{WAS:"WSH"},wnba:{GSV:"GS",LVA:"LV",NYL:"NY"}};
const ab=(sp,x)=>{x=String(x||"").toUpperCase();return (ALIAS[sp]&&ALIAS[sp][x])||x};
const norm=s=>String(s||"").toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\b\.?/g,"").replace(/[^a-z]/g,"");
const f=v=>{const m=String(v??"").replace(/,/g,"").match(/-?\d+(\.\d+)?/);return m?parseFloat(m[0]):0};
const first=v=>f(String(v).split("/")[0]);
const second=v=>f(String(v).split("/")[1]);

/* flatten a summary boxscore into {athleteId, name, team, groups:{type:{label:value}}} */
function players(sum){
  const out=[];
  for(const t of (sum.boxscore&&sum.boxscore.players)||[]){
    const byId={};
    for(const g of t.statistics||[]){
      const type=g.type||g.name||"";
      for(const a of g.athletes||[]){
        const id=a.athlete.id,r=byId[id]||(byId[id]={id,name:a.athlete.displayName,team:t.team.abbreviation,groups:{}});
        const o={};(g.labels||[]).forEach((l,i)=>o[l]=a.stats[i]);
        r.groups[type]=Object.assign(r.groups[type]||{},o);
      }
    }
    out.push(...Object.values(byId));
  }
  return out;
}
const G=(p,t)=>p.groups[t]||{};
function ipOuts(ip){const[w,fr]=String(ip).split(".");return f(w)*3+f(fr||0)}

/* stat family (from the site's fam()) -> [value, unit label] or null if the box score can't give it */
function statFor(sp,fam,p){
  if(sp==="nhl"){
    const g=Object.values(p.groups).reduce((a,b)=>Object.assign(a,b),{});
    const m={"Shots on goal":["S","SOG"],"Blocked shots":["BS","blk"],"Hits":["HT","hits"],"Goals":["G","G"],"Assists":["A","A"],"Saves":["SV","saves"],"Goalie saves":["SV","saves"]};
    if(fam==="Points")return [f(g.G)+f(g.A),"pts"];
    const k=m[fam];return k&&g[k[0]]!=null?[f(g[k[0]]),k[1]]:null;
  }
  if(sp==="mlb"){
    const b=G(p,"batting"),pi=G(p,"pitching"),isP=Object.keys(pi).length>0&&pi.IP!=null;
    if(isP){const m={"Strikeouts":["K","K"],"Earned runs allowed":["ER","ER"],"Hits allowed":["H","H allowed"]};
      if(fam==="Pitching outs")return [ipOuts(pi.IP),"outs"];const k=m[fam];return k?[f(pi[k[0]]),k[1]]:null}
    const m={"Hits":["H","H"],"Runs":["R","R"],"RBIs":["RBI","RBI"],"Batter strikeouts":["K","K"],"Home runs":["HR","HR"]};
    if(fam==="Hits + runs + RBIs")return [f(b.H)+f(b.R)+f(b.RBI),"H+R+RBI"];
    const k=m[fam];return k&&b[k[0]]!=null?[f(b[k[0]]),k[1]]:null;
  }
  if(sp==="nfl"||sp==="cfb"){
    const pa=G(p,"passing"),ru=G(p,"rushing"),re=G(p,"receiving"),de=G(p,"defensive"),ki=G(p,"kicking");
    switch(fam){
      case"Passing yards":return pa.YDS!=null?[f(pa.YDS),"pass yds"]:null;
      case"Passing TDs":return pa.TD!=null?[f(pa.TD),"pass TD"]:null;
      case"Completions":case"Passing completions":return pa["C/ATT"]!=null?[first(pa["C/ATT"]),"cmp"]:null;
      case"Pass attempts":case"Passing attempts":return pa["C/ATT"]!=null?[second(pa["C/ATT"]),"att"]:null;
      case"Interceptions thrown":return pa.INT!=null?[f(pa.INT),"INT"]:null;
      case"Rushing yards":return ru.YDS!=null?[f(ru.YDS),"rush yds"]:null;
      case"Rushing attempts":return ru.CAR!=null?[f(ru.CAR),"car"]:null;
      case"Rushing TDs":return ru.TD!=null?[f(ru.TD),"rush TD"]:null;
      case"Receiving yards":return re.YDS!=null?[f(re.YDS),"rec yds"]:null;
      case"Receptions":return re.REC!=null?[f(re.REC),"rec"]:null;
      case"Longest reception":return re.LONG!=null?[f(re.LONG),"long"]:null;
      case"Rush + rec yards":return (ru.YDS!=null||re.YDS!=null)?[f(ru.YDS)+f(re.YDS),"yds"]:null;
      case"Tackles":case"Tackles + assists":return de.TOT!=null?[f(de.TOT),"tkl"]:null;
      case"Solo tackles":return de.SOLO!=null?[f(de.SOLO),"solo"]:null;
      case"Sacks":return de.SACKS!=null?[f(de.SACKS),"sacks"]:null;
      case"Kicking points":return ki.PTS!=null?[f(ki.PTS),"pts"]:null;
      case"FGs made":return ki.FG!=null?[first(ki.FG),"FG"]:null;
    }
    return null;
  }
  if(sp==="wnba"){
    const g=Object.values(p.groups).reduce((a,b)=>Object.assign(a,b),{});
    const n=k=>f(g[k]);
    const m={"Points":["PTS","pts"],"Rebounds":["REB","reb"],"Assists":["AST","ast"],"Steals":["STL","stl"],"Blocks":["BLK","blk"],"Turnovers":["TO","TO"]};
    if(fam==="Threes made")return g["3PT"]!=null?[first(g["3PT"]),"3PM"]:null;
    if(fam==="Blocks + steals")return [n("BLK")+n("STL"),"stocks"];
    if(fam==="Pts + reb")return [n("PTS")+n("REB"),"pts+reb"];
    if(fam==="Pts + ast")return [n("PTS")+n("AST"),"pts+ast"];
    if(fam==="Reb + ast")return [n("REB")+n("AST"),"reb+ast"];
    if(fam==="Pts + reb + ast")return [n("PTS")+n("REB")+n("AST"),"PRA"];
    const k=m[fam];return k&&g[k[0]]!=null?[n(k[0]),k[1]]:null;
  }
  return null;
}

/* "AWAY @ HOME" / "A vs B" -> [teamA, teamB] */
function gameTeams(g){const m=String(g||"").match(/([A-Z]{2,5})\s*(?:@|vs\.?)\s*([A-Z]{2,5})/);return m?[m[1],m[2]]:[]}
function etDate(d){const p=new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(d);return p.replace(/-/g,"")}

function matchEvent(sp,pick,events){
  const want=gameTeams(pick.game).map(x=>ab(sp,x)),t0=new Date(pick.startTime).getTime();
  let best=null,bs=0;
  for(const e of events){
    const c=e.competitions[0].competitors.map(x=>ab(sp,x.team.abbreviation));
    const hit=want.filter(w=>c.includes(w)).length;
    const dt=Math.abs(new Date(e.date).getTime()-t0)/36e5;
    const score=hit*10-dt;
    if(hit>=2&&dt<4||hit>=1&&dt<1.5){if(score>bs||!best){best=e;bs=score}}
  }
  return best;
}
function phaseOf(e){const t=e.status.type;return t.state==="in"?"live":t.state==="post"?"final":"pre"}
function scoreLine(e){const c=e.competitions[0].competitors.slice().sort((a,b)=>(a.homeAway==="away"?-1:1)-(b.homeAway==="away"?-1:1));
  return `${c[0].team.abbreviation} ${c[0].score||0}–${c[1].score||0} ${c[1].team.abbreviation}`}

const cache={sb:{},sum:{}};
async function getJSON(u){const r=await fetch(u);if(!r.ok)throw new Error(r.status);return r.json()}

async function poll(){
  const S=state,L=window.LIVE=window.LIVE||{};
  const now=Date.now(),open=S.picks.filter(p=>isOpen(p)&&p.startTime&&PATH[p.sport]&&now>new Date(p.startTime).getTime()-15*60e3&&now<new Date(p.startTime).getTime()+9*36e5);
  if(!open.length){if(Object.keys(L).length){root.LIVE={};render()}return 0}
  cache.sb={};const next={};let live=0;
  const keys=[...new Set(open.map(p=>p.sport+"|"+etDate(new Date(p.startTime))))];
  await Promise.all(keys.map(async k=>{const[sp,d]=k.split("|");
    try{cache.sb[k]=(await getJSON(`${API}${PATH[sp]}/scoreboard?dates=${d}&limit=400${sp==="cfb"?"&groups=80":""}`)).events||[]}catch(e){cache.sb[k]=null}}));
  const need={};
  for(const p of open){
    const evs=cache.sb[p.sport+"|"+etDate(new Date(p.startTime))];if(!evs)continue;
    const e=matchEvent(p.sport,p,evs);if(!e)continue;
    const ph=phaseOf(e);if(ph==="pre")continue;
    if(ph==="live")live++;
    (need[e.id]=need[e.id]||{e,sp:p.sport,picks:[]}).picks.push(p);
  }
  await Promise.all(Object.values(need).map(async n=>{
    const ck=n.sp+n.e.id,ph=phaseOf(n.e);
    try{if(ph==="live"||!cache.sum[ck])cache.sum[ck]=players(await getJSON(`${API}${PATH[n.sp]}/summary?event=${n.e.id}`))}catch(e){return}
    const pl=cache.sum[ck],det=n.e.status.type.shortDetail||"",head=`${scoreLine(n.e)}${ph==="live"?" · "+det:" · Final"}`;
    for(const p of n.picks){
      const row=pl.find(x=>String(x.id)===String(p.espnId))||pl.find(x=>norm(x.name)===norm(p.player));
      let text=null;
      if(row){const s=statFor(p.sport,fam(p),row);if(s)text=`${Math.round(s[0]*10)/10} ${s[1]}`}
      next[p.id]={phase:ph,line:head,text,played:!!row};
    }
  }));
  root.LIVE=next;root.LIVE_AT=new Date();render();return live;
}
function start(){
  let timer=null;
  const tick=async()=>{let live=0;try{live=await poll()}catch(e){}
    timer=setTimeout(tick,document.hidden?120e3:(live?30e3:90e3))};
  document.addEventListener("visibilitychange",()=>{if(!document.hidden){clearTimeout(timer);tick()}});
  tick();
}
root.Live={start,statFor,players,matchEvent,gameTeams,ab};
if(typeof module!=="undefined")module.exports=root.Live;
})(typeof window!=="undefined"?window:globalThis);
