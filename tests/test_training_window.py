"""MOCK_TEST_ONLY collected-period guards and chronological learning boundary."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from baseball_lab.data.lineage import write_json,checksum
from baseball_lab.data.training_window import periods,validate_window,acquire
from baseball_lab.r1.environment import fit
from test_r1 import mock_dataset
from test_web import web,call


def manifests(root):
    for year in (2024,2025):
        p=root/f'data/local/collections/MOCK_TEST_ONLY-{year}';p.mkdir(parents=True)
        (p/'plays.csv').write_text('MOCK_TEST_ONLY')
        write_json(p/'manifest.json',{'league':'MLB','granularity':'play','season':year,
            'status':'ACQUIRED_SCHEMA_CHECKED','source_status':'REAL_OBSERVED','rights_status':'RETROSHEET_CREDIT_REQUIRED',
            'source_url':'MOCK_TEST_ONLY','date_range':[f'{year}0501',f'{year}0505'],
            'files':[{'path':str((p/'plays.csv').relative_to(root)),'sha256':checksum(p/'plays.csv')}]})


def test_window_validation_and_source_integrity_happen_before_normalization(tmp_path):
    manifests(tmp_path)
    assert validate_window(tmp_path,'2024-05-01','2025-05-05')==('2024-05-01','2025-05-05')
    for first,last in [('2023-05-01','2025-05-05'),('2024-04-30','2025-05-05'),('2024-05-01','2025-05-06'),('2025-05-05','2024-05-01')]:
        with pytest.raises(ValueError):validate_window(tmp_path,first,last)
    p=tmp_path/'data/local/collections/MOCK_TEST_ONLY-2024/plays.csv';p.write_text('MOCK_TEST_ONLY tampered')
    with patch('baseball_lab.r1.data.normalize') as normalize:
        with pytest.raises(ValueError,match='SHA-256'):acquire(tmp_path,'2024-05-01','2025-05-05')
        normalize.assert_not_called()


def test_multiple_seasons_fit_uses_only_earlier_observations_for_legal_actions():
    data=mock_dataset();rows=data['records'];second=deepcopy(rows)
    for r in second:
        r['date']=r['date'].replace('2024','2025');r['game_id']+='2025';r['record_id']+='2025'
    data['records']+=second
    data['manifest'].update(schema='collected-training-window-v1',selected_seasons=[2024,2025],
        date_semantics='whole game aligned to last actual recorded play date')
    envs,model=fit(data,'2024-05-01','2025-05-05')
    assert model['split']['fit']['dates'][1]<model['split']['validation']['dates'][0]<model['split']['test']['dates'][0]
    assert model['legal_actions_selected_without_test']
    assert model['source_window']['selected_seasons']==[2024,2025]
    # Test-only changed choices cannot change which actions training is allowed.
    cutoff=model['split']['test']['dates'][0]
    for r in data['records']:
        if r['date']>=cutoff:r['runs']=0
    assert fit(data,'2024-05-01','2025-05-05')[1]['support']==model['support']


def test_web_checks_collected_window_before_scheduling(web):
    wb,server=web;manifests(wb.root)
    opts={'source':'retrosheet','study':'half_inning','collected_window':True,'start':'2024-04-30','end':'2025-05-05','episodes':20,'seed':41}
    status,_=call(server,'/api/start','POST',json.dumps({'kind':'run','options':opts}),{'X-Lab-Token':wb.token})
    assert status==400 and not list(wb.outputs.glob('*/task.json'))
    state=json.loads(call(server,'/api/state')[1])
    assert set(state['readiness']['scoring']['collected_periods'])=={'2024','2025'}
