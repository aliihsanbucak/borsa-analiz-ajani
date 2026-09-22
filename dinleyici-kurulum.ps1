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
# conhost --headless: Windows 11 varsayilan terminali Windows Terminal oldugunda
# -WindowStyle Hidden yok sayilir ve gorunur bir pencere acilir; kullanici onu
# kapatinca dinleyici 0xC000013A ile olur. Headless konsol hic pencere acmaz.
$Action = New-ScheduledTaskAction -Execute "conhost.exe" `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`"" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Bekci tetigi: 22 Eylul 2026 22:01'de dinleyici dis bir sebeple (0xC000013A)
# olduruldu; wrapper'in yeniden baslatma dongusu da onunla birlikte oldugu icin
# oturum yeniden acilana kadar sorgular sessizce cevapsiz kaldi. 10 dakikada bir
# tetiklemek zararsiz: MultipleInstances IgnoreNew calisan kopyaya dokunmaz,
# gorev olmusse yeniden baslatir.
$Bekci = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 10)

# Dinleyici uzun omurlu bir surectir: zaman asimi yok, pil modunda durdurma yok.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($Trigger, $Bekci) `
    -Settings $Settings -Description "Telegram'dan gelen sembol sorgularini analiz eden dinleyici." `
    -Force | Out-Null

Write-Host "Gorev kuruldu: $TaskName (her oturum acilisinda baslar, olurse 10 dk icinde yeniden kalkar)."
Write-Host "Simdi baslatmak icin: Start-ScheduledTask -TaskName '$TaskName'"
