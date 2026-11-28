"""Small report projection, tied to the original research file revision."""
from collections import OrderedDict
import json
from threading import Lock

from baseball_lab.data.lineage import write_json
from .strategy_view import build as strategy_view

LEARNING_SCHEMAS=('Match-pitch-decision-game-v7','Match-pitch-decision-game-v8')
FORMAT='learning-page-data-v2'
PAGE_KEYS=('schema','learning_review','overview','status','teams','leagues','cohorts','heatmaps','evidence')
_cache=OrderedDict()
_lock=Lock()


def page_data(view):
    return {**{key:view[key] for key in PAGE_KEYS},
            'learning':{'optimizer_steps':view['learning']['optimizer_steps']}}


def build(result):
    return page_data(strategy_view(result))


def revision(source):
    stat=source.stat()
    return (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino)


def save(source,view):
    write_json(source.with_name('report-data.json'),
               {'format':FORMAT,'source_revision':list(revision(source)),'view':view},compact=True)


def _read(source,source_revision):
    cache=source.with_name('report-data.json')
    if not cache.is_symlink() and cache.is_file():
        try:
            saved=json.loads(cache.read_text(encoding='utf-8'))
            if saved['format']==FORMAT and saved['source_revision']==list(source_revision):
                view=saved['view']
                if view['learning_review'] and view['status']=='COMPLETED':
                    return page_data(view)
        except (OSError,ValueError,TypeError,KeyError):
            pass
    raw=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(raw,dict):raise ValueError('학습 기록 형식이 올바르지 않습니다.')
    return build(raw) if raw.get('schema') in LEARNING_SCHEMAS else raw


def load(source):
    source_revision=revision(source)
    key=(source,source_revision)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    view=_read(source,source_revision)
    # Legacy results are rendered from their original structure as before.
    if view.get('learning_review'):
        with _lock:
            _cache[key]=view
            _cache.move_to_end(key)
            if len(_cache)>4:_cache.popitem(last=False)
    return view
