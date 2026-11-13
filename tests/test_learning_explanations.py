"""MOCK_TEST_ONLY fixtures; explanations must match the actual split algorithm."""
from unittest.mock import patch
from baseball_lab.data.learning_preview import preview
from baseball_lab.data.compact import periods
from test_web import web,call
import json


def test_full_period_explains_2014_kbo_and_all_three_time_ranges(tmp_path):
    p=periods();r=preview(tmp_path,p['2000']['start'],p['2025']['end'],{'MLB':1,'KBO':1})
    assert r['season_count']==26 and r['calibration_cutoff_exclusive']=='2015-05-22'
    assert r['splits'][1]['start']=='2015-05-22'
    assert r['splits'][0]['end']<r['splits'][1]['start']<=r['splits'][1]['end']<r['splits'][2]['start']
    kbo=next(v for v in r['leagues'] if v['league']=='KBO')
    assert kbo['period']=='2014 시즌 한 시즌만 사용' and 'KBO에도 적용되지는 않습니다' in kbo['use']
    assert r['weights']=={'MLB':.5,'KBO':.5} and r['can_start']


def test_explanation_does_not_scan_source_files_or_make_up_future_npb(tmp_path):
    p=periods()
    with patch('baseball_lab.data.catalog.DatasetCatalog.iter_plays',side_effect=AssertionError('MOCK_TEST_ONLY no source scan')):
        r=preview(tmp_path,p['2000']['start'],p['2025']['end'],{'MLB':1,'NPB':1})
    assert not r['can_start'] and '2025' in r['issues'][0]
    assert not next(v for v in r['leagues'] if v['league']=='NPB')['period'].startswith('2025')
    r=preview(tmp_path,p['2025']['start'],p['2025']['end'],{'MLB':2,'NPB':1})
    assert r['can_start'] and r['weights']['MLB']==2/3


def test_unavailable_npb_is_rejected_before_long_input_processing(web):
    wb,server=web;p=periods()
    with patch('subprocess.Popen',side_effect=AssertionError('MOCK_TEST_ONLY must not launch')):
        code,body=call(server,'/api/start','POST',json.dumps({'kind':'run','options':{'source':'retrosheet','study':'half_inning','collected_window':True,'start':p['2000']['start'],'end':p['2025']['end'],'league_mixture':{'MLB':1,'NPB':1},'episodes':20,'seed':41}}),{'X-Lab-Token':wb.token})
    assert code==400 and 'NPB' in json.loads(body)['error']
    assert wb.job is None
