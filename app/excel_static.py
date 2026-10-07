"""Genesis 0.6: local Excel/VBA inventory. Never starts Office or executes VBA.

Source is confined to the local source directory and T054. Public summaries are
constructed from metadata, never by serializing the source-bearing structures.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STEPS = ['入力点検', '作業用コピー・ハッシュ確認', 'コンテナの静的読取',
         'VBA・構造の静的抽出', '共通形式への保存', '原本不変確認', '外部出力']
SUPPORTED = {'.xlsx', '.xlsm', '.xlam', '.xlsb', '.xls'}
CONTENT_TYPES = {
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
    '.xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.main+xml',
    '.xlam': 'application/vnd.ms-excel.addin.macroEnabled.main+xml',
    '.xlsb': 'application/vnd.ms-excel.sheet.binary.macroEnabled.main',
}


def stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def identifier(prefix):
    return prefix + '-' + uuid.uuid4().hex.upper()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


class ScanError(Exception):
    """Only fixed diagnostic codes may leave the component."""


def clean_line(line):
    # Preserve character positions, discard strings and comments. Doubled quotes
    # are escaped quotes, not the end of a VBA string.
    out = []; quoted = False; i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            if quoted and i + 1 < len(line) and line[i + 1] == '"':
                out.extend('  '); i += 2; continue
            quoted = not quoted; out.append(' ')
        elif not quoted and c == "'":
            break
        else:
            out.append(' ' if quoted else c)
        i += 1
    result = ''.join(out)
    return '' if re.match(r'^\s*Rem(?:\s|$)', result, re.I) else result


def procedures(source, module_type):
    lines = source.splitlines(); logical = []; pending = ''; begin = 1
    for number, physical in enumerate(lines, 1):
        s = clean_line(physical).rstrip()
        if not pending:
            begin = number
        pending += s[:-1] + ' ' if s.endswith('_') else s
        if not s.endswith('_'):
            logical.append((begin, number, pending)); pending = ''
    if pending:
        logical.append((begin, len(lines), pending))
    pattern = re.compile(r'^\s*(?:(?:Public|Private|Friend|Static)\s+)*(Sub|Function|Property\s+(?:Get|Let|Set))\s+([^\W\d]\w*)\b', re.I)
    found = []; current = None; warnings = []
    for start, end, text in logical:
        m = pattern.match(text)
        if m:
            if current:
                current['endLine'] = start - 1
                current['incomplete'] = True
                warnings.append('PROCEDURE_END_UNCONFIRMED')
            kind = ' '.join(x.capitalize() for x in m.group(1).split())
            name = m.group(2)
            is_event = ((module_type == 'Workbook' and name.lower().startswith('workbook_')) or
                        (module_type == 'Worksheet' and name.lower().startswith('worksheet_')) or
                        (module_type == 'UserForm' and name.lower().startswith('userform_')) or
                        name.lower() in {'auto_open', 'auto_close'})
            current = {'name': name, 'kind': kind, 'startLine': start, 'endLine': None,
                       'eventCandidate': is_event, 'incomplete': False, 'explicitCalls': []}
            found.append(current)
        if current:
            current['explicitCalls'].extend(re.findall(r'\bCall\s+([\w.]+)', text, re.I))
            if re.match(r'^\s*End\s+(Sub|Function|Property)\b', text, re.I):
                current['endLine'] = end; current = None
    if current:
        current['endLine'] = len(lines); current['incomplete'] = True
        warnings.append('PROCEDURE_END_UNCONFIRMED')
    for p in found:
        p['lineCount'] = p['endLine'] - p['startLine'] + 1
    # Tokens in comments/strings are deliberately distinguished from executable
    # references. Neither category is evidence of runtime execution.
    static_text = '\n'.join(clean_line(x) for x in lines)
    markers = []
    for token in ['OnAction', 'RefreshAll', 'Workbook_Open', 'Auto_Open']:
        if re.search(r'\b' + token + r'\b', source, re.I):
            markers.append({'name': token, 'locationKind': 'static-token' if re.search(r'\b' + token + r'\b', static_text, re.I) else 'comment-or-string', 'executed': False})
    return found, sorted(set(warnings)), markers


def checked_xml(data):
    # Also detects the declaration in UTF-16/UTF-32 XML before parsing.
    declaration = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in declaration or b'<!ENTITY' in declaration:
        raise ScanError('XML_ENTITY_FORBIDDEN')
    return ET.fromstring(data)


class ExcelAnalyzer:
    def __init__(self, root=ROOT, workspace=None):
        self.root = Path(root)
        self.config = json.loads((self.root / 'excel_config.json').read_text(encoding='utf-8-sig'))
        self.workspace = Path(workspace) if workspace else self.root / 'excel_runs'
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.db_path = self.workspace / 'excel.sqlite3'
        self.lock = threading.Lock()
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS Runs(RunID TEXT PRIMARY KEY, RequestID TEXT NOT NULL, Created TEXT NOT NULL, Status TEXT NOT NULL, Body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS Steps(RunID TEXT, Seq INTEGER, Name TEXT, Status TEXT, Diagnostic TEXT, PRIMARY KEY(RunID,Seq), FOREIGN KEY(RunID) REFERENCES Runs);
            CREATE TABLE IF NOT EXISTS T050(RunID TEXT, ObjectID TEXT, Kind TEXT, Name TEXT, ParentID TEXT, Body TEXT, PRIMARY KEY(RunID,ObjectID), FOREIGN KEY(RunID) REFERENCES Runs);
            CREATE TABLE IF NOT EXISTS T051(RunID TEXT, RelationID TEXT, FromID TEXT, ToID TEXT, Kind TEXT, Certainty TEXT, Body TEXT, PRIMARY KEY(RunID,RelationID), FOREIGN KEY(RunID,FromID) REFERENCES T050(RunID,ObjectID), FOREIGN KEY(RunID,ToID) REFERENCES T050(RunID,ObjectID));
            CREATE TABLE IF NOT EXISTS T054(RunID TEXT, ObjectID TEXT, SourceText TEXT, SHA256 TEXT, SourceFile TEXT, PRIMARY KEY(RunID,ObjectID), FOREIGN KEY(RunID,ObjectID) REFERENCES T050(RunID,ObjectID));
            CREATE TABLE IF NOT EXISTS Exports(ExportID TEXT PRIMARY KEY, RunID TEXT, Created TEXT, Status TEXT, Body TEXT, FOREIGN KEY(RunID) REFERENCES Runs);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_run(self, run):
        with self.db() as db:
            db.execute('UPDATE Runs SET Status=?,Body=? WHERE RunID=?', (run['status'], json.dumps(run, ensure_ascii=False), run['runId']))

    def step(self, rid, seq, status, diagnostic=''):
        with self.db() as db:
            db.execute('UPDATE Steps SET Status=?,Diagnostic=? WHERE RunID=? AND Seq=?', (status, diagnostic, rid, seq))

    def run(self, input_path, request_id='REQ-EXCEL-LOCAL-APPROVED', auto_export=True):
        with self.lock:
            return self._run(input_path, request_id, auto_export)

    def _run(self, input_path, request_id, auto_export):
        rid = identifier('RUN'); directory = self.workspace / rid
        directory.mkdir()
        run = {'runId': rid, 'requestId': str(request_id)[:100], 'created': stamp(), 'status': 'RUNNING',
               'sourcePath': '', 'copyPath': '', 'originalSHA256': '', 'copySHA256': '', 'afterSHA256': '',
               'sourceUnchanged': None, 'fileName': '', 'moduleCount': 0, 'procedureCount': 0,
               'objectCount': 0, 'relationCount': 0, 'warnings': [], 'diagnostic': '',
               'apiRequests': 0, 'macroExecutions': 0, 'officeStarted': False,
               'accessDatabaseWrite': False, 'engine': 'POI 5.2.3 / Genesis 0.6.0', 'directory': str(directory)}
        with self.db() as db:
            db.execute('INSERT INTO Runs VALUES(?,?,?,?,?)', (rid, run['requestId'], run['created'], run['status'], json.dumps(run)))
            db.executemany('INSERT INTO Steps VALUES(?,?,?,?,?)', [(rid, n, name, 'NOT_RUN', '') for n, name in enumerate(STEPS, 1)])
        seq = 1; source = None; objects = []; relations = []; sources = []
        try:
            self.step(rid, seq, 'RUNNING')
            raw = str(input_path).strip().strip('"')
            if not raw or raw.startswith(('\\\\', '//')) or '://' in raw:
                raise ScanError('LOCAL_FILE_REQUIRED')
            source = Path(raw).resolve(strict=True)
            if str(source).startswith('\\\\') or not source.is_file():
                raise ScanError('LOCAL_FILE_REQUIRED')
            if source.suffix.lower() not in SUPPORTED:
                raise ScanError('UNSUPPORTED_EXTENSION')
            if source.stat().st_size > self.config['maxFileBytes']:
                raise ScanError('FILE_SIZE_LIMIT')
            run.update(sourcePath=str(source), fileName=source.name)
            self.step(rid, seq, 'PASS'); seq = 2; self.step(rid, seq, 'RUNNING')
            run['originalSHA256'] = sha_file(source)
            work = directory / ('input' + source.suffix.lower())
            with source.open('rb') as src, work.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            run['copyPath'] = str(work); run['copySHA256'] = sha_file(work)
            if run['copySHA256'] != run['originalSHA256']:
                raise ScanError('COPY_HASH_MISMATCH')
            self.step(rid, seq, 'PASS'); seq = 3; self.step(rid, seq, 'RUNNING')
            inventory = self.read_container(work, directory)
            self.step(rid, seq, 'PASS'); seq = 4; self.step(rid, seq, 'RUNNING')
            run['warnings'].extend(inventory['warnings'])
            run['externalLinkCount'] = inventory['externalLinkCount']
            run['workbookFeatures'] = inventory.get('workbookFeatures', {})
            run['status'] = inventory['status']
            wb_id = identifier('OBJ')
            objects.append({'id': wb_id, 'kind': 'WorkbookFile', 'name': source.name, 'parentId': None})
            sheet_ids = {}
            for sheet in inventory['sheets']:
                sid = identifier('OBJ'); sheet_ids[sheet.get('codeName', '')] = sid
                objects.append({'id': sid, 'kind': 'WorksheetFile', 'name': sheet['name'], 'parentId': wb_id, 'codeName': sheet.get('codeName', '')})
                relations.append(self.relation(wb_id, sid, 'contains', 'confirmed-structure'))
            by_name = {}
            for module in inventory['modules']:
                # Source files are numeric names emitted by our helper, not names
                # supplied by the workbook.
                file = module['file']
                if not re.fullmatch(r'module_\d{4}\.txt', file):
                    raise ScanError('READER_FILE_INVALID')
                path = directory / 'source' / file
                code = path.read_bytes().decode('utf-8')
                mid = identifier('OBJ'); ptype = module['projectType']
                kind = {'Module': 'Module', 'Class': 'Class', 'BaseClass': 'UserForm'}.get(ptype, 'DocumentUnknown')
                if ptype == 'Document' and module['name'] == inventory.get('workbookCodeName'):
                    kind = 'Workbook'
                elif ptype == 'Document' and module['name'] in sheet_ids and module['name']:
                    kind = 'Worksheet'
                if kind == 'DocumentUnknown':
                    run['warnings'].append('DOCUMENT_TYPE_UNCONFIRMED')
                ps, warnings, markers = procedures(code, kind)
                run['warnings'].extend(warnings)
                parent = sheet_ids.get(module['name'], wb_id) if kind == 'Worksheet' else wb_id
                obj = {'id': mid, 'name': module['name'], 'kind': kind, 'parentId': parent,
                       'lineCount': len(code.splitlines()), 'sourceSHA256': sha_file(path),
                       'sourceFile': 'source/' + file, 'markers': markers}
                objects.append(obj); relations.append(self.relation(parent, mid, 'contains', 'confirmed-structure'))
                sources.append((rid, mid, code, obj['sourceSHA256'], str(path)))
                for p in ps:
                    # Object class and VBA declaration kind are different axes.
                    # Keep both; a Sub must still be searchable as a Procedure.
                    objp = {**p, 'id': identifier('OBJ'), 'kind': 'Procedure', 'procedureKind': p['kind'], 'parentId': mid, 'moduleName': module['name']}
                    objects.append(objp); relations.append(self.relation(mid, objp['id'], 'contains', 'confirmed-structure'))
                    by_name.setdefault(p['name'].lower(), []).append(objp['id'])
                run['moduleCount'] += 1; run['procedureCount'] += len(ps)
            for obj in objects:
                for name in obj.get('explicitCalls', []):
                    candidates = by_name.get(name.lower(), [])
                    if len(candidates) == 1:
                        relations.append(self.relation(obj['id'], candidates[0], 'explicit-call', 'static-candidate'))
                    else:
                        run['warnings'].append('CALL_TARGET_UNRESOLVED')
            run['warnings'] = sorted(set(run['warnings']))
            if run['status'] == 'SUCCESS' and run['warnings']:
                run['status'] = 'PARTIAL'
            self.step(rid, seq, 'PASS' if run['status'] in ('SUCCESS', 'NO_VBA') else run['status'])
            seq = 5; self.step(rid, seq, 'RUNNING')
            for obj in objects:
                obj.update(runId=rid, sourceHash=run['copySHA256'])
            with self.db() as db:
                db.executemany('INSERT INTO T050 VALUES(?,?,?,?,?,?)', [(rid, o['id'], o['kind'], o['name'], o.get('parentId'), json.dumps(o, ensure_ascii=False)) for o in objects])
                db.executemany('INSERT INTO T051 VALUES(?,?,?,?,?,?,?)', [(rid, r['id'], r['fromId'], r['toId'], r['kind'], r['certainty'], json.dumps(r)) for r in relations])
                db.executemany('INSERT INTO T054 VALUES(?,?,?,?,?)', sources)
            run['objectCount'] = len(objects); run['relationCount'] = len(relations)
            self.step(rid, seq, 'PASS')
        except Exception as ex:
            run['status'] = 'FAILED'
            run['diagnostic'] = str(ex) if isinstance(ex, ScanError) else 'LOCAL_' + type(ex).__name__.upper()
            self.step(rid, seq, 'FAILED', run['diagnostic'])
        finally:
            if source and run['originalSHA256']:
                try:
                    run['afterSHA256'] = sha_file(source)
                    run['sourceUnchanged'] = run['afterSHA256'] == run['originalSHA256']
                    if not run['sourceUnchanged']:
                        run['status'] = 'FAILED'; run['diagnostic'] = 'SOURCE_CHANGED_DURING_SCAN'
                    self.step(rid, 6, 'PASS' if run['sourceUnchanged'] else 'FAILED', '' if run['sourceUnchanged'] else 'SOURCE_CHANGED_DURING_SCAN')
                except OSError:
                    run['status'] = 'FAILED'; run['diagnostic'] = 'SOURCE_AFTER_HASH_UNAVAILABLE'
                    self.step(rid, 6, 'FAILED', run['diagnostic'])
            self.save_run(run)
        if auto_export:
            self.export(rid)
        return self.detail(rid)

    @staticmethod
    def relation(start, end, kind, certainty):
        return {'id': identifier('REL'), 'fromId': start, 'toId': end, 'kind': kind, 'certainty': certainty}

    def read_container(self, work, directory):
        result = {'status': 'NO_VBA', 'warnings': [], 'modules': [], 'sheets': [], 'externalLinkCount': 0}
        with work.open('rb') as f:
            raw_header = f.read(8)
        binary = None
        if raw_header == bytes.fromhex('d0cf11e0a1b11ae1'):
            binary = work
        elif zipfile.is_zipfile(work):
            with zipfile.ZipFile(work) as z:
                infos = z.infolist()
                if len(infos) > self.config['maxEntries'] or sum(i.file_size for i in infos) > self.config['maxZipBytes']:
                    raise ScanError('ZIP_LIMIT')
                seen = set()
                for i in infos:
                    p = PurePosixPath(i.filename)
                    if i.filename in seen or p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename:
                        raise ScanError('ZIP_PATH_INVALID')
                    seen.add(i.filename)
                    if i.file_size > self.config['maxEntryBytes'] or i.flag_bits & 1:
                        raise ScanError('ZIP_ENTRY_LIMIT_OR_ENCRYPTED')
                if '[Content_Types].xml' not in seen:
                    raise ScanError('OOXML_CONTENT_TYPES_MISSING')
                types = checked_xml(z.read('[Content_Types].xml'))
                main_part = '/xl/workbook.bin' if work.suffix.lower() == '.xlsb' else '/xl/workbook.xml'
                declared = [x.get('ContentType') for x in types if x.get('PartName') == main_part]
                if declared != [CONTENT_TYPES.get(work.suffix.lower())] or not declared[0]:
                    raise ScanError('EXTENSION_CONTENT_MISMATCH')
                if 'xl/workbook.xml' in seen:
                    wb = checked_xml(z.read('xl/workbook.xml'))
                    props = wb.find('{*}workbookPr')
                    if props is not None:
                        result['workbookCodeName'] = props.get('codeName', '')
                    targets = {}
                    if 'xl/_rels/workbook.xml.rels' in seen:
                        for rel in checked_xml(z.read('xl/_rels/workbook.xml.rels')):
                            if rel.get('TargetMode') != 'External':
                                target = rel.get('Target', '')
                                targets[rel.get('Id')] = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                    for sheet in wb.findall('{*}sheets/{*}sheet'):
                        rid = next((v for k, v in sheet.attrib.items() if k.endswith('}id')), '')
                        name = targets.get(rid, '')
                        code_name = ''
                        if name in seen:
                            sh = checked_xml(z.read(name)); pr = sh.find('{*}sheetPr')
                            if pr is not None:
                                code_name = pr.get('codeName', '')
                        result['sheets'].append({'name': sheet.get('name', ''), 'codeName': code_name})
                elif 'xl/workbook.bin' in seen:
                    result['warnings'].append('XLSB_SHEET_STRUCTURE_UNVERIFIED')
                else:
                    raise ScanError('WORKBOOK_PART_MISSING')
                for name in seen:
                    if name.endswith('.rels'):
                        result['externalLinkCount'] += sum(r.get('TargetMode') == 'External' for r in checked_xml(z.read(name)))
                if result['externalLinkCount']:
                    result['warnings'].append('EXTERNAL_LINK_PRESENT_NOT_UPDATED')
                if 'xl/vbaProject.bin' in seen:
                    if work.suffix.lower() == '.xlsx':
                        raise ScanError('XLSX_HAS_VBA_FORMAT_MISMATCH')
                    binary = directory / 'vbaProject.bin'
                    binary.write_bytes(z.read('xl/vbaProject.bin'))
        else:
            raise ScanError('UNRECOGNIZED_OR_CORRUPT_FILE')
        if binary:
            output = directory / 'source'
            cp = str(self.root / 'java' / 'classes') + os.pathsep + str(self.root / 'java' / 'lib' / '*')
            cmd = [self.config['java'], '-Xmx256m', '-cp', cp, 'LocalVbaReader', 'extract', str(binary), str(output)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.config['javaTimeoutSeconds'], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if proc.returncode != 0:
                result['status'] = 'VBA_UNREADABLE'
                result['warnings'].append('LOCAL_VBA_READER_FAILED')
                return result
            metadata = json.loads((output / 'index.json').read_text(encoding='utf-8'))
            if binary == work and work.suffix.lower() != '.xls' and metadata['status'] != 'ENCRYPTED':
                raise ScanError('EXTENSION_CONTENT_MISMATCH')
            result['status'] = metadata['status']; result['modules'] = metadata['modules']
            if metadata['protectionMetadata']:
                result['warnings'].append('PROTECTION_METADATA_PRESENT_LOCK_STATE_UNKNOWN')
            if metadata['sheets'] and not result['sheets']:
                result['sheets'] = [{'name': n, 'codeName': ''} for n in metadata['sheets']]
        from excel_features import read_features
        result['workbookFeatures'] = read_features(work, checked_xml)
        return result

    def detail(self, rid):
        with self.db() as db:
            row = db.execute('SELECT Body FROM Runs WHERE RunID=?', (rid,)).fetchone()
            if not row:
                raise ScanError('RUN_NOT_FOUND')
            run = json.loads(row[0])
            run['objects'] = [json.loads(r[0]) for r in db.execute('SELECT Body FROM T050 WHERE RunID=? ORDER BY rowid', (rid,))]
            run['relations'] = [json.loads(r[0]) for r in db.execute('SELECT Body FROM T051 WHERE RunID=? ORDER BY rowid', (rid,))]
            run['steps'] = [dict(r) for r in db.execute('SELECT Seq,Name,Status,Diagnostic FROM Steps WHERE RunID=? ORDER BY Seq', (rid,))]
            run['exports'] = [json.loads(r[0]) for r in db.execute('SELECT Body FROM Exports WHERE RunID=? ORDER BY rowid DESC', (rid,))]
        return run

    def list_runs(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT Body FROM Runs ORDER BY rowid DESC')]

    def export(self, rid):
        # Only this Run snapshot is read. No Office, parser, original file read,
        # external connection or analysis run is involved in retrying an export.
        from excel_export import write_exports
        run = self.detail(rid)
        eid = identifier('EXP'); folder = self.workspace / rid / 'exports' / eid
        folder.mkdir(parents=True)
        export = {'exportId': eid, 'runId': rid, 'created': stamp(), 'status': 'RUNNING', 'path': str(folder), 'files': [], 'diagnostic': ''}
        with self.db() as db:
            db.execute('INSERT INTO Exports VALUES(?,?,?,?,?)', (eid, rid, export['created'], export['status'], json.dumps(export)))
        self.step(rid, 7, 'RUNNING')
        try:
            with self.db() as db:
                sources = [dict(r) for r in db.execute('SELECT ObjectID,SHA256,SourceFile FROM T054 WHERE RunID=?', (rid,))]
            write_exports(run, sources, folder, export)
            export['status'] = 'SUCCESS' if all(x['status'] == 'PASS' for x in export['files']) else 'FAILED'
        except Exception as ex:
            export['status'] = 'FAILED'; export['diagnostic'] = 'EXPORT_' + type(ex).__name__.upper()
        with self.db() as db:
            db.execute('UPDATE Exports SET Status=?,Body=? WHERE ExportID=?', (export['status'], json.dumps(export, ensure_ascii=False), eid))
        dump(folder / '出力状況.json', export)
        self.step(rid, 7, 'PASS' if export['status'] == 'SUCCESS' else 'FAILED', export['diagnostic'])
        return export

    def downloadable(self, rid, eid, name):
        run = self.detail(rid)
        export = next((e for e in run['exports'] if e['exportId'] == eid), None)
        if not export:
            raise ScanError('EXPORT_NOT_FOUND')
        item = next((x for x in export['files'] if x['name'] == name and x['status'] == 'PASS'), None)
        if not item:
            raise ScanError('ARTIFACT_NOT_FOUND')
        p = Path(export['path']) / name
        if sha_file(p) != item['sha256']:
            raise ScanError('ARTIFACT_HASH_MISMATCH')
        return p
