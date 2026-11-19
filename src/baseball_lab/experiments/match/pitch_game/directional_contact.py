"""Contact-area targets are explicit model assumptions, not observed intentions."""
from collections import Counter,defaultdict
from functools import lru_cache
from importlib.resources import files
import gzip,hashlib,json,math
from baseball_lab.data.batting_directions import CONTACT,AIMS

ASSET='batting-directions-v1.json.gz'
ASSET_SHA256='d483210d14a194549578849a2a64d34d0c159102d07dc1a238ac29f3288a22d0'


@lru_cache(maxsize=1)
def directions():
    body=files('baseball_lab').joinpath('data','resources',ASSET).read_bytes()
    if hashlib.sha256(body).hexdigest()!=ASSET_SHA256:raise ValueError('타격 방향 자료 지문이 다릅니다.')
    data=json.loads(gzip.decompress(body))
    if data['schema']!='observed-batting-directions-v1' or data['source_status']!='REAL_OBSERVED':raise ValueError('실제 타구 기록이 필요합니다.')
    return data


class ContactModel:
    def __init__(self,value):
        self.value=value;self.counts={};self.pool={}
        for part,rows in value['counts'].items():
            fine=defaultdict(Counter);pool=defaultdict(Counter)
            for b,s,hand,aim,side,kind,event,n in rows:
                fine[b,s,hand,aim][side,kind,event]+=n;pool[hand,aim][side,kind,event]+=n
            self.counts[part]=fine;self.pool[part]=pool
        self.strength=min((None,10,50,200),key=lambda a:self.check('validation',a)['brier'] or 0.)
        self.metrics={p:self.check(p,self.strength) for p in ('validation','test')}

    @lru_cache(maxsize=2048)
    def distribution(self,b,s,hand,aim,strength):
        pooled=self.pool['fit'].get((hand,aim),Counter());n=sum(pooled.values())
        if not n:return {}
        base={key:v/n for key,v in pooled.items()};fine=self.counts['fit'].get((b,s,hand,aim),Counter());m=sum(fine.values())
        if strength is None or not m:return base
        return {key:(fine[key]+strength*p)/(m+strength) for key,p in base.items()}

    def check(self,part,strength):
        total=covered=0;brier=loss=0.
        for cell,counts in self.counts[part].items():
            if cell[-1] is None:continue
            total+=sum(counts.values());q=self.distribution(*cell,strength)
            if not q:continue
            norm=sum(p*p for p in q.values())
            for target,n in counts.items():
                p=q.get(target,0.);covered+=n;brier+=n*(norm-2*p+1);loss-=n*math.log(max(p,1e-12))
        return {'contact_rows':total,'covered_rows':covered,'brier':brier/covered if covered else None,'log_loss':loss/covered if covered else None}

    def legal(self,b,s,hand):
        return tuple('swing:'+aim for aim in AIMS if sum(self.counts['fit'].get((b,s,hand,aim),{}).values())>=10)

    @lru_cache(maxsize=512)
    def outcomes(self,b,s,hand,aim):
        joint=self.distribution(b,s,hand,aim,self.strength);answer=Counter()
        for (_,_,event),p in joint.items():answer[event]+=p
        return answer

    @lru_cache(maxsize=1024)
    def sample_options(self,b,s,hand,aim,event):
        if aim is not None:
            joint=self.distribution(b,s,hand,aim,self.strength)
        else:
            # Ordinary swing keeps every recorded direction, including unknown.
            joint=Counter()
            for key,counts in self.counts['fit'].items():
                if key[:3]==(b,s,hand):joint.update(counts)
            if not joint:
                for (h,a),counts in self.pool['fit'].items():
                    if h==hand:joint.update(counts)
        options={key:p for key,p in joint.items() if key[-1]==event}
        return options

    def sample(self,b,s,hand,aim,event,rng):
        options=self.sample_options(b,s,hand,aim,event)
        if not options:return {'side':None,'kind':None,'basis':'unavailable'}
        side,kind,_=rng.choices(tuple(options),weights=tuple(options.values()),k=1)[0]
        return {'side':side,'kind':kind,'basis':'modeled from native recorded contact area; not measured trajectory'}
