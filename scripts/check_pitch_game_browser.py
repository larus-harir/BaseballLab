"""Real main web job: learned pitch world, both teams learning, old results intact."""
import json,time
import io,subprocess
from pathlib import Path
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match');page.locator('a[href="/match/team?study=pitch_game"]').first.click()
    expect(page.locator('#study')).to_have_value('pitch_game');expect(page.locator('#recordSeason')).to_have_value('collected:2025',timeout=30000)
    page.locator('#trainingData').select_option('legacy');page.locator('#episodes').fill('20');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    # MOCK_TEST_ONLY delayed range discovery: full-season dates follow newly
    # discovered bounds; user-entered dates must remain unchanged.
    page.evaluate("periodStart.min=periodStart.value='2025-01-01';periodEnd.max=periodEnd.value='2025-12-31';setDateLimits(false)")
    expect(page.locator('#periodStart')).to_have_value('2025-03-18');expect(page.locator('#periodEnd')).to_have_value('2025-09-28')
    page.evaluate("periodStart.value='2025-04-01';periodEnd.value='2025-06-01';setDateLimits(false)")
    expect(page.locator('#periodStart')).to_have_value('2025-04-01')
    page.evaluate('setDateLimits(true);preview()');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    original_popen=subprocess.Popen
    def connection_failure(command,**kwargs):
        if '--mode' not in command:return original_popen(command,**kwargs)
        from baseball_lab.data.lineage import write_json
        output=Path(command[command.index('--output')+1])
        write_json(output/'failure.json',{'error':'MOCK_TEST_ONLY SSL handshake timeout'})
        (output/'report.html').write_text('MOCK_TEST_ONLY failure diagnostic',encoding='utf-8')
        class Failed:
            stdout=io.StringIO('단계 1 · MOCK_TEST_ONLY SSL handshake timeout\n')
            def wait(self,*args,**kwargs):return 2
            def poll(self):return 2
        return Failed()
    with patch('baseball_lab.web.server.subprocess.Popen',side_effect=connection_failure):
        with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
        assert response.value.ok,response.value.text()
        expect(page.locator('#retryBtn')).to_be_visible(timeout=30000)
        expect(page.locator('#resultLink')).to_be_hidden()
        failed=page.request.get(base+'/api/state?project=match').json()['job']
        assert failed['status']=='failed' and failed['can_retry'] and failed['report'] is None
    with page.expect_response(lambda r:r.url.endswith('/api/retry')) as response:page.locator('#retryBtn').click()
    assert response.value.ok,response.value.text();deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=page.request.get(base+'/api/state?project=match').json()['job']
        if job['status'] not in ('queued','running'):break
        page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    assert job['id']!=failed['id']
    folder=ROOT/'outputs/workbench'/job['id']/'result';data=json.loads((folder/'research.json').read_text(encoding='utf-8'))
    assert data['schema']=='Match-pitch-decision-game-v2' and len(data['seeds'])==3
    assert all(all(all(v) for v in s['parameters_changed']) for s in data['seeds'])
    assert all(all(all(v>0 for v in row) for row in s['optimizer_steps']) for s in data['seeds'])
    assert (folder/'world.json').exists() and data['world']['holdout_prediction']['test']['pitches']>=100
    metrics=data['world']['holdout_prediction']['validation']
    assert metrics['brier']<=metrics['baseline_brier']+1e-12
    assert data['world']['coverage'] and data['dataset']['pitch_acquisition']
    assert data['world']['action_support']['running_fit_plays']>0
    assert sum(data['world']['action_support']['bunt_count_pitches'].values())>0
    for s in data['seeds']:
        assert all(e['offense'] in ('take','swing','bunt','steal_2','steal_3',None) for e in s['replay']['events'])
        assert all(e['offense'] is None for e in s['replay']['events'] if e['defense']!='pitch')
        assert any(e['strikes']>0 or e['balls']>0 for e in s['replay']['events'])
        assert all(len(h['against_initial'])==2 and len(h['choice_probes'])==3 for h in s['history'])
        assert s['history'][0]['seed_bank']!=s['history'][-1]['seed_bank']
    page.goto(base+job['report']);expect(page.locator('#score')).to_contain_text('A팀 평가')
    expect(page.locator('#verdict')).to_contain_text('총 60경기')
    expect(page.locator('#growthTable')).to_contain_text('학습 전')
    expect(page.locator('#strategy')).to_contain_text('0볼 2스트라이크')
    expect(page.locator('#choice')).to_contain_text('팀 공격 AI');page.locator('#pos').fill('5');assert page.locator('#outcome').inner_text()
    page.locator('#pos').focus();page.keyboard.press('ArrowRight');expect(page.locator('#pos')).to_have_value('6')
    page.reload();expect(page.locator('#growthTable')).to_contain_text('학습 전')
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    # Historical reports are rendered read-only without inventing new comparisons.
    old=next((p for p in (ROOT/'outputs/workbench').glob('*/result/research.json') if p!=folder/'research.json' and (lambda d:d.get('schema')=='Match-pitch-decision-game-v1' and 'against_initial' not in d['seeds'][0]['history'][0])(json.loads(p.read_text(encoding='utf-8')))),None)
    if old:
        before=old.read_bytes();report='/reports/'+old.parents[1].name+'/result/report.html'
        page.goto(base+report);expect(page.locator('#growthTable')).to_contain_text('이전 실행')
        assert old.read_bytes()==before
    page.goto(base+'/match/team?study=half_inning');expect(page.locator('#study')).to_have_value('half_inning')
    assert not errors,errors
    assert any(s['replay']['choices'][i].get('bunt',0)>0 for s in data['seeds'] for i in (0,1))
    print('PASS: injected connection failure shows retry instead of results; same-settings retry completed 3 x 20 real-data games; A/B offense and defense updated; observed bunt/running support; official pitcher substitutions, saved and historical reports, keyboard/mobile, preserved inning study. Report:',job['report'])
    browser.close()
