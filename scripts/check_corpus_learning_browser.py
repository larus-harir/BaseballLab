"""Real packaged multi-league learning: no raw acquisition, filters and reports."""
import json,time,sys
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect

with local_server(ROOT) as (base,wb),sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/match')
    assert page.locator('a[href*=half_inning]').count()==0 and page.locator('a[href="/simulation"]').count()==0
    page.goto(base+'/match/team?study=half_inning')
    expect(page.locator('#trainingData')).to_have_value('corpus')
    expect(page.locator('#corpusSummary')).to_contain_text('MLB 2010~2026',timeout=30000)
    expect(page.locator('#corpusSummary')).to_contain_text('KBO 2016~2026')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2026')
    assert page.locator('#corpusYear option').count()==18
    expect(page.locator('#legacyScope')).to_be_hidden()
    expect(page.locator('#sourcePreview')).to_contain_text('연도별 학습 표본 확인')
    expect(page.locator('#trainingData')).to_be_hidden()
    expect(page.locator('.research-detail')).to_contain_text('코스가 없는 시즌도')
    page.locator('#trainingOptions > summary').click()
    page.locator('#corpusMLB').uncheck();page.locator('#corpusKBO').uncheck()
    expect(page.locator('#corpusYear option')).to_have_count(9)
    page.locator('#corpusMLB').check();page.locator('#corpusKBO').check()
    expect(page.locator('#corpusYear option')).to_have_count(18)
    expect(page.locator('#study')).to_have_value('pitch_game')
    assert page.locator('#study option').count()==0
    assert '실행 로그' in page.locator('#taskPanel').inner_text()
    page.locator('#corpusYear').select_option('all')
    expect(page.locator('#corpusSummary')).to_contain_text('NPB 2019~2026')
    page.locator('#episodes').fill('51');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
    if '--reuse-latest' in sys.argv:
        job=None
        for source in sorted((ROOT/'outputs/workbench').glob('*/result/research.json'),reverse=True):
            value=json.loads(source.read_text(encoding='utf-8'))
            if value.get('schema')=='Match-pitch-decision-game-v8' and value.get('status')=='COMPLETED' and value.get('config',{}).get('episodes')==51 and (source.parent/'overview.html').is_file():
                job=json.loads((source.parents[1]/'task.json').read_text(encoding='utf-8'));break
        assert job,'A completed 51-game x 3 real run with saved overview is required'
    else:
        with page.expect_response(lambda r:r.url.endswith('/api/start')) as response:page.locator('#trainBtn').click()
        assert response.value.ok,response.value.text()
        deadline=time.monotonic()+240;last_done=0
        while time.monotonic()<deadline:
            job=page.request.get(base+'/api/state?project=match').json()['job']
            if job.get('progress_scope')=='all_runs':
                assert job['completed_episodes']>=last_done
                last_done=job['completed_episodes'];assert job['target_episodes']==153
            if job['status'] not in ('queued','running'):break
            page.wait_for_timeout(1000)
    assert job['status']=='completed',job
    assert job['completed_episodes']==job['target_episodes']==153
    data=json.loads((ROOT/'outputs/workbench'/job['id']/'result/research.json').read_text(encoding='utf-8'))
    assert data['schema']=='Match-pitch-decision-game-v8' and len(data['seeds'])==3
    assert {c['league'] for c in data['world']['cohorts']}=={'MLB','KBO','NPB'}
    assert {c['season'] for c in data['world']['cohorts']}==set(range(2010,2027))
    assert all(len(s['training_environments'])==36 and s['shared_policy_consistent'] and s['shared_value_consistent'] for s in data['seeds'])
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
    page.goto(base+job['report']);expect(page.locator('#teamCards')).to_contain_text('공격')
    view=page.locator('#data').text_content();view=json.loads(view)
    assert view['schema']=='strategy-report-view-v3'
    choices=page.locator('[data-choice-record]')
    expect(choices).to_have_count(2)
    choices.nth(0).locator('summary').focus();page.keyboard.press('Enter')
    expect(choices.nth(0)).to_have_attribute('open','')
    expect(choices.nth(1)).to_have_attribute('open','')
    choices.nth(1).locator('summary').click()
    expect(choices.nth(0)).not_to_have_attribute('open','')
    expect(choices.nth(1)).not_to_have_attribute('open','')
    assert all(s['situation_specific'] and s['probe_id'] for s in view['overview']['explanations'])
    assert '여전히' not in page.locator('#reasons').inner_text()
    assert all(len(t)<70 for t in page.locator('#reasons .narrative').all_inner_texts())
    expect(page.locator('#reasons details p').first).not_to_be_visible()
    page.locator('#reasons details summary').first.click()
    expect(page.locator('#reasons table').first).to_be_visible()
    expect(page.locator('#reasons details[open]')).to_have_count(len(view['overview']['explanations']))
    assert page.locator('#reasons table').first.locator('tbody tr').count()>=1
    original=(ROOT/'outputs/workbench'/job['id']/'result/research.json').read_bytes()
    page.locator('#glanceLink').click();expect(page).to_have_url(base+job['report'].replace('report.html','overview.html'))
    expect(page.locator('h1')).to_be_visible();assert page.locator('.grids svg').count()==2
    assert len(page.locator('h1').inner_text())<70
    expect(page.locator('.story-evidence p').first).not_to_be_visible()
    page.locator('.story-evidence > summary').click()
    expect(page.locator('.story-evidence h3')).to_have_count(2)
    expect(page.locator('.story-evidence p').first).to_be_visible()
    assert '한눈에 보기' in page.title() and not page.locator('select').count()
    page.locator('a[href="report.html#pitch"]').first.click();expect(page.locator('#pitch')).to_be_visible()
    page.locator('#glanceLink').click();page.locator('.interpretation a[href="report.html#evidence"]').click();expect(page.locator('#evidence')).to_be_visible()
    page.locator('#tab-summary').click()
    assert (ROOT/'outputs/workbench'/job['id']/'result/research.json').read_bytes()==original
    assert (ROOT/'outputs/workbench'/job['id']/'result/overview.html').is_file()
    assert all(all(t['checks'].values()) for t in view['teams'])
    assert not page.locator('#verdict').count()
    assert 'A팀' not in page.locator('main').inner_text() and 'B팀' not in page.locator('main').inner_text()
    assert '코스 미확인' not in page.locator('main').inner_text()
    assert page.locator('select').count()==0
    assert view['overview']['games']==153 and view['overview']['runs']==3
    assert page.locator('#countOverview > .scroll tbody tr').count()==12
    assert all(c['preferences']['course']['states']>0 for c in view['overview']['counts'])
    assert any(row.get('reward_observations',0)>0 for row in view['overview']['feedback']['course'].values())
    assert 'undefined' not in page.locator('#summary').inner_text()
    expect(page.locator('#auditBadge')).to_contain_text('집계 일치')
    page.locator('#tab-pitch').click();expect(page.locator('#courseDenominator')).to_contain_text('코스 직접 선택')
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
    assert view['heatmaps']['generated|KBO|all'][0]['known']>0
    page.locator('#tab-growth').focus();page.keyboard.press('Enter');expect(page.locator('#growth')).to_be_visible()
    assert page.locator('#growthCharts svg').count()==4
    assert page.locator('#courseComparison svg').count()==2
    assert '같은 경기 상황' in page.locator('#summary').inner_text()
    assert page.locator('#replayDetail').count()==0
    assert page.locator('#reasons .narrative').count()>0
    assert all(seed.get('replay',{}).get('events') for seed in data['seeds'])
    page.locator('#tab-growth').focus();page.keyboard.press('ArrowRight');expect(page.locator('#evidence')).to_be_visible()
    page.locator('#evidence details').nth(0).locator('summary').click()
    expect(page.locator('#management')).to_contain_text('대조 일치')
    page.locator('#evidence details').nth(1).locator('summary').click()
    expect(page.locator('#quality')).to_contain_text('KBO 2016')
    page.reload();expect(page.locator('#evidence')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    for tab in ('summary','pitch','growth','evidence'):
        page.locator('#tab-'+tab).click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),tab
    old_shared=next((p for p in (ROOT/'outputs/workbench').glob('*/result/research.json') if json.loads(p.read_text(encoding='utf-8')).get('schema')=='Match-pitch-decision-game-v7'),None)
    if old_shared:
        original=old_shared.read_bytes();page.goto(base+'/reports/'+old_shared.parents[1].name+'/result/report.html')
        assert page.locator('select').count()==0 and page.locator('#countOverview > .scroll tbody tr').count()==12
        assert 'undefined' not in page.locator('main').inner_text() and 'NaN' not in page.locator('main').inner_text()
        assert old_shared.read_bytes()==original
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
