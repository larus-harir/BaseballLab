"""Replay frozen empirical policies against their bound, verified data/model."""
import json
from pathlib import Path

from baseball_lab.data.lineage import write_json
from baseball_lab.outcome.empirical import load_model
from baseball_lab.tracking.evidence_report import write_report
from .training import restore,probes
from .environment import EmpiricalEnvironment,OBSERVATION_SCHEMA,ACTION_SCHEMA


def replay(checkpoint,model_path,output,*,seed=20261104,test_only=False):
    model,dataset=load_model(model_path,test_only=test_only)
    snapshot=json.loads(Path(checkpoint).read_text(encoding='utf-8'))
    if (snapshot.get('checkpoint_version')!='empirical-pa-policies-v1'
            or snapshot.get('model_id')!=model.artifact['model_id']
            or snapshot.get('dataset_version')!=model.artifact['dataset_version']
            or snapshot.get('observation_schema')!=OBSERVATION_SCHEMA
            or snapshot.get('action_schema')!=ACTION_SCHEMA
            or snapshot.get('pitch_types')!=list(model.pitch_types)):
        raise ValueError('정책·데이터·모델 버전이 호환되지 않습니다.')
    if snapshot['source_status']=='MOCK_TEST_ONLY' and not test_only:
        raise ValueError('MOCK_TEST_ONLY 정책을 연구 재생에 사용할 수 없습니다.')
    batter,pitcher=restore(snapshot['batter'],model.pitch_types),restore(snapshot['pitcher'],model.pitch_types)
    if batter.role!='batter' or pitcher.role!='pitcher': raise ValueError('정책 역할 불일치')
    env=EmpiricalEnvironment(model,snapshot['run_id'])
    events=[]
    for i in range(8):
        result=env.play(batter,pitcher,seed+i,f'replay:{snapshot["checkpoint_step"]}:{i}',record=True)
        for event in result.events:
            event.update({'checkpoint_step':snapshot['checkpoint_step'],'seed':seed+i})
            if test_only:event.update({'source_status':'MOCK_TEST_ONLY','probability_status':'MOCK_TEST_ONLY','location_status':'MOCK_TEST_ONLY'})
        events.extend(result.events)
    replays=[{'checkpoint_step':snapshot['checkpoint_step'],'seed_start':seed,'events':events}]
    run={'run_id':snapshot['run_id'],'training_executed':False,'research_executed':not test_only,
         'config':{'episodes':snapshot['checkpoint_step']},'source_statuses':{'events':snapshot['source_status']},
         'history':[{'checkpoint_step':snapshot['checkpoint_step'],'training_episodes':snapshot['checkpoint_step'],
                     'optimizer_steps':{'batter':batter.steps,'pitcher':pitcher.steps},'evaluation':[],
                     'probes':probes(batter,pitcher),'decisions':{'learner_batter_decisions':{},'learner_pitcher_decisions':{},'first_pitch_batter':{}},
                     'opponent_pool':snapshot['opponent_pool'],'source_status':snapshot['source_status'],
                     'batter_policy_id':f"{snapshot['run_id']}:batter:{snapshot['checkpoint_step']}",
                     'pitcher_policy_id':f"{snapshot['run_id']}:pitcher:{snapshot['checkpoint_step']}"}]}
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("재생 결과를 덮어쓰지 않습니다. 새 --output을 지정하세요.")
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'replays.json',replays);write_json(output/'evaluation.json',run)
    write_report(output,run,dataset,model.artifact,replays)
    return replays
