"""Bounded official-source snapshots; no implicit eligibility for AI training."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import re
import hashlib
import unicodedata
from baseball_lab.data.protection import open_private,private

ALLOWED_HOSTS={'www.retrosheet.org','npb.jp'}

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urlparse(newurl)
        if p.scheme!='https' or p.hostname not in ALLOWED_HOSTS or p.username or p.port not in (None,443):
            raise ValueError('공식 제공자 밖 이동 거부')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url,path,limit=2*1024*1024):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ALLOWED_HOSTS or p.username or p.port not in (None,443):raise ValueError('공식 HTTPS 원천만 허용')
    path=Path(path)
    if path.exists():raise FileExistsError('기존 원본 덮어쓰기 금지')
    partial=path.with_suffix(path.suffix+'.part')
    if partial.exists() or partial.is_symlink():raise FileExistsError('기존 임시 원본 덮어쓰기 금지')
    try:
        with urllib.request.build_opener(Redirect()).open(url,timeout=45) as response,open_private(partial) as out:
            expected=response.headers.get('Content-Length')
            n=0
            while chunk:=response.read(1024*1024):
                n+=len(chunk)
                if n>limit:raise ValueError('원본 크기 한도 초과')
                out.write(chunk)
            if expected is not None and n!=int(expected):raise ValueError('원본 다운로드가 중간에 끊겼습니다.')
        partial.replace(path);private(path)
    finally:partial.unlink(missing_ok=True)

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tables=[];self.table=None;self.row=None;self.cell=None;self.link=None;self.rows=[];self.depth=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.table=[]
        if not self.depth:return
        if tag=='tr':self.row=[]
        if tag in ('th','td'):self.cell=[];self.link=None
        if tag=='a' and self.cell is not None:self.link=a.get('href')
        if tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('th','td') and self.cell is not None and self.row is not None:
            self.row.append({'text':re.sub(r'\s+',' ',' '.join(self.cell)).strip(),'href':self.link});self.cell=None
        if tag=='tr' and self.row is not None and self.table is not None:self.table.append(self.row);self.row=None
        if tag=='table' and self.depth:
            self.depth-=1
            if self.depth==0:self.tables.append(self.table);self.table=None

NPB_FIELDS={'試合':'G','打席':'PA','打数':'AB','得点':'R','安打':'H','二塁打':'2B','三塁打':'3B','本塁打':'HR','塁打':'TB','打点':'RBI','盗塁':'SB','盗塁刺':'CS','犠打':'SH','犠飛':'SF','四球':'BB','故意四':'IBB','死球':'HBP','三振':'SO','併殺打':'GDP','セ｜ブ':'SV','ホ｜ル':'HLD','完封勝':'SHO','ボ｜ク':'BK','勝利':'W','敗北':'L','セーブ':'SV','ホールド':'HLD','暴投':'WP','ボーク':'BK','完投':'CG','完封':'SHO','打者':'TBF','被安打':'H','被本塁打':'HR','奪三振':'SO','失点':'R','自責点':'ER'}

def npb_counts(fields):
    counts={}
    for key,value in fields.items():
        canonical='G' if key=='登板' else NPB_FIELDS.get(key)
        if canonical and re.fullmatch(r'\d+',value):counts[canonical]=int(value)
    for h in ('投球回','回数'):
        if h not in fields:continue
        m=re.fullmatch(r'(\d+)(?:\s*(?:\.([12])|([12])/3))?',fields[h])
        if not m:raise ValueError('NPB 이닝 정수부 확인 실패')
        fraction=re.sub(r'\s+','',fields.get('', ''))
        if fraction not in ('','1/3','2/3','.1','.2'):raise ValueError('NPB 이닝 분수 확인 실패')
        if (m[2] or m[3]) and fraction:raise ValueError('NPB 이닝 분수 중복')
        outs=int(m[2] or m[3] or 0)+(int(fraction[-1] if fraction.startswith('.') else fraction[0]) if fraction else 0)
        counts['IP_OUTS']=int(m[1])*3+outs
    return counts

def parse_npb(text,season,role,conference,source_sha256):
    parser=Tables();parser.feed(text);found=[]
    for table in parser.tables:
        if not table:continue
        headers=[re.sub(r'\s+','',x['text']) for x in table[0]]
        if not headers or headers[0]!='チーム' or '試合' not in headers:continue
        for cells in table[1:]:
            if len(cells)!=len(headers):raise ValueError('NPB 통계 열 수 불일치')
            fields={h:c['text'] for h,c in zip(headers,cells)};counts=npb_counts(fields)
            href=cells[0]['href'] or ''
            teamid=href.rsplit('/',1)[-1].removesuffix('.html')
            if not re.fullmatch(r'id[bp]1_[a-z0-9]+',teamid):raise ValueError('NPB 팀 원천 ID 확인 실패')
            found.append({'league':'NPB','season':season,'role':role,'granularity':'team_season','source_namespace':'npb-official','source_team_id':conference+':'+teamid.split('_',1)[1],'team':cells[0]['text'],'row_kind':'season_total','counts':counts,'source_fields':fields,'source_sha256':source_sha256})
    if len(found)!=6:raise ValueError(f'NPB {season}/{conference}/{role}: 예상 6팀과 다름 ({len(found)})')
    return found


def parse_npb_players(text,season,role,team_id,source_sha256):
    """Team-table rows, including non-qualified players; names are not official IDs."""
    parser=Tables();parser.feed(text);found=[];seen=set()
    for table in parser.tables:
        if not table:continue
        headers=[re.sub(r'\s+','',x['text']) for x in table[0]]
        if not headers or headers[0]!='選手' or not {'試合','登板'}.intersection(headers):continue
        for cells in table[1:]:
            if len(cells)!=len(headers):raise ValueError('NPB 선수 통계 열 수 불일치')
            fields={h:c['text'] for h,c in zip(headers,cells)}
            name=unicodedata.normalize('NFKC',fields['選手']).strip()
            if not name or name in seen:raise ValueError('NPB 선수 이름 누락/중복')
            seen.add(name)
            local_id=f'{season}:{role}:{team_id}:name:'+hashlib.sha256(name.encode()).hexdigest()[:20]
            fields['identity_status']='ROW_SCOPED_NAME_ONLY_NOT_VERIFIED_PERSON_ID'
            found.append({'league':'NPB','season':season,'role':role,'granularity':'player_season_team',
                'source_namespace':'npb-official-name-only','source_player_id':local_id,
                'player_name':fields['選手'],'identity_quality':'ROW_SCOPED_NAME_ONLY_NOT_VERIFIED_PERSON_ID',
                'team':team_id,'row_kind':'team_split','counts':npb_counts(fields),
                'source_fields':fields,'source_sha256':source_sha256})
    if not found:raise ValueError('NPB 선수 표 없음')
    return found
