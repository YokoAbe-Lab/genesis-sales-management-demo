param([string]$Root=(Join-Path (Split-Path $PSScriptRoot) 'components\work'))
$ErrorActionPreference='Stop'
# Fixed fictional fixtures, not a record of a successful registration workflow.
$e=New-Object -ComObject DAO.DBEngine.120
$db=$e.OpenDatabase((Join-Path $Root '販売システム管理2.accdb'))
try{
 if($db.OpenRecordset('SELECT Count(*) AS N FROM S_Quote').Fields.Item(0).Value -ne 0){throw 'Demo already populated; no existing records will be overwritten.'}
 $sql=@(
 "INSERT INTO M_Company (CompanyID,CompanyName,Address,Tel,BankInfo,RegistrationNo,Rounding,Ready) VALUES (90001,'架空デモ販売株式会社','架空市サンプル町','000-0000-0000','架空銀行・実在しない口座','架空会社','切捨て',True)",
 "INSERT INTO T_得意先マスター (ClientID,ClientCode,ClientName,PostalCode,Address,Tel) VALUES (90001,'DEMO-001','架空得意先A','000-0000','架空市デモ町','000-0000-0000')",
 "INSERT INTO T_担当者マスター (StaffID,StaffName) VALUES (90001,'架空担当者A')",
 "INSERT INTO T_売上商品マスター (ProductID,ProductCode,ProductName,UnitPrice,Category) VALUES (90001,'DEMO-P01','架空商品A',1000,'デモ')",
 "INSERT INTO M_Terms (TermsID,TermsName,MonthsAfter,DueDay,Active) VALUES (90001,'翌月末（架空）',1,0,True)",
 "INSERT INTO M_Tax (TaxID,TaxName,Rate,Active) VALUES (90001,'デモ税率10%',0.1,True)",
 "INSERT INTO M_ClientPolicy (ClientID,TermsID,StaffID,Active,ClosingDay,PaymentMonths,PaymentDay) VALUES (90001,90001,90001,True,0,1,0)",
 "INSERT INTO M_ProductPolicy (ProductID,TaxID,Active) VALUES (90001,90001,True)",
 "INSERT INTO S_Quote (QuoteID,ClientID,QuoteDate,ValidUntil,Status,Notes,TransactionNo,StaffID,RunID) VALUES (90001,90001,#2026-10-01#,#2026-10-31#,'受注済','架空データ','DEMO-TX-001',90001,'00000000-0000-4000-8000-000000000001')",
 "INSERT INTO S_QuoteLine (QuoteLineID,QuoteID,ProductID,ProductName,Quantity,UnitPrice,Amount,TaxRate) VALUES (90001,90001,90001,'架空商品A',10,1000,10000,0.1)",
 "INSERT INTO S_Order (OrderID,QuoteID,ClientID,OrderDate,Status,Notes,TransactionNo,StaffID,RunID) VALUES (90001,90001,90001,#2026-10-02#,'納品済','架空データ','DEMO-TX-001',90001,'00000000-0000-4000-8000-000000000001')",
 "INSERT INTO S_OrderLine (OrderLineID,OrderID,ProductID,ProductName,Quantity,UnitPrice,Amount,CancelledQuantity,TaxRate) VALUES (90001,90001,90001,'架空商品A',10,1000,10000,0,0.1)",
 "INSERT INTO S_Delivery (DeliveryID,OrderID,DeliveryDate,Notes,RunID) VALUES (90001,90001,#2026-10-03#,'架空データ','00000000-0000-4000-8000-000000000001')",
 "INSERT INTO T_売上台帳 (sumi,SalesDate,ClientID,ClientName,ProductID,ProductName,Quantity,UnitPrice,Amount,StaffID) VALUES (90001,#2026-10-03#,90001,'架空得意先A',90001,'架空商品A',10,1000,10000,90001)",
 "INSERT INTO S_DeliveryLine (DeliveryLineID,DeliveryID,OrderLineID,Quantity,SalesID) VALUES (90001,90001,90001,10,90001)",
 "INSERT INTO S_SaleMeta (SalesID,TransactionNo,TaxRate,StaffID,Status) VALUES (90001,'DEMO-TX-001',0.1,90001,'計上')",
 "INSERT INTO S_InvoiceControl (InvoiceID,InvoiceNumber,ClientID,NetAmount,TaxAmount,TotalAmount,DueAt,InvoiceDate,Status) VALUES (90001,'DEMO-INV-001',90001,10000,1000,11000,#2026-11-30#,#2026-10-04#,'発行済')",
 "INSERT INTO S_InvoiceSource (SalesID,InvoiceID,RunID,BilledQuantity,NetAmount,TaxAmount) VALUES (90001,90001,'00000000-0000-4000-8000-000000000001',10,10000,1000)",
 "INSERT INTO S_Payment (PaymentID,ClientID,PaidAt,Amount,Reference,Status,CreatedBy) VALUES (90001,90001,#2026-10-05#,5000,'DEMO-PAY-001','消込済','DEMO')",
 "INSERT INTO S_Allocation (AllocationID,InvoiceID,PaymentID,Amount,CreatedBy,Reason) VALUES (90001,90001,90001,5000,'DEMO','架空データ')",
 "INSERT INTO S_PaymentTrace (TraceID,AllocationID,TransactionNo,Amount) VALUES (90001,90001,'DEMO-TX-001',5000)"
 )
 $e.Workspaces.Item(0).BeginTrans()
 try{foreach($q in $sql){$db.Execute($q,128)};$e.Workspaces.Item(0).CommitTrans()}catch{$e.Workspaces.Item(0).Rollback();throw}
 'Fictional fixture: sales 10000, tax 1000, payment 5000, outstanding 6000.'
}finally{$db.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($e)}
