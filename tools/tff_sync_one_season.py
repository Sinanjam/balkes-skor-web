#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, csv, datetime as dt, html, json, random, re, time
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

TEAM_KEYS=['BALIKESIRSPOR','BALIKESIRSPOR BALTOK','NEV SAGLIK GRUBU BALIKESIRSPOR','BALIKESIRSPOR KULUBU']
MATCH_PATTERNS=[
 'https://www.tff.org/Default.aspx?macId={id}&pageID=528',
 'https://www.tff.org/Default.aspx?pageID=528&macId={id}',
 'https://www.tff.org/Default.aspx?macId={id}&pageId=528',
 'https://www.tff.org/Default.aspx?pageId=528&macId={id}',
 'https://www.tff.org/Default.aspx?pageID=29&macId={id}',
 'https://www.tff.org/Default.aspx?macId={id}&pageID=29']
HEADERS={'User-Agent':'Mozilla/5.0 BalkesSeasonSync/1.0','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.7'}

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def norm(s):
    s=str(s or '').upper(); trans=str.maketrans({'İ':'I','ı':'I','Ğ':'G','Ü':'U','Ş':'S','Ö':'O','Ç':'C','ğ':'G','ü':'U','ş':'S','ö':'O','ç':'C'})
    return re.sub(r'\s+',' ',s.translate(trans)).strip()
def is_balkes(text):
    n=norm(text); return any(k in n for k in TEAM_KEYS)
def text_from_html(src):
    soup=BeautifulSoup(src or '', 'lxml')
    for tag in soup(['script','style','noscript']): tag.decompose()
    text=soup.get_text('\n').replace('\xa0',' ')
    text=re.sub(r'[ \t]+',' ',text); text=re.sub(r'\n{3,}','\n\n',text)
    return text.strip()
def extract_macids(s): return set(re.findall(r'macId=([0-9]+)', s or '', flags=re.I))
def extract_tff_urls(s):
    urls=set()
    for m in re.finditer(r'https?://(?:www\.)?tff\.org/[^\s"\'<>]+', s or '', flags=re.I): urls.add(html.unescape(m.group(0)))
    soup=BeautifulSoup(s or '', 'lxml')
    for a in soup.select('a[href]'):
        href=a.get('href') or ''
        if 'tff.org' in href: urls.add(href)
    cleaned=set()
    for u in urls:
        u=unquote(u)
        if 'uddg=' in u:
            qs=parse_qs(urlparse(u).query)
            if qs.get('uddg'): u=qs['uddg'][0]
        if 'tff.org' in u: cleaned.add(u.rstrip(').,;'))
    return cleaned

def load_json(path, fallback):
    if not path.exists(): return fallback
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return fallback
def dump_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def pick_season(arg, queue_path):
    if arg!='auto': return arg
    queue=load_json(queue_path,{})
    for st in ['missing','partial','failed']:
        for season,item in queue.items():
            if (item or {}).get('status')==st: return season
    raise SystemExit('No missing/partial season left')
def planned_queries(season):
    return [f'site:tff.org/Default.aspx?macId= "Balıkesirspor" "{season}"', f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "macId"', f'site:tff.org/Default.aspx "BALIKESİRSPOR" "{season}" "Match Details"', f'site:tff.org/Default.aspx "Balıkesirspor Baltok" "{season}"', f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "Ziraat"', f'site:tff.org/Default.aspx "Balıkesirspor" "{season}" "Puan"']
def search_query(query, out):
    url='https://duckduckgo.com/html/?q='+quote_plus(query)
    r=requests.get(url, headers=HEADERS, timeout=40)
    safe=re.sub(r'[^A-Za-z0-9_.-]+','_',query)[:120]
    out.mkdir(parents=True, exist_ok=True); (out/f'search_{safe}.html').write_text(r.text, encoding='utf-8')
    ids=set()
    for u in extract_tff_urls(r.text): ids |= extract_macids(u)
    return ids
def existing_ids_for_season(data_dir, season):
    ids=set(); sdir=data_dir/'seasons'/season
    for p in sdir.glob('matches/*.json'):
        if p.stem.isdigit(): ids.add(p.stem)
    idx=load_json(sdir/'matches_index.json', [])
    if isinstance(idx, list):
        for m in idx:
            mid=str(m.get('id',''))
            if mid.isdigit(): ids.add(mid)
    return ids
def date_to_season(date_iso):
    try: y,m,d=map(int,date_iso.split('-'))
    except Exception: return ''
    return f'{y}-{y+1}' if m>=7 else f'{y-1}-{y}'
def parse_date_time(text):
    m=re.search(r'\b([0-3]?\d)[./]([01]?\d)[./]((?:19|20)\d{2})\b', text)
    date_iso=''; date_display=''
    if m:
        dd,mm,yy=int(m.group(1)),int(m.group(2)),int(m.group(3)); date_iso=f'{yy:04d}-{mm:02d}-{dd:02d}'; date_display=f'{dd:02d}.{mm:02d}.{yy:04d}'
    tm=re.search(r'\b([0-2]\d:[0-5]\d)\b', text); time_s=tm.group(1) if tm else ''
    if date_display and time_s: date_display=f'{date_display} - {time_s}'
    return date_iso,time_s,date_display
def parse_score_teams(text):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    for line in lines[:160]:
        if not is_balkes(line): continue
        m=re.search(r'(.+?)\s+([0-9]+)\s*[-–]\s*([0-9]+)\s+(.+)', line)
        if m: return m.group(1).strip(),m.group(4).strip(),int(m.group(2)),int(m.group(3))
    for i,line in enumerate(lines[:220]):
        m=re.search(r'\b([0-9]+)\s*[-–]\s*([0-9]+)\b', line)
        if m:
            before=lines[i-1] if i>0 else ''; after=lines[i+1] if i+1<len(lines) else ''
            if before and after and (is_balkes(before) or is_balkes(after)): return before,after,int(m.group(1)),int(m.group(2))
    return '', '', None, None
def infer_round_type(text):
    n=norm(text)
    if 'KUPA' in n or 'ZIRAAT' in n: return 'cup'
    if 'PLAY-OFF' in n or 'PLAY OFF' in n: return 'playoff'
    if 'LIG' in n: return 'league'
    return 'unknown'
def infer_week(text):
    m=re.search(r'\b([0-9]{1,2})\.\s*Hafta\b', text, flags=re.I)
    if m: return int(m.group(1)), f'{int(m.group(1))}. Hafta'
    return None, ''
def infer_competition(text):
    for line in [x.strip() for x in text.splitlines() if x.strip()][:160]:
        n=norm(line)
        if ('LIG' in n or 'KUPA' in n or 'PLAY' in n) and len(line)<140: return line
    return ''
def validate_match_id(mid, season):
    last=''
    for pat in MATCH_PATTERNS:
        url=pat.format(id=mid)
        try:
            r=requests.get(url, headers=HEADERS, timeout=35)
            if r.status_code!=200: last=f'HTTP {r.status_code}'; continue
            src=r.text; text=text_from_html(src)
            if len(text)<250: last='too short'; continue
            if not is_balkes(text): return None, {'macId':mid,'sourceUrl':url,'reason':'Balıkesirspor not found'}
            date_iso,time_s,date_display=parse_date_time(text); inferred=date_to_season(date_iso) if date_iso else ''
            if inferred and inferred != season: return None, {'macId':mid,'sourceUrl':url,'reason':f'season mismatch: {inferred}'}
            if (not inferred) and season not in text: return None, {'macId':mid,'sourceUrl':url,'reason':'season not confirmed'}
            return {'macId':mid,'url':url,'html':src,'text':text,'date':date_iso,'time':time_s,'dateDisplay':date_display}, None
        except Exception as e: last=str(e)[:200]
    return None, {'macId':mid,'sourceUrl':'','reason':last or 'not fetched'}
def make_detail(match, season):
    text=match['text']; home,away,sh,sa=parse_score_teams(text); week,stage=infer_week(text); comp=infer_competition(text); rt=infer_round_type(text)
    is_home=is_balkes(home); opponent=away if is_home else home; gf=sh if is_home else sa; ga=sa if is_home else sh
    result=''
    if gf is not None and ga is not None: result='W' if gf>ga else ('D' if gf==ga else 'L')
    score_display=f'{sh}-{sa}' if sh is not None and sa is not None else ''
    notes=[]
    if not home or not away: notes.append('Takım adları otomatik güvenle ayrıştırılamadı.')
    if not score_display: notes.append('Skor otomatik güvenle ayrıştırılamadı.')
    if not comp: notes.append('Müsabaka adı otomatik güvenle ayrıştırılamadı.')
    return {'id':match['macId'],'tffMatchId':match['macId'],'season':season,'competition':comp,'group':'','roundType':rt,'week':week,'stage':stage,'date':match['date'],'time':match['time'],'dateDisplay':match['dateDisplay'],'stadium':'','venue':'','city':'','referee':'','assistantReferees':[],'fourthOfficial':'','referees':[],'homeTeam':home,'awayTeam':away,'score':{'home':sh,'away':sa,'display':score_display,'played':True},'halfTimeScore':{'home':None,'away':None,'display':''},'events':[],'homeCoach':'','awayCoach':'','lineups':{'home':{'team':home,'starting11':[],'substitutes':[],'coach':''},'away':{'team':away,'starting11':[],'substitutes':[],'coach':''}},'source':{'name':'TFF','url':match['url']},'dataQuality':{'level':'official_tff_open_data','notes':notes},'balkes':{'isHome':bool(is_home),'opponent':opponent,'goalsFor':gf,'goalsAgainst':ga,'result':result}}
def index_from_detail(d):
    return {'id':d['id'],'season':d['season'],'competition':d.get('competition',''),'roundType':d.get('roundType','unknown'),'week':d.get('week'),'stage':d.get('stage',''),'date':d.get('date',''),'time':d.get('time',''),'dateDisplay':d.get('dateDisplay',''),'homeTeam':d.get('homeTeam',''),'awayTeam':d.get('awayTeam',''),'score':d.get('score',{}),'balkes':d.get('balkes',{}),'detailUrl':f"seasons/{d['season']}/matches/{d['id']}.json",'source':d.get('source',{'name':'TFF','url':''})}
def season_summary(index):
    s={'matches':len(index),'leagueMatches':0,'playoffMatches':0,'cupMatches':0,'wins':0,'draws':0,'losses':0,'goalsFor':0,'goalsAgainst':0,'goalDifference':0,'points':None,'finalRank':None}; pts=0
    for m in index:
        rt=m.get('roundType')
        if rt=='league': s['leagueMatches']+=1
        elif rt=='playoff': s['playoffMatches']+=1
        elif rt=='cup': s['cupMatches']+=1
        b=m.get('balkes') or {}; gf=b.get('goalsFor'); ga=b.get('goalsAgainst')
        if gf is not None and ga is not None:
            s['goalsFor']+=int(gf); s['goalsAgainst']+=int(ga)
            if int(gf)>int(ga): s['wins']+=1; pts+=3
            elif int(gf)==int(ga): s['draws']+=1; pts+=1
            else: s['losses']+=1
    s['goalDifference']=s['goalsFor']-s['goalsAgainst']
    if s['leagueMatches']: s['points']=pts
    return s
def update_global_indexes(data_dir):
    manifest=load_json(data_dir/'manifest.json',{}); allm=[]
    for s in manifest.get('availableSeasons',[]) or []:
        idx=load_json(data_dir/'seasons'/s.get('id','')/'matches_index.json',[])
        if isinstance(idx,list): allm+=idx
    opponents={}; search=[]
    for m in allm:
        b=m.get('balkes') or {}; opp=b.get('opponent') or ''
        if opp:
            r=opponents.setdefault(opp,{'name':opp,'matches':0,'wins':0,'draws':0,'losses':0,'goalsFor':0,'goalsAgainst':0,'lastMatchDate':'','seasons':[],'matchIds':[]})
            r['matches']+=1; r['goalsFor']+=int(b.get('goalsFor') or 0); r['goalsAgainst']+=int(b.get('goalsAgainst') or 0)
            if b.get('result')=='W': r['wins']+=1
            if b.get('result')=='D': r['draws']+=1
            if b.get('result')=='L': r['losses']+=1
            if m.get('season') not in r['seasons']: r['seasons'].append(m.get('season'))
            r['matchIds'].append(m.get('id'))
            if m.get('date') and m.get('date')>r.get('lastMatchDate',''): r['lastMatchDate']=m.get('date')
        title=f"{m.get('homeTeam','')} {m.get('score',{}).get('display','')} {m.get('awayTeam','')}".strip()
        search.append({'id':f"match_{m.get('id')}",'type':'match','season':m.get('season'),'title':title,'subtitle':f"{m.get('season')} • {m.get('competition','')} • {m.get('stage','')}",'keywords':f"{m.get('homeTeam','')} {m.get('awayTeam','')} {m.get('score',{}).get('display','')} {m.get('id')} {m.get('stage','')}"})
    players=load_json(data_dir/'players_index.json',[])
    if not isinstance(players,list): players=[]
    dump_json(data_dir/'players_index.json',players); dump_json(data_dir/'opponents_index.json',sorted(opponents.values(),key=lambda x:x['name'])); dump_json(data_dir/'search_index.json',search)
def update_manifest_and_report(data_dir, season, index, summary):
    p=data_dir/'manifest.json'; m=load_json(p,{})
    m.setdefault('app','Balkes Skor'); m['schemaVersion']=int(m.get('schemaVersion') or 2); m['dataVersion']=int(m.get('dataVersion') or 0)+1; m['appDataVersion']=int(m.get('appDataVersion') or 0)+1; m['lastUpdated']=now(); m['generatedAt']=m.get('generatedAt') or now(); m['dataBaseUrl']=m.get('dataBaseUrl') or 'https://raw.githubusercontent.com/Sinanjam/balkes-skor-web/main/docs/data/'; m.setdefault('team','Balıkesirspor'); m.setdefault('assets',{'logo':'assets/logo_balkes_skor.png'}); m.setdefault('global',{'playersIndexUrl':'players_index.json','opponentsIndexUrl':'opponents_index.json','searchIndexUrl':'search_index.json','dataReportUrl':'data_report.json'})
    seasons=[s for s in m.get('availableSeasons',[]) if s.get('id')!=season]
    seasons.append({'id':season,'name':season,'matchCount':len(index),'competition':index[0].get('competition','') if index else '', 'group':'','summary':{'matches':summary['matches'],'wins':summary['wins'],'draws':summary['draws'],'losses':summary['losses'],'goalsFor':summary['goalsFor'],'goalsAgainst':summary['goalsAgainst'],'goalDifference':summary['goalDifference'],'points':summary['points'],'finalRank':summary['finalRank']}})
    seasons.sort(key=lambda x:x.get('id',''), reverse=True); m['availableSeasons']=seasons; dump_json(p,m)
    total=sum(int(s.get('matchCount') or (s.get('summary') or {}).get('matches') or 0) for s in seasons)
    report=load_json(data_dir/'data_report.json',{})
    if not isinstance(report,dict): report={}
    report['generatedAt']=now(); report['source']='TFF açık sayfaları ve Balkes Skor season sync'; report['totalAppMatches']=total; report['seasons']=[s['id'] for s in seasons]; report.setdefault('coverage',{}); report.setdefault('validation',{})
    dump_json(data_dir/'data_report.json',report)
def update_queue(queue_path, season, status, notes):
    q=load_json(queue_path,{}) ; q.setdefault(season,{}) ; q[season]['status']=status; q[season]['notes']=notes; q[season]['updatedAt']=now(); dump_json(queue_path,q)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--season',default='auto'); ap.add_argument('--data-dir',default='docs/data'); ap.add_argument('--reports-dir',default='reports/season-sync'); ap.add_argument('--queue',default='tools/season_queue.json'); ap.add_argument('--max-search-queries',default='0'); ap.add_argument('--min-delay',type=float,default=1.8); ap.add_argument('--max-delay',type=float,default=4.5); args=ap.parse_args()
    data_dir=Path(args.data_dir); reports=Path(args.reports_dir); queue=Path(args.queue); season=pick_season(args.season,queue)
    sreport=reports/season; raw=sreport/'raw'; sreport.mkdir(parents=True,exist_ok=True); raw.mkdir(parents=True,exist_ok=True); reports.mkdir(parents=True,exist_ok=True); (reports/'LAST_SEASON.txt').write_text(season,encoding='utf-8')
    candidates=existing_ids_for_season(data_dir,season); queries=planned_queries(season); maxq=int(args.max_search_queries or 0); queries=queries[:maxq] if maxq else queries
    for q in queries:
        try: candidates |= search_query(q,sreport); time.sleep(random.uniform(args.min_delay,args.max_delay))
        except Exception as e: (sreport/'search_errors.log').open('a',encoding='utf-8').write(f'{q}\t{e}\n')
    (sreport/'candidate_macids.txt').write_text('\n'.join(sorted(candidates,key=int))+'\n',encoding='utf-8')
    good=[]; uncertain=[]
    for mid in sorted(candidates,key=int):
        match,bad=validate_match_id(mid,season)
        if match: good.append(match); (raw/f'{mid}.txt').write_text(match['text'],encoding='utf-8'); (raw/f'{mid}.html').write_text(match['html'],encoding='utf-8')
        elif bad: uncertain.append(bad)
        time.sleep(random.uniform(args.min_delay,args.max_delay))
    with (sreport/'uncertain_candidates.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['macId','sourceUrl','reason']); w.writeheader(); w.writerows(uncertain)
    if not good:
        update_queue(queue,season,'missing','No verified TFF Balıkesirspor match found in this run.'); (sreport/'SUMMARY.md').write_text(f'# {season} sync\n\nNo verified TFF Balıkesirspor matches found.\n\nUncertain candidates: {len(uncertain)}\n',encoding='utf-8'); print(f'No verified matches for {season}'); return
    details=[make_detail(m,season) for m in good]; details.sort(key=lambda x:(x.get('date') or '', int(x['id']))); index=[index_from_detail(d) for d in details]; summary=season_summary(index)
    sdir=data_dir/'seasons'/season; (sdir/'matches').mkdir(parents=True,exist_ok=True)
    for d in details: dump_json(sdir/'matches'/f"{d['id']}.json",d)
    dump_json(sdir/'matches_index.json',index); 
    if not (sdir/'standings_by_week.json').exists(): dump_json(sdir/'standings_by_week.json',[])
    dump_json(sdir/'season.json',{'id':season,'name':season,'team':{'id':'balikesirspor','name':'Balıkesirspor','tffClubId':'135'},'competition':index[0].get('competition','') if index else '','group':'','summary':summary,'files':{'matchesIndex':f'seasons/{season}/matches_index.json','standingsByWeek':f'seasons/{season}/standings_by_week.json'},'source':{'name':'TFF','note':'Açık TFF sayfalarından dönüştürülmüş veri'},'dataQuality':{'level':'official_tff_open_data','notes':['GitHub Actions season sync ile otomatik güncellendi.']}})
    update_manifest_and_report(data_dir,season,index,summary); update_global_indexes(data_dir); status='done' if len(index)>=20 else 'partial'; update_queue(queue,season,status,f'Verified {len(index)} TFF matches.')
    with (sreport/'macids_with_sources.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['season','macId','match','sourceUrl','confidence','notes']); w.writeheader()
        for d in details: w.writerow({'season':season,'macId':d['id'],'match':f"{d.get('homeTeam','')} - {d.get('awayTeam','')}",'sourceUrl':d['source']['url'],'confidence':'high','notes':'TFF maç detay sayfasında Balıkesirspor doğrulandı'})
    (sreport/'SUMMARY.md').write_text(f"# {season} sync\n\n- Verified matches: `{len(index)}`\n- Candidate macIds: `{len(candidates)}`\n- Uncertain/rejected: `{len(uncertain)}`\n- Queue status: `{status}`\n- Wins/draws/losses: `{summary['wins']}/{summary['draws']}/{summary['losses']}`\n- Goals: `{summary['goalsFor']}-{summary['goalsAgainst']}`\n\nStandings güvenle parse edilmezse `standings_by_week.json` boş dizi kalır.\n",encoding='utf-8')
    print(f'Season {season}: verified {len(index)} matches, status={status}')
if __name__=='__main__': main()
