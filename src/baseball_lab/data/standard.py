"""Cross-source season contract. Missing measurements never become zero.

Source IDs are scoped by provider and league, not matched by player names.
This contract does not turn season totals into action/transition training data.
"""
from baseball_lab.data.lineage import content_hash

SCHEMA='league-season-stat-v1'
COUNTS=('G','PA','TBF','AB','H','2B','3B','HR','SO','BB','HBP','SF','SH','R','RBI','SB','CS','IP_OUTS','ER','TB','IBB','GDP','W','L','SV','HLD','WP','BK','CG','SHO')
REASONS=('not_collected','not_published','ambiguous_definition','not_applicable')


def innings_outs(text):
    """Baseball IP notation, not decimal innings. Reject ambiguous fractions."""
    if not isinstance(text,str):raise ValueError('이닝은 원문 문자열로 제공하세요.')
    parts=text.strip().split('.')
    if len(parts)>2 or not parts[0].isdigit() or (len(parts)==2 and parts[1] not in ('0','1','2')):
        raise ValueError('확인할 수 없는 이닝 표기입니다.')
    return int(parts[0])*3+(int(parts[1]) if len(parts)==2 else 0)


def normalize_season_row(*,league,season,role,source_player_id,source_namespace,counts,
                         source_sha256,team=None,row_kind='season_total',missing_reasons=None):
    if league not in ('MLB','KBO','NPB'):raise ValueError('등록된 리그가 아닙니다.')
    if type(season) is not int or not 1800<=season<=2200:raise ValueError('시즌 연도를 확인하세요.')
    if role not in ('batter','pitcher','team_batting','team_pitching'):raise ValueError('집계 역할을 확인하세요.')
    if row_kind not in ('season_total','team_split'):raise ValueError('전체 시즌과 팀별 분할을 구분하세요.')
    for value in (source_player_id,source_namespace,source_sha256):
        if not isinstance(value,str) or not value.strip():raise ValueError('원천 식별자와 지문이 필요합니다.')
    if row_kind=='team_split' and not team:raise ValueError('팀 분할에는 팀 식별자가 필요합니다.')
    if set(counts)-set(COUNTS):raise ValueError('의미를 등록하지 않은 원천 열입니다.')
    reasons=dict(missing_reasons or {})
    if set(reasons)-set(COUNTS):raise ValueError('결측 사유의 필드가 등록되지 않았습니다.')
    normalized={}
    for key in COUNTS:
        value=counts.get(key)
        if value is not None and (type(value) is not int or value<0):raise ValueError('계수는 음수가 아닌 정수 또는 결측이어야 합니다: '+key)
        if value is None:
            reason=reasons.setdefault(key,'not_collected')
            if reason not in REASONS:raise ValueError('결측 사유를 확인하세요.')
        elif key in reasons:raise ValueError('값이 있는 필드에 결측 사유를 붙일 수 없습니다.')
        normalized[key]=value
    c=normalized
    if c['H'] is not None:
        if c['AB'] is not None and c['H']>c['AB']:raise ValueError('안타가 타수보다 큽니다.')
        if all(c[k] is not None for k in ('2B','3B','HR')) and sum(c[k] for k in ('2B','3B','HR'))>c['H']:
            raise ValueError('장타 합계가 안타보다 큽니다.')
    denominator=c['PA'] if role in ('batter','team_batting') else c['TBF']
    if denominator is not None:
        if c['AB'] is not None and c['AB']>denominator:raise ValueError('타수가 타석 분모보다 큽니다.')
        for key in ('H','SO','BB','HBP'):
            if c[key] is not None and c[key]>denominator:raise ValueError('사건 계수가 타석 분모보다 큽니다.')
        known=sum(c[key] or 0 for key in ('H','SO','BB','HBP'))
        if known>denominator:raise ValueError('타석 사건 계수가 서로 모순됩니다.')
    complete=all(c[k] is not None for k in ('H','SO','BB','HBP','2B','3B','HR')) and denominator is not None and denominator>0
    events=None
    if complete:
        events={'strikeout':c['SO'],'walk':c['BB'],'hbp':c['HBP'],
                'single':c['H']-c['2B']-c['3B']-c['HR'],'double':c['2B'],
                'triple':c['3B'],'home_run':c['HR'],'other':denominator-c['H']-c['SO']-c['BB']-c['HBP']}
    identity={'league':league,'season':season,'role':role,'source_namespace':source_namespace,
              'source_player_id':source_player_id,'row_kind':row_kind,'team':team}
    return {'schema':SCHEMA,**identity,'entity_id':content_hash(identity),
            'source_sha256':source_sha256,'counts':c,'missing_reasons':reasons,
            'units':{'counts':'events','IP_OUTS':'outs','rates':'explicit numerator/denominator'},
            'events':events,'eligibility':{'descriptive':True,'categorical_partition':complete,
                'policy_learning':False,'cross_league_calibrated':False},
            'limitations':['Season aggregates do not identify actions, transitions or counterfactual outcomes.',
                           'League/rules/era/park effects are not removed by sharing column names.']}


def select_window(rows,*,leagues=None,start=None,end=None,last_seasons=None):
    """Select a collection window without erasing league/season context.

    last_seasons means each league's last N available seasons, not a global
    MLB date boundary. Returns constituent rows, not a pooled ability estimate.
    """
    if leagues is not None and (not leagues or set(leagues)-{'MLB','KBO','NPB'}):raise ValueError('수집할 리그를 확인하세요.')
    for year in (start,end):
        if year is not None and (type(year) is not int or not 1800<=year<=2200):raise ValueError('시즌 연도를 확인하세요.')
    if last_seasons is not None and (type(last_seasons) is not int or last_seasons<1):raise ValueError('최근 시즌 수는 양의 정수입니다.')
    if start is not None and end is not None and start>end:raise ValueError('시즌 범위가 역전됐습니다.')
    selected=[r for r in rows if (leagues is None or r['league'] in leagues) and
              (start is None or r['season']>=start) and (end is None or r['season']<=end)]
    if last_seasons:
        allowed={league:set(sorted({r['season'] for r in selected if r['league']==league})[-last_seasons:]) for league in {r['league'] for r in selected}}
        selected=[r for r in selected if r['season'] in allowed[r['league']]]
    ids=[r['entity_id'] for r in selected]
    if len(ids)!=len(set(ids)):raise ValueError('동일한 원천 개체·시즌 행이 중복됐습니다.')
    groups={}
    for r in selected:
        key=(r['league'],r['season'],r['role'],r['source_namespace'],r['source_player_id'])
        groups.setdefault(key,set()).add(r['row_kind'])
    if any(len(kinds)>1 for kinds in groups.values()):raise ValueError('시즌 합계와 팀 분할을 함께 합산할 수 없습니다.')
    return selected
