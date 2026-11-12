"""Prepare verified public sources in the user's own checkout."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.warehouse import build


def prepare_sources(root, league, start=2025, end=2025):
    if league == 'MLB':
        if not 2000 <= start <= end <= 2025:
            raise ValueError('MLB 자동 수집은 2000~2025 시즌을 지원합니다.')
        from collect_league_seasons import mlb,new_dir,fetch,TERMS_URL,reusable_manifest
        missing=[y for y in range(start,end+1) if reusable_manifest(root,f'https://www.retrosheet.org/downloads/plays/{y}plays.zip') is None]
        if missing:
            folder=new_dir(root,'MLB',end,'notice')
            notice=folder/'source-notice.html'
            fetch(TERMS_URL,notice)
            text=notice.read_text(encoding='utf-8')
            if 'free to make any desired use' not in text or 'copyrighted by Retrosheet' not in text:
                raise ValueError('Retrosheet 이용 고지 확인 실패')
            for y in missing:
                print(f'MLB {y} 시즌 내려받기·검사',flush=True)
                mlb(root,y,text)
    elif league == 'NPB':
        from collect_npb_community import collect
        from prepare_npb_community import prepare
        print('NPB 공개 CSV 내려받기·검사 (최초 약 302 MB)',flush=True)
        m,folder=collect(root)
        if m['summary']['failures']:
            errors=[f.get('error_type','오류') for f in m['files'] if f['status']=='FAILED']
            raise ValueError('NPB 파일 수신 실패: '+', '.join(sorted(set(errors)))+'. 인터넷 연결을 확인한 뒤 다시 시도하세요.')
        print(prepare(root,folder/'manifest.json'),flush=True)
    else:
        raise ValueError('지원하지 않는 자료입니다.')
    print('선수·학습 자료 연결 중',flush=True)
    manifest,path=build(root)
    print(league+' 기록 연결 완료 · '+str(manifest['rows']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--league',choices=['MLB','NPB'],default='NPB')
    p.add_argument('--start',type=int,default=2025)
    p.add_argument('--end',type=int,default=2025)
    a=p.parse_args()
    prepare_sources(ROOT,a.league,a.start,a.end)
