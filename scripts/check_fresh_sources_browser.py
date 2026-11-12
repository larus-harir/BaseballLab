"""Fresh-install checks using verified real cached originals as a test transport.

No network or fabricated players: copies downloaded bytes into an isolated root.
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_player_sources import prepare_sources
from baseball_lab.data.training_window import sources


def main():
    mlb_source=sources(ROOT)[2022]
    mlb_zip=ROOT/next(f['path'] for f in mlb_source['files'] if f['path'].endswith('.zip'))
    manifests=list((ROOT/'data/local/community/npb-armstjc').glob('*/manifest.json'))
    npb=next(json.loads(p.read_text()) for p in manifests if json.loads(p.read_text()).get('summary',{}).get('failures')==0)
    npb_urls={f['url']:ROOT/f['path'] for f in npb['files']+npb['evidence']}
    from collect_npb_community import API,REVISION
    npb_urls[API+f'/git/trees/{REVISION}?recursive=1']=(ROOT/npb['evidence'][0]['path']).parent/'tree.json'
    def transport(url,path,limit=0):
        if url.endswith('plays.html'):
            path.write_text('free to make any desired use copyrighted by Retrosheet '+mlb_source['source_url'])
        else:
            assert url==mlb_source['source_url'],url
            shutil.copyfile(mlb_zip,path)
    with tempfile.TemporaryDirectory(prefix='baseball-fresh-') as folder:
        root=Path(folder)
        with local_server(root) as (base,wb),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/match/team')
            expect(page.locator('#recordSeason option[value="collected:2000"]')).to_have_count(1)
            page.locator('#recordSeason').select_option('collected:2022')
            expect(page.locator('#trainBtn')).to_be_enabled()
            # No-data NPB must settle, retain a real season and offer an enabled button.
            page.goto(base+'/eramatch?league=NPB')
            expect(page.locator('#prepareControls')).to_be_visible()
            expect(page.locator('#bSeason')).to_have_value('2025')
            expect(page.locator('#prepare')).to_be_enabled()
            requests=[]
            def fail_prepare(route):
                requests.append(route.request.post_data_json)
                route.fulfill(status=400,content_type='application/json',body=json.dumps({'error':'MOCK_TEST_ONLY connection unavailable'}))
            page.route('**/api/matchup/prepare',fail_prepare)
            page.locator('#prepare').click()
            expect(page.locator('#formError')).to_contain_text('connection unavailable')
            expect(page.locator('#prepare')).to_be_enabled()
            assert requests==[{'project':'npb','season':2025}]
            page.unroute('**/api/matchup/prepare')
            # Click the actual training button: download first, submit learning second.
            learning=[]
            def capture_learning(route):
                learning.append(route.request.post_data_json)
                route.fulfill(content_type='application/json',body='{"id":"MOCK_TEST_ONLY learning submission"}')
            page.route('**/api/start',capture_learning)
            def prepare_worker(job_id,command,output):
                assert command[-6:]==['--league','MLB','--start','2022','--end','2022']
                try:
                    prepare_sources(root,'MLB',2022,2022)
                    with wb.lock:
                        wb._cache=(0,None);wb.job.update(status='completed',message='MOCK_TEST_ONLY actual source preparation completed')
                except Exception as error:
                    with wb.lock:wb.job.update(status='failed',message=str(error))
            page.goto(base+'/match/team')
            page.locator('#recordSeason').select_option('collected:2022')
            with patch('collect_league_seasons.fetch',side_effect=transport),patch.object(wb,'_worker',side_effect=prepare_worker):
                page.locator('#trainBtn').click()
                expect(page.locator('#recordSeason option:checked')).to_contain_text('준비됨',timeout=120000)
                expect(page.locator('#trainBtn')).to_be_enabled(timeout=120000)
            assert len(learning)==1,learning
            options=learning[0]['options']
            assert options['collected_window'] and options['start'].startswith('2022-')
            assert options['start'][5:]!='01-01' and options['end'][5:]!='12-31'
            page.unroute('**/api/start')
            # Cached preparation must work with all network calls disabled.
            with patch('collect_league_seasons.fetch',side_effect=AssertionError('offline cache attempted network')):
                prepare_sources(root,'MLB',2022,2022)
            with patch('collect_npb_community.fetch',side_effect=lambda url:npb_urls[url].read_bytes()):
                prepare_sources(root,'NPB')
            wb._cache=(0,None)
            page.goto(base+'/eramatch?league=NPB')
            expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            expect(page.locator('#calculate')).to_be_enabled()
            page.locator('#calculate').click()
            expect(page.locator('#result')).to_be_visible(timeout=30000)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.goto(base+'/eramatch?league=MLB')
            # Fresh MLB 2022 remains default even though 2025 is downloadable.
            expect(page.locator('#bSeason')).to_have_value('2022',timeout=30000)
            expect(page.locator('#calculate')).to_be_enabled()
            page.goto(base+'/match/team')
            page.locator('#recordSeason').select_option('collected:2022')
            expect(page.locator('#recordSeason option:checked')).to_contain_text('준비됨')
            assert not errors,errors
            browser.close()
    print('PASS: fresh 26 MLB seasons; NPB no-data/button/error/retry; actual source preparation, cache/offline, NPB matchup and mobile; originals unchanged.')


if __name__=='__main__':main()
