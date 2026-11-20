<#
Starts a throw-away local MySQL 8.4 server for this project, with no installer and no admin rights.

  * downloads the official MySQL 8.4 LTS "no-install" ZIP from cdn.mysql.com (about 280 MB, once)
  * keeps binaries and data in .mysql\ inside the project (git-ignored)
  * listens on 127.0.0.1:3307 so it never clashes with an existing MySQL on 3306
  * creates database fuel_passthrough and user fuel_analyst / fuel_pass (the config.py defaults)

Usage (from the project folder):
    powershell -ExecutionPolicy Bypass -File scripts\start_local_mysql.ps1
    $env:MYSQL_PORT = "3307"; python run_pipeline.py

Stop the server:  .mysql\mysql-8.4.13-winx64\bin\mysqladmin.exe -uroot --host=127.0.0.1 --port=3307 shutdown
Already have MySQL 8? Skip this script and set MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD.
#>
param(
    [string]$Version = "8.4.13",
    [int]$Port = 3307,
    [string]$ZipPath = ""          # optional: use an already-downloaded ZIP
)
$ErrorActionPreference = "Stop"
$root    = Join-Path (Split-Path $PSScriptRoot -Parent) ".mysql"
$base    = Join-Path $root "mysql-$Version-winx64"
$data    = Join-Path $root "data"
$ini     = Join-Path $root "my.ini"
$bin     = Join-Path $base "bin"
New-Item -ItemType Directory -Force $root | Out-Null

if (-not (Test-Path $base)) {
    if (-not $ZipPath) {
        $ZipPath = Join-Path $root "mysql-$Version-winx64.zip"
        $url = "https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-$Version-winx64.zip"
        Write-Host "Downloading $url ..."
        Invoke-WebRequest -Uri $url -OutFile $ZipPath -UseBasicParsing
    }
    Write-Host "Extracting ..."
    Expand-Archive -Path $ZipPath -DestinationPath $root -Force
}

$fwd = { param($p) $p -replace '\\', '/' }
@"
[mysqld]
basedir=$(& $fwd $base)
datadir=$(& $fwd $data)
port=$Port
bind-address=127.0.0.1
mysqlx=OFF
[client]
port=$Port
"@ | Set-Content -Path $ini -Encoding ascii

if (-not (Test-Path $data)) {
    Write-Host "Initialising data directory ..."
    & "$bin\mysqld.exe" --defaults-file="$ini" --initialize-insecure
}

$ErrorActionPreference = "Continue"     # native tools write to stderr; judge them by exit code
function Test-MySql { & "$bin\mysqladmin.exe" -uroot "--host=127.0.0.1" "--port=$Port" ping 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }

if (Test-MySql) {
    Write-Host "mysqld is already running on 127.0.0.1:$Port"
} else {
    Write-Host "Starting mysqld on 127.0.0.1:$Port ..."
    Start-Process -FilePath "$bin\mysqld.exe" -ArgumentList "--defaults-file=`"$ini`"" -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-MySql); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Test-MySql)) { throw "mysqld did not start - see $data\*.err" }
}

$sql = @"
CREATE DATABASE IF NOT EXISTS fuel_passthrough;
CREATE USER IF NOT EXISTS 'fuel_analyst'@'localhost' IDENTIFIED BY 'fuel_pass';
CREATE USER IF NOT EXISTS 'fuel_analyst'@'127.0.0.1' IDENTIFIED BY 'fuel_pass';
GRANT ALL PRIVILEGES ON fuel_passthrough.* TO 'fuel_analyst'@'localhost';
GRANT ALL PRIVILEGES ON fuel_passthrough.* TO 'fuel_analyst'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
& "$bin\mysql.exe" -uroot "--host=127.0.0.1" "--port=$Port" -e $sql
if ($LASTEXITCODE -ne 0) { throw "could not create the project database/user" }
Write-Host "MySQL is ready. Now run:  `$env:MYSQL_PORT = `"$Port`"; python run_pipeline.py"
