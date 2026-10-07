param([Parameter(Mandatory=$true)][string]$Database)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$engine=$null;$db=$null
function Rows([string]$sql){
 $rs=$db.OpenRecordset($sql,4)
 try{while(!$rs.EOF){$row=[ordered]@{};foreach($field in $rs.Fields){$v=$field.Value;if($v -is [DBNull]){$v=$null};if($v -is [datetime]){$v=$v.ToString('yyyy-MM-dd HH:mm:ss')};$row[$field.Name]=$v};[pscustomobject]$row;$rs.MoveNext()}}finally{$rs.Close()}
}
try{
 $engine=New-Object -ComObject DAO.DBEngine.120
 $db=$engine.OpenDatabase($Database,$false,$true)
 $queries=[ordered]@{
  quotes='SELECT TOP 500 * FROM S_Quote ORDER BY QuoteID DESC'
  quoteLines='SELECT TOP 2000 * FROM S_QuoteLine ORDER BY QuoteLineID DESC'
  orders='SELECT TOP 500 * FROM S_Order ORDER BY OrderID DESC'
  orderLines='SELECT TOP 2000 * FROM SQ_受注明細状況 ORDER BY OrderID DESC'
  deliveries='SELECT TOP 500 * FROM S_Delivery ORDER BY DeliveryID DESC'
  deliveryLines='SELECT TOP 2000 * FROM S_DeliveryLine ORDER BY DeliveryLineID DESC'
  sales='SELECT TOP 2000 s.*,m.TransactionNo,m.TaxRate FROM T_売上台帳 AS s LEFT JOIN S_SaleMeta AS m ON s.sumi=m.SalesID ORDER BY s.sumi DESC'
  invoices='SELECT TOP 500 * FROM SQ_請求残 ORDER BY InvoiceID DESC'
  invoiceLines='SELECT TOP 2000 * FROM S_InvoiceSource ORDER BY InvoiceID DESC'
  payments='SELECT TOP 500 * FROM S_Payment ORDER BY PaymentID DESC'
  allocations='SELECT TOP 2000 * FROM S_Allocation ORDER BY AllocationID DESC'
  paymentTrace='SELECT TOP 2000 * FROM S_PaymentTrace ORDER BY TraceID DESC'
  customerTotals='SELECT * FROM SQ_顧客別売上'
  productTotals='SELECT * FROM SQ_商品別売上'
  monthlyTotals='SELECT * FROM SQ_月別売上'
  orderBalance='SELECT * FROM SQ_受注残'
  unbilled='SELECT * FROM SQ_未請求売上'
  trace='SELECT TOP 2000 * FROM CQ_追跡'
  errors='SELECT TOP 500 * FROM J_Error ORDER BY ErrorID DESC'
  company='SELECT * FROM M_Company'
  tax='SELECT * FROM M_Tax'
  terms='SELECT * FROM M_ClientPolicy'
  closes='SELECT * FROM S_MonthClose'
  returns='SELECT * FROM S_Return'
 }
 $tables=[ordered]@{};$failures=@()
 foreach($key in $queries.Keys){try{$tables[$key]=@(Rows $queries[$key])}catch{$tables[$key]=@();$failures+=@{section=$key;error=$_.Exception.Message}}}
 $metrics=[ordered]@{}
 $start=(Get-Date -Day 1).Date;$end=$start.AddMonths(1)
 $metricQueries=[ordered]@{
  '未処理見積'="SELECT Count(*) AS N FROM S_Quote WHERE Status IN ('見積作成','見積確定')"
  '未処理受注'="SELECT Count(*) AS N FROM S_Order WHERE Status IN ('受注済','一部納品')"
  '未請求明細'='SELECT Count(*) AS N FROM SQ_未請求売上'
  '未入金請求'='SELECT Count(*) AS N FROM SQ_請求残 WHERE OutstandingAmount>0'
  '請求残高'='SELECT Sum(OutstandingAmount) AS N FROM SQ_請求残'
  '受注残高'='SELECT Sum(受注残金額) AS N FROM SQ_受注残'
  '今月売上'="SELECT Sum(Amount) AS N FROM T_売上台帳 WHERE SalesDate>=#$($start.ToString('yyyy-MM-dd'))# AND SalesDate<#$($end.ToString('yyyy-MM-dd'))#"
  '今月入金'="SELECT Sum(Amount) AS N FROM S_Payment WHERE Status<>'取消' AND PaidAt>=#$($start.ToString('yyyy-MM-dd'))# AND PaidAt<#$($end.ToString('yyyy-MM-dd'))#"
  'エラー・確認待ち'="SELECT Count(*) AS N FROM J_Error WHERE Status<>'解消済'"
 }
 foreach($key in $metricQueries.Keys){try{$v=@(Rows $metricQueries[$key])[0].N;$metrics[$key]=if($null -eq $v){0}else{$v}}catch{$metrics[$key]=$null;$failures+=@{section=$key;error=$_.Exception.Message}}}
 $metrics['エラー・確認待ち'] += [int](@(Rows "SELECT Count(*) AS N FROM J_Run WHERE Status IN ('承認待ち','差戻し')")[0].N)
 $metrics['エラー・確認待ち'] += [int](@(Rows 'SELECT Count(*) AS N FROM SQ_請求残 WHERE OutstandingAmount<0')[0].N)
 $excel=$false;try{$excel=$null -ne [type]::GetTypeFromProgID('Excel.Application')}catch{}
 @{connected=$true;readOnly=$true;excelInstalled=$excel;tables=$tables;metrics=$metrics;errors=$failures;checkedAt=(Get-Date).ToString('o')}|ConvertTo-Json -Depth 9 -Compress
}catch{ @{connected=$false;readOnly=$true;tables=@{};errors=@(@{section='Access';error=$_.Exception.Message});checkedAt=(Get-Date).ToString('o')}|ConvertTo-Json -Depth 6 -Compress;exit 1}
finally{if($db){$db.Close()};if($engine){[void][Runtime.InteropServices.Marshal]::ReleaseComObject($engine)}}
