"""Prepare the pinned community NPB source in the user's own checkout."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from collect_npb_community import collect
from prepare_npb_community import prepare
from baseball_lab.data.warehouse import build

if __name__=='__main__':
    m,folder=collect(ROOT)
    if m['summary']['failures']:raise SystemExit('NPB 파일 수신 실패. 검증된 원본은 보존했습니다.')
    print(prepare(ROOT,folder/'manifest.json'),flush=True)
    manifest,path=build(ROOT)
    print('NPB 선수 기록 연결 완료 ·',manifest['rows'],flush=True)
