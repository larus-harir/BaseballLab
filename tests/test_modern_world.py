"""Real modern corpus and isolated MOCK_TEST_ONLY parser counterexamples."""
from collections import Counter
from copy import deepcopy
from random import Random
import pytest,numpy as np
from baseball_lab.experiments.match.pitch_game.modern_world import ModernWorld,data,inventory,features,historical_context
from baseball_lab.experiments.match.pitch_game.corpus_world import Observation
from baseball_lab.data.modern_corpus import hf_pitch

@pytest.fixture(scope='module')
def world():return ModernWorld()


def test_all_existing_modern_years_and_partial_fields_are_kept_in_one_corpus(world):
    d=data();assert len(d['cohorts'])==36 and inventory()['cycle_games']==51
    assert {v['season'] for v in d['cohorts'].values() if v['league']=='MLB'}==set(range(2010,2027))
    assert {v['season'] for v in d['cohorts'].values() if v['league']=='KBO'}==set(range(2016,2027))
    assert sum(sum(v['used_pitches'].values()) for v in d['cohorts'].values())==15053562
    assert len({(c['league'],c['season']) for c in d['cohorts'].values()})==36
    for year in range(2016,2023):
        c=next(c for c in d['cohorts'].values() if c['league']=='KBO' and c['season']==year)
        assert c['capabilities']['fit']['course']==0 and c['capabilities']['fit']['family']>0
        assert c['capabilities']['fit']['pitches']>100000
    for c in d['cohorts'].values():
        assert c['split']['fit'][1]<c['split']['validation'][0]<c['split']['test'][0]
        assert all(0<=v.get(k,0)<=v['pitches'] for v in c['capabilities'].values() for k in ('family','course','speed'))


def test_actual_new_kbo_releases_match_independent_canonical_h_and_hr_totals():
    d=data()
    for year in range(2023,2027):
        c=d['cohorts'][f'KBO:{year}:slothman-naver-v0'];n=Counter()
        for rows in c['counts'].values():
            for row in rows:n.update(row[-1])
        expected=d['annual_history']['KBO:'+str(year)]
        assert sum(n[e] for e in ('single','double','triple','home_run'))==expected['H']['n']
        assert n['home_run']==expected['HR']['n']
        assert d['quality'][str(year)]['games']==720
        assert c['capabilities']['fit']['course']>100000


def test_repeated_pa_result_is_not_a_pitch_result_and_units_are_explicit():
    row={'pitch_number':1,'balls':0,'strikes':0,'pitch_result':'T','events':'home_run','pitch_type':'FF',
         'release_speed_kmh':144,'plate_x':0,'plate_z':2.5,'sz_bot':1.5,'sz_top':3.5,'batter':'MOCK_TEST_ONLY'}
    p=hf_pitch(row);assert p==(0,0,'take','fastball','middle_middle',40.,'strike')
    assert hf_pitch({**row,'pitch_number':0}) is None
    assert hf_pitch({**row,'pitch_result':'H'})[-1]=='home_run'
    assert hf_pitch({**row,'plate_z':None})[4] is None
    assert hf_pitch({**row,'pitch_result':'W'})[2]=='bunt'


def test_season_totals_are_past_context_not_fictional_pitch_worlds():
    catalog=inventory();assert min(catalog['history']['KBO'])==2010 and min(catalog['history']['NPB'])==2015
    assert not any(k.startswith('KBO:2010:') for k in data()['cohorts'])
    for league,year in (('KBO',2016),('NPB',2019),('MLB',2010)):
        values,used=historical_context(league,year)
        assert all(2010<=y<year for y in used) and len(values)==10
    assert set(range(2010,2016))<=set(historical_context('KBO',2016)[1])
    assert set(range(2015,2019))<=set(historical_context('NPB',2019)[1])
    assert historical_context('MLB',2010)[1]==()


def test_all_years_are_scheduled_and_coarse_records_cannot_invent_course(world):
    visits=[world.training_context(91,i) for i in range(1,52)]
    assert set(visits)==set(world.cohorts) and Counter(v.split(':')[0] for v in visits)=={'MLB':17,'KBO':17,'NPB':17}
    for league,year in (('KBO',2016),('KBO',2024),('MLB',2010),('MLB',2015),('NPB',2019)):
        key=next(k for k,c in world.cohorts.items() if c.value['league']==league and c.value['season']==year)
        world.requested_context=key;world.begin_game(0)
        obs=Observation(1,0,0,0,0,0,0,0,0,league,year)
        legal=world.defense_legal(obs);assert 'intentional_walk' in legal
        if league=='KBO' and year==2016:
            assert all(not a.startswith('pitch:') or ':any:' in a for a in legal)
            assert world.prepare(obs,'pitch',Random(3)).location_cue==''
        if league=='MLB' and year==2010:assert set(legal)=={'pitch','intentional_walk'}
        if league=='KBO' and year==2024:assert 'bunt' in world.legal(obs)
        agents=world.new_team(4)
        for agent in agents:assert len(features(obs,agent.role))==len(agent.feature_names)
    with pytest.raises(ValueError):ModernWorld(['NPB'],[2010])


def test_missing_feature_masks_are_distinct_from_known_center_or_slow():
    w=ModernWorld(['KBO'],[2016]);agent=w.new_team(3)[0]
    missing=Observation(1,0,0,0,0,0,0,0,0,'KBO',2016)
    known=Observation(1,0,0,0,0,0,0,0,0,'KBO',2016,'fastball','middle_middle','slow','R')
    a,b=features(missing,'batter'),features(known,'batter')
    for name in ('has_family_cue','has_course_cue','has_speed_cue'):
        i=agent.feature_names.index(name);assert a[i]==0 and b[i]==1


def test_pa_start_runner_fields_are_not_mislabeled_as_current_pitch_state():
    from baseball_lab.experiments.match.pitch_game.corpus_world import corpus
    old=corpus()['cohorts'];new=data()['cohorts']
    for year in (2023,2024,2025):
        prior=next(c for c in old.values() if c['league']=='KBO' and c['season']==year)
        current=new[f'KBO:{year}:slothman-naver-v0']
        assert current['movements']==prior['movements']
        assert current['split']==prior['split']
        assert 'native per-pitch' in current['movement_source']
    current=new['KBO:2026:slothman-naver-v0']
    assert 'not full-league' in current['movement_source']
    assert 1000<sum(current['used_movements'].values())<20000


def test_partial_or_unpinned_supplement_cache_is_not_treated_as_complete(tmp_path):
    import json
    from baseball_lab.data.modern_sources import collect,REVISION,PITCH_FILES
    directory=tmp_path/'data/local/modern-releases/MOCK_TEST_ONLY';directory.mkdir(parents=True)
    path=directory/'manifest.json'
    for files in ([],[{'year':y,'sha256':'MOCK_TEST_ONLY'} for y in PITCH_FILES]):
        path.write_text(json.dumps({'status':'ACQUIRED','revision':REVISION,'files':files}))
        with pytest.raises(ValueError,match='고정 배포'):collect(tmp_path)


def test_sparse_native_movement_uses_only_exact_earlier_same_league_observations():
    from baseball_lab.experiments.match.pitch_game.corpus_world import legal_movement
    w=ModernWorld(['KBO'],[2026]);w.begin_game(0)
    with pytest.raises(ValueError):w.current.movement(1,7,'triple')
    result=w.advance(1,7,'triple',Random(71));record=w.evidence['supplemental_movement_backoffs'][0]
    expected=Counter()
    for name,c in data()['cohorts'].items():
        if c['league']!='KBO' or c['season']>=2026:continue
        for outs,bases,event,bunt,values in c['movements']['fit']:
            if (outs,bases,event,bunt)!=(1,7,'triple',False):continue
            for delta,end,runs,n in values:
                if legal_movement(1,7,'triple',delta,end,runs):expected[delta,end,runs]+=n
    assert expected and Counter({tuple(v[:3]):v[3] for v in record['outcomes']})==expected
    assert (result[0]-1,*result[1:]) in expected and all(s['environment'].startswith('KBO:') and int(s['environment'].split(':')[1])<2026 for s in record['sources'])
    assert sum(s['observations'] for s in record['sources'])==sum(expected.values())
    assert all(s['fit_end']<w.current.value['split']['fit'][0] for s in record['sources'])
    w.advance(1,7,'triple',Random(72));assert len(w.evidence['supplemental_movement_backoffs'])==1


def test_every_native_base_out_and_hit_state_has_audited_movement_support(world):
    from baseball_lab.experiments.match.pitch_game.corpus_world import legal_movement
    for key,c in world.cohorts.items():
        world.requested_context=key;world.begin_game(0)
        for outs in range(3):
            for bases in range(8):
                assert world.advance(outs,bases,'strikeout',Random(5))==(outs+1,bases if outs<2 else 0,0)
                assert world.advance(outs,bases,'home_run',Random(5))==(outs,0,1+bases.bit_count())
                for event in ('out','single','double','triple'):
                    end_outs,end_bases,runs=world.advance(outs,bases,event,Random(5))
                    assert legal_movement(outs,bases,event,end_outs-outs,end_bases,runs)


def test_absent_past_movement_is_not_replaced_by_invented_or_future_outcomes(monkeypatch):
    w=ModernWorld(['MLB'],[2010]);w.begin_game(0)
    def absent(*args,**kwargs):raise ValueError('MOCK_TEST_ONLY unsupported transition')
    monkeypatch.setattr(w.current,'movement',absent)
    with pytest.raises(ValueError,match='과거 관측도 없습니다'):w.advance(0,0,'triple',Random(4))
