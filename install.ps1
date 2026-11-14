$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "dist\EMITDesktop"
$exeSource = Join-Path $source "EMITDesktop.exe"

if (-not (Test-Path -LiteralPath $exeSource)) {
    throw "Missing build output. Run .\build.ps1 first."
}

$target = Join-Path $env:LOCALAPPDATA "Programs\EMITDesktop"
if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item -LiteralPath $source -Destination $target -Recurse

$exe = Join-Path $target "EMITDesktop.exe"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-ItemProperty -Path $runKey -Name "EMITDesktop" -Value "`"$exe`"" -PropertyType String -Force | Out-Null

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\EMIT Desktop.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($startMenu)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $target
$shortcut.Description = "EMIT Desktop continuous authentication"
$shortcut.Save()

Write-Host "Installed: $exe"
Write-Host "Start Menu: $startMenu"
Write-Host "Windows startup entry enabled."
