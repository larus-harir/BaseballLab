"""Fresh offline UI: official names and adaptive observed HR/extra-base outcomes."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from check_incremental_browser import local_server
from playwright.sync_api import sync_playwright,expect


def search(page,side,text):
    page.locator('#'+side+'Query').fill(text)
    expect(page.locator('#'+side+'Player')).to_contain_text(text,timeout=30000)
    expect(page.locator('#calculate')).to_be_enabled(timeout=30000)


def run(page,selector='#calculate'):
    with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as response:page.locator(selector).click()
    value=response.value.json();assert response.value.ok,value
    expect(page.locator('#result')).to_be_visible()
    return value


def main():
    with tempfile.TemporaryDirectory(prefix='baseball-name-events-') as folder,patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY offline')),local_server(Path(folder)) as (base,wb),sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/eramatch?league=MLB')
        expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
        search(page,'b','Ohtani');search(page,'p','Skenes')
        expect(page.locator('#bPlayer')).not_to_contain_text('ohtas001')
        expect(page.locator('#bInfo')).to_contain_text('홈런')
        mlb=run(page);assert mlb['analysis']['batter']['name']=='Shohei Ohtani'
        for league,batter,pitcher,year in [('KBO','김도영','양현종',2024),('NPB','近本','伊藤',2025)]:
            page.locator('#league').select_option(league)
            expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
            page.locator('#bSeason').select_option(str(year));page.locator('#pSeason').select_option(str(year))
            search(page,'b',batter);search(page,'p',pitcher)
            result=run(page);r=result['analysis'];q=r['model']['probabilities']
            assert 'home_run' in q and 'hit_other' in q and 'double' not in q and 'triple' not in q
            assert sum(r['simulation']['counts'].values())==r['simulation']['n']
            assert r['batter']['counts']['HR'] is not None and r['pitcher']['counts']['HR'] is not None
            assert r['batter']['counts']['2B'] is not None and r['pitcher']['counts']['2B'] is None
            expect(page.locator('#facts')).to_contain_text('이번 홈런 수')
            expect(page.locator('#eventChart')).to_contain_text('홈런 외 안타')
            expect(page.locator('#eventChart')).to_contain_text('홈런')
            again=run(page,'#reproduce')['analysis']
            assert again['run_id']==r['run_id'] and again['simulation']['events']==r['simulation']['events']
            page.goto(base+result['report']);expect(page.locator('#facts')).to_contain_text('이번 홈런 수')
            page.goto(base+'/eramatch?league='+league)
        page.goto(base+'/eramatch?mode=common')
        expect(page.locator('#run')).to_be_enabled(timeout=30000)
        page.locator('#bSource').select_option('MLB:2025');page.locator('#pSource').select_option('NPB:2025');page.locator('#reference').select_option('MLB:2025')
        page.locator('#bQuery').fill('Ohtani');expect(page.locator('#bPlayer')).to_contain_text('Shohei Ohtani',timeout=30000)
        expect(page.locator('#run')).to_be_enabled()
        with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as response:page.locator('#run').click()
        value=response.value.json();assert response.value.ok,value
        assert 'home_run' in value['analysis']['simulation']['counts']
        expect(page.locator('#numbers')).to_contain_text('홈런')
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        assert not list((Path(folder)/'data').rglob('*.csv')) and not list((Path(folder)/'data').rglob('*.zip'))
        browser.close()
    print('PASS: offline official MLB names; real MLB/KBO/NPB HR and source stats; adaptive cross-league table; exact replay and saved reopen; mobile; no raw downloads or JS errors.')


if __name__=='__main__':main()
