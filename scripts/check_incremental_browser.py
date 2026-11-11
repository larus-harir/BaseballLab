"""Real Chromium acceptance checks for incremental redesign.

Requires Playwright, Chromium and the already connected real local catalogs.
The fresh-install case uses an explicit test transport copying the checked-in-
cache official distributions; it exercises unpacking/normalization/catalog
creation without redownloading the same public files. No synthetic player
records are supplied to the application.
"""
from contextlib import contextmanager
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from playwright.sync_api import sync_playwright,expect
from baseball_lab.web.server import Workbench,make_handler
from baseball_lab.data.protection import private


@contextmanager
def local_server(root):
    workbench=Workbench(root)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(workbench))
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port),workbench
    finally:
        server.shutdown();server.server_close();thread.join()


def choose(page,side,name):
    page.locator('#'+side+'Query').fill(name)
    expect(page.locator('#'+side+'Player option')).to_have_count(1,timeout=20000)
    expect(page.locator('#'+side+'Player')).to_contain_text(name)
    expect(page.locator('#'+side+'Player')).to_be_enabled()
    option=page.locator('#'+side+'Player option')
    page.locator('#'+side+'Player').select_option(option.get_attribute('value'))


def run_matchup(page,batter,pitcher):
    choose(page,'b',batter);choose(page,'p',pitcher)
    page.locator('#calculate').click()
    expect(page.locator('#result')).to_be_visible(timeout=30000)
    expect(page.locator('#resultTitle')).to_contain_text(batter)
    expect(page.locator('#resultTitle')).to_contain_text(pitcher)


def text_contrast(page,selector):
    colors=page.locator(selector).first.evaluate("""element=>{
      const foreground=getComputedStyle(element).color;
      let current=element,background='rgb(255, 255, 255)';
      while(current){const candidate=getComputedStyle(current).backgroundColor;
        if(candidate!=='rgba(0, 0, 0, 0)'&&candidate!=='transparent'){background=candidate;break}
        current=current.parentElement;
      }
      return {foreground,background};
    }""")
    def luminance(text):
        channels=[float(x)/255 for x in re.findall(r'[\d.]+',text)[:3]]
        values=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in channels]
        return sum(x*y for x,y in zip(values,(.2126,.7152,.0722)))
    a,b=sorted((luminance(colors['foreground']),luminance(colors['background'])))
    ratio=(b+.05)/(a+.05)
    assert ratio>=4.5,f'text contrast sample {selector}: {ratio:.2f}'
    return {'selector':selector,'ratio':round(ratio,2),**colors}


@contextmanager
def verified_distribution_transport(root):
    """Test-only transport. Every accepted URL maps to an existing official file."""
    from baseball_lab.r1.provider import TERMS_URL
    from baseball_lab.data.retrosheet_releases import RELEASES
    from baseball_lab.matchup.mlb import ROSTER_URL
    files={TERMS_URL:root/'data/local/retrosheet/official-2024/source-notice.html',
           RELEASES[2024]['url']:root/'data/local/retrosheet/official-2024/2024plays.zip',
           ROSTER_URL:root/'data/local/catalog/mlb-2024/2024eve.zip'}
    if not all(path.is_file() for path in files.values()):raise RuntimeError('실제 2024 공식 보관본을 먼저 준비하세요.')
    def copy_distribution(url,destination,limit):
        path=files.get(url)
        if path is None:raise AssertionError('MOCK_TEST_ONLY unregistered test download')
        if path.stat().st_size>limit:raise AssertionError('MOCK_TEST_ONLY bounded transport overflow')
        shutil.copyfile(path,destination);private(destination)
    class LocalOfficialOpener:
        def open(self,url,timeout=45):
            path=files.get(url)
            if path is None:raise AssertionError('MOCK_TEST_ONLY unknown roster URL')
            return path.open('rb')
    with patch('baseball_lab.r1.provider.download',copy_distribution),patch('baseball_lab.matchup.mlb.urllib.request.build_opener',return_value=LocalOfficialOpener()):
        yield


def main():
    # Keep this established command and its shared real-source helpers usable.
    # The unified UI has one current acceptance runner instead of stale layouts.
    from check_design_browser import main as check_current_design
    check_current_design()


if __name__=='__main__':main()
