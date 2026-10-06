#!/usr/bin/env python3
"""Build MLB postseason prop docs. Usage: mlb_build.py <gamePk:prevGamePk:label:target> ...
Data: MLB Stats API (season stats, game logs, boxscores, probable pitchers)."""
import json, sys, math, os, glob, re, urllib.request, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK as W, WEEK, TODAY, REPO, SEASON_YEAR
M = W + '/mlb'
API = 'https://statsapi.mlb.com/api/v1'
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))
def cached(name, u):
    p = f'{M}/cache/{name}.json'
    if os.path.exists(p): return json.load(open(p))
    os.makedirs(f'{M}/cache', exist_ok=True); d = get(u); json.dump(d, open(p, 'w')); return d
SEASON = int(TODAY[:4])
sched = {g['gamePk']: g for day in json.load(open(M + '/sched.json'))['dates'] for g in day['games']}

lg_hit = cached('lg_hit', f'{API}/teams/stats?stats=season&group=hitting&season={SEASON}&sportIds=1')
lg_pit = cached('lg_pit', f'{API}/teams/stats?stats=season&group=pitching&season={SEASON}&sportIds=1')
TH = {s['team']['id']: s['stat'] for s in lg_hit['stats'][0]['splits']}
TP = {s['team']['id']: s['stat'] for s in lg_pit['stats'][0]['splits']}
def tot(D, k): return sum(float(v[k]) for v in D.values())
LG_K_PA = tot(TH, 'strikeOuts') / tot(TH, 'plateAppearances')
LG_H_PA = tot(TH, 'hits') / tot(TH, 'plateAppearances')
LG_BB_PA = tot(TH, 'baseOnBalls') / tot(TH, 'plateAppearances')
LG_WHIP = (tot(TP, 'hits') + tot(TP, 'baseOnBalls')) / sum(float(v['inningsPitched']) for v in TP.values())
LG_R_G = tot(TH, 'runs') / tot(TH, 'gamesPlayed')

def person(pid):
    return cached(f'p_{pid}', f'{API}/people/{pid}?hydrate=stats(group=[hitting,pitching],type=[season,gameLog],season={SEASON},gameType=R),currentTeam')['people'][0]
def stat_of(p, group, typ):
    for s in p.get('stats', []):
        if s['group']['displayName'] == group and s['type']['displayName'] == typ: return s['splits']
    return []
def pois_cdf(k, lam): return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(int(k) + 1))
def p_over(line, lam): return 1 - pois_cdf(math.floor(line), lam)
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def f2(x): return f'{x:.2f}'

HIT = {  # stat name: (key or func, ref line, min per-game rate)
    'Hits': ('hits', 0.5, 0.75), 'Total bases': ('totalBases', 1.5, 1.2), 'Hits + runs + RBIs': (None, 1.5, 1.6),
    'Runs': ('runs', 0.5, 0.55), 'RBIs': ('rbi', 0.5, 0.55), 'Home runs': ('homeRuns', 0.5, 0.2),
    'Stolen bases': ('stolenBases', 0.5, 0.2), 'Batter strikeouts': ('strikeOuts', 0.5, 0.9)}
PIT = ['Strikeouts', 'Pitching outs', 'Hits allowed', 'Walks allowed', 'Earned runs allowed']

def hitter_cands(pid, team, opp_team_id, opp_sp):
    p = person(pid); ss = stat_of(p, 'hitting', 'season')
    if not ss: return []
    s = ss[0]['stat']; g = s['gamesPlayed']; pa = s['plateAppearances']
    if g < 60 or pa / g < 3.3: return []
    pa_g = pa / g
    # opposing starter factor (covers ~60% of PAs)
    fh = fk = 1.0; spnote = 'starter not announced; team-level only'
    if opp_sp:
        sp = person(opp_sp['id']); sps = stat_of(sp, 'pitching', 'season')
        if sps:
            t = sps[0]['stat']; bf = t['battersFaced']
            if bf > 150:
                whip = float(t['whip']); kpa = t['strikeOuts'] / bf
                fh = 0.6 * (whip / LG_WHIP) + 0.4; fk = 0.6 * (kpa / LG_K_PA) + 0.4
                spnote = f"{opp_sp['fullName']} ({t['whip']} WHIP, {kpa:.1%} K rate vs league {LG_WHIP:.2f}/{LG_K_PA:.1%})"
    out = []
    for st, (k, line, mn) in HIT.items():
        if st == 'Hits + runs + RBIs':
            per = (s['hits'] + s['runs'] + s['rbi']) / g
            proj = (s['hits'] * fh + (s['runs'] + s['rbi']) * (0.5 + 0.5 * fh)) / g
            tot_ = s['hits'] + s['runs'] + s['rbi']
        else:
            tot_ = s[k]; per = tot_ / g
            fac = fk if st == 'Batter strikeouts' else (1.0 if st == 'Stolen bases' else fh if st in ('Hits', 'Total bases', 'Home runs') else 0.5 + 0.5 * fh)
            proj = per * fac
        if per < mn: continue
        po = p_over(line, proj)
        if st in ('Home runs', 'Stolen bases') and po < 0.5: continue  # a Less on a rare event is not a real lean
        out.append(dict(kind='hit', pid=pid, name=p['fullName'], pos=p['primaryPosition']['abbreviation'], team=team, stat=st,
                        proj=proj, line=line, pover=po, edge=abs(po - 0.5), per=per, tot=tot_, g=g, pa_g=pa_g, s=s, spnote=spnote, p=p))
    return out

def pitcher_cands(sp, team, opp_id):
    p = person(sp['id']); ss = stat_of(p, 'pitching', 'season')
    if not ss: return []
    s = ss[0]['stat']; gs = s['gamesStarted']
    if gs < 8: return []
    logs = [x for x in stat_of(p, 'pitching', 'gameLog') if x['stat'].get('gamesStarted')][-5:]
    def outs(st): ip = str(st['inningsPitched']); a, b = ip.split('.'); return int(a) * 3 + int(b)
    season = {'Strikeouts': s['strikeOuts'] / gs, 'Pitching outs': outs(s) / max(1, s['gamesPlayed']) * (s['gamesPlayed'] / gs if s['gamesPlayed'] == gs else 1),
              'Hits allowed': s['hits'] / gs, 'Walks allowed': s['baseOnBalls'] / gs, 'Earned runs allowed': s['earnedRuns'] / gs}
    if s['gamesPlayed'] != gs:  # had relief outings; use starts from game log for outs
        st_logs = [x for x in stat_of(p, 'pitching', 'gameLog') if x['stat'].get('gamesStarted')]
        if st_logs: season['Pitching outs'] = sum(outs(x['stat']) for x in st_logs) / len(st_logs)
    rec = {}
    if logs:
        n = len(logs)
        rec = {'Strikeouts': sum(x['stat']['strikeOuts'] for x in logs) / n, 'Pitching outs': sum(outs(x['stat']) for x in logs) / n,
               'Hits allowed': sum(x['stat']['hits'] for x in logs) / n, 'Walks allowed': sum(x['stat']['baseOnBalls'] for x in logs) / n,
               'Earned runs allowed': sum(x['stat']['earnedRuns'] for x in logs) / n}
    o = TH[opp_id]; opa = o['plateAppearances']
    f = {'Strikeouts': (o['strikeOuts'] / opa) / LG_K_PA, 'Hits allowed': (o['hits'] / opa) / LG_H_PA,
         'Walks allowed': (o['baseOnBalls'] / opa) / LG_BB_PA, 'Earned runs allowed': (o['runs'] / o['gamesPlayed']) / LG_R_G, 'Pitching outs': 1.0}
    out = []
    for st in PIT:
        base = 0.6 * season[st] + 0.4 * rec.get(st, season[st])
        if st == 'Pitching outs': base *= 0.95  # postseason hooks are quicker
        proj = base * f[st]
        line = math.floor(season[st]) + 0.5
        if st == 'Pitching outs':
            po = 1 - ncdf((line - proj) / 3.0)
        else:
            po = p_over(line, proj)
        out.append(dict(kind='pit', pid=sp['id'], name=p['fullName'], pos='SP', team=team, stat=st, proj=proj, line=line, pover=po,
                        edge=abs(po - 0.5), season=season[st], rec=rec.get(st), n=len(logs), fac=f[st], s=s, gs=gs, p=p))
    return out

GROUPS = [['Strikeouts', 'Pitching outs', 'Hits allowed', 'Walks allowed', 'Earned runs allowed'],
          ['Hits', 'Total bases', 'Hits + runs + RBIs'], ['Runs', 'RBIs', 'Home runs', 'Stolen bases', 'Batter strikeouts'],
          ['Total bases', 'Hits + runs + RBIs', 'Hits', 'Batter strikeouts', 'Runs', 'RBIs']]
def choose(c, need, existing):
    chosen = []; used = {e[0] for e in existing}; stats = collections.Counter(e[1] for e in existing); teams = collections.Counter(e[2] for e in existing)
    gi = 0
    while len(chosen) < need and gi < 60:
        grp = GROUPS[gi % len(GROUPS)]; gi += 1
        pool = [x for x in c if x['stat'] in grp and x['name'] not in used and x['edge'] >= 0.07]
        if not pool: continue
        pool.sort(key=lambda x: (teams[x['team']], stats[x['stat']], -x['edge']))
        x = pool[0]; chosen.append(x); used.add(x['name']); stats[x['stat']] += 1; teams[x['team']] += 1
    return chosen

def bio(p):
    b = {'age': p.get('currentAge'), 'height': p.get('height'), 'weight': f"{p.get('weight')} lbs" if p.get('weight') else None,
         'hand': f"Bats {p.get('batSide', {}).get('code', '?')} / Throws {p.get('pitchHand', {}).get('code', '?')}",
         'college': ', '.join(x for x in [p.get('birthCity'), p.get('birthStateProvince') or p.get('birthCountry')] if x),
         'exp': f"MLB debut {p['mlbDebutDate']}" if p.get('mlbDebutDate') else None}
    return {k: v for k, v in b.items() if v}

def build(c, g, label, prev, doc_id):
    a, h = g['teams']['away']['team'], g['teams']['home']['team']
    dt = datetime.datetime.fromisoformat(g['gameDate'].replace('Z', '+00:00')).astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
    game = f"{a['abbreviation']} @ {h['abbreviation']} · {label}"
    opp = h if c['team'] == a['abbreviation'] else a
    side = 'More' if c['pover'] > 0.5 else 'Less'; pct = max(c['pover'], 1 - c['pover'])
    conf = 3 if c['edge'] >= 0.2 and c['stat'] not in ('Batter strikeouts', 'Home runs', 'Stolen bases') else 2
    p = c['p']; pid = c['pid']
    page = f"https://www.mlb.com/player/{pid}"
    sources = [{'title': f"MLB.com: {c['name']}", 'url': page},
               {'title': f"MLB Stats API: {c['name']} {SEASON} stats and game log", 'url': f"{API}/people/{pid}?hydrate=stats(group=[hitting,pitching],type=[season,gameLog],season={SEASON})"},
               {'title': f"MLB.com probable pitchers / schedule ({label})", 'url': f"{API}/schedule?sportId=1&date={dt.date().isoformat()}&hydrate=probablePitcher"}]
    if prev: sources.append({'title': f"Previous game box score (gamePk {prev})", 'url': f"https://www.mlb.com/gameday/{prev}/final/box"})
    ot = TH[opp['id']]; opa = ot['plateAppearances']; opit = TP[opp['id']]
    if c['kind'] == 'pit':
        s = c['s']; unit = {'Strikeouts': 'K', 'Pitching outs': 'outs', 'Hits allowed': 'H', 'Walks allowed': 'BB', 'Earned runs allowed': 'ER'}[c['stat']]
        rec = f"; last {c['n']} starts {c['rec']:.1f}" if c['rec'] is not None else ''
        adj = {'Strikeouts': f"{opp['abbreviation']} K rate {ot['strikeOuts'] / opa:.1%} vs league {LG_K_PA:.1%}",
               'Hits allowed': f"{opp['abbreviation']} hit rate {ot['hits'] / opa:.3f}/PA vs league {LG_H_PA:.3f}",
               'Walks allowed': f"{opp['abbreviation']} walk rate {ot['baseOnBalls'] / opa:.1%} vs league {LG_BB_PA:.1%}",
               'Earned runs allowed': f"{opp['abbreviation']} {ot['runs'] / ot['gamesPlayed']:.2f} runs/g vs league {LG_R_G:.2f}",
               'Pitching outs': 'trimmed 5% for postseason hooks'}[c['stat']]
        basis = f"{c['season']:.1f} {unit}/start over {c['gs']} starts{rec}; {adj} (x{c['fac']:.2f}); ref {c['line']}"
        analysis = (f"{c['name']} is MLB.com's listed probable starter. He made {c['gs']} starts this season ({s['inningsPitched']} IP, {s['era']} ERA, {s['whip']} WHIP, {s['strikeOuts']} K, {s['baseOnBalls']} BB) "
                    f"and averaged {c['season']:.1f} {c['stat'].lower()} per start" + (f", {c['rec']:.1f} over his last {c['n']} starts" if c['rec'] is not None else '') + ". "
                    f"Weighting the season 60/40 with recent form and adjusting for the opponent ({adj}) gives {c['proj']:.1f}. "
                    f"No book line was posted when I checked, so the reference is {c['line']}, the half-point under his season per-start average; that makes this a {side} lean at about {pct:.0%}. "
                    "Postseason managers pull starters early and lean on bullpens, which mostly hurts volume stats like outs and strikeouts; a short outing is the main risk.")
        why = f"{c['name']} averages {c['season']:.1f} {c['stat'].lower()} per start; the matchup projects {c['proj']:.1f}."
        projval = f"{c['proj']:.1f} {unit}"
        projline = [{'stat': 'Strikeouts', 'proj': f"{s['strikeOuts'] / c['gs']:.1f}"}, {'stat': 'Innings', 'proj': f"{float(s['inningsPitched']) / c['gs']:.1f}"}, {'stat': 'ERA', 'proj': s['era']}]
        matchup = (f"{opp['name']} hit with a {ot['strikeOuts'] / opa:.1%} strikeout rate, {ot['avg']} average and {ot['ops']} OPS this season and scored {ot['runs'] / ot['gamesPlayed']:.2f} runs per game "
                   f"(league: {LG_K_PA:.1%} K rate, {LG_R_G:.2f} runs).")
        newsTag = 'Probable starter'
        logs = [x for x in stat_of(p, 'pitching', 'gameLog') if x.get('opponent', {}).get('id') == opp['id']]
        history = (f"Against {opp['name']} this regular season: " + '; '.join(f"{x['date']}: {x['stat']['inningsPitched']} IP, {x['stat']['strikeOuts']} K, {x['stat']['hits']} H, {x['stat']['earnedRuns']} ER" for x in logs)
                   + '.') if logs else f"He did not face {opp['name']} in the regular season per his MLB game log."
    else:
        s = c['s']
        unit = {'Hits': 'H', 'Total bases': 'TB', 'Hits + runs + RBIs': 'H+R+RBI', 'Runs': 'R', 'RBIs': 'RBI', 'Home runs': 'HR', 'Stolen bases': 'SB', 'Batter strikeouts': 'K'}[c['stat']]
        basis = f"{c['tot']} {unit} in {c['g']} G ({c['per']:.2f}/g, {c['pa_g']:.1f} PA/g); vs {c['spnote']}; ref {c['line']}"
        analysis = (f"{c['name']} started the previous game of this series and hit {s['avg']}/{s['obp']}/{s['slg']} with {s['homeRuns']} HR, {s['rbi']} RBI and {s['stolenBases']} SB over {c['g']} regular-season games. "
                    f"That is {c['per']:.2f} {c['stat'].lower()} per game at {c['pa_g']:.1f} plate appearances a game. "
                    f"The opposing starter is {c['spnote']}; I apply that to the roughly 60% of plate appearances a starter usually covers, which gives {f2(c['proj'])}. "
                    f"Against a reference of {c['line']} (no book line posted when I checked) a Poisson read puts the {side} at about {pct:.0%}. "
                    "Postseason risks: bullpen matchups late, lineup shuffles against a lefty or righty, and a small single-game sample.")
        why = f"{c['name']} averages {c['per']:.2f} {c['stat'].lower()} per game; the pitching matchup projects {f2(c['proj'])}."
        projval = f"{f2(c['proj'])} {unit}"
        projline = [{'stat': 'Hits', 'proj': f"{s['hits'] / c['g']:.2f}"}, {'stat': 'Total bases', 'proj': f"{s['totalBases'] / c['g']:.2f}"},
                    {'stat': 'H+R+RBI', 'proj': f"{(s['hits'] + s['runs'] + s['rbi']) / c['g']:.2f}"}]
        matchup = (f"{opp['name']} pitching allowed a {opit['whip']} WHIP and {opit['era']} ERA this season (league WHIP {LG_WHIP:.2f}). Starter: {c['spnote']}.")
        newsTag = 'Lineup regular'
        logs = [x for x in stat_of(p, 'hitting', 'gameLog') if x.get('opponent', {}).get('id') == opp['id']]
        if logs:
            hh = sum(x['stat']['hits'] for x in logs); ab = sum(x['stat']['atBats'] for x in logs); hr = sum(x['stat']['homeRuns'] for x in logs)
            history = f"Against {opp['name']} in the {SEASON} regular season: {len(logs)} games, {hh} for {ab}, {hr} HR (MLB game log). Postseason games so far are not included."
        else:
            history = f"No regular-season games against {opp['name']} in his {SEASON} MLB game log."
    team_t = TH[[t for t in (a, h) if t['abbreviation'] == c['team']][0]['id']]
    tout = {'scored': f"{c['team']} {team_t['runs'] / team_t['gamesPlayed']:.2f} runs/g ({team_t['ops']} OPS)",
            'allowed': f"{opp['abbreviation']} pitching {opit['era']} ERA, {opit['whip']} WHIP",
            'defense': f"{opp['abbreviation']} hitters {ot['strikeOuts'] / opa:.1%} K rate, {ot['ops']} OPS"}
    doc = {'sport': 'mlb', 'week': WEEK, 'id': doc_id, 'player': c['name'], 'team': c['team'], 'position': c['pos'], 'game': game,
           'gameTime': dt.strftime('%a ') + f'{dt.month}/{dt.day}', 'startTime': dt.isoformat(), 'stat': c['stat'], 'side': side, 'line': None, 'lines': [],
           'projection': {'value': projval, 'basis': basis}, 'projBasis': basis, 'projLine': projline, 'confidence': conf, 'status': 'pending',
           'newsTag': newsTag, 'why': why, 'analysis': analysis, 'matchup': matchup,
           'matchupSources': [{'title': f'MLB Stats API team stats {SEASON}', 'url': f'{API}/teams/stats?stats=season&group=hitting&season={SEASON}&sportIds=1'}],
           'teamOutlook': tout, 'history': history, 'historySources': [{'title': f"MLB game log: {c['name']}", 'url': page}],
           'bio': bio(p), 'bioSource': {'title': f"MLB.com: {c['name']}", 'url': page}, 'sources': sources,
           'headshot': f"https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/{pid}/headshot/67/current"}
    return doc

if __name__ == '__main__':
    existing = [json.load(open(f)) for f in glob.glob(W + '/export/picks/*mlb*.json')]
    nxt = max(int(os.path.basename(f)[:-5].split('-')[-1]) for f in glob.glob(W + '/export/picks/*mlb*.json')) + 1
    os.makedirs(W + '/new/mlb', exist_ok=True)
    for arg in sys.argv[1:]:
        pk, prev, label, target = arg.split(':'); pk, prev, target = int(pk), int(prev), int(target)
        g = sched[pk]; a, h = g['teams']['away'], g['teams']['home']
        game = f"{a['team']['abbreviation']} @ {h['team']['abbreviation']} · {label}"
        ex = [(e['player'], e['stat'], e['team']) for e in existing if e['game'] == game]
        box = cached(f'box_{prev}', f'{API}/game/{prev}/boxscore')
        cands = []
        for side, other in (('away', 'home'), ('home', 'away')):
            t = g['teams'][side]['team']; o = g['teams'][other]['team']
            bt = [bt for bt in box['teams'].values() if bt['team']['id'] == t['id']][0]
            for hid in bt['battingOrder']:
                cands += hitter_cands(hid, t['abbreviation'], o['id'], g['teams'][other].get('probablePitcher'))
            sp = g['teams'][side].get('probablePitcher')
            if sp: cands += pitcher_cands(sp, t['abbreviation'], o['id'])
        ch = choose(cands, max(0, target - len(ex)), ex)
        for c in ch:
            did = f'{WEEK}-mlb-{nxt:02d}'; nxt += 1
            d = build(c, g, label, prev, did); json.dump(d, open(f'{W}/new/mlb/{did}.json', 'w'), indent=1, ensure_ascii=False)
            print(did, game, c['name'], c['team'], c['stat'], d['side'], d['projection']['value'], c['line'], d['confidence'])
        print(game, 'existing', len(ex), 'added', len(ch))
