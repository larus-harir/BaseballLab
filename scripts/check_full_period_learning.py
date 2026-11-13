"""Real 2000--2025 input acceptance plus short neural MLB/KBO mixed learning.

Retains a new report; never overwrites source snapshots or existing studies.
"""
import json
from pathlib import Path
import secrets
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from baseball_lab.data.compact import periods
from baseball_lab.data.training_window import acquire
from baseball_lab.data.lineage import write_json
from baseball_lab.experiments.match.team_win.mixed import train
from baseball_lab.experiments.match.team_win.training import Config
ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'outputs'/('full-period-acceptance-'+secrets.token_hex(6))
    source_periods=periods();start=source_periods['2000']['start'];end=source_periods['2025']['end']
    begin=time.perf_counter();dataset=acquire(ROOT,start,end);prepared=time.perf_counter()-begin
    print('전체 기간 입력 확인 완료',len(dataset['records']),flush=True)
    result=train(ROOT,dataset,start,end,output,Config(episodes=20,seeds=(41,),evaluation_n=20,evaluate_every=20,batch_size=2),{'MLB':1,'KBO':1})
    summary={'source_years':dataset['manifest']['selected_seasons'],'source_records':len(dataset['records']),
        'source_seconds':prepared,'total_seconds':time.perf_counter()-begin,'dataset_id':dataset['manifest']['dataset_id'],
        'episodes':20,'seeds':[41],'mixture':{'MLB':1,'KBO':1},'report':str(output.relative_to(ROOT)/'report.html')}
    assert (output/'research.json').is_file() and (output/'report.html').is_file()
    write_json(output/'acceptance.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
