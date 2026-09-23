"""일회성 조사 도구: 라벨된 클립 전체로 증거별 정밀도·임계 스윕·가중치 시뮬레이션 (plan-pvp.md §2.10).

usage: PYTHONIOENCODING=utf-8 python scripts/probe/eval_signal_precision.py
"""
import json,glob,os,collections
import numpy as np
cl=[]
for f in glob.glob('C:/Users/tester/Videos/LumiaBriefingRoom/clips/*.json'):
    d=json.load(open(f,encoding='utf-8')); d['id']=os.path.basename(f)[:-5]; cl.append(d)
P=[c for c in cl if c['userLabel']=='pvp']; V=[c for c in cl if c['userLabel']=='pve']
print('n',len(cl),len(P),len(V), 'conflict',sum(bool(c.get('labelConflict')) for c in cl))
def has(c,s): return s in (c.get('pvpSignals') or [])
def tag(c,t): return t in c['tags']
print('--- by tag (pvp,pve, precision)')
for t in ['kill','assist','death','teammate_death','no_result']:
    a=sum(tag(c,t) for c in P); b=sum(tag(c,t) for c in V); print(t,a,b,round(a/(a+b),2) if a+b else None)
# kill/assist
ka=lambda c: c['killDelta']>0 or c['assistDelta']>0
print('kill/assist',sum(ka(c) for c in P),sum(ka(c) for c in V))
# death only (no kill/assist)
def only(c,t): return tag(c,t) and not ka(c)
for name,fn in [('death(no k/a)',lambda c: c['died'] and not ka(c)),('teammate_death(no k/a,no death)',lambda c: tag(c,'teammate_death') and not ka(c) and not c['died'])]:
    print(name,sum(fn(c) for c in P),sum(fn(c) for c in V))
# teammate death by day
for lo,hi in [(1,2),(3,9)]:
    fn=lambda c:(tag(c,'teammate_death') and not ka(c) and not c['died'] and c.get('gameDay') and lo<=c['gameDay']<=hi)
    print('tm_death day',lo,hi,sum(fn(c) for c in P),sum(fn(c) for c in V))
# ultimate: for clips without k/a/death evidence
rest=lambda c: not ka(c) and not c['died']
ud=lambda c: c.get('ultimateDelta')
print('--- ultimate sweep (all clips / only clips w/o k,a,death)')
for thr in [0.10,0.15,0.2,0.25,0.3,0.4]:
    for name,flt in [('all',lambda c:True),('rest',rest)]:
        a=sum(1 for c in P if flt(c) and ud(c) is not None and ud(c)>=thr); n1=sum(1 for c in P if flt(c))
        b=sum(1 for c in V if flt(c) and ud(c) is not None and ud(c)>=thr); n0=sum(1 for c in V if flt(c))
        print(thr,name,f'pvp {a}/{n1} pve {b}/{n0} prec {a/(a+b) if a+b else 0:.2f}')
# AUC of ultimate delta on all
def auc(pos,neg):
    s=sorted([(x,1) for x in pos]+[(x,0) for x in neg]); 
    r=0;rk=0
    import itertools
    ranks=np.argsort(np.argsort([x for x,_ in s]))+1
    sp=sum(ranks[i] for i,(x,l) in enumerate(s) if l==1); n1=len(pos);n0=len(neg)
    return (sp-n1*(n1+1)/2)/(n1*n0)
print('AUC ultimate all',round(auc([ud(c) or 0 for c in P],[ud(c) or 0 for c in V]),3))
print('AUC ultimate rest',round(auc([ud(c) or 0 for c in P if rest(c)],[ud(c) or 0 for c in V if rest(c)]),3), 'n', sum(rest(c) for c in P), sum(rest(c) for c in V))
# enemy ring in rest
er=lambda c:c.get('enemyRingMean')
print('AUC rings rest',round(auc([er(c) or 0 for c in P if rest(c)],[er(c) or 0 for c in V if rest(c)]),3))
# score distribution
print('--- score hist')
for name,g in [('pvp',P),('pve',V)]:
    print(name,collections.Counter(round(c['pvpScore'],1) for c in g))
# duration
print('dur median pvp/pve',np.median([c['durationSec'] for c in P]),np.median([c['durationSec'] for c in V]))
# pve with evidence
print('--- pve with k/a/death/tm evidence')
for c in V:
    if ka(c) or c['died'] or tag(c,'teammate_death'): print(c['id'],c['title'],c['tags'],c['pvpSignals'],c.get('gameDay'),'conflict' if c.get('labelConflict') else '')
print('--- pvp with score<0.6')
for c in P:
    if c['pvpScore']<0.6: print(c['id'],c['title'],c['tags'],c['pvpSignals'],c['pvpScore'],'ult',round(ud(c) or 0,2),'ring',round(er(c) or 0,2),'conflict' if c.get('labelConflict') else '')
print('=====EXTRA')
R=[c for c in cl if rest(c)]
notult=lambda c:(ud(c) or 0)<0.25
R2=[c for c in R if notult(c)]
print('rest',len(R),'rest&ult<0.25',sum(c['userLabel']=='pvp' for c in R2),sum(c['userLabel']=='pve' for c in R2))
for thr in [0.3,0.5,0.6,0.8,1.0,1.5]:
    a=sum(1 for c in R2 if c['userLabel']=='pvp' and (er(c) or 0)>=thr); b=sum(1 for c in R2 if c['userLabel']=='pve' and (er(c) or 0)>=thr)
    print('ring>=',thr,a,b)
print('AUC ring residual',round(auc([er(c) or 0 for c in R2 if c['userLabel']=='pvp'],[er(c) or 0 for c in R2 if c['userLabel']=='pve']),3))
print('AUC duration rest',round(auc([c['durationSec'] for c in R if c['userLabel']=='pvp'],[c['durationSec'] for c in R if c['userLabel']=='pve']),3))
print('AUC duration residual',round(auc([c['durationSec'] for c in R2 if c['userLabel']=='pvp'],[c['durationSec'] for c in R2 if c['userLabel']=='pve']),3))
print('AUC confidence residual',round(auc([c['detectorConfidence'] for c in R2 if c['userLabel']=='pvp'],[c['detectorConfidence'] for c in R2 if c['userLabel']=='pve']),3))
# simulate scoring
def score(c,wu=0.75,thr=0.25,wr=0.0,wd=0.9,wt=0.8,ws=0.5,wtm=0.0):
    if ka(c): return 1.0
    cand=[0]
    if c['died']: cand.append(wd)
    if tag(c,'teammate_death'): cand.append(ws if (c.get('gameDay') or 9)<=2 else wt)
    if (ud(c) or 0)>=thr: cand.append(wu)
    if wr and (er(c) or 0)>0: cand.append(wr*min((er(c) or 0)/1.5,1))
    return max(cand)
def prf(fn,t):
    tp=sum(fn(c)>=t for c in P); fp=sum(fn(c)>=t for c in V)
    return round(tp/(tp+fp),3),round(tp/len(P),3)
for name,fn in [('current',lambda c:score(c,0.6,0.15)),('thr.25 w.75',lambda c:score(c)),('thr.25 w.75 ring.5',lambda c:score(c,wr=0.5)),('thr.25 w.75 ring.6',lambda c:score(c,wr=0.6))]:
    print(name,[ (t,)+prf(fn,t) for t in (0.5,0.6,0.7,0.8)])
