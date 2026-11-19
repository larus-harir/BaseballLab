"""Real packaged multi-league learning: no raw acquisition, filters and reports."""
import json,time
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect

with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match/team?study=pitch_game')
    expect(page.locator('#trainingData')).to_have_value('corpus')
    expect(page.locator('#corpusSummary')).to_contain_text('MLB 2000~2025',timeout=30000)
    expect(page.locator('#corpusSummary')).to_contain_text('KBO 2016~2025')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2026')
    assert page.locator('#corpusYear option').count()==28
    expect(page.locator('#legacyScope')).to_be_hidden()
    expect(page.locator('#sourcePreview')).to_contain_text('연도별 학습 표본 확인')
    page.locator('#trainingData').select_option('legacy');expect(page.locator('#legacyScope')).to_be_visible()
    page.locator('#study').select_option('half_inning');expect(page.locator('#trainingDataWrap')).to_be_hidden()
    page.locator('#study').select_option('pitch_game');page.locator('#trainingData').select_option('corpus')
    page.locator('#corpusYear').select_option('2019')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2019')
    page.locator('#episodes').fill('20');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
    assert response.value.ok,response.value.text()
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=page.request.get(base+'/api/state?project=match').json()['job']
        if job['status'] not in ('queued','running'):break
        page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    data=json.loads((ROOT/'outputs/workbench'/job['id']/'result/research.json').read_text(encoding='utf-8'))
    assert data['schema']=='Match-pitch-decision-game-v4' and len(data['seeds'])==3
    assert {c['league'] for c in data['world']['cohorts']}=={'MLB','KBO','NPB'}
    assert {c['season'] for c in data['world']['cohorts']}=={2019}
    assert all(len(s['training_environments'])==3 for s in data['seeds'])
    assert all(all(all(v) for v in s['parameters_changed']) for s in data['seeds'])
    assert all(any(k.startswith('pitch:') for counts in s['training_choices'] for k in counts) for s in data['seeds'])
    for seed in data['seeds']:
        assert len(seed['history'])==5
        assert 'A_wins' not in seed['history'][-1]
        assert seed['training_outcomes']['A']+seed['training_outcomes']['B']==20
        for i,t in enumerate(seed['history'][-1]['strategy']):
            observed={**t['offense'],**t['defense']}
            assert observed==seed['training_choices'][i]
            assert t['targets'] and t['batted_area']
    assert data['strategy_analysis']['preferences']
    page.goto(base+job['report']);expect(page.locator('#teamCards')).to_contain_text('타격 방향 목표')
    expect(page.locator('#preferences')).to_contain_text('학습 전')
    assert not page.locator('#verdict').count()
    assert page.locator('#context option').count()>0
    assert 'undefined' not in page.locator('#summary').inner_text()
    page.locator('#tab-growth').focus();page.keyboard.press('Enter')
    expect(page.locator('#growth')).to_be_visible()
    page.locator('#growthRole').select_option('defense')
    expect(page.locator('#growthCharts')).to_contain_text('투구·수비 선택')
    page.keyboard.press('Tab')
    page.locator('#tab-scene').click();expect(page.locator('#batChoice')).to_contain_text('시도')
    assert page.locator('#sceneField svg').count()==1
    position=int(page.locator('#position').input_value());page.locator('#position').focus();page.keyboard.press('ArrowRight')
    expect(page.locator('#position')).to_have_value(str(position+1))
    page.locator('#tab-scene').focus();page.keyboard.press('ArrowRight')
    expect(page.locator('#evidence')).to_be_visible();expect(page.locator('#coverage')).to_contain_text('KBO 2019')
    page.reload();expect(page.locator('#summary')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print('PASS: 3league real training; no ranking tournaments; all executed actions counted; directional targets and outcomes; preference/growth tabs; pitch zone/field sectors; keyboard/mobile/saved reopen. Report:',job['report'])
    browser.close()
