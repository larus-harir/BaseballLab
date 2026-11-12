"""Exercise collected data through existing screens; no downloads or retraining."""
import json
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect


def main():
    errors=[];checks=[]
    with local_server(ROOT) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':950});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        for league,season in [('KBO',2026),('NPB',2025),('MLB',2000)]:
            page.locator('#league').select_option(league)
            expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            expect(page.locator('#bSeason option')).to_contain_text([str(y) for y in sorted({int(v) for v in page.locator('#bSeason option').all_text_contents()},reverse=True)])
            page.locator('#bSeason').select_option(str(season));page.locator('#pSeason').select_option(str(season))
            expect(page.locator('#bPlayer')).to_be_enabled(timeout=30000);expect(page.locator('#pPlayer')).to_be_enabled()
            with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze'),timeout=60000) as response:page.locator('#calculate').click()
            data=response.value.json();assert response.value.ok,data
            r=data['analysis'];assert r['data_mode']=='collected' and r['batter']['league']==league and r['batter']['season']==season
            assert sum(r['simulation']['counts'].values())==r['simulation']['n']
            assert len(r['model']['probabilities'])==(8 if league=='MLB' else 4)
            expect(page.locator('#headline')).not_to_contain_text('NaN')
            page.locator('#tab-principles').click();expect(page.locator('#calcBody05')).not_to_be_empty()
            page.locator('#tab-duel').click();page.locator('#observations').evaluate('e=>e.open=true')
            expect(page.locator('#observationBody')).not_to_be_empty(timeout=60000)
            expect(page.locator('#observationStatus')).not_to_contain_text('열지 못했습니다')
            if league=='NPB':expect(page.locator('#observationBody')).to_contain_text('보고된 구속')
            if league=='KBO':
                page.locator('#bSeason').select_option('2024');expect(page.locator('#bPlayer')).to_be_enabled()
                with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as auxiliary:page.locator('#calculate').click()
                assert auxiliary.value.ok
                page.locator('#observations').evaluate('e=>e.open=true');expect(page.locator('#observationBody')).to_contain_text('실제 팀별 수비 기록',timeout=30000)
            page.goto(base+data['report']);expect(page.locator('#result')).to_be_visible(timeout=20000)
            expect(page.locator('#headline')).not_to_contain_text('NaN')
            for width in (1280,390):
                page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            checks.append(f'{league} {season}: primary selection, actual run, observations, saved reopen, desktop/mobile')
            page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=20000)
        page.locator('#tab-developer').click();page.locator('#advanced').evaluate('e=>e.open=true')
        page.locator('#dataSource').select_option('legacy');page.locator('#tab-duel').click()
        expect(page.locator('#selectors')).to_be_visible(timeout=15000)
        page.locator('#bSeason').select_option('2024');page.locator('#pSeason').select_option('2024')
        expect(page.locator('#calculate')).to_be_enabled()
        with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as response:page.locator('#calculate').click()
        legacy=response.value.json();assert response.value.ok and legacy['analysis']['model']['model']=='legacy'
        page.locator('#league').select_option('NPB');expect(page.locator('#selectors')).to_be_visible(timeout=20000)
        expect(page.locator('#dataSource')).to_have_value('collected')
        checks.append('legacy calculation preserved; NPB switch does not substitute KBO')
        page.goto(base+'/simulation');expect(page.locator('#season option')).to_have_count(26,timeout=15000)
        page.goto(base+'/lab/data');expect(page.locator('#items')).to_contain_text('비공식 CSV 원본',timeout=20000)
        assert page.locator('button').filter(has_text='원본 무결성 확인').count()>=4
        assert not errors,errors
        print(json.dumps({'checks':checks+['observer 26 seasons','collected source inventory'],'javascript_errors':errors},ensure_ascii=False,indent=2))
        browser.close()

if __name__=='__main__':main()
