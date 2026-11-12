"""Saved statistical reports use the existing local protection boundary."""
import json
import pytest
from test_web import web,call
from test_matchup import mock_catalog


def test_statistical_run_persists_lineage_and_storage_dependency(web,mock_catalog):
    wb,s=web;root,_=mock_catalog
    assert root==wb.root
    payload={'project':'eramatch','options':{'batter':'KBO:batter:b1:1982','pitcher':'KBO:pitcher:p1:2024','n':25,'seed':41,'repetitions':2}}
    headers={'X-Lab-Token':wb.token}
    status,body=call(s,'/api/matchup/analyze','POST',json.dumps(payload),headers)
    assert status==200
    result=json.loads(body);assert result['analysis']['training_executed'] is False
    assert result['analysis']['execution']['engine_id']
    assert sum(result['analysis']['simulation']['counts'].values())==25
    report=result['report'];assert call(s,report)[0]==200
    assert call(s,report.replace('report.html','analysis.json'))[0]==403
    state=json.loads(call(s,'/api/state')[1]);assert state['runs'][0]['kind']=='matchup'
    original=(wb.outputs/state['runs'][0]['id']/'result/analysis.json').read_bytes()
    assert call(s,report)[0]==200
    assert (wb.outputs/state['runs'][0]['id']/'result/analysis.json').read_bytes()==original
    item=next(i for i in wb.storage.inventory()['items'] if i['id']=='catalog:kbo-assignment')
    assert item['dependent_runs']==1 and item['category']=='private'
    assert wb.storage.verify('catalog:kbo-assignment')['verified']
    with wb.lock:
        wb.job={'status':'running'}
    assert call(s,'/api/matchup/analyze','POST',json.dumps(payload),headers)[0]==400


def test_same_season_guard_and_invalid_profiles(mock_catalog):
    from baseball_lab.matchup import service
    from unittest.mock import patch
    root,catalog=mock_catalog
    with patch('baseball_lab.data.catalog.DatasetCatalog.get',return_value=catalog):
        with pytest.raises(ValueError,match='시즌'):service.analyze(root,'baseball',{'batter':'KBO:batter:b1:1982','pitcher':'KBO:pitcher:p1:2024','model':'normalized'})


def test_project_history_filters_before_limiting(web):
    wb,_=web
    from baseball_lab.data.lineage import write_json
    write_json(wb.outputs/'000_old_match/task.json',{'id':'000_old_match','kind':'run','status':'completed'})
    for i in range(31):
        identifier=f'2026_statistical_{i:02d}'
        write_json(wb.outputs/identifier/'task.json',{'id':identifier,'kind':'matchup','project':'baseball','status':'completed'})
    assert len(wb.state('baseball')['runs'])==30
    assert wb.state('match')['runs'][0]['id']=='000_old_match'
    assert not wb.state('eramatch')['runs']
