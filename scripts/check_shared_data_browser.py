"""Real collected-data UI checks. Creates new reports; no source rewrites."""
import json
from pathlib import Path
from time import monotonic
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect


def main():
    errors=[]
    with local_server(ROOT) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':950});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/eramatch?mode=common')
        expect(page.locator('#run')).to_be_enabled(timeout=30000)
        page.locator('#bSource').select_option('KBO:2025');page.locator('#pSource').select_option('MLB:2025')
        expect(page.locator('#run')).to_be_enabled(timeout=15000)
        page.locator('#reference').select_option('MLB:2025');page.get_by_text('보정·재현 설정',exact=True).click();page.locator('#seed').fill('41')
        with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as response:page.locator('#run').click()
        d=response.value.json();assert response.value.ok,d
        r=d['analysis'];assert r['batter']['league']=='KBO' and r['pitcher']['league']=='MLB'
        assert set(r['model']['probabilities'])=={'strikeout','walk','hit','other'}
        expect(page.locator('#resultTitle')).to_contain_text('MLB')
        page.locator('#calculation').locator('..').evaluate('e=>e.open=true')
        expect(page.locator('#calculation')).to_contain_text('검증된 리그 실력 환산이 아닙니다')
        page.goto(base+d['report']);expect(page.locator('#resultTitle')).to_contain_text('KBO')
        for width in (1280,390):
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.goto(base+'/match/team?study=half_inning')
        expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=15000)
        expect(page.locator('#periodStart')).to_have_value('2021-04-01')
        page.locator('#recordSeason').select_option('all');expect(page.locator('#periodStart')).to_have_value('2015-04-05')
        page.locator('#recordSeason').select_option('collected:2025');expect(page.locator('#periodStart')).to_have_value('2025-03-18')
        page.locator('#periodEnd').fill('2025-09-29');page.locator('#periodEnd').press('Tab')
        expect(page.locator('#trainBtn')).to_be_disabled();expect(page.locator('#periodError')).not_to_be_empty()
        # Submit the same validated two-season path from the actual web controls.
        page.locator('#recordSeason').select_option('all')
        page.locator('#periodStart').fill('2024-03-20');page.locator('#periodEnd').fill('2025-09-28')
        page.locator('#episodes').fill('20');page.locator('#episodes').press('Tab')
        expect(page.locator('#trainBtn')).to_be_enabled()
        with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
        assert response.value.ok,response.value.text()
        deadline=monotonic()+180
        while monotonic()<deadline:
            job=page.request.get(base+'/api/state?project=match').json()['job']
            if job and job['status'] in ('completed','failed','blocked','cancelled'):break
            page.wait_for_timeout(500)
        assert job['status']=='completed',job
        evidence=wb.outputs/job['id']/'result/research.json';result=json.loads(evidence.read_text())
        assert result['dataset']['selected_seasons']==[2024,2025]
        assert all(r['both_parameters_changed'] for r in result['seeds'])
        assert not errors,errors
        print(json.dumps({'cross_league_report':d['report'],'web_learning_job':job['id'],
            'seasons':result['dataset']['selected_seasons'],'source_segments':result['dataset']['used_segments'],
            'checks':['four shared events','real KBO/MLB reference with NPB use gate','saved report reopen','desktop/mobile width','all/recent/season dates','out-of-range blocked','web neural learning completed'],
            'javascript_errors':errors},ensure_ascii=False,indent=2))
        browser.close()

if __name__=='__main__':main()
