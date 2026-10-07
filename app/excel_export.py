"""Local report exports. Source-bearing T054 rows never enter HTML/CSV/JSON/PDF."""
import csv
import html
import json
import zipfile
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from excel_static import dump, sha_file


def csv_cell(value):
    text = str(value) if value is not None else ''
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


def safe_snapshot(run):
    return {k: v for k, v in run.items() if k not in {'exports', 'directory'}}


def report_html(run):
    esc = lambda s: html.escape(str(s))
    rows = ''.join('<tr>' + ''.join('<td>' + esc(o.get(k, '')) + '</td>' for k in ['kind', 'name', 'lineCount']) + '</tr>' for o in run['objects'])
    warnings = '、'.join(run['warnings']) or '抽出時の警告なし（実行確認ではありません）'
    return f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Genesis Excel静的解析報告書</title>
<style>body{{font:17px/1.75 "Yu Gothic",Meiryo,sans-serif;color:#173650;background:#f3f8fc;max-width:1100px;margin:40px auto;padding:24px}}h1,h2{{color:#123654}}article{{background:white;padding:24px;border:1px solid #9bb3c8;border-radius:12px;margin:20px 0}}td,th{{padding:9px;border:1px solid #a8bccb;text-align:left}}table{{border-collapse:collapse;width:100%}}.warn{{background:#fff0d9;padding:16px}}.meta{{overflow-wrap:anywhere;font-size:14px}}@page{{size:A4 landscape;margin:14mm}}@media print{{body{{margin:0;padding:0;background:white;font-size:11pt;max-width:none}}article{{break-inside:auto;padding:12px;border-radius:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style>
<h1>Genesis｜Excel静的解析報告書</h1><p>Excelとマクロを起動せず、保存されている構造を調べた結果です。</p>
<article><h2>取得結果</h2><p>判定：<strong>{esc(run['status'])}</strong>　モジュール {run['moduleCount']} 件　プロシージャ {run['procedureCount']} 件</p>
<p>原本不変：{esc(run['sourceUnchanged'])} ／ 追加API送信：0回 ／ VBA実行：0回</p>
<p class="meta">RunID：{esc(run['runId'])}<br>RequestID：{esc(run['requestId'])}<br>対象：{esc(run['fileName'])}<br>日時：{esc(run['created'])}<br>SHA-256：{esc(run['copySHA256'])}</p></article>
<article><h2>読み方と限界</h2><p>「confirmed-structure」は保存構造から確認した包含関係です。「static-candidate」はコード上の呼出候補であり、実際に実行されたことを意味しません。</p><p class="warn">{esc(warnings)}<br>診断：{esc(run['diagnostic'] or 'なし')}</p><p>VBA全文はこの報告書には含みません。sourceフォルダと明示された納品ZIPだけに含みます。Access内のT050・T051・T054への書込みは未接続です。</p></article>
<article><h2>オブジェクト一覧</h2><table><thead><tr><th>種類</th><th>名前</th><th>行数</th></tr></thead><tbody>{rows}</tbody></table></article></html>'''


def report_pdf(run, path):
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak
    font='GenesisMeiryo'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font,'C:/Windows/Fonts/meiryo.ttc',subfontIndex=0))
    base=ParagraphStyle('body07',fontName=font,fontSize=10.5,leading=16,textColor=colors.HexColor('#173650'),wordWrap='CJK',spaceAfter=5)
    head=ParagraphStyle('head07',parent=base,fontSize=19,leading=27,spaceAfter=10)
    small=ParagraphStyle('small07',parent=base,fontSize=9,leading=13)
    p=lambda t,style=base: Paragraph(html.escape(str(t)),style)
    def tab(data,widths):
        t=Table([[p(c,small) for c in row] for row in data],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E2EFF8')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#9BB3C8')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return t
    story=[p('Genesis Excel静的解析報告書',head),p('対象：'+run['fileName']+'　判定：'+run['status']),
           p(f"モジュール {run['moduleCount']}件　処理 {run['procedureCount']}件　関係 {run['relationCount']}件　原本不変：{run['sourceUnchanged']}"),
           p('RequestID：'+run['requestId'],small),p('SHA-256：'+run['copySHA256'],small),
           p('Excel起動・マクロ実行・OnAction実行なし。Access側T050・T051・T054は未接続です。',small),Spacer(1,8)]
    names={'formulas':'数式','conditionalFormats':'条件付き書式','validations':'データ入力規則','tables':'テーブル','definedNames':'定義名','filters':'フィルター','charts':'グラフ','shapes':'図形','onActions':'OnAction保存参照'}
    features=run.get('workbookFeatures',{})
    story.append(p('Excelに保存されている機能',head))
    story.append(tab([['対象','件数','確認範囲']]+[[v,features.get('counts',{}).get(k,'未取得'),'保存定義のみ確認　実行・再計算なし'] for k,v in names.items()],[200,70,490]))
    story += [Spacer(1,8),p('警告：'+('、'.join(run['warnings']) or '抽出時の警告なし')+'　診断：'+(run['diagnostic'] or 'なし'),small),
              p('解析時のAPI送信は0回です。別工程のAI API連携試験1回は、AI連携記録に実際の状態を保存します。',small),PageBreak(),p('オブジェクトと静的な関係',head)]
    data=[['種類','名前','行数','確認範囲']]
    for o in run['objects']:data.append([o['kind'],o['name'],o.get('lineCount',''),'イベント候補' if o.get('eventCandidate') else '保存構造'])
    story.append(tab(data,[145,345,55,215]))
    story+=[Spacer(1,10),p('関係の読み方',base),p('containsは保存構造の包含関係、explicit-callは静的な呼出候補です。呼出候補は実行成功の証明ではありません。VBA本文はこのPDFには含めません。',small)]
    def footer(canvas,doc):
        canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#173650'))
        canvas.drawString(40,24,run['runId']+'  '+run['created']);canvas.drawRightString(802,24,str(doc.page)+' ページ')
    SimpleDocTemplate(str(path),pagesize=landscape(A4),rightMargin=40,leftMargin=40,topMargin=25,bottomMargin=45,title='Genesis Excel静的解析報告書').build(story,onFirstPage=footer,onLaterPages=footer)



def write_exports(run, sources, folder, export):
    snapshot = safe_snapshot(run)
    builders = {
        '解析結果.html': lambda p: p.write_text(report_html(run), encoding='utf-8'),
        '解析概要.json': lambda p: dump(p, snapshot),
        'オブジェクト.csv': lambda p: write_csv(p, ['RunID', 'ObjectID', '種類', '名前', '行数', 'SHA256'],
            [[run['runId'], o['id'], o['kind'], o['name'], o.get('lineCount', ''), o.get('sourceSHA256', '')] for o in run['objects']]),
        '関係.csv': lambda p: write_csv(p, ['RunID', 'RelationID', 'FromID', 'ToID', '種類', '確実性'],
            [[run['runId'], r['id'], r['fromId'], r['toId'], r['kind'], r['certainty']] for r in run['relations']]),
        '解析報告書.pdf': lambda p: report_pdf(run, p),
    }
    # Every file has a pre-created status before the first write.
    export['files'] = [{'name': name, 'status': 'NOT_RUN', 'sha256': '', 'diagnostic': ''} for name in [*builders, '成果物ハッシュ.json', '解析一式_VBA全文を含む.zip']]
    for item in export['files']:
        name = item['name']; path = folder / name
        try:
            if name in builders:
                builders[name](path)
            elif name == '成果物ハッシュ.json':
                manifest = [{'name': x['name'], 'sha256': x['sha256'], 'status': x['status']} for x in export['files'] if x['status'] != 'NOT_RUN']
                for source in sources:
                    manifest.append({'name': 'source/' + Path(source['SourceFile']).name, 'sha256': source['SHA256'], 'status': 'LOCAL_SOURCE'})
                dump(path, {'runId': run['runId'], 'exportId': export['exportId'], 'includesRawVBA': True, 'files': manifest})
            else:
                with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
                    for prev in export['files']:
                        if prev['status'] == 'PASS':
                            z.write(folder / prev['name'], prev['name'])
                    for source in sources:
                        src = Path(source['SourceFile'])
                        if sha_file(src) != source['SHA256']:
                            raise ValueError('FROZEN_SOURCE_HASH_MISMATCH')
                        z.write(src, 'source/' + src.name)
                with zipfile.ZipFile(path) as z:
                    if z.testzip():
                        raise ValueError('ZIP_CRC_FAILED')
            item.update(status='PASS', sha256=sha_file(path))
        except Exception as ex:
            item.update(status='FAILED', diagnostic='FILE_' + type(ex).__name__.upper())


def write_csv(path, header, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(header)
        for row in rows:
            writer.writerow([csv_cell(x) for x in row])
