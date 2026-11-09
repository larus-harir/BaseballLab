"""MOCK_TEST_ONLY records test contracts; never a production fallback."""
import csv
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from baseball_lab.data.lineage import checksum
from baseball_lab.matchup.models import EVENTS,distribution,generalized_log5,log5,normalized,legacy,simulate
from baseball_lab.matchup.catalog import event_counts,innings_outs,build_legacy,read_catalog,import_assignment,LEGACY_FILES
from baseball_lab.matchup.service import analyze,overview
from baseball_lab.matchup.mlb import observed_rows,validate
from baseball_lab.matchup.web import render
from test_web import web,call


def event_data(n=10):
    return dict(zip(EVENTS,[n,n,1,n,2,1,2,3*n]))


def profile(role,season=2024,n=10):
    counts=event_data(n);league=distribution(event_data(20))
    return {'events':counts,'season':season,'league_rates':league,'role':role}


def test_binary_special_case_neutrality_and_commutativity():
    b,p,l=.32,.21,.25
    q,_,_=generalized_log5({'yes':b,'no':1-b},{'yes':p,'no':1-p},{'yes':l,'no':1-l})
    assert q['yes']==pytest.approx(log5(b,p,l))
    league=distribution(event_data(20));b=distribution(event_data(3));p=distribution(event_data(13))
    assert generalized_log5(b,league,league)[0]==pytest.approx(b)
    assert generalized_log5(b,p,league)[0]==pytest.approx(generalized_log5(p,b,league)[0])
    with pytest.raises(ValueError):generalized_log5(b,p,{'other':1})
    with pytest.raises(ValueError):generalized_log5({'yes':1.,'no':0.},{'yes':0.,'no':1.},{'yes':.5,'no':.5})


def test_full_partition_missing_and_actual_ab_not_pa_minus_walk():
    c={'PA':100,'AB':80,'SO':10,'BB':10,'HP':2,'H':30,'HR':5,'2B':4,'3B':1,'SF':5,'SH':3}
    values,issue=event_counts(c,'batter')
    assert issue is None and sum(values.values())==100 and values['single']==20 and values['other']==48
    assert c['AB']!=c['PA']-c['BB']
    assert event_counts({**c,'2B':None},'batter')[0] is None
    assert event_counts({**c,'H':90},'batter')[0] is None
    assert event_counts({**c,'PA':10},'batter')[0] is None
    assert innings_outs('123.2')==371
    for bad in ('1.3','1.20','-1','3.5'):
        with pytest.raises(ValueError):innings_outs(bad)


def test_tiny_sample_probability_mass_cross_season_and_repeatability():
    b,p=profile('batter',1982,1),profile('pitcher',2024,1)
    b['events']={e:int(e=='home_run') for e in EVENTS}
    p['events']={e:int(e=='other') for e in EVENTS}
    league=distribution(event_data())
    model=normalized(b,p,league,strength=100,neutral=league)
    assert sum(model['probabilities'].values())==pytest.approx(1)
    assert all(0<=x<=1 for x in model['probabilities'].values())
    assert simulate(model,25,41,5)==simulate(model,25,41,5)
    assert sum(simulate(model,25,41,5)['counts'].values())==25
    with pytest.raises(ValueError):normalized(b,p,league,strength=0)
    with pytest.raises(ValueError):normalized(b,p,league,strength=float('nan'))
    for args in [(True,41,5),(0,41,5),(10,-1,5),(10,41,201)]:
        with pytest.raises(ValueError):simulate(model,*args)


def legacy_profiles():
    b={'season':1982,'legacy_row':{'PA':400,'AB':350,'H':120,'SO':40,'BB':40,'HR':20,'2B':20,'3B':2,'SF':3}}
    p={'season':2024,'legacy_row':{'TBF':600,'SO':140,'BB':45,'HR':12}}
    l={'K_rate':.18,'BB_rate':.09,'HR_rate':.025,'BABIP':.30}
    return b,p,{'1982':l,'2024':l},l


def test_legacy_explicit_original_assumptions_and_edge_branch():
    b,p,yearly,l=legacy_profiles();model=legacy(b,p,yearly,l)
    assert model['steps']['pitcher_adjusted']['BABIP']==l['BABIP']
    assert model['probabilities']['hbp']==0
    assert model['steps']['batter_adjusted']['BABIP']!=b['legacy_row']['H']/b['legacy_row']['AB']
    # Original's zero non-HR hits still takes the residual triple branch.
    b['legacy_row'].update(H=20,HR=20,**{'2B':0,'3B':0})
    model=legacy(b,p,yearly,l)
    assert model['probabilities']['triple']>0 and model['probabilities']['single']==0
    # Original independently combined binary rates can exceed total mass 1.
    for row in (b['legacy_row'],p['legacy_row']):
        row.update(SO=90000,BB=90000,HR=50000)
    b['legacy_row'].update(PA=100000,AB=100000,H=50000)
    p['legacy_row']['TBF']=100000
    model=legacy(b,p,yearly,l)
    assert model['steps']['displayed_k_bb_hr_sum']>1
    assert sum(model['probabilities'].values())==pytest.approx(1)
    assert model['probabilities']['home_run']<model['steps']['claimed_binary']['HR_rate']
    assert simulate(model,50,9,2)['counts']['triple']==0


@pytest.fixture
def mock_catalog(tmp_path):
    directory=tmp_path/'data/local/catalog/kbo-assignment';directory.mkdir(parents=True)
    fields=['Id','Name','Year','Team','PA','TBF','AB','H','SO','BB','HR','2B','3B','HP','SF','SH','IP']
    def row(pid,name,year,team,role):
        return dict(zip(fields,[pid,name,year,team,400 if role=='batter' else '',600 if role=='pitcher' else '',350 if role=='batter' else '',100,50,40,10,15,2,3,4,2,'150.2' if role=='pitcher' else '']))
    bat=[row('b1','MOCK_TEST_ONLY 동명이인',1982,'A','batter'),row('b1','MOCK_TEST_ONLY 동명이인',1982,'B','batter'),row('b2','MOCK_TEST_ONLY 동명이인',1982,'A','batter'),row('b3','MOCK_TEST_ONLY 중복',1982,'A','batter'),row('b3','MOCK_TEST_ONLY 중복',1982,'A','batter')]
    pit=[row('p1','MOCK_TEST_ONLY 투수',2024,'A','pitcher')]
    # Give both seasons a complete batting league prior.
    bat.append(row('b4','MOCK_TEST_ONLY 리그',2024,'A','batter'))
    for filename,rows in zip(LEGACY_FILES[1:],[bat,pit]):
        with (directory/Path(filename).name).open('w',encoding='cp949',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    source={'id':'kbo-assignment','status':'LEGACY_UNVERIFIED','label':'MOCK_TEST_ONLY','license':'MOCK_TEST_ONLY','files':[]}
    return tmp_path,build_legacy(directory,source)


def test_identity_team_splits_first_eligible_and_duplicates(mock_catalog):
    root,c=mock_catalog;b=c['profiles']['KBO:batter:b1:1982'];duplicate=c['profiles']['KBO:batter:b3:1982']
    assert b['counts']['PA']==800 and b['legacy_row']['PA']==400
    assert b['legacy_source_row']==2 and b['team_rows']==2
    assert not duplicate['normalized_eligible'] and not duplicate['legacy_eligible']
    found=overview(root,'eramatch',role='batter',query='동명이인',season=1982)
    assert found['matched']==2 and len({p['player_id'] for p in found['profiles']})==2
    result=analyze(root,'eramatch',{'batter':b['id'],'pitcher':'KBO:pitcher:p1:2024','repetitions':2})
    assert result['training_executed'] is False and result['comparison']['model']=='normalized'
    with pytest.raises(ValueError):analyze(root,'eramatch',{'batter':[],'pitcher':'p1'})
    with pytest.raises(ValueError):analyze(root,'eramatch',{'batter':b['id'],'pitcher':b['id']})
    with pytest.raises(ValueError):overview(root,'https://untrusted.example')
    path=root/'data/local/catalog/kbo-assignment/catalog.json';path.write_text(path.read_text().replace('MOCK_TEST_ONLY','changed'))
    with pytest.raises(ValueError,match='무결성'):read_catalog(root,'kbo-assignment')


def test_catalog_symlink_and_unknown_zip_rejected(tmp_path):
    with pytest.raises(ValueError,match='ZIP 버전'):import_assignment(tmp_path,b'not original')
    external=tmp_path/'outside';external.mkdir()
    parent=tmp_path/'data/local/catalog';parent.mkdir(parents=True)
    (parent/'mlb-2024').symlink_to(external,target_is_directory=True)
    with pytest.raises(ValueError,match='링크'):read_catalog(tmp_path,'mlb-2024')


def test_changed_source_file_invalidates_cached_catalog(mock_catalog):
    from baseball_lab.matchup.catalog import save_catalog
    root,c=mock_catalog;directory=root/'data/local/catalog/kbo-assignment'
    raw=directory/Path(LEGACY_FILES[1]).name
    c['source']['files']=[{'name':raw.name,'sha256':checksum(raw)}]
    save_catalog(directory,c)
    assert read_catalog(root,'kbo-assignment')['dataset_id']==c['dataset_id']
    raw.write_bytes(raw.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='원본'):read_catalog(root,'kbo-assignment')


def test_legacy_stays_available_when_improved_events_missing(mock_catalog):
    from baseball_lab.matchup.catalog import save_catalog
    root,c=mock_catalog;p=c['profiles']['KBO:pitcher:p1:2024']
    p['normalized_eligible']=False;p['events']=None
    save_catalog(root/'data/local/catalog/kbo-assignment',c)
    result=analyze(root,'eramatch',{'batter':'KBO:batter:b1:1982','pitcher':p['id'],'repetitions':1})
    assert result['model']['model']=='legacy' and result['comparison'] is None
    assert '부족' in result['comparison_error']


def test_chronological_validation_no_player_or_game_leakage():
    rows=[]
    for part,date in [('fit','20240401'),('validation','20240720'),('test','20240901')]:
        for i,e in enumerate(EVENTS):
            rows.append({'id':part+str(i),'game':part,'date':date,'batter':'new' if part=='test' else 'b','pitcher':'p','event':e})
    result=validate(rows)
    assert result['split']['fit']['n']==8 and result['split']['test']['n']==8
    assert result['comparison']['log5']['test']['cold_start_n']==8
    assert result['selected_strength'] in (25,100,300,1000)
    bad=[{**r,'game':'same'} for r in rows]
    with pytest.raises(ValueError,match='독립'):validate(bad)
    suspended=rows+[{'id':'s1','game':'BOS202406260','date':'20240626','batter':'b','pitcher':'p','event':'walk'},
                    {'id':'s2','game':'BOS202406260','date':'20240826','batter':'b','pitcher':'p','event':'walk'}]
    checked=validate(suspended)
    assert checked['split']['fit']['n']==8 and checked['split']['test']['n']==10
    assert checked['split']['test']['dates'][0]=='20240826'
    assert checked['suspended_game_handling']['cross_date_games']==1


def test_official_rows_partition_and_duplicate_id(tmp_path):
    path=tmp_path/'MOCK_TEST_ONLY.csv';fields=['gametype','pbp','pa','gid','pn','date','k','walk','hbp','single','double','triple','hr','batter','pitcher','batteam','pitteam','ab','sf','sh']
    row=dict.fromkeys(fields,'0');row.update(gametype='regular',pbp='full',pa='1',gid='ANA202404010',date='20240402',pn='1',batter='b',pitcher='p',batteam='A',pitteam='B',ab='1',double='1')
    def write(rows):
        with path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    write([row]);assert observed_rows(path)[0]['event']=='double'
    assert observed_rows(path)[0]['date']=='20240402'
    write([row,row])
    with pytest.raises(ValueError,match='중복'):observed_rows(path)
    write([{**row,'k':'1'}])
    with pytest.raises(ValueError,match='사건'):observed_rows(path)


def test_matchup_http_project_routes_security_and_missing_data(web):
    wb,server=web
    for path in ('/baseball','/eramatch'):
        status,body=call(server,path);assert status==200 and '선택에 따라 바뀌는 설명' in body.decode()
    assert json.loads(call(server,'/api/matchup/catalog?project=baseball')[1])['ready'] is False
    assert call(server,'/api/matchup/catalog?project=../../etc')[0]==400
    assert call(server,'/api/matchup/import','POST',b'zip')[0]==403
    assert call(server,'/api/matchup/import','POST',b'zip',{'X-Lab-Token':wb.token})[0]==400
    assert call(server,'/api/matchup/analyze','POST','[]',{'X-Lab-Token':wb.token})[0]==400
    assert call(server,'/api/matchup/analyze','POST','{}',{'X-Lab-Token':wb.token})[0]==400
    assert call(server,'/api/matchup/prepare','POST','{}',{'X-Lab-Token':wb.token,'Origin':'https://untrusted.example'})[0]==403
    assert not list(wb.outputs.glob('*/task.json'))


def test_report_json_cannot_close_script():
    html=render('eramatch',analysis={'name':'</script><img src=x onerror=alert(1)>'})
    assert '</script><img' not in html
    assert '\\u003c/script\\u003e' in html
