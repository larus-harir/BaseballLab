"""MOCK_TEST_ONLY: observation endpoint is read-only and bounded to known sources."""
from unittest.mock import patch
import json
from test_web import web,call
from baseball_lab.data.retrosheet_releases import validate_period


def test_observation_get_preserves_units_and_does_not_schedule_a_job(web):
    wb,server=web
    data={'source_status':'REAL_OBSERVED','capabilities':{'measured_exit_velocity':False},'counts':{'completed_pa':10,'batted_ball_pa':6},'path':'/tmp/MOCK_TEST_ONLY/private.csv'}
    with patch('baseball_lab.data.contact_observations.summarize',return_value=data) as lookup:
        code,body=call(server,'/api/observations?season=2024&role=batter&player=MOCK_TEST_ONLY')
    assert code==200 and json.loads(body)['counts']==data['counts']
    assert 'path' not in json.loads(body)
    lookup.assert_called_once_with(wb.root,2024,role='batter',player_id='MOCK_TEST_ONLY')
    assert wb.job is None and not list(wb.outputs.glob('*/task.json'))
    assert call(server,'/api/observations?season=../../etc&player=x')[0]==400
    assert call(server,'/api/observations?season=2025&player=x')[0]==400
    assert call(server,'/api/observations?season=2024&role=../path&player=x')[0]==400


def test_single_day_record_view_does_not_require_training_partitions():
    assert validate_period('2024-03-20','2024-03-20',min_days=1)==('2024-03-20','2024-03-20')
