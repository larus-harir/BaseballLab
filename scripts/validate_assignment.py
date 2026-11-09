"""Compare the inspected, pinned assignment with the shared reproduction model.

The original CLI/imports are never run. Only its reviewed class definition is
compiled to call simulate(), with captured output and a controlled RNG. Raw
source/data remain private. This command never fetches an unknown archive.
"""
import argparse
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from random import Random
import re
from types import SimpleNamespace
from zipfile import ZipFile
import hashlib

from baseball_lab.matchup.catalog import LEGACY_SHA,LEGACY_FILES,read_catalog
from baseball_lab.matchup.models import legacy,simulate,LEGACY_CONSTANTS
from baseball_lab.data.lineage import write_json


def validate_assignment(root,archive):
    archive=Path(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=LEGACY_SHA:raise ValueError('검토한 원본 ZIP이 아닙니다.')
    with ZipFile(archive) as z:source=z.read(LEGACY_FILES[0]).decode('utf-8')
    tree=ast.parse(source)
    definition=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='KBOSimulator')
    # No top-level main(), imports or original file loading is executed.
    namespace={'pd':SimpleNamespace(notna=lambda v:v is not None),'STABILIZATION_CONSTANTS':LEGACY_CONSTANTS}
    exec(compile(ast.Module(body=[definition],type_ignores=[]),'<reviewed-assignment-class>','exec'),namespace)
    original=namespace['KBOSimulator'].__new__(namespace['KBOSimulator'])
    catalog=read_catalog(root,'kbo-assignment')
    original.league_stats={int(y):v for y,v in catalog['legacy_yearly'].items()}
    original.league_stats['all']=catalog['legacy_all']
    bs=[p for p in catalog['profiles'].values() if p['role']=='batter' and p['legacy_eligible'] and all(p['legacy_row'].get(k) is not None for k in ('2B','3B','AB','H','SO','BB','HR'))]
    ps=[p for p in catalog['profiles'].values() if p['role']=='pitcher' and p['legacy_eligible']]
    selector=Random(20261109);cases=[]
    # Include the user's historic/current example plus varied seasons/profiles.
    cases.append((next(b for b in bs if b['name']=='백인천' and b['season']==1982),next(p for p in ps if p['name']=='원태인' and p['season']==2024)))
    cases.extend((selector.choice(bs),selector.choice(ps)) for _ in range(39))
    # Exercise original edge behavior as MOCK_TEST_ONLY mutations, separate from records.
    b,p=cases[0];b={**b,'legacy_row':{**b['legacy_row'],'H':20,'HR':20,'2B':0,'3B':0}}
    cases.append((b,p))
    extreme={**b,'legacy_row':{**b['legacy_row'],'PA':100000,'AB':100000,'H':50000,'HR':50000,'SO':90000,'BB':90000}}
    cases.append((extreme,{**p,'legacy_row':{**p['legacy_row'],'TBF':100000,'SO':90000,'BB':90000,'HR':50000}}))
    checks=0
    for b,p in cases:
        model=legacy(b,p,catalog['legacy_yearly'],catalog['legacy_all'])
        for seed in (0,1,41,42,20261109):
            namespace['random']=Random(seed)
            output=io.StringIO()
            with redirect_stdout(output):original.simulate({**b['legacy_row'],'Year':b['season'],'Name':b['name']},{**p['legacy_row'],'Year':p['season'],'Name':p['name']},simulated_pa=25)
            mapping={'single':'단타','double':'2루타','triple':'3루타','home_run':'홈런','walk':'볼넷','strikeout':'삼진','other':'아웃'}
            observed={e:int(re.search(re.escape(label)+r': (\d+)',output.getvalue())[1]) for e,label in mapping.items()};observed['hbp']=0
            actual=simulate(model,25,seed,1)['counts']
            if observed!=actual:raise AssertionError(f'원본 사건 수 차이: case {checks}')
            for key,label in [('K_rate','삼진'),('BB_rate','볼넷'),('HR_rate','홈런')]:
                printed=float(re.search(label+r' 확률 : ([\d.]+)%',output.getvalue())[1])/100
                if abs(printed-model['steps']['claimed_binary'][key])>0.000050001:raise AssertionError('원본 표시 확률 차이')
            checks+=1
    return {'archive_sha256':LEGACY_SHA,'original_code_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'dataset_id':catalog['dataset_id'],'real_profile_pairs':40,'mock_edge_pairs':2,'seeds_per_pair':5,
            'exact_25pa_count_comparisons':checks,'passed':True,
            'scope':'Counts and rounded binary probabilities match reviewed original simulate(); not validation of KBO accuracy, causal effects, era fairness or licenses.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    result=validate_assignment(root,args.archive or root/'data/local/catalog/kbo-assignment/assignment-original.zip')
    if args.output:write_json(args.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
