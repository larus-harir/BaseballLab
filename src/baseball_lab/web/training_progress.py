"""Validated worker progress across independent learning runs."""
import json

PREFIX='LEARNING_PROGRESS '


def parse(line):
    if not line.startswith(PREFIX):return None
    try:d=json.loads(line[len(PREFIX):])
    except (ValueError,TypeError):return None
    if not isinstance(d,dict):return None
    done,total=d.get('completed'),d.get('total');phase=d.get('phase')
    if type(done) is not int or type(total) is not int or not 0<=done<=total<=300000 or not total:return None
    if phase not in ('training','summarizing'):return None
    message='배운 플레이와 결과를 정리하고 있습니다.' if phase=='summarizing' else f'AI가 야구 플레이를 연습하고 있습니다. 전체 {total:,}경기 중 {done:,}경기 완료'
    return {'completed_episodes':done,'target_episodes':total,'progress_scope':'all_runs','message':message}
