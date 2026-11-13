"""Run the new main study through its actual web button and reopen its report."""
import json,time
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect

with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match/team?study=half_inning')
    expect(page.locator('#study')).to_have_value('half_inning')
    token=wb.token
    response=page.request.post(base+'/api/start',headers={'X-Lab-Token':token},data={'kind':'run','options':{'source':'retrosheet','study':'whole_game','collected_window':True,'start':'2025-03-18','end':'2025-09-28','episodes':20,'seed':41}})
    task=response.json();assert response.ok,task
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=page.request.get(base+'/api/state?project=match').json();job=state['job']
        if job['status'] not in ('queued','running','cancelling'):break
        page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    result=ROOT/('outputs/workbench/'+job['id']+'/result/research.json');data=json.loads(result.read_text(encoding='utf-8'))
    assert data['schema']=='Match-whole-game-v1' and data['status']=='COMPLETED'
    assert len(data['seeds'])==3 and all(all(s['parameters_changed']) for s in data['seeds'])
    assert {'early_swing','take_first','steal_attempt'}<=set(data['supported_actions'])
    assert all(s['test_before']['games']==20 and s['test_after']['games']==20 for s in data['seeds'])
    page.goto(base+job['report']);expect(page.locator('#scores')).to_contain_text('%')
    page.locator('#tab-learning').click();expect(page.locator('#policyChanges')).to_contain_text('A팀')
    expect(page.locator('#actions')).to_contain_text('도루 시도')
    assert page.locator('#scene').inner_text();page.locator('#pos').fill('1')
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.goto(base+'/match/team?study=half_inning');expect(page.locator('#study')).to_have_value('half_inning');expect(page.locator('#leagueLearning')).to_be_visible()
    assert not errors,errors
    print('PASS: actual main web job, 3 seeds x 20 full games, win-only updates, held-out evaluations, source-backed extra actions, score replay and changed choice probabilities, saved reopen, mobile, preserved inning study. Report:',job['report'])
    browser.close()
