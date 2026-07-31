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

Copia i tuoi dati salvati sul **NAS** o nel PC locale dentro la cartella `wger-elfrancia/` del server Proxmox:

* 📄 **`database.sqlite`** ➔ posizionalo in `wger-elfrancia/database.sqlite`
* 📁 **`media/`** ➔ posizionala in `wger-elfrancia/media/`

> **Esempio di trasferimento da PC a Proxmox tramite SCP:**
> ```bash
> scp database.sqlite root@<IP_PROXMOX_CONTAINER>:/root/wger-elfrancia/
> scp -r media root@<IP_PROXMOX_CONTAINER>:/root/wger-elfrancia/
> ```

---

## 🚀 4. Avvio dell'App con Docker Compose

Esegui il comando di avvio nella cartella `wger-elfrancia/`:

```bash
docker compose up -d --build
```

L'applicazione sarà accessibile all'indirizzo:
👉 `http://<IP_PROXMOX_CONTAINER>:8000`

---

## 🌐 5. Configurazione per Reverse Proxy (Nginx Proxy Manager / Cloudflare Tunnel)

Se accedi all'app tramite dominio esterno (es. `https://onyx.francescoadreani.dev`), aggiungi il dominio al file `docker-compose.yml` nella variabile `CSRF_TRUSTED_ORIGINS`:

```yaml
environment:
  - CSRF_TRUSTED_ORIGINS=https://tuodominio.it,http://tuodominio.it
```

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
