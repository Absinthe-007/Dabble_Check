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
        const id=a.athlete.id,r=byId[id]||(byId[id]={id,name:a.athlete.displayName,team:t.team.abbreviation,groups:{},starter:null,pos:"",order:a.batOrder||0,dnp:false});
        if(a.starter!=null)r.starter=!!a.starter;
        if(a.didNotPlay)r.dnp=true;
        r.pos=r.pos||(a.position&&a.position.abbreviation)||(a.athlete.position&&a.athlete.position.abbreviation)||"";
        r.gtype=r.gtype||type;
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
function matchup(e){const c=e.competitions[0].competitors.slice().sort((a,b)=>(a.homeAway==="away"?-1:1)-(b.homeAway==="away"?-1:1));return `${c[0].team.abbreviation} @ ${c[1].team.abbreviation}`}
function scoreLine(e){const c=e.competitions[0].competitors.slice().sort((a,b)=>(a.homeAway==="away"?-1:1)-(b.homeAway==="away"?-1:1));
  return `${c[0].team.abbreviation} ${c[0].score||0}–${c[1].score||0} ${c[1].team.abbreviation}`}

/* compact stat line for the all-players view */
function lineFor(sp,p){
  const g=p.groups,v=(o,k)=>o&&o[k]!=null?o[k]:null,j=a=>a.filter(Boolean).join(" · ");
  if(sp==="mlb"){const b=g.batting,pi=g.pitching;
    if(pi&&pi.IP!=null)return j([`${pi.IP} IP`,`${pi.H} H`,`${pi.ER} ER`,`${pi.K} K`,`${pi.BB} BB`]);
    if(b)return j([`${b["H-AB"]}`,+b.R?`${b.R} R`:"",+b.RBI?`${b.RBI} RBI`:"",+b.HR?`${b.HR} HR`:"",+b.K?`${b.K} K`:"",+b.BB?`${b.BB} BB`:""]);return""}
  if(sp==="nhl"){const x=Object.values(g).reduce((a,b)=>Object.assign(a,b),{});
    if(x.SV!=null&&x.SA!=null)return `${x.SV}/${x.SA} SV`;
    if(x.TOI==null)return"";
    return j([`${f(x.G)}G ${f(x.A)}A`,`${f(x.S)} SOG`,+x.HT?`${x.HT} hit`:"",+x.BS?`${x.BS} blk`:"",x.TOI])}
  if(sp==="wnba"){const x=Object.values(g).reduce((a,b)=>Object.assign(a,b),{});
    if(p.dnp||x.PTS==null)return p.dnp?"DNP":"";return j([`${x.MIN} min`,`${x.PTS} pts`,`${x.REB} reb`,`${x.AST} ast`,+x.STL?`${x.STL} stl`:"",+x.BLK?`${x.BLK} blk`:""])}
  const o=[],pa=g.passing,ru=g.rushing,re=g.receiving,de=g.defensive,ki=g.kicking;
  if(pa&&pa["C/ATT"]!=null)o.push(`${pa["C/ATT"]} ${pa.YDS} yd ${pa.TD} TD ${pa.INT} INT`);
  if(ru&&ru.CAR!=null)o.push(`${ru.CAR} car ${ru.YDS} yd${+ru.TD?` ${ru.TD} TD`:""}`);
  if(re&&re.REC!=null)o.push(`${re.REC} rec ${re.YDS} yd${+re.TD?` ${re.TD} TD`:""}`);
  if(de&&de.TOT!=null)o.push(`${de.TOT} tkl${+de.SACKS?` ${de.SACKS} sk`:""}`);
  if(ki&&ki.FG!=null)o.push(`FG ${ki.FG}`);
  return o.join(" · ");
}
function ordered(sp,pl){
  const rank=p=>p.starter===true?0:p.starter===false?2:1;
  return pl.slice().sort((a,b)=>rank(a)-rank(b)||(a.order-b.order)||0);
}

async function getRoster(sp,id){
  const r=await getJSON(`${API}${PATH[sp]}/teams/${id}/roster`),a=r.athletes||[];
  const items=a.length&&a[0].items?a.flatMap(x=>x.items):a;
  return items.map(i=>({id:i.id,name:i.displayName||i.fullName,pos:(i.position&&i.position.abbreviation)||"",jersey:i.jersey||"",
    inj:(i.injuries&&i.injuries[0]&&i.injuries[0].status)||((i.status&&i.status.name&&i.status.name!=="Active")?i.status.name:"")}));
}
function rowOf(sp,r,b){
  const played=!!b&&Object.keys(b.groups).length>0&&!b.dnp,line=b?lineFor(sp,b):"";
  const st=b&&b.starter===true;
  return {id:r.id,name:r.name,pos:r.pos||(b&&b.pos)||"",jersey:r.jersey,inj:r.inj,starter:st,played,line,order:b?b.order||0:99,
    rank:st?0:played?1:b&&b.dnp?3:2};
}

const cache={sb:{},sum:{},ros:{}};
async function getJSON(u){const r=await fetch(u);if(!r.ok)throw new Error(r.status);return r.json()}

const openGames=new Set();            // event keys whose panel is expanded (their box scores get fetched)
async function poll(){
  const S=state,now=Date.now();
  const open=S.picks.filter(p=>isOpen(p)&&p.startTime&&PATH[p.sport]&&now>new Date(p.startTime).getTime()-15*60e3&&now<new Date(p.startTime).getTime()+9*36e5);
  cache.sb={};const next={},games={};let live=0;
  const etNow=new Date(),hr=+new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",hour12:false}).format(etNow);
  const dates=[etDate(etNow)];if(hr<7)dates.push(etDate(new Date(now-864e5)));
  const keys=new Set(open.map(p=>p.sport+"|"+etDate(new Date(p.startTime))));
  for(const sp of Object.keys(PATH))for(const d of dates)keys.add(sp+"|"+d);
  await Promise.all([...keys].map(async k=>{const[sp,d]=k.split("|");
    try{cache.sb[k]=(await getJSON(`${API}${PATH[sp]}/scoreboard?dates=${d}&limit=400${sp==="cfb"?"&groups=80":""}`)).events||[]}catch(e){cache.sb[k]=null}}));
  const need={};
  const want=(e,sp)=>{const id=sp+e.id;return need[id]||(need[id]={e,sp,picks:[],id})};
  for(const p of open){
    const evs=cache.sb[p.sport+"|"+etDate(new Date(p.startTime))];if(!evs)continue;
    const e=matchEvent(p.sport,p,evs);if(!e||phaseOf(e)==="pre")continue;
    want(e,p.sport).picks.push(p);
  }
  // every live or finished game today, any sport; box scores only for games with picks or an expanded panel
  const seen=new Set();
  for(const k of keys){const sp=k.split("|")[0];if(!dates.includes(k.split("|")[1]))continue;
    for(const e of cache.sb[k]||[]){const id=sp+e.id;if(seen.has(id))continue;seen.add(id);const ph=phaseOf(e);
      games[id]={id,sp,ph,e,line:ph==="pre"?matchup(e)+" · "+(e.status.type.shortDetail||""):scoreLine(e)+(ph==="live"?" · "+(e.status.type.shortDetail||""):" · Final"),teams:null};
      if(ph==="live")live++;
      if(openGames.has(id))want(e,sp)}}
  // rosters for every expanded game (so players who haven't played yet still show)
  const rosters={};
  await Promise.all(Object.values(games).filter(g=>openGames.has(g.id)).flatMap(g=>g.e.competitions[0].competitors.map(async c=>{
    const rk=g.sp+c.team.id;
    try{if(!cache.ros[rk])cache.ros[rk]=await getRoster(g.sp,c.team.id)}catch(e){}
    rosters[rk]=cache.ros[rk]||[]})));
  await Promise.all(Object.values(need).filter(n=>phaseOf(n.e)!=="pre").map(async n=>{
    const ck=n.id,ph=phaseOf(n.e);
    try{if(ph==="live"||!cache.sum[ck])cache.sum[ck]=players(await getJSON(`${API}${PATH[n.sp]}/summary?event=${n.e.id}`))}catch(e){return}
    const pl=cache.sum[ck],head=`${scoreLine(n.e)}${ph==="live"?" · "+(n.e.status.type.shortDetail||""):" · Final"}`;
    if(games[ck])games[ck].players=pl;
    for(const p of n.picks){
      const row=pl.find(x=>String(x.id)===String(p.espnId))||pl.find(x=>norm(x.name)===norm(p.player));
      let text=null;
      if(row){const s=statFor(p.sport,fam(p),row);if(s)text=`${Math.round(s[0]*10)/10} ${s[1]}`}
      next[p.id]={phase:ph,line:head,text,played:!!row};
    }
  }));
  for(const g of Object.values(games)){
    if(!openGames.has(g.id))continue;
    const box=g.players||cache.sum[g.id]||[];
    g.teams=g.e.competitions[0].competitors.slice().sort((a,b)=>(a.homeAway==="away"?-1:1)-(b.homeAway==="away"?-1:1)).map(c=>{
      const ab_=c.team.abbreviation,ros=rosters[g.sp+c.team.id]||[],byId={};
      box.filter(x=>x.team===ab_).forEach(x=>byId[x.id]=x);
      const rows=ros.map(r=>{const b=byId[r.id];delete byId[r.id];return rowOf(g.sp,r,b)});
      Object.values(byId).forEach(b=>rows.push(rowOf(g.sp,{id:b.id,name:b.name,pos:b.pos,jersey:"",inj:""},b)));
      rows.sort((a,b)=>a.rank-b.rank||a.order-b.order||a.pos.localeCompare(b.pos)||a.name.localeCompare(b.name));
      return {abbr:ab_,name:c.team.displayName||c.team.name||ab_,rows};
    });
  }
  window.LIVE=next;window.GAMES=games;window.LIVE_AT=new Date();render();return live;
}
function start(){
  let timer=null;
  const tick=async()=>{let live=0;try{live=await poll()}catch(e){}
    timer=setTimeout(tick,document.hidden?120e3:(live?30e3:90e3))};
  document.addEventListener("visibilitychange",()=>{if(!document.hidden){clearTimeout(timer);tick()}});
  tick();
}
root.Live={start,statFor,players,matchEvent,gameTeams,ab,lineFor,ordered,openGames,poll:()=>poll()};
if(typeof module!=="undefined")module.exports=root.Live;
})(typeof window!=="undefined"?window:globalThis);
