"""Optional real-browser acceptance check. Requires playwright + Chromium and local catalogs.

Run from the repository after preparing MLB 2024 and connecting the original
assignment. No private records or original ZIP are distributed by this script.
"""
from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1];out=root/'docs/images/three-projects';out.mkdir(parents=True,exist_ok=True);errors=[]
import sys,threading,shutil,tempfile
sys.path.insert(0,str(root/'src'))
from http.server import ThreadingHTTPServer
from baseball_lab.web.server import Workbench,make_handler
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Workbench(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(server.server_port)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/');expect(page.get_by_role('link',name='선수 대결 실행',exact=True)).to_be_visible();page.screenshot(path=str(out/'portal.png'),full_page=True)
 page.get_by_role('link',name='선수 대결 실행',exact=True).click();expect(page.locator('#selectors')).to_be_visible(timeout=20000)
 page.locator('#bQuery').fill('Aaron Judge');expect(page.locator('#bPlayer option')).to_have_count(1,timeout=10000);expect(page.locator('#bPlayer')).to_contain_text('Aaron Judge');page.locator('#bPlayer').select_option(label=page.locator('#bPlayer option').inner_text())
 page.locator('#pQuery').fill('Tarik Skubal');expect(page.locator('#pPlayer option')).to_have_count(1);expect(page.locator('#pPlayer')).to_contain_text('Tarik Skubal');page.locator('#pPlayer').select_option(label=page.locator('#pPlayer option').inner_text())
 page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible(timeout=20000);expect(page.locator('#resultTitle')).to_contain_text('Aaron Judge');expect(page.locator('#resultTitle')).to_contain_text('Tarik Skubal')
 page.screenshot(path=str(out/'baseball.png'),full_page=True)
 page.locator('#context details').first.locator('summary').click();page.locator('#explanation').screenshot(path=str(out/'explanation.png'))
 report=page.locator('#reportLink a').get_attribute('href');page.goto(base+report);expect(page.locator('#result')).to_be_visible();expect(page.locator('#setup')).to_be_hidden()
 page.goto(base+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=20000)
 page.locator('#bSeason').select_option('1982');page.locator('#bQuery').fill('백인천');expect(page.locator('#bPlayer option')).to_have_count(1);expect(page.locator('#bPlayer')).to_contain_text('백인천');expect(page.locator('#bPlayer')).to_be_enabled();page.locator('#bPlayer').select_option(label=page.locator('#bPlayer option').inner_text())
 page.locator('#pSeason').select_option('2024');page.locator('#pQuery').fill('원태인');expect(page.locator('#pPlayer option')).to_have_count(1);expect(page.locator('#pPlayer')).to_contain_text('원태인');expect(page.locator('#pPlayer')).to_be_enabled();page.locator('#pPlayer').select_option(label=page.locator('#pPlayer option').inner_text())
 page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible(timeout=20000);expect(page.locator('#resultTitle')).to_contain_text('백인천');expect(page.locator('#resultTitle')).to_contain_text('원태인');expect(page.locator('#timeline button')).to_have_count(25)
 page.locator('#comparisonBlock summary').click();expect(page.locator('#comparison')).to_contain_text('과제 방식');page.screenshot(path=str(out/'eramatch.png'),full_page=True)
 page.locator('#model').select_option('normalized');page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible(timeout=10000);expect(page.locator('#probabilities')).to_contain_text('사구')
 # Empty name search never fabricates a selectable profile.
 page.locator('#bQuery').fill('없는선수-MOCK_TEST_ONLY');expect(page.locator('#bPlayer')).to_contain_text('조건에 맞는 선수 없음');expect(page.locator('#bPlayer')).to_be_enabled();page.locator('#calculate').click();expect(page.locator('#formError')).to_contain_text('모두 선택')
 page.goto(base+'/match');expect(page.get_by_text('인간 야구의 역사·현대 전략',exact=False)).to_be_visible();page.get_by_role('link',name='실험 설정하기',exact=True).click();expect(page.locator('.research-help')).to_be_visible();page.screenshot(path=str(out/'match.png'),full_page=True)
 # Preserve working prior R1 result, replay and independent scene entry.
 expect(page.locator('#runs details summary')).to_be_visible(timeout=10000);page.locator('#runs details summary').click()
 links=page.locator('#runs .run').filter(has_text='AI 학습').get_by_role('link',name='결과 보기');expect(links.first).to_be_visible(timeout=10000)
 with page.expect_popup() as popup:links.first.click()
 resultpage=popup.value;resultpage.on('pageerror',lambda e:errors.append(str(e)));resultpage.wait_for_load_state()
 expect(resultpage.locator('#verdict')).not_to_be_empty()
 slider=resultpage.locator('#evolutionSlider');slider.fill(slider.get_attribute('max'))
 resultpage.locator('#tab-watch').click();expect(resultpage.locator('#bases svg')).to_be_visible()
 if resultpage.locator('#next').is_enabled():resultpage.locator('#next').click()
 resultpage.locator('#tab-overview').click();resultpage.screenshot(path=str(out/'match-result.png'),full_page=True)
 resultpage.close()
 page.goto(base+'/simulation');expect(page.locator('body')).to_contain_text('장면 살펴보기')
 mobile=browser.new_page(viewport={'width':390,'height':844});mobile.on('pageerror',lambda e:errors.append(str(e)))
 mobile.goto(base+'/eramatch');expect(mobile.locator('#selectors')).to_be_visible(timeout=20000);mobile.screenshot(path=str(out/'mobile.png'),full_page=True)
 # Read-only JS measurement, no page modification.
 assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile horizontal overflow'
 # Empty-data environment exposes preparation, never invented profiles.
 with tempfile.TemporaryDirectory() as empty:
  fresh=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Workbench(empty)));threading.Thread(target=fresh.serve_forever,daemon=True).start()
  freshbase='http://127.0.0.1:'+str(fresh.server_port)
  page.goto(freshbase+'/baseball');expect(page.locator('#prepare')).to_be_visible();expect(page.locator('#selectors')).to_be_hidden()
  page.goto(freshbase+'/eramatch');expect(page.locator('#import')).to_be_visible();expect(page.locator('#selectors')).to_be_hidden()
  page.locator('#archive').set_input_files({'name':'MOCK_TEST_ONLY.zip','mimeType':'application/zip','buffer':b'not the assignment'})
  page.locator('#import').click();expect(page.locator('#formError')).to_contain_text('ZIP 버전')
  assert not list(Path(empty).glob('outputs/workbench/*/task.json'))
  fresh.shutdown();fresh.server_close()
 browser.close()
server.shutdown();server.server_close()
print(json.dumps({'browser_errors':errors,'screenshots':[str(x.relative_to(root)) for x in out.glob('*.png')]},ensure_ascii=False));assert not errors
