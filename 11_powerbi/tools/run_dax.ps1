# Run DAX queries against the model open in Power BI Desktop (local Analysis Services instance).
# Usage: run_dax.ps1 -QueryFile queries.dax -Out result.json   (queries separated by lines "-- QUERY <name>")
param([string]$QueryFile, [string]$Out)
$port = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces" -Recurse -Filter msmdsrv.port.txt |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::Unicode).Trim() })
Add-Type -Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll"
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
$conn.Open()
$c0 = $conn.CreateCommand(); $c0.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"; $rr = $c0.ExecuteReader(); $rr.Read() | Out-Null; $db = $rr.GetValue(0); $rr.Close()
$conn.ChangeDatabase($db)
$results = @()
foreach ($block in ([IO.File]::ReadAllText($QueryFile) -split "(?m)^-- QUERY ")) {
  if (-not $block.Trim()) { continue }
  $name, $dax = $block -split "`n", 2
  $cmd = $conn.CreateCommand(); $cmd.CommandText = $dax; $cmd.CommandTimeout = 300
  try {
    $r = $cmd.ExecuteReader(); $rows = @()
    while ($r.Read()) { $row = @{}; for ($i = 0; $i -lt $r.FieldCount; $i++) { $row[$r.GetName($i)] = $r.GetValue($i) }; $rows += $row }
    $r.Close(); $results += @{ name = $name.Trim(); ok = $true; rows = $rows }
  } catch { $results += @{ name = $name.Trim(); ok = $false; error = $_.Exception.Message } }
}
$conn.Close()
$results | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $Out
"port=$port db=$db queries=$($results.Count)"
