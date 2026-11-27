"""Pruned paths, real packaged sources, transport recovery and safe fixture deletion."""
from pathlib import Path
import tempfile
from check_incremental_browser import local_server
from playwright.sync_api import sync_playwright,expect

with tempfile.TemporaryDirectory(prefix='baseball-pruned-ui-') as folder:
    root=Path(folder);target=root/'outputs/workbench/MOCK_TEST_ONLY';target.mkdir(parents=True)
    (target/'mock.log').write_text('MOCK_TEST_ONLY disposable UI deletion fixture')
    with local_server(root) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/pitch-corpus',lambda route:route.fulfill(status=503,json={'error':'MOCK_TEST_ONLY 기록 연결 실패'}))
        page.goto(base+'/match/team');expect(page.locator('#catalogRetry')).to_be_visible();expect(page.locator('#trainBtn')).to_be_disabled()
        page.unroute('**/api/pitch-corpus');page.locator('#catalogRetry').click();expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
        assert page.locator('#periodStart,#uploadForm,#leagueLearning').count()==0
        page.locator('#trainingOptions > summary').click()
        for league in ('MLB','KBO','NPB'):page.locator('#corpus'+league).uncheck()
        expect(page.locator('#trainBtn')).to_be_disabled();expect(page.locator('#formError')).to_contain_text('리그')
        page.locator('#corpusMLB').check();expect(page.locator('#trainBtn')).to_be_enabled()
        page.goto(base+'/eramatch?league=MLB');expect(page.locator('#calculate')).to_be_enabled(timeout=30000);page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible()
        expect(page.locator('#plateDetails')).not_to_have_attribute('open','');expect(page.locator('#rerun')).to_be_visible()
        page.locator('#eventChart button').first.click();expect(page.locator('#plateDetails')).to_have_attribute('open','');expect(page.locator('#replayOutcome')).to_be_visible()
        page.locator('#plateDetails > summary').click();expect(page.locator('#rerun')).to_be_visible()
        page.goto(base+'/eramatch?mode=common');expect(page.locator('#run')).to_be_enabled(timeout=30000)
        assert not page.locator('#usageNotice').is_visible()
        page.goto(base+'/simulation');page.locator('#source').select_option('observed');expect(page.locator('#styleSettings')).to_be_hidden()
        page.locator('#source').select_option('model');expect(page.locator('#styleSettings')).to_be_visible();assert '2024' not in page.locator('#message').inner_text()
        page.goto(base+'/lab/data');page.get_by_text('사용 가능한 학습 기록과 출처',exact=True).click()
        expect(page.locator('#sourceCoverage')).to_contain_text('KBO 2016~2026',timeout=30000)
        expect(page.locator('#sourceCoverage')).to_contain_text('NPB 2019~2026')
        inventory=page.request.get(base+'/api/storage').json();item=next(i for i in inventory['items'] if i['id']=='run:MOCK_TEST_ONLY')
        saved=page.locator('#items > details');saved.locator('summary').first.click()
        card=page.locator('#items section').filter(has=page.get_by_role('heading',name=item['label'],exact=True))
        card.get_by_role('button',name='삭제 검토',exact=True).click();expect(page.locator('#confirmDelete')).to_be_disabled()
        page.locator('#cancelDelete').click();assert target.exists()
        card.get_by_role('button',name='삭제 검토',exact=True).click();page.locator('#confirmLoss').check();page.locator('#confirmDelete').click()
        expect(page.locator('#deleteDialog')).not_to_be_visible();assert not target.exists()
        page.set_viewport_size({'width':390,'height':844})
        for path in ('/','/match','/match/team','/eramatch','/eramatch?mode=common','/simulation','/lab/data'):
            page.goto(base+path);page.wait_for_timeout(200);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),path
        assert not errors,errors;browser.close()
print('PASS: modern learning recovery/validation; compact match results and replay; common comparison; observation controls; actual source coverage; two-step deletion on disposable fixture only; all main pages mobile.')
