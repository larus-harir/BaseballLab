"""MOCK_TEST_ONLY existing interfaces consume collected records without uploads."""
import csv,json
from pathlib import Path
from unittest.mock import patch
import pytest
from baseball_lab.data.lineage import checksum,write_json
from baseball_lab.matchup.service import overview,analyze
from baseball_lab.data.auxiliary import summarize
from baseball_lab.web.storage import Storage
from test_shared_execution import prepared
from test_web import web,call


def community(root):
    rows,file=prepared(root)
    for r in rows[-2:]:
        r.update(source_namespace='armstjc-npb-spaia',rights_status='PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED')
    file.write_text(''.join(json.dumps(r)+'\n' for r in rows));m=json.loads((file.parent/'manifest.json').read_text());m['rows_sha256']=checksum(file);write_json(file.parent/'manifest.json',m)
    return rows


def test_primary_catalog_and_existing_analyze_route_use_collected_ids(web):
    wb,server=web;community(wb.root)
    for league,project,year in [('MLB','baseball',2024),('KBO','eramatch',1990),('NPB','eramatch',2025)]:
        code,raw=call(server,f'/api/matchup/catalog?project={project}&league={league}&season={year}')
        data=json.loads(raw);assert code==200 and data['ready'] and data['data_mode']=='collected'
        b=next(p for p in data['profiles'] if p['role']=='batter');p=next(p for p in data['profiles'] if p['role']=='pitcher')
        body={'project':project,'options':{'batter':b['id'],'pitcher':p['id'],'n':25,'seed':41,'league':league}}
        code,raw=call(server,'/api/matchup/analyze','POST',json.dumps(body),{'X-Lab-Token':wb.token})
        result=json.loads(raw);assert code==200,result
        r=result['analysis'];assert r['data_mode']=='collected' and r['batter']['league']==league
        assert sum(r['simulation']['counts'].values())==25 and not r['training_executed']
        assert call(server,result['report'])[0]==200


def test_collected_lookup_preserves_legacy_fallback_when_no_collection(tmp_path):
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY no network')):
        data=overview(tmp_path,'eramatch',data_mode='collected',season=2024,league='KBO')
        assert data['ready'] and data['data_mode']=='collected' and 1982 in data['seasons']
        data=overview(tmp_path,'eramatch',data_mode='collected',league='NPB')
        assert data['ready'] and data['league']=='NPB' and data['seasons']==[2025] and data['cached_seasons']==[2025]


def test_team_running_versions_are_not_double_counted_or_repaired(tmp_path):
    p=tmp_path/'data/local/community/kaggle-MOCK_TEST_ONLY';p.mkdir(parents=True)
    files=[]
    for name,n in [('KBO_Runner_data.csv',1),('KBO_Running_data.csv',2)]:
        path=p/name;path.write_text('team,games,steals,caught_stealing,steal_attempts,year\n'+''.join(f'MOCK_TEST_ONLY_{i},143,65,65,200,2024\n' for i in range(n)))
        files.append({'path':str(path.relative_to(tmp_path)),'sha256':checksum(path)})
    write_json(p/'manifest.json',{'source_namespace':'kaggle-lazyjun01/kbo-runners-data2001-2024','version':1,'source_url':'MOCK_TEST_ONLY','publisher_license':'MOCK_TEST_ONLY','files':files})
    r=summarize(tmp_path,'KBO',2024)
    assert len(r['tables'])==1 and len(r['tables'][0]['rows'])==2
    assert r['tables'][0]['rows'][0]['steals']=='65' and 'quality_note' in r['tables'][0]['rows'][0]
    storage=Storage(tmp_path);items=storage.inventory()['items'];item=next(i for i in items if i['id']=='collected:community')
    assert not item['deletable'] and item['categories']['official']==0
    with pytest.raises(ValueError):storage.preview('collected:community')
    assert storage.verify('collected:community')['verified']
    (p/'KBO_Running_data.csv').write_text('MOCK_TEST_ONLY tampered')
    with pytest.raises(ValueError):storage.verify('collected:community')


def test_rule_check_matches_completed_inning_donors_without_changing_original(tmp_path):
    from baseball_lab.r1.data import normalize
    path=tmp_path/'MOCK_TEST_ONLY.csv'
    fields=['gid','event','inning','vis_home','score_v','score_h','pitches','pa','bunt','iw','outs_pre','outs_post','runs','pn','gametype','pbp',*[f'br{i}_{s}' for i in (1,2,3) for s in ('pre','post')]]
    rows=[]
    def add(event,inning,bottom,before,after,pre,post,iw=0):
        r=dict.fromkeys(fields,'');r.update(gid='TST200005010',event=event,inning=str(inning),vis_home=str(bottom),score_v='0',score_h='0',pitches='I' if iw else 'C',pa='1',bunt='0',iw=str(iw),outs_pre=str(before),outs_post=str(after),runs='0',pn=str(len(rows)+1),gametype='regular',pbp='full')
        for i in (1,2,3):
            r[f'br{i}_pre']='MOCK_TEST_ONLY' if pre&(1<<(i-1)) else ''
            r[f'br{i}_post']='MOCK_TEST_ONLY' if post&(1<<(i-1)) else ''
        rows.append(r)
    add('IW',1,0,0,0,0,1,1)
    for outs in range(3):add('K',1,0,outs,outs+1,1,0 if outs==2 else 1)
    add('D',9,1,0,0,0,2)
    add('K',9,1,0,1,2,2);add('K',9,1,1,2,2,2)
    add('IW.2-3(WP)',9,1,2,2,2,5,1);add('K',9,1,2,3,5,0)
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    before=path.read_bytes()
    with pytest.raises(ValueError,match='intentional walks'):normalize(path,tmp_path,{'provider':'MOCK_TEST_ONLY'},official=True,persist=False)
    data=normalize(path,tmp_path,{'provider':'MOCK_TEST_ONLY'},official=True,persist=False,regulation_rule_check=True)
    m=data['manifest']
    assert m['intentional_walks']==2 and m['intentional_walk_rule_matches']==1
    assert m['isolated_intentional_walks']==m['isolated_intentional_walk_rule_matches']==1
    assert 'pure IW events' in m['intentional_walk_validation_population']
    assert any(r['event_codes']==['IW.2-3(WP)'] for r in data['records'])
    assert before==path.read_bytes() and not (tmp_path/'dataset.json').exists()


def test_npb_cross_file_numeric_ids_match_without_name_guessing(tmp_path):
    p=tmp_path/'data/local/community/npb-armstjc/MOCK_TEST_ONLY';p.mkdir(parents=True)
    raw=p/'pbp.csv';raw.write_text('game_type_id,pitcher,batter,release_speed_kmh,game_id,play_id\n1,123.0,456.0,149.0,MOCK_TEST_ONLY,1\n')
    write_json(p/'manifest.json',{'source_url':'MOCK_TEST_ONLY','files':[{'kind':'pbp','seasons':['2025'],'path':str(raw.relative_to(tmp_path)),'sha256':checksum(raw)}]})
    d=summarize(tmp_path,'NPB',2025,'pitcher','123')
    assert len(d['pitch_samples'])==1 and d['pitch_samples'][0]['release_speed_kmh']=='149.0'
    assert not summarize(tmp_path,'NPB',2025,'pitcher','999')['pitch_samples']


def test_cross_season_residual_display_does_not_read_wrong_pitcher_cohort(tmp_path):
    from test_product_completion import result
    from baseball_lab.matchup.outcome_details import attach
    r=result();r['pitcher']['season']=2000
    original=list(r['simulation']['events'])
    with patch('baseball_lab.matchup.outcome_details.index',side_effect=AssertionError('MOCK_TEST_ONLY wrong cohort lookup')):
        attach(tmp_path,r)
    assert r['event_display']['events']==original
    assert not r['event_display']['other']['detail_available']
    assert '서로 다른 시즌' in r['event_display']['other']['reason']
