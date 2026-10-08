param([string]$PythonPath='python')
$ErrorActionPreference='Stop'
& $PythonPath (Join-Path $PSScriptRoot 'app.py')
