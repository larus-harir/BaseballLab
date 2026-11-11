"""Browser QA: slow real KBO matchup, nonblocking navigation and Match dates.

Only the delay is mocked. Profiles/calculation are the bundled supplied KBO
records; they remain unverified as an official predictive research source.
"""
import argparse
from pathlib import Path
import json
from threading import Event
import tempfile
import time
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server,choose
from check_strict_product_browser import submit,validate_counts,replay_identity
from playwright.sync_api import sync_playwright,expect
from baseball_lab.matchup.service import analyze as real_analyze,overview as real_overview


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--screenshots',type=Path,default=Path('/tmp/responsiveness-qa-images'));args=parser.parse_args();args.screenshots.mkdir(exist_ok=True)
    errors=[];checks=[]
    with tempfile.TemporaryDirectory(prefix='baseball-responsive-qa-') as root,local_server(root) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1366,'height':950});page.on('pageerror',lambda e:errors.append(e.stack))
        page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        page.locator('#bSeason').select_option('2024');page.locator('#pSeason').select_option('2022');choose(page,'b','김도영');choose(page,'p','안우진')
        entered=Event();release=Event()
        def delayed(*values,**options):
            entered.set()
            if not release.wait(12):raise RuntimeError('MOCK_TEST_ONLY delay was not released')
            return real_analyze(*values,**options)
        with patch('baseball_lab.matchup.service.analyze',side_effect=delayed):
            page.locator('#calculate').click();assert entered.wait(3)
            try:
                t=time.monotonic();response=page.request.get(base+'/api/state?project=match',timeout=2000)
                assert response.ok and time.monotonic()-t<2
                # Selecting a tab and leaving the page must work before analysis finishes.
                page.locator('#tab-principles').click(timeout=2000);expect(page.locator('#principles')).to_be_visible()
                page.locator('header nav a[href="/match"]').click(timeout=2000)
                expect(page.locator('h1')).to_be_visible(timeout=2000)
                conflict=page.request.post(base+'/api/start',headers={'X-Lab-Token':wb.token},data={'kind':'run','options':{'source':'retrosheet','study':'half_inning','start':'2024-03-20','end':'2024-09-30','episodes':20,'seed':1}},timeout=2000)
                assert conflict.status==400
                assert not list(wb.outputs.glob('*/result/research.json'))
            finally:release.set()
            limit=time.monotonic()+20
            while time.monotonic()<limit:
                if list(wb.outputs.glob('*/result/analysis.json')):break
                page.wait_for_timeout(100)
            else:raise AssertionError('real KBO delayed run did not finish')
        checks.append('Held actual KBO analysis: state <2s, tab+page navigation, conflicting write rejected')
        page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        page.locator('#bSeason').select_option('2024');page.locator('#pSeason').select_option('2022');choose(page,'b','김도영');choose(page,'p','안우진')
        sample=submit(page,'#calculate');validate_counts(sample,25)
        fresh=submit(page,'#rerun');assert fresh['analysis']['simulation']['seed']!=sample['analysis']['simulation']['seed']
        assert fresh['analysis']['model']['probabilities']==sample['analysis']['model']['probabilities']
        replay_identity(page,base,fresh,25)
        checks.append('Real bundled KBO: new sample, fixed probabilities, exact replay and saved reopen')
        page.goto(base+'/match');assert page.locator('a[href="/match/at-bat"]').count()==0
        page.goto(base+'/match/team?study=half_inning');expect(page.locator('#recordSeason')).to_be_visible(timeout=10000)
        page.locator('#recordSeason').select_option('2023')
        expect(page.locator('#periodStart')).to_have_value('2023-03-30');expect(page.locator('#periodEnd')).to_have_value('2023-10-01')
        before=len(list(wb.outputs.glob('*/task.json')))
        for first,last in [('2023-03-29','2023-10-01'),('2023-03-30','2023-10-02'),('2023-09-01','2023-08-01'),('2023-05-01','2023-05-02')]:
            page.locator('#periodStart').fill(first);page.locator('#periodEnd').fill(last);page.locator('#periodEnd').press('Tab')
            expect(page.locator('#periodError')).not_to_be_empty()
            assert page.locator('#trainBtn').is_disabled() or page.locator('#periodStart').evaluate('e=>!e.checkValidity()') or page.locator('#periodEnd').evaluate('e=>!e.checkValidity()')
            assert len(list(wb.outputs.glob('*/task.json')))==before
        page.locator('#recordSeason').select_option('2024');expect(page.locator('#periodStart')).to_have_value('2024-03-20');expect(page.locator('#periodEnd')).to_have_value('2024-09-30')
        expect(page.locator('#periodError')).to_be_empty()
        page.screenshot(path=str(args.screenshots/'dates-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('#periodEnd').fill('2024-10-01');page.locator('#periodEnd').press('Tab');expect(page.locator('#periodError')).not_to_be_empty()
        page.screenshot(path=str(args.screenshots/'dates-mobile-error.png'),full_page=True)
        checks.append('2023/2024 date bounds, reversed/short periods, immediate error, no task started, 390px layout')
        # Delay only the superseded MLB response while KBO finishes normally.
        with local_server(ROOT) as (realbase,_):
            stale_entered=Event();stale_release=Event()
            def delayed_catalog(*values,**options):
                if values[1]=='baseball' and options.get('role') is None:
                    stale_entered.set()
                    if not stale_release.wait(12):raise RuntimeError('MOCK_TEST_ONLY stale response release timeout')
                return real_overview(*values,**options)
            with patch('baseball_lab.matchup.service.overview',side_effect=delayed_catalog):
                page.goto(realbase+'/eramatch?league=MLB',wait_until='domcontentloaded');assert stale_entered.wait(3)
                try:
                    page.locator('#league').select_option('KBO')
                    expect(page.locator('#selectors')).to_be_visible(timeout=5000)
                    expect(page.locator('#calculate')).to_be_enabled(timeout=3000)
                    expect(page.locator('#league')).to_have_value('KBO')
                finally:stale_release.set()
                page.wait_for_timeout(500)
                expect(page.locator('#league')).to_have_value('KBO')
                assert page.locator('#bPlayer').input_value().startswith('KBO:')
        checks.append('Superseded delayed MLB catalog does not block ready KBO controls or overwrite league')
        assert not errors,errors;browser.close()
    result={'checks':checks,'page_errors':errors,'data':'real bundled supplied KBO records; delay mocked only'}
    Path('/tmp/baseball-responsiveness-browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
