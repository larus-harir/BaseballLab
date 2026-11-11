"""MOCK_TEST_ONLY: held operations exercise actual lock/request boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import json

import pytest
from baseball_lab.web.server import Workbench
from test_web import web,call


def test_slow_matchup_does_not_block_status_navigation_or_cancellation(web):
    wb,server=web;entered=Event();release=Event()
    def slow(*args,**kwargs):
        entered.set();assert release.wait(5),'MOCK_TEST_ONLY release timeout'
        raise ValueError('MOCK_TEST_ONLY no result generated')
    def request():
        return call(server,'/api/matchup/analyze','POST',json.dumps({'project':'eramatch','options':{}}),{'X-Lab-Token':wb.token})
    with patch('baseball_lab.matchup.service.analyze',side_effect=slow),ThreadPoolExecutor(max_workers=4) as pool:
        first=pool.submit(request)
        try:
            assert entered.wait(2)
            assert pool.submit(call,server,'/api/state').result(timeout=1)[0]==200
            assert pool.submit(call,server,'/match').result(timeout=1)[0]==200
            # No job is not an error of responsiveness; it must be reported now.
            code,_=pool.submit(call,server,'/api/cancel','POST','{}',{'X-Lab-Token':wb.token}).result(timeout=1)
            assert code in (200,400)
        finally:release.set()
        assert first.result(timeout=2)[0]==400
    assert not list(wb.outputs.glob('*/result/analysis.json'))


def test_active_matchup_rejects_conflicting_write_without_waiting(tmp_path):
    wb=Workbench(tmp_path);entered=Event();release=Event()
    def slow(*args,**kwargs):
        entered.set();assert release.wait(5)
        raise ValueError('MOCK_TEST_ONLY computation failed')
    with patch('baseball_lab.matchup.service.analyze',side_effect=slow),ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(wb.matchup_analyze,'eramatch',{})
        try:
            assert entered.wait(2)
            second=pool.submit(wb.matchup_analyze,'eramatch',{})
            with pytest.raises(ValueError):second.result(timeout=1)
        finally:release.set()
        with pytest.raises(ValueError):first.result(timeout=2)
    # Failure releases reservation, so the next operation reaches its own error.
    with patch('baseball_lab.matchup.service.analyze',side_effect=ValueError('MOCK_TEST_ONLY next request')):
        with pytest.raises(ValueError,match='next request'):wb.matchup_analyze('eramatch',{})


def test_slow_catalog_verification_does_not_hold_workbench_state_lock(tmp_path):
    wb=Workbench(tmp_path);entered=Event();release=Event()
    def slow(*args,**kwargs):
        entered.set();assert release.wait(5)
        raise ValueError('MOCK_TEST_ONLY catalog failure')
    with patch.object(wb.catalog,'get',side_effect=slow),ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(wb.matchup_prepare,project='baseball',season=2024)
        try:
            assert entered.wait(2)
            assert isinstance(pool.submit(wb.state).result(timeout=1),dict)
        finally:release.set()
        # Preparation may verify synchronously or report a failed asynchronous job.
        try:first.result(timeout=2)
        except ValueError:pass
    assert not list(wb.outputs.glob('*/result/analysis.json'))


@pytest.mark.parametrize('start,end',[
    ('2025-03-20','2025-09-30'),
    ('2024-03-19','2024-09-30'),
    ('2024-03-20','2024-10-01'),
    ('2023-03-29','2023-10-01'),
    ('2023-03-30','2023-10-02'),
    ('2023-10-01','2024-03-20'),
    ('2024-05-06','2024-05-01'),
    ('2024-05-01','2024-05-02'),
    ('','2024-09-30'),
])
def test_invalid_training_period_rejected_before_task_or_download(web,start,end):
    wb,server=web
    payload={'kind':'run','options':{'source':'retrosheet','study':'half_inning','start':start,'end':end,'episodes':20,'seed':1}}
    with patch.object(wb.catalog,'ensure',side_effect=AssertionError('MOCK_TEST_ONLY must reject before acquisition')):
        status,body=call(server,'/api/start','POST',json.dumps(payload),{'X-Lab-Token':wb.token})
    assert status==400
    assert json.loads(body)['error']
    assert not list(wb.outputs.glob('*/task.json'))
