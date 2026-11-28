"""Exercise scouting, draft, lineup, block play, transfer and resume."""
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright
from check_incremental_browser import local_server


def submit(page, button):
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/manager')) as pending:
        button.click()
    response=pending.value
    assert response.ok,response.text()
    return response.json()


def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


with TemporaryDirectory(prefix='baseball-manager-') as directory, local_server(Path(directory)) as (base,_), sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':860})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base)
    page.get_by_role('link',name='구단 만들기').click()
    expect(page.locator('#replace-team input')).to_have_count(10)
    page.get_by_role('radio',name='타이거즈').check()
    page.locator('#club-name').fill('연습 구단')
    state=submit(page,page.get_by_role('button',name='선수 선발 시작'))
    # All three cards fit on mobile with names and letter grades only.
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#draft-cards .player-card')).to_have_count(3)
    expect(page.locator('#draft-cards .grade')).to_have_count(9)
    assert '%' not in page.locator('#draft-cards').inner_text()
    no_overflow(page)
    page.set_viewport_size({'width':1280,'height':860})
    for i in range(16):
        expect(page.locator('#draft-cards .player-card')).to_have_count(3)
        selected=0
        if not state['focus_used']:
            for j,card in enumerate(state['choices']):
                if card['training']:
                    selected=j
                    page.locator('#draft-cards .player-card').nth(j).click()
                    page.locator('#pick-focus').select_option(card['training'][0]['id'])
                    break
        card=state['choices'][selected]
        assert card['name'] and not any(c.isdigit() for c in card['name'])
        expect(page.locator('#draft-cards .player-card[aria-pressed="true"]')).to_contain_text(card['name'])
        slot=state['draft']
        state=submit(page,page.get_by_role('button',name=card['name']+' 선발',exact=True))
        assert card['name']==state['roster'][slot]['name']
        if i<15:expect(page.locator('.club-banner strong')).to_contain_text(f'{i+1} / 16명')
    assert state['focus_used']==1 and len(state['roster'])==16
    expect(page.locator('#advance-season')).to_have_text('다음 30경기 진행')
    state=submit(page,page.locator('#advance-season'))
    assert state['day']==30 and len(state['standings'])==10
    expect(page.locator('#season .club-banner')).to_contain_text('30 / 144경기')
    page.get_by_role('tab',name='시즌',exact=True).focus()
    page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab',name='라인업')).to_be_focused()
    state=submit(page,page.locator('[data-order=batting][data-index="0"][data-delta="1"]'))
    assert state['batting'][:2]==['1루수','포수']
    slot=page.locator('#market-slot').input_value()
    previous=state['roster'][slot]['id']
    state=submit(page,page.locator('#market-cards button[data-pick]'))
    assert state['roster'][slot]['id']!=previous
    page.goto(base+'/manager')
    page.get_by_role('link',name='이어하기').click()
    expect(page.locator('#season .club-banner')).to_contain_text('30 / 144경기')
    expect(page.locator('#market-details')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844})
    assert submit(page,page.locator('#advance-season'))['day']==60
    expect(page.locator('#season .club-banner')).to_contain_text('60 / 144경기')
    for name in ('선수 기록','경기 기록','라인업','시즌'):
        page.get_by_role('tab',name=name,exact=True).click()
        no_overflow(page)
    assert not errors,errors
    browser.close()
    print('PASS: graded draft, training, 30-game checkpoint, lineup and transfer, resume, keyboard/mobile')
