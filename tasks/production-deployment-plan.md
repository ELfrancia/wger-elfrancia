# Piano di implementazione: deployment di produzione su Proxmox

## Obiettivo

Pubblicare Workout App in modo sicuro e mantenibile su un container LXC/VM
Proxmox usando Docker Compose. L'architettura scelta e' **Caddy + Gunicorn +
Django + PostgreSQL + Redis**.

Gunicorn e' il server WSGI di produzione, Caddy termina HTTPS e inoltra le
richieste, PostgreSQL sostituisce SQLite per i dati applicativi e Redis offre
cache e supporto affidabile a sessioni e rate limiting. E' la scelta piu'
solida per un'app personale o familiare self-hosted: potente, semplice da
gestire e senza componenti superflui.

## Architettura

```text
Internet / LAN
       |
       v
Caddy (porte 80/443, certificati TLS automatici)
       |
       v
Gunicorn + Django (rete Docker privata)
       |---------------------|
       v                     v
PostgreSQL                Redis
       |
       v
volume Docker + backup Proxmox/NAS
```

## Decisioni architetturali

- Usare Caddy anziche' esporre Gunicorn sulla rete: HTTPS automatico, reverse
  proxy, compressione e configurazione molto piu' snella di Nginx.
- Usare PostgreSQL anziche' SQLite: evita i limiti di concorrenza e rende
  affidabili backup e futuri aggiornamenti.
- Tenere Redis in rete privata: cache, sessioni e protezione login; nessuna
  porta Redis o PostgreSQL esposta all'esterno.
- Usare `settings.main` con `DJANGO_DEBUG=False`, mai `settings.local_dev`.
- Gestire segreti e parametri di produzione in un file `.env` escluso da Git.
- Non montare il codice sorgente nel container di produzione: l'immagine deve
  essere immutabile e ricostruibile.

## Attivita'

### Fase 1 - Preparazione e sicurezza

#### Task 1: Inventario e backup pre-migrazione

**Descrizione:** fermare la strada verso il deploy solo dopo aver verificato
il database SQLite corrente, la cartella media e la disponibilita' dei backup.

**Criteri di accettazione:**

- [ ] Backup consistente di `database.sqlite` e `media/` salvato sul NAS.
- [ ] Backup testato aprendo una copia del database o ripristinandola in una
      cartella temporanea.
- [ ] Inventariati dominio, DNS pubblico e IP/LAN del container Proxmox.

**Verifica:** checksum dei backup e dimensioni coerenti con gli originali.

**Dipendenze:** nessuna.

#### Task 2: Segreti e impostazioni Django di produzione

**Descrizione:** creare un `.env` non versionato con chiavi persistenti,
dominio e configurazione sicura; rimuovere i valori permissivi destinati allo
sviluppo.

**Criteri di accettazione:**

- [ ] `DJANGO_SETTINGS_MODULE=settings.main` e `DJANGO_DEBUG=False`.
- [ ] `SECRET_KEY` e chiavi JWT sono uniche, persistenti e non presenti nel
      repository.
- [ ] `SITE_URL`, `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` contengono solo il
      dominio e gli indirizzi realmente usati.
- [ ] Abilitati proxy HTTPS (`X_FORWARDED_PROTO_HEADER_SET=True`) e cookie
      sicuri quando l'accesso e' solo HTTPS.

**Verifica:** `python manage.py check --deploy` non riporta errori critici.

**Dipendenze:** Task 1.

### Checkpoint: configurazione pronta

- [ ] I segreti non sono tracciati da Git.
- [ ] Il controllo Django per il deploy e' pulito o ogni avviso residuo e'
      esplicitamente gestito.

### Fase 2 - Servizi containerizzati

#### Task 3: Immagine Django/Gunicorn di produzione

**Descrizione:** separare il runtime di produzione da quello di sviluppo,
avviando Gunicorn e raccogliendo gli statici durante build/deploy.

**Criteri di accettazione:**

- [ ] Il comando del servizio web e' Gunicorn, mai `manage.py runserver`.
- [ ] Nessun bind mount del progetto o `node_modules` nel compose di
      produzione.
- [ ] Le migrazioni e `collectstatic` sono eseguite in modo ripetibile prima
      dell'avvio applicativo.
- [ ] Gunicorn ha timeout, graceful shutdown e numero di worker parametrizzati
      per CPU/RAM del LXC.

**Verifica:** log del container mostra Gunicorn; riavvio senza warning del
development server.

**Dipendenze:** Task 2.

#### Task 4: PostgreSQL e migrazione da SQLite

**Descrizione:** aggiungere PostgreSQL con volume persistente e trasferire i
dati esistenti con una procedura reversibile.

**Criteri di accettazione:**

- [ ] PostgreSQL e' accessibile esclusivamente dalla rete Docker.
- [ ] Il database usa un volume nominato incluso nel backup Proxmox/NAS.
- [ ] Dump dati SQLite, migrazioni e import PostgreSQL completano senza errori.
- [ ] Dopo il passaggio, utenti, schede, allenamenti e immagini restano
      disponibili.

**Verifica:** conteggi dei modelli principali prima/dopo e test manuale di
login, consultazione scheda e salvataggio allenamento.

**Dipendenze:** Task 1, Task 2.

#### Task 5: Redis per cache e sessioni

**Descrizione:** rendere la cache condivisa fra worker Gunicorn e migliorare
la gestione delle sessioni/rate limiting.

**Criteri di accettazione:**

- [ ] Redis non ha porte pubblicate sull'host.
- [ ] Django usa `django_redis.cache.RedisCache` tramite variabili d'ambiente.
- [ ] Riavvio di un worker non invalida impropriamente la sessione attiva.

**Verifica:** health check Redis e shell Django che legge/scrive la cache.

**Dipendenze:** Task 2.

### Checkpoint: applicazione in rete privata

- [ ] `docker compose up -d --build` avvia web, database e cache.
- [ ] Django supera migrazioni e controlli di sicurezza.
- [ ] Porte 5432 e 6379 non sono raggiungibili dalla LAN.

### Fase 3 - HTTPS e pubblicazione

#### Task 6: Caddy come reverse proxy

**Descrizione:** aggiungere Caddy davanti a Gunicorn, esponendo soltanto le
porte HTTP/HTTPS e servendo statici/media in modo efficiente.

**Criteri di accettazione:**

- [ ] Solo Caddy pubblica le porte 80 e 443; Gunicorn resta interno.
- [ ] Il certificato TLS e il redirect HTTP -> HTTPS sono automatici.
- [ ] Statici e media sono serviti tramite volumi condivisi senza passare da
      Django quando possibile.
- [ ] Header `X-Forwarded-Proto` e `Host` raggiungono Django correttamente.

**Verifica:** test esterno HTTPS, upload/download media, login e POST protetto
da CSRF attraverso il dominio reale.

**Dipendenze:** Task 3, Task 4, Task 5.

#### Task 7: Firewall, DNS e accesso amministrativo

**Descrizione:** limitare la superficie esposta e rendere raggiungibile il
servizio con un dominio stabile.

**Criteri di accettazione:**

- [ ] DNS A/AAAA punta al proxy o al router corretto; per TLS pubblico le porte
      80/443 arrivano a Caddy.
- [ ] Firewall consente solo 80/443 pubblici e SSH amministrativo limitato.
- [ ] Account amministratore usa password forte e 2FA, se abilitata.

**Verifica:** scansione delle porte dall'esterno e accesso HTTPS da una rete
esterna.

**Dipendenze:** Task 6.

### Fase 4 - Operativita'

#### Task 8: Health check, log e backup automatici

**Descrizione:** definire la manutenzione ordinaria per evitare perdita di
dati e rilevare problemi rapidamente.

**Criteri di accettazione:**

- [ ] Health check Compose per web, PostgreSQL e Redis.
- [ ] Log dei container consultabili e con rotazione configurata.
- [ ] Backup giornaliero PostgreSQL (`pg_dump`) e copia di `media/` sul NAS.
- [ ] Eseguito almeno un ripristino completo di prova.

**Verifica:** simulazione di restore in una directory/istanza separata.

**Dipendenze:** Task 4, Task 6.

#### Task 9: Documentazione operativa

**Descrizione:** aggiornare le guide locali con i comandi sicuri di deploy,
aggiornamento, rollback e recovery.

**Criteri di accettazione:**

- [ ] Documentati avvio, aggiornamento, visualizzazione log e backup.
- [ ] Documentati rollback dell'immagine e ripristino PostgreSQL/media.
- [ ] Distinta chiaramente la procedura locale di sviluppo da quella Proxmox.

**Verifica:** seguire la guida su una macchina pulita o in un container di
prova.

**Dipendenze:** Task 8.

## Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Errore nella migrazione SQLite -> PostgreSQL | Alto | Backup verificato, import in staging e rollback sul file SQLite originale. |
| Certificato HTTPS non emesso | Medio | Verificare DNS e inoltro porte 80/443 prima di avviare Caddy. |
| Perdita di sessioni al riavvio | Medio | `SECRET_KEY` persistente e Redis con volume/backup ove necessario. |
| Risorse LXC insufficienti | Medio | Partire con 2 worker Gunicorn, monitorare e tarare in base a CPU/RAM. |
| Segreti nel repository | Alto | `.env` ignorato, `.env.example` senza valori reali, rotazione se una chiave e' stata esposta. |

## Definizione di completamento

- [ ] Nessun processo usa `runserver` nel deployment Proxmox.
- [ ] L'app e' disponibile via HTTPS con certificato valido.
- [ ] Dati e media risiedono in storage persistente e sono stati ripristinati
      con successo almeno una volta.
- [ ] `python manage.py check --deploy` e i test mirati passano.
- [ ] Aggiornamento e rollback sono documentati e ripetibili.
