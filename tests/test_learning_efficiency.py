"""Immutable validation reuse, exact action masks and honest result projections."""
from copy import deepcopy
from pathlib import Path
import json,os,subprocess,sys
import numpy as np
import pytest
from baseball_lab.experiments.match.pitch_game.modern_world import ModernWorld,data,ASSET_SHA256
from baseball_lab.experiments.match.pitch_game.corpus_world import Cohort
from baseball_lab.experiments.match.pitch_game.directional_contact import ContactModel
from baseball_lab.experiments.match.pitch_game.validated_world import load
from baseball_lab.experiments.match.pitch_game.strategy_view import choice_groups,recent_stats
from baseball_lab.experiments.match.pitch_game.strategy import new_stats


def test_packaged_validation_matches_full_recomputation_for_every_native_world():
    raw=data();cached=load(ASSET_SHA256);assert set(cached)==set(raw['cohorts'])
    for key,value in raw['cohorts'].items():
        fresh=Cohort(value);contact=ContactModel(raw['contacts'][key]);v=cached[key]
        for name in ('strength','metrics','movement_metrics','running_metrics'):assert getattr(fresh,name)==v['pitch'][name]
        assert contact.strength==v['contact']['strength'] and contact.metrics==v['contact']['metrics']


def test_normal_start_reuses_validated_metrics_and_old_code_invalidates_them(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Repeated validation scan during ordinary start')
    with monkeypatch.context() as m:
        for method in ('check','check_running','check_movements'):m.setattr(Cohort,method,forbidden)
        m.setattr(ContactModel,'check',forbidden)
        world=ModernWorld();assert world.evidence['validation_reused'] and len(world.cohorts)==36
    import baseball_lab.experiments.match.pitch_game.validated_world as module
    load.cache_clear()
    with monkeypatch.context() as m:
        m.setattr(module,'algorithm_hash',lambda:'MOCK_TEST_ONLY_changed_implementation')
        assert load(ASSET_SHA256) is None
    load.cache_clear()


def test_action_order_is_stable_across_interpreter_hash_seeds():
    root=Path(__file__).resolve().parents[1]
    code="from baseball_lab.experiments.match.pitch_game.modern_world import ModernWorld;import json;w=ModernWorld(['KBO'],[2024]);print(json.dumps(w.defense_actions))"
    values=[subprocess.check_output([sys.executable,'-c',code],env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONPATH':str(root/'src'),'OPENBLAS_NUM_THREADS':'1'},text=True) for seed in ('1','71')]
    assert values[0]==values[1]


def test_swing_variants_are_one_judgement_without_losing_direction_counts():
    raw={'take':6,'swing':1,'swing:pull':2,'swing:opposite':3,'bunt':2}
    assert choice_groups(raw,'offense')=={'take':6,'swing':6,'bunt':2}
    assert choice_groups(raw,'direction')=={'swing:pull':2,'swing:opposite':3}
    assert sum(choice_groups(raw,'offense').values())==sum(raw.values())


def test_recent_choices_are_not_lifetime_exploration_and_saved_counters_stay_intact():
    # MOCK_TEST_ONLY cumulative counters; none enter packaged source data.
    before=new_stats();after=new_stats()
    before[0]['offense']={'take':100,'swing:pull':10}
    after[0]['offense']={'take':110,'swing:pull':60,'swing':20}
    r={'seeds':[{'history':[{'games':0,'strategy':new_stats()},{'games':8,'strategy':before},{'games':12,'strategy':after}]}]}
    original=deepcopy(r);recent=recent_stats(r)
    assert recent['games']==4 and recent['offense']=={'take':10,'swing':70}
    assert recent['targets']=={} and r==original


def test_compact_atomic_json_preserves_payload_and_rejects_nan(tmp_path):
    from baseball_lab.data.lineage import write_json
    value={'MOCK_TEST_ONLY':'한글','values':[1,2.5,False,None]}
    a,b=tmp_path/'plain.json',tmp_path/'compact.json'
    write_json(a,value);write_json(b,value,compact=True)
    assert json.loads(a.read_text())==json.loads(b.read_text())==value
    assert b.stat().st_size<a.stat().st_size
    with pytest.raises(ValueError):write_json(tmp_path/'invalid.json',{'v':float('nan')},compact=True)


def test_balanced_replica_average_does_not_hide_individual_policy_changes():
    from test_strategy_view import mock_result
    from baseball_lab.experiments.match.pitch_game.strategy_view import build
    d=mock_result();d['schema']='Match-pitch-decision-game-v7'
    context={'environment':'MLB:2024:MOCK_TEST_ONLY','hand':'R','cue':None}
    pairs=[]
    for after in ({'take':.9,'swing':.1},{'take':.1,'swing':.9}):
        policy={'offense':{'before':{'take':.5,'swing':.5},'after':after},'defense':{'before':{'pitch':1.},'after':{'pitch':1.}}}
        pairs.append({'context':context,'teams':[policy,deepcopy(policy)]})
    d['strategy_analysis']['preferences']=pairs;view=build(d)
    assert view['learning']['max_change']==pytest.approx(0.)
    assert view['learning']['individual_max']==pytest.approx(.4)
