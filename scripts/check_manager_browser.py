"""Exercise scouting, draft, lineup, block play, transfer and resume."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from check_incremental_browser import local_server


def submit(page, button):
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/manager')) as pending:
        button.click()
    response=pending.value
    assert response.ok,response.text()
    return response.json()


def no_overflow(page):
    width,document=page.evaluate('[innerWidth,document.documentElement.scrollWidth]')
    assert document<=width,(width,document)


with TemporaryDirectory(prefix='baseball-manager-') as directory, local_server(Path(directory)) as (base,_), sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':860})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base)
    page.get_by_role('link',name='구단 만들기').click()
    expect(page.locator('#replace-team input')).to_have_count(10)
    page.get_by_role('radio',name='타이거즈').check()
    page.locator('#club-name').fill('연습 구단')
    # This seed reaches the playoffs after two automatically played rounds.
    with patch('baseball_lab.experiments.manager.store.secrets.randbits',return_value=6):
        state=submit(page,page.get_by_role('button',name='선수 선발 시작'))
    # All three cards fit on mobile with names and letter grades only.
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#draft-cards .player-card')).to_have_count(3)
    expect(page.locator('#draft-cards .grade')).to_have_count(15)
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
    dialog=page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text('리그 순위')
    expect(dialog).to_contain_text('마지막 경기')
    assert '득실' not in dialog.inner_text()
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(page.locator('#season .club-banner')).to_contain_text('30 / 144경기')
    page.get_by_role('tab',name='시즌',exact=True).focus()
    page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab',name='라인업')).to_be_focused()
    first=page.locator('[data-order=batting][data-index="0"]')
    expect(first).to_contain_text('홈런')
    expect(first).to_contain_text('주력')
    first.press('Enter')
    expect(first).to_have_attribute('aria-pressed','true')
    state=submit(page,page.locator('[data-order=batting][data-index="8"]'))
    assert (state['batting'][0],state['batting'][-1])==('지명타자','포수')
    page.locator('#batter-list [data-profile]').first.click()
    expect(dialog).to_contain_text('수비력')
    expect(dialog).to_contain_text('집중 훈련')
    page.keyboard.press('Escape')
    page.locator('#market-details summary').click()
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
    expect(dialog).to_be_visible()
    dialog.get_by_role('button',name='확인',exact=True).click()
    for name in ('선수 기록','경기 기록','라인업','시즌'):
        page.get_by_role('tab',name=name,exact=True).click()
        no_overflow(page)
        if name=='라인업':
            expect(page.locator('#pitcher-list')).to_be_hidden()
            page.get_by_role('button',name='투수 7').click()
            expect(page.locator('#pitcher-list')).to_be_visible()
            expect(page.locator('#batter-list')).to_be_hidden()
            no_overflow(page)
    for day in (90,120,144):
        state=submit(page,page.locator('#advance-season'))
        assert state['day']==day
        if not state['season_report']:
            expect(dialog).to_be_visible()
            if day<144:dialog.get_by_role('button',name='확인',exact=True).click()
    assert state['postseason']['next']['name']=='플레이오프'
    assert all(r['winner'] for r in state['postseason']['rounds'][:2])
    dialog.get_by_role('button',name='포스트시즌 대진').click()
    while next_game:=state['postseason']['next']:
        assert state['team'] in next_game['teams']
        state=submit(page,page.locator('#advance-playoff'))
        expect(dialog).to_contain_text(f"{next_game['number']}차전")
        expect(dialog.locator('.manager-table')).to_be_visible()
        no_overflow(page)
        page.keyboard.press('Escape')
    expect(page.get_by_role('heading',name='시즌 성적표')).to_be_visible()
    expect(page.locator('.award-mvp')).to_contain_text('MVP')
    recap=page.locator('#manager-panel-report')
    recap.get_by_text('수비 골드글러브',exact=False).click()
    expect(recap.get_by_text('순 안타 저지',exact=False).first).to_be_visible()
    no_overflow(page)
    page.reload()
    expect(page.get_by_role('heading',name='시즌 성적표')).to_be_visible()
    page.get_by_role('tab',name='포스트시즌').click()
    expect(page.locator('.post-path')).to_contain_text('한국시리즈')
    expect(page.locator('[data-series="0"][data-playoff-game="0"]')).to_be_visible()
    before=state['id']
    page.get_by_role('tab',name='시즌 성적표').click()
    state=submit(page,page.get_by_role('button',name='같은 구단으로 새 시즌'))
    assert state['id']!=before and state['name']=='연습 구단' and not state['roster']
    state=submit(page,page.get_by_role('button',name='남은 선수 빠르게 선발'))
    assert len(state['roster'])==16 and state['day']==0
    page.go_back()
    expect(page.get_by_role('heading',name='시즌 성적표')).to_be_visible()
    assert not errors,errors
    browser.close()
    print('PASS: draft and quick restart, compact lineup, transfer, postseason and awards, saved game, keyboard/mobile')
