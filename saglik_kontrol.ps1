$ErrorActionPreference = "Continue"
# Sabah calismasi rapor uretmediyse fark et ve telafi et.
#
# Neden gerekli: run_daily.ps1 kendi hatalarini Telegram'a bildiriyor, ama DISARIDAN
# oldurulen bir calisma hicbir kod satiri calistirmaz - o yuzden sessiz kalir.
# 22 Eylul 2026'da tam bu oldu: gorevin "RunOnlyIfNetworkAvailable" kosulu, Wi-Fi
# gorev basladiktan 11 saniye sonra dustugu icin process'i 0x8007042B ile oldurdu;
# ag bekleme dongusu hic ikinci turunu atamadi, Telegram'a da tek kelime gitmedi.
# Bu betik gunun ortasinda "bugunun raporu var mi?" diye bakan bagimsiz bir gozdur.

$ProjectDir = $PSScriptRoot
$Today = Get-Date -Format "yyyy-MM-dd"
$LogDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$WrapperLog = Join-Path $LogDir "wrapper_$Today.log"
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

function Yaz([string]$Satir) {
    "[saglik-kontrol] $Satir" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
}

Yaz "=== Saglik kontrolu: $(Get-Date) ==="

$ReportPath = Join-Path $LogDir "rapor_$Today.txt"
if (Test-Path $ReportPath) {
    $Boyut = (Get-Item $ReportPath).Length
    Yaz "Bugunun raporu yerinde ($Boyut bayt); telafiye gerek yok."
    exit 0
}

Yaz "Bugun icin rapor bulunamadi ($ReportPath). Telafi calismasi baslatiliyor."

# Once haberi ver: telafi de basarisiz olursa en azindan sessizlik olmaz.
try {
    $PyYolu = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $AlertYolu = Join-Path $ProjectDir "src\send_alert.py"
    & $PyYolu $AlertYolu "Borsa Analiz Ajani: sabah calismasi bugun rapor uretmedi (muhtemelen calisma disaridan kesildi). Telafi calismasi simdi baslatiliyor." *>> $WrapperLog
} catch {
    Yaz "UYARI: Telafi bildirimi gonderilemedi: $($_.Exception.Message)"
}

$RunYolu = Join-Path $ProjectDir "run_daily.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunYolu
$TelafiCikis = $LASTEXITCODE

if ((Test-Path $ReportPath) -and $TelafiCikis -eq 0) {
    Yaz "Telafi calismasi basarili; rapor uretildi ve gonderildi."
    exit 0
}

Yaz "HATA: Telafi calismasi da rapor uretemedi (cikis kodu $TelafiCikis)."
# Cikis kodu 0 olsa bile rapor yoksa haber verilmeli: run_daily.ps1 son adimdaki
# `claude` cagrisinin basarisini kontrol etmiyor, yani rapor uretilmeden 0 ile
# cikmasi mumkun. Burada tek olcut dosyanin var olup olmadigidir.
try {
    $PyYolu = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $AlertYolu = Join-Path $ProjectDir "src\send_alert.py"
    & $PyYolu $AlertYolu "Borsa Analiz Ajani: telafi calismasi da rapor uretemedi (cikis kodu $TelafiCikis). Elle bakilmasi gerekiyor." *>> $WrapperLog
} catch {
    Yaz "UYARI: Ikinci ariza bildirimi gonderilemedi: $($_.Exception.Message)"
}
exit 1
