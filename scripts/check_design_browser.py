"""Real-source design acceptance. Does not synthesize records or overwrite runs."""
import json
from pathlib import Path
from unittest.mock import patch
from check_incremental_browser import ROOT,local_server,choose,verified_distribution_transport,text_contrast
from check_strict_product_browser import submit,validate_counts,replay_identity,verify_visible_units,train_and_read
from playwright.sync_api import sync_playwright,expect
import argparse,tempfile


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-training',action='store_true');args=parser.parse_args()
    out=Path('/tmp/design-first-images');out.mkdir(exist_ok=True);errors=[];checks=[];samples=[]
    with local_server(ROOT) as (base,wb),sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1366,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/');assert page.locator('main a[href="/baseball"]').count()==0
        expect(page.get_by_role('link',name='대결하기')).to_be_visible()
        page.get_by_role('link',name='대결하기').click();expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        for league,year,pyear,batter,pitcher,n in [('KBO',2024,2022,'김도영','안우진',100),('MLB',2023,2023,'Mike Trout','Gerrit Cole',25),('MLB',2024,2024,'Aaron Judge','Tarik Skubal',250),('KBO',1982,2024,'백인천','원태인',25)]:
            page.locator('#league').select_option(league)
            expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            page.locator('#bSeason').select_option(str(year))
            if league=='KBO':page.locator('#pSeason').select_option(str(pyear))
            choose(page,'b',batter);choose(page,'p',pitcher);page.locator('#n').fill(str(n))
            sample=submit(page,'#calculate');r=validate_counts(sample,n);
            for selector in ('body','#calculate','.fact small'):text_contrast(page,selector)
            verify_visible_units(page,n);samples.append(sample)
            assert r['project']==('baseball' if league=='MLB' else 'eramatch')
            page.locator('#result').screenshot(path=str(out/('after-result-'+league+'.png')))
            if batter=='김도영' and pitcher=='안우진':page.locator('#result').screenshot(path=str(out/'after-result.png'))
            page.locator('#tab-principles').click();expect(page.locator('#principlesPlayers')).to_contain_text(batter)
            assert page.locator('#calculationFlow a').count()==7
            page.locator('#explainEvent').select_option('strikeout')
            expect(page.locator('#calcBody05')).to_contain_text(f"{r['model']['probabilities']['strikeout']*100:.1f}%")
            if league=='MLB':expect(page.locator('#calcBody07')).to_contain_text(f"{r['validation']['comparison']['log5']['test']['log_loss']:.4f}")
            page.locator('#explainEvent').select_option('home_run');expect(page.locator('#calcBody05')).to_contain_text(f"{r['model']['probabilities']['home_run']*100:.1f}%")
            page.locator('#principles').screenshot(path=str(out/('after-principles-'+league+'.png')))
            if batter=='김도영' and pitcher=='안우진':page.locator('#principles').screenshot(path=str(out/'after-principles.png'))
            page.locator('#tab-duel').click();new=submit(page,'#rerun');assert new['analysis']['simulation']['seed']!=r['simulation']['seed'];assert new['analysis']['model']['probabilities']==r['model']['probabilities']
            replay_identity(page,base,new,n)
            page.goto(base+'/eramatch?league='+league);expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            checks.append(f'{league} {year}/{pyear}, {n} PA, dynamic 7-step guide, new/exact replay')
        # Both calculations applied to the same eligible KBO profiles.
        page.locator('#league').select_option('KBO');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
        page.locator('#bSeason').select_option('2024');page.locator('#pSeason').select_option('2013');choose(page,'b','김도영');choose(page,'p','서재응')
        r=submit(page,'#calculate')['analysis'];assert r['comparison']
        page.locator('#tab-principles').click();expect(page.locator('#modelDifferences')).to_contain_text('실제로 달라진 확률')
        page.locator('#tab-duel').click();page.set_viewport_size({'width':390,'height':844})
        for tab in ['duel','principles','developer']:
            page.locator('#tab-'+tab).click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),tab
        page.locator('#tab-duel').focus();page.keyboard.press('ArrowRight');expect(page.locator('#tab-principles')).to_be_focused()
        page.screenshot(path=str(out/'after-mobile-principles.png'))
        page.set_viewport_size({'width':1366,'height':1000});page.goto(base+'/baseball');expect(page.locator('#league')).to_have_value('MLB')
        # Fast league changes must not mix two profile catalogs.
        page.locator('#league').select_option('KBO');page.locator('#league').select_option('MLB');expect(page.locator('#selectors')).to_be_visible(timeout=30000);choose(page,'b','Aaron Judge');choose(page,'p','Tarik Skubal');r=submit(page,'#calculate')['analysis'];assert r['batter']['id'].startswith('MLB:')
        if not args.skip_training:
            for study in ['one_run','half_inning']:train_and_read(page,base,wb,study,out)
        # Cached KBO needs no network, and source failure has an actionable retry.
        with tempfile.TemporaryDirectory() as fresh,local_server(fresh) as (other,_):
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY offline cache')):
                page.goto(other+'/eramatch');expect(page.locator('#selectors')).to_be_visible(timeout=30000)
            with patch('baseball_lab.data.catalog.DatasetCatalog.ensure',side_effect=OSError('MOCK_TEST_ONLY network unavailable')):
                page.locator('#league').select_option('MLB');expect(page.locator('#prepare')).to_be_visible(timeout=30000)
            with verified_distribution_transport(ROOT):
                page.locator('#prepare').click();expect(page.locator('#selectors')).to_be_visible(timeout=120000)
        assert not errors,errors;browser.close()
    Path('/tmp/design-first-browser-results.json').write_text(json.dumps({'actual_source_checks':checks,'page_errors':errors,'mock_records_used':False,'training':not args.skip_training},ensure_ascii=False,indent=2));print(json.dumps({'checks':checks,'errors':errors,'training':not args.skip_training},ensure_ascii=False))


if __name__=='__main__':main()
