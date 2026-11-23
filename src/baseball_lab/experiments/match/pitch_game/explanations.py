"""Plain-language interpretations of recorded signals, never invented thoughts."""
from collections import Counter

FAMILIES={'fastball':'직구','sinker':'싱커·투심','cutter':'커터','slider':'슬라이더','curve':'커브','changeup':'체인지업','splitter':'포크·스플리터','knuckle':'너클볼'}
NAMES={'swing':'스윙','take':'지켜보기','bunt':'번트','steal':'도루','pitch':'구종 지정 없는 투구','intentional_walk':'고의볼넷','pull':'당겨치기','center':'가운데 타격','opposite':'밀어치기','left':'좌측 타격','right':'우측 타격'}
HEIGHTS={'high':'높은 코스','middle':'중간 높이 코스','low':'낮은 코스'}


def particle(text,closed,opened):
    c=ord(text[-1]);return text+(closed if 0xAC00<=c<=0xD7A3 and (c-0xAC00)%28 else opened)


def label(action):
    if action.startswith('family:'):return FAMILIES.get(action.split(':')[1],action)
    if action.startswith('area:'):
        side,height=action.split(':')[1].split('_')
        return {'left':'왼쪽','middle':'가운데','right':'오른쪽'}[side]+' '+HEIGHTS[height]
    return NAMES.get(action.split(':')[-1],action)


def explain(overview,defense,defense_feedback=None):
    rows=[]
    for view in ('offense','direction','defense','course'):
        values=overview['preferences'][view]
        if not values['after']:continue
        candidates=[k for k in values['after'] if k.startswith('family:')] if view=='defense' else []
        action=max(candidates or values['after'],key=lambda a:values['after'][a])
        before=values['before'].get(action,0);after=values['after'][action];delta=after-before
        row=overview['feedback'][view].get(action,{})
        signal=row.get('mean_advantage');n=row.get('decisions',0);name=label(action)
        summary=particle(name,'을','를')+' '+('조금 더 고르는 쪽으로 바뀌었습니다.' if 0<delta<.02 else '더 자주 고르는 쪽으로 바뀌었습니다.' if delta>=.02 else '이전보다 덜 고르지만 여전히 가장 선호합니다.' if delta<0 else '계속 가장 선호하고 있습니다.')
        if signal is None:
            reason='선택은 달라졌지만 이 실행에는 승패 학습 신호가 남아 있지 않아 이유를 더 좁힐 수 없습니다.'
        elif signal>0:
            reason='이 선택을 한 경험에서 상대적으로 좋은 승패 신호를 받았습니다. 학습은 이를 유리한 경험으로 반영했습니다.' if delta>=0 else '이 선택의 승패 신호는 유리했지만 최종 선호는 줄었습니다. 다른 선택과 함께 갱신된 영향이 있어 이 신호만으로 변화 이유를 설명하기는 어렵습니다.'
        elif signal<0:
            reason='이 선택을 한 경험의 승패 신호는 불리한 방향이었습니다.'+(' 그런데 최종 선호는 늘어, 다른 선택과의 공유 갱신 영향도 함께 봐야 합니다.' if delta>0 else ' 학습에서는 이 경험을 불리한 신호로 반영했습니다.')
        else:reason='이 선택의 승패 신호에는 뚜렷한 방향이 없었습니다. 최종 선호 변화만으로 유리한 전략을 찾았다고 보지는 않습니다.'
        context='';pattern=None
        if view=='defense' and action.startswith('family:'):
            heights=Counter()
            for pitch,count in defense.items():
                parts=pitch.split(':')
                if len(parts)<4 or parts[0]!='pitch' or parts[1]!=action.split(':')[1] or parts[2]=='any':continue
                height=parts[2].split('_')[-1]
                if height in HEIGHTS:heights[height]+=count
            if heights:
                height=heights.most_common(1)[0][0];pattern={'height':height,'count':heights[height],'known':sum(heights.values())}
                context=particle(name,'은','는')+f' {HEIGHTS[height]}에서 가장 많이 사용했습니다.'
                joint=Counter()
                for pitch,detail in (defense_feedback or {}).items():
                    parts=pitch.split(':')
                    if len(parts)>=4 and parts[0]=='pitch' and parts[1]==action.split(':')[1] and parts[2].endswith('_'+height):
                        for field in ('decisions','hits','strikeouts'):joint[field]+=detail.get(field,0)
                if joint['decisions']:
                    pattern.update(joint)
        observed=''
        if n and row.get('events'):
            if view in ('offense','direction'):
                walks=row.get('terminal_results',{}).get('walk',0)
                observed=f'실제 연습에서는 이 선택 100회당 안타 {100*row.get("hits",0)/n:.1f}회, 볼넷 {100*walks/n:.1f}회가 기록됐습니다.'
            else:
                observed=f'실제 연습에서는 투구 100구당 피안타 {100*row.get("hits",0)/n:.1f}회, 삼진 {100*row.get("strikeouts",0)/n:.1f}회가 기록됐습니다.'
                if pattern and pattern.get('decisions'):
                    m=pattern['decisions'];observed=f'이 구종·높이 조합에서 100구당 피안타 {100*pattern["hits"]/m:.1f}회, 삼진 {100*pattern["strikeouts"]/m:.1f}회가 기록됐습니다.'
        rows.append({'view':view,'action':action,'title':name,'summary':summary,'reason':reason,'context':context,'observed':observed,
                     'before':before,'after':after,'delta':delta,'decisions':n,'signal':signal,'pattern':pattern})
    return rows
