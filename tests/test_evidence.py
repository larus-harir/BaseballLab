"""All generated inputs below are MOCK_TEST_ONLY. No research dataset is fabricated."""
import csv
import json
import os
from pathlib import Path
from random import Random
from unittest.mock import patch

import numpy as np
import pytest

from baseball_lab.data.lineage import RawSource,checksum,content_hash
from baseball_lab.data.statcast import audit,load_dataset,acquire,manual_source,REQUIRED
from baseball_lab.outcome.empirical import fit,load_model,EmpiricalModel
from baseball_lab.research.training import ResearchConfig,train,neural
from baseball_lab.research.replay import replay
from baseball_lab.research.environment import EmpiricalEnvironment
from baseball_lab.tracking.evidence_report import write_report


@pytest.fixture
def fixture_data(tmp_path):
    # Independent, deliberately artificial rows for adapter/model/optimizer correctness.
    rows=[]
    for day_index,day in enumerate(('2024-05-01','2024-05-02','2024-05-03'),1):
        counter=0
        for b in range(4):
            for s in range(3):
                for kind in ('FF','SL'):
                    for action in ('take','swing'):
                        for repeat in range(2):
                            counter+=1
                            description=('called_strike' if kind=='FF' else 'ball') if action=='take' else (
                                'foul' if repeat==0 else 'swinging_strike' if kind=='FF' else 'hit_into_play')
                            rows.append(dict(game_date=day,game_pk=day_index*100000+counter,at_bat_number=1,pitch_number=1,
                                             balls=b,strikes=s,pitch_type=kind,description=description,
                                             events='single' if description=='hit_into_play' else '',game_type='R',
                                             plate_x=0.1 if repeat==0 else 1.2,plate_z=2.5,sz_top=3.5,sz_bot=1.5,
                                             release_speed=90,release_spin_rate='',launch_speed='',launch_angle=''))
    path=tmp_path/'mock_test_only.csv'
    with path.open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    source=RawSource('MOCK_TEST_ONLY fixture','https://example.invalid/mock',str(path),'2024-05-04T00:00:00+00:00',
                     checksum(path),'MOCK_TEST_ONLY','Test generated, no real baseball observations','unit_test_generator')
    dataset=audit([source],tmp_path/'data')
    return tmp_path,source,dataset


@pytest.fixture
def fitted(fixture_data):
    root,source,dataset=fixture_data
    artifact=fit(root/'data/dataset.json',root/'model',train_before='2024-05-02',test_from='2024-05-03',
                 min_support=1,min_fit_rows=1,min_holdout_rows=1,test_only=True)
    assert artifact['validation']['eligibility_issues']==[]
    return root,source,dataset,artifact


def test_units_missingness_and_status(fixture_data):
    root,source,data=fixture_data
    m=data['manifest']
    assert m['source_status']=='MOCK_TEST_ONLY' and m['used_rows']==288
    assert m['missingness_report']['release_spin_rate']['rate']==1
    assert data['records'][0]['release_spin_rate'] is None
    assert data['records'][0]['release_speed_kmh']==pytest.approx(144.84096)
    assert load_dataset(root/'data/dataset.json')==data


def test_raw_hash_and_normalized_data_corruption(fixture_data):
    root,source,data=fixture_data
    data['records'][0]['balls']=2
    (root/'data/dataset.json').write_text(json.dumps(data))
    with pytest.raises(ValueError,match='무결성'):
        load_dataset(root/'data/dataset.json')
    Path(source.path).write_text('corrupt')
    with pytest.raises(ValueError,match='해시'):
        source.verify()


def test_duplicates_and_conflicting_ids(fixture_data):
    root,source,data=fixture_data
    result=audit([source,source],root/'duplicates')
    assert result['manifest']['used_rows']==288 and result['manifest']['exclusions']['duplicate']==288
    raw=Path(source.path).read_text().replace('called_strike','ball',1)
    other=root/'conflicting.csv';other.write_text(raw)
    conflict=RawSource(**{**source.to_dict(),'path':str(other),'raw_file_checksum':checksum(other)})
    with pytest.raises(ValueError,match='충돌'):
        audit([source,conflict],root/'bad')


def test_no_mock_calibration_or_model_in_research(fitted):
    root,source,data,artifact=fitted
    assert not artifact['validation']['research_ready']
    assert artifact['validation']['status']=='MOCK_TEST_ONLY'
    with pytest.raises(ValueError,match='실제 기록'):
        fit(root/'data/dataset.json',root/'no',train_before='2024-05-02',test_from='2024-05-03')
    with pytest.raises(ValueError,match='연구 실행 보류'):
        load_model(root/'model/model.json')
    with pytest.raises(ValueError):
        train(ResearchConfig(episodes=8),root/'model/model.json',root/'no-run')
    assert not (root/'no-run').exists()


def test_time_split_no_leakage_and_validation_is_independent(fitted):
    root,source,data,a=fitted
    ids=[set(a['split'][key]['record_ids']) for key in ('fit','validation','test')]
    assert not ids[0]&ids[1] and not ids[0]&ids[2] and not ids[1]&ids[2]
    assert {r['game_date'] for r in a['fit_records']}=={'2024-05-01'}
    assert a['validation']['test']['n']==96
    assert all(v['absolute_error']==pytest.approx(0) for v in a['validation']['test']['distributions'])
    assert all(v['absolute_mean_error']==pytest.approx(0) for v in a['validation']['test']['arrival_validation'])
    assert all(status=='MOCK_TEST_ONLY' for status in a['validation']['test']['source_statuses'].values())


def test_empirical_frequencies_and_action_independent_pitch_arrival(fitted):
    root,source,data,a=fitted
    model,dataset=load_model(root/'model/model.json',test_only=True)
    for b in range(4):
        for s in range(3):
            for kind in model.pitch_types:
                first=model.sample(b,s,kind,'take',Random(14))
                second=model.sample(b,s,kind,'swing',Random(14))
                assert first['sampled_record']['record_id']==second['sampled_record']['record_id']
                assert sum(first['probabilities'].values())==pytest.approx(1)
                assert all(reference in a['split']['fit']['record_ids'] for reference in second['reference_record_ids'])
                assert first['sampled_record']['pitch_type']==kind
    with pytest.raises(ValueError,match='지원하지 않는 행동'):
        model.probabilities(0,0,'UNSUPPORTED','swing')


def test_sparse_pooling_reports_used_support(fitted):
    root,source,data,a=fitted
    a['settings']['min_support']=3
    model=EmpiricalModel(a)
    probs,n,level=model.probabilities(0,0,'FF','take',a['fit_records'][0])
    assert n>=3 and 'pooled' in level


def test_model_hash_and_bound_dataset(fitted):
    root,source,data,a=fitted
    a['fit_records'][0]['event']='home_run'
    (root/'model/model.json').write_text(json.dumps(a))
    with pytest.raises(ValueError,match='무결성'):
        load_model(root/'model/model.json',test_only=True)


def test_acquisition_failure_records_no_fake_data(tmp_path):
    with patch('baseball_lab.data.statcast.request_bytes',side_effect=OSError('403 policy denied')):
        with pytest.raises(OSError):
            acquire('2024-05-01','2024-05-02',tmp_path,usage_note='test request',authorization_reference='MOCK_TEST_ONLY request test')
    failure=json.loads((tmp_path/'acquisition_failure.json').read_text())
    assert failure['research_executed'] is False and failure['partial_sources']==[]
    assert not list(tmp_path.glob('*.csv'))


def test_robots_denial_and_html_response(tmp_path):
    with patch('baseball_lab.data.statcast.request_bytes',return_value=b'User-agent: *\nDisallow: /'):
        with pytest.raises(PermissionError):
            acquire('2024-05-01','2024-05-01',tmp_path/'robots',usage_note='test',authorization_reference='MOCK_TEST_ONLY request test')
    with patch('baseball_lab.data.statcast.request_bytes',side_effect=[b'User-agent: *\nAllow: /',b'<html>error</html>']):
        with pytest.raises(ValueError,match='CSV'):
            acquire('2024-05-01','2024-05-01',tmp_path/'html',usage_note='test',authorization_reference='MOCK_TEST_ONLY request test')
    assert not list(tmp_path.rglob('*.csv'))


def test_manual_export_requires_real_source_and_timezone(tmp_path):
    path=tmp_path/'raw.csv';path.write_text('test')
    with pytest.raises(ValueError):manual_source(path,'http://example.com','note','2024-01-01T00:00:00+00:00')
    with pytest.raises(ValueError,match='시간대'):manual_source(path,'https://baseballsavant.mlb.com/statcast_search','note','2024-01-01T00:00:00')


def test_empty_view_has_no_research_results(tmp_path):
    write_report(tmp_path,failure={'error':'source blocked','research_executed':False})
    data=json.loads((tmp_path/'report-data.json').read_text())
    assert data['status']=='DATA_REQUIRED' and data['run'] is None
    assert data['observed']==data['replays']==[] and data['model'] is None
    assert 'source blocked' in (tmp_path/'report.html').read_text(encoding='utf-8')


def test_two_policies_really_update_and_replay_without_research_claim(fitted):
    root,source,data,a=fitted
    config=ResearchConfig(episodes=24,evaluate_every=8,evaluation_n=5,batch_size=4,seed=41)
    first=train(config,root/'model/model.json',root/'run-a',test_only=True,progress=lambda *a:None)
    second=train(config,root/'model/model.json',root/'run-b',test_only=True,progress=lambda *a:None)
    assert first['training_executed'] and not first['research_executed']
    assert first['source_statuses']['events']=='MOCK_TEST_ONLY'
    assert first['history'][-1]['optimizer_steps']=={'batter':3,'pitcher':3}
    assert [h['evaluation'] for h in first['history']]==[h['evaluation'] for h in second['history']]
    assert [h['probes'] for h in first['history']]==[h['probes'] for h in second['history']]
    initial=json.loads((root/'run-a/checkpoints/pa_000000.json').read_text())
    final=json.loads((root/'run-a/checkpoints/pa_000024.json').read_text())
    for role in ('batter','pitcher'):
        assert any(not np.array_equal(x,y) for x,y in zip(initial[role]['parameters'],final[role]['parameters']))
    events=[json.loads(line) for line in (root/'run-a/events.jsonl').read_text().splitlines()]
    assert len({e['training_episode'] for e in events})==24
    assert all(e['source_status']=='MOCK_TEST_ONLY' for e in events)
    assert all(set(e['observed_state_batter'])=={'balls','strikes'} for e in events)
    assert all(e['reward']==0 for e in events if not e['terminal_result'])
    before=(root/'run-a/checkpoints/pa_000024.json').read_bytes()
    replay(root/'run-a/checkpoints/pa_000024.json',root/'model/model.json',root/'replay',test_only=True)
    assert before==(root/'run-a/checkpoints/pa_000024.json').read_bytes()


def test_aggregate_match_does_not_hide_wrong_conditional_predictions():
    from collections import defaultdict
    from baseball_lab.outcome.empirical import validate,EVENTS
    # MOCK_TEST_ONLY: deliberately invert conditional outcomes while matching the aggregate.
    rows=[{'balls':0,'strikes':0,'pitch_type':kind,'observed_action':'take','event':event,
           'plate_x':None,'plate_z':None,'release_speed_kmh':None} for kind,event in [('FF','ball'),('SL','strike')]]
    class Wrong:
        def __init__(self):self.groups=defaultdict(lambda:rows)
        def probabilities(self,b,s,k,a,arrival):return {e:float(e==('strike' if k=='FF' else 'ball')) for e in EVENTS},2,'test'
        def donors(self,b,s,k,a,arrival):return [rows[1 if k=='FF' else 0]],'test'
        def arrival_donors(self,*args):return rows,'test'
    result=validate(Wrong(),rows,1)
    assert result['total_variation']==0
    assert result['weighted_conditional_tv']==1
    assert result['brier_difference_vs_baseline']>0
