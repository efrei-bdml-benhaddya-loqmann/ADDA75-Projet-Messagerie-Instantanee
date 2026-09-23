# Roadmap — Messagerie Instantanée (Python)

> Document de travail partagé. Une case cochée = code mergé sur `main` **et relu par l'autre**.
> Référence unique des exigences : [`Projet_Messagerie_Instantanee.md`](Projet_Messagerie_Instantanee.md).

## 0. Décisions techniques (à valider ensemble avant de coder)

| Sujet | Choix | Pourquoi |
| :--- | :--- | :--- |
| Langage | Python 3.12+ | Accord du prof |
| Framework | **FastAPI** + Uvicorn | REST et WebSocket natifs dans le même serveur, validation JSON via Pydantic, OpenAPI généré automatiquement |
| Dépendances | `uv` (`pyproject.toml` + `uv.lock`) | Environnement reproductible pour nous deux et pour le correcteur |
| ORM | SQLAlchemy 2.0 (mode synchrone) | Standard Python, requêtes typées |
| Base de données | **SQLite fichier** (`data/messagerie.db`), PostgreSQL possible via `DATABASE_URL` | Équivalent Python de H2 embarqué accepté par l'énoncé. **Fichier**, pas mémoire : l'historique doit survivre au redémarrage (démo étape 5) |
| Hachage mot de passe | `pwdlib[bcrypt]` | `passlib` n'est plus maintenu |
| JWT | `PyJWT` (HS256, expiration courte) | Équivalent direct du TP4 |
| Configuration | `pydantic-settings` + `.env` (non commité) | Clé secrète JWT hors du code |
| Tests | `pytest` + `TestClient` FastAPI (gère aussi les WebSocket) | Automatiser ce qu'on testerait à la main dans Postman |
| Qualité | `ruff` (lint + format) | Même style de code pour nous deux |
| Clients | 2 pages HTML/JS vanilla (`desktop/`, `mobile/`) + `common/api.js` partagé | Le front n'est pas noté sur le design |
| Bonus | Accusé de réception **+** rate limiting **+** Swagger | Swagger est quasi gratuit avec FastAPI, donc on ne compte pas dessus seul : les deux autres montrent une vraie maîtrise |

### Points d'attention propres à Python/FastAPI
- **JSON en camelCase, code en snake_case** : l'énoncé impose `expediteurId`, `dateEnvoi`, `motDePasse`. On écrit `expediteur_id` en Python et on configure les schémas Pydantic avec `alias_generator=to_camel` + `populate_by_name=True`.
- **401 et pas 403** : vérifier qu'une requête sans token renvoie bien `401 Unauthorized` (piège connu avec `HTTPBearer` selon la version de FastAPI). On écrit notre propre dépendance `get_current_user` qui lève `HTTPException(401)`.
- **Auth WebSocket** : pas de header `Authorization` possible depuis le `WebSocket` JS du navigateur → token en query param `?token=...`, vérifié **avant** `websocket.accept()`. Si invalide : fermeture avec le code `1008` (policy violation).
- **Sync vs async** : les routes REST en `def` (FastAPI les exécute dans un thread). Dans le handler WebSocket (`async def`), les accès BDD passent par `run_in_threadpool` pour ne pas bloquer la boucle d'événements.
- **Un seul worker Uvicorn** : les connexions WebSocket sont gardées en mémoire dans le process. Avec plusieurs workers il faudrait un bus partagé (Redis pub/sub) — à mentionner dans le rapport.
- **Dates** : générées côté serveur en UTC, sérialisées en ISO 8601 (`2026-09-21T10:15:30`).

## 1. Structure du repo

Organisation **par domaine** : chacun de nous possède ses dossiers, ce qui limite les conflits Git.

```text
P1/
├── backend/
│   ├── pyproject.toml
│   ├── .env.example                 JWT_SECRET, DATABASE_URL…
│   ├── app/
│   │   ├── main.py                  création de l'app, inclusion des routers
│   │   ├── core/                    config.py, database.py, errors.py      (commun)
│   │   ├── users/                   models.py, schemas.py, service.py, router.py   (A)
│   │   ├── auth/                    security.py (hash + JWT), deps.py (get_current_user), router.py   (A)
│   │   ├── messages/                models.py, schemas.py, service.py, router.py   (B)
│   │   └── realtime/                manager.py (connexions + présence), router.py (/ws/messages)   (B)
│   └── tests/                       test_accounts.py, test_auth.py, test_messages.py, test_ws.py
├── clients/
│   ├── common/api.js                appels REST + connexion WS
│   ├── desktop/                     page « bureau »   (A)
│   └── mobile/                      page « mobile »   (B)
├── docs/
│   ├── rapport/                     rapport 5–8 pages
│   └── postman/                     collection Postman (REST + WS)
└── README.md                        comment lancer le projet
```

## 2. Contrats partagés (à écrire ENSEMBLE en étape 0)

Ce sont les seuls points de contact entre nos deux parties. Une fois figés, on peut avancer en parallèle.

**`auth/security.py`** — écrit par A, utilisé par B dans le WebSocket
```python
def create_access_token(user_id: int) -> str: ...
def decode_access_token(token: str) -> int: ...   # renvoie user_id, lève InvalidTokenError si invalide/expiré
```

**`auth/deps.py`** — écrit par A, utilisé par B dans `GET /api/messages/{id}`
```python
def get_current_user(...) -> User: ...            # 401 si token absent/invalide
```

**`realtime/manager.py`** — écrit par B, lu par A dans `GET /api/utilisateurs`
```python
class ConnectionManager:
    async def connect(self, user_id: int, ws: WebSocket) -> None: ...
    def disconnect(self, user_id: int) -> None: ...
    def is_online(self, user_id: int) -> bool: ...
    async def send_to(self, user_id: int, payload: dict) -> bool: ...   # False si hors ligne
```

**Endpoints et JSON**
| Méthode | URL | Entrée | Sortie | Erreurs |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/comptes` | `{username, motDePasse}` | `201 {id, username}` | `400`/`422` champs invalides, `409` username pris |
| `POST` | `/api/auth/login` | `{username, motDePasse}` | `200 {token, tokenType: "bearer"}` | `401` identifiants faux |
| `GET` | `/api/utilisateurs` | — | `200 [{id, username, connecte}]` | `401` |
| `GET` | `/api/messages/{utilisateurId}` | — | `200 [{id, expediteurId, destinataireId, contenu, dateEnvoi}]` trié par date | `401`, `404` utilisateur inconnu |
| `WS` | `/ws/messages?token=...` | format §4 de l'énoncé | format §4 de l'énoncé | fermeture `1008` si token invalide |

**Règles de sécurité communes**
- L'`expediteurId` est **toujours** déduit du JWT, jamais lu depuis le JSON du client.
- La `dateEnvoi` est **toujours** générée par le serveur.
- Le mot de passe n'apparaît jamais dans une réponse ni dans les logs.

## 3. Répartition

Principe : **chacun possède un domaine backend complet** (modèle → service → route → tests), et **chacun relit toutes les PR de l'autre**. En soutenance, les deux doivent pouvoir expliquer tout le projet.

### 👤 Loqmann (A) — Identité & sécurité
Barème : API REST (3) + JWT (3) + une partie de l'architecture (4) et du bonus (2).

- [ ] Squelette : `uv init`, dépendances, `main.py`, `core/config.py`, `core/database.py`, `.env.example`, ruff
- [ ] Modèle `User` (username unique, `password_hash`)
- [ ] `POST /api/comptes` : hachage, `409` si doublon, validation Pydantic
- [ ] `POST /api/auth/login` : vérification, génération du JWT, `401` si échec
- [ ] `security.py` + `get_current_user` (401 garanti)
- [ ] `GET /api/utilisateurs` avec `connecte` via `ConnectionManager.is_online`
- [ ] Format d'erreur JSON homogène (`core/errors.py`)
- [ ] Tests pytest : comptes, login, 401 sans token / token expiré / token falsifié
- [ ] Bonus **rate limiting** : module `core/rate_limit.py` (fenêtre glissante par utilisateur) utilisé par B dans le handler WS + sur `/api/auth/login` (anti brute-force)
- [ ] Bonus **Swagger** soigné : bouton « Authorize » JWT, exemples, descriptions
- [ ] Client **desktop** + partie REST de `common/api.js` (inscription, login, liste utilisateurs, historique)
- [ ] Rapport : schéma d'architecture, **question REST vs WebSocket pour l'historique**, choix sécurité

### 👤 Binôme (B) — Messages & temps réel
Barème : WebSocket (5) + persistance (2) + une partie de l'architecture (4) et du bonus (2).

- [ ] Modèle `Message` (FK vers `User`, index sur le couple expéditeur/destinataire)
- [ ] `messages/service.py` : `save_message(...)`, `get_conversation(user_a, user_b)`
- [ ] `GET /api/messages/{utilisateurId}` (d'abord sans sécurité, puis avec `get_current_user`)
- [ ] `ConnectionManager` (connexions + présence)
- [ ] Endpoint `/ws/messages` : vérif du token avant `accept()`, boucle de réception, validation du JSON par un schéma Pydantic
- [ ] Traitement d'un message : **persister** → **retransmettre** au destinataire s'il est connecté → confirmer à l'expéditeur
- [ ] Destinataire hors ligne : message persisté, récupéré via l'historique à la reconnexion
- [ ] Nettoyage propre à la déconnexion (`WebSocketDisconnect`)
- [ ] Tests pytest : WS refusé sans token, message A → B reçu, message persisté
- [ ] Bonus **accusé de réception** (`envoye` / `livre` / `lu`)
- [ ] Client **mobile** + partie WebSocket de `common/api.js` (connexion, envoi, réception)
- [ ] Rapport : **question destinataire hors ligne (lien avec Kafka)**, difficultés du temps réel

### 👥 Ensemble
- [ ] Étape 0 : valider ce document, écrire les contrats (section 2) en stubs
- [ ] Collection Postman commune (REST + WebSocket)
- [ ] Test réel : 2 machines sur le même réseau (`uvicorn --host 0.0.0.0`, CORS configuré)
- [ ] README (installation `uv sync`, lancement backend, ouverture des clients)
- [ ] Répétition du scénario de démo §2.1 + captures d'écran pour le rapport
- [ ] Relecture croisée du rapport

## 4. Ordre des étapes (suit le §7 de l'énoncé)

| # | Étape | A (Loqmann) | B (Binôme) | Critère de fin |
| :-: | :--- | :--- | :--- | :--- |
| 0 | Cadrage | Squelette projet | Relit le squelette, écrit le stub `ConnectionManager` | `uv run uvicorn app.main:app` démarre, contrats en place |
| 1 | Modèles & BDD | `User` | `Message` | Tables créées dans SQLite |
| 2 | REST sans sécurité | comptes, login (sans JWT), utilisateurs | historique | Tout passe dans Postman |
| 3 | JWT | `security.py`, `get_current_user` | branche l'historique sur l'utilisateur courant | `401` vérifié par un test |
| 4 | WebSocket | relit, branche la présence dans `/api/utilisateurs` | manager, endpoint, traitement des messages | Message A → B avec 2 clients Postman |
| 5 | Clients | desktop | mobile | Démo complète sur 2 machines |
| 6 | Bonus | rate limiting + Swagger | accusé de réception | |
| 7 | Livrables | ses sections du rapport + README | ses sections du rapport | Rapport relu, démo répétée |

## 5. Workflow Git

- `main` toujours fonctionnel. Pas de push direct dessus.
- Une branche par tâche : `feat/auth-jwt`, `feat/ws-endpoint`, …
- Commits conventionnels : `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- **PR obligatoire, relue et approuvée par l'autre** avant merge. `ruff check` et `pytest` passent avant d'ouvrir la PR.
- La relecture sert à apprendre la partie de l'autre : poser les questions dans la PR.

## 6. Ce que chacun doit savoir expliquer à la soutenance

- Pourquoi REST pour comptes/historique/utilisateurs et WebSocket pour les messages (et pourquoi pas le polling).
- Le cycle de vie du JWT : création au login → `Authorization: Bearer` en REST → query param au handshake WS → validation.
- Pourquoi le mot de passe est haché avec un sel (bcrypt) et jamais renvoyé.
- Le chemin complet d'un message : client A → WS → serveur (validation, persistance) → WS → client B.
- Ce qui se passe si B est hors ligne.
- Pourquoi `expediteurId` et `dateEnvoi` ne viennent pas du client.
- Pourquoi l'état des connexions en mémoire limite à un seul worker, et comment on passerait à l'échelle.
