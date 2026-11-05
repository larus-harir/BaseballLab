"""Embed shared offline field renderer; no CDN or external resource required."""
from pathlib import Path


def embed(template):
    return template.replace('__FIELD_SCRIPT__',Path(__file__).with_name('field.js').read_text(encoding='utf-8'))
