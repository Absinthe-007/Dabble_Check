#!/usr/bin/env python3
"""Fill/refresh real book lines on open picks from RotoWire's embedded prop tables.

usage: rw_lines.py <pending_dir> <out_dir> [sport ...]
Reads pick JSON docs (open picks, unstarted games) from <pending_dir>, fetches
RotoWire's player-props page per sport, and writes changed docs to <out_dir>
(same file names, plus a changes.json summary). Nothing is written to the DB here.
Side follows projection vs the consensus (median) line; a flipped side caps
confidence at 2 and clears any must-play flag.
"""
import json, os, re, statistics, subprocess, sys, datetime

BOOKS = {'betrivers': 'BetRivers', 'caesars': 'Caesars', 'draftkings': 'DraftKings', 'fanduel': 'FanDuel',
         'mgm': 'BetMGM', 'thescore': 'theScore', 'hardrock': 'Hard Rock Bet', 'circasports': 'Circa Sports',
         'betr': 'Betr', 'fanatics': 'Fanatics'}
STATS = {
    'nfl': {'Passing completions': 'comp', 'Completions': 'comp', 'Passing attempts': 'passatt', 'Pass attempts': 'passatt',
            'Passing yards': 'passyds', 'Passing TDs': 'passtd', 'Interceptions thrown': 'intsthrown',
            'Rushing yards': 'rushyds', 'Receiving yards': 'recyds', 'Receptions': 'recs',
            'Rush + rec yards': 'rushrec', 'Kicking points': 'kickpts', 'FGs made': 'fgm',
            'Tackles + assists': 'tackle', 'Tackles': 'tackle', 'Solo tackles': 'solo', 'Sacks': 'sack'},
    'nhl': {'Shots on goal': 'shot', 'Points': 'point', 'Assists': 'ast', 'Blocked shots': 'blk', 'Power play points': 'pppt'},
    'wnba': {'Points': 'pts', 'Rebounds': 'reb', 'Assists': 'ast', 'Threes made': 'threes'},
}
URL = 'https://www.rotowire.com/betting/%s/player-props.php'


def fetch(sport):
    out = subprocess.run(['curl', '-sS', '-m', '90', '-A', 'Mozilla/5.0', URL % sport], capture_output=True, check=True)
    return out.stdout.decode('utf-8', 'replace')


def parse(html):
    """-> {(name, statkey): {book: line}}"""
    res = {}
    for m in re.finditer(r'\{"gameID":"\d+","playerID":"\d+"[^{}]*\}', html):
        try:
            r = json.loads(m.group(0))
        except ValueError:
            continue
        for k, v in r.items():
            mm = re.match(r'([a-z]+)_([a-z]+)$', k)
            if not mm or mm.group(1) not in BOOKS or v in (None, ''):
                continue
            try:
                f = float(v)
            except ValueError:
                continue
            if abs(f) > 400 or mm.group(2) in ('firsttd', 'anytd', 'lasttd', 'firstgoal', 'anygoal'):
                continue
            res.setdefault((r['name'], mm.group(2)), {})[BOOKS[mm.group(1)]] = f
    return res


def projnum(d):
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)', str((d.get('projection') or {}).get('value', '')))
    return float(m.group(1)) if m else None


def main():
    pend, out = sys.argv[1], sys.argv[2]
    sports = sys.argv[3:] or ['nfl', 'nhl', 'wnba']
    os.makedirs(out, exist_ok=True)
    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')
    tables = {s: parse(fetch(s)) for s in sports}
    for s, t in tables.items():
        print(s, 'rows', len(t))
    summary = []
    for fn in sorted(os.listdir(pend)):
        d = json.load(open(os.path.join(pend, fn)))
        s = d.get('sport')
        if s not in tables or d.get('status') != 'pending' or (d.get('startTime') or '') <= now:
            continue
        key = STATS[s].get(d.get('stat'))
        books = tables[s].get((d.get('player'), key)) if key else None
        if not books:
            continue
        vals = list(books.values())
        line = statistics.median(vals)
        if line == int(line):  # whole-number lines are fine; keep as float
            line = float(line)
        new_lines = [{'book': b, 'line': l} for b, l in sorted(books.items())]
        old_line, old_side = d.get('line'), d.get('side')
        p = projnum(d)
        side = old_side
        if p is not None and p != line:
            side = 'More' if p > line else 'Less'
        if old_line == line and side == old_side and d.get('lines') == new_lines:
            continue
        d['line'], d['lines'] = line, new_lines
        note = 'Book lines (RotoWire, %s): %s; consensus %s.' % (
            now[:10], ', '.join('%s %g' % (b, l) for b, l in sorted(books.items())), '%g' % line)
        flipped = side != old_side
        if flipped:
            d['side'] = side
            d['confidence'] = min(int(d.get('confidence') or 2), 2)
            if d.get('must'):
                d['must'] = {'__delete__': True}
            note += ' Side moved to %s: projection %g vs the book line.' % (side, p)
        d['analysis'] = (d.get('analysis') or '').rstrip() + ' ' + note
        src = {'title': 'RotoWire: %s player props (book lines)' % s.upper(), 'url': URL % s}
        if not any(x.get('url') == src['url'] for x in d.get('sources', [])):
            d.setdefault('sources', []).append(src)
        json.dump(d, open(os.path.join(out, fn), 'w'), indent=1)
        summary.append({'id': fn[:-5], 'player': d['player'], 'stat': d['stat'], 'old': old_line, 'new': line,
                        'side': side, 'flipped': flipped})
    json.dump(summary, open(os.path.join(out, 'changes.json'), 'w'), indent=1)
    print('changed', len(summary), 'flipped', sum(x['flipped'] for x in summary))


if __name__ == '__main__':
    main()
