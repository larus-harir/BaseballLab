"""Actual packaged releases; MOCK_TEST_ONLY records are isolated parser tests."""
from collections import Counter
from copy import deepcopy
from random import Random
import json
import numpy as np
import pytest
from baseball_lab.data.tracking_corpus import normalized,npb_position,cell,NPB_FAMILY,COLS
from baseball_lab.experiments.match.pitch_game.tracking_world import TrackingWorld,data,inventory,ASSET_SHA256,LOCATIONS
from baseball_lab.experiments.match.pitch_game.corpus_world import Observation,Cohort
from baseball_lab.experiments.match.pitch_game.strategy_view import build


@pytest.fixture(scope='module')
def world():return TrackingWorld()


def test_native_display_geometry_and_statcast_units_are_not_interchanged():
    assert npb_position(100,116/(2*(93/200)))=='middle_middle'
    assert npb_position(0,0)=='left_high' and npb_position(None,0) is None
    assert cell(float('nan'),.5) is None
    assert NPB_FAMILY[31]=='fastball' and NPB_FAMILY[41]=='changeup' and 50 not in NPB_FAMILY
    row={'game_type':'R','game_date':'2026-04-01','game_pk':'MOCK_TEST_ONLY','balls':'0','strikes':'0',
         'outs_when_up':'0','description':'swinging_strike','pitch_type':'FF','pitcher':'MOCK_TEST_ONLY',
         'plate_x':'0','plate_z':'2.5','sz_bot':'1.5','sz_top':'3.5','release_speed':'90',
         'inning':'1','inning_topbot':'Top','at_bat_number':'1','pitch_number':'1'}
    n=dict(zip(COLS,normalized(row,'MLB','MOCK_TEST_ONLY')))
    assert n['location']=='middle_middle' and n['speed']==pytest.approx(90*.44704)
    assert n['event']=='strike' and n['terminal'] is None and n['bottom']==0
    n=dict(zip(COLS,normalized({**row,'location_x_norm':'.1','location_z_norm':'.8','speed_kmh':'144'},'KBO','MOCK_TEST_ONLY')))
    assert n['location']=='left_high' and n['speed']==40
    assert normalized({**row,'game_type':'S'},'MLB','MOCK_TEST_ONLY') is None


def test_real_new_releases_are_complete_tracking_only_and_do_not_duplicate_providers(world):
    d=data();assert len(d['cohorts'])==17 and inventory()['cycle_games']==24
    assert d['quality']['KBO']=={'raw_rows':43620,'unsupported_or_nonregular':16,'course_rows':43596,'not_course_eligible':8}
    assert d['quality']['MLB'].get('duplicate_normalized_rows',0)==0
    assert d['quality']['MLB']['course_rows']==5262024
    assert d['quality']['NPB']['course_rows']==1778853
    assert len({(v['league'],v['season']) for v in d['cohorts'].values()})==17
    for c in d['cohorts'].values():
        assert c['split']['fit'][1]<c['split']['validation'][0]<c['split']['test'][0]
        for rows in c['counts'].values():
            assert all(row[3] and row[4] in LOCATIONS and row[5] in ('slow','middle','fast') for row in rows)
    assert sum(sum(c['used_pitches'].values()) for c in d['cohorts'].values())==7084473
    assert 'pitch' not in world.defense_actions
    assert world.evidence['asset_sha256']==ASSET_SHA256
    assert all('manifest_sha256' in s or 'renderer_sha256' in s for s in d['sources'])


def test_all_selected_years_cycle_and_leagues_receive_equal_opportunity(world):
    visits=[world.training_context(41,i) for i in range(1,25)]
    assert set(visits)==set(world.cohorts)
    assert Counter(v.split(':')[0] for v in visits)=={'MLB':8,'KBO':8,'NPB':8}
    for league in ('MLB','NPB'):
        assert len({v for v in visits if v.startswith(league)})==8
    filtered=TrackingWorld(['KBO','NPB'],[2026])
    assert len({filtered.training_context(42,i) for i in (1,2)})==2
    with pytest.raises(ValueError):TrackingWorld(['KBO'],[2019])


def test_legal_pitch_patterns_have_native_fit_evidence_and_future_does_not_select_them(world):
    for key,c in world.cohorts.items():
        world.requested_context=key;world.begin_game(0)
        for slot in range(3):
            obs=Observation(1,0,0,0,0,0,0,0,slot,world.league,world.season)
            actions=world.defense_legal(obs)
            assert len(actions)>1 and 'pitch' not in actions
            for action in actions:
                if not action.startswith('pitch:'):continue
                assert c.patterns[action][1] in LOCATIONS
                assert world._eligible[key][c.patterns[action]]>=20
                delivered=world.prepare(obs,action,Random(1))
                assert delivered.location_cue in LOCATIONS and delivered.pitch_family_cue
    c=next(iter(world.cohorts.values()));altered=deepcopy(c.value)
    for row in altered['counts']['test']:row[-1]={k:v*7 for k,v in row[-1].items()}
    assert Cohort(altered).strength==c.strength


def test_shared_updates_pool_both_roles_and_save_one_policy_pair(tmp_path,monkeypatch):
    from baseball_lab.agents.neural import NeuralPolicy
    from baseball_lab.experiments.match.pitch_game.research import train
    from baseball_lab.experiments.match.team_win.training import Config
    w=TrackingWorld(seasons=[2026]);calls=[];original=NeuralPolicy.update
    def observed(self,episodes,*args,**kw):
        calls.append((self.role,[reward for _,reward in episodes]))
        return original(self,episodes,*args,**kw)
    monkeypatch.setattr(NeuralPolicy,'update',observed)
    result=train({'manifest':{'source_status':'REAL_OBSERVED','dataset_id':ASSET_SHA256}},None,None,tmp_path/'new-run',Config(20,(41,),10,20,batch_size=10),world=w)
    assert len(calls)==4 and all(len(rewards)==20 and sum(rewards)==0 for _,rewards in calls)
    seed=result['seeds'][0];assert seed['shared_policy_consistent'] and seed['pooled_role_episodes']==40
    assert all(all(t) for t in seed['parameters_changed']) and seed['optimizer_steps']==[[2,2],[2,2]]
    for h in seed['history']:
        assert 'A_wins' not in h and all(p['teams'][0]==p['teams'][1] for p in h['strategy_probes'])
    checkpoint=json.loads((tmp_path/'new-run/checkpoints/41-20.json').read_text())
    assert 'teams' not in checkpoint and len(checkpoint['shared_policy'])==2
    before=deepcopy(result);view=build(result);assert before==result
    assert view['schema']=='strategy-report-view-v3' and len(view['teams'])==1
    assert all(len(p['teams'])==1 for p in view['contexts'])
    t=view['teams'][0];assert all(t['checks'].values())
    assert t['management']['games']==40
    assert t['actual_pitches']==sum(sum(n for k,n in team['defense'].items() if k.startswith('pitch:')) for team in result['strategy_analysis']['teams'])
    assert all(m[0]['total']==m[0]['known'] for m in view['heatmaps'].values())
    html=(tmp_path/'new-run/report.html').read_text()
    assert 'A팀' not in html and 'B팀' not in html and '코스 미확인' not in html
    assert '통합 AI 전략 관찰' in html


def test_new_supplement_hosts_do_not_broaden_existing_provider_access():
    from baseball_lab.data.pitch_sources import HOSTS,safe
    assert 'drive.google.com' not in HOSTS
    with pytest.raises(ValueError):safe('https://drive.google.com/uc?id=MOCK_TEST_ONLY')
    safe('https://drive.google.com/uc?id=MOCK_TEST_ONLY',{'drive.google.com'})
    for url in ('http://drive.google.com/file','https://evil.invalid/file','https://drive.google.com:444/file','https://x@drive.google.com/file'):
        with pytest.raises(ValueError):safe(url,{'drive.google.com'})


def test_conflicting_pitch_keys_quarantine_all_versions_without_count_inflation():
    import sqlite3
    from collections import defaultdict
    from baseball_lab.data.tracking_corpus import insert_unique
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE p ('+','.join(c+(' PRIMARY KEY' if c=='uid' else '') for c in COLS)+')')
    db.execute('CREATE TABLE conflicts (uid TEXT PRIMARY KEY)')
    row=['MOCK_TEST_ONLY', 'MLB:2026:MOCK_TEST_ONLY', *[None]*(len(COLS)-2)]
    quality=defaultdict(Counter);quarantined=set()
    insert_unique(db,[row,row],quality,quarantined)
    assert db.execute('SELECT COUNT(*) FROM p').fetchone()[0]==1
    assert quality['MLB']['duplicate_normalized_rows']==1
    conflict=list(row);conflict[COLS.index('event')]='foul'
    insert_unique(db,[conflict,row,conflict],quality,quarantined)
    assert db.execute('SELECT COUNT(*) FROM p').fetchone()[0]==0
    assert quality['MLB']['conflicting_pitch_ids']==1
    assert db.execute('SELECT uid FROM conflicts').fetchone()[0]=='MOCK_TEST_ONLY'
    db.close()


def test_tracking_world_is_available_without_network_or_private_catalog(tmp_path,monkeypatch):
    import urllib.request
    def forbidden(*args,**kwargs):raise AssertionError('Tracking world must read package counts, not download')
    monkeypatch.setattr(urllib.request.OpenerDirector,'open',forbidden)
    monkeypatch.chdir(tmp_path)
    w=TrackingWorld(['KBO'],[2026])
    assert len(w.cohorts)==1 and not list(tmp_path.iterdir())
    from baseball_lab.data.tracking_sources import definitions
    folder=tmp_path/'data/local/tracking-definitions';folder.mkdir(parents=True)
    (folder/'npb-renderer.js').write_text('MOCK_TEST_ONLY tampered definition')
    with pytest.raises(ValueError,match='NPB'):definitions(tmp_path)
