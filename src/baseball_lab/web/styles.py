"""Inline the packaged design system for web and standalone saved reports."""
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def app_styles():
    root=files('baseball_lab').joinpath('web')
    return '\n'.join(root.joinpath(name).read_text(encoding='utf-8') for name in ('app.css','report.css'))


def apply_app_styles(html):
    return html.replace('__APP_STYLES__',app_styles()) if '__APP_STYLES__' in html else html
