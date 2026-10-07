$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$sdkPath=Join-Path $PSScriptRoot 'build-tools\dotnet\dotnet.exe'
if (-not (Test-Path -LiteralPath $sdkPath)) { $sdkPath='dotnet' }
& $sdkPath publish decoder -c Release -r win-x64 --self-contained true -o decoder-runtime --nologo
if ($LASTEXITCODE -ne 0) { throw 'Decoder build failed' }
python app.py
