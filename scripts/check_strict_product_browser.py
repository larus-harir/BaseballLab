"""Real-cache product regression: UI random/reproduce contracts and real learning.

Run after preparing the registered MLB/KBO catalogs. Screenshots/results go to
/tmp by default; neither originals nor existing runs are overwritten. These
are real-source app checks, separate from MOCK_TEST_ONLY unit fixtures.
"""
import argparse
import json
from pathlib import Path
import shutil
import time

from check_incremental_browser import ROOT, choose, local_server
from playwright.sync_api import sync_playwright, expect


def submit(page, selector):
    with page.expect_response(lambda r: '/api/matchup/analyze' in r.url and r.request.method == 'POST', timeout=120000) as pending:
        page.locator(selector).click()
    response = pending.value
    assert response.ok, response.text()
    result = response.json()
    expect(page.locator('#result')).to_be_visible(timeout=30000)
    expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
    return result


def validate_counts(result, n):
    r = result['analysis']; s = r['simulation']
    assert s['n'] == n == len(s['events']) == sum(s['counts'].values())
    assert abs(sum(r['model']['probabilities'].values())-1) < 1e-10
    reading = r['reading']
    assert sum(x['count'] for x in reading['rows']) == n
    assert abs(sum(x['expected'] for x in reading['rows'])-n) < 1e-8
    return r


def verify_visible_units(page, n):
    expect(page.locator('#resultTitle')).to_contain_text(str(n)+'타석')
    expect(page.locator('#headline')).to_contain_text(str(n)+'타석')
    expect(page.locator('#distributionTitle')).to_contain_text(str(n)+'타석')
    expect(page.locator('#replayIndex')).to_have_attribute('max', str(n))
    page.locator('#replayIndex').fill(str(n)); page.locator('#replayIndex').press('Tab')
    expect(page.locator('#replayPosition')).to_contain_text(str(n)+'번째 타석 / '+str(n))
    text = page.locator('body').inner_text()
    assert '25타석은' not in text and '번의 가상 대결' not in text
    assert '사구 후보' not in text and '실제 타수 미수록' not in text


def players(page, base, project, year, batter, pitcher, pitcher_year=None):
    page.goto(base+'/'+project)
    expect(page.locator('#selectors')).to_be_visible(timeout=120000)
    page.locator('#bSeason').select_option(str(year))
    if project == 'eramatch':page.locator('#pSeason').select_option(str(pitcher_year or year))
    else:expect(page.locator('#pSeason')).to_have_value(str(year))
    choose(page,'b',batter);choose(page,'p',pitcher)


def replay_identity(page, base, sample, n):
    original = sample['analysis']; result = []
    for _ in range(2):
        r = submit(page,'#reproduce'); result.append(r)
        a = validate_counts(r,n)
        assert a['simulation'] == original['simulation']
        assert a['run_id'] == original['run_id']
    ids = [r['analysis']['execution']['execution_id'] for r in [sample,*result]]
    assert len(set(ids)) == 3, ids
    page.goto(base+sample['report'])
    loaded = json.loads(page.locator('#initial').text_content())
    assert loaded['simulation'] == original['simulation']
    assert loaded['run_id'] == original['run_id']
    page.reload();expect(page.locator('#result')).to_be_visible()
    assert json.loads(page.locator('#initial').text_content())['simulation'] == original['simulation']
    # Dynamic saved-report view must also carry the current session authorization.
    reproduced = submit(page,'#reproduce')
    assert reproduced['analysis']['simulation'] == original['simulation']
    return ids


def train_and_read(page, base, wb, study, records):
    page.goto(base+'/match/team?study='+study)
    expect(page.locator('#study')).to_have_value(study)
    page.locator('#episodes').fill('400')
    page.locator('#trainBtn').click()
    expect(page.locator('#cancelBtn')).to_be_visible(timeout=15000)
    deadline = time.monotonic()+300
    while time.monotonic()<deadline:
        if wb.job and wb.job['status'] in ('completed','failed'):break
        page.wait_for_timeout(500)
    job=wb.state('match')['job'];assert job['status']=='completed',job.get('logs',[])[-10:]
    source=wb.outputs/job['id']/'result/research.json';before=source.read_bytes()
    research=json.loads(before)
    assert len(research['seeds'])==3 and all(s['both_parameters_changed'] for s in research['seeds'])
    assert all([h['episodes'] for h in s['history']]==[0,200,400] for s in research['seeds'])
    page.goto(base+job['report']);expect(page.locator('#verdict')).not_to_be_empty()
    if page.locator('#tab-evolution').count():page.locator('#tab-evolution').click()
    slider=page.locator('#evolutionSlider')
    for i in range(3):slider.fill(str(i))
    page.locator('#tab-watch').click();expect(page.locator('#bases svg')).to_be_visible()
    if page.locator('#next').is_enabled():page.locator('#next').click()
    page.locator('#tab-evidence').click();expect(page.locator('body')).to_contain_text('검증')
    page.reload();expect(page.locator('#verdict')).not_to_be_empty()
    assert source.read_bytes()==before
    page.screenshot(path=str(records/('match-'+study+'.png')),full_page=True)
    print('Actual training completed: '+study+' 400 x 3',flush=True)
    return {'study':study,'episodes_per_seed':400,'seeds':3,'stages':[0,200,400],'status':job['status']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--skip-training',action='store_true')
    parser.add_argument('--screenshots',type=Path,default=Path('/tmp/strict-product-images'))
    args=parser.parse_args();out=args.screenshots;out.mkdir(parents=True,exist_ok=True)
    errors=[];checks=[];training=[]
    with sync_playwright() as p,local_server(ROOT) as (base,wb):
        browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1366,'height':950})
        page.on('pageerror',lambda e:errors.append(str(e)))
        players(page,base,'baseball',2023,'Mike Trout','Gerrit Cole')
        sample=submit(page,'#calculate');validate_counts(sample,25);verify_visible_units(page,25)
        page.locator('#result').screenshot(path=str(out/'mlb-25.png'))
        copies=[sample,submit(page,'#rerun'),submit(page,'#rerun')]
        assert len({r['analysis']['simulation']['seed'] for r in copies})==3
        assert all(r['analysis']['model']['probabilities']==sample['analysis']['model']['probabilities'] for r in copies)
        assert len({r['report'] for r in copies})==3
        page.locator('#result').screenshot(path=str(out/'new-sample-2.png'))
        replay_identity(page,base,copies[-1],25)
        page.locator('#result').screenshot(path=str(out/'same-sample-reproduced.png'))
        checks.append('MLB2023: 25 PA, three fresh seeds, fixed probabilities, exact replay and saved history')
        for n in (100,250):
            players(page,base,'baseball',2023,'Mike Trout','Gerrit Cole')
            page.locator('#n').fill(str(n));r=submit(page,'#calculate');validate_counts(r,n);verify_visible_units(page,n)
            page.locator('#result').screenshot(path=str(out/('mlb-'+str(n)+'.png')))
        players(page,base,'baseball',2024,'Aaron Judge','Tarik Skubal')
        r=submit(page,'#calculate');validate_counts(r,25)
        assert r['analysis']['event_display']['other']['detail_available']
        assert len(r['analysis']['reading']['rows'])>8
        page.locator('#otherTitle').click()
        page.locator('#result').screenshot(path=str(out/'mlb-event-details.png'))
        checks.append('MLB2024 season switch and exclusive detailed events; 25/100/250 denominators match')
        players(page,base,'eramatch',2024,'김도영','안우진',2022)
        page.locator('#n').fill('100');sample=submit(page,'#calculate');validate_counts(sample,100);verify_visible_units(page,100)
        assert not sample['analysis']['event_display']['other']['detail_available']
        assert '사구' in sample['analysis']['reading']['other']['definition']
        page.locator('#result').screenshot(path=str(out/'after-kbo-100.png'))
        copies=[sample,submit(page,'#rerun'),submit(page,'#rerun')]
        assert len({r['analysis']['simulation']['seed'] for r in copies})==3
        assert all(r['analysis']['model']['probabilities']==sample['analysis']['model']['probabilities'] for r in copies)
        replay_identity(page,base,copies[-1],100)
        for n in (25,250):
            players(page,base,'eramatch',2024,'김도영','안우진',2022)
            page.locator('#n').fill(str(n));r=submit(page,'#calculate');validate_counts(r,n);verify_visible_units(page,n)
        checks.append('KBO 김도영2024/안우진2022: fresh/reproduce modes, 25/100/250 units, no invented missing events')
        # Native duplicate click must schedule exactly one POST.
        sent=[]
        def count_post(request):
            if '/api/matchup/analyze' in request.url and request.method=='POST':sent.append(request)
        page.on('request',count_post)
        with page.expect_response(lambda r:'/api/matchup/analyze' in r.url and r.request.method=='POST',timeout=30000):
            page.evaluate("document.getElementById('rerun').click();document.getElementById('rerun').click()")
        expect(page.locator('#rerun')).to_be_enabled(timeout=30000)
        assert len(sent)==1,sent
        page.remove_listener('request',count_post)
        page.locator('#tab-developer').click();page.locator('#advanced > summary').click();page.locator('#reproduceMode').check();page.locator('#seed').fill('4242')
        page.locator('#tab-duel').click();fixed=[submit(page,'#calculate'),submit(page,'#calculate')]
        assert fixed[0]['analysis']['simulation']==fixed[1]['analysis']['simulation']
        assert fixed[0]['report']!=fixed[1]['report']
        assert fixed[0]['analysis']['simulation']['seed']==4242
        page.locator('#tab-developer').click();page.locator('#advanced > summary').click();page.locator('#tab-duel').click()
        # Explicit missing-data label must appear in every user-facing event view.
        expect(page.locator('#eventChart')).to_contain_text('세부 기록 없음')
        page.locator('#eventFilter').select_option('other');page.locator('#firstFiltered').click()
        expect(page.locator('#replayOutcome')).to_contain_text('세부 기록 없음')
        page.locator('#eventFilter').select_option('all');page.locator('#replayIndex').fill('250');page.locator('#replayIndex').press('Tab')
        checks.append('Native double click submits once; advanced fixed 4242 seed reproduces exactly; missing-data label in chart/filter/replay')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('#previous').focus();assert page.evaluate('document.activeElement.id')=='previous';page.keyboard.press('Enter');expect(page.locator('#replayPosition')).to_contain_text('249번째 타석 / 250')
        page.locator('#result').screenshot(path=str(out/'mobile-390.png'))
        page.set_viewport_size({'width':1366,'height':950})
        if not args.skip_training:
            for study in ('one_run','half_inning'):training.append(train_and_read(page,base,wb,study,out))
        for route in ('/','/match','/lab/data'):
            page.goto(base+route);assert page.locator('body').inner_text()
        browser.close()
    report={'real_cached_source_checks':checks,'training':training,'page_errors':errors,
            'screenshots_directory':str(out),'mock_data_used':False}
    Path('/tmp/baseball-strict-browser-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2));assert not errors


if __name__=='__main__':main()
