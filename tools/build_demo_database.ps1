param([string]$Destination=(Join-Path (Split-Path $PSScriptRoot) 'components\work\販売システム管理2.accdb'))
$ErrorActionPreference='Stop'
# Build a new empty database from reviewed schema only. Never import old rows or Office objects.
if(Test-Path -LiteralPath $Destination){throw 'Destination already exists; existing data will not be overwritten.'}
$schema=Get-Content -LiteralPath (Join-Path (Split-Path $PSScriptRoot) 'demo\sales-schema.json') -Raw -Encoding UTF8|ConvertFrom-Json
[void][IO.Directory]::CreateDirectory((Split-Path $Destination))
$e=New-Object -ComObject DAO.DBEngine.120
$db=$e.CreateDatabase($Destination,';LANGID=0x0411;CP=932;COUNTRY=0',128)
try{
 foreach($t in $schema.tables){
  $td=$db.CreateTableDef($t.name)
  foreach($f in $t.fields){
   $field=$td.CreateField($f.name,[int]$f.type,[int]$f.size)
   if($f.auto){$field.Attributes=$field.Attributes -bor 16}
   $field.Required=[bool]$f.required
   if($f.type -in 10,12){$field.AllowZeroLength=[bool]$f.allowZeroLength}
   if($f.default){$field.DefaultValue=$f.default}
   if($f.validation){$field.ValidationRule=$f.validation}
   $td.Fields.Append($field)
  }
  $db.TableDefs.Append($td)
  foreach($i in $t.indexes){$idx=$td.CreateIndex($i.name);$idx.Primary=[bool]$i.primary;$idx.Unique=[bool]$i.unique;$idx.IgnoreNulls=[bool]$i.ignoreNulls;foreach($f in $i.fields){$fi=$idx.CreateField($f.name);$fi.Attributes=[int]$f.attributes;$idx.Fields.Append($fi)};$td.Indexes.Append($idx)}
 }
 foreach($q in $schema.queries){[void]$db.CreateQueryDef($q.name,$q.sql)}
 foreach($r in $schema.relations){$rel=$db.CreateRelation($r.name,$r.table,$r.foreignTable,[int]$r.attributes);foreach($f in $r.fields){$rf=$rel.CreateField($f.name);$rf.ForeignName=$f.foreignName;$rel.Fields.Append($rf)};$db.Relations.Append($rel)}
 'Clean database created without source records.'
}finally{$db.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($e)}
