"""MOCK_TEST_ONLY common-event transport, provenance and HTTP integration."""
import json
from unittest.mock import patch
import pytest
from baseball_lab.data.standard import normalize_season_row
from baseball_lab.data.lineage import checksum,write_json
from baseball_lab.matchup.shared import catalog,analyze,partition
from baseball_lab.web.server import Workbench
from test_web import web,call


def prepared(root):
    rows=[]
    for league,year in [('MLB',2024),('KBO',1990),('NPB',2025)]:
        for role in ('batter','pitcher'):
            c={'PA' if role=='batter' else 'TBF':100,'SO':20,'BB':10,'H':25}
            row=normalize_season_row(league=league,season=year,role=role,source_player_id='MOCK_TEST_ONLY',
                source_namespace='MOCK_TEST_ONLY',counts=c,source_sha256='MOCK_TEST_ONLY')
            row.update(granularity='player_season',provenance_status='MOCK_TEST_ONLY',source_fields={'選手':'MOCK_TEST_ONLY </script><img>'})
            rows.append(row)
    folder=root/'data/local/standardized/MOCK_TEST_ONLY';folder.mkdir(parents=True)
    file=folder/'rows.jsonl';file.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    write_json(folder/'manifest.json',{'created_at':'MOCK_TEST_ONLY','dataset_id':'MOCK_TEST_ONLY','selection':{},'rows_sha256':checksum(file)})
    return rows,file


def test_missing_hit_splits_and_hbp_are_not_invented(tmp_path):
    rows,_=prepared(tmp_path);d=catalog(tmp_path)
    assert len(d['profiles'])==6
    b=rows[2];p=rows[1]
    result=analyze(tmp_path,{'batter':b['entity_id'],'pitcher':p['entity_id'],'reference':'MLB:2024','seed':41})
    assert result['model']['probabilities']==pytest.approx({'strikeout':.2,'walk':.1,'hit':.25,'other':.45})
    assert result['batter']['counts']['HBP'] is None and result['pitcher']['counts']['2B'] is None
    assert result['data_policy']['absolute_league_strength_validated'] is False
    assert sum(result['simulation']['counts'].values())==25
    assert analyze(tmp_path,{'batter':b['entity_id'],'pitcher':p['entity_id'],'reference':'MLB:2024','seed':41})['run_id']==result['run_id']
    assert partition({'role':'pitcher','counts':{'TBF':0,'H':0,'SO':0,'BB':0}}) is None


def test_saved_common_result_uses_existing_storage_and_escapes_html(tmp_path):
    rows,_=prepared(tmp_path);wb=Workbench(tmp_path)
    result=wb.matchup_analyze('eramatch',{'data_mode':'common','batter':rows[0]['entity_id'],'pitcher':rows[3]['entity_id'],'reference':'KBO:1990','seed':41})
    assert result['analysis']['training_executed'] is False
    html=next(wb.outputs.glob('*/result/report.html')).read_text()
    assert '</script><img>' not in html
    assert '공통 비교' in html
    assert wb.state('eramatch')['runs'][0]['kind']=='matchup'


def test_catalog_tamper_and_invalid_references_fail(tmp_path):
    rows,file=prepared(tmp_path);catalog(tmp_path);file.write_text('{}\n')
    with pytest.raises(ValueError,match='검증값'):catalog(tmp_path)


def test_common_http_endpoint_and_existing_csrf(web):
    from test_web import call
    wb,server=web;rows,_=prepared(wb.root)
    status,data=call(server,'/api/shared/catalog?league=NPB&season=2025&role=pitcher')
    data=json.loads(data)
    assert status==200 and data['matched']==1
    assert data['player_sources']['pitcher']==['KBO:1990','MLB:2024']
    options={'data_mode':'common','batter':rows[0]['entity_id'],'pitcher':rows[3]['entity_id'],'reference':'MLB:2024','seed':41}
    status,data=call(server,'/api/matchup/analyze','POST',json.dumps({'project':'eramatch','options':options}))
    assert status==403
    status,data=call(server,'/api/matchup/analyze','POST',json.dumps({'project':'eramatch','options':options}),{'X-Lab-Token':wb.token})
    data=json.loads(data)
    assert status==200 and data['analysis']['model']['model']=='common'


def test_npb_secondary_use_restriction_cannot_be_bypassed_in_api(tmp_path):
    rows,_=prepared(tmp_path)
    for pitcher,reference in [(rows[5]['entity_id'],'MLB:2024'),(rows[1]['entity_id'],'NPB:2025')]:
        with pytest.raises(ValueError,match='2차 이용'):
            analyze(tmp_path,{'batter':rows[0]['entity_id'],'pitcher':pitcher,'reference':reference})


def test_builtin_ambiguous_team_totals_are_not_promoted_to_common_profiles(tmp_path):
    data=catalog(tmp_path)
    blocked={('1700',1992),('1700',1994),('1700',1998),('1700',1999)}
    assert not any(p['role']=='pitcher' and (p['player_id'],p['season']) in blocked for p in data['profiles'].values())
