#!/usr/bin/env python3
"""Build NHL prop docs for given dates. Usage: nhl_build.py YYYY-MM-DD [more dates]
Writes new/nhl/<doc_id>.json. Data: NHL stats API, NHL web API, ESPN injuries, Daily Faceoff goalies."""
import json, sys, math, re, glob, os, urllib.request, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK as W, WEEK, TODAY, REPO, SEASON_YEAR
N = W + '/nhl'
UA = {'User-Agent': 'Mozilla/5.0'}
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
def cached(name, u):
    p = f'{N}/cache/{name}.json'
    if os.path.exists(p): return json.load(open(p))
    os.makedirs(f'{N}/cache', exist_ok=True); d = get(u); json.dump(d, open(p, 'w')); return d
def load(f): return json.load(open(f'{N}/{f}.json'))['data']

LS, CS = f'{SEASON_YEAR - 1}{SEASON_YEAR}', f'{SEASON_YEAR}{SEASON_YEAR + 1}'
sumL = {r['playerId']: r for r in load('sum_' + LS)}; sumC = {r['playerId']: r for r in load('sum_' + CS)}
rtL = {r['playerId']: r for r in load('rt_' + LS)}; rtC = {r['playerId']: r for r in load('rt_' + CS)}
gL = {r['playerId']: r for r in load('g_' + LS)}; gC = {r['playerId']: r for r in load('g_' + CS)}
TEAMNAME2AB = {}
teamL = {}; teamC = {}
FULL = {}
for f, dst in (('team_' + LS, teamL), ('team_' + CS, teamC)):
    for r in load(f): dst[r['teamFullName']] = r
# abbrev map from schedule files
games = []
for f in sorted(glob.glob(N + '/score_*.json')):
    for g in json.load(open(f)).get('games', []):
        for side in ('awayTeam', 'homeTeam'):
            t = g[side]; FULL[t['abbrev']] = t['name']['default']
        games.append(g)
def team_by_ab(ab, src):
    nm = {r: r for r in src}
    for full, r in src.items():
        if full.endswith(FULL.get(ab, '##')) or FULL.get(ab, '##') in full: return r
    return None
def tstat(ab, key):
    """blend last/current season team stat, current weighted 3x per game"""
    a, c = team_by_ab(ab, teamL), team_by_ab(ab, teamC)
    num = den = 0
    if a: num += a[key] * a['gamesPlayed']; den += a['gamesPlayed']
    if c: num += c[key] * c['gamesPlayed'] * 3; den += c['gamesPlayed'] * 3
    return num / den if den else None
LG = {k: sum(r[k] for r in teamL.values()) / len(teamL) for k in ('shotsAgainstPerGame', 'goalsAgainstPerGame', 'shotsForPerGame', 'goalsForPerGame')}
teamGP = {}
for full, r in teamC.items(): teamGP[full] = r['gamesPlayed']
def tgp(ab):
    r = team_by_ab(ab, teamC); return r['gamesPlayed'] if r else 0

# injuries (ESPN)
inj = {}
for t in json.load(open(N + '/inj.json'))['injuries']:
    for i in t['injuries']:
        inj[i['athlete']['displayName'].lower()] = i['status']
# goalies (Daily Faceoff, today's page only)
h = open(N + '/dfo.html').read()
dfo = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']
dfo_date = dfo.get('date') or dfo.get('specificDate')
confirmed = {}
for g in dfo['data']:
    for s in ('away', 'home'):
        if g[s + 'NewsStrengthName'] == 'Confirmed':
            confirmed[g[s + 'GoalieName']] = dict(src=g[s + 'NewsSourceUrl'], who=g[s + 'NewsSourceName'], note=g[s + 'NewsDetails'])

def pois_cdf(k, lam):
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(int(k) + 1))
def p_over(line, lam):  # P(X > line) for half-integer line
    return 1 - pois_cdf(math.floor(line), lam)
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def nearest_line(rate, opts): return min(opts, key=lambda o: abs(o - rate))
def blend(tl, gpl, tc, gpc, w=3):
    den = gpl + w * gpc
    return (tl + w * tc) / den if den else None
def f1(x): return f'{x:.1f}'
def f2(x): return f'{x:.2f}'

STATS = {  # name: (summary key/realtime key, src, lines, min LS rate)
    'Shots on goal': ('shots', 'sum', [0.5, 1.5, 2.5, 3.5, 4.5], 1.8),
    'Points': ('points', 'sum', [0.5], 0.62),
    'Assists': ('assists', 'sum', [0.5], 0.45),
    'Blocked shots': ('blockedShots', 'rt', [0.5, 1.5, 2.5, 3.5], 1.3),
    'Hits': ('hits', 'rt', [0.5, 1.5, 2.5, 3.5, 4.5], 1.9),
}
ABBR = {'Shots on goal': 'SOG', 'Points': 'pts', 'Assists': 'ast', 'Blocked shots': 'blk', 'Hits': 'hits', 'Saves': 'saves'}

def player_rates(pid):
    sl, sc, rl, rc = sumL.get(pid), sumC.get(pid), rtL.get(pid), rtC.get(pid)
    if not sl or sl['gamesPlayed'] < 30 or not sc: return None
    out = {}
    for st, (k, src, lines, mn) in STATS.items():
        L = sl if src == 'sum' else rl; C = sc if src == 'sum' else rc
        if not L or not C: continue
        out[st] = dict(ls=L[k] / L['gamesPlayed'], lst=L[k], lgp=L['gamesPlayed'], cst=C[k], cgp=C['gamesPlayed'],
                       blend=blend(L[k], L['gamesPlayed'], C[k], C['gamesPlayed']))
    return out

def gametime(iso):
    dt = datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
    return dt, dt.strftime('%a ') + f'{dt.month}/{dt.day}', dt.isoformat()

def candidates(g):
    away, home = g['awayTeam']['abbrev'], g['homeTeam']['abbrev']
    out = []
    for team, opp, ha in ((away, home, 'away'), (home, away, 'home')):
        sa_f = (tstat(opp, 'shotsAgainstPerGame') or LG['shotsAgainstPerGame']) / LG['shotsAgainstPerGame']
        ga_f = ((tstat(opp, 'goalsAgainstPerGame') or LG['goalsAgainstPerGame']) / LG['goalsAgainstPerGame']) ** 0.5
        gp_team = tgp(team)
        for pid, sc in sumC.items():
            if sc['teamAbbrevs'].split(',')[-1].strip() != team: continue
            if sc['gamesPlayed'] < gp_team or gp_team == 0: continue  # played every game so far
            if sc['skaterFullName'].lower() in inj: continue
            rates = player_rates(pid)
            if not rates: continue
            for st, r in rates.items():
                k, src, lines, mn = STATS[st]
                if r['ls'] < mn: continue
                fac = sa_f if st == 'Shots on goal' else ga_f if st in ('Points', 'Assists') else 1.0
                proj = r['blend'] * fac
                line = 0.5 if st in ('Points', 'Assists') else nearest_line(r['ls'], lines)
                po = p_over(line, proj)
                out.append(dict(pid=pid, name=sc['skaterFullName'], pos=sc['positionCode'], team=team, opp=opp, stat=st,
                                proj=proj, line=line, pover=po, edge=abs(po - 0.5), fac=fac, r=r, rates=rates, ha=ha))
        # goalie saves (confirmed only; Daily Faceoff page covers today's games only)
        gdate = g['startTimeUTC'] and datetime.datetime.fromisoformat(g['startTimeUTC'].replace('Z', '+00:00')).astimezone(datetime.timezone(datetime.timedelta(hours=-4))).date().isoformat()
        for pid, gc in (gC.items() if gdate == TODAY else []):
            if gc['teamAbbrevs'].split(',')[-1].strip() != team: continue
            if gc['goalieFullName'] not in confirmed: continue
            gl = gL.get(pid)
            if not gl or gl['gamesStarted'] < 15: continue
            oppsf = tstat(opp, 'shotsForPerGame') or LG['shotsForPerGame']
            sv = (gl['saves'] + 3 * gc['saves']) / (gl['shotsAgainst'] + 3 * gc['shotsAgainst'])
            proj = oppsf * sv
            lsr = gl['saves'] / gl['gamesStarted']
            line = math.floor(lsr) + 0.5
            po = 1 - ncdf((line - proj) / 6.0)
            out.append(dict(pid=pid, name=gc['goalieFullName'], pos='G', team=team, opp=opp, stat='Saves', proj=proj, line=line,
                            pover=po, edge=abs(po - 0.5), gl=gl, gc=gc, sv=sv, oppsf=oppsf, ha=ha, conf=confirmed[gc['goalieFullName']]))
    return out

GROUPS = [['Shots on goal'], ['Points', 'Assists'], ['Blocked shots', 'Hits'], ['Saves', 'Hits', 'Blocked shots', 'Shots on goal', 'Points', 'Assists']]
def choose(cands, need, existing):
    chosen = []; used_players = {e[0] for e in existing}; used_stats = collections.Counter(e[1] for e in existing)
    teams = collections.Counter(e[2] for e in existing)
    gi = 0
    while len(chosen) < need and gi < 40:
        grp = GROUPS[gi % len(GROUPS)]; gi += 1
        pool = [c for c in cands if c['stat'] in grp and c['name'] not in used_players and c['edge'] >= 0.06]
        if not pool: continue
        # prefer the team with fewer picks, then the less-used stat, then edge
        pool.sort(key=lambda c: (teams[c['team']], used_stats[c['stat']], -c['edge']))
        c = pool[0]; chosen.append(c); used_players.add(c['name']); used_stats[c['stat']] += 1; teams[c['team']] += 1
    return chosen

def landing(pid): return cached(f'land_{pid}', f'https://api-web.nhle.com/v1/player/{pid}/landing')
def gamelog(pid, s): return cached(f'log_{pid}_{s}', f'https://api-web.nhle.com/v1/player/{pid}/game-log/{s}/2')

def bio(pid):
    d = landing(pid)
    by = d.get('birthDate'); age = None
    if by:
        b = datetime.date.fromisoformat(by); t = datetime.date.fromisoformat(TODAY); age = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    hi = d.get('heightInInches'); dr = d.get('draftDetails')
    out = {'age': age, 'height': f"{hi // 12}'{hi % 12}\"" if hi else None, 'weight': f"{d.get('weightInPounds')} lbs",
           'hand': ('Shoots ' if d.get('position') != 'G' else 'Catches ') + (d.get('shootsCatches') or ''),
           'college': ', '.join(x for x in [(d.get('birthCity') or {}).get('default'), d.get('birthCountry')] if x),
           'exp': f"Drafted {dr['year']}, round {dr['round']}, pick {dr['overallPick']} ({dr['teamAbbrev']})" if dr else 'Undrafted'}
    return {k: v for k, v in out.items() if v}, d.get('headshot'), d

def vs_history(pid, opp, stat):
    rows = [g for g in gamelog(pid, LS).get('gameLog', []) if g.get('opponentAbbrev') == opp]
    rows += [g for g in gamelog(pid, CS).get('gameLog', []) if g.get('opponentAbbrev') == opp]
    return rows

def build(c, g, doc_id):
    dt, gtime, start = gametime(g['startTimeUTC'])
    away, home = g['awayTeam']['abbrev'], g['homeTeam']['abbrev']
    game = f'{away} @ {home}'
    b, head, land = bio(c['pid'])
    team, opp, st = c['team'], c['opp'], c['stat']
    side = 'More' if c['pover'] > 0.5 else 'Less'
    pct = c['pover'] if side == 'More' else 1 - c['pover']
    conf = 3 if c['edge'] >= 0.2 else 2
    if st in ('Blocked shots', 'Hits'): conf = min(conf, 2)
    ofull, tfull = FULL.get(opp, opp), FULL.get(team, team)
    gf_t, ga_o = tstat(team, 'goalsForPerGame'), tstat(opp, 'goalsAgainstPerGame')
    sf_t, sa_o = tstat(team, 'shotsForPerGame'), tstat(opp, 'shotsAgainstPerGame')
    tl, tc = team_by_ab(team, teamL), team_by_ab(team, teamC); ol, oc = team_by_ab(opp, teamL), team_by_ab(opp, teamC)
    stat_url = f'https://www.nhl.com/stats/skaters?reportType=season&seasonFrom={LS}&seasonTo={CS}&gameType=2'
    sources = [
        {'title': f"NHL.com: {c['name']} player page", 'url': f"https://www.nhl.com/player/{c['pid']}"},
        {'title': f'NHL schedule, {dt.strftime("%b")} {dt.day}', 'url': f"https://api-web.nhle.com/v1/schedule/{dt.date().isoformat()}"},
        {'title': 'ESPN NHL injuries', 'url': 'https://www.espn.com/nhl/injuries'},
    ]
    hist_rows = vs_history(c['pid'], opp, st)
    msrc = [{'title': f'NHL.com team stats {LS[:4]}-{LS[6:]} and {CS[:4]}-{CS[6:]}', 'url': 'https://www.nhl.com/stats/teams'}]
    hsrc = [{'title': f"NHL.com game log: {c['name']} {LS[:4]}-{LS[6:]}", 'url': f"https://api-web.nhle.com/v1/player/{c['pid']}/game-log/{LS}/2"}]
    if st == 'Saves':
        gl, gc = c['gl'], c['gc']
        sources.insert(1, {'title': f"Daily Faceoff starting goalies ({c['conf']['who']})", 'url': 'https://www.dailyfaceoff.com/starting-goalies'})
        if c['conf']['src']: sources.append({'title': f"Goalie confirmation: {c['conf']['who']}", 'url': c['conf']['src']})
        sources.append({'title': 'NHL.com goalie stats', 'url': 'https://www.nhl.com/stats/goalies'})
        lsr = gl['saves'] / gl['gamesStarted']
        cur = f"{gc['saves']} saves in {gc['gamesStarted']} start{'s' if gc['gamesStarted'] != 1 else ''} this season" if gc['gamesStarted'] else 'no starts yet this season'
        basis = f"{c['oppsf']:.1f} {opp} shots/g (blended) x {c['sv']:.3f} sv% = {c['proj']:.1f}; {lsr:.1f} saves/start last season; ref {c['line']}"
        analysis = (f"Daily Faceoff lists {c['name']} as the confirmed starter ({c['conf']['note'].strip()} Source: {c['conf']['who']}). "
                    f"He averaged {lsr:.1f} saves per start last season ({gl['saves']} saves, {gl['gamesStarted']} starts, {gl['savePct']:.3f}) and has {cur}. "
                    f"{ofull} generated {c['oppsf']:.1f} shots per game on my blend of last season and this season (league average {LG['shotsForPerGame']:.1f}). "
                    f"Multiplying by his blended save rate gives {c['proj']:.1f} saves against a reference of {c['line']}, the half-point under his per-start average; no book line was posted when I checked. "
                    f"That is a {side} lean at roughly {pct:.0%}. The risks are a pull after an early goal flurry, a lopsided game script that suppresses shots, and score effects late.")
        why = f"{c['name']} is confirmed in net; {ofull} project for {c['oppsf']:.1f} shots, which works out to {c['proj']:.1f} saves at his save rate."
        projval = f"{c['proj']:.1f} saves"
        projline = [{'stat': 'Saves', 'proj': f1(c['proj'])}, {'stat': 'Goals against', 'proj': f1(c['oppsf'] * (1 - c['sv']))}]
        hs = ''
        if hist_rows:
            sa_ = sum((r.get('shotsAgainst') or 0) - (r.get('goalsAgainst') or 0) for r in hist_rows)
            hs = f" Against {opp} since the start of last season he played {len(hist_rows)} game(s) and made {sa_} saves ({sa_ / len(hist_rows):.1f} per game)."
        history = f"{c['name']} started {gl['gamesStarted']} games last season with a {gl['savePct']:.3f} save percentage and {gl['goalsAgainstAverage']:.2f} GAA.{hs} Shots-faced history by opponent is from NHL.com game logs."
        matchup = (f"{ofull} averaged {ol['shotsForPerGame']:.1f} shots and {ol['goalsForPerGame']:.2f} goals per game last season" if ol else f"{ofull} season-ago data not found") + \
                  (f", and {oc['shotsForPerGame']:.1f} shots in {oc['gamesPlayed']} games this season." if oc else '.')
        newsTag = 'Confirmed starter'
    else:
        r = c['r']
        lsrate, cur = r['ls'], (r['cst'] / r['cgp'] if r['cgp'] else 0)
        unit = ABBR[st]
        if st == 'Shots on goal':
            adj = f"{opp} allowed {sa_o:.1f} shots/g vs league {LG['shotsAgainstPerGame']:.1f} (x{c['fac']:.2f})"
        elif st in ('Points', 'Assists'):
            adj = f"{opp} allowed {ga_o:.2f} goals/g vs league {LG['goalsAgainstPerGame']:.2f} (x{c['fac']:.2f}, damped)"
        else:
            adj = 'no opponent adjustment for this stat'
        basis = f"{r['lst']} {unit} in {r['lgp']} GP last season ({f2(lsrate)}/g); {r['cst']} in {r['cgp']} GP this season; blend {f2(r['blend'])}; {adj}; ref {c['line']}"
        if st in ('Points', 'Assists'):
            prob = f"About a {c['pover']:.0%} chance of at least one {'point' if st == 'Points' else 'assist'} on a Poisson read of {f2(c['proj'])} per game"
        else:
            prob = f"A Poisson read of {f2(c['proj'])} per game puts {'more than' if side == 'More' else 'fewer than or equal to'} {c['line']} at about {pct:.0%}"
        role = {'D': 'defenseman', 'C': 'center', 'L': 'left wing', 'R': 'right wing'}.get(c['pos'], c['pos'])
        toi = sumC[c['pid']]['timeOnIcePerGame'] / 60
        analysis = (f"{c['name']} ({tfull} {role}) had {r['lst']} {st.lower()} in {r['lgp']} games last season ({f2(lsrate)} per game) and has {r['cst']} in {r['cgp']} games this season ({f2(cur)} per game) while averaging {toi:.1f} minutes. "
                    f"He has dressed for every {team} game so far and is not on ESPN's injury list. "
                    f"Weighting this season three times per game gives {f2(r['blend'])}; {adj.replace(' (x', ', a factor of ').replace(')', '')}. "
                    f"That projects {f2(c['proj'])} against a reference of {c['line']} (no book line posted when I checked; the reference is the half-point nearest his season-ago rate). {prob}. "
                    + ("Peripheral stats like these swing with deployment and score effects, so this stays a low-confidence lean." if st in ('Blocked shots', 'Hits') else
                       "The main risks are a small early-season sample, line-combination changes and power-play time."))
        why = f"{c['name']} averages {f2(lsrate)} {st.lower()} per game over last season and {f2(cur)} this season; the matchup projects {f2(c['proj'])}."
        projval = f"{f2(c['proj'])} {unit}"
        projline = [{'stat': s, 'proj': f2(v['blend'] * (c['fac'] if s == st else 1))} for s, v in c['rates'].items() if s in ('Shots on goal', 'Points', 'Blocked shots', 'Hits')]
        if hist_rows:
            gp_ = len(hist_rows); g_ = sum(x.get('goals', 0) for x in hist_rows); a_ = sum(x.get('assists', 0) for x in hist_rows); s_ = sum(x.get('shots', 0) for x in hist_rows)
            history = f"Against {opp} since the start of last season: {gp_} game(s), {g_} goals, {a_} assists, {s_} shots on goal (NHL.com game logs; hits and blocks are not broken out by game there)."
        else:
            history = f"I found no games against {opp} in his NHL.com game logs since the start of last season."
        matchup = (f"{ofull} allowed {ol['shotsAgainstPerGame']:.1f} shots and {ol['goalsAgainstPerGame']:.2f} goals per game last season" if ol else f"{ofull} season-ago data not found") + \
                  (f"; through {oc['gamesPlayed']} games this season it is {oc['shotsAgainstPerGame']:.1f} shots and {oc['goalsAgainstPerGame']:.2f} goals against." if oc else '.') + \
                  f" League average last season was {LG['shotsAgainstPerGame']:.1f} shots and {LG['goalsAgainstPerGame']:.2f} goals against."
        newsTag = {'Shots on goal': 'Shot volume', 'Points': 'Scoring rate', 'Assists': 'Playmaking rate', 'Blocked shots': 'Shot blocker', 'Hits': 'Physical role'}[st]
        sources.insert(1, {'title': 'NHL.com skater stats (summary and realtime)', 'url': stat_url})
    tout = {'scored': f"{tfull} {gf_t:.2f} goals/g (blended)" if gf_t else 'Not verified',
            'allowed': f"{ofull} allow {ga_o:.2f} goals/g (blended)" if ga_o else 'Not verified',
            'defense': f"{ofull} allow {sa_o:.1f} shots/g (blended; league {LG['shotsAgainstPerGame']:.1f})" if sa_o else 'Not verified'}
    doc = {'sport': 'nhl', 'week': WEEK, 'id': doc_id, 'player': c['name'], 'team': team, 'position': c['pos'],
           'game': game, 'gameTime': gtime, 'startTime': start, 'stat': st, 'side': side, 'line': None, 'lines': [],
           'projection': {'value': projval, 'basis': basis}, 'projBasis': basis, 'projLine': projline,
           'confidence': conf, 'status': 'pending', 'newsTag': newsTag, 'why': why, 'analysis': analysis,
           'matchup': matchup, 'matchupSources': msrc, 'teamOutlook': tout, 'history': history, 'historySources': hsrc,
           'bio': b, 'bioSource': {'title': f"NHL.com: {c['name']}", 'url': f"https://www.nhl.com/player/{c['pid']}"},
           'sources': sources}
    if head: doc['headshot'] = head
    return doc

if __name__ == '__main__':
    dates = sys.argv[1:]
    existing = [json.load(open(f)) for f in glob.glob(W + '/export/picks/*.json')] + [json.load(open(f)) for f in glob.glob(W + '/new/*/*.json')]
    nums = [int(re.sub(r'.*-', '', e['id'] if 'id' in e else '0')) for e in existing if e.get('sport') == 'nhl' and 'id' in e]
    nums += [int(os.path.basename(f)[:-5].split('-')[-1]) for f in glob.glob(W + '/export/picks/*nhl*.json')]
    nxt = max(nums) + 1
    os.makedirs(W + '/new/nhl', exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    seen = set(); report = []
    for g in games:
        if g['id'] in seen: continue
        seen.add(g['id'])
        dt = datetime.datetime.fromisoformat(g['startTimeUTC'].replace('Z', '+00:00'))
        if dt.astimezone(datetime.timezone(datetime.timedelta(hours=-4))).date().isoformat() not in dates: continue
        if dt <= now or g.get('gameState') not in ('FUT', 'PRE'): continue
        game = f"{g['awayTeam']['abbrev']} @ {g['homeTeam']['abbrev']}"
        ex = [(e['player'], e['stat'], e['team']) for e in existing if e.get('sport') == 'nhl' and e['game'].replace('SJS', 'SJS') == game
              and e.get('startTime', '')[:10] == dt.astimezone(datetime.timezone(datetime.timedelta(hours=-4))).date().isoformat()]
        need = max(0, 4 - len(ex))
        ch = choose(candidates(g), need, ex)
        for c in ch:
            did = f'{WEEK}-nhl-{nxt:02d}'; nxt += 1
            d = build(c, g, did); json.dump(d, open(f'{W}/new/nhl/{did}.json', 'w'), indent=1, ensure_ascii=False)
            report.append((did, game, c['name'], c['stat'], d['side'], d['projection']['value'], c['line'], d['confidence']))
        print(game, 'existing', len(ex), 'added', len(ch))
    for r in report: print(*r)
