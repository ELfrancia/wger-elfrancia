# Script di avvio automatico per Workout App (wger-elfrancia)
Write-Host "🏋️ Avvio in corso di Workout App..." -ForegroundColor Cyan

# Verifico se l'ambiente virtuale esiste
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creazione ambiente virtuale Python (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}

# Attivazione ambiente virtuale
Write-Host "⚡ Attivazione ambiente virtuale..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Installazione dipendenze se necessario
Write-Host "📥 Verifica ed installazione dipendenze..." -ForegroundColor Yellow
pip install -e . --quiet
npm install --quiet

# Generazione/Inizializzazione automatica Database e Dati
Write-Host "⚙️ Inizializzazione automatica del database e dati..." -ForegroundColor Yellow
python manage.py setup_app

# Avvio del server
Write-Host "🚀 Server in avvio su http://localhost:8000 ..." -ForegroundColor Green
python manage.py runserver 0.0.0.0:8000
