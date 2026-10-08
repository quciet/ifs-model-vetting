param([string]$DotnetPath)
$ErrorActionPreference='Stop'
if (-not $DotnetPath) { $DotnetPath=Join-Path $PSScriptRoot '..\DevelopmentTools\dotnet\dotnet.exe' }
& $DotnetPath publish (Join-Path $PSScriptRoot 'decoder') -c Release -r win-x64 --self-contained true -o (Join-Path $PSScriptRoot 'decoder-runtime') --nologo
if ($LASTEXITCODE -ne 0) { throw 'Decoder publish failed' }
