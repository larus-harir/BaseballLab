/* Explanations read the exact saved intermediates; no second probability engine. */
function principles(result){
 const b=result?.batter||selected.b,p=result?.pitcher||selected.p;
 $('principlesPlayers').textContent=b&&p?`${b.name} (${b.season}) × ${p.name} (${p.season})`:'선수 선택에 따라 계산 예시가 바뀝니다';
 $('records').innerHTML=b&&p?'<div class="row"><div>'+raw(b)+'</div><div>'+raw(p)+'</div></div>':'<p class="empty">대결 탭에서 두 선수를 선택하세요.</p>';
 const definitions=[['01','시즌 기록','타석·안타·삼진 등 실제 시즌 기록'],['02','시대 보정','각 시즌의 리그 평균을 기준으로 조정'],['03','표본 안정화','기록이 적으면 리그 평균을 더 반영'],['04','BABIP / DIPS','인플레이 안타와 수비·환경의 영향'],['05','Log5','타자·투수·리그 비율을 결합'],['06','몬테카를로','계산된 확률로 타석을 추첨'],['07','결과 검사','예상·실제 표본·예측 오차 비교']];
 $('calculationFlow').innerHTML=definitions.map(([i,t,d])=>'<a href="#calc-'+i+'"><span>'+i+'</span><strong>'+t+'</strong><small>'+d+'</small></a>').join('');
 for(const i of ['02','03','04','05','06','07'])$('calcBody'+i).innerHTML='<p class="empty">대결을 실행하면 이 선택의 실제 수치를 표시합니다.</p>';
 if(!result){$('modelDifferences').innerHTML=comparisonTable(null);return}
 if(result.model.model==='common'){
  const r=result,s=r.model.steps,keys=Object.keys(r.model.probabilities);
  $('calcBody02').innerHTML='<p>원래 리그 평균 대비 빈도를 '+esc(s.target)+' 환경으로 옮겼습니다.</p>'+table(['결과','타자 기록','투수 기록','기준 환경'],keys.map(k=>[labels[k],pct(s.batter_raw[k]),pct(s.pitcher_raw[k]),pct(s.reference[k])]));
  $('calcBody03').innerHTML='<p>타자 '+s.batter_n+'타석 · 투수 '+s.pitcher_n+'명 상대. 원래 리그 평균을 '+s.strength+'타석만큼 섞었습니다. 탐색용 보정이며 검증된 리그 간 실력 환산이 아닙니다.</p>';
  $('calcBody04').innerHTML='<p>안타 종류·타수·희생플라이가 부족하면 BABIP를 계산하지 않습니다. 확보된 홈런·장타·사구는 분리하고, 구분할 수 없는 안타만 묶습니다. 나머지 결과를 전부 아웃으로 해석하지 않습니다.</p>';
  $('calcBody05').innerHTML='<p>사건별 보정 타자 × 보정 투수 ÷ 기준 환경의 빈도를 구한 뒤 합계를 100%로 맞춥니다.</p>'+table(['결과','계산 확률'],keys.map(k=>[labels[k],pct(r.model.probabilities[k])]));
  $('calcBody06').innerHTML=table(['결과','예상 개수','이번 개수'],keys.map(k=>[labels[k],r.simulation.expected[k].toFixed(1),r.simulation.counts[k]]));
  $('calcBody07').innerHTML='<p>'+esc(r.simulation.uncertainty)+'</p><p>출처·원래 시즌·관측 타석 수를 보존합니다. 예측·인과 검증을 통과한 모형이라는 뜻은 아닙니다.</p>';
  $('modelDifferences').innerHTML=r.model.assumptions.map(x=>'<p>'+esc(x)+'</p>').join('');return;
 }
 const r=result,s=r.model.steps,legacy=r.model.model==='legacy',event=$('explainEvent').value,key=legacy?({strikeout:'K_rate',walk:'BB_rate',home_run:'HR_rate'})[event]:event;
 const safe=x=>x==null?'미집계':pct(x),br=s.batter_raw?.[key],be=s.batter_era?.[key],ba=s.batter_adjusted?.[key],pr=s.pitcher_raw?.[key],pe=s.pitcher_era?.[key],pa=s.pitcher_adjusted?.[key],lr=s.reference?.[key];
 const label=labels[event],nn=r.simulation.n,q=r.model.probabilities[event];
 $('calcBody02').innerHTML='<p>'+label+' 비율 · 기록 → 시즌 환경을 맞춘 비율</p>'+table(['선수','기록 비율','시대 보정 후'],[[b.name,safe(br),safe(be)],[p.name,safe(pr),safe(pe)]])+'<p class="caption">'+(legacy?'원본 비율 × 통산 리그 비율 ÷ 해당 시즌 리그 비율':'개인 비율을 기준 리그로 옮긴 뒤 전체 사건 합계로 정규화')+'</p>';
 const bn=s.batter_n,pn=s.pitcher_n,c=legacy?s.constants?.['batter_'+({strikeout:'k',walk:'bb',home_run:'hr'})[event]]:s.strength;
 $('calcBody03').innerHTML=table(['선수','사용 표본','시대 보정 후','평균을 섞은 후'],[[b.name,bn??'리그 전체',safe(be),safe(ba)],[p.name,pn??'리그 전체',safe(pe),safe(pa)]])+'<div class="formula">(선수 비율 × 표본 + 리그 비율 × 보정량) ÷ (표본 + 보정량)</div><p class="caption">'+(c==null?'리그 빈도 모형은 선수별 보정을 사용하지 않습니다.':'타자 '+label+' 보정량 '+c+' · '+(legacy?'원본의 사건별 고정 상수':'기간을 나눠 검사한 MLB 강도와 KBO 미검증 기본 강도를 구분'))+'</p>';
 function babip(player){const c=player.counts,den=c.AB==null||c.SF==null?null:c.AB-c.SO-c.HR+c.SF;return den>0?{den,value:(c.H-c.HR)/den}:null}
 const bb=babip(b),pb=babip(p);
 $('calcBody04').innerHTML='<div class="formula">BABIP = (안타 − 홈런) ÷ (타수 − 삼진 − 홈런 + 희생플라이)</div>'+table(['선수','인플레이 분모','관측 BABIP'],[[b.name,bb?.den??'미집계',safe(bb?.value)],[p.name,pb?.den??'미집계',safe(pb?.value)]])+'<p>홈런 외 타구의 안타 비율입니다. 수비와 환경도 영향을 줍니다. DIPS는 이런 영향을 구분하려는 관점이며 운을 완전히 제거하는 계산법은 아닙니다.</p>'+(legacy?'<p class="assumption">원본 가정: 투수 BABIP를 리그 '+safe(s.reference?.BABIP)+'로 고정. 타자의 원본 보정 BABIP '+safe(s.batter_adjusted?.BABIP)+'. 희생플라이 결측을 0으로 처리하는 원본 규칙은 관측값과 구분합니다.</p>':'<p class="caption">현재 사건 모형은 허용 안타 종류를 직접 반영합니다. 수비의 인과 효과를 따로 추정한 것은 아닙니다.</p>');
 const stages=[['타자 기록',br],['타자 보정',ba],['투수 보정',pa],['리그 기준',lr],['추첨 확률',q]];
 $('calcBody05').innerHTML='<h3>'+label+' 확률은 '+pct(q)+'</h3><div class="stagebars">'+stages.map(([t,v])=>'<div><span>'+t+'</span><i><b style="width:'+Math.min(100,100*(v??0))+'%"></b></i><strong>'+safe(v)+'</strong></div>').join('')+'</div><div class="formula">'+(legacy?'이항 Log5 = (b×p/l) ÷ (b×p/l + (1−b)×(1−p)/(1−l))':'사건 가중치 = 보정 타자 × 보정 투수 ÷ 리그<br>추첨 확률 = 사건 가중치 ÷ 전체 가중치 합')+'</div>'+(legacy?'<p class="caption">원본 결합값 '+safe(s.claimed_binary?.[key])+' → 삼진·볼넷·홈런 순서의 구간을 적용한 최종 확률 '+pct(q)+'</p>':'<p class="caption">전체 가중치 합 '+(s.normalizer?.toFixed(6)??'리그 빈도')+' · 모든 사건 확률 합계 '+pct(Object.values(r.model.probabilities).reduce((a,z)=>a+z,0))+'</p>');
 const n=r.simulation.counts[event],band=r.simulation.sampling_bands[event];
 $('calcBody06').innerHTML='<div class="calc-numbers"><div><small>'+nn+'타석 예상 '+label+'</small><strong>'+(nn*q).toFixed(1)+'개</strong></div><div><small>이번 추첨</small><strong>'+n+'개</strong></div><div><small>별도 '+r.simulation.repetitions+'회 반복의 중앙 95%</small><strong>'+band.range_95.join('~')+'개</strong></div></div><p>다시 대결하면 확률은 같고 표본은 달라집니다. 같은 결과 재현은 당시 추첨 순서를 복원합니다.</p>';
 const v=r.validation;
 $('calcBody07').innerHTML='<p>예상 '+pct(q)+' / 이번 '+n+'÷'+nn+' = '+pct(n/nn)+'. 타석을 분모로 한 비율입니다.</p>'+(v&&!r.validation_warning?'<h3>MLB '+b.season+' · 나중 날짜의 기록으로 검사</h3>'+table(['방식','로그손실 ↓','Brier ↓'],['league','batter','log5'].map(k=>[({league:'리그 빈도',batter:'타자만',log5:'타자+투수'})[k],v.comparison[k].test.log_loss.toFixed(4),v.comparison[k].test.brier.toFixed(4)]))+'<p class="caption">모형 만들기 '+esc(v.split.fit.dates.join('~'))+' · 최종 검사 '+esc(v.split.test.dates.join('~'))+' / '+num(v.split.test.n)+'타석. '+(v.strength_policy?'2024에서 고른 강도 '+v.strength_policy.strength+'을 고정한 회고 검사.':'중간 기간으로 보정량을 선택.')+' 시즌 전체 프로필의 개별 맞대결 예측을 보증하는 검사는 아닙니다.</p><h3>안타 확률 교정</h3>'+table(['검사 표본','예상 안타 비율','실제 안타 비율'],v.comparison.log5.test.hit_calibration.filter(x=>x.n).map(x=>[num(x.n),pct(x.predicted_sum/x.n),pct(x.observed_sum/x.n)])):'<p class="assumption">'+esc(r.validation_warning||'KBO의 외부 예측 검사와 시대 간 공정성 검사는 아직 없습니다. 원본 210조건 재현은 계산 일치 검사입니다.')+'</p>');
 $('modelDifferences').innerHTML=comparisonTable(r);
}
function comparisonTable(r){const alt=r?.comparison,legacy=r?.model.model==='legacy',a=legacy?r?.model:alt,z=legacy?alt:r?.model;
 const rows=[['사건 결합','이항 Log5 + 순서 분기','전체 사건 가중치 정규화','겹치지 않는 확률 합계 100%','구조 검사'],['사구','별도 사건 없음','별도 사건으로 분리','볼넷·안타와 구분','KBO HP 원천 정의 미확인'],['이적 선수','자격을 충족한 첫 팀 행','선수 ID·시즌의 팀 행 합산','한 시즌 기록 누락·중복 방지','중복·결측 검사'],['시대 보정','통산 / 해당 시즌 비율','상대 빈도를 기준 리그로 이동','시즌 환경 비교','시대 공정성 외부 검증 전'],['투수 BABIP','리그 평균으로 고정','관측 허용 안타 구성 사용','고정 가정을 줄임','인과 분리 검증 전'],['표본 안정화','사건별 고정 상수','MLB 기간 검사로 강도 선택','희소 기록의 극단값 완화','KBO 강도는 별도 검증 전']];
 let html='<div class="tablewrap">'+table(['항목','기존 계산','개선된 계산','왜 달라졌나','확인 범위'],rows)+'</div>';
 if(a&&z)html+='<h3>같은 선수에서 실제로 달라진 확률</h3><div class="tablewrap">'+table(['사건','기존 계산','개선된 계산','차이'],events.map(e=>[labels[e],pct(a.probabilities[e]),pct(z.probabilities[e]),((z.probabilities[e]-a.probabilities[e])*100).toFixed(2)+'%p']))+'</div>';
 else if(r)html+='<p class="caption">'+esc(r.comparison_error||'이 자료에는 두 방식을 같은 선수에 적용할 비교 기록이 없습니다. MLB 예측 검사는 위의 리그/타자/타자+투수 비교를 사용합니다.')+'</p>';
 return html;
}
