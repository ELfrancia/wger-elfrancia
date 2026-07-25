# 🐳 Migrazione Semplice con Docker + GitHub + NAS

Visto che usi **Docker**, sul nuovo PC non devi installare Python o Node.js.

### 📤 1. SUL PC ATTUALE:
1. `git push origin master`
2. Copia sul **NAS**: `database.sqlite` e la cartella `media/`

---

### 📥 2. SUL NUOVO PC:
1. **Clona da GitHub:**
   ```bash
   git clone https://github.com/ELfrancia/wger-elfrancia.git
   cd wger-elfrancia
   ```
2. **Scarica dal NAS e incolla dentro `wger-elfrancia/`:**
   * `database.sqlite`
   * la cartella `media/`

---

### 🚀 3. AVVIO CON DOCKER (Un solo comando):
```bash
docker-compose up -d --build
```

L'app si avvia su **http://localhost:8000**!
