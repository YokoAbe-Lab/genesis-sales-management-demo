"""Deterministic sample-only analysis. No LLM, upload, Access, or network."""
import base64
import csv
import hashlib
import io
import json
import math
import statistics as stats
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
DATASETS={'sales':('sample_sales.csv','地区別の販売実績'), 'checks':('sample_checks.csv','点検用の販売実績'), 'categories':('sample_categories.csv','数値のない相談分類')}
CHARTS={'kpi':'KPIカード','bar':'棒グラフ','horizontal':'横棒グラフ','line':'折れ線グラフ','stack':'積み上げ棒グラフ','share':'構成比グラフ','scatter':'散布図','heat':'ヒートマップ','table':'集計表','pivot':'ピボット形式の表'}
AGGS={'sum':'合計','mean':'平均','count':'件数'}
GOALS={'compare':'分類ごとの違いを比較したい','time':'期間ごとの変化を知りたい','share':'全体に占める割合を知りたい','relation':'2つの数値の関係を見たい'}
SECTIONS=[('situation','事実','現在の状況'),('reading','読み解き','グラフの見方'),('numbers','事実','数値から分かること'),('feature','事実','このグラフの最大の特徴'),('caution','事実','注意事項'),('problem','読み解き','問題定義'),('cause','推測','考えられる原因'),('action','提案','今後の対応案'),('additional','提案','追加で確認すべき資料'),('limits','事実','データの不足や限界'),('source','事実','使用したファイルと項目と条件')]
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def stamp(): return datetime.now().astimezone().isoformat(timespec='seconds')
def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError): return None
def fmt(v): return '未確認' if v is None else (f'{v:,.1f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v))
def load(dataset):
    if dataset not in DATASETS: raise ValueError('内蔵サンプルを選んでください。')
    path=ROOT/'samples'/DATASETS[dataset][0]
    raw=path.read_bytes()
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    fields=list(rows[0]) if rows else []
    return rows,{'dataset':dataset,'name':DATASETS[dataset][1],'fileName':path.name,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'table':'CSVの全行','fields':fields,'synthetic':True}
def settings(data,fields):
    defaults={'dataset':'sales','measure':'金額' if '金額' in fields else '', 'group':'地区','dateField':'日付' if '日付' in fields else '', 'secondary':'商品','aggregate':'sum' if '金額' in fields else 'count','chart':'bar','from':'','to':'','region':'全て','includeOutliers':False,'goal':'compare','audience':'業務担当者','decision':'違いを確認し、追加調査の対象を決める'}
    for k in defaults:
        if k in data: defaults[k]=data[k]
    c=defaults
    if c['dataset'] not in DATASETS or c['chart'] not in CHARTS or c['aggregate'] not in AGGS or c['goal'] not in GOALS: raise ValueError('選択条件を確認してください。')
    for k in ['group','secondary']:
        if c[k] not in fields: raise ValueError('分類項目を選んでください。')
    if c['measure'] not in ['',*([x for x in ['金額','数量'] if x in fields])]: raise ValueError('数値項目を確認してください。')
    if c['dateField'] not in ['',*(['日付'] if '日付' in fields else [])]: raise ValueError('日付項目を確認してください。')
    if not c['measure'] and c['aggregate']!='count': raise ValueError('数値項目がない場合は件数を選んでください。')
    if c['region'] not in ['全て','A地区','B地区','C地区']: raise ValueError('地区を確認してください。')
    if type(c['includeOutliers']) is not bool: raise ValueError('外れ値の扱いを確認してください。')
    for k in ['from','to']:
        if c[k]:
            date.fromisoformat(c[k])
            if not c['dateField']: raise ValueError('期間指定には日付項目が必要です。')
    if c['from'] and c['to'] and c['from']>c['to']: raise ValueError('開始日は終了日以前にしてください。')
    for k in ['audience','decision']:
        if not isinstance(c[k],str) or len(c[k])>180: raise ValueError('回答は180文字以内にしてください。')
    return c
def analyze(data):
    rows,source=load(data.get('dataset','sales'))
    c=settings(data,source['fields'])
    numeric=c['measure']
    vals=[num(r.get(numeric)) for r in rows] if numeric else []
    validvals=sorted(v for v in vals if v is not None and v>=0)
    bounds=None
    if len(validvals)>=4:
        q1,_,q3=stats.quantiles(validvals,n=4,method='inclusive')
        if q3>q1: bounds=(q1-1.5*(q3-q1),q3+1.5*(q3-q1))
    counts=Counter(r.get('ID') for r in rows if r.get('ID'))
    diag=Counter(); evidence=[]; included=[]
    for i,r in enumerate(rows,2):
        reasons=[]; warnings=[]
        axis_fields=['金額','数量'] if c['chart']=='scatter' else []
        required=['ID',c['group'],c['secondary']]+([numeric] if numeric else [])+([c['dateField']] if c['dateField'] else [])+axis_fields
        blanks=[f for f in set(required) if not r.get(f,'').strip()]
        if blanks: reasons.append('必須項目の空欄');diag['空欄・必須不足']+=1
        if r.get('ID') and counts[r['ID']]>1: reasons.append('ID重複');diag['重複']+=1
        if c['dateField'] and r.get(c['dateField']):
            try:
                d=r[c['dateField']]
                if len(d)!=10 or date.fromisoformat(d).isoformat()!=d: raise ValueError()
            except ValueError: reasons.append('日付形式の不一致');diag['日付異常']+=1
        value=num(r.get(numeric)) if numeric else 1
        if numeric and value is None: reasons.append('数値にできない値');diag['数値形式']+=1
        if any(num(r.get(f)) is None or num(r.get(f))<0 for f in axis_fields if f!=numeric):
            reasons.append('散布図の軸項目が不正');diag['数値形式']+=1
        if numeric and value is not None:
            if value<0: reasons.append('負の値は今回のサンプル仕様外');diag['対象外の値']+=1
            elif bounds and not bounds[0]<=value<=bounds[1]:
                warnings.append('外れ値候補');diag['外れ値候補']+=1
                if not c['includeOutliers']: reasons.append('外れ値候補を保留')
        if r.get('状態')!='対象': reasons.append('状態が対象外');diag['対象外の値']+=1
        filtered=False
        if not reasons:
            d=r.get(c['dateField'],'')
            filtered=bool((c['from'] and d<c['from']) or (c['to'] and d>c['to']) or (c['region']!='全て' and r.get('地区')!=c['region']))
        item={'line':i,'values':r,'included':not reasons and not filtered,'reasons':reasons or (['抽出条件の対象外'] if filtered else []),'warnings':warnings,'number':value}
        evidence.append(item)
        if item['included']: included.append(item)
    groups=defaultdict(list); matrix=defaultdict(list)
    temporal=c['chart']=='line'
    if temporal and not c['dateField']: raise ValueError('折れ線グラフには日付項目が必要です。')
    for item in included:
        r=item['values']; key=r[c['dateField']][:7] if temporal else r[c['group']]
        groups[key].append(item)
        matrix[(key,r[c['secondary']])].append(item)
    def agg(items):
        if c['aggregate']=='count': return len(items)
        values=[i['number'] for i in items]
        return sum(values) if c['aggregate']=='sum' else (stats.mean(values) if values else None)
    series=[{'label':k,'value':agg(v),'lines':[i['line'] for i in v]} for k,v in sorted(groups.items())]
    mcols=sorted({b for a,b in matrix})
    cross=[{'label':s['label'],'values':[agg(matrix[(s['label'],b)]) if matrix[(s['label'],b)] else None for b in mcols]} for s in series]
    if c['chart'] in ['share','stack'] and c['aggregate']=='mean': raise ValueError('平均は足し合わせられません。構成比・積み上げでは合計か件数を選んでください。')
    if c['chart']=='stack' and c['group']==c['secondary']: raise ValueError('積み上げの色分けには別の分類項目を選んでください。')
    if c['chart']=='scatter' and not all(x in source['fields'] for x in ['金額','数量']): raise ValueError('散布図には数量と金額の2つの数値が必要です。')
    iv=[i['number'] for i in included] if numeric else []
    summary={'count':len(included),'sum':sum(iv) if iv else None,'max':max(iv) if iv else None,'min':min(iv) if iv else None,'mean':stats.mean(iv) if iv else None,'median':stats.median(iv) if iv else None,'categories':len(groups),'excluded':len(rows)-len(included)}
    total=sum(s['value'] for s in series if s['value'] is not None) if c['aggregate']!='mean' else None
    ranked=sorted(series,key=lambda s:s['value'],reverse=True)
    feature='対象データがありません。条件とデータ点検結果を確認してください。'
    featureEvidence={'item':'月' if temporal else c['group'],'value':None,'total':total,'share':None,'conditions':c,'source':source['fileName'],'lines':[]}
    if ranked:
        top=ranked[0]; tie=len(ranked)>1 and abs(top['value']-ranked[1]['value'])<=max(abs(top['value'])*.05,1e-9)
        share=top['value']/total*100 if total and total>0 else None
        featureEvidence.update(value=top['value'],share=share,lines=top['lines'])
        if tie: feature='明確な一つの特徴は確認できません。上位の項目が近い値です（差が5%以内）。'
        elif temporal:
            feature=f"{top['label']}が最大で、{AGGS[c['aggregate']]}は{fmt(top['value'])}です。"
        elif share is not None: feature=f"{top['label']}が最も多く、全体の{share:.1f}パーセントを占めています。"
        else: feature=f"{top['label']}の平均が最も大きく、{fmt(top['value'])}です。平均の構成比は計算しません。"
    if c['chart']=='scatter' and included:
        xs=[num(i['values']['数量']) for i in included];ys=[num(i['values']['金額']) for i in included]
        spread=f"数量は{fmt(min(xs))}～{fmt(max(xs))}個、金額は{fmt(min(ys))}～{fmt(max(ys))}円"
        feature=spread+'に分布しています。因果関係は未確認です。'
        featureEvidence.update(item='数量 × 金額',value=spread,total=None,share=None,lines=[i['line'] for i in included])
    cards=[]
    def card(label,value,unit=''): cards.append({'label':label,'value':fmt(value),'unit':unit})
    unit='円' if numeric=='金額' else '個' if numeric=='数量' else '件'
    if temporal and series:
        latest=series[-1]; card('最新月の'+AGGS[c['aggregate']],latest['value'],'件' if c['aggregate']=='count' else unit)
        year,month=map(int,latest['label'].split('-')); prev=f'{year if month>1 else year-1}-{month-1 if month>1 else 12:02}'
        prior=next((s for s in series if s['label']==prev),None)
        ratio=(latest['value']/prior['value']-1)*100 if prior and prior['value'] else None
        card('前月比',None if ratio is None else round(ratio,1),'%' if ratio is not None else '比較可能な前月なし')
        chart_unit='件' if c['aggregate']=='count' else unit
        card('月別最大',max(s['value'] for s in series),chart_unit);card('月別最小',min(s['value'] for s in series),chart_unit)
        card('月別平均',stats.mean(s['value'] for s in series),chart_unit)
        card('前月からの変化','増加' if ratio is not None and ratio>0 else '減少' if ratio is not None and ratio<0 else '同じ' if ratio==0 else None)
    elif not numeric or c['chart']=='share' or c['aggregate']=='count':
        card('対象件数',len(included),'件');card('カテゴリ数',len(groups),'種類')
        card('最多カテゴリ',ranked[0]['label'] if ranked else None);card('最少カテゴリ',ranked[-1]['label'] if ranked else None)
        if not numeric: card('空欄のある行',diag['空欄・必須不足'],'行');card('重複に該当する行',diag['重複'],'行')
        else: card('最大構成比',round(featureEvidence['share'],1) if featureEvidence['share'] is not None else None,'%')
    else:
        for title,key in [('合計値','sum'),('最大値','max'),('最小値','min'),('平均値','mean'),('中央値','median')]: card(title,summary[key],unit)
        card('対象件数',len(included),'件')
    recommend={'compare':('bar','分類ごとの大小を比較するため、棒グラフを推薦します。'),'time':('line','日付ごとの変化を見るため、折れ線グラフを推薦します。'),'share':('share','全体に占める割合を見るため、構成比グラフを推薦します。'),'relation':('scatter','2つの数値の関係を見るため、散布図を推薦します。')}[c['goal']]
    if (recommend[0]=='line' and not c['dateField']) or (recommend[0]=='scatter' and not numeric): recommend=('bar','必要な日付または数値がないため、件数の棒グラフを推薦します。')
    if recommend[0]=='share' and c['aggregate']=='mean': recommend=('bar','平均値は足し合わせられないため、平均の大小を比べる棒グラフを推薦します。')
    dates=[i['values'][c['dateField']] for i in included] if c['dateField'] else []
    period=f'{min(dates)} ～ {max(dates)}' if dates else '日付なし／対象なし'
    conditions=f"{c['group']}別・{numeric or '行'}の{AGGS[c['aggregate']]}・地区 {c['region']}・期間 {c['from'] or '指定なし'} ～ {c['to'] or '指定なし'}"
    issues=sum(bool(i['reasons'] or i['warnings']) for i in evidence)
    text={
      'situation':f"架空の{source['name']} {len(rows)}行のうち、条件と点検を満たした{len(included)}行を分析しました。対象期間は{period}です。",
      'reading':f"{CHARTS[c['chart']]}で、{('月' if temporal else c['group'])}ごとの{numeric or '行'}の{AGGS[c['aggregate']]}を示します。"+('点は数量と金額の組合せです。点の並びだけで原因は判断できません。' if c['chart']=='scatter' else '単位と対象条件を確認して比較してください。'),
      'numbers':f"対象行の{numeric}は合計{fmt(summary['sum'])}{unit}、最大{fmt(summary['max'])}{unit}、最小{fmt(summary['min'])}{unit}、平均{fmt(summary['mean'])}{unit}です。" if numeric else f"対象は{len(included)}行、分類は{len(groups)}種類です。数値項目がないため、金額などの平均は計算していません。",
      'feature':feature,
      'caution':f"点検で注意・対象外となった行は{issues}行です。条件による除外を含め{summary['excluded']}行を集計から外しました。空欄と0は区別し、ID重複は該当する全行を除外しています。外れ値候補は{'含めています' if c['includeOutliers'] else '保留しています'}。",
      'problem':f"判断したいことは「{c['decision'] or '未回答'}」です。分類や期間の違いを比較するための資料です。差があることだけで業務上の問題とは確定できません。",
      'cause':'原因は未確認です。対象の構成、取扱量、集計範囲などが影響している可能性はありますが、このデータだけで因果関係を断定しません。',
      'action':'根拠の行と集計条件を確認し、比較の目的に合うかを判断してください。大きな差がある分類は、追加資料と合わせて調査する案が考えられます。',
      'additional':'比較する前期間の資料、分類の定義、対象外とした行の扱い、実際の取扱量や件数を確認してください。',
      'limits':'全て架空サンプルです。実際の売上・相談実績を示しません。外れ値は四分位範囲の1.5倍を使う確認候補で、誤りの確定ではありません。文章はローカルの定型処理で作成し、AIへの通信は行っていません。',
      'source':f"{source['fileName']}／{source['table']}。項目 {numeric or '件数'}・{c['group']}・{c['dateField'] or '日付なし'}。条件 {conditions}。SHA-256 {source['sha256']}。"
    }
    if c['chart']=='scatter':
        text['reading']='横軸は数量（個）、縦軸は金額（円）です。1つの点が元データの1行を表します。重なる点があります。点の並びだけで原因は判断できません。'
        text['source']+=' 散布図の使用項目は数量・金額です。'
    prior_info={'status':'比較元なし','changed':None}
    if c['dataset']=='sales':
        p=ROOT/'samples/sample_previous.csv';old=list(csv.DictReader(io.StringIO(p.read_text(encoding='utf-8-sig'))))
        before={r['ID']:r for r in old};after={r['ID']:r for r in rows}
        prior_info={'status':'架空の前回ファイルと比較','added':len(after.keys()-before.keys()),'removed':len(before.keys()-after.keys()),'changed':sum(before[k]!=after[k] for k in before.keys()&after.keys()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'fileName':p.name}
    return {'config':c,'source':source,'period':period,'conditions':conditions,'summary':summary,'cards':cards,'series':series,'matrix':cross,'matrixColumns':mcols,'feature':feature,'featureEvidence':featureEvidence,'diagnostics':dict(diag),'qualityRows':issues,'evidence':evidence,'generated':text,'recommendation':{'chart':recommend[0],'reason':recommend[1],'engine':'ローカル推薦（AI未接続）'},'priorData':prior_info,'calculatedAt':stamp(),'sections':SECTIONS,'chartNames':CHARTS,'unit':unit,'testCaseIds':['AN-T01','AN-T02','AN-T03','AN-T04','AN-T05','AN-T06']}

FONT=next((p for p in [Path('C:/Windows/Fonts/meiryo.ttc'),Path('C:/Windows/Fonts/YuGothM.ttc')] if p.exists()),None)
def chart_png(a):
    """One renderer shared by Web and exported documents."""
    im=Image.new('RGB',(1100,520),'white');d=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype(str(FONT),n) if FONT else ImageFont.load_default()
    def text(x,y,t,n=18,fill='#1e384b',anchor=None): d.text((x,y),str(t),font=font(n),fill=fill,anchor=anchor)
    c=a['config'];s=a['series'];colors=['#205d88','#4f8fb8','#8db6d0','#386677','#789cab','#a7c6d7']
    chart_title='散布図   数量 × 金額（1行1点）' if c['chart']=='scatter' else CHARTS[c['chart']]+'   '+('月別' if c['chart']=='line' else c['group'])+'／'+AGGS[c['aggregate']]
    text(30,15,chart_title,24)
    text(30,49,'架空データ  |  '+a['conditions'],14,'#445967')
    if not s: text(550,240,'対象データがありません',26,anchor='mm')
    elif c['chart']=='kpi':
        for j,k in enumerate(a['cards']):
            x=30+(j%3)*355;y=100+(j//3)*175
            d.rounded_rectangle((x,y,x+330,y+140),12,fill='#f0f6fa',outline='#a9c2d3')
            text(x+20,y+18,k['label'],20);text(x+20,y+60,k['value']+k['unit'],30)
    elif c['chart'] in ['table','pivot','heat']:
        pivot=c['chart']!='table';cols=a['matrixColumns'] if pivot else [AGGS[c['aggregate']]]
        vals=[r['values'] for r in a['matrix']] if pivot else [[r['value']] for r in s]
        cellw=min(230,800/max(len(cols),1));cellh=min(62,360/(len(s)+1))
        maxv=max([v for row in vals for v in row if v is not None] or [1]) or 1
        for j,t in enumerate(['分類']+cols):
            x=60+j*cellw;d.rectangle((x,95,x+cellw,95+cellh),fill='#e8f1f7');text(x+10,105,t,18)
        for i,r in enumerate(s):
            y=95+(i+1)*cellh;text(70,y+10,r['label'],18)
            for j,v in enumerate(vals[i]):
                x=60+(j+1)*cellw
                fill='#f4f8fa' if c['chart']!='heat' or v is None else (int(238-160*v/maxv),int(246-90*v/maxv),int(251-45*v/maxv))
                d.rectangle((x,y,x+cellw,y+cellh),fill=fill,outline='white')
                text(x+10,y+10,fmt(v),18,fill='#122e40')
    elif c['chart']=='share':
        total=sum(r['value'] for r in s)
        if total<=0: text(200,200,'正の合計がないため構成比は表示しません',24)
        else:
            angle=-90
            for j,r in enumerate(s):
                span=r['value']/total*360;d.pieslice((65,95,465,495),angle,angle+span,fill=colors[j%len(colors)]);angle+=span
                d.rectangle((520,110+j*54,540,130+j*54),fill=colors[j%len(colors)])
                text(555,104+j*54,f"{r['label']}  {r['value']/total*100:.1f}%  ({fmt(r['value'])})",22)
            d.ellipse((178,208,352,382),fill='white');text(265,285,'構成比',25,anchor='mm')
    elif c['chart']=='scatter':
        points=[(num(e['values'].get('数量')),num(e['values'].get('金額'))) for e in a['evidence'] if e['included']]
        points=[(x,y) for x,y in points if x is not None and y is not None]
        xmax=max([x for x,y in points] or [1]) or 1;ymax=max([y for x,y in points] or [1]) or 1
        d.line((105,100,105,430,1035,430),fill='#446d86',width=2)
        for x,y in points:
            px=115+x/xmax*880;py=423-y/ymax*300;d.ellipse((px-6,py-6,px+6,py+6),fill=colors[0],outline='white')
        text(550,465,'数量（個）',18);text(35,85,'金額（円）',18)
        for k in range(5): text(95,423-k*75,fmt(ymax*k/4),14,anchor='rm');text(115+k*220,440,fmt(xmax*k/4),14,anchor='mm')
    else:
        horizontal=c['chart']=='horizontal';stack=c['chart']=='stack';line=c['chart']=='line'
        vmax=max([r['value'] for r in s] or [1]) or 1
        if horizontal:
            for j,r in enumerate(s):
                y=105+j*min(100,340/len(s));text(155,y+16,r['label'],20,anchor='rm')
                width=r['value']/vmax*650;d.rectangle((180,y,180+width,y+34),fill=colors[0]);text(195+width,y+4,fmt(r['value']),19)
        else:
            for k in range(5):
                y=430-k*78;d.line((105,y,1040,y),fill='#c6d7e3');text(94,y,fmt(vmax*k/4),15,anchor='rm')
            step=900/max(len(s),1);positions=[]
            for j,r in enumerate(s):
                x=120+(j+.5)*step;h=r['value']/vmax*310;y=430-h;positions.append((x,y))
                if stack:
                    bottom=430
                    for k,v in enumerate(a['matrix'][j]['values']):
                        ht=(v or 0)/vmax*310;d.rectangle((x-step*.26,bottom-ht,x+step*.26,bottom),fill=colors[k%len(colors)]);bottom-=ht
                elif not line: d.rounded_rectangle((x-step*.26,y,x+step*.26,430),4,fill=colors[0])
                text(x,450,r['label'],18,anchor='mm');text(x,y-16,fmt(r['value']),17,anchor='mm')
            if line:
                if len(positions)>1:d.line(positions,fill=colors[0],width=4)
                for x,y in positions:d.ellipse((x-5,y-5,x+5,y+5),fill=colors[0])
            if stack:
                for k,t in enumerate(a['matrixColumns']):text(180+k*190,483,'■ '+t,16,colors[k%len(colors)])
        text(960,72,'単位：'+('件' if c['aggregate']=='count' else a['unit']),16)
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()
def for_browser(a):
    return {**a,'chartImage':'data:image/png;base64,'+base64.b64encode(chart_png(a)).decode()}
