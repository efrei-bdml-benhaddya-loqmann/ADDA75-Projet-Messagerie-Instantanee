# Rapport de Synthèse — Application de Messagerie Instantanée

**Module :** ADDA75 — API et Web Services  
**Formation :** Master Ingénierie Informatique  
**Auteurs :**  
- Loqmann Benhaddya (Binôme B : Messages, Persistance & Temps Réel WebSocket)  
- Binôme (Binôme A : Identité, Sécurité JWT & API REST)  

---

<!-- TODO: Section 1 (Architecture globale & schéma) complétée et relue par Binôme A -->

## 1. Vue d'ensemble de l'architecture

Le projet repose sur une stricte séparation des responsabilités entre opérations synchrones transactionnelles (REST / HTTP) et acheminement bidirectionnel asynchrone (WebSocket) :

```text
Appareil A (Desktop / Web)                  Appareil B (Mobile / Smartphone)
       │                                                   │
       │   HTTPS REST (Auth, Historique, Utilisateurs)     │
       │   WSS WebSocket (Messages temps réel, Accusés)    │
       │                                                   │
       └─────────────────────────┬─────────────────────────┘
                                 │
                     SERVEUR CENTRAL (FastAPI)
                     ├── Auth & Deps (JWT HS256)
                     ├── Messages REST (Historique)
                     └── Realtime WebSocket (ConnectionManager)
                                 │
                     BASE DE DONNÉES (SQLite / PostgreSQL)
                     ├── Table 'users'
                     └── Table 'messages' (indexée sur exp_id, dest_id)
```

### Justification de la séparation REST / WebSocket
<!-- TODO: Binôme A finalisera la réponse détaillée sur la propriété REST (cache, URL identifiable) -->
- **REST pour les comptes, l'authentification et l'historique :** Ce sont des opérations ponctuelles de lecture/écriture de ressources bien identifiées par des URIs (`/api/messages/{id}`). L'historique bénéficie des propriétés fondamentales de REST : mise en cache possible par les intermédiaires, pagination standardisée, et requêtes atomiques indépendantes.
- **WebSocket pour le flux instantané :** Canal persistant duplex à très faible surcharge (overhead de trame réduit à quelques octets après le handshake HTTP initial), indispensable pour que le serveur pousse immédiatement une notification au destinataire sans recourir au polling.

---

## 2. Gestion du destinataire hors ligne & Parallèle avec Apache Kafka

### 2.1. Comportement du serveur en cas d'absence du destinataire
Lorsqu'un client A émet un message destiné à un client B qui n'a pas de connexion WebSocket active :
1. **Aucune perte de données :** Le serveur persiste systématiquement le message dans la table relationnelle `messages` avec l'horodatage UTC généré côté serveur.
2. **Accusé de réception adapté :** Le serveur assigne initialement au message le statut `envoye` (et non `livre`). L'expéditeur reçoit un acquittement WebSocket (`type: "ack"`, `statut: "envoye"`), l'informant que son message est stocké sur le serveur mais en attente de livraison au terminal de B.
3. **Récupération à la reconnexion :** Lorsque le client B se reconnecte ultérieurement (ou rouvre son application), il effectue une requête REST `GET /api/messages/{expediteur_id}`. L'historique complet, incluant les messages envoyés en son absence, lui est retourné ordonné chronologiquement. Dès consultation, B émet une trame `read` qui met à jour le statut en `lu` et notifie l'expéditeur si celui-ci est en ligne.

### 2.2. Parallèle architectural avec Apache Kafka (Chapitre 6)
Cette problématique met en lumière les différences fondamentales entre systèmes de messagerie éphémères et journaux d'événements distribués :

| Caractéristique | WebSocket pur sans persistance | Message Broker classique (ex: AMQP) | Apache Kafka | Notre Architecture (FastAPI + BDD) |
| :--- | :--- | :--- | :--- | :--- |
| **Persistance** | Aucune (mémoire vive volatile) | Files temporaires (vidées dès acquittement) | Journal append-only immuable persistant sur disque | Table SQL `messages` indexée et persistée sur disque |
| **Destinataire hors ligne** | **Message irrémédiablement perdu** (fire-and-forget) | Stocké dans la file du destinataire jusqu'à expiration (TTL) | Conservé selon la politique de rétention (ex: 7 jours), sans impact sur le producteur | Conservé indéfiniment en base jusqu'à suppression |
| **Curseur de lecture** | Aucun | Géré par le broker (dépilement) | Géré par le consommateur via l'`offset` | Géré par l'application cliente via l'identifiant / horodatage des messages |
| **Rejeu (Replay)** | Impossible | Impossible | Relecture intégrale possible en réinitialisant l'offset | Relecture totale ou partielle possible via l'API REST |

Dans Apache Kafka, la déconnexion d'un consommateur n'altère en rien la publication des événements : les partitions de topics enregistrent les messages de façon durable dans un journal séquentiel. À sa reconnexion, le consommateur reprend la lecture là où son curseur (`offset`) s'était arrêté.

Dans notre messagerie, la base de données relationnelle remplit exactement ce rôle de **journal de commit durable** : la livraison temps réel (WebSocket) est une optimisation opportuniste de faible latence, tandis que la base de données relationnelle constitue la source de vérité autoritaire et pérenne garantissant une sémantique d'acheminement *at-least-once*.

---

## 3. Difficultés rencontrées et solutions d'ingénierie temps réel

### 3.1. État en mémoire et limitation à un worker Uvicorn
Le `ConnectionManager` stocke les connexions actives dans un dictionnaire Python en mémoire du processus :
```python
self._active_connections: dict[int, WebSocket] = {}
```
- **Problématique :** Si Uvicorn est exécuté avec plusieurs workers (`--workers 4`) ou si le serveur est répliqué derrière un répartiteur de charge, chaque processus possède son propre espace mémoire isolé. Si Alice est connectée sur le Worker 1 et Bob sur le Worker 2, le Worker 1 ne trouvera pas la socket de Bob dans son registre local et considérera Bob comme hors ligne.
- **Solution de passage à l'échelle :** Pour déployer en environnement multi-instances haute disponibilité, il est impératif d'introduire un **bus de messages distribué en mémoire (ex: Redis Pub/Sub)**. Chaque worker souscrit aux canaux des utilisateurs dont il gère des sockets locales. Lorsqu'un message doit être acheminé, il est publié sur le bus Redis et récupéré par le worker détenant la connexion de l'utilisateur concerné.

### 3.2. Concurrence asynchrone et ORM synchrone
FastAPI repose sur le moteur asynchrone `asyncio` (boucle d'événements sur un unique thread principal).
- **Problématique :** Les opérations de session SQLAlchemy 2.0 choisies pour ce projet sont synchrones et bloquantes. Effectuer un `db.commit()` directement dans le corps d'une coroutine WebSocket `async def` bloque l'intégralité de la boucle d'événements, figeant temporairement le traitement des messages de tous les autres utilisateurs connectés.
- **Solution appliquée :** Utilisation de `starlette.concurrency.run_in_threadpool` pour toutes les opérations de base de données exécutées dans le cycle WebSocket. FastAPI déporte l'accès I/O bloquant vers un pool de threads sous-jacent, préservant la fluidité et la réactivité du canal temps réel.

### 3.3. Déconnexions silencieuses et résilience
Sur mobile, une perte de signal 4G/Wi-Fi ou la mise en veille de l'appareil ne transmet pas toujours la trame de fermeture TCP FIN/RST.
- **Gestion mise en place :** Toute tentative d'écriture `ws.send_json()` levant une exception conduit à l'éviction immédiate de l'entrée dans `ConnectionManager.disconnect()`, protégeant le serveur contre les fuites de descripteurs et garantissant l'exactitude de l'indicateur de présence.
- **Accusés d'acheminement à triple état :** Le système distingue formellement `envoye` (message sécurisé en base), `livre` (socket du destinataire récepteur confirmée) et `lu` (affichage dans la fenêtre active de discussion).

---

## 4. Procédure de validation et démonstration

Le bon fonctionnement a été validé par une suite automatisée complète sous `pytest` :
- `test_auth_stubs.py` : Contrôle des tokens JWT HS256, expiration, falsification et rejet systématique par HTTP 401.
- `test_message_model.py` : Intégrité référentielle, indexation composite et prise en charge du fuseau UTC.
- `test_messages.py` : Consultation chronologique de l'historique REST et contrôle 404/401.
- `test_realtime_manager.py` : Cycle de vie du registre de présence en mémoire et gestion des sockets défaillantes.
- `test_ws.py` : Rejet de connexion sans jeton avec code RFC 1008, retransmission instantanée entre deux clients connectés, accusé de lecture et persistance lors de l'envoi hors ligne suivie d'une reconnexion.
