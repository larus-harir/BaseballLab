"""MOCK_TEST_ONLY codes verify units and missingness, not baseball performance."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from baseball_lab.data.contact_observations import _aggregate, summarize, _index, decode_pitch_sequence


def play(number, **changes):
    return {'gid':'MOCK_TEST_ONLY2024', 'pn':str(number), 'pa':'1', 'bip':'1',
            'batter':'MOCK_TEST_ONLY_B', 'pitcher':'MOCK_TEST_ONLY_P',
            'hittype':'G', 'loc':'6M', 'firstf':'6', 'pitches':'B>FX',
            'event':'63/G6M', **changes}


def test_completed_pa_units_and_missing_sensor_values():
    rows=[play(1),play(2,batter='MOCK_TEST_ONLY_C',hittype='BP',loc='',firstf='0',pitches=''),
          play(3,pa='0'),play(4,bip='0',hittype='',loc='',firstf='0',pitches='BCCS')]
    before=deepcopy(rows);data=_aggregate(rows);total=data['season']
    assert rows==before and total['pa']==3 and total['contact']==2
    assert total['types']=={'G':1,'BP':1}
    assert total['locations']=={'6M':1}
    assert total['fielders']=={'6':1}
    assert total['location_unknown']==total['fielder_unknown']==1
    assert total['pitch_sequences_present']==2
    assert total['sequence_examples'][0]['pitch_result_codes']=='B>FX'
    assert data['batter']['MOCK_TEST_ONLY_B']['pa']==2
    assert data['pitcher']['MOCK_TEST_ONLY_P']['pa']==3


def test_unknown_codes_remain_unknown_and_duplicate_pa_is_rejected():
    d=_aggregate([play(1,hittype='MOCK_TEST_ONLY_UNKNOWN',loc='?',firstf='')])['season']
    assert d['types']=={} and d['type_unknown']==d['location_unknown']==d['fielder_unknown']==1
    with pytest.raises(ValueError,match='중복'):_aggregate([play(1),play(1)])
    with pytest.raises(ValueError,match='식별자'):_aggregate([play(1,batter='')])


def test_public_view_is_read_only_and_never_turns_codes_into_coordinates(tmp_path):
    _index.cache_clear()
    descriptor={'ready':True,'metadata':{'status':'REAL_OBSERVED',
        'sha256':[{'name':'MOCK_TEST_ONLY.csv','sha256':'MOCK_TEST_ONLY'}],
        'license':'MOCK_TEST_ONLY source'}}
    # Explicit test transport only. Production entry still requires the catalog's
    # registered source pin and original-file verification.
    with patch('baseball_lab.data.contact_observations.DatasetCatalog') as Catalog:
        Catalog.return_value.describe.return_value=descriptor
        Catalog.return_value.iter_plays.return_value=iter([play(1)])
        a=summarize(tmp_path,2024,role='batter',player_id='MOCK_TEST_ONLY_B')
        a['contact_examples'][0]['recorded_location_code']='changed'
        b=summarize(tmp_path,2024,role='batter',player_id='MOCK_TEST_ONLY_B')
        assert b['contact_examples'][0]['recorded_location_code']=='6M'
        assert all(b['capabilities'][k] is False for k in ('measured_exit_velocity','launch_angle',
            'measured_pitch_velocity','pitch_type','plate_coordinates','ball_trajectory'))
        assert b['counts']=={'completed_pa':1,'batted_ball_pa':1,'pitch_sequence_present_pa':1,
                             'home_run_pa':0,'home_run_pa_in_bip':0,'home_run_pa_outside_bip':0}
        assert b['location_note'] and b['pitch_note']
        with pytest.raises(ValueError,match='관측 기록'):
            summarize(tmp_path,2024,role='batter',player_id='MOCK_TEST_ONLY_missing')
    _index.cache_clear()


def test_documented_pitch_results_do_not_count_annotations_or_automatic_calls_as_pitches():
    tokens=decode_pitch_sequence('B>C1*SFAVN?X')
    assert ''.join(t['code'] for t in tokens)=='B>C1*SFAVN?X'
    assert [t['label'] for t in tokens if t['kind']=='pitch_result']==[
        '볼','루킹 스트라이크','헛스윙 스트라이크','파울','타구 인플레이']
    assert next(t for t in tokens if t['code']=='V')['kind']=='automatic_call'
    assert next(t for t in tokens if t['code']=='1')['kind']=='pickoff_throw'
    assert next(t for t in tokens if t['code']=='?')['kind']=='unknown'


def test_home_runs_outside_source_bip_are_not_presented_as_contact_sample():
    data=_aggregate([play(1,hr='1',bip='0'),play(2,hr='1',bip='1'),play(3,hr='0')])['season']
    assert data['pa']==3 and data['home_runs']==2
    assert data['contact']==2 and data['home_runs_in_bip']==1


@pytest.mark.parametrize('role,identifier',[(None,'x'),('batter',None),('unknown','x'),('pitcher','')])
def test_arbitrary_filters_are_rejected(tmp_path,role,identifier):
    with pytest.raises(ValueError):summarize(tmp_path,2024,role=role,player_id=identifier)


def test_simultaneous_first_read_joins_one_index_build():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from baseball_lab.data.contact_observations import _shared_index
    entered=Event();release=Event();calls=[]
    # MOCK_TEST_ONLY cached stand-in makes concurrent misses deterministic.
    from functools import lru_cache
    @lru_cache(maxsize=1)
    def slow(root,year,signature):
        calls.append(signature);entered.set();assert release.wait(3);return {'MOCK_TEST_ONLY':True}
    with patch('baseball_lab.data.contact_observations._index',slow),ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(_shared_index,'MOCK_TEST_ONLY',2024,'same-source')
        assert entered.wait(1)
        b=pool.submit(_shared_index,'MOCK_TEST_ONLY',2024,'same-source')
        release.set();assert a.result(timeout=2)==b.result(timeout=2)
    assert calls==['same-source']
