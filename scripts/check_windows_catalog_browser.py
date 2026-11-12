"""Windows CRLF package regression through the real fresh-install web UI."""
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
from baseball_lab.data import compact


def main():
    with tempfile.TemporaryDirectory(prefix='baseball-crlf-') as folder:
        root=Path(folder);package=root/'package';resource=package/'resources';resource.mkdir(parents=True)
        originals=ROOT/'src/baseball_lab/data/resources'
        (resource/'index.json').write_bytes((originals/'index.json').read_bytes().replace(b'\n',b'\r\n'))
        shutil.copyfile(originals/'players.json.gz',resource/'players.json.gz')
        compact.index.cache_clear();compact.players.cache_clear()
        try:
            with patch.object(compact,'files',return_value=package),patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY offline')),local_server(root) as (base,wb),sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/eramatch?league=MLB')
                expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
                page.locator('#bSeason').focus();page.keyboard.press('Tab');expect(page.locator('#pSeason')).to_be_focused()
                page.locator('#bSeason').select_option('2015');page.locator('#pSeason').select_option('2025')
                expect(page.locator('#calculate')).to_be_enabled()
                with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as response:page.locator('#calculate').click()
                result=response.value.json();assert response.value.ok,result
                assert result['analysis']['batter']['season']==2015 and result['analysis']['pitcher']['season']==2025
                expect(page.locator('#result')).to_be_visible()
                report=result['report']
                page.locator('#league').select_option('NPB')
                expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
                expect(page.locator('#bSeason')).to_have_value('2025')
                page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible()
                page.goto(base+report);assert page.locator('body').inner_text()
                page.goto(base+'/match/team?study=half_inning')
                expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=30000)
                options=page.locator('#recordSeason option').evaluate_all('items=>items.map(e=>({value:e.value,label:e.textContent}))')
                expected=['recent:5','all']+['collected:'+str(y) for y in range(2025,1999,-1)]
                assert [o['value'] for o in options]==expected,options
                assert len({o['label'] for o in options})==28
                assert all(not any(s in o['label'] for s in ('인터넷','다운로드','원본','읽기')) for o in options)
                page.locator('#recordSeason').select_option('collected:2002')
                with page.expect_response(lambda r:'/api/state?' in r.url):pass
                expect(page.locator('#recordSeason')).to_have_value('collected:2002')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                assert not list((root/'data').rglob('*.csv')) and not list((root/'data').rglob('*.zip'))
                browser.close()
        finally:
            compact.index.cache_clear();compact.players.cache_clear()
    print('PASS: CRLF checkout, offline MLB 2015 vs 2025 and NPB, saved report, sorted unique seasons, preserved selection, mobile; no JS errors or raw downloads.')


if __name__=='__main__':main()
