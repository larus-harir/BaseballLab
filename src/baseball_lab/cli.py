"""Evidence-first CLI. Production paths never fall back to synthetic models."""
import argparse
from datetime import datetime
from pathlib import Path

from baseball_lab.data.lineage import RawSource, utc_now
from baseball_lab.experiments.registry import REPOSITORY_ROOT


def main():
    parser=argparse.ArgumentParser(description='야구 AI 연구실 · 실제 데이터와 실행 근거로 관찰하는 E01')
    parser.add_argument('--mode',choices=('prepare','audit','fit','inspect','train','replay','baseline','web','run','scoring','simulate'),default='web')
    parser.add_argument('--port',type=int,default=8765,help='웹 연구실 포트')
    parser.add_argument('--authorization-reference',help='자동 수집에 별도로 허용받은 근거 (기본은 수동 내보내기)')
    parser.add_argument('--data-dir',type=Path,default=REPOSITORY_ROOT/'data/local/statcast')
    parser.add_argument('--model',type=Path,help='실제 데이터로 보정·독립 검증한 model.json')
    parser.add_argument('--start');parser.add_argument('--end')
    parser.add_argument('--train-before',default='2024-05-04');parser.add_argument('--test-from',default='2024-05-05')
    parser.add_argument('--usage-note',default='Local exploratory research; terms not independently verified by software; no redistribution grant')
    parser.add_argument('--csv',type=Path,action='append',help='사용자가 공식 사이트에서 내보낸 원본 CSV')
    parser.add_argument('--source-url',help='수동 내보내기의 공식 원천 HTTPS URL')
    parser.add_argument('--acquired-at',help='원본 획득 시각 ISO-8601')
    parser.add_argument('--episodes',type=int,default=600,help='학습 타석 수; 경기 수가 아님')
    parser.add_argument('--seed',type=int,default=20261104)
    parser.add_argument('--seeds',help='득점 상황 연구의 여러 재현 번호. 예: 41,42,43')
    parser.add_argument('--evaluate-every',type=int)
    parser.add_argument('--evaluation-n',type=int,default=100,help='상대별 평가 타석 수')
    parser.add_argument('--min-support',type=int,default=10)
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--open',action='store_true',help='한국어 관찰실을 브라우저로 열기')
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--observation-source',choices=('model','observed'),default='model')
    parser.add_argument('--outs',type=int,default=0)
    parser.add_argument('--bases',type=int,default=1)
    parser.add_argument('--policy-style',choices=('basic','random'),default='basic')
    args=parser.parse_args()
    args.start=args.start or ('2024-03-20' if args.mode in ('scoring','simulate') else '2024-05-01')
    args.end=args.end or ('2024-09-30' if args.mode in ('scoring','simulate') else '2024-05-06')
    args.evaluate_every=args.evaluate_every or (max(200,args.episodes//3) if args.mode=='scoring' else 200)
    if args.list:
        print('E01 · 실제 경기 기록으로 득점·실점 방어를 배우는 상황 실험. 웹에서 AI 학습 시작을 누르세요. 전체 경기 승리는 아직 미지원입니다.')
        return
    if args.mode=='web':
        if not 0<=args.port<=65535:parser.error('포트는 0~65535 사이의 정수로 입력하세요.')
        from baseball_lab.web.server import serve
        try: serve(REPOSITORY_ROOT,args.port,args.open)
        except OSError as exc: parser.exit(2,f'연구실을 열지 못했어요: {exc}. --port 8766 등 다른 번호를 사용하세요.\n')
        return
    output=args.output or REPOSITORY_ROOT/'outputs/E01'/('research_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    model_path=args.model or args.data_dir/'model.json'
    try:
        from baseball_lab.data.statcast import acquire,audit,manual_source,load_dataset
        from baseball_lab.outcome.empirical import fit,load_model
        from baseball_lab.tracking.evidence_report import write_report
        if args.mode=='simulate':
            from baseball_lab.r1.provider import acquire
            from baseball_lab.simulation.scoring import observe
            dataset=acquire(REPOSITORY_ROOT/'data/local/retrosheet',year=datetime.fromisoformat(args.start).year)
            observe(dataset,args.start,args.end,output,seed=args.seed,outs=args.outs,bases=args.bases,source=args.observation_source,style=args.policy_style)
            print('관찰 완료 · 정책 학습 없이 실제 기록 또는 모델 전이를 재생합니다.',flush=True)
        elif args.mode=='scoring':
            from baseball_lab.r1.provider import acquire
            from baseball_lab.r1.training import train,Config
            seeds=tuple(int(s.strip()) for s in args.seeds.split(',')) if args.seeds else (args.seed,args.seed+1,args.seed+2)
            config=Config(args.episodes,seeds,args.evaluate_every,args.evaluation_n)
            config.validate()
            dataset=acquire(REPOSITORY_ROOT/'data/local/retrosheet',year=datetime.fromisoformat(args.start).year)
            print('단계 2 · 경기와 날짜를 나눠 실제 전이 분포를 검사합니다.',flush=True)
            print('단계 3 · 출루가 아닌 한 점 득점·실점 방어를 학습합니다. 전체 경기 승리는 아닙니다.',flush=True)
            train(dataset,args.start,args.end,output,config)
        elif args.mode=='run':
            from baseball_lab.research.pipeline import Plan,run
            run(Plan(args.start,args.end),args.data_dir,output,episodes=args.episodes,seed=args.seed,authorization_reference=args.authorization_reference)
        elif args.mode=='prepare':
            acquisition=acquire(args.start,args.end,args.data_dir/'raw',usage_note=args.usage_note,authorization_reference=args.authorization_reference)
            sources=[RawSource(**s) for s in acquisition['sources']]
            dataset=audit(sources,args.data_dir)
            model=fit(args.data_dir/'dataset.json',args.data_dir,train_before=args.train_before,test_from=args.test_from,min_support=args.min_support)
            write_report(output,dataset=dataset,model=model)
            print(f"자료 {dataset['manifest']['used_rows']}구 / 연구 적격: {model['validation']['research_ready']}")
            print(f'모델: {args.data_dir/"model.json"}')
            if not model['validation']['research_ready']:
                print('연구 실행 보류: '+str(model['validation']['eligibility_issues']))
        elif args.mode=='audit':
            if not args.csv or not args.source_url or not args.acquired_at:
                parser.error('--csv, --source-url, --acquired-at를 지정하세요.')
            sources=[manual_source(p,args.source_url,args.usage_note,args.acquired_at) for p in args.csv]
            dataset=audit(sources,args.data_dir)
            write_report(output,dataset=dataset)
            print(f"실제 내보내기 자료 감사 완료: 사용 {dataset['manifest']['used_rows']}구. fit 단계가 필요합니다.")
        elif args.mode=='fit':
            model=fit(args.data_dir/'dataset.json',args.data_dir,train_before=args.train_before,test_from=args.test_from,min_support=args.min_support)
            dataset=load_dataset(args.data_dir/'dataset.json')
            write_report(output,dataset=dataset,model=model)
            print(f"보정·독립 검증 완료. 연구 적격: {model['validation']['research_ready']}")
        elif args.mode in ('inspect','baseline'):
            model,dataset=load_model(model_path)
            write_report(output,dataset=dataset,model=model.artifact)
            print('실제 자료·보정 검증 화면입니다. AI 학습은 실행하지 않았습니다.')
        elif args.mode=='replay':
            if not args.checkpoint: parser.error('--mode replay에는 --checkpoint가 필요합니다.')
            from baseball_lab.research.replay import replay
            replay(args.checkpoint,model_path,output,seed=args.seed)
        else:
            if args.checkpoint: parser.error('저장 모델 재평가는 --mode replay를 사용하세요.')
            if not model_path.exists():
                raise FileNotFoundError('실데이터·보정 모델이 없습니다. 먼저 python scripts/quickstart.py --mode prepare --open 을 실행하세요. 공식 CSV 수동 내보내기도 audit로 가져올 수 있습니다.')
            from baseball_lab.research.training import ResearchConfig,train
            config=ResearchConfig(args.episodes,args.seed,args.evaluate_every,args.evaluation_n)
            train(config,model_path,output)
        print(f'관찰실: {(output/"report.html").resolve()}')
        if args.open:
            import webbrowser
            webbrowser.open((output/'report.html').resolve().as_uri())
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError) as exc:
        failure={'status':'DATA_OR_VALIDATION_REQUIRED','observed_at':utc_now(),'error':str(exc),
                 'research_executed':False,'synthetic_fallback':False}
        # Keep previous successful runs intact if the chosen directory already has evidence.
        if not output.exists() or not any(output.iterdir()):
            from baseball_lab.tracking.evidence_report import write_report
            write_report(output,failure=failure)
            print(f'대기 상태 관찰실: {(output/"report.html").resolve()}')
            if args.open:
                import webbrowser
                webbrowser.open((output/'report.html').resolve().as_uri())
        parser.exit(2,f'연구 실행 보류: {exc}\n임의 합성 자료로 대체하지 않았습니다.\n')
