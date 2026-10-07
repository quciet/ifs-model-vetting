param([string]$DotnetPath, [string]$PythonPath, [string]$InnoPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $DotnetPath) { $DotnetPath=Join-Path $PSScriptRoot 'build-tools\dotnet\dotnet.exe' }
if (-not $PythonPath) { $PythonPath=Join-Path $PSScriptRoot '.packaging-venv\Scripts\python.exe' }
if (-not $InnoPath) { $InnoPath=Join-Path $PSScriptRoot 'build-tools\inno\ISCC.exe' }
foreach ($toolPath in @($DotnetPath,$PythonPath,$InnoPath)) {
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Build tool missing: $toolPath" }
}
& $DotnetPath publish decoder -c Release -r win-x64 --self-contained true -o decoder-runtime --nologo
if ($LASTEXITCODE -ne 0) { throw 'Decoder publish failed' }
& $PythonPath -m PyInstaller packaging/IFsModelVetting.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw 'Python packaging failed' }
Copy-Item -LiteralPath 'USER_GUIDE.txt' -Destination 'dist\IFsModelVetting\USER_GUIDE.txt'
Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.txt' -Destination 'dist\IFsModelVetting\THIRD_PARTY_NOTICES.txt'
Copy-Item -LiteralPath 'licenses' -Destination 'dist\IFsModelVetting' -Recurse -Force
& $InnoPath /Q packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
Compress-Archive -Path 'dist\IFsModelVetting' -DestinationPath 'release\IFsModelVetting-Portable-0.1.0-win-x64.zip' -Force
Write-Output 'Windows installer and portable ZIP are in release.'
