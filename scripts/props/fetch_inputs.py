#!/usr/bin/env python3
"""Download the schedule, stats, injury and goalie files the builders read. Run once per session, before the builders."""
import datetime, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK, WEEK, TODAY, SEASON_YEAR

UA = {'User-Agent': 'Mozilla/5.0'}
def raw(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
def save(path, u):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        open(path, 'wb').write(raw(u))
    except Exception as e:
        print('failed', u, e)

week = datetime.date.fromisoformat(WEEK)
days = [week + datetime.timedelta(days=i) for i in range(8)]  # through the next Monday (MNF, Monday NHL)

# ESPN slate for the week (CFB limited to the Top 25 group)
ESPN = {'nfl': 'football/nfl', 'cfb': 'football/college-football', 'nhl': 'hockey/nhl', 'wnba': 'basketball/wnba'}
slate = {}
for s, p in ESPN.items():
    ev = {}
    for d in days:
        extra = '&groups=80&limit=300' if s == 'cfb' else ''
        try:
            data = json.loads(raw(f'https://site.api.espn.com/apis/site/v2/sports/{p}/scoreboard?dates={d:%Y%m%d}{extra}'))
        except Exception as e:
            print('failed', s, d, e); continue
        for e in data.get('events', []):
            c = e['competitions'][0]; t = {x['homeAway']: x for x in c['competitors']}
            ev[e['id']] = dict(id=e['id'], date=e['date'], name=e['shortName'], state=e['status']['type']['state'],
                               home=t['home']['team']['abbreviation'], away=t['away']['team']['abbreviation'],
                               hr=t['home'].get('curatedRank', {}).get('current'), ar=t['away'].get('curatedRank', {}).get('current'),
                               note=(c.get('notes') or [{}])[0].get('headline', ''))
    slate[s] = sorted(ev.values(), key=lambda e: e['date'])
    print(s, len(slate[s]), 'games,', sum(e['state'] == 'pre' for e in slate[s]), 'not started')
os.makedirs(f'{WORK}/sched', exist_ok=True)
json.dump(slate, open(f'{WORK}/sched/slate.json', 'w'), indent=1)

# NHL: two seasons of skater/goalie/team stats, injuries, today's goalies, daily scores
N = f'{WORK}/nhl'
for season in (f'{SEASON_YEAR - 1}{SEASON_YEAR}', f'{SEASON_YEAR}{SEASON_YEAR + 1}'):
    q = f'limit=-1&cayenneExp=seasonId={season}%20and%20gameTypeId=2'
    save(f'{N}/sum_{season}.json', f'https://api.nhle.com/stats/rest/en/skater/summary?{q}')
    save(f'{N}/rt_{season}.json', f'https://api.nhle.com/stats/rest/en/skater/realtime?{q}')
    save(f'{N}/g_{season}.json', f'https://api.nhle.com/stats/rest/en/goalie/summary?{q}')
    save(f'{N}/team_{season}.json', f'https://api.nhle.com/stats/rest/en/team/summary?{q}')
save(f'{N}/inj.json', 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries')
save(f'{N}/dfo.html', 'https://www.dailyfaceoff.com/starting-goalies')
for d in days:
    save(f'{N}/score_{d:%d}.json', f'https://api-web.nhle.com/v1/score/{d.isoformat()}')

# WNBA injuries
save(f'{WORK}/wnba/inj.json', 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries')
print('inputs saved under', WORK, '| today', TODAY, '| week', WEEK)
