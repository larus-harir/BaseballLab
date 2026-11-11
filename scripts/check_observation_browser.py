"""Real registered MLB observation UI checks; no mock player records."""
import json,sys
from pathlib import Path
from check_incremental_browser import ROOT,local_server,run_matchup
from playwright.sync_api import sync_playwright,expect
with local_server(ROOT) as (base,wb),sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1366,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/eramatch?league=MLB');expect(page.locator('#selectors')).to_be_visible(timeout=30000);run_matchup(page,'Aaron Judge','Tarik Skubal')
 page.locator('#observations summary').first.click();expect(page.locator('#observationBody svg')).to_be_visible(timeout=90000);expect(page.locator('#observationStatus')).to_contain_text('Aaron Judge');expect(page.locator('#observationBody')).to_contain_text('이 원천에는 기록이 없습니다');expect(page.locator('.pitch-chips').first).not_to_be_empty()
 cohort=page.locator('#observationStatus').inner_text();page.locator('#observationRole').select_option('pitcher');expect(page.locator('#observationStatus')).to_contain_text('Tarik Skubal',timeout=30000)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.locator('#observations').screenshot(path='/tmp/observations-mobile.png')
 page.locator('#tab-principles').click();page.locator('#tab-duel').click();page.locator('#rerun').click();expect(page.locator('#rerun')).to_be_enabled(timeout=30000);expect(page.locator('#observations')).not_to_have_attribute('open','')
 page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000);page.locator('#bSeason').select_option('2024');page.locator('#pSeason').select_option('2022');run_matchup(page,'김도영','안우진');expect(page.locator('#observations')).to_be_hidden()
 b.close();assert not errors,errors;print(json.dumps({'cohort':cohort,'pitcher_switch':True,'mobile_overflow':False,'missing_measurements_explicit':True,'page_errors':errors},ensure_ascii=False))
