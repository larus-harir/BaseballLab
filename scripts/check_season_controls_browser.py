from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
with local_server(ROOT) as (base,wb),sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/match/team?study=half_inning');expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=20000)
 assert not page.locator('#periodStart').is_visible()
 page.locator('#learnKBO').check();page.locator('#recordSeason').select_option('collected:2024');expect(page.locator('#sourcePreview')).to_contain_text('KBO: 2023',timeout=30000)
 page.goto(base+'/eramatch?league=MLB');expect(page.locator('#selectors')).to_be_visible(timeout=20000)
 page.locator('#bSeason').select_option('2023');page.locator('#pSeason').select_option('2024');expect(page.locator('#calculate')).to_be_enabled(timeout=20000)
 with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze'),timeout=60000) as r:page.locator('#calculate').click()
 d=r.value.json();assert r.value.ok,d;assert d['analysis']['batter']['season']==2023 and d['analysis']['pitcher']['season']==2024
 page.locator('#tab-developer').click();page.locator('#advanced').evaluate('e=>e.open=true');page.locator('#dataSource').select_option('legacy');page.locator('#tab-duel').click()
 expect(page.locator('#selectors')).to_be_visible(timeout=20000);page.locator('#bSeason').select_option('2023');page.locator('#pSeason').select_option('2024');expect(page.locator('#calculate')).to_be_enabled(timeout=20000)
 with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze'),timeout=60000) as r:page.locator('#calculate').click()
 d=r.value.json();assert r.value.ok,d;assert d['analysis']['batter']['season']==2023 and d['analysis']['pitcher']['season']==2024
 page.locator('#league').select_option('NPB');expect(page.locator('#selectors')).to_be_visible(timeout=20000);expect(page.locator('#calculate')).to_be_enabled()
 with page.expect_response(lambda r:r.url.endswith('/api/matchup/analyze')) as r:page.locator('#calculate').click()
 assert r.value.ok,r.value.text();assert r.value.json()['analysis']['batter']['league']=='NPB'
 assert not errors,errors
 print('PASS: hidden dates, KBO 2023 preview for MLB 2024, MLB 2023 vs 2024, NPB run; no JS errors');b.close()
