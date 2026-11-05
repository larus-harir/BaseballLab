"""Readable first, inspectable second. Render old R1 evidence without modifying it."""
import json
from pathlib import Path
from baseball_lab.data.lineage import write_json
from .summary import build_summary
from baseball_lab.data.protection import public_view
from baseball_lab.web.scene_assets import embed


def render(result):
    payload=json.dumps(public_view({**result,'reading':build_summary(result)}),ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    return embed(Path(__file__).with_name('report.html').read_text(encoding='utf-8')).replace('__RESEARCH__',payload)


def report(output,result):
    output=Path(output);reading=build_summary(result)
    (output/'report.html').write_text(render(result),encoding='utf-8')
    write_json(output/'summary.json',reading)
    lines=['# Match-B · 이번 학습 한눈에 보기','',reading['headline'],reading['growth_headline'],'',
           f"반복당 {reading['episodes_per_repeat']:,}상황 학습 · {reading['finished_repeats']}/{reading['planned_repeats']}회 최종 평가 완료"]
    if reading['duel']:
        d=reading['duel'];lines += [f"현재 맞대결: 공격 득점 {100*d['rate']:.1f}% / 수비 차단 {100*(1-d['rate']):.1f}% ({d['n']:,}대결)."]
    for g in reading['growth']:
        if g['before']:lines.append(f"{g['label']}: 같은 고정 상대에 대한 성공률 {100*g['before']['rate']:.1f}% → {100*g['after']['rate']:.1f}%. {g['text']}")
    for c in reading['choices']:lines.append(f"{c['label']}: {100*c['before']:.1f}% → {100*c['after']:.1f}%. {c['text']}")
    lines += ['',reading['scope'],'자세한 비교·리플레이·자료 근거는 report.html의 탭에서 확인하세요.','',result['dataset']['credit']]
    (output/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
