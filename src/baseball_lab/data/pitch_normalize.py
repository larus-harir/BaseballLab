"""Pitch observations across providers. Unknown fields stay unknown.

Current pitch measurements and terminal labels are world-model targets, never
pre-pitch policy inputs. KBO relay_text repeats a PA's future result: read it
only on the actual terminal pitch. SPAIA pixel coordinates are NOT metres.
"""
import math,re

SCHEMA='observed-multileague-pitch-v1'
FAMILIES={'FF':'fastball','FT':'sinker','SI':'sinker','FC':'cutter','SL':'slider','CU':'curve','KC':'curve',
          'CH':'changeup','FS':'splitter','KN':'knuckle',
          '직구':'fastball','포심':'fastball','투심':'sinker','싱커':'sinker','커터':'cutter',
          '슬라이더':'slider','커브':'curve','체인지업':'changeup','포크':'splitter','스플리터':'splitter'}
JAPANESE=(('カットボール','cutter'),('スライダー','slider'),('チェンジアップ','changeup'),
          ('ツーシーム','sinker'),('スプリット','splitter'),('フォーク','splitter'),
          ('ナックルカーブ','curve'),('カーブ','curve'),('ナックル','knuckle'),
          ('ストレート','fastball'),('真っ直ぐ','fastball'))
NPB_REGULAR={'1':'セ・リーグ公式戦','2':'パ・リーグ公式戦','26':'セ・パ交流戦'}


def number(v):
    try:n=float(v)
    except (ValueError,TypeError):return None
    return n if math.isfinite(n) else None


def integer(v):
    n=number(v)
    return int(n) if n is not None and n==int(n) else None


def identifier(v):
    v=str(v or '').strip()
    if v.lower() in ('','nan','none','null'):return None
    return re.sub(r'\.0+$','',v)


def hand(v):return {'R':'R','L':'L','S':'S','right':'R','left':'L','switch':'S'}.get(v)


def metric_zone(px,pz,bot,top,stand):
    if None in (px,pz,bot,top) or top<=bot or stand not in ('L','R'):return None
    horizontal='middle' if abs(px)<=17/72 else ('inside' if (px<0)==(stand=='R') else 'outside')
    height=(pz-bot)/(top-bot)
    return horizontal+'_'+('low' if height<1/3 else 'high' if height>2/3 else 'middle')


def text_zone(text):
    horizontal='inside' if '内角' in text else 'outside' if '外角' in text else 'middle' if 'ど真ん中' in text or '真ん中' in text else None
    vertical='high' if '高め' in text else 'low' if '低め' in text or 'ワンバウンド' in text else 'middle' if 'ど真ん中' in text else None
    return horizontal+'_'+vertical if horizontal and vertical else None


def final_event(text):
    if any(word in text for word in ('Double Play','Triple Play','Grounded Into DP','Sac Fly','Sac Bunt',
                                    'Fielders Choice','Catcher Interference','병살','삼중살','희생번트','희생플라이')):return 'out'
    for words,event in ((('Home Run','ホームラン','本塁打','홈런'),'home_run'),
                        (('Triple','三塁打','スリーベース','3루타'),'triple'),
                        (('Double','二塁打','ツーベース','2루타'),'double'),
                        (('Single','ヒット','安打','1루타','내야안타'),'single')):
        if any(w in text for w in words):return event
    if any(w in text for w in ('Out','out','アウト','아웃','실책','失策','Error','Choice','선택')):return 'out'
    return None


def base_flags(values):
    return sum((1<<i) for i,v in enumerate(values) if identifier(v) not in (None,'0'))


def record(*,league,source,date,game,pa,seq,inning,bottom,balls,strikes,outs,bases,pitcher,batter,
           action,event,family,location,speed,raw_type,raw_code,coord_system='not_published',
           x_m=None,z_m=None,raw_x=None,raw_z=None,runs=None,home_difference=None,bat_score=None):
    if not game or not date or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError('missing_game_or_date')
    if inning is None or bottom not in (0,1) or outs not in (0,1,2):raise ValueError('missing_pre_pitch_situation')
    if balls not in range(4) or strikes not in range(3):raise ValueError('invalid_or_ambiguous_pre_pitch_count')
    terminal=('walk' if event=='ball' and balls==3 else 'strikeout' if event=='strike' and strikes==2
              or event=='bunt_foul' and strikes==2 else event if event in ('out','single','double','triple','home_run','hbp') else None)
    missing={k:('not_published' if k in ('location','x_m','z_m') else 'not_observed_or_unresolved') for k,v in
             {'action':action,'event':event,'family':family,'location':location,'speed_mps':speed,
              'x_m':x_m,'z_m':z_m,'runs':runs}.items() if v is None}
    return {'schema':SCHEMA,'league':league,'season':int(date[:4]),'namespace':source,
        'date':date,'game':source+':'+game,'pa':source+':'+game+':'+str(pa),'sequence':seq,
        'inning':inning,'bottom':bottom,'balls':balls,'strikes':strikes,'outs':outs,'bases':bases,
        'pitcher':source+':'+str(pitcher) if pitcher else None,'batter':source+':'+str(batter) if batter else None,
        'observed_action':action,'event':event,'terminal':terminal,'pitch_family':family,'location':location,
        'speed_mps':speed if speed is not None and 0<speed<80 else None,
        'coordinate_system':coord_system,'x_m':x_m,'z_m':z_m,'raw_x':raw_x,'raw_z':raw_z,
        'raw_type':raw_type,'raw_code':raw_code,'runs':runs,'home_difference':home_difference,
        'bat_score':bat_score,'missing':missing}


def mlb(row,ab,game):
    if not ab or not game:raise ValueError('unlinked_at_bat_or_game')
    b,s=integer(row['b_count']),integer(row['s_count']);code=row['code'];event=action=None
    if code in ('B','*B','I','P'):event,action='ball','take'
    elif code=='C':event,action='strike','take'
    elif code in ('S','W','T'):event,action='strike','swing'
    elif code in ('F','R'):event,action='foul','swing'
    elif code in ('L','M'):event,action=('bunt_foul' if code=='L' else 'strike'),'bunt'
    elif code=='H':event,action='hbp','take'
    elif code in ('X','D','E'):event,action=final_event(ab['event']),'bunt' if 'Bunt' in ab['event'] else 'swing'
    px,pz,bot,top=(number(row.get(k)) for k in ('px','pz','sz_bot','sz_top'))
    velocity=number(row.get('start_speed'))
    return record(league='MLB',source='kaggle-pschale-gameday-v2',date=game['date'],game=identifier(ab['g_id']),pa=identifier(row['ab_id']),
        seq=integer(row['pitch_num']),inning=integer(ab['inning']),bottom=0 if ab['top'] in ('True','1','1.0') else 1,
        balls=b,strikes=s,outs=integer(row['outs']),bases=base_flags([row.get('on_'+str(i)+'b') for i in (1,2,3)]),
        pitcher=identifier(ab['pitcher_id']),batter=identifier(ab['batter_id']),action=action,event=event,
        family=FAMILIES.get(row['pitch_type']),location=metric_zone(px,pz,bot,top,hand(ab.get('stand'))),
        speed=velocity*.44704 if velocity else None,raw_type=row['pitch_type'],raw_code=code,
        coord_system='MLB_Gameday_plate_feet_catcher_view',x_m=px*.3048 if px is not None else None,
        z_m=pz*.3048 if pz is not None else None,raw_x=px,raw_z=pz,bat_score=number(row.get('b_score')))


def kbo(row,previous,line,game_info):
    if game_info.get('is_regular_season')!='True':raise ValueError('not_regular_season')
    code=row['pitch_result'];post_b,post_s=integer(row['ball_count_B']),integer(row['ball_count_S'])
    b,s=post_b,post_s
    # Naver pitchResult convention: T=taken strike, S=swinging strike.
    event,action={'B':('ball','take'),'T':('strike','take'),'S':('strike','swing'),
                  'F':('foul','swing'),'H':(None,'swing')}.get(code,(None,None))
    if code=='B' and b is not None:b-=1
    elif code in ('T','S') and s is not None:s-=1
    elif code=='F':
        same=previous and all(previous.get(k)==row.get(k) for k in ('batter_id','inning','home_or_away'))
        s=integer(previous['ball_count_S']) if same else 0 if post_s==1 else None
    if code=='H':
        event=final_event(row.get('relay_text',''))
        if '번트' in row.get('relay_text',''):action='bunt'
    game=row['game_id'];bottom=integer(row['home_or_away']);velocity=number(row.get('pitch_speed'))
    # No averages, WPA, relay text or current-pitch speed is a policy observation.
    return record(league='KBO',source='nextpitchh-naver-v1',date=game_info['date'],game=game,pa='row-'+str(line),
        seq=line,inning=integer(row['inning']),bottom=bottom,balls=b,strikes=s,
        outs=integer(row['out_count']),bases=base_flags([row.get('is_base'+str(i)) for i in (1,2,3)]),
        pitcher=row.get('pitcher_id'),batter=row.get('batter_id'),action=action,event=event,
        family=FAMILIES.get(row.get('pitch_type')),location=None,speed=velocity/3.6 if velocity else None,
        raw_type=row.get('pitch_type'),raw_code=code,home_difference=number(row.get('score_diff')))


def npb(row):
    if NPB_REGULAR.get(row.get('game_type_id'))!=row.get('game_type_name'):raise ValueError('not_regular_season')
    if integer(row.get('pitch_number')) is None or not row.get('pitch_id'):raise ValueError('not_a_pitch')
    text=row.get('description_jap','');code=integer(row.get('presult'));event=action=None
    if code in (118,119):event,action='ball','take'
    elif code in (117,131):event,action='strike','take'
    elif code in (116,130):event,action='strike','swing'
    elif code==101:event,action='foul','swing'
    elif code==103:event,action='hbp','take'
    elif code in (102,104,105,106):event,action={102:'single',104:'double',105:'triple',106:'home_run'}[code],'swing'
    elif code in (107,108,109,110,111,112,114,115,126):event,action='out','swing'
    if 'バント' in text or code in (114,126):
        action='bunt'
        if event=='foul':event='bunt_foul'
    family=next((v for word,v in JAPANESE if word in text),None)
    state=row.get('game_state_name','')
    bottom=0 if '表' in state else 1 if '裏' in state else None
    velocity=number(row.get('release_speed_kmh'));x=number(row.get('plate_x'));z=number(row.get('plate_y'))
    return record(league='NPB',source='armstjc-spaia-v1',date=row['game_date'][:10],game=row['game_id'],
        pa=identifier(row.get('fiveDigitSerialNumber')) or row.get('inning_ab_num'),seq=integer(row['pitch_number']),
        inning=integer(row['inning']),bottom=bottom,balls=integer(row.get('balls')),strikes=integer(row.get('strikes')),
        outs=integer(row.get('outs_when_up')),bases=base_flags([row.get('on_'+str(i)+'b') for i in (1,2,3)]),
        pitcher=identifier(row.get('pitcher')),batter=identifier(row.get('batter')),action=action,event=event,
        family=family,location=text_zone(text),speed=velocity/3.6 if velocity else None,
        raw_type=identifier(row['pitch_id']),raw_code=str(code),coord_system='SPAIA_display_pixels_unverified',
        raw_x=x,raw_z=z,runs=integer(row.get('addedRuns')))
