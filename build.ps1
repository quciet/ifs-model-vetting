param([string]$DotnetPath, [string]$PythonPath, [string]$InnoPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $DotnetPath) { $DotnetPath=Join-Path $PSScriptRoot 'build-tools\dotnet\dotnet.exe' }
if (-not $PythonPath) { $PythonPath=Join-Path $PSScriptRoot '.packaging-venv314\Scripts\python.exe' }
if (-not $InnoPath) { $InnoPath=Join-Path $PSScriptRoot 'build-tools\inno\ISCC.exe' }
foreach ($toolPath in @($DotnetPath,$PythonPath,$InnoPath)) {
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Build tool missing: $toolPath" }
}
& $DotnetPath publish decoder -c Release -r win-x64 --self-contained true -o decoder-runtime --nologo
if ($LASTEXITCODE -ne 0) { throw 'Decoder publish failed' }
& $PythonPath -m PyInstaller packaging/IFsModelVetting.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw 'Python packaging failed' }
Copy-Item -LiteralPath 'USER_GUIDE.txt' -Destination 'dist\IFsModelVetting\USER_GUIDE.txt'
Copy-Item -LiteralPath 'LICENSE' -Destination 'dist\IFsModelVetting\LICENSE'
Copy-Item -LiteralPath 'packaging\INSTALLATION_NOTICE.txt' -Destination 'dist\IFsModelVetting\INSTALLATION_NOTICE.txt'
Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.txt' -Destination 'dist\IFsModelVetting\THIRD_PARTY_NOTICES.txt'
Copy-Item -LiteralPath 'licenses' -Destination 'dist\IFsModelVetting' -Recurse -Force
& $InnoPath /Q packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$versionMatch=Select-String -LiteralPath 'packaging\installer.iss' -Pattern '^#define AppVersion "([^"]+)"$'
if (-not $versionMatch) { throw 'Installer version is missing' }
$appVersion=$versionMatch.Matches[0].Groups[1].Value
Compress-Archive -Path 'dist\IFsModelVetting' -DestinationPath "release\IFsModelVetting-Portable-$appVersion-win-x64.zip" -Force
Get-ChildItem -LiteralPath 'release' -File | Where-Object { $_.Name -like "*-$appVersion-win-x64.*" } | ForEach-Object {
    $hash=Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
} | Set-Content -LiteralPath "release\SHA256SUMS-$appVersion.txt" -Encoding ascii
Write-Output 'Windows installer and portable ZIP are in release.'
