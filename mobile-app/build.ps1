# PowerShell Build Script for Onyx Mobile App (Android)
[CmdletBinding()]
param (
    [switch]$Release
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== Onyx Mobile App Build (PowerShell) ===" -ForegroundColor Cyan

# 1. Ensure Environment
if (-not $env:JAVA_HOME) {
    $Jdk21 = Get-ChildItem "C:\Program Files\Microsoft\jdk-21*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Jdk21 -and (Test-Path "$($Jdk21.FullName)\bin\java.exe")) {
        $env:JAVA_HOME = $Jdk21.FullName
        $env:Path = "$env:JAVA_HOME\bin;$env:Path"
        Write-Host "Set JAVA_HOME to Microsoft OpenJDK 21: $env:JAVA_HOME" -ForegroundColor DarkGray
    } elseif (Test-Path "C:\Program Files\Android\Android Studio\jbr") {
        $env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
        $env:Path = "$env:JAVA_HOME\bin;$env:Path"
        Write-Host "Set JAVA_HOME from Android Studio JBR: $env:JAVA_HOME" -ForegroundColor DarkGray
    }
}

if (-not $env:ANDROID_HOME) {
    if (Test-Path "$env:LOCALAPPDATA\Android\Sdk") {
        $env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
        Write-Host "Set ANDROID_HOME: $env:ANDROID_HOME" -ForegroundColor DarkGray
    }
}

# 2. Check Node modules
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
    npm install
}

# 3. Sync Capacitor Android
Write-Host "Syncing Capacitor Android platform..." -ForegroundColor Yellow
npx cap sync android

# 4. Run Gradle Build
Set-Location "$ScriptDir\android"

Write-Host "Building Debug APK with Gradle..." -ForegroundColor Green
.\gradlew.bat clean :app:assembleDebug

$HasKeystore = Test-Path "keystore.properties"
if ($Release -or $HasKeystore) {
    if ($HasKeystore) {
        Write-Host "Building Release APK with Gradle..." -ForegroundColor Green
        .\gradlew.bat :app:assembleRelease
    } else {
        Write-Warning "Release requested but keystore.properties not found! Skipping release signing."
    }
}

# 5. Export to dist/
Set-Location $ScriptDir
if (-not (Test-Path "dist")) {
    New-Item -ItemType Directory -Path "dist" | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DebugApk = "android\app\build\outputs\apk\debug\app-debug.apk"

if (Test-Path $DebugApk) {
    Copy-Item $DebugApk "dist\OnyxWorkout-debug-$Timestamp.apk" -Force
    Copy-Item $DebugApk "dist\OnyxWorkout-debug-latest.apk" -Force
    Write-Host "Debug APK copied to: dist\OnyxWorkout-debug-latest.apk" -ForegroundColor Green
}

$ReleaseApk = "android\app\build\outputs\apk\release\app-release.apk"
if (Test-Path $ReleaseApk) {
    Copy-Item $ReleaseApk "dist\OnyxWorkout-release-$Timestamp.apk" -Force
    Copy-Item $ReleaseApk "dist\OnyxWorkout-release-latest.apk" -Force
    Write-Host "Release APK copied to: dist\OnyxWorkout-release-latest.apk" -ForegroundColor Green
}

Write-Host "=== Build Completed Successfully ===" -ForegroundColor Cyan
