"""Exercise draft, block play, changes and reload on the bundled KBO data."""
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright
from check_incremental_browser import local_server


def submit(page, button):
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/manager')) as response:
        button.click()
    value=response.value
    assert value.ok,value.text()
    return value.json()


with TemporaryDirectory(prefix='baseball-manager-') as directory, local_server(Path(directory)) as (base,_), sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':860})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base)
    page.get_by_role('link',name='구단 만들기').click()
    expect(page.locator('#replace-team option')).to_have_count(10)
    page.locator('#replace-team').select_option('KIA')
    page.locator('#club-name').fill('연습 구단')
    state=submit(page,page.get_by_role('button',name='선수 선발 시작'))
    for i in range(16):
        expect(page.locator('#draft-cards article')).to_have_count(3)
        if not state['focus_used']:
            for j,card in enumerate(state['choices']):
                if card['training']:
                    target=page.locator('#draft-cards article').nth(j)
                    target.locator('select').select_option(card['training'][0]['id'])
                    break
            else:target=page.locator('#draft-cards article').first
        else:target=page.locator('#draft-cards article').first
        state=submit(page,target.get_by_role('button',name='선발',exact=True))
        if i<15:expect(page.locator('.slot-list li')).to_have_count(i+1)
    assert state['focus_used']==1
    assert len(state['roster'])==16
    expect(page.locator('#advance-season')).to_have_text('다음 30경기 진행')
    state=submit(page,page.locator('#advance-season'))
    assert state['day']==30 and len(state['standings'])==10
    expect(page.locator('.manager-summary')).to_contain_text('30 / 144')
    page.get_by_text('라인업 · 집중 훈련',exact=True).click()
    state=submit(page,page.locator('[data-order=batting][data-index="0"][data-delta="1"]'))
    assert state['batting'][:2]==['1루수','포수']
    page.get_by_text('선수 한 명 교체',exact=True).click()
    slot=page.locator('#market-slot').input_value()
    previous=state['roster'][slot]['id']
    state=submit(page,page.locator('#market-cards button').first)
    assert state['roster'][slot]['id']!=previous
    page.goto(base+'/manager')
    page.get_by_role('link',name='저장한 시즌 이어하기').click()
    expect(page.locator('.manager-summary')).to_contain_text('30 / 144')
    expect(page.locator('#market-details')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert submit(page,page.locator('#advance-season'))['day']==60
    expect(page.locator('.manager-summary')).to_contain_text('60 / 144')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    browser.close()
    print('PASS: draft and training, 30-game checkpoint, lineup and transfer, saved season resume, mobile layout')
