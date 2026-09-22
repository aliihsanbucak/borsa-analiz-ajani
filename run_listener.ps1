# Borsa Analiz Ajani - sembol sorgu dinleyicisi.
# Telegram'a yazilan sembolu (THYAO, AAPL, BTC) alip analiz eder ve cevaplar.
# Windows oturum acilisinda otomatik baslar (bkz. dinleyici-kurulum.ps1),
# ayrica bu dosyaya cift tiklanarak elle de baslatilabilir.

$ErrorActionPreference = "Continue"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$LogDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$WrapperLog = Join-Path $LogDir "listener_wrapper.log"
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

try {
    chcp 65001 | Out-Null
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# claude CLI dinleyicinin ic surecinden cagriliyor; PATH'te olmali.
$env:Path += ";C:\Program Files\nodejs;$env:APPDATA\npm"

# Ag hazir olmadan baslarsa ilk sorgu bosa duser. Gunluk raporla ayni
# mantik, daha kisa ust sinirla - dinleyici zaten sonsuza kadar bekleyebilir.
$NetworkHost = "api.telegram.org"
$Deadline = (Get-Date).AddMinutes(15)
while ((Get-Date) -lt $Deadline) {
    try {
        if ([System.Net.Dns]::GetHostAddresses($NetworkHost).Count -gt 0) {
            "$(Get-Date -Format s) Ag hazir, dinleyici baslatiliyor." | Out-File $WrapperLog -Append
            break
        }
    } catch {
        Start-Sleep -Seconds 15
    }
}

# Dinleyici kendi icinde sonsuz dongu; bir sekilde cikarsa (ag kopmasi,
# beklenmeyen hata) 30 saniye sonra yeniden baslat.
while ($true) {
    "$(Get-Date -Format s) Dinleyici baslatiliyor." | Out-File $WrapperLog -Append
    & (Join-Path $ProjectDir ".venv\Scripts\python.exe") (Join-Path $ProjectDir "src\listen.py") *>> $WrapperLog
    "$(Get-Date -Format s) Dinleyici $LASTEXITCODE kodu ile cikti; 30 sn sonra tekrar denenecek." |
        Out-File $WrapperLog -Append
    Start-Sleep -Seconds 30
}
