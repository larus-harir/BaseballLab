"""Frozen R1 policies on an independent registered season; no tuning/retraining."""
import argparse
import json
from pathlib import Path
from baseball_lab.data.lineage import checksum, write_json
from baseball_lab.experiments.registry import REPOSITORY_ROOT
from baseball_lab.r1.provider import acquire
from baseball_lab.r1.environment import Environment, fit, restore, diagnostic
from .training import evaluate


def external(research,year,*,n=500):
    research=Path(research);result=json.loads(research.read_text(encoding='utf-8'))
    if result['status']!='COMPLETED':raise ValueError('학습이 완료된 정책만 독립 시즌에서 평가합니다.')
    if n<20:raise ValueError('최소 20회 평가가 필요합니다.')
    start,end=result['model']['selected_dates']
    if start[:4]==str(year) or end[:4]==str(year):raise ValueError('학습과 다른 시즌을 선택하세요.')
    original=acquire(REPOSITORY_ROOT/'data/local/retrosheet',year=int(start[:4]))
    envs,model=fit(original,start,end)
    target=acquire(REPOSITORY_ROOT/'data/local/retrosheet',year=year)
    # Legal actions are frozen from original fit/validation, never selected on the new season.
    env=Environment(target['records'],envs['fit'].legal,f'external-season-{year}')
    rows=[]
    for run in result['seeds']:
        checkpoint=research.parent/run['checkpoints'][-1]
        saved=json.loads(checkpoint.read_text(encoding='utf-8'))
        if saved['run_id']!=result['run_id'] or saved['dataset_id']!=model['dataset_id']:
            raise ValueError('저장 정책의 연구·원천이 일치하지 않습니다.')
        rows.append({'seed':run['seed'],'checkpoint_sha256':checksum(checkpoint),
                     **evaluate(env,restore(saved['batter']),restore(saved['pitcher']),n,run['seed']+900000)})
    evidence={'year':year,'run_id':result['run_id'],'source_url':target['manifest']['source_url'],
              'dataset_id':target['manifest']['dataset_id'],'games':target['manifest']['games'],
              'turns':target['manifest']['used_segments'],'training_executed':False,'rows':rows,
              'transition_check':diagnostic(envs['fit'],target['records']),
              'scope':'Frozen policies, whole independent season, unchanged legal actions and 24-state starts; not causal or historical strategy validation.',
              'credit':target['manifest']['credit']}
    path=research.parent/f'external-{year}.json'
    if path.exists():raise ValueError('기존 외부 평가를 덮어쓰지 않습니다.')
    write_json(path,evidence)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='저장 정책을 학습에 쓰지 않은 시즌에서 확인')
    parser.add_argument('--research',required=True,type=Path);parser.add_argument('--year',type=int,required=True)
    args=parser.parse_args();result=external(args.research,args.year)
    print(f"외부 {args.year}년 평가 완료: {result['games']}경기 / 재학습 없음")
