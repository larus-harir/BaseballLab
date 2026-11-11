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
    parser=argparse.ArgumentParser();parser.add_argument('--skip-fresh',action='store_true')
    parser.add_argument('--screenshots',type=Path,default=ROOT/'docs/images/incremental')
    args=parser.parse_args();out=args.screenshots;out.mkdir(parents=True,exist_ok=True)
    errors=[];scenarios=[];contrast=[]
    with sync_playwright() as playwright,local_server(ROOT) as (base,workbench):
        browser=playwright.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1366,'height':1000},device_scale_factor=1,timezone_id='Asia/Seoul')
        context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
        page=context.new_page();page.goto(base+'/')
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.tagName')=='A','keyboard focus did not reach navigation'
        page.screenshot(path=str(out/'home-desktop.png'),full_page=True)
        page.locator('a[href="/baseball"]').last.click()
        expect(page.locator('#selectors')).to_be_visible(timeout=120000)
        expect(page.locator('#model')).to_be_hidden();expect(page.locator('#seed')).to_be_hidden()
        run_matchup(page,'Aaron Judge','Tarik Skubal')
        contrast=[text_contrast(page,selector) for selector in ('body','#calculate','.fact small')]
        page.screenshot(path=str(out/'baseball-2024.png'),full_page=True)
        position=page.locator('#replayPosition').inner_text()
        page.locator('#next').click();expect(page.locator('#replayPosition')).not_to_have_text(position)
        page.locator('#previous').click();expect(page.locator('#replayPosition')).to_have_text(position)
        page.locator('#play').click();expect(page.locator('#replayPosition')).not_to_have_text(position,timeout=5000)
        page.locator('#play').click()
        page.locator('#replayIndex').focus();page.keyboard.press('Control+A');page.keyboard.type('3');page.keyboard.press('Tab')
        expect(page.locator('#replayPosition')).to_contain_text('3 / 25')
        page.locator('#advanced > summary').click();expect(page.locator('#model')).to_be_visible();expect(page.locator('#seed')).to_be_visible()
        page.locator('#advanced > summary').click()
        details=page.locator('#context details').first
        details.locator('summary').click();page.locator('#explanation').screenshot(path=str(out/'calculation-explanation.png'))
        report=page.locator('#reportLink a').get_attribute('href')
        page.goto(base+report);expect(page.locator('#setup')).to_be_hidden();expect(page.locator('#resultTitle')).to_contain_text('Aaron Judge')
        scenarios.append('MLB2024 default matchup, hidden advanced settings, replay, explanation, saved report')

        page.goto(base+'/baseball');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        page.locator('#bSeason').select_option('2023')
        expect(page.locator('#pSeason')).to_have_value('2023',timeout=30000)
        expect(page.locator('#selectors')).to_be_visible(timeout=120000)
        run_matchup(page,'Mike Trout','Gerrit Cole')
        expect(page.locator('#resultTitle')).to_contain_text('2023')
        expect(page.locator('#context')).to_contain_text('2024년 검증에서 고른 보정 강도 300')
        page.locator('#context').get_by_text('이 모델의 실제 예측 검사',exact=True).click()
        expect(page.locator('#context')).to_contain_text('미래 예측이 아닌 회고 검사입니다.')
        page.locator('#context').get_by_text('이 모델의 실제 예측 검사',exact=True).click()
        page.screenshot(path=str(out/'baseball-2023.png'),full_page=True)
        scenarios.append('MLB2023 actual-season selection and matchup')

        original=ROOT/'data/local/catalog/kbo-assignment/catalog.json';before=original.read_bytes()
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY cached KBO needs no network')):
            page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            expect(page.locator('#importControls')).to_be_hidden()
            page.locator('#bSeason').select_option('1982');page.locator('#pSeason').select_option('2024')
            run_matchup(page,'백인천','원태인')
            page.screenshot(path=str(out/'eramatch.png'),full_page=True)
        assert original.read_bytes()==before,'connected assignment catalog was rewritten'
        page.locator('#bQuery').fill('없는선수-MOCK_TEST_ONLY')
        expect(page.locator('#bPlayer')).to_contain_text('없',timeout=20000)
        if page.locator('#calculate').is_enabled():
            page.locator('#calculate').click();expect(page.locator('#formError')).not_to_be_empty()
            expect(page.locator('#formError')).to_be_focused()
        scenarios.append('Cached EraMatch, original bytes unchanged, empty search and actionable error')

        page.goto(base+'/match');page.locator('a[href="/match/team"]').first.click()
        expect(page.locator('.research-help')).to_be_visible()
        expect(page.locator('#runs details > summary')).to_be_visible(timeout=20000)
        page.locator('#runs details > summary').click()
        links=page.locator('#runs .run').filter(has_text='AI 학습').get_by_role('link',name='결과 보기')
        expect(links.first).to_be_visible(timeout=20000)
        with page.expect_popup() as popup:links.first.click()
        research=popup.value;expect(research.locator('#verdict')).not_to_be_empty()
        slider=research.locator('#evolutionSlider');slider.fill(slider.get_attribute('max'))
        research.locator('#tab-watch').click();expect(research.locator('#bases svg')).to_be_visible()
        if research.locator('#next').is_enabled():research.locator('#next').click()
        research.locator('#tab-overview').click();research.screenshot(path=str(out/'match-preserved.png'),full_page=True);research.close()
        page.goto(base+'/simulation');expect(page.locator('body')).to_contain_text('장면 살펴보기')
        scenarios.append('Existing Match report, learning stage slider, replay and independent scene route')

        mobile=browser.new_page(viewport={'width':390,'height':844})
        mobile.on('pageerror',lambda error:errors.append(str(error)))
        mobile.goto(base+'/eramatch');expect(mobile.locator('#selectors')).to_be_visible(timeout=30000)
        mobile.locator('#bSeason').select_option('1982');mobile.locator('#pSeason').select_option('2024')
        run_matchup(mobile,'백인천','원태인')
        mobile.locator('#next').click();expect(mobile.locator('#replayPosition')).to_contain_text('2 / 25')
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'),'mobile horizontal overflow'
        mobile.screenshot(path=str(out/'mobile-390.png'),full_page=True)
        mobile.close();scenarios.append('390px mobile matchup and replay without horizontal overflow')

        if not args.skip_fresh:
            with tempfile.TemporaryDirectory(prefix='baseball-real-install-') as freshroot,local_server(freshroot) as (freshbase,fresh):
                with patch('baseball_lab.data.catalog.DatasetCatalog.ensure',side_effect=OSError('MOCK_TEST_ONLY network unavailable')):
                    page.goto(freshbase+'/baseball');expect(page.locator('#prepare')).to_be_visible(timeout=30000)
                    expect(page.locator('#selectors')).to_be_hidden()
                    assert not list(Path(freshroot).glob('outputs/workbench/*/result/analysis.json'))
                    page.screenshot(path=str(out/'network-retry.png'),full_page=True)
                with verified_distribution_transport(ROOT):
                    page.locator('#prepare').click();expect(page.locator('#selectors')).to_be_visible(timeout=120000)
                    run_matchup(page,'Aaron Judge','Tarik Skubal')
                    page.screenshot(path=str(out/'fresh-install-result.png'),full_page=True)
                assert fresh.job is None or fresh.job['status']=='completed'
                assert (Path(freshroot)/'data/local/catalog/mlb-2024/catalog.json').is_file()
            with tempfile.TemporaryDirectory(prefix='baseball-empty-assignment-') as empty,local_server(empty) as (emptybase,_):
                page.goto(emptybase+'/eramatch');expect(page.locator('#importControls')).to_be_visible(timeout=20000)
                expect(page.locator('#selectors')).to_be_hidden()
                page.locator('#archive').set_input_files({'name':'MOCK_TEST_ONLY.zip','mimeType':'application/zip','buffer':b'not a recognized assignment'})
                page.locator('#import').click();expect(page.locator('#formError')).to_contain_text('ZIP',timeout=20000)
                assert not list(Path(empty).glob('outputs/workbench/*/result/analysis.json'))
            scenarios.append('Fresh install provider failure/retry and actual-distribution normalization; missing assignment and bad ZIP')
        browser.close()
    report={'browser_errors':errors,'scenarios':scenarios,'contrast_samples':contrast,'viewport_desktop':1366,'viewport_mobile':390,
            'fresh_install_transport':'skipped' if args.skip_fresh else 'verified local official distribution transport; no invented player data',
            'screenshots':[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name for path in out.glob('*.png')]}
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    Path('/tmp/baseball-incremental-browser-results.json').write_text(encoded)
    suffix='focused' if args.skip_fresh else 'full'
    Path('/tmp/baseball-incremental-browser-'+suffix+'-results.json').write_text(encoded)
    print(json.dumps(report,ensure_ascii=False,indent=2));assert not errors


if __name__=='__main__':main()
