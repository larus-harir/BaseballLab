"""MOCK_TEST_ONLY season explanation and local preparation routing."""
from unittest.mock import patch
from baseball_lab.data.learning_preview import preview
from baseball_lab.web.server import Workbench


def test_preview_names_each_league_year_instead_of_implying_same_season(tmp_path):
    fake={'mlb':{'2024':{'dates':['2024-04-01','2024-05-01','2024-06-01','2024-07-01','2024-08-01']}},'npb':{'daily_counts':{}}}
    with patch('baseball_lab.data.learning_preview.index',return_value=fake),patch('baseball_lab.matchup.shared.catalog',return_value={'baselines':{'KBO:2023':{},'KBO:2024':{}}}):
        r=preview(tmp_path,'2024-03-20','2024-09-30',{'MLB':1,'KBO':1,'NPB':1})
    assert 'KBO: 2023 시즌' in r['lines']
    assert any('자료 없음' in x for x in r['lines'] if x.startswith('NPB:'))
    assert r['calibration_cutoff_exclusive']=='2024-07-01'


def test_npb_connection_uses_fixed_preparation_script_not_legacy_kbo(tmp_path):
    wb=Workbench(tmp_path)
    with patch('baseball_lab.web.server.threading.Thread') as thread:
        job=wb.matchup_prepare(project='npb',season=2025)
    assert job['status']=='queued' and wb.job['project']=='eramatch'
    args=thread.call_args.kwargs['args'];assert any(x.endswith('prepare_player_sources.py') for x in args[1])
    assert args[1][-6:]==['--league','NPB','--start','2025','--end','2025']
    assert not list((tmp_path/'data/local/catalog').glob('*'))


def test_fresh_collected_catalog_works_without_downloads(tmp_path):
    from baseball_lab.matchup.service import overview
    mlb=overview(tmp_path,'baseball',league='MLB',data_mode='collected',season=2022)
    assert mlb['supported_seasons']==list(range(2025,1999,-1))
    assert mlb['ready'] and mlb['cached_seasons']==list(range(2025,1999,-1)) and mlb['selected_season']==2022
    npb=overview(tmp_path,'eramatch',league='NPB',data_mode='collected')
    assert npb['supported_seasons']==[2025] and npb['selected_season']==2025 and npb['ready']


def test_mlb_download_job_is_bounded_and_uses_separate_source_route(tmp_path):
    import pytest
    wb=Workbench(tmp_path)
    for invalid in (1999,2026,'2022',True):
        with pytest.raises(ValueError):wb.matchup_prepare(project='mlb_collected',season=invalid)
    with patch('baseball_lab.web.server.threading.Thread') as thread:
        wb.matchup_prepare(project='mlb_collected',season=2022)
    command=thread.call_args.kwargs['args'][1]
    assert command[-6:]==['--league','MLB','--start','2022','--end','2022']
