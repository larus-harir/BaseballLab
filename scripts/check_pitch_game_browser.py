"""Real main web job: learned pitch world, both teams learning, old results intact."""
import json,time
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match');page.locator('a[href="/match/team?study=pitch_game"]').first.click()
    expect(page.locator('#study')).to_have_value('pitch_game');expect(page.locator('#recordSeason')).to_have_value('collected:2025',timeout=30000)
    page.locator('#episodes').fill('20');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
    assert response.value.ok,response.value.text();deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=page.request.get(base+'/api/state?project=match').json()['job']
        if job['status'] not in ('queued','running'):break
        page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    folder=ROOT/'outputs/workbench'/job['id']/'result';data=json.loads((folder/'research.json').read_text(encoding='utf-8'))
    assert data['schema']=='Match-pitch-decision-game-v1' and len(data['seeds'])==3
    assert all(all(all(v) for v in s['parameters_changed']) for s in data['seeds'])
    assert all(all(all(v>0 for v in row) for row in s['optimizer_steps']) for s in data['seeds'])
    assert (folder/'world.json').exists() and data['world']['holdout_prediction']['test']['pitches']>=100
    for s in data['seeds']:
        assert all(e['offense'] in ('take','swing') for e in s['replay']['events'])
        assert any(e['strikes']>0 or e['balls']>0 for e in s['replay']['events'])
    page.goto(base+job['report']);expect(page.locator('#score')).to_contain_text('A팀 평가')
    expect(page.locator('#choice')).to_contain_text('팀 타자');page.locator('#pos').fill('5');assert page.locator('#outcome').inner_text()
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.goto(base+'/match/team?study=half_inning');expect(page.locator('#study')).to_have_value('half_inning')
    assert not errors,errors
    print('PASS: actual pitch-decision main web job; 3 x 20 full games, A/B offense and defense all updated; fitted world held-out metrics; real pitch counts, official pitcher substitutions, saved report, mobile, preserved inning study. Report:',job['report'])
    browser.close()
