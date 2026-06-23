# gns-proxy.ps1 — zero-install CORS proxy for the CBS 3D tracker (Windows).
#
# Several upstream APIs the tracker relies on don't send
# Access-Control-Allow-Origin headers, so the browser blocks direct fetches.
# This script forwards a couple of routes and adds permissive CORS headers:
#
#     http://localhost:8010/proxy/<path>  ->  https://api.glideandseek.com/<path>
#     http://localhost:8010/metar/<path>  ->  https://aviationweather.gov/<path>
#
# tracker.html automatically tries the local proxy when the direct fetch fails
# (see _gnsFetch and the METAR fetcher).
# Same behaviour as gns-proxy.js, but needs only Windows PowerShell.
#
# Usage:       powershell -ExecutionPolicy Bypass -File gns-proxy.ps1
#              powershell -ExecutionPolicy Bypass -File gns-proxy.ps1 -Port 9000
# Smoke test:  curl http://localhost:8010/proxy/v2/aircraft
#              curl 'http://localhost:8010/metar/api/data/metar?ids=KJFK&format=json&hours=1'
# Stop:        Ctrl+C

param([int]$Port = 8010)

# Windows PowerShell 5.1 defaults to TLS 1.0 — most APIs require TLS 1.2+
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Route prefix -> upstream base URL.  Order matters: longest prefix first.
$routes = @(
  @{ Prefix = "/proxy/"; Target = "https://api.glideandseek.com" },
  @{ Prefix = "/metar/"; Target = "https://aviationweather.gov" }
)

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
foreach ($r in $routes) {
  Write-Host "[gns-proxy] http://localhost:$Port$($r.Prefix)  ->  $($r.Target)"
}
Write-Host "[gns-proxy] smoke test: curl http://localhost:$Port/proxy/v2/aircraft"

try {
  while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $req = $ctx.Request
    $res = $ctx.Response

    $res.Headers.Add("Access-Control-Allow-Origin",  "*")
    $res.Headers.Add("Access-Control-Allow-Methods", "GET, OPTIONS")
    $res.Headers.Add("Access-Control-Allow-Headers", "*")

    if ($req.HttpMethod -eq "OPTIONS") {
      $res.StatusCode = 204
      $res.Close()
      continue
    }

    $path = $req.Url.PathAndQuery
    $route = $null
    if ($req.HttpMethod -eq "GET") {
      foreach ($r in $routes) {
        if ($path.StartsWith($r.Prefix)) { $route = $r; break }
      }
    }
    if ($null -eq $route) {
      $res.StatusCode = 404
      $msg = [Text.Encoding]::UTF8.GetBytes("Use GET /proxy/<gns path> or /metar/<aviationweather path>")
      $res.OutputStream.Write($msg, 0, $msg.Length)
      $res.Close()
      continue
    }

    try {
      $upstream = $route.Target + $path.Substring($route.Prefix.Length - 1)
      $wc = New-Object System.Net.WebClient
      $wc.Headers.Add("User-Agent", "cbs-tracker-proxy/1.0")
      $data = $wc.DownloadData($upstream)
      $res.ContentType = "application/json; charset=utf-8"
      $res.OutputStream.Write($data, 0, $data.Length)
    } catch {
      $res.StatusCode = 502
      $msg = [Text.Encoding]::UTF8.GetBytes("Upstream error: $($_.Exception.Message)")
      $res.OutputStream.Write($msg, 0, $msg.Length)
    }
    $res.Close()
  }
} finally {
  $listener.Stop()
}
