#!/usr/bin/env python3
"""WNBA semifinal props. Usage: wnba_build.py <eventId:prevEventId:label:target> ...  Data: ESPN box scores, game logs, injuries."""
import json, sys, math, os, glob, urllib.request, datetime, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK as W, WEEK, TODAY, REPO, SEASON_YEAR
D = W + '/wnba'
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))
def cached(name, u):
    p = f'{D}/cache/{name}.json'
    if os.path.exists(p): return json.load(open(p))
    os.makedirs(f'{D}/cache', exist_ok=True); d = get(u); json.dump(d, open(p, 'w')); return d
inj = {}
for t in json.load(open(D + '/inj.json'))['injuries']:
    for i in t['injuries']: inj[i['athlete']['displayName']] = i
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
BASE = ['points', 'totalRebounds', 'assists', 'steals', 'blocks', 'turnovers', '3pm']
STATS = {'Points': ['points'], 'Rebounds': ['totalRebounds'], 'Assists': ['assists'], 'Blocks': ['blocks'], 'Steals': ['steals'],
         'Blocks + steals': ['blocks', 'steals'], 'Threes made': ['3pm'], 'Turnovers': ['turnovers'],
         'Pts + reb + ast': ['points', 'totalRebounds', 'assists'], 'Pts + reb': ['points', 'totalRebounds'],
         'Pts + ast': ['points', 'assists'], 'Reb + ast': ['totalRebounds', 'assists']}
MIN_AVG = {'Points': 8, 'Rebounds': 4, 'Assists': 2.5, 'Blocks': 0.9, 'Steals': 1.0, 'Blocks + steals': 1.6, 'Threes made': 1.2,
           'Turnovers': 2.0, 'Pts + reb + ast': 15, 'Pts + reb': 12, 'Pts + ast': 12, 'Reb + ast': 7}

def games(aid):
    g = cached(f'gl_{aid}', f'https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{aid}/gamelog')
    names = g['names']; out = []
    for st in g['seasonTypes']:
        if 'Preseason' in st['displayName']: continue
        post = 'Postseason' in st['displayName']
        for cat in st['categories']:
            for e in cat.get('events', []):
                r = dict(zip(names, e['stats'])); ev = g['events'].get(e['eventId'], {})
                if float(r['minutes'] or 0) <= 0: continue
                row = {k: float(r[k]) for k in ('minutes', 'points', 'totalRebounds', 'assists', 'steals', 'blocks', 'turnovers')}
                row['3pm'] = float(r['threePointFieldGoalsMade-threePointFieldGoalsAttempted'].split('-')[0])
                row.update(post=post, date=ev.get('gameDate', '')[:10], opp=ev.get('opponent', {}).get('abbreviation'), note=ev.get('eventNote', ''))
                out.append(row)
    return sorted(out, key=lambda r: r['date'])

def cands_for(aid, name, pos, team, opp, headshot):
    gs = games(aid)
    reg = [g for g in gs if not g['post']]; post = [g for g in gs if g['post']]
    if len(reg) < 20: return []
    recent = reg[-10:] + post
    out = []
    for st, keys in STATS.items():
        val = lambda g: sum(g[k] for k in keys)
        season = statistics.mean(val(g) for g in reg)
        if season < MIN_AVG[st]: continue
        w = [(val(g), 2 if g['post'] else 1) for g in recent]
        rec = sum(v * k for v, k in w) / sum(k for _, k in w)
        vs = [val(g) for g in gs if g['opp'] == opp]
        proj = 0.45 * season + 0.4 * rec + (0.15 * statistics.mean(vs) if len(vs) >= 2 else 0.15 * rec)
        sd = max(statistics.pstdev([val(g) for g in reg]), 0.8)
        line = round(season * 2) / 2
        if line == int(line): line += 0.5 if season > line else -0.5
        line = max(line, 0.5)
        po = 1 - ncdf((line - proj) / sd)
        out.append(dict(aid=aid, name=name, pos=pos, team=team, opp=opp, stat=st, proj=proj, line=line, pover=po, edge=abs(po - 0.5),
                        season=season, rec=rec, vs=vs, sd=sd, nreg=len(reg), post=post, keys=keys, headshot=headshot, gs=gs))
    return out

GROUPS = [['Rebounds', 'Assists', 'Reb + ast'], ['Blocks', 'Steals', 'Blocks + steals', 'Turnovers'], ['Threes made', 'Pts + reb + ast', 'Pts + reb', 'Pts + ast'],
          ['Points', 'Rebounds', 'Assists', 'Threes made', 'Pts + reb + ast', 'Blocks + steals']]
def choose(c, need, existing):
    ch = []; used = {e[0] for e in existing}; stats = collections.Counter(e[1] for e in existing); teams = collections.Counter(e[2] for e in existing); gi = 0
    while len(ch) < need and gi < 40:
        grp = GROUPS[gi % len(GROUPS)]; gi += 1
        thr = 0.08 if gi <= 20 else 0.05
        pool = [x for x in c if x['stat'] in grp and x['name'] not in used and x['edge'] >= thr]
        if not pool: continue
        pool.sort(key=lambda x: (teams[x['team']], stats[x['stat']], -x['edge'])); x = pool[0]
        ch.append(x); used.add(x['name']); stats[x['stat']] += 1; teams[x['team']] += 1
    return ch

def build(c, ev, label, prev, did):
    comp = ev['header']['competitions'][0] if 'header' in ev else None
    dt = datetime.datetime.fromisoformat(comp['date'].replace('Z', '+00:00')).astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
    t = {x['homeAway']: x['team']['abbreviation'] for x in comp['competitors']}
    game = f"{t['away']} @ {t['home']} · {label}"
    side = 'More' if c['pover'] > 0.5 else 'Less'; pct = max(c['pover'], 1 - c['pover'])
    conf = 3 if c['edge'] >= 0.2 and c['stat'] not in ('Blocks', 'Steals', 'Blocks + steals', 'Turnovers') else 2
    st = c['stat']; post = c['post']
    pl = '; '.join(f"{g['note'].replace('Semifinals - ', 'Semis ').replace('First Round - ', 'R1 ')} vs {g['opp']}: {int(sum(g[k] for k in c['keys']))}" for g in post)
    inj_note = inj.get(c['name'])
    team_inj = [n for n in ROSTER.get(c['team'], []) if n in inj and n != c['name']]
    tm = f" Teammate status: {', '.join(team_inj)} listed out or limited on ESPN's injury report." if team_inj else ''
    basis = f"{c['season']:.1f}/g over {c['nreg']} reg-season games; recent 10 + playoffs weighted {c['rec']:.1f}" + \
            (f"; vs {c['opp']} {statistics.mean(c['vs']):.1f} in {len(c['vs'])}" if len(c['vs']) >= 2 else '') + f"; ref {c['line']}"
    analysis = (f"{c['name']} averaged {c['season']:.1f} {st.lower()} over {c['nreg']} regular-season games and has gone {pl or 'n/a'} in the playoffs. "
                f"Weighting her last 10 regular-season games and playoff games (playoffs counted double) gives {c['rec']:.1f}"
                + (f", and she has averaged {statistics.mean(c['vs']):.1f} in {len(c['vs'])} games against {c['opp']} this year" if len(c['vs']) >= 2 else '') + ". "
                f"The blend projects {c['proj']:.1f} against a reference of {c['line']} (the half-point nearest her season average; no book line posted when I checked). "
                f"With her game-to-game spread (standard deviation {c['sd']:.1f}) that is a {side} lean at about {pct:.0%}.{tm} "
                "Game 2 on Wednesday can change rotations and minutes before Friday, so this should be rechecked after that game.")
    why = f"{c['name']} averages {c['season']:.1f} {st.lower()} and projects {c['proj']:.1f} for Game 3."
    hist = [g for g in c['gs'] if g['opp'] == c['opp']]
    history = (f"Against {c['opp']} this season: " + '; '.join(f"{g['date']}: {int(g['points'])} pts, {int(g['totalRebounds'])} reb, {int(g['assists'])} ast" for g in hist) + '.') if hist else f"No games against {c['opp']} in her ESPN game log this season."
    pg = lambda k: statistics.mean(g[k] for g in c['gs'] if not g['post'])
    doc = {'sport': 'wnba', 'week': WEEK, 'id': did, 'player': c['name'], 'team': c['team'], 'position': c['pos'], 'game': game,
           'gameTime': dt.strftime('%a ') + f'{dt.month}/{dt.day}', 'startTime': dt.isoformat(), 'stat': st, 'side': side, 'line': None, 'lines': [],
           'projection': {'value': f"{c['proj']:.1f} {st.lower()}", 'basis': basis}, 'projBasis': basis,
           'projLine': [{'stat': 'Points', 'proj': f"{pg('points'):.1f}"}, {'stat': 'Rebounds', 'proj': f"{pg('totalRebounds'):.1f}"}, {'stat': 'Assists', 'proj': f"{pg('assists'):.1f}"}],
           'confidence': conf, 'status': 'pending', 'newsTag': 'Semis rotation', 'why': why, 'analysis': analysis,
           'matchup': f"Semifinal series vs {c['opp']}. Playoff log: {pl or 'none'}. Season average {c['season']:.1f}, recent weighted {c['rec']:.1f}.",
           'matchupSources': [{'title': f'ESPN box score, {label.replace("G3", "G1")}', 'url': f'https://www.espn.com/wnba/boxscore/_/gameId/{prev}'}],
           'teamOutlook': {'scored': f"{c['team']} semifinal series in progress", 'allowed': f"{c['opp']} defense: see ESPN box scores", 'defense': 'Not verified beyond box scores'},
           'history': history, 'historySources': [{'title': f"ESPN game log: {c['name']}", 'url': f"https://www.espn.com/wnba/player/gamelog/_/id/{c['aid']}"}],
           'bio': BIO(c['aid']), 'bioSource': {'title': f"ESPN: {c['name']}", 'url': f"https://www.espn.com/wnba/player/_/id/{c['aid']}"},
           'sources': [{'title': f"ESPN game log: {c['name']}", 'url': f"https://www.espn.com/wnba/player/gamelog/_/id/{c['aid']}"},
                       {'title': f'ESPN box score, semifinal Game 1', 'url': f'https://www.espn.com/wnba/boxscore/_/gameId/{prev}'},
                       {'title': 'ESPN WNBA injuries', 'url': 'https://www.espn.com/wnba/injuries'}],
           'espnId': c['aid']}
    return doc

ROSTER = {}
def BIO(aid):
    a = cached(f'ath_{aid}', f'https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{aid}')['athlete']
    b = {'age': a.get('age'), 'height': a.get('displayHeight'), 'weight': a.get('displayWeight'),
         'college': (a.get('college') or {}).get('name') or (a.get('birthPlace') or {}).get('country'),
         'exp': f"{a['experience']['years']} WNBA seasons" if (a.get('experience') or {}).get('years') else None}
    return {k: v for k, v in b.items() if v}
if __name__ == '__main__':
    existing = [json.load(open(f)) for f in glob.glob(W + '/export/picks/*wnba*.json')]
    nxt = max(int(os.path.basename(f)[:-5].split('-')[-1]) for f in glob.glob(W + '/export/picks/*wnba*.json')) + 1
    os.makedirs(W + '/new/wnba', exist_ok=True)
    for arg in sys.argv[1:]:
        eid, prev, label, target = arg.split(':'); target = int(target)
        ev = cached(f'sum_{eid}', f'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={eid}')
        box = cached(f'sum_{prev}', f'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={prev}')
        comp = ev['header']['competitions'][0]; t = {x['homeAway']: x['team']['abbreviation'] for x in comp['competitors']}
        game = f"{t['away']} @ {t['home']} · {label}"
        ex = [(e['player'], e['stat'], e['team']) for e in existing if e['game'] == game]
        cands = []
        for tb in box['boxscore']['players']:
            team = tb['team']['abbreviation']; opp = t['home'] if team == t['away'] else t['away']
            ROSTER[team] = [a['athlete']['displayName'] for a in tb['statistics'][0]['athletes']]
            for a in tb['statistics'][0]['athletes']:
                nm = a['athlete']['displayName']
                if a.get('didNotPlay') or not a['stats'] or float(a['stats'][0] or 0) < 17: continue
                if nm in inj: continue
                cands += cands_for(a['athlete']['id'], nm, a['athlete']['position']['abbreviation'], team, opp, a['athlete'].get('headshot', {}).get('href'))
        ch = choose(cands, max(0, target - len(ex)), ex)
        for c in ch:
            did = f'{WEEK}-wnba-{nxt:02d}'; nxt += 1
            d = build(c, ev, label, prev, did); json.dump(d, open(f'{W}/new/wnba/{did}.json', 'w'), indent=1, ensure_ascii=False)
            print(did, game, c['name'], c['team'], c['stat'], d['side'], d['projection']['value'], c['line'], d['confidence'])
        print(game, 'existing', ex, 'added', len(ch))
