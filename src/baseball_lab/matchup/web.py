"""The same explanation and result view for both statistical projects."""
import json
from pathlib import Path
from baseball_lab.data.protection import public_view


def render(project,token='',analysis=None):
    if project not in ('baseball','eramatch'):raise ValueError('알 수 없는 프로젝트')
    body=Path(__file__).parents[1].joinpath('web/matchup.html').read_text(encoding='utf-8')
    display=public_view(analysis)
    if display and 'simulation' in display and 'model' in display:
        from .reading import interpret
        display['reading']=interpret(display)
    if display and display.get('project')=='baseball' and display.get('validation') and 'last actual PA date' not in display['validation']['method']:
        display['validation_warning']='이 저장 결과의 예측 검사는 중단 경기 날짜를 바로잡기 전 기록입니다. 선수 기록의 대결 결과와 분리해서 보며, 최신 검사로 다시 실행하세요.'
        display['model_status']='PERIOD_CHECK_SUPERSEDED'
    initial=json.dumps(display,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return body.replace('__PROJECT__',project).replace('__SESSION_TOKEN__',token).replace('__ANALYSIS__',initial)
