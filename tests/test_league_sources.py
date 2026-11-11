"""MOCK_TEST_ONLY source-format regressions; fixtures are not baseball evidence."""
import pytest
from baseball_lab.data.league_sources import npb_counts,parse_npb_players,fetch


@pytest.mark.parametrize('whole,fraction,outs',[
    ('134','.2',404),('134 .2','',404),('134 2/3','',404),('134.1','',403),('0','',0),
])
def test_npb_innings_notation_is_counted_as_outs(whole,fraction,outs):
    assert npb_counts({'投球回':whole,'':fraction})['IP_OUTS']==outs


@pytest.mark.parametrize('whole,fraction',[('134 .3',''),('134 2/3','.2'),('unknown','')])
def test_unknown_or_duplicate_innings_fraction_is_rejected(whole,fraction):
    with pytest.raises(ValueError):npb_counts({'投球回':whole,'':fraction})


def test_roster_player_ids_are_scoped_and_missing_fields_stay_missing():
    page='<table><tr><th>選手</th><th>登板</th><th>打者</th><th>投球回</th><th>三振</th></tr><tr><td>MOCK_TEST_ONLY</td><td>1</td><td>3</td><td>0 .2</td><td>1</td></tr></table>'
    r=parse_npb_players(page,2025,'pitcher','g','MOCK_TEST_ONLY')[0]
    assert r['counts']=={'G':1,'TBF':3,'IP_OUTS':2,'SO':1}
    assert 'AB' not in r['counts'] and r['row_kind']=='team_split'
    assert r['source_fields']['identity_status']=='ROW_SCOPED_NAME_ONLY_NOT_VERIFIED_PERSON_ID'
    assert r['source_player_id']!=parse_npb_players(page,2024,'pitcher','g','MOCK_TEST_ONLY')[0]['source_player_id']
    assert r['source_player_id']!=parse_npb_players(page,2025,'pitcher','t','MOCK_TEST_ONLY')[0]['source_player_id']


def test_collector_rejects_unapproved_source_before_network_access(tmp_path):
    for url in ['http://npb.jp/bis/2025/','https://example.com/','https://npb.jp:8443/','https://user@npb.jp/','https://www.koreabaseball.com/']:
        with pytest.raises(ValueError):fetch(url,tmp_path/'unused')
    assert not (tmp_path/'unused').exists()
