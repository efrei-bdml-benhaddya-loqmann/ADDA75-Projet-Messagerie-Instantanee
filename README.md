# Messagerie instantanée entre deux appareils — ADDA75

Projet de synthèse du module **API et Web Services** ([énoncé](Projet_Messagerie_Instantanee.md)).
Un serveur central FastAPI expose une API REST (comptes, connexion, présence, historique) et un
canal WebSocket (messages en temps réel). Deux clients web distincts — **bureau** et **mobile** —
communiquent uniquement via ce serveur.

```text
Client bureau (PC)            Client mobile (téléphone)
        │  REST : comptes, login, utilisateurs, historique  │
        │  WebSocket : messages, accusés, saisie            │
        └──────────────────────┬────────────────────────────┘
                     Serveur FastAPI (uvicorn)
                               │
                     SQLite (backend/data/messagerie.db)
```

## Prérequis

- [uv](https://docs.astral.sh/uv/) (installe lui-même Python 3.13 si besoin)
- Un navigateur sur chaque appareil, les deux appareils sur le **même réseau** (Wi-Fi)

## Lancer le projet

```bash
cd backend
uv sync                         # installe les dépendances (pyproject.toml + uv.lock)
cp .env.example .env            # puis remplacer JWT_SECRET :
python3 -c "import secrets; print(secrets.token_hex(32))"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` rend le serveur joignable depuis les autres appareils du réseau.
Adresse IP de l'ordinateur serveur : `ipconfig getifaddr en0` (macOS) ou `ip -4 addr` (Linux).

Les clients sont servis par le même serveur :

| Page | URL |
| :--- | :--- |
| Choix du client | `http://<IP>:8000/clients/` |
| Client bureau | `http://<IP>:8000/clients/desktop/` |
| Client mobile | `http://<IP>:8000/clients/mobile/` |
| Swagger (doc OpenAPI) | `http://<IP>:8000/docs` |
| Santé | `http://<IP>:8000/health` |

## Scénario de démonstration (énoncé §2.1)

1. **Appareil A** (ordinateur) : ouvrir le client bureau, saisir un nom et un mot de passe, « Créer un compte ».
2. **Appareil B** (téléphone) : ouvrir le client mobile, créer un second compte.
   Chaque client voit l'autre dans sa liste de conversations, avec « En ligne » et un **point vert**.
3. Sur A, cliquer sur le contact et envoyer un message : il apparaît **immédiatement** sur B
   (point bleu « non lu » dans la liste, ou directement dans la conversation ouverte).
4. Répondre depuis B : le message apparaît immédiatement sur A.
5. Sur A, « Se déconnecter », puis se reconnecter : en rouvrant le contact, **tout l'historique**
   est rechargé depuis le serveur (`GET /api/messages/{id}`).

À observer en plus :
- le statut sous son dernier message envoyé, comme dans iMessage : « Envoyé » (stocké sur le
  serveur, destinataire hors ligne), « Distribué », « Lu » ;
- la bulle « … » animée pendant que l'autre écrit ;
- un message envoyé à un destinataire hors ligne affiche dans la console du serveur
  `Webhook simulé : notification envoyée à l'utilisateur …`, puis passe à « Distribué » à sa reconnexion ;
- au-delà de 10 messages en 10 secondes, le client affiche le message anti-spam ;
- le panneau repliable « Journal REST / WebSocket » (en bas de la barre latérale ou de la liste)
  détaille chaque échange.

L'interface reprend celle de Messages (iMessage) sur macOS et iOS, y compris le mode sombre.

## API

| Méthode | URL | Auth | Rôle |
| :--- | :--- | :---: | :--- |
| `POST` | `/api/comptes` | — | Créer un compte `{username, motDePasse}` → `201` (`409` si pris, `422` si invalide) |
| `POST` | `/api/auth/login` | — | Obtenir un JWT `{token, tokenType}` (`401` si faux, `429` après 5 essais/min) |
| `GET` | `/api/utilisateurs` | JWT | Utilisateurs et statut `connecte` |
| `GET` | `/api/messages/{utilisateurId}` | JWT | Historique avec cet utilisateur, trié par date (`404` si inconnu) |
| `WS` | `/ws/messages?token=<JWT>` | JWT | Canal temps réel (fermé avec le code `1008` si le jeton est invalide) |

Toute requête protégée sans jeton valide reçoit `401 Unauthorized`. Les erreurs ont toujours le
format `{"detail": "...", "code": "..."}`.

Trames WebSocket :

| Sens | Trame |
| :--- | :--- |
| client → serveur | `{"type": "message", "destinataireId": 2, "contenu": "Bonjour !"}` |
| serveur → destinataire | `{"type": "message", "id", "expediteurId", "destinataireId", "contenu", "dateEnvoi", "statut"}` |
| serveur → expéditeur | `{"type": "ack", ...mêmes champs}` (statut `envoye` ou `livre`) |
| serveur → expéditeur | `{"type": "delivered_ack", "destinataireId", "messageIds"}` à la reconnexion du destinataire |
| client → serveur | `{"type": "read", "expediteurId": 1}` → l'expéditeur reçoit `{"type": "read_ack", "readerId", "messageIds"}` |
| client ↔ serveur | `{"type": "typing", "destinataireId": 2, "isTyping": true}` |
| client → serveur | `{"type": "ping"}` → `{"type": "pong"}` |
| serveur → client | `{"type": "error", "code": "RATE_LIMITED" \| "DESTINATAIRE_INCONNU" \| "JSON_INVALIDE" \| ..., "detail"}` |

`expediteurId` et `dateEnvoi` ne sont jamais lus depuis le client : le serveur les déduit du JWT et
de son horloge.

## Tests

```bash
cd backend
uv run pytest        # tests automatisés REST + WebSocket
uv run ruff check .  # lint
```

Collection **Bruno** (REST, avec assertions et tests automatisés, comme aux TP1/TP2) :
[`docs/bruno/`](docs/bruno/). L'ouvrir dans Bruno (*Open Collection*), choisir l'environnement
`Local`, puis *Run* sur la collection. En ligne de commande, serveur lancé :

```bash
cd docs/bruno
npx @usebruno/cli run -r --env Local
```

Si la CLI échoue avec `Cannot find module '@jitl/quickjs-wasmfile-…'` (Node 26), ajouter les
modules manquants :
`npx -p @usebruno/cli -p @jitl/quickjs-wasmfile-debug-asyncify -p @jitl/quickjs-wasmfile-release-asyncify -p @jitl/quickjs-wasmfile-debug-sync -p @jitl/quickjs-wasmfile-release-sync bru run -r --env Local`.

Un export Postman équivalent est fourni dans [`docs/postman/`](docs/postman/). Pour tester le
WebSocket à la main dans Postman : *New → WebSocket*, URL
`ws://localhost:8000/ws/messages?token=<JWT>`, puis envoyer les trames ci-dessus.

## Structure

```text
backend/app/
  core/       config, base de données, erreurs, rate limiting
  users/      modèle User, POST /api/comptes, GET /api/utilisateurs
  auth/       bcrypt, JWT, get_current_user, POST /api/auth/login
  messages/   modèle Message, service, GET /api/messages/{id}
  realtime/   ConnectionManager (présence), /ws/messages, webhook simulé
backend/tests/   pytest
clients/
  common/     api.js (REST + WebSocket), chat.js (logique d'interface partagée)
  desktop/    client bureau
  mobile/     client mobile
docs/rapport/ rapport
docs/bruno/   collection Bruno (REST + tests)
docs/postman/ export Postman de la même collection
```

## Limites connues

- Un seul worker uvicorn : les connexions WebSocket et les compteurs anti-spam sont en mémoire
  (voir le rapport pour le passage à l'échelle avec Redis).
- HTTP/WS en clair sur le réseau local ; en production il faudrait HTTPS/WSS (reverse proxy TLS).
- Une connexion WebSocket par utilisateur : si le même compte s'ouvre deux fois, la plus récente
  reçoit les messages.
