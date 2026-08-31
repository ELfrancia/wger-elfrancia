# 🖥️ Guida al Deployment su Proxmox VE — Workout App

Questa guida ti spiega come installare ed eseguire **Workout App** sul tuo server **Proxmox VE** usando Docker.

---

## 📌 1. Scelta dell'Ambiente su Proxmox

Su Proxmox VE puoi eseguire l'app in due modi:

### Opzione A (Consigliata): Container LXC con Docker
I container LXC richiedono pochissime risorse (RAM e CPU) rispetto a una VM completa.

1. **Creazione automatica LXC Docker (tramite Proxmox Community Helper Scripts / ex tteck):**
   * Nel Shell di Proxmox VE (nodo principale), incolla il seguente comando:
     ```bash
     bash -c "$(wget -qLO - https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh)"
     ```
   * Segui la procedura guidata e seleziona le impostazioni predefinite.

2. **Creazione manuale LXC Docker (se preferisci farlo a mano):**
   * Crea un CT LXC (Ubuntu/Debian).
   * **IMPORTANTE:** Nelle opzioni del container, abilita **Nesting** (`Options -> Features -> Nesting: Checked`).
   * Installa Docker all'interno del container:
     ```bash
     apt update && apt install -y curl git
     curl -fsSL https://get.docker.com | sh
     ```

---

### Opzione B: Macchina Virtuale (VM Ubuntu Server)
Se gestisci le tue app all'interno di una VM Linux dedicata:
* Installa Docker e Git nella VM:
  ```bash
  sudo apt update && sudo apt install -y curl git
  curl -fsSL https://get.docker.com | sudo sh
  ```

---

## 📥 2. Deploy dell'Applicazione

Accedi via SSH al tuo container LXC o VM su Proxmox ed esegui:

```bash
# 1. Clona la repository
git clone https://github.com/ELfrancia/wger-elfrancia.git
cd wger-elfrancia
```

---

## 📂 3. Copia dei Dati Esistenti (Database e Media)

Copia i tuoi dati (`database.sqlite` e la cartella `media/`) dentro la cartella `wger-elfrancia/` del tuo container su Proxmox usando uno di questi metodi:

### Metodo 1: Con WinSCP o FileZilla (Interfaccia Grafica - Consigliato da Windows)
1. Scarica ed apri **WinSCP** o **FileZilla** sul tuo PC.
2. Crea una connessione **SFTP**:
   * **Host:** L'indirizzo IP del container LXC o VM su Proxmox
   * **Porta:** 22
   * **Utente:** `root`
   * **Password:** La password SSH del tuo container LXC / VM
3. Nel pannello di destra naviga fino a `/root/wger-elfrancia/`.
4. Trascina dal PC locale (pannello di sinistra) il file **`database.sqlite`** e l'intera cartella **`media/`** direttamente in `/root/wger-elfrancia/`.

---

### Metodo 2: Da PowerShell / Terminale Windows (Con SCP)
Apri il PowerShell sul tuo PC nella cartella del progetto ed esegui:

```powershell
# Trasferisci il file del database
scp database.sqlite root@<IP_CONTAINER_PROXMOX>:/root/wger-elfrancia/

# Trasferisci l'intera cartella media
scp -r media root@<IP_CONTAINER_PROXMOX>:/root/wger-elfrancia/
```

---

### Metodo 3: Dal Nodo Proxmox se la cartella media è sul NAS
Se il tuo NAS è montato come Storage su Proxmox, puoi trasferire i file nel container LXC usando il comando nativo `pct push`:

```bash
# Esegui nella shell del nodo Proxmox VE (sostituisci 100 con l'ID del tuo LXC):
pct push 100 /percorso/sul/nas/database.sqlite /root/wger-elfrancia/database.sqlite
pct push 100 /percorso/sul/nas/media /root/wger-elfrancia/media -r
```

---

## 🚀 4. Avvio dell'App con Docker Compose

Esegui il comando di avvio nella cartella `wger-elfrancia/`:

```bash
docker compose up -d --build
```

L'applicazione sarà accessibile all'indirizzo:
👉 `http://<IP_PROXMOX_CONTAINER>:8000`

---

## 🌐 5. Configurazione per Reverse Proxy & Variabili d'Ambiente

In produzione (es. dietro reverse proxy come Nginx Proxy Manager, Cloudflare Tunnel, Caddy), configura le variabili d'ambiente necessarie in `docker-compose.yml` o tramite file `.env`:

```yaml
environment:
  - DJANGO_SETTINGS_MODULE=settings.main
  - DJANGO_DEBUG=False
  - DJANGO_SECRET_KEY=genera-una-chiave-segreta-lunga-e-casuale-qui
  - ALLOWED_HOSTS=onyx.francescoadreani.dev,localhost,127.0.0.1
  - CSRF_TRUSTED_ORIGINS=https://onyx.francescoadreani.dev
  - AXES_ENABLED=True
  - X_FORWARDED_PROTO_HEADER_SET=True
  - DJANGO_DB_DATABASE=/app/database.sqlite
```

> ⚠️ **Sicurezza in Produzione:**
> - `DJANGO_SECRET_KEY`: Imposta sempre una chiave casuale e robusta (mai lasciare il default).
> - `ALLOWED_HOSTS`: Includi il tuo dominio pubblico per prevenire attacchi di Host Header poisoning.
> - `CSRF_TRUSTED_ORIGINS`: Includi l'URL completo con schema (`https://...`).
> - `DJANGO_DEBUG`: Lasciare impostato su `False`.

E riavvia il container:
```bash
docker compose up -d
```

---

## 🔄 6. Backup Automatico e Aggiornamenti

### Per aggiornare l'app in futuro:
```bash
cd wger-elfrancia
git pull
docker compose up -d --build
```

### Per fare un backup dei dati:
I tuoi dati risiedono direttamente sul file system nella cartella dell'app:
* `database.sqlite`
* cartella `media/`

Puoi includerli nella routine di backup di Proxmox (PBS) o sincronizzarli col NAS.
