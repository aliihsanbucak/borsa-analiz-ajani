# Sembol sorgu dinleyicisini Windows oturum acilisinda otomatik baslatir.
# Bir kez calistirilmasi yeterlidir; tekrar calistirmak zararsizdir (gorev
# varsa ustune yazilir). Yonetici hakki GEREKMEZ - gorev kullanici baglaminda,
# en dusuk ayricalikla kaydedilir.
#
# Kullanim:  .\dinleyici-kurulum.ps1
# Kaldirma:  .\dinleyici-kurulum.ps1 -Kaldir

param([switch]$Kaldir)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$TaskName = "BorsaAnalizAjani-Dinleyici"

if ($Kaldir) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Gorev kaldirildi: $TaskName"
    Write-Host "Su anda calisan dinleyici varsa Gorev Yoneticisi'nden pythonw/python surecini kapat."
    return
}

$Launcher = Join-Path $ProjectDir "run_listener.ps1"
if (-not (Test-Path $Launcher)) { throw "run_listener.ps1 bulunamadi: $Launcher" }

# -WindowStyle Hidden: dinleyici arka planda, konsol penceresi acmadan calissin.
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`"" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Dinleyici uzun omurlu bir surectir: zaman asimi yok, pil modunda durdurma yok.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Telegram'dan gelen sembol sorgularini analiz eden dinleyici." `
    -Force | Out-Null

Write-Host "Gorev kuruldu: $TaskName (her oturum acilisinda baslar)."
Write-Host "Simdi baslatmak icin: Start-ScheduledTask -TaskName '$TaskName'"
