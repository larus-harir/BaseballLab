"""Individually inspected official distributions, not unchecked year substitution."""
RELEASES = {
    2024: {'url':'https://www.retrosheet.org/downloads/plays/2024plays.zip',
           'sha256':'a3e8c08876ddf70e1ffb0b20486c2873cf4aae19e0acc8002096e9056107615b'},
    2023: {'url':'https://www.retrosheet.org/downloads/plays/2023plays.zip',
           'skip_empty_no_play':True,
           'sha256':'0129befd7944f60a858e5fdc265a44ed20afaa568679b37fca1083e3c083b20e'},
}

# Earliest/latest actual regular-season play dates in the pinned releases.
PERIODS = {2023:{'start':'2023-03-30','end':'2023-10-01'},
           2024:{'start':'2024-03-20','end':'2024-09-30'}}


def validate_period(start,end,*,min_days=3):
    from datetime import date
    if not isinstance(start,str) or not isinstance(end,str) or not start or not end:
        raise ValueError('기록 시작일과 종료일을 모두 선택하세요.')
    try:first,last=date.fromisoformat(start),date.fromisoformat(end)
    except ValueError:raise ValueError('날짜를 연-월-일 형식으로 선택하세요.') from None
    if first.year not in PERIODS or last.year not in PERIODS:
        raise ValueError('현재 학습할 수 있는 시즌은 2023년과 2024년입니다.')
    if first.year!=last.year:raise ValueError('시즌을 섞을 수 없습니다. 같은 연도의 날짜를 선택하세요.')
    bounds=PERIODS[first.year]
    if str(first)<bounds['start'] or str(last)>bounds['end']:
        raise ValueError(f"{first.year}년 기록 범위는 {bounds['start']}부터 {bounds['end']}까지입니다.")
    if first>last:raise ValueError('종료일은 시작일보다 같거나 뒤여야 합니다.')
    if (last-first).days<min_days-1:raise ValueError('학습·검사·최종 확인을 나누려면 최소 3일을 선택하세요. 시즌 전체를 권장합니다.')
    return str(first),str(last)
