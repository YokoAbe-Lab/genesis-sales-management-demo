"""Create inert synthetic workbook containers without starting Excel or VBA.
Source text is assembled as fixture data, saved locally and never printed.
"""
from pathlib import Path
import struct,subprocess,json,hashlib,zipfile
from openpyxl import Workbook
ROOT=Path(__file__).resolve().parents[1]; F=ROOT/'標準テストExcel'; S=F/'教材定義';(S/'VBA').mkdir(parents=True,exist_ok=True)
def u16(n):return struct.pack('<H',n)
def u32(n):return struct.pack('<I',n)
def rec(n,b):return u16(n)+u32(len(b))+b
def compress(b):
 out=bytearray(b'\x01')
 for i in range(0,len(b),3500):
  part=b[i:i+3500];payload=b''.join(b'\0'+part[j:j+8] for j in range(0,len(part),8))
  out+=u16(0xB000|(len(payload)-1))+payload
 return bytes(out)
def line(*words):return ' '.join(words)
def proc(name,kind='Sub',body=None,access='Public'):
 sig=line(access,kind,name+'()')
 if kind=='Function':sig+=line('', 'As','Long')
 return [sig,*(body or []),line('End',kind)]
def source(name,lines):return '\r\n'.join([line('Attribute','VB_Name','=','"'+name+'"'),line('Option','Explicit'),*lines,''])
module=proc('Auto_Open',body=[line('Call','PrintDemo')])+proc('PrintDemo',body=[line('Call','Helper'),line('Dim','note','As','String'),line('note','=','"架空教材 印刷確認"'),line("'",'OnAction','RefreshAll','are tokens only')])
module+=proc('Helper')+proc('Compute','Function',body=[line('Compute','=','42')])
module +=[line('Public','Function','Continued','_'),line('(',')','As','Long'),line('Continued','=','1'),line('End','Function'),line("'",'Public','Sub','NotAProcedure()')]
module+=proc('Strings',body=[line('Dim','s','As','String'),line('s','=','"Public Sub AlsoNotAProcedure()"')])
cls=[line('Public','Property','Get','Value()','As','Long'),line('Value','=','1'),line('End','Property'),line('Public','Property','Let','Value(ByVal','v','As','Long)'),line('End','Property')]
codes={'ThisWorkbook':source('ThisWorkbook',proc('Workbook_Open',access='Private')),'Sheet1':source('Sheet1',proc('Worksheet_Activate',access='Private')),'ModuleMain':source('ModuleMain',module),'ClassCounter':source('ClassCounter',cls),'FormPreview':source('FormPreview',proc('UserForm_Initialize',access='Private'))}
types={'ThisWorkbook':'Document','Sheet1':'Document','ModuleMain':'Module','ClassCounter':'Class','FormPreview':'BaseClass'}
directory=rec(1,u32(1))+rec(2,u32(0x409))+rec(0x14,u32(0x409))+rec(3,u16(932))+rec(4,b'GenesisFixture')
directory+=rec(5,b'')+rec(0x40,b'')+rec(6,b'')+rec(0x3d,b'')+rec(7,u32(0))+rec(8,u32(0))+u16(9)+u32(4)+u32(1)+u16(0)+rec(0x0c,b'')+rec(0x3c,b'')+rec(0x0f,u16(len(codes)))+rec(0x13,u16(0))
for name,code in codes.items():
 b=name.encode('cp932');wide=name.encode('utf-16le')
 directory+=rec(0x19,b)+rec(0x47,wide)+rec(0x1a,b)+rec(0x32,wide)+rec(0x1c,b'')+rec(0x48,b'')+rec(0x31,u32(0))+rec(0x1e,u32(0))+rec(0x2c,u16(0))+rec(0x21 if types[name]=='Module' else 0x22,b'')+rec(0x2b,b'')
 (S/'VBA'/name).write_bytes(compress(code.encode('cp932')))
directory+=rec(0x10,b'');(S/'VBA/dir').write_bytes(compress(directory))
props='\r\n'.join([f'{types[n]}={n}'+('/&H00000000' if types[n]=='Document' else '') for n in codes])+ '\r\nName="GenesisFixture"\r\n'
(S/'PROJECT').write_bytes(props.encode('cp932'))
(S/'PROJECTwm').write_bytes(b''.join(n.encode()+b'\0'+n.encode('utf-16le')+b'\0\0' for n in codes)+b'\0\0')
cp=str(ROOT/'app/java/classes')+';'+str(ROOT/'app/java/lib/*')
def java(args):
 r=subprocess.run(['java','-Xmx256m','-cp',cp,'LocalVbaReader',*map(str,args)],capture_output=True,timeout=30)
 if r.returncode:raise RuntimeError('FIXTURE_BUILD_FAILED')
java(['fixture',S,F/'vbaProject.bin','bin']);java(['fixture',S,F/'standard.xls','xls']);java(['fixture',S,F/'encrypted.xls','encrypted'])
w=Workbook();w.active.title='Sample';w.active.sheet_properties.codeName='Sheet1';w.code_name='ThisWorkbook';w.active.append(['Item','Value']);w.active.append(['Synthetic',10]);w.save(F/'standard.xlsx')
for ext,ctype in [('xlsm','application/vnd.ms-excel.sheet.macroEnabled.main+xml'),('xlam','application/vnd.ms-excel.addin.macroEnabled.main+xml'),('xlsb','application/vnd.ms-excel.sheet.binary.macroEnabled.main')]:
 with zipfile.ZipFile(F/'standard.xlsx') as base:parts={n:base.read(n) for n in base.namelist()}
 parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace(b'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',ctype.encode()).replace(b'</Types>',b'<Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')
 parts['xl/vbaProject.bin']=(F/'vbaProject.bin').read_bytes()
 parts['xl/_rels/workbook.xml.rels']=parts['xl/_rels/workbook.xml.rels'].replace(b'</Relationships>',b'<Relationship Id="rVba" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>')
 if ext=='xlsb':
  # Binary package envelope fixture only. Sheet binary semantics are deliberately unverified.
  parts.pop('xl/workbook.xml');parts['xl/workbook.bin']=b'\x83\x01\x00\x84\x01\x00'
  parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace(b'/xl/workbook.xml',b'/xl/workbook.bin')
  parts['_rels/.rels']=parts['_rels/.rels'].replace(b'xl/workbook.xml',b'xl/workbook.bin')
 with zipfile.ZipFile(F/f'standard.{ext}','w',zipfile.ZIP_DEFLATED) as z:
  for n,b in parts.items():z.writestr(n,b)
# External relationship is an inert documentation-domain reference; never requested.
with zipfile.ZipFile(F/'standard.xlsm') as z:parts={n:z.read(n) for n in z.namelist()}
parts['xl/_rels/workbook.xml.rels']=parts['xl/_rels/workbook.xml.rels'].replace(b'</Relationships>',b'<Relationship Id="rExternal" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLinkPath" TargetMode="External" Target="https://example.invalid/no-request"/></Relationships>')
with zipfile.ZipFile(F/'external.xlsm','w',zipfile.ZIP_DEFLATED) as z:
 for n,b in parts.items():z.writestr(n,b)
(F/'corrupt.xlsm').write_bytes(b'not-an-excel-file')
expected={'modules':{n:{'sha256':hashlib.sha256(c.encode()).hexdigest(),'lineCount':len(c.splitlines()),'type':types[n]} for n,c in codes.items()},'notice':'Synthetic OOXML/BIFF/OLE static-parser fixtures. xlsb is a package envelope fixture, not verified as an Excel-openable workbook. No VBA execution or Excel save verification.'}
(F/'expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
print('SYNTHETIC_FIXTURES_CREATED; VBA_OUTPUT_TO_CONVERSATION=0')
