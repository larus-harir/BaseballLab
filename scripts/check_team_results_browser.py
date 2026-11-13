"""Review actual saved whole-game results without rerunning any training."""
import hashlib,json
from pathlib import Path
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect


def main():
    candidates=[]
    for path in (ROOT/'outputs/workbench').glob('*/result/research.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema')=='Match-whole-game-v1' and data.get('status')=='COMPLETED':candidates.append((path,data))
    path,data=max(candidates,key=lambda v:v[0].stat().st_mtime);before=hashlib.sha256(path.read_bytes()).hexdigest()
    with local_server(ROOT) as (base,wb),sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/reports/'+str(path.parent.relative_to(wb.outputs))+'/report.html')
        expect(page.locator('#teams')).to_contain_text('A팀')
        expect(page.locator('#teams')).to_contain_text('B팀')
        expect(page.locator('#teams')).to_contain_text('타격·주루 담당 AI')
        expect(page.locator('#teams')).to_contain_text('투구 담당 AI')
        expect(page.locator('#teams')).to_contain_text('고정 비교 상대')
        replay=data['seeds'][0]['replay']
        expect(page.locator('#scoreboard')).to_contain_text('A '+str(replay['home'])+' : '+str(replay['away'])+' B')
        n=sum(s['test_after']['games'] for s in data['seeds']);w=sum(s['test_after']['wins'] for s in data['seeds'])
        expect(page.locator('#headline')).to_contain_text('A팀 '+str(w)+'승 · B팀 '+str(n-w)+'승')
        expect(page.locator('#roleNote')).to_contain_text('고정한 평가용 상대')
        if len(data['seeds'])>1:
            page.locator('#runSelect').select_option('1');r=data['seeds'][1]['replay']
            expect(page.locator('#scoreboard')).to_contain_text('A '+str(r['home'])+' : '+str(r['away'])+' B')
        page.locator('#tab-summary').focus();page.keyboard.press('ArrowRight')
        expect(page.locator('#game')).to_be_visible();expect(page.locator('#tab-game')).to_be_focused()
        old=page.locator('#scenePosition').inner_text();page.locator('#next').click();assert old!=page.locator('#scenePosition').inner_text()
        page.locator('#nextScore').click();expect(page.locator('#sceneOutcome')).to_contain_text('점 득점')
        page.locator('#tab-learning').click();expect(page.locator('#policyChanges')).to_contain_text('A팀 공격 AI')
        expect(page.locator('#learning')).to_contain_text('따로 학습하지 않았습니다')
        for tab in ('summary','game','learning'):
            page.set_viewport_size({'width':390,'height':844});page.locator('#tab-'+tab).click()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),tab
        assert not errors,errors;assert wb.job is None
        browser.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    print('PASS: actual saved result; A/B scores and learner/fixed roles; per-team offense/defense; aggregate vs one-game scope; run selection, keyboard tabs, replay and next score; mobile; no new jobs or JSON changes.')


if __name__=='__main__':main()
