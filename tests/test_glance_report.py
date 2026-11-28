"""MOCK_TEST_ONLY fixtures; summary must reuse rather than change evidence."""
from copy import deepcopy
from pathlib import Path
import json
from urllib.error import HTTPError
from urllib.request import urlopen
import pytest
from test_web import web
from test_strategy_view import mock_result
from baseball_lab.experiments.match.pitch_game.glance import build,render
from baseball_lab.experiments.match.pitch_game.strategy import new_stats
from baseball_lab.experiments.match.pitch_game.strategy_view import build as detailed
from baseball_lab.experiments.match.pitch_game.research import report


def sample(after=(.8,.7)):
    d=mock_result();d['schema']='Match-pitch-decision-game-v8';d['config']={'episodes':20};d['seeds']=[]
    preferences=[];combined=new_stats()
    for seed,p in enumerate(after):
        def policy(value):return {'offense':{'take':1-value,'swing':value},'defense':{'pitch:cutter:left_high:fast':value,'pitch:fastball:right_low:fast':1-value}}
        old,new=policy(.5),policy(p);context={'environment':'MLB:2024:MOCK_TEST_ONLY','balls':0,'strikes':0,'hand':'R','cue':None}
        probes=lambda v:[{'id':'MOCK_TEST_ONLY','context':context,'teams':[v,deepcopy(v)]}]
        stats=new_stats();stats[0]['offense']={'swing':8,'take':2};stats[1]['defense']={'pitch:cutter:left_high:fast':8,'pitch:fastball:right_low:fast':2}
        d['seeds'].append({'seed':seed,'history':[{'games':0,'strategy':new_stats(),'strategy_probes':probes(old)},{'games':20,'strategy':stats,'strategy_probes':probes(new)}], 'training_environments':{'MLB:2024:MOCK_TEST_ONLY':20}})
        preferences.append({'seed':seed,'context':context,'teams':[{role:{'before':old[role],'after':new[role]} for role in old}]*2})
        for i in (0,1):
            for role in ('offense','defense'):
                for a,n in stats[i][role].items():combined[i][role][a]=combined[i][role].get(a,0)+n
    d['strategy_analysis']={'teams':combined,'preferences':preferences};return d


def test_glance_uses_exact_detailed_aggregates_without_mutation():
    d=sample();original=deepcopy(d);v=detailed(d);g=build(d)
    assert d==original and g['games']==v['overview']['games']==40
    assert g['pitches']==v['overview']['pitches']==20
    assert g['cards'][0]['count']==16 and g['cards'][0]['total']==20
    for c,role in zip(g['cards'],('offense','defense')):
        assert c['rows']==v['overview']['overall'][role][:2]
        assert c['rows'][0]['runs']==2
        assert sum(r['before'] for r in c['rows'])==pytest.approx(1.)
        assert sum(r['after'] for r in c['rows'])==pytest.approx(1.)
    assert '전체 기준 상황의 평균' in render(d)


def test_mixed_runs_empty_course_and_partial_status_are_honest():
    d=sample((.8,.2));assert '변화는 실행마다 방향이 달랐' in render(d)
    d=mock_result();d['schema']='Match-pitch-decision-game-v7';d['status']='RUNNING'
    html=render(d)
    assert '중간 저장 기록' in html and '전후 비교 기록 없음' in html
    assert '<svg' not in html and '0.0%' not in html
    v=detailed(sample());v['overview']['preferences']['course']['after']['area:left_high']=float('nan')
    with pytest.raises(ValueError,match='수치가 올바르지'):render(v)


def test_summary_escapes_strings_and_new_runs_save_both_pages(tmp_path):
    v=detailed(sample());v['overview']['overall']['offense'][0]['action']='<script>alert("MOCK_TEST_ONLY")</script>'
    html=render(v);assert '<script>' not in html and '&lt;script&gt;' in html
    report(tmp_path,sample())
    assert 'overview.html' in (tmp_path/'report.html').read_text()
    assert 'report.html#pitch' in (tmp_path/'overview.html').read_text()


def test_summary_route_reads_saved_evidence_and_refuses_escape(web,tmp_path):
    wb,server=web;folder=wb.outputs/'MOCK_TEST_ONLY'/'result';folder.mkdir(parents=True)
    source=folder/'research.json';source.write_text(json.dumps(sample()),encoding='utf-8');original=source.read_bytes()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    with urlopen(base+'/reports/MOCK_TEST_ONLY/result/overview.html') as response:assert '한눈에 보기' in response.read().decode()
    assert source.read_bytes()==original and not (folder/'overview.html').exists()
    with pytest.raises(HTTPError) as error:urlopen(base+'/reports/%2e%2e/outside/overview.html')
    assert error.value.code==403
    source.write_text('MOCK_TEST_ONLY invalid json')
    with pytest.raises(HTTPError) as error:urlopen(base+'/reports/MOCK_TEST_ONLY/result/overview.html')
    assert error.value.code==409
    source.unlink()
    with pytest.raises(HTTPError) as error:urlopen(base+'/reports/MOCK_TEST_ONLY/result/overview.html')
    assert error.value.code==404
    outside=tmp_path/'outside.json';outside.write_text(json.dumps(sample()));source.symlink_to(outside)
    with pytest.raises(HTTPError) as error:urlopen(base+'/reports/MOCK_TEST_ONLY/result/overview.html')
    assert error.value.code==403


def test_completed_reports_share_small_projection_and_reload_changed_source(tmp_path,monkeypatch):
    from baseball_lab.experiments.match.pitch_game import report_data

    source=tmp_path/'research.json'
    d=sample()
    source.write_text(json.dumps(d),encoding='utf-8')
    report(tmp_path,d)
    original=Path.read_text

    def no_raw_read(path,*args,**kwargs):
        assert path!=source,'Completed reports should use the saved projection'
        return original(path,*args,**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path,'read_text',no_raw_read)
        view=report_data.load(source)
        assert report_data.load(source) is view
        assert view['overview']==detailed(d)['overview']
        assert not {'contexts','growth','runs'} & view.keys()
    changed=sample((.9,.9))
    source.write_text(json.dumps(changed),encoding='utf-8')
    assert report_data.load(source)['overview']==detailed(changed)['overview']
