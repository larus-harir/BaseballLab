"""MOCK_TEST_ONLY community parsing, provider isolation and archived originals."""
import csv,io,json
from pathlib import Path
from zipfile import ZipFile
import pytest
from baseball_lab.data.community import integer,outs,extract,player_rows,safe_url
from baseball_lab.data.lineage import write_json,checksum
from baseball_lab.matchup.shared import catalog,analyze
from test_shared_execution import prepared


def test_integer_counts_and_baseball_fractions_do_not_become_decimal_innings():
    assert integer('3.0')==3 and integer('') is None
    assert outs('2/3')==2 and outs('128 2/3')==386 and outs('16.1')==49
    for value in ('-1','NaN123','3.5'):
        with pytest.raises(ValueError):integer(value)
    with pytest.raises(ValueError):outs('16.4')


def test_csv_archive_traversal_and_unregistered_hosts_fail_before_extraction(tmp_path):
    path=tmp_path/'bad.zip'
    with ZipFile(path,'w') as z:z.writestr('../MOCK_TEST_ONLY.csv','MOCK_TEST_ONLY')
    with pytest.raises(ValueError):extract(path,tmp_path)
    for url in ('https://untrusted.example/','http://www.kaggle.com/','https://user@www.kaggle.com/'):
        with pytest.raises(ValueError):safe_url(url)
    assert not (tmp_path.parent/'MOCK_TEST_ONLY.csv').exists()


def test_community_provider_does_not_double_count_or_inherit_whole_league_ban(tmp_path):
    rows,file=prepared(tmp_path)
    # Same league/season, separate licensed provider. Its counts stay separate.
    community=[]
    for row in rows[-2:]:
        r={**row,'source_namespace':'armstjc-npb-spaia','rights_status':'PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED',
            'entity_id':'MOCK_TEST_ONLY-community-'+row['role']}
        community.append(r)
    file.write_text(''.join(json.dumps(r)+'\n' for r in rows+community))
    meta=file.parent/'manifest.json';m=json.loads(meta.read_text());m['rows_sha256']=checksum(file);write_json(meta,m)
    d=catalog(tmp_path)
    assert d['baselines']['NPB:2025']['sample_n']==100
    assert d['baselines']['NPB:2025']['source_namespace']=='armstjc-npb-spaia'
    assert sum(p['league']=='NPB' for p in d['profiles'].values())==2
    r=analyze(tmp_path,{'batter':rows[0]['entity_id'],'pitcher':community[1]['entity_id'],'reference':'NPB:2025','seed':41})
    assert r['simulation']['n']==25 and not r['training_executed']
    assert not r['data_policy']['absolute_league_strength_validated']
