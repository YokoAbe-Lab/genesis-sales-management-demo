"""Read OOXML stored feature definitions without starting Excel."""
import zipfile
from xml.etree import ElementTree as ET

KEYS=['formulas','conditionalFormats','validations','tables','definedNames','filters','charts','shapes','onActions']

def read_features(work,checked_xml):
    items={k:[] for k in KEYS}
    result={'status':'UNSUPPORTED_CONTAINER','items':items,'counts':{k:0 for k in KEYS},
            'executed':False,'formulaCalculation':'NOT_EXECUTED','onActionExecuted':False}
    if not zipfile.is_zipfile(work):return result
    with zipfile.ZipFile(work) as z:
        names=set(z.namelist())
        if 'xl/workbook.xml' not in names:return result
        wb=checked_xml(z.read('xl/workbook.xml'))
        for d in wb.findall('{*}definedNames/{*}definedName'):
            items['definedNames'].append({'name':d.get('name'),'ref':d.text or ''})
        for part in sorted(names):
            if not part.endswith('.xml'):continue
            if part.startswith('xl/worksheets/') and '/_rels/' not in part:
                doc=checked_xml(z.read(part))
                for cell in doc.findall('.//{*}sheetData/{*}row/{*}c'):
                    f=cell.find('{*}f')
                    if f is not None:items['formulas'].append({'part':part,'cell':cell.get('r'),'formula':f.text or '', 'cachedValue':cell.findtext('{*}v')})
                for cf in doc.findall('{*}conditionalFormatting'):
                    for r in cf.findall('{*}cfRule'):items['conditionalFormats'].append({'part':part,'range':cf.get('sqref'),'type':r.get('type'),'operator':r.get('operator'),'formula':[e.text for e in r.findall('{*}formula')]})
                for r in doc.findall('{*}dataValidations/{*}dataValidation'):
                    items['validations'].append({'part':part,'range':r.get('sqref'),'type':r.get('type'),'formula1':r.findtext('{*}formula1')})
                for f in doc.findall('{*}autoFilter'):items['filters'].append({'part':part,'range':f.get('ref')})
            elif part.startswith('xl/tables/'):
                doc=checked_xml(z.read(part));items['tables'].append({'part':part,'name':doc.get('name'),'range':doc.get('ref')})
                for f in doc.findall('{*}autoFilter'):items['filters'].append({'part':part,'range':f.get('ref')})
            elif '/charts/chart' in part and part.startswith('xl/'):
                doc=checked_xml(z.read(part));items['charts'].append({'part':part,'references':[f.text for f in doc.findall('.//{*}f')]})
            elif part.startswith('xl/drawings/drawing'):
                doc=checked_xml(z.read(part))
                for s in doc.findall('.//{*}sp'):
                    p=s.find('{*}nvSpPr/{*}cNvPr');name=p.get('name','') if p is not None else ''
                    items['shapes'].append({'part':part,'name':name,'type':'shape'})
                    if s.get('macro'):items['onActions'].append({'part':part,'shape':name,'target':s.get('macro'),'certainty':'stored-reference','executed':False})
        result.update(status='READ',counts={k:len(v) for k,v in items.items()})
    return result
