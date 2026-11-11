"""MOCK_TEST_ONLY snapshot integrity and repeated collection behavior."""
import json
from pathlib import Path
from baseball_lab.data.lineage import write_json,checksum
from baseball_lab.data.warehouse import build
import pytest


def snapshot(root,name,counts,season=2024):
    p=root/'data/local/collections'/name;p.mkdir(parents=True)
    r={'league':'NPB','season':season,'role':'batter','granularity':'team_season','source_namespace':'MOCK_TEST_ONLY',
       'source_team_id':'MOCK_TEAM','source_sha256':'MOCK_TEST_ONLY','counts':counts}
    rows=p/'rows.jsonl';rows.write_text(json.dumps(r)+'\n')
    write_json(p/'manifest.json',{'league':'NPB','season':season,'rows_file':'rows.jsonl','rows_sha256':checksum(rows),'source_status':'REAL_OBSERVED'})
    return p


def test_duplicate_snapshots_do_not_double_count_and_changed_counts_fail(tmp_path):
    snapshot(tmp_path,'a',{'PA':100,'AB':90,'H':20});snapshot(tmp_path,'b',{'PA':100,'AB':90,'H':20})
    m,path=build(tmp_path,include_builtin=False)
    assert m['rows']==1 and m['coverage']['NPB']['roles']==['team_batting']
    assert build(tmp_path,include_builtin=False)[1]==path
    snapshot(tmp_path,'c',{'PA':100,'AB':90,'H':25})
    with pytest.raises(ValueError,match='충돌'):build(tmp_path,include_builtin=False)


def test_tampered_rows_are_not_used_and_unselected_years_not_loaded(tmp_path):
    p=snapshot(tmp_path,'a',{'PA':100});(p/'rows.jsonl').write_text('MOCK_TEST_ONLY changed')
    with pytest.raises(ValueError,match='지문'):build(tmp_path,include_builtin=False)
    m,_=build(tmp_path,leagues=['MLB'],include_builtin=False)
    assert m['rows']==0


def test_invalid_windows_fail_before_loading_and_storage_links_are_rejected(tmp_path):
    p=snapshot(tmp_path,'a',{'PA':100});(p/'rows.jsonl').write_text('MOCK_TEST_ONLY changed')
    with pytest.raises(ValueError,match='양의 정수'):build(tmp_path,last_seasons=-1,include_builtin=False)
    outside=tmp_path/'outside';outside.mkdir()
    (tmp_path/'data/local/standardized').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='링크'):build(tmp_path,leagues=['MLB'],include_builtin=False)
    assert not list(outside.iterdir())


def test_explicit_parser_revision_preserves_and_verifies_previous_snapshot(tmp_path):
    old=snapshot(tmp_path,'a',{'PA':100,'H':20})
    new=snapshot(tmp_path,'b',{'PA':100,'H':25})
    path=new/'manifest.json';m=json.loads(path.read_text())
    m['supersedes']={'manifest':str((old/'manifest.json').relative_to(tmp_path)),'sha256':checksum(old/'manifest.json')}
    write_json(path,m)
    result,folder=build(tmp_path,include_builtin=False)
    assert result['rows']==1
    assert json.loads((folder/'rows.jsonl').read_text())['counts']['H']==25
    assert json.loads((old/'rows.jsonl').read_text())['counts']['H']==20
    (old/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='지문'):build(tmp_path,include_builtin=False)
