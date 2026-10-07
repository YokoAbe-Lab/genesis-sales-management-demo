import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const [input,output]=process.argv.slice(2);
const p=JSON.parse(await fs.readFile(input,'utf8')),a=p.run.analysis;
const wb=Workbook.create(),summary=wb.worksheets.add('集計結果'),source=wb.worksheets.add('元データと条件');
const safe=v=>typeof v==='string'&&/^[=+@]/.test(v)?"'"+v:v;
function block(sheet,row,col,values){sheet.getRangeByIndexes(row,col,values.length,values[0].length).values=values.map(r=>r.map(safe));}
for(const sheet of [summary,source]){sheet.showGridLines=false;sheet.getRange('A1:J100').format.font.name='Meiryo';sheet.getRange('A1:J100').format.font.size=11;sheet.getRange('A1:J100').format.rowHeight=25;sheet.getRange('A1:J100').format.columnWidth=18;}
block(summary,1,0,[[a.source.name+'の集計結果']]);summary.getRange('A2').format.font.size=16;
block(summary,3,0,[['承認時点の固定結果です。再計算用ブックではありません。']]);
block(summary,5,0,[[a.config.chart==='line'?'月':a.config.group,'値','単位','元の行番号']]);
block(summary,6,0,a.series.map(s=>[s.label,s.value,a.config.aggregate==='count'?'件':a.unit,s.lines.join(', ')]));
summary.getRange('B7:B60').setNumberFormat('#,##0.0');summary.getRange('D1:D70').format.columnWidth=40;
const bottom=8+a.series.length;block(summary,bottom,0,[['説明区分','内容']]);
const reportRows=a.sections.map(([key,kind,title])=>[kind+'：'+title,a.finalText[key]]);
reportRows.push(['抽出条件',a.conditions],['RunID',p.run.runId],['承認ID',p.approval.id]);
summary.getRange('B1:B100').format.columnWidth=34;
for(let i=0;i<reportRows.length;i++){
 const row=bottom+1+i;summary.getRangeByIndexes(row,1,1,3).merge();
 block(summary,row,0,[reportRows[i]]);
 const cells=summary.getRangeByIndexes(row,0,1,4);cells.format.wrapText=true;
 cells.format.verticalAlignment='center';cells.format.rowHeight=Math.max(44,Math.ceil(reportRows[i][1].length/56)*16+10);
}
block(source,0,0,[['元ファイル',a.source.path],['SHA256',a.source.sha256],['条件',a.conditions],['元表',a.source.table],['RunID',p.run.runId]]);
source.getRange('B1:H5').format.rowHeight=27;
for(let row=0;row<5;row++)source.getRangeByIndexes(row,1,1,9).merge();
source.getRange('A1:J5').format.wrapText=true;source.getRange('A1:J5').format.rowHeight=42;
const fields=a.source.fields;
block(source,6,0,[['行番号',...fields,'集計対象','理由']]);
const numeric=new Set(['金額','数量']);
const rows=a.evidence.map(e=>[e.line,...fields.map(f=>numeric.has(f)&&e.values[f]!==''&&Number.isFinite(Number(e.values[f]))?Number(e.values[f]):e.values[f]),e.included?'対象':'対象外',[...e.reasons,...e.warnings].join('・')]);
block(source,7,0,rows);source.freezePanes.freezeRows(7);
source.getRangeByIndexes(6,0,rows.length+1,fields.length+3).format.rowHeight=30;
source.getRangeByIndexes(0,fields.length+2,100,1).format.columnWidth=42;
source.getRangeByIndexes(6,0,rows.length+1,fields.length+3).format.borders={preset:'all',style:'thin',color:'#E0E7ED'};
source.getRangeByIndexes(6,0,1,fields.length+3).format.horizontalAlignment='center';
for(const [sheet,row,width] of [[summary,5,4],[source,6,fields.length+3]]){let r=sheet.getRangeByIndexes(row,0,1,width);r.format.fill='#214F70';r.format.font.color='#FFFFFF';r.format.font.bold=true;}
wb.recalculate();
const check=await wb.inspect({kind:'table',range:'集計結果!A6:D12',include:'values',tableMaxRows:7,tableMaxCols:4});
await fs.writeFile(output+'.check.json',check.ndjson);
const dir=path.dirname(output);
for(const [sheetName,range,suffix] of [['集計結果','A1:D18',''],['集計結果',`A${bottom+5}:D${bottom+reportRows.length+1}`,'_読み解き'],['元データと条件','A1:J17','']]){const png=await wb.render({sheetName,range,scale:1.5,format:'png'});await fs.writeFile(path.join(dir,sheetName+suffix+'_確認.png'),new Uint8Array(await png.arrayBuffer()));}
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
