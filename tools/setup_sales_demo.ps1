$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
foreach($dataset in @('work','test')){
 $folder=Join-Path $root ('components\'+$dataset)
 $database=Join-Path $folder '販売システム管理2.accdb'
 if(Test-Path -LiteralPath $database){Write-Output ($dataset+': existing database preserved');continue}
 & (Join-Path $PSScriptRoot 'build_demo_database.ps1') -Destination $database
 & (Join-Path $PSScriptRoot 'seed_demo.ps1') -Root $folder
}
