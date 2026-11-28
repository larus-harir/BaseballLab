"""Product acceptance checks against isolated, offline packaged data.

Run: python scripts/check_product_revision_browser.py
Requires Playwright and Chromium. Never starts training or opens the real
workbench root. Only MOCK_TEST_ONLY, created below, is deleted through the UI.
"""
from pathlib import Path
import re
import tempfile
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from check_incremental_browser import local_server


TIMEOUT = 30000


def no_overflow(page):
    dimensions = page.evaluate("""() => ({width: innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth})""")
    assert max(dimensions['document'], dimensions['body']) <= dimensions['width'], dimensions


def keyboard_to(page, selector, limit=60):
    """Reach a visible target using Tab, including its visible focus ring."""
    for _ in range(limit):
        page.keyboard.press('Tab')
        if page.locator(selector).evaluate('e => e === document.activeElement'):
            ring = page.locator(selector).evaluate("""e => {
                const s=getComputedStyle(e);
                return {style:s.outlineStyle,width:parseFloat(s.outlineWidth),
                    color:s.outlineColor};
            }""")
            assert ring['style'] != 'none' and ring['width'] >= 2, ring
            return
    raise AssertionError('Keyboard could not reach ' + selector)


def run(page, selector='#calculate'):
    with page.expect_response(lambda response: response.url.endswith('/api/matchup/analyze')) as pending:
        page.locator(selector).click()
    response = pending.value
    result = response.json()
    assert response.ok, result
    expect(page.locator('#result')).to_be_visible(timeout=TIMEOUT)
    analysis = result['analysis']
    assert sum(analysis['simulation']['counts'].values()) == analysis['simulation']['n']
    return result


def navigation_mobile_keyboard(page, base, root):
    page.goto(base + '/')
    keyboard_to(page, 'a.button[href="/eramatch"]')
    page.keyboard.press('Enter')
    expect(page.locator('#calculate')).to_be_enabled(timeout=TIMEOUT)
    page.locator('#tab-duel').focus()
    page.keyboard.press('ArrowRight')
    expect(page.locator('#tab-principles')).to_be_focused()
    expect(page.locator('#tab-principles')).to_have_attribute('aria-selected', 'true')
    expect(page.locator('#principles')).to_be_visible()
    page.keyboard.press('End')
    expect(page.locator('#tab-developer')).to_be_focused()
    page.keyboard.press('Home')
    expect(page.locator('#tab-duel')).to_be_focused()

    page.set_viewport_size({'width': 390, 'height': 844})
    for path in ('/', '/eramatch?league=MLB', '/eramatch?league=KBO',
                 '/eramatch?league=NPB', '/eramatch?mode=common', '/match',
                 '/match/team', '/lab/data', '/simulation'):
        page.goto(base + path)
        if path.startswith('/eramatch'):
            expect(page.locator('#run' if 'mode=common' in path else '#calculate')).to_be_enabled(timeout=TIMEOUT)
        elif path == '/match/team':
            expect(page.locator('#trainBtn')).to_be_enabled(timeout=TIMEOUT)
        elif path == '/lab/data':
            expect(page.locator('#storageMessage')).to_contain_text('개', timeout=TIMEOUT)
        no_overflow(page)
    page.goto(base + '/simulation')
    page.locator('#source').select_option('observed')
    expect(page.locator('#styleSettings')).to_be_hidden()
    expect(page.locator('#style')).to_be_disabled()
    page.locator('#source').select_option('model')
    expect(page.locator('#styleSettings')).to_be_visible()
    expect(page.locator('#style')).to_be_enabled()


def league_results_validation_saved(page, base, root):
    for league in ('MLB', 'KBO', 'NPB'):
        page.goto(base + '/eramatch?league=' + league)
        expect(page.locator('#calculate')).to_be_enabled(timeout=TIMEOUT)
        page.locator('#n').fill('0')
        page.locator('#calculate').click()
        expect(page.locator('#formError')).to_contain_text('타석')
        expect(page.locator('#formError')).to_be_focused()
        expect(page.locator('#result')).to_be_hidden()
        page.locator('#n').fill('37')
        result = run(page)
        analysis = result['analysis']
        assert analysis['batter']['league'] == league
        assert analysis['simulation']['n'] == 37
        expect(page.locator('#headline')).to_contain_text('37타석')
        expect(page.locator('#result')).to_be_focused()
        expect(page.locator('#otherMeaning')).not_to_be_visible()
        assert '원천' not in page.locator('#detailScope').inner_text()
        chart_text=page.locator('#eventChart').inner_text()
        assert '그 밖의 결과' not in chart_text, chart_text
        no_overflow(page)
        page.locator('#eventChart button').first.click()
        expect(page.locator('#plateDetails')).to_have_attribute('open', '')
        expect(page.locator('#replayOutcome')).to_be_visible()
        again = run(page, '#reproduce')['analysis']
        assert again['run_id'] == analysis['run_id']
        assert again['simulation']['events'] == analysis['simulation']['events']
        page.locator('#n').fill('38')
        expect(page.locator('#result')).to_be_hidden()
        page.goto(base + result['report'])
        expect(page.locator('#resultTitle')).to_contain_text(analysis['batter']['name'])
        expect(page.locator('#headline')).to_contain_text('37타석')
        expect(page.locator('#setup')).to_be_hidden()
        page.set_viewport_size({'width': 390, 'height': 844})
        no_overflow(page)
        page.set_viewport_size({'width': 1440, 'height': 1000})


def common_validation_saved_stale(page, base, root):
    page.goto(base + '/eramatch?mode=common')
    expect(page.locator('#run')).to_be_enabled(timeout=TIMEOUT)
    page.locator('#bSource').select_option('MLB:2025')
    page.locator('#pSource').select_option('NPB:2025')
    page.locator('#reference').select_option('MLB:2025')
    expect(page.locator('#run')).to_be_enabled(timeout=TIMEOUT)
    page.locator('#n').fill('0')
    page.locator('#run').click()
    expect(page.locator('#message')).to_contain_text(re.compile('타석|1.*10.?000'))
    expect(page.locator('#result')).to_be_hidden()
    page.locator('#n').fill('37')
    result = run(page, '#run')
    analysis = result['analysis']
    assert analysis['simulation']['n'] == 37
    expect(page.locator('#headline')).to_contain_text('37타석')
    page.set_viewport_size({'width': 390, 'height': 844})
    no_overflow(page)
    page.locator('#n').fill('38')
    expect(page.locator('#result')).to_be_hidden()

    # Change the current selection after the real response is computed but before
    # it reaches the browser. The saved earlier calculation must not replace the
    # current selection with an apparently current result.
    def change_before_response(route):
        response = route.fetch()
        expect(page.locator('#n')).to_be_disabled()
        page.locator('#n').evaluate("""element => {
            element.value='39';
            element.dispatchEvent(new Event('input', {bubbles:true}));
        }""")
        route.fulfill(response=response)

    page.route('**/api/matchup/analyze', change_before_response)
    with page.expect_response(lambda response: response.url.endswith('/api/matchup/analyze')) as pending:
        page.locator('#run').click()
    assert pending.value.ok
    expect(page.locator('#run')).to_be_enabled()
    expect(page.locator('#result')).to_be_hidden()
    expect(page.locator('#n')).to_have_value('39')
    page.unroute('**/api/matchup/analyze', change_before_response)
    page.goto(base + result['report'])
    expect(page.locator('#resultTitle')).to_contain_text(analysis['batter']['name'])
    expect(page.locator('#headline')).to_contain_text('37타석')
    expect(page.locator('#setup')).to_be_hidden()
    no_overflow(page)


def learning_recovery_and_disposable_deletion(page, base, root):
    def fail_catalog(route):
        route.fulfill(status=503, json={'error': 'MOCK_TEST_ONLY 기록 연결 실패'})

    page.route('**/api/pitch-corpus', fail_catalog)
    page.goto(base + '/match/team')
    expect(page.locator('#catalogRetry')).to_be_visible()
    expect(page.locator('#trainBtn')).to_be_disabled()
    expect(page.locator('#formError')).to_contain_text('MOCK_TEST_ONLY')
    page.unroute('**/api/pitch-corpus', fail_catalog)
    page.locator('#catalogRetry').click()
    expect(page.locator('#trainBtn')).to_be_enabled(timeout=TIMEOUT)
    page.locator('#trainingOptions > summary').click()
    for league in ('MLB', 'KBO', 'NPB'):
        page.locator('#corpus' + league).uncheck()
    expect(page.locator('#trainBtn')).to_be_disabled()
    expect(page.locator('#formError')).to_contain_text('리그')
    page.locator('#corpusMLB').check()
    expect(page.locator('#trainBtn')).to_be_enabled()
    page.locator('#episodes').fill('0')
    page.locator('#trainBtn').click()
    assert page.locator('#episodes').evaluate('e => !e.validity.valid')
    expect(page.locator('#episodes')).to_be_focused()
    assert page.request.get(base + '/api/state?project=match').json()['job'] is None, 'Invalid form started training'

    target = root / 'outputs/workbench/MOCK_TEST_ONLY'
    target.mkdir(parents=True, exist_ok=False)
    (target / 'mock.log').write_text('MOCK_TEST_ONLY disposable deletion fixture', encoding='utf-8')
    page.goto(base + '/lab/data')
    page.get_by_text('사용 가능한 학습 기록과 출처', exact=True).click()
    expect(page.locator('#sourceCoverage')).to_contain_text('KBO 2016~2026', timeout=TIMEOUT)
    expect(page.locator('#sourceCoverage')).to_contain_text('NPB 2019~2026')
    inventory = page.request.get(base + '/api/storage').json()
    item = next(item for item in inventory['items'] if item['id'] == 'run:MOCK_TEST_ONLY')
    page.locator('#items > details > summary').click()
    card = page.locator('#items section').filter(has=page.get_by_role('heading', name=item['label'], exact=True))
    review = card.get_by_role('button', name='삭제 검토', exact=True)
    review.click()
    expect(page.locator('#confirmDelete')).to_be_disabled()
    assert target.exists()
    page.locator('#cancelDelete').click()
    expect(page.locator('#deleteDialog')).not_to_be_visible()
    assert target.exists()
    review.click()
    expect(page.locator('#confirmLoss')).not_to_be_checked()
    expect(page.locator('#confirmDelete')).to_be_disabled()
    page.locator('#confirmLoss').check()
    page.locator('#confirmDelete').click()
    expect(page.locator('#deleteDialog')).not_to_be_visible()
    assert not target.exists()


def main():
    checks = (navigation_mobile_keyboard, league_results_validation_saved,
              common_validation_saved_stale, learning_recovery_and_disposable_deletion)
    failures = []
    with tempfile.TemporaryDirectory(prefix='baseball-product-revision-') as folder:
        root = Path(folder)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('MOCK_TEST_ONLY offline')):
            with local_server(root) as (base, _workbench), sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                for check in checks:
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    try:
                        check(page, base, root)
                        assert not errors, errors
                        print('PASS:', check.__name__, flush=True)
                    except Exception as error:
                        failures.append(check.__name__ + ': ' + str(error))
                        print('FAIL:', failures[-1], flush=True)
                    finally:
                        page.close()
                browser.close()
        assert not list((root / 'data').rglob('*.csv'))
        assert not list((root / 'data').rglob('*.zip'))
    assert not failures, '\n\n'.join(failures)
    print('PASS: product browser acceptance; isolated offline root; no training or real-file deletion.')


if __name__ == '__main__':
    main()
