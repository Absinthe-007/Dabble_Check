#!/usr/bin/env python3
"""Cross-check open-pick book lines against BettingPros player pages (independent of RotoWire).
Each player page embeds `consensusLines` {market_id: {line,...}} plus the market list (id -> slug).
usage: verify_lines.py data/picks.json -> .props-work/line_check.json"""
import json, re, subprocess, sys, unicodedata, collections
from concurrent.futures import ThreadPoolExecutor
SLUG2STAT = {'passing-yards': 'Passing yards', 'rushing-yards': 'Rushing yards', 'receiving-yards': 'Receiving yards',
 'receptions': 'Receptions', 'passing-completions': 'Passing completions', 'passing-attempts': 'Passing attempts',
 'passing-touchdowns': 'Passing TDs', 'interceptions': 'Interceptions thrown', 'tackles-assists': 'Tackles + assists',
 'shots-on-goal': 'Shots on goal', 'points': 'Points', 'assists': 'Assists', 'blocked-shots': 'Blocked shots',
 'rebounds': 'Rebounds', 'threes': 'Threes made', 'saves': 'Goalie saves', 'sacks': 'Sacks',
 'rushing-attempts': 'Rushing attempts', 'longest-reception': 'Longest reception'}
ALT = {'Passing completions': ['Completions'], 'Passing attempts': ['Pass attempts'], 'Interceptions thrown': ['Interceptions thrown']}
def slugify(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()
    return re.sub(r'-+', '-', re.sub(r"[^a-z0-9]+", '-', s.replace("'", ''))).strip('-')
def page(sport, name):
    u = 'https://www.bettingpros.com/%s/props/%s/' % (sport, slugify(name))
    h = subprocess.run(['curl', '-sS', '-m', '60', '-A', 'Mozilla/5.0', '-L', u], capture_output=True).stdout.decode('utf-8', 'replace')
    ids = {int(i): sl for i, sl in re.findall(r'\{"id":(\d+),"sport_id":\d+,"sport":"\w+","category":"player-props","slug":"([^"]+)"', h)}
    m = re.search(r'"consensusLines":(\{.*?\}\})', h)
    if not m: return None
    cl = json.loads(m.group(1))
    return {SLUG2STAT.get(ids.get(int(k)), ids.get(int(k))): v['line'] for k, v in cl.items() if ids.get(int(k))}
def main():
    picks = json.load(open(sys.argv[1]))
    todo = [p for p in picks if p['status'] == 'pending' and isinstance(p.get('line'), (int, float))]
    names = sorted({(p['sport'], p['player']) for p in todo})
    print('players', len(names), flush=True)
    with ThreadPoolExecutor(4) as ex: got = dict(zip(names, ex.map(lambda a: page(*a), names)))
    res = []; nopage = [n for n, v in got.items() if v is None]
    for p in todo:
        g = got.get((p['sport'], p['player']))
        if not g: continue
        st = p['stat']; ln = g.get(st)
        if ln is None:
            for a in ALT.get(st, []): ln = g.get(a) if ln is None else ln
        if ln is None: res.append(dict(id=p['id'], player=p['player'], stat=st, ours=p['line'], bp=None, diff=None)); continue
        res.append(dict(id=p['id'], sport=p['sport'], player=p['player'], stat=st, ours=p['line'], bp=ln, diff=round(p['line'] - ln, 2)))
    json.dump(dict(results=res, nopage=nopage), open('.props-work/line_check.json', 'w'), indent=1)
    cmp = [r for r in res if r['diff'] is not None]
    d = collections.Counter(('exact' if abs(r['diff']) < .01 else 'within1' if abs(r['diff']) <= 1 else 'off') for r in cmp)
    print('open picks with lines', len(todo), '| compared', len(cmp), dict(d), '| stat not on BettingPros', len(res) - len(cmp), '| no page', len(nopage))
    for r in cmp:
        if abs(r['diff']) > 1: print('OFF', r)
main()
