"""Fictional identities and scouting grades for the manager interface."""
from bisect import bisect_left, bisect_right
from functools import lru_cache
from random import Random

from . import season

SURNAMES = '김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 전 홍 유 문 양 손 백 노 진 주 남 고'.split()
GIVEN_NAMES = ('도윤 민준 서준 이준 시우 하준 지호 지후 예준 준우 유찬 하진 태오 지한 현우 '
               '재윤 재하 강우 연준 건우 준서 정후 서우 태윤 선우 도현 준혁 승우 현준 진우').split()


@lru_cache(maxsize=16)
def names(seed):
    profiles=season.league()[0]
    real_names={p['name'] for p in profiles.values()}
    possibilities=[surname+given for surname in SURNAMES for given in GIVEN_NAMES if surname+given not in real_names]
    Random(f'{seed}:fictional-roster').shuffle(possibilities)
    if len(possibilities)<len(profiles):
        raise ValueError('가상 선수 이름 풀이 부족합니다.')
    return dict(zip(sorted(profiles),possibilities))


def trait_score(focus,profile,rates):
    event,direction,_=season.TRAINING[profile['role']][focus]
    if focus=='power':
        singles,doubles,triples=profile['hit_mix']
        extra=(doubles+triples)/(singles+doubles+triples)
        return rates['home_run']+rates['hit_other']*extra
    return direction*rates[event]


@lru_cache(maxsize=1)
def distributions():
    profiles,_,_,pools,_=season.league()
    return {role:{focus:sorted(trait_score(focus,profiles[key],profiles[key]['rates']) for key in pools[role])
                  for focus in choices} for role,choices in season.TRAINING.items()}


def grade(focus,profile,rates):
    values=distributions()[profile['role']][focus]
    score=trait_score(focus,profile,rates)
    # Midrank keeps tied abilities at the same grade.
    percentile=(bisect_left(values,score)+bisect_right(values,score))/(2*len(values))
    return next(letter for threshold,letter in ((.93,'S'),(.75,'A'),(.45,'B'),(.20,'C'),(0,'D'))
                if percentile>=threshold)


def scouting(profile,focus):
    current=season.adjusted(profile,focus)
    ratings=[];training=[]
    for key,(event,_,label) in season.TRAINING[profile['role']].items():
        rating=grade(key,profile,current)
        ratings.append({'id':key,'name':label,'grade':rating})
        preview=season.adjusted(profile,key)
        if round(preview[event]*100,1)!=round(profile['rates'][event]*100,1):
            training.append({'id':key,'name':label,'before':grade(key,profile,profile['rates']),
                             'after':grade(key,profile,preview)})
    return ratings,training
