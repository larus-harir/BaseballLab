"""Real packaged multi-league learning: no raw acquisition, filters and reports."""
import json,time
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect

with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match/team?study=pitch_game')
    expect(page.locator('#trainingData')).to_have_value('corpus')
    expect(page.locator('#corpusSummary')).to_contain_text('MLB 2010~2026',timeout=30000)
    expect(page.locator('#corpusSummary')).to_contain_text('KBO 2016~2026')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2026')
    assert page.locator('#corpusYear option').count()==18
    expect(page.locator('#legacyScope')).to_be_hidden()
    expect(page.locator('#sourcePreview')).to_contain_text('연도별 학습 표본 확인')
    expect(page.locator('#trainingData')).to_be_hidden()
    expect(page.locator('#sourcePreview')).to_contain_text('코스가 없는 시즌도')
    page.locator('#study').select_option('half_inning');expect(page.locator('#trainingDataWrap')).to_be_hidden()
    page.locator('#study').select_option('pitch_game')
    page.locator('#corpusYear').select_option('all')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2026')
    page.locator('#episodes').fill('51');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
    assert response.value.ok,response.value.text()
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=page.request.get(base+'/api/state?project=match').json()['job']
        if job['status'] not in ('queued','running'):break
        page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    data=json.loads((ROOT/'outputs/workbench'/job['id']/'result/research.json').read_text(encoding='utf-8'))
    assert data['schema']=='Match-pitch-decision-game-v6' and len(data['seeds'])==3
    assert {c['league'] for c in data['world']['cohorts']}=={'MLB','KBO','NPB'}
    assert {c['season'] for c in data['world']['cohorts']}==set(range(2010,2027))
    assert all(len(s['training_environments'])==36 and s['shared_policy_consistent'] for s in data['seeds'])
    assert all(all(all(v) for v in s['parameters_changed']) for s in data['seeds'])
    assert all(any(k.startswith('pitch:') for counts in s['training_choices'] for k in counts) for s in data['seeds'])
    for seed in data['seeds']:
        assert len(seed['history'])==6
        assert 'A_wins' not in seed['history'][-1]
        assert seed['training_outcomes']['A']+seed['training_outcomes']['B']==51
        for i,t in enumerate(seed['history'][-1]['strategy']):
            observed={**t['offense'],**t['defense']}
            assert observed==seed['training_choices'][i]
            assert t['targets'] and t['batted_area']
            assert t['management']['games']==51 and t['management']['changes']<=102
            assert sum(t['management']['histogram'].values())==51
    assert data['strategy_analysis']['preferences']
    assert any(c['fit']['course']==0 for c in data['world']['capabilities'].values())
    assert any(c['fit']['course']>0 for c in data['world']['capabilities'].values())
    page.goto(base+job['report']);expect(page.locator('#teamCards')).to_contain_text('통합 공격 AI')
    view=page.locator('#data').text_content();view=json.loads(view)
    assert view['schema']=='strategy-report-view-v3'
    assert all(all(t['checks'].values()) for t in view['teams'])
    assert not page.locator('#verdict').count()
    assert 'A팀' not in page.locator('main').inner_text() and 'B팀' not in page.locator('main').inner_text()
    assert '코스 미확인' not in page.locator('main').inner_text()
    assert page.locator('#context option').count()>0
    assert 'undefined' not in page.locator('#summary').inner_text()
    expect(page.locator('#auditBadge')).to_contain_text('일치')
    page.locator('#tab-pitch').click();expect(page.locator('#heatmaps')).to_contain_text('분모:')
    page.locator('#pitchLeague').select_option('MLB')
    assert page.locator('#heatmaps svg').count()==1
    for m in view['heatmaps']['generated|MLB|all']:
        assert m['known']+m['missing']+m['unspecified']==m['total']
        assert abs(sum(x or 0 for x in m['shares'].values())-1)<1e-9
    colors=page.locator('#heatmaps svg g').evaluate_all("els=>els.map(e=>({color:e.querySelector('rect').getAttribute('fill'),ink:e.querySelector('text').getAttribute('fill')}))")
    import re
    def luminance(rgb):
        x=[v/255 for v in rgb];return sum(w*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for v,w in zip(x,(.2126,.7152,.0722)))
    for c in colors:
        lum=luminance([int(v) for v in re.findall(r'\d+',c['color'])]);ratio=1.05/(lum+.05) if c['ink']=='#fff' else (lum+.05)/.05
        assert ratio>=4.5
    page.locator('#pitchLeague').select_option('KBO');expect(page.locator('#heatmaps svg')).to_have_count(1)
    assert view['heatmaps']['generated|KBO|all'][0]['known']>0
    page.locator('#pitchLeague').select_option('MLB');page.locator('#pitchFamily').select_option('fastball')
    page.locator('#tab-growth').focus();page.keyboard.press('Enter');expect(page.locator('#growth')).to_be_visible()
    page.locator('#growthRole').select_option('defense');expect(page.locator('#preferenceHeadline')).to_contain_text('선택 확률')
    expect(page.locator('#batChoice')).to_contain_text('시도');assert page.locator('#sceneField svg').count()==1
    position=int(page.locator('#position').input_value());page.locator('#position').focus();page.keyboard.press('ArrowRight');expect(page.locator('#position')).to_have_value(str(position+1))
    page.locator('#tab-growth').focus();page.keyboard.press('ArrowRight');expect(page.locator('#evidence')).to_be_visible()
    expect(page.locator('#management')).to_contain_text('대조 일치');expect(page.locator('#quality')).to_contain_text('KBO 2016')
    page.reload();expect(page.locator('#summary')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    for tab in ('summary','pitch','growth','evidence'):
        page.locator('#tab-'+tab).click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),tab
    old=next((p for p in (ROOT/'outputs/workbench').glob('*/result/research.json') if (lambda d:d.get('schema')=='Match-pitch-decision-game-v4' and 'pitch_bins' not in d['strategy_analysis']['teams'][0])(json.loads(p.read_text(encoding='utf-8')))),None)
    if old:
        original=old.read_bytes();page.goto(base+'/reports/'+old.parents[1].name+'/result/report.html')
        page.locator('#tab-pitch').click();assert page.locator('#pitchLeague option').count()==1
        page.locator('#pitchMode').select_option('generated');expect(page.locator('#pitchFamily')).to_be_disabled()
        page.locator('#tab-evidence').click();expect(page.locator('#management')).to_contain_text('이전 기록은 합계만')
        assert old.read_bytes()==original
    assert not errors,errors
    print('PASS: compact summary; real joint heatmaps/contrast; acquired KBO positions used by shared AI; games-based substitution audits; growth/replay; keyboard/mobile; old reports read-only. Report:',job['report'])
    browser.close()
