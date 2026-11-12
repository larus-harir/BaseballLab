"""Read-only source index over the existing stores, with explicit preparation.

Descriptors use one contract while provider-native payloads remain unchanged:
player-season catalogs for BaseballLab/EraMatch; the existing observed-turn
dataset for Match. Inspecting readiness never starts downloads or rewrites data.
"""
import json
import csv
from pathlib import Path

from baseball_lab.data.lineage import checksum,utc_now
from baseball_lab.data.retrosheet_releases import RELEASES
from baseball_lab.matchup.catalog import read_catalog,source_directory,LEGACY_SHA,catalog_verification

_RAW_CACHE={}


class DatasetCatalog:
    def __init__(self,root):self.root=Path(root).resolve()

    def supported_seasons(self,project):
        if project=='match':
            from .training_window import sources
            return sorted(set(RELEASES)|set(sources(self.root)))
        if project in ('baseball','match'):return sorted(RELEASES)
        if project=='eramatch':
            data=self.get('eramatch')
            return sorted({p['season'] for p in data['profiles'].values()}) if data else []
        raise ValueError('지원하는 프로젝트를 선택하세요.')

    def source_id(self,project,season=2024):
        if project not in ('baseball','eramatch','match'):raise ValueError('지원하는 프로젝트를 선택하세요.')
        if type(season) is not int:raise ValueError('시즌은 정수 연도여야 합니다.')
        if project in ('baseball','match'):
            if season not in self.supported_seasons(project):raise ValueError('이 시즌의 확인된 MLB 기록이 없습니다.')
            return f'mlb-{season}' if project=='baseball' else f'retrosheet-{season}'
        if not 1982<=season<=2025:raise ValueError('과제에 포함된 시즌 범위는 1982~2025년입니다.')
        return 'kbo-assignment'

    def get(self,project,season=2024):
        source=self.source_id(project,season)
        if project=='match' and season not in RELEASES:
            return None  # Preparation belongs to ensure(), not a read lookup.
        if project!='match':
            data=read_catalog(self.root,source)
            if data is not None or project!='eramatch':return data
            archive=source_directory(self.root,source)/'assignment-original.zip'
            if archive.is_file() and checksum(archive)!=LEGACY_SHA:
                raise ValueError('보관한 과제 원본 ZIP이 검토한 버전과 다릅니다.')
            from baseball_lab.experiments.eramatch.builtin import load_builtin
            return load_builtin()
        directory=self._raw_directory(season)
        path=directory/'dataset.json'
        if path.is_symlink():raise ValueError('공식 자료 경로에 링크를 사용할 수 없습니다.')
        if not path.is_file():return None
        self._describe_match(season,source)
        from baseball_lab.r1.data import load
        return load(path)

    def ensure(self,project,season=2024,progress=None):
        self.source_id(project,season)
        if progress:progress('보관한 선수 기록을 확인하고 있어요.')
        existing=self.get(project,season)
        if existing is not None:return existing
        if project=='baseball':
            from baseball_lab.matchup.mlb import prepare
            return prepare(self.root,season,progress=progress)
        if project=='match':
            if season not in RELEASES:
                from .training_window import acquire,periods
                bounds=periods(self.root)[str(season)]
                return acquire(self.root,bounds['start'],bounds['end'])
            from baseball_lab.r1.provider import acquire
            if progress:progress(f'{season}년 공식 경기 기록을 준비하고 있어요.')
            return acquire(self.root/'data/local/retrosheet',year=season)
        from baseball_lab.experiments.eramatch.builtin import load_builtin
        return load_builtin()

    def describe(self,project,season=2024):
        source_id=self.source_id(project,season)
        if project=='match':return self._describe_match(season,source_id)
        data=self.get(project,season)
        seasons=self.supported_seasons(project)
        base={'project':project,'source_id':source_id,'league':'KBO' if project=='eramatch' else 'MLB',
              'supported_seasons':seasons,'seasons':seasons,'ready':data is not None,
              'needs_connection':False,'automatic_preparation':project=='baseball','metadata':None}
        if data is None:
            base['message']='EraMatch 기본 기록이 없습니다. 프로그램을 업데이트하거나 다시 설치하세요.' if project=='eramatch' else f'{season}년 공식 선수 기록을 자동으로 준비합니다.'
            return base
        profiles=list(data['profiles'].values());source=data['source']
        included=project=='eramatch' and not (source_directory(self.root,source_id)/'catalog.json').is_file()
        if included:
            from baseball_lab.experiments.eramatch.builtin import verification
            verified=verification()
        else:verified=catalog_verification(self.root,source_id)
        actual_seasons=sorted({p['season'] for p in profiles})
        original_rows=data.get('audit',{}).get('rows')
        fields=('PA','TBF','AB','H','SO','BB','HBP','HP','HR','2B','3B','SF','SH','IP_OUTS')
        missing={role:{field:sum(p['counts'].get(field) is None for p in profiles if p['role']==role)
                       for field in fields} for role in ('batter','pitcher')}
        metadata={'schema':'dataset-descriptor-v1','dataset_id':data['dataset_id'],'provider':'user-assignment' if project=='eramatch' else 'Retrosheet',
                  'league':base['league'],'seasons':actual_seasons,'granularity':['season','PA'] if project=='baseball' else ['season'],
                  'source_schema':data['schema'],'units':{'counts':'events','PA':'completed plate appearances','TBF':'batters faced','AB':'official at bats','IP_OUTS':'outs; three per inning','rates':'event count / stated denominator'},
                  'license':source.get('license'),'source_url':source.get('source_url'),
                  'acquisition_method':'application-included assignment season aggregates' if included else 'user supplied pinned archive' if project=='eramatch' else 'official downloadable distribution; verified local cache reused',
                  'acquired_at':source.get('acquired_at'),'cache_checked_at':utc_now(),'verified_at':verified['verified_at'],'version':data['dataset_id'],
                  'sha256':[{'name':verified['name'],'sha256':verified['sha256']}] if included else source.get('files',[]),
                  'included_with_application':included,'original_input_hashes':source.get('files',[]) if included else [],
                  'row_count':sum(original_rows.values()) if original_rows else sum(data['league_counts'][str(season)].values()),
                  'row_counts_by_role':original_rows,'profile_count':len(profiles),'missingness':missing,'entity_ids':{'keys':['league','role','player_id','season'],'names_are_identifiers':False},
                  'known_biases':source.get('field_assumptions',[])+(['시대·팀·구장·수비와 관측 선택이 섞인 시즌 집계입니다.'] if project=='eramatch' else ['정규시즌 완료 타석만 포함합니다. 구장·수비·상대 선택의 인과 효과를 분리하지 않습니다.']),
                  'allowed_uses':['local assignment reproduction','unvalidated normalized comparison'] if project=='eramatch' else ['statistical PA exploration','predictive comparison','source observations'],
                  'status':source['status'],'capabilities':{'independent_pa':True,'normalized_comparison_profiles':sum(p['normalized_eligible'] for p in profiles),'pitch_actions':False,'full_game':False},
                  'readiness':{'ready':True,'needs_connection':False},
                  'coverage':{'profile_count':len(profiles),'selected_season':season,'profiles_in_selected_season':sum(p['season']==season for p in profiles)},
                  'verification_scope':verified['scope'] if included else 'catalog content identity and registered original file checksums; causal validity and licensing are distinct'}
        base.update(message='보관한 기록을 확인했습니다. 선수를 고르고 바로 대결하세요.',metadata=metadata)
        if season not in actual_seasons:
            base.update(ready=False,message='이 시즌의 선수 기록은 없습니다. 포함된 다른 시즌을 선택하세요.')
            metadata['readiness']['ready']=False
        return base

    def list_sources(self):
        entries=[('baseball',year) for year in self.supported_seasons('baseball')]+[('eramatch',2024)]+[('match',year) for year in self.supported_seasons('match')]
        result=[]
        for project,season in entries:
            try:result.append(self.describe(project,season))
            except (OSError,ValueError,KeyError,TypeError) as exc:
                # One damaged source must not hide other valid sources. It is
                # reported without switching league/year or repairing originals.
                result.append({'project':project,'source_id':self.source_id(project,season),
                    'league':'KBO' if project=='eramatch' else 'MLB','ready':False,'needs_connection':False,
                    'automatic_preparation':False,'supported_seasons':[] if project=='eramatch' else self.supported_seasons(project),
                    'seasons':[],'metadata':None,'error':str(exc),'message':f'보관 자료를 확인해야 합니다: {exc}'})
        from baseball_lab.matchup.collected import available,overview
        if available(self.root):
            for league in ('MLB','KBO','NPB'):
                try:
                    d=overview(self.root,'baseball' if league=='MLB' else 'eramatch',league=league)
                    if d['supported_seasons']:result.append({**{k:v for k,v in d.items() if k!='profiles'},'source_id':'collected-'+league.lower()})
                except (OSError,ValueError,KeyError) as exc:result.append({'source_id':'collected-'+league.lower(),'ready':False,'error':str(exc)})
        return result

    def iter_plays(self,season):
        """Verified official plays, including non-PA events; callers choose units."""
        self.source_id('match',season)
        descriptor=self.describe('match',season)
        if not descriptor['ready']:raise ValueError('이 시즌의 플레이별 원본이 없어 세부 사건을 확인할 수 없습니다.')
        if descriptor.get('collected'):
            from .training_window import sources
            from .warehouse import local_path
            entry=next(f for f in sources(self.root)[season]['files'] if f['path'].endswith('.csv'))
            path=local_path(self.root,self.root/entry['path'])
        else:path=self._raw_directory(season)/f'{season}plays.csv'
        with path.open(encoding='utf-8-sig',newline='') as file:
            for row in csv.DictReader(file):
                if row['gametype']=='regular' and row['pbp']=='full':yield row

    def _raw_directory(self,season):
        path=self.root/f'data/local/retrosheet/official-{season}';current=self.root
        for part in path.relative_to(self.root).parts:
            current=current/part
            if current.is_symlink():raise ValueError('공식 자료 경로에 링크를 사용할 수 없습니다.')
        return path

    def _describe_match(self,season,source_id):
        directory=self._raw_directory(season);path=directory/'dataset.json'
        base={'project':'match','source_id':source_id,'league':'MLB','supported_seasons':self.supported_seasons('match'),
              'seasons':[season],'ready':False,'needs_connection':False,'automatic_preparation':True,'metadata':None,
              'message':f'{season}년 공식 경기 기록은 학습을 시작할 때 자동으로 준비합니다.'}
        if not path.is_file():
            from .training_window import sources
            m=sources(self.root).get(season)
            if not m:return base
            from .warehouse import local_path
            files=[(local_path(self.root,self.root/f['path']),f['sha256']) for f in m['files']]
            fingerprint=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns,sha) for p,sha in files)
            key='collected:'+str(self.root)+':'+str(season);cached=_RAW_CACHE.get(key)
            if not cached or cached[0]!=fingerprint:
                if any(checksum(p)!=sha for p,sha in files):raise ValueError('수집 원본의 지문이 다릅니다.')
                _RAW_CACHE[key]=(fingerprint,m,utc_now())
            base.update(ready=True,collected=True,message='수집한 실제 플레이 원본을 사용합니다.',metadata={
                'schema':'dataset-descriptor-v1','provider':'Retrosheet','league':'MLB','seasons':[season],
                'source_schema':m['schema'],'status':m['source_status'],'source_url':m['source_url'],
                'dataset_id':m['files'][-1]['sha256'],'version':m['files'][-1]['sha256'],'row_count':m['row_count'],
                'sha256':[{'name':p.name,'sha256':sha} for p,sha in files],'license':m.get('credit'),
                'verified_at':_RAW_CACHE[key][2],'capabilities':{'observed_turns':True,'pitch_actions':False,'full_game':False}})
            return base
        files=[path,directory/f'{season}plays.zip',directory/f'{season}plays.csv']
        if any(p.is_symlink() or not p.is_file() for p in files):raise ValueError('공식 원본 경로를 확인하세요.')
        fingerprint=tuple((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in files)
        cached=_RAW_CACHE.get(str(directory))
        if cached and cached[0]==fingerprint:manifest=cached[1]
        else:
            # The existing turn dataset is ~90MB. Read its manifest prefix only;
            # Match's existing load() still verifies all turns on actual execution.
            text='';decoder=json.JSONDecoder();manifest=None
            with path.open(encoding='utf-8') as f:
                while len(text)<2*1024*1024:
                    chunk=f.read(65536)
                    if not chunk:break
                    text+=chunk
                    try:
                        prefix=text.index('"manifest"');start=text.index(':',prefix)+1
                        manifest,_=decoder.raw_decode(text[start:].lstrip());break
                    except (ValueError,json.JSONDecodeError):continue
            if not isinstance(manifest,dict):raise ValueError('기존 경기 자료의 메타데이터를 읽지 못했습니다.')
            if manifest.get('source_version')!=RELEASES[season]['sha256'] or checksum(files[1])!=RELEASES[season]['sha256'] or checksum(files[2])!=manifest.get('parsed_csv_sha256'):
                raise ValueError('보관한 공식 경기 기록의 버전·해시가 다릅니다.')
            _RAW_CACHE[str(directory)]=(fingerprint,manifest,utc_now())
        verified_at=_RAW_CACHE[str(directory)][2]
        base.update(ready=True,message='공식 원본을 확인했습니다. 기존 Match 학습 경로가 정제 기록과 환경을 검사합니다.',metadata={
            'schema':'dataset-descriptor-v1','provider':'Retrosheet','league':'MLB','seasons':[season],'granularity':['game','PA'],
            'source_schema':manifest.get('schema'),'dataset_id':manifest.get('dataset_id'),'version':manifest['source_version'],
            'units':{'outs':'outs','bases':'occupied-base bit mask','runs':'runs'},'license':manifest.get('credit'),
            'source_url':manifest.get('source_url'),'acquisition_method':'official download; existing local raw and normalized store',
            'acquired_at':manifest.get('acquired_at'),'cache_checked_at':utc_now(),'verified_at':verified_at,'sha256':[{'name':p.name,'sha256':manifest.get('parsed_csv_sha256') if p.suffix=='.csv' else manifest['source_version']} for p in files[1:]],
            'row_count':manifest.get('raw_event_rows'),'used_segments':manifest.get('used_segments'),'missingness':manifest.get('exclusions',{}),
            'entity_ids':{'keys':['game_id','play_number','source_row_id']},'known_biases':['관측된 인간 선택·선수·상황의 편향과 미관측 반사실 결과가 남아 있습니다.'],
            'allowed_uses':['observed turn replay','limited one-run experiment under stated assumptions'],'status':manifest.get('source_status'),
            'capabilities':{'observed_turns':True,'pitch_actions':False,'full_game':False},
            'verification_scope':'manifest fields plus pinned archive and parsed CSV checksums; Match validates normalized turns on execution'})
        return base
