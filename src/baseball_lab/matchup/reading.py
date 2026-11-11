"""Result interpretation shared by new runs and read-only older report views."""
from collections import Counter
from .models import EVENTS,LABELS


def interpret(result):
    if result['model']['model']=='common':
        q=result['model']['probabilities'];s=result['simulation']
        return {'headline':'리그 평균 대비 공통 기록 비교 · 절대 실력 검증 전',
            'rows':[{'key':k,'label':result['labels'][k],'count':s['counts'][k],'expected':s['expected'][k],'probability':q[k]} for k in q],
            'notes':[result['scope']],'hits':s['counts']['hit'],'extra_base_hits':None,
            'events':s['events'],'labels':result['labels'],'denominator':s['n']}
    simulation=result['simulation'];q=result['model']['probabilities'];n=simulation['n'];counts=simulation['counts']
    detail=result.get('event_display',{});display=detail.get('events',simulation['events']);labels={**LABELS,**detail.get('labels',{})}
    labels['other']='기타 결과 (세부 기록 없음)'
    actual=Counter(display);rows=[]
    rates=detail.get('other',{}).get('conditional_rates',{})
    for key in EVENTS:
        if key=='other' and rates:
            rows.extend({'key':sub,'label':labels[sub],'count':actual[sub],'expected':n*q[key]*rate,
                         'probability':q[key]*rate} for sub,rate in rates.items() if rate)
        else:rows.append({'key':key,'label':labels[key],'count':counts[key],'expected':n*q[key],'probability':q[key]})
    hits=sum(counts[k] for k in ('single','double','triple','home_run'))
    extra=sum(counts[k] for k in ('double','triple','home_run'))
    expected_k=n*q['strikeout'];difference=counts['strikeout']-expected_k
    notes=[f"안타 {hits}개 중 장타는 {extra}개입니다.",
           f"삼진은 예상 {expected_k:.1f}개보다 {abs(difference):.1f}개 {'많았습니다' if difference>0 else '적었습니다' if difference<0 else '차이 없었습니다'}."]
    if not difference:notes[-1]=f'삼진은 예상 {expected_k:.1f}개와 같았습니다.'
    other=detail.get('other',{'detail_available':False,'simulation_n':counts['other'],
        'definition':'삼진·볼넷·안타 등 표시한 개별 사건에 속하지 않은 결과입니다.',
        'reason':'이 저장 결과에는 원인별 타석 정보가 없습니다. 전부 타자 아웃으로 해석하지 않습니다.'})
    if not detail and result['model']['model']=='legacy':
        other['definition']='과제 원본에서 삼진·볼넷·안타를 뺀 나머지입니다. 사구를 별도로 구분하지 않았습니다.'
    return {'rows':rows,'notes':notes,'hits':hits,'extra_base_hits':extra,'other':other,
            'events':display,'labels':labels,'denominator':n}
