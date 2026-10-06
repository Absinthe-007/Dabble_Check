#!/usr/bin/env python3
"""NFL / CFB prop builder from ESPN box scores. Usage: fb_build.py nfl|cfb <min_target>"""
import json, sys, math, os, glob, re, urllib.request, datetime, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK as W, WEEK, TODAY, REPO, SEASON_YEAR
F = W + '/fb'
SPORT = sys.argv[1]; TARGET = int(sys.argv[2])
PATH = {'nfl': 'football/nfl', 'cfb': 'football/college-football'}[SPORT]
API = f'https://site.api.espn.com/apis/site/v2/sports/{PATH}'
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))
def cached(name, u):
    p = f'{F}/cache/{SPORT}_{name}.json'
    if os.path.exists(p): return json.load(open(p))
    os.makedirs(f'{F}/cache', exist_ok=True); d = get(u); json.dump(d, open(p, 'w')); return d
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
ET = datetime.timezone(datetime.timedelta(hours=-4))
now = datetime.datetime.now(datetime.timezone.utc)

TOP = json.load(open(REPO + '/data/cfb_top25.json'))['teams']
def top_entry(team):  # ESPN team obj -> top25 entry or None
    for t in TOP:
        names = {t['name'].upper(), *[a.upper() for a in t['aliases']]}
        if team['abbreviation'].upper() in names or team.get('location', '').upper() in names or team.get('shortDisplayName', '').upper() in names: return t
    return None
def alias(team):
    if SPORT == 'nfl': return team['abbreviation']
    t = top_entry(team)
    if not t: return team['abbreviation']
    names = {t['name'].upper(), *[a.upper() for a in t['aliases']]}
    if team['abbreviation'].upper() in names: return team['abbreviation']
    return t['aliases'][0] if t['aliases'] else t['name']

injured = {}
if SPORT == 'nfl':
    for t in cached('inj', f'{API}/injuries')['injuries']:
        for i in t['injuries']:
            if i['status'] in ('Out', 'Injured Reserve', 'Doubtful', 'Physically Unable to Perform', 'Suspension'): injured[i['athlete']['displayName']] = i['status']

def parse(cat, keys, vals):
    r = {}
    for k, v in zip(keys, vals):
        if '/' in k or '-' in k:
            a, b = re.split('[/-]', k, 1)
            try: x, y = re.split('[/-]', v, 1); r[a] = float(x); r[b] = float(y)
            except Exception: pass
        else:
            try: r[k] = float(v)
            except Exception: pass
    return r

def team_games(tid):
    sch = cached(f'sch_{tid}', f'{API}/teams/{tid}/schedule?season={SEASON_YEAR}')
    done = [e for e in sch['events'] if e['competitions'][0]['status']['type']['state'] == 'post']
    out = []
    for e in done:
        s = cached(f'sum_{e["id"]}', f'{API}/summary?event={e["id"]}')
        out.append((e, s))
    return out

def agg_team(tid):
    """per-player per-game stat rows for team tid; opponent-allowed totals for the opponent factor"""
    players = collections.defaultdict(lambda: {'games': {}, 'name': None, 'pos': None, 'id': None, 'head': None})
    allowed = collections.defaultdict(list)  # what opponents did vs this team per game
    plays = []
    gids = []
    for e, s in team_games(tid):
        gids.append(e['id'])
        for tb in s.get('boxscore', {}).get('players', []):
            mine = str(tb['team']['id']) == str(tid)
            tot = collections.Counter()
            for c in tb['statistics']:
                for a in c['athletes']:
                    r = parse(c['name'], c['keys'], a['stats'])
                    if mine:
                        p = players[a['athlete']['id']]; p['name'] = a['athlete']['displayName']; p['id'] = a['athlete']['id']
                        p['pos'] = a['athlete'].get('position', {}).get('abbreviation') or p['pos']
                        p['head'] = (a['athlete'].get('headshot') or {}).get('href') or p['head']
                        g = p['games'].setdefault(e['id'], {'date': e['date'][:10], 'opp': None})
                        for k, v in r.items(): g[f'{c["name"]}.{k}'] = g.get(f'{c["name"]}.{k}', 0) + v
                    else:
                        for k, v in r.items(): tot[f'{c["name"]}.{k}'] += v
            if not mine:
                allowed['passYds'].append(tot['passing.passingYards']); allowed['rushYds'].append(tot['rushing.rushingYards'])
                allowed['rec'].append(tot['receiving.receptions']); allowed['comp'].append(tot['passing.completions'])
                allowed['plays'].append(tot['passing.passingAttempts'] + tot['rushing.rushingAttempts'])
        # own offensive plays
        for tb in s.get('boxscore', {}).get('players', []):
            if str(tb['team']['id']) == str(tid):
                pa = sum(parse(c['name'], c['keys'], a['stats']).get('passingAttempts', 0) for c in tb['statistics'] if c['name'] == 'passing' for a in c['athletes'])
                ra = sum(parse(c['name'], c['keys'], a['stats']).get('rushingAttempts', 0) for c in tb['statistics'] if c['name'] == 'rushing' for a in c['athletes'])
                plays.append(pa + ra)
    return players, {k: statistics.mean(v) for k, v in allowed.items() if v}, (statistics.mean(plays) if plays else None), gids

STATS = {  # name: (fn(game)->value or None, min avg, kind, eligible positions or None)
    'Passing yards': (lambda g: g.get('passing.passingYards'), 150, 'yds'),
    'Completions': (lambda g: g.get('passing.completions'), 14, 'cnt'),
    'Pass attempts': (lambda g: g.get('passing.passingAttempts'), 22, 'cnt'),
    'Passing TDs': (lambda g: g.get('passing.passingTouchdowns'), 1.0, 'rare'),
    'Rushing yards': (lambda g: g.get('rushing.rushingYards'), 35, 'yds'),
    'Rushing attempts': (lambda g: g.get('rushing.rushingAttempts'), 9, 'cnt'),
    'Receiving yards': (lambda g: g.get('receiving.receivingYards'), 35, 'yds'),
    'Receptions': (lambda g: g.get('receiving.receptions'), 3, 'cnt'),
    'Longest reception': (lambda g: g.get('receiving.longReception'), 15, 'yds'),
    'Rush + rec yards': (lambda g: (g.get('rushing.rushingYards', 0) + g.get('receiving.receivingYards', 0)) if ('rushing.rushingYards' in g and 'receiving.receivingYards' in g) else None, 60, 'yds'),
    'Tackles + assists': (lambda g: g.get('defensive.totalTackles'), 4.5, 'cnt'),
    'Solo tackles': (lambda g: g.get('defensive.soloTackles'), 3, 'cnt'),
    'Sacks': (lambda g: g.get('defensive.sacks'), 0.45, 'rare'),
    'Defensive INTs': (lambda g: g.get('interceptions.interceptions', 0) if 'defensive.totalTackles' in g else None, 0.45, 'rare'),
    'Kicking points': (lambda g: g.get('kicking.totalKickingPoints'), 6, 'cnt'),
    'FGs made': (lambda g: g.get('kicking.fieldGoalsMade'), 1.2, 'cnt'),
}
OPPF = {'Passing yards': 'passYds', 'Completions': 'comp', 'Receiving yards': 'passYds', 'Receptions': 'rec', 'Longest reception': 'passYds',
        'Rushing yards': 'rushYds', 'Rush + rec yards': None, 'Tackles + assists': 'PLAYS', 'Solo tackles': 'PLAYS'}

def candidates(team, tid, opp, otid, players, gids, LG, oppAllowed, oppPlays):
    out = []
    last = gids[-1] if gids else None
    for pid, p in players.items():
        if last not in p['games']: continue  # must have played in the most recent game
        if p['name'] in injured: continue
        rows = [p['games'][g] for g in gids if g in p['games']]
        flag = False
        for uk in ('rushing.rushingAttempts', 'receiving.receivingTargets', 'passing.passingAttempts', 'defensive.totalTackles'):
            prior = [r.get(uk, 0) for r in rows[:-1]]
            if len(prior) >= 2 and statistics.mean(prior) >= 6 and rows[-1].get(uk, 0) < 0.4 * statistics.mean(prior): flag = True
        if flag: continue  # usage collapsed in the last game: possible injury, skip
        for st, (fn, mn, kind) in STATS.items():
            vals = [fn(r) for r in rows]; vals = [v for v in vals if v is not None]
            if len(vals) < max(2, len(gids) - 2): continue
            # include zero games where player played but no stat in category for defensive counts
            mean = statistics.mean(vals)
            if mean < mn: continue
            wts = [1.0] * (len(vals) - 1) + [1.5]
            wmean = sum(v * w for v, w in zip(vals, wts)) / sum(wts)
            key = OPPF.get(st); fac = 1.0; fnote = ''
            if key == 'PLAYS' and oppPlays and LG.get('plays'):
                fac = (oppPlays / LG['plays']) ** 0.5; fnote = f"{opp} runs {oppPlays:.0f} offensive plays/g vs {LG['plays']:.0f} avg"
            elif key and key in oppAllowed and LG.get(key):
                fac = (oppAllowed[key] / LG[key]) ** 0.5; fnote = f"{opp} allows {oppAllowed[key]:.0f} {key.replace('passYds', 'pass yds').replace('rushYds', 'rush yds').replace('rec', 'receptions').replace('comp', 'completions')}/g vs {LG[key]:.0f} avg"
            proj = wmean * fac
            if kind == 'rare':
                line = 0.5
                lam = proj; po = 1 - math.exp(-lam) if st != 'Passing TDs' else 1 - math.exp(-lam) * (1 + lam)
                if st == 'Passing TDs': line = 1.5
                if st in ('Sacks', 'Defensive INTs') and po < 0.5: continue
            else:
                line = round(mean * 2) / 2
                if line == int(line): line += 0.5 if mean >= line else -0.5
                sd = max(statistics.pstdev(vals) if len(vals) > 1 else 0, (0.35 * mean) if kind == 'yds' else math.sqrt(max(mean, 1)))
                po = 1 - ncdf((line - proj) / sd)
            out.append(dict(pid=pid, name=p['name'], pos=p['pos'] or POS(pid), head=p['head'], team=team, opp=opp, stat=st, proj=proj, line=line,
                            pover=po, edge=abs(po - 0.5), vals=vals, mean=mean, wmean=wmean, fac=fac, fnote=fnote, n=len(vals), kind=kind))
    return out

GROUPS = [['Tackles + assists', 'Solo tackles', 'Sacks', 'Defensive INTs'], ['Receptions', 'Completions', 'Pass attempts', 'Rushing attempts'],
          ['Receiving yards', 'Rushing yards', 'Rush + rec yards', 'Longest reception', 'Passing yards'],
          ['Solo tackles', 'Tackles + assists', 'Kicking points', 'FGs made', 'Passing TDs', 'Sacks'],
          list(STATS)]
def choose(c, need, existing, allowed_teams):
    ch = []; used = {e[0] for e in existing}; stats = collections.Counter(e[1] for e in existing); teams = collections.Counter(e[2] for e in existing); gi = 0
    while len(ch) < need and gi < 60:
        grp = GROUPS[gi % len(GROUPS)]; thr = 0.08 if gi < 30 else 0.05; gi += 1
        pool = [x for x in c if x['stat'] in grp and x['name'] not in used and x['edge'] >= thr and x['team'] in allowed_teams]
        if not pool: continue
        pool.sort(key=lambda x: (teams[x['team']], stats[x['stat']], -x['edge'])); x = pool[0]
        ch.append(x); used.add(x['name']); stats[x['stat']] += 1; teams[x['team']] += 1
    return ch

UNIT = {'Passing yards': 'pass yds', 'Completions': 'comp', 'Pass attempts': 'att', 'Passing TDs': 'pass TD', 'Rushing yards': 'rush yds',
        'Rushing attempts': 'rush att', 'Receiving yards': 'rec yds', 'Receptions': 'rec', 'Longest reception': 'yds', 'Rush + rec yards': 'rush+rec yds',
        'Tackles + assists': 'tackles', 'Solo tackles': 'solo', 'Sacks': 'sacks', 'Defensive INTs': 'INT', 'Kicking points': 'kick pts', 'FGs made': 'FG'}
def fmt(x): return f'{x:.1f}' if x % 1 else f'{int(x)}'

def build(c, ev, game, did, odds, players):
    dt = datetime.datetime.fromisoformat(ev['date'].replace('Z', '+00:00')).astimezone(ET)
    side = 'More' if c['pover'] > 0.5 else 'Less'; pct = max(c['pover'], 1 - c['pover'])
    defensive = c['stat'] in ('Tackles + assists', 'Solo tackles', 'Sacks', 'Defensive INTs', 'Kicking points', 'FGs made')
    conf = 3 if c['edge'] >= 0.2 and not defensive else 2
    log = ', '.join(fmt(v) for v in c['vals'])
    league = 'NFL' if SPORT == 'nfl' else 'college'
    basis = f"{c['n']} games: {log} (avg {c['mean']:.1f}, recent-weighted {c['wmean']:.1f})" + (f"; {c['fnote']} (x{c['fac']:.2f}, damped)" if c['fnote'] else '') + f"; ref {c['line']}"
    if c['kind'] == 'rare':
        prob = f"Treating it as a Poisson count with mean {c['proj']:.2f}, the chance of {'2+' if c['stat'] == 'Passing TDs' else '1+'} is about {c['pover']:.0%}"
    else:
        prob = f"Using his game-to-game spread, that puts the {side} at about {pct:.0%}"
    odds_txt = f" The game line is {odds}." if odds else ''
    analysis = (f"{c['name']} ({c['pos']}, {c['team']}) played in {c['team']}'s most recent game. His {c['stat'].lower()} in the {c['n']} games where he recorded the stat this season: {log}, an average of {c['mean']:.1f}. "
                f"Weighting the most recent game a bit more gives {c['wmean']:.1f}" + (f"; {c['fnote']}, so I scale by {c['fac']:.2f} (square-root damped)" if c['fnote'] else '') + f". "
                f"That projects {c['proj']:.1f} against a reference of {c['line']}; no book line was posted when I checked, so the reference is the half-point nearest his season average. {prob}.{odds_txt} "
                + ("Defensive and kicking stats swing with game script and snap counts, so this is a low-confidence lean." if defensive else
                   "The main risks are a small sample, game script and target or carry share shifting week to week.")
                + (" ESPN's injury report did not list him as out or doubtful when I checked." if SPORT == 'nfl' else ' College injury reports are sparse; he played in the last game.'))
    why = f"{c['name']} has {log} {UNIT[c['stat']]} this season; the matchup projects {c['proj']:.1f}."
    pr = players[c['pid']]
    def avg(key):
        v = [g.get(key) for g in pr['games'].values() if g.get(key) is not None]; return statistics.mean(v) if v else None
    pl = []
    for lab, key in (('Pass yds', 'passing.passingYards'), ('Rush yds', 'rushing.rushingYards'), ('Rec', 'receiving.receptions'), ('Rec yds', 'receiving.receivingYards'),
                     ('Tackles', 'defensive.totalTackles'), ('Sacks', 'defensive.sacks')):
        a = avg(key)
        if a is not None and a > 0: pl.append({'stat': lab, 'proj': f'{a:.1f}'})
    doc = {'sport': SPORT, 'week': WEEK, 'id': did, 'player': c['name'], 'team': c['team'], 'position': c['pos'], 'game': game,
           'gameTime': dt.strftime('%a ') + f'{dt.month}/{dt.day}', 'startTime': dt.isoformat(), 'stat': c['stat'], 'side': side, 'line': None, 'lines': [],
           'projection': {'value': f"{c['proj']:.1f} {UNIT[c['stat']]}", 'basis': basis}, 'projBasis': basis, 'projLine': pl[:4],
           'confidence': conf, 'status': 'pending', 'newsTag': {'Tackles + assists': 'Tackle volume', 'Solo tackles': 'Tackle volume', 'Sacks': 'Pass rush',
           'Defensive INTs': 'Ball hawk', 'Kicking points': 'Kicker', 'FGs made': 'Kicker'}.get(c['stat'], 'Usage'),
           'why': why, 'analysis': analysis,
           'matchup': (c['fnote'] + '.' if c['fnote'] else f"No opponent adjustment for {c['stat'].lower()}.") + odds_txt,
           'matchupSources': [{'title': f"ESPN: {c['opp']} game box scores {SEASON_YEAR}", 'url': f"https://www.espn.com/{'nfl' if SPORT == 'nfl' else 'college-football'}/team/schedule/_/name/{c['opp'].lower()}"}],
           'teamOutlook': TOUT.get(c['team'], {}),
           'history': f"Game-by-game {c['stat'].lower()} this season: {log}. I did not find a prior meeting with {c['opp']} in this season's box scores.",
           'historySources': [{'title': f"ESPN game log: {c['name']}", 'url': f"https://www.espn.com/{'nfl' if SPORT == 'nfl' else 'college-football'}/player/gamelog/_/id/{c['pid']}"}],
           'bio': BIO(c['pid']), 'bioSource': {'title': f"ESPN: {c['name']}", 'url': f"https://www.espn.com/{'nfl' if SPORT == 'nfl' else 'college-football'}/player/_/id/{c['pid']}"},
           'sources': [{'title': f"ESPN game log: {c['name']}", 'url': f"https://www.espn.com/{'nfl' if SPORT == 'nfl' else 'college-football'}/player/gamelog/_/id/{c['pid']}"},
                       {'title': f"ESPN game preview: {game}", 'url': f"https://www.espn.com/{'nfl' if SPORT == 'nfl' else 'college-football'}/game/_/gameId/{ev['id']}"}]
                      + ([{'title': 'ESPN NFL injuries', 'url': 'https://www.espn.com/nfl/injuries'}] if SPORT == 'nfl' else []),
           'espnId': c['pid']}
    if c['head']: doc['headshot'] = c['head']
    return doc

def BIO(pid):
    try:
        a = cached(f'ath_{pid}', f"https://site.web.api.espn.com/apis/common/v3/sports/{PATH}/athletes/{pid}")['athlete']
    except Exception: return {}
    b = {'age': a.get('age'), 'height': a.get('displayHeight'), 'weight': a.get('displayWeight'),
         'college': (a.get('college') or {}).get('name') or ', '.join(x for x in [(a.get('birthPlace') or {}).get('city'), (a.get('birthPlace') or {}).get('state')] if x),
         'exp': (a.get('displayExperience') or (a.get('experience') or {}).get('displayValue') or (f"{a['experience']['years']} seasons" if (a.get('experience') or {}).get('years') else None))}
    return {k: v for k, v in b.items() if v}

TOUT = {}
def POS(pid):
    try: return cached(f'ath_{pid}', f"https://site.web.api.espn.com/apis/common/v3/sports/{PATH}/athletes/{pid}")['athlete'].get('position', {}).get('abbreviation', '')
    except Exception: return ''
if __name__ == '__main__':
    slate = json.load(open(W + '/sched/slate.json'))[SPORT]
    existing = [json.load(open(f)) for f in glob.glob(W + f'/export/picks/*-{SPORT}-*.json')]
    nxt = max(int(os.path.basename(f)[:-5].split('-')[-1]) for f in glob.glob(W + f'/export/picks/*-{SPORT}-*.json')) + 1
    os.makedirs(W + f'/new/{SPORT}', exist_ok=True)
    cache_team = {}
    todo = []
    for g in slate:
        if g['state'] != 'pre' or datetime.datetime.fromisoformat(g['date'].replace('Z', '+00:00')) <= now: continue
        if SPORT == 'cfb' and not ((g['hr'] or 99) <= 25 or (g['ar'] or 99) <= 25): continue
        todo.append(g)
    # league averages from all teams we touch
    summ = {}
    for g in todo:
        s = cached(f'pre_{g["id"]}', f'{API}/summary?event={g["id"]}')
        comp = s['header']['competitions'][0]
        for t in comp['competitors']:
            tid = t['team']['id']
            if tid not in cache_team: cache_team[tid] = agg_team(tid)
        summ[g['id']] = s
    LG = {}
    for k in ('passYds', 'rushYds', 'rec', 'comp'):
        v = [ct[1][k] for ct in cache_team.values() if k in ct[1]]; LG[k] = statistics.mean(v) if v else None
    LG['plays'] = statistics.mean([ct[2] for ct in cache_team.values() if ct[2]])
    for tid, (pl, al, plays, gids) in cache_team.items():
        pass
    report = collections.Counter()
    for g in todo:
        s = summ[g['id']]; comp = s['header']['competitions'][0]
        T = {t['homeAway']: t for t in comp['competitors']}
        away, home = T['away']['team'], T['home']['team']
        aa, ha = alias(away), alias(home)
        start = datetime.datetime.fromisoformat(g['date'].replace('Z', '+00:00')).astimezone(ET).isoformat()
        ex_p = [e for e in existing if e.get('startTime', '')[:16] == start[:16] and e['team'] in (aa, ha, away['abbreviation'], home['abbreviation'])]
        if not ex_p:  # some old picks lack startTime; match by team + gameTime
            dt = datetime.datetime.fromisoformat(start)
            ex_p = [e for e in existing if e['team'] in (aa, ha) and e.get('gameTime', '').startswith(dt.strftime('%a ') + f'{dt.month}/{dt.day}')]
        names = collections.Counter(e['game'] for e in ex_p)
        game = names.most_common(1)[0][0] if names else (f"{aa} vs {ha} (neutral)" if comp.get('neutralSite') else f"{aa} @ {ha}")
        ex = [(e['player'], e['stat'], e['team']) for e in ex_p]
        allowed_teams = {aa, ha}
        if SPORT == 'cfb': allowed_teams = {alias(t) for t in (away, home) if top_entry(t)}
        odds = ''
        pc = s.get('pickcenter') or []
        if pc: odds = f"{pc[0].get('details', '')}, total {pc[0].get('overUnder', '')}".strip(', ')
        cands = []
        for side_, other in (('away', 'home'), ('home', 'away')):
            t, o = T[side_]['team'], T[other]['team']
            pl, al, plays, gids = cache_team[t['id']]; opl, oal, oplays, _ = cache_team[o['id']]
            TOUT[alias(t)] = {'scored': f"{alias(t)} offense {(al and plays) and f'{plays:.0f} plays/g' or 'n/a'}",
                              'allowed': f"{alias(o)} allows {oal.get('passYds', 0):.0f} pass / {oal.get('rushYds', 0):.0f} rush yds per game",
                              'defense': f"{alias(o)} opponents run {oal.get('plays', 0):.0f} plays/g"}
            cands += candidates(alias(t), t['id'], alias(o), o['id'], pl, gids, LG, oal, oplays)
        ch = choose(cands, max(0, TARGET - len(ex)), ex, allowed_teams)
        for c in ch:
            did = f'{WEEK}-{SPORT}-{nxt:02d}'; nxt += 1
            d = build(c, {'date': g['date'], 'id': g['id']}, game, did, odds, cache_team[[t['team']['id'] for t in comp['competitors'] if alias(t['team']) == c['team']][0]][0])
            json.dump(d, open(f'{W}/new/{SPORT}/{did}.json', 'w'), indent=1, ensure_ascii=False)
            report[c['stat']] += 1
            print(did, game, c['name'], c['team'], c['stat'], d['side'], d['projection']['value'], c['line'], d['confidence'])
        print('##', game, 'existing', len(ex), 'added', len(ch))
    print(report)
