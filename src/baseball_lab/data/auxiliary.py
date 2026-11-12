"""Read-only team context from acquired KBO CSV; never alter PA probabilities."""
import csv,json,math
from pathlib import Path
from .warehouse import local_path
from .lineage import checksum


def summarize(root,league,season,role=None,player_id=None):
    if league not in ('KBO','NPB'):raise ValueError('팀 보조 기록은 KBO·NPB에서 확인하세요.')
    if type(season) is not int or not 1800<=season<=2200:raise ValueError('시즌을 확인하세요.')
    result={'league':league,'season':season,'tables':[],'scope':'실제 팀 시즌 기록입니다. 선수 대결의 가상 확률이나 선택 행동의 효과로 대입하지 않습니다.'}
    if league=='NPB':
        result['note']='NPB 선수 기록은 정규시즌 종류가 확인된 경기의 집계입니다. 아래는 해당 선수의 구속값이 있는 원본 행 예시입니다. 위치 좌표의 단위·기준은 검증하지 않아 원문 값만 보존하며 구장 그림에 배치하지 않습니다.'
        result.update(npb_samples(root,season,role,player_id))
        return result
    root=Path(root).resolve();chosen={}
    for file in (root/'data/local/community').glob('kaggle-*/manifest.json'):
        local_path(root,file);m=json.loads(file.read_text(encoding='utf-8'));key=m.get('source_namespace','')
        if key not in ('kaggle-lazyjun01/kbo-defensive-data2001-2024','kaggle-lazyjun01/kbo-runners-data2001-2024'):continue
        previous=chosen.get(key)
        if previous is None or m['version']>previous['version']:chosen[key]=m
    for key,m in chosen.items():
        files=m['files']
        # The Runner/Running files overlap. Use the explicitly chosen fuller
        # table, and retain its inconsistent original cells with a warning.
        if 'runners' in key:files=[next((x for x in files if x['path'].endswith('KBO_Running_data.csv')),files[0])]
        for item in files:
            path=local_path(root,root/item['path'])
            if checksum(path)!=item['sha256']:raise ValueError('팀 보조 원본의 검증값이 다릅니다.')
            with path.open(encoding='utf-8-sig',newline='') as f:rows=[r for r in csv.DictReader(f) if r.get('year')==str(season)]
            for row in rows:
                if 'steals' in row and int(row['steals'])+int(row['caught_stealing'])!=int(row['steal_attempts']):
                    row['quality_note']='도루 시도와 성공·실패 합계가 다릅니다. 이 기록으로 성공률을 추정하지 않습니다.'
            if rows:result['tables'].append({'kind':'running' if 'runners' in key else 'defense','rows':rows,
                'source_url':m['source_url'],'license':m['publisher_license'],'source_sha256':item['sha256']})
    result['note']='팀 이름을 선수 기록과 임의로 대응하지 않았습니다. 이 시즌의 팀별 관측 자료를 별도로 보여 줍니다.'
    return result


def npb_samples(root,season,role,player_id):
    if role not in ('batter','pitcher',None):raise ValueError('선수 역할을 확인하세요.')
    if player_id is not None and (not isinstance(player_id,str) or len(player_id)>80):raise ValueError('선수 ID를 확인하세요.')
    root=Path(root).resolve();samples=[];sources=[]
    from .community import integer
    requested=integer(player_id) if role and player_id else None
    manifests=sorted((root/'data/local/community/npb-armstjc').glob('*/manifest.json'),reverse=True)
    for manifest in manifests[:1]:
        local_path(root,manifest);m=json.loads(manifest.read_text(encoding='utf-8'))
        for item in m['files']:
            if item.get('kind')!='pbp' or str(season) not in item.get('seasons',[]):continue
            path=local_path(root,root/item['path'])
            if checksum(path)!=item['sha256']:raise ValueError('NPB 장면 원본의 지문이 다릅니다.')
            with path.open(encoding='utf-8-sig',newline='') as f:
                for r in csv.DictReader(f):
                    if r.get('game_type_id') not in ('1','2','26'):continue
                    if role and requested is not None:
                        try:source_id=integer(r.get(role))
                        except ValueError:continue
                        if source_id!=requested:continue
                    speed=r.get('release_speed_kmh','')
                    try:valid=math.isfinite(float(speed)) and float(speed)>0
                    except (TypeError,ValueError):valid=False
                    if not valid:continue
                    samples.append({k:r.get(k) or None for k in ('game_id','play_id','pitcher','batter','release_speed_kmh','plate_x','plate_y','description_jap')})
                    if len(samples)==5:break
            sources.append({'sha256':item['sha256'],'url':m['source_url']})
            if len(samples)==5:break
    return {'pitch_samples':samples,'sources':sources,'sample_scope':'source order, first five regular-season rows with a positive reported km/h value; no claim of independent pitch totals or calibrated coordinates',
        'attribution':'This uses data sourced from the Nippon Baseball Data Repository, which can be accessed here: https://github.com/armstjc/Nippon-Baseball-Data-Repository'}
