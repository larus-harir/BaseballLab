"""MOCK_TEST_ONLY regressions for 2002's documented IW + wild pitch event."""
import csv
from pathlib import Path
import pytest
from baseball_lab.r1.data import normalize,pure_intentional_walk


def source(path,event):
    fields=['gid','event','inning','vis_home','score_v','score_h','pitches','pa','bunt','iw','outs_pre','outs_post','runs','pn','gametype','pbp',*[f'br{i}_{s}' for i in (1,2,3) for s in ('pre','post')]]
    rows=[]
    def add(code,inning,before,after,bases,end,runs=0,score=0,iw=0):
        r=dict.fromkeys(fields,'');r.update(gid='TST200206030',event=code,inning=str(inning),vis_home='0',score_v=str(score),score_h='0',pitches='I' if iw else 'C',pa='1',bunt='0',iw=str(iw),outs_pre=str(before),outs_post=str(after),runs=str(runs),pn=str(len(rows)+1),gametype='regular',pbp='full')
        for i in (1,2,3):r[f'br{i}_pre']='MOCK_TEST_ONLY' if bases&(1<<(i-1)) else '';r[f'br{i}_post']='MOCK_TEST_ONLY' if end&(1<<(i-1)) else ''
        rows.append(r)
    add('IW',1,0,0,0,1,iw=1)
    for o in range(3):add('K',1,o,o+1,1,0 if o==2 else 1)
    add(event,2,1,1,6,5,runs=1,iw=1)
    add('K',2,1,2,5,5,score=1);add('K',2,2,3,5,0,score=1)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def test_documented_wild_pitch_is_retained_but_not_a_pure_force_walk(tmp_path):
    path=tmp_path/'MOCK_TEST_ONLY.csv';source(path,'IW.3-H(NR);2-3(WP)');before=path.read_bytes()
    r=normalize(path,tmp_path,{'provider':'MOCK_TEST_ONLY'},official=True,persist=False,regulation_rule_check=True)
    assert r['manifest']['isolated_intentional_walks']==r['manifest']['isolated_intentional_walk_rule_matches']==1
    composite=next(v for v in r['records'] if v['runs'])
    assert composite['event_codes']==['IW.3-H(NR);2-3(WP)'] and composite['end_bases']==5
    assert not pure_intentional_walk(composite)
    assert path.read_bytes()==before and not (tmp_path/'dataset.json').exists()


def test_unexplained_numerical_mismatch_still_stops_validation(tmp_path):
    path=tmp_path/'MOCK_TEST_ONLY.csv';source(path,'IW.3-H;2-3')
    with pytest.raises(ValueError,match='intentional walks'):
        normalize(path,tmp_path,{'provider':'MOCK_TEST_ONLY'},official=True,persist=False,regulation_rule_check=True)
