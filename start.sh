#!/usr/bin/env bash

echo "🏋️ Avvio in corso di Workout App..."

if [ ! -d ".venv" ]; then
    echo "📦 Creazione ambiente virtuale Python (.venv)..."
    python3 -m venv .venv
fi

echo "⚡ Attivazione ambiente virtuale..."
source .venv/bin/activate

echo "📥 Verifica ed installazione dipendenze..."
pip install -e . --quiet
npm install --quiet

echo "⚙️ Inizializzazione automatica del database e dati..."
python manage.py setup_app

echo "🚀 Server in avvio su http://localhost:8000 ..."
python manage.py runserver 0.0.0.0:8000
