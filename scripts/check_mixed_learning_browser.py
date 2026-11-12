"""Real-data single/mixed league controls, neural training and saved reporting."""
import json
from time import monotonic
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect


def main():
    errors=[]
    with local_server(ROOT) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':950});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/match/team?study=half_inning')
        expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=20000)
        page.locator('#learnKBO').check();page.locator('#learnNPB').check()
        expect(page.locator('#recordSeason')).to_have_value('collected:2025')
        expect(page.locator('#mixtureHelp')).to_contain_text('33.3%')
        page.locator('#learnMLB').uncheck();expect(page.locator('#mixtureHelp')).to_contain_text('50.0%')
        page.locator('#learnMLB').check();page.locator('#weightNPB').fill('0')
        expect(page.locator('#trainBtn')).to_be_disabled();page.locator('#weightNPB').fill('1')
        page.locator('#episodes').fill('20');page.locator('#episodes').press('Tab')
        expect(page.locator('#trainBtn')).to_be_enabled()
        for width in (1280,390):
            page.set_viewport_size({'width':width,'height':950});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
        assert response.value.ok,response.value.text();job_id=response.value.json()['id'];deadline=monotonic()+180
        while monotonic()<deadline:
            job=page.request.get(base+'/api/state?project=match').json()['job']
            if job and job['id']==job_id and job['status'] in ('completed','failed','blocked','cancelled'):break
            page.wait_for_timeout(500)
        assert job['status']=='completed',job
        research=wb.outputs/job_id/'result/research.json';r=json.loads(research.read_text())
        assert r['model']['mixture']['weights']=={'MLB':1/3,'KBO':1/3,'NPB':1/3}
        assert all(s['both_parameters_changed'] and sum(s['league_exposure'].values())==20 for s in r['seeds'])
        page.goto(base+job['report']);expect(page.locator('#mixturePanel')).to_be_visible()
        expect(page.locator('#mixtureSources')).to_contain_text('KBO');expect(page.locator('#mixtureSources')).to_contain_text('NPB')
        assert page.locator('#leagueResults tbody tr').count()==3
        expect(page.locator('#mixtureAttribution')).to_contain_text('Nippon Baseball Data Repository')
        for width in (1280,390):
            page.set_viewport_size({'width':width,'height':950});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print(json.dumps({'job':job_id,'status':r['status'],'weights':r['model']['mixture']['weights'],
            'calibration_cutoff':r['model']['mixture']['calibration_cutoff_exclusive'],
            'exposure':[s['league_exposure'] for s in r['seeds']],
            'both_parameters_changed':[s['both_parameters_changed'] for s in r['seeds']],
            'javascript_errors':errors},ensure_ascii=False,indent=2));browser.close()

if __name__=='__main__':main()
