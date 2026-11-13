"""Check dynamic learning help and reopen the actual full-period acceptance run."""
import json
from pathlib import Path
import shutil
import tempfile
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect


def main():
    acceptances=sorted((ROOT/'outputs').glob('full-period-acceptance-*/acceptance.json'),key=lambda p:p.stat().st_mtime)
    if not acceptances:raise RuntimeError('Run check_full_period_learning.py first')
    latest=acceptances[-1];verified=json.loads(latest.read_text(encoding='utf-8'))
    assert verified['source_years']==list(range(2000,2026))
    with tempfile.TemporaryDirectory(prefix='baseball-help-') as folder,local_server(Path(folder)) as (base,wb),sync_playwright() as pw:
        result=wb.outputs/'MOCK_TEST_ONLY_fullperiod/result';result.mkdir(parents=True)
        for name in ('research.json','report.html'):shutil.copyfile(latest.parent/name,result/name)
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/match/team?study=half_inning')
        expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=30000)
        page.locator('#recordSeason').select_option('all');page.locator('#learnKBO').check()
        expect(page.locator('#recordSeason')).to_have_value('all')
        expect(page.locator('#sourcePreview')).to_contain_text('2014 시즌 한 시즌만 사용',timeout=30000)
        expect(page.locator('#sourcePreview')).to_contain_text('2015-05-22')
        expect(page.locator('#sourcePreview')).to_contain_text('중간 점검')
        expect(page.locator('#sourcePreview')).to_contain_text('최종 평가')
        expect(page.locator('#sourcePreview')).to_contain_text('선택한 MLB 전체 기간이 KBO에도 적용되지는 않습니다')
        expect(page.locator('#trainBtn')).to_be_enabled()
        page.locator('#weightMLB').fill('2');expect(page.locator('#mixtureHelp')).to_contain_text('66.7%')
        page.locator('#learnNPB').check();expect(page.locator('#sourcePreview')).to_contain_text('NPB를 제외하거나 MLB 2025 시즌을 선택하세요')
        expect(page.locator('#trainBtn')).to_be_disabled()
        page.locator('#recordSeason').select_option('collected:2025');expect(page.locator('#trainBtn')).to_be_enabled(timeout=30000)
        expect(page.locator('#sourcePreview')).to_contain_text('2024 시즌 한 시즌만 사용')
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.goto(base+'/reports/MOCK_TEST_ONLY_fullperiod/result/report.html')
        expect(page.locator('#mixturePanel')).to_be_visible(timeout=30000)
        expect(page.locator('#mixtureScope')).to_contain_text('2015-05-22')
        expect(page.locator('#mixtureSources')).to_contain_text('2014-01-01')
        expect(page.locator('#mixtureSources')).to_contain_text('발생 비율을 계산한 기록')
        page.locator('#tab-evidence').click();expect(page.locator('#split')).to_contain_text('최종 평가: 학습 후 성적 확인')
        assert not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()
    print('PASS: all-period KBO 2014 and exact date split explained; selection preserved; ratio meaning; unavailable NPB blocked before loading; actual full-period report; mobile; no JS errors.')


if __name__=='__main__':main()
