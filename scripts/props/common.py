"""Shared settings for the prop builders.

PROPS_WORK  working folder for downloads, the database export and new pick docs (default: <repo>/.props-work)
PROPS_TODAY date the run treats as today, YYYY-MM-DD (default: today, US Eastern)
PROPS_WEEK  week id / Monday the picks belong to (default: Monday of PROPS_TODAY's week)
"""
import datetime, os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.environ.get('PROPS_WORK', os.path.join(REPO, '.props-work'))
_today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4))).date()
TODAY = os.environ.get('PROPS_TODAY', _today.isoformat())
_t = datetime.date.fromisoformat(TODAY)
WEEK = os.environ.get('PROPS_WEEK', (_t - datetime.timedelta(days=_t.weekday())).isoformat())
SEASON_YEAR = _t.year if _t.month >= 7 else _t.year - 1  # NHL/NFL/CFB season start year
os.makedirs(WORK, exist_ok=True)
