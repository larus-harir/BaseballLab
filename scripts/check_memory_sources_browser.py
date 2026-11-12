"""Real-data acceptance: offline matchup aggregates; zero persisted learning inputs.

Network test transport reuses a hash-verified official ZIP. Learning is real;
this test does not certify the user's Windows host or external connectivity.
"""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server
from playwright.sync_api import sync_playwright,expect
from baseball_lab.data.compact import index,npb_before
from baseball_lab.data.training_window import acquire,sources
from baseball_lab.experiments.match.team_win.half_inning import train
from baseball_lab.experiments.match.team_win.training import Config
from baseball_lab.experiments.match.team_win.mixed import npb_before as observed_npb,outcome_labels


def main():
    source=sources(ROOT)[2025]
    archive=ROOT/next(f['path'] for f in source['files'] if f['path'].endswith('.zip'))
    with tempfile.TemporaryDirectory(prefix='baseball-no-raw-') as folder:
        root=Path(folder)
        m=index()['mlb']['2025']
        with patch('baseball_lab.data.memory_source.fetch',return_value=archive.read_bytes()):
            dataset=acquire(root,m['start'],m['end'])
        assert not list(root.rglob('*')),'Learning source acquisition wrote files'
        # Retain exact observed records, split dates and donor identities.
        cached=next(json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'data/local/training-windows').glob('*/dataset.json') if json.loads((p.parent/'manifest.json').read_text(encoding='utf-8'))['source_sha256']==m['csv_sha256'])
        expected=cached['records']
        assert [{k:v for k,v in r.items() if k!='common_event'} for r in dataset['records']]==expected
        assert outcome_labels(root,dataset)=={r['record_id']:r['common_event'] for r in dataset['records']}
        del cached,expected
        for cutoff in ('2025-05-01','2025-07-01','2026-01-01'):
            a=npb_before(cutoff);b=observed_npb(ROOT,cutoff)
            assert a==b,(cutoff,a,b)
        result=train(dataset,m['start'],m['end'],root/'outputs/direct-check',Config(episodes=20,seeds=(41,),evaluation_n=20,evaluate_every=20,batch_size=2))
        from baseball_lab.experiments.match.team_win.mixed import train as train_mixed,validate
        assert set(validate(root,{'MLB':1,'KBO':1,'NPB':1}))=={'MLB','KBO','NPB'}
        train_mixed(root,dataset,m['start'],m['end'],root/'outputs/mixed-check',Config(episodes=20,seeds=(41,),evaluation_n=20,evaluate_every=20,batch_size=2),{'MLB':1,'KBO':1,'NPB':1})
        assert not (root/'data').exists()
        with local_server(root) as (base,wb),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            preparations=[]
            page.route('**/api/matchup/prepare',lambda route:(preparations.append(route.request.post_data_json),route.abort()))
            # No external acquisition is permitted anywhere in these browser flows.
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY offline')):
                page.goto(base+'/eramatch?league=MLB')
                expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
                page.locator('#bSeason').select_option('2015');page.locator('#pSeason').select_option('2025')
                expect(page.locator('#calculate')).to_be_enabled()
                page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible(timeout=30000)
                page.locator('#league').select_option('NPB')
                expect(page.locator('#calculate')).to_be_enabled(timeout=30000)
                expect(page.locator('#bSeason')).to_have_value('2025')
                page.locator('#calculate').click();expect(page.locator('#result')).to_be_visible()
                assert not preparations,preparations
                assert not list((root/'data/local').rglob('*.csv')) and not list((root/'data/local').rglob('*.zip'))
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.goto(base+'/match/team?study=half_inning')
                expect(page.locator('#recordSeason')).to_have_value('recent:5',timeout=30000)
                page.locator('#recordSeason').select_option('collected:2025')
                page.locator('#learnKBO').check();page.locator('#learnNPB').check()
                expect(page.locator('#sourcePreview')).to_contain_text('KBO: 2024',timeout=30000)
                submitted=[]
                def submit(route):
                    submitted.append(route.request.post_data_json)
                    route.fulfill(content_type='application/json',body='{"id":"MOCK_TEST_ONLY submission"}')
                page.route('**/api/start',submit)
                page.locator('#trainBtn').click();expect(page.locator('#trainBtn')).to_be_enabled()
                assert len(submitted)==1 and submitted[0]['options']['collected_window']
                assert set(submitted[0]['options']['league_mixture'])=={'MLB','KBO','NPB'}
                assert not preparations and not errors,(preparations,errors)
                # The real study's stored report is readable after training ends.
                html=(root/'outputs/direct-check/report.html').read_text(encoding='utf-8')
                assert 'MODEL_SIMULATED' in html or '학습' in html
            browser.close()
    print('PASS: exact 2025 donor records; NPB dated counts match 3 cutoffs; real neural MLB and mixed-league learning; offline MLB 2015 vs 2025 and NPB; mixed-learning submission; mobile; no persisted raw/normalized inputs.')


if __name__=='__main__':main()
