/**
 * Module partagé pour les appels API REST et la communication WebSocket.
 * Utilisé par les interfaces Desktop et Mobile.
 *
 * Spécifications : ROADMAP.md (§1 et §2)
 */

/**
 * Erreur renvoyée par l'API REST, avec le statut HTTP (401, 409, 422, 429…).
 */
export class ApiError extends Error {
    constructor(status, body) {
        // Format d'erreur du serveur : {detail, code, erreurs?}
        const details = (body.erreurs || []).map((e) => `${e.champ} : ${e.message}`);
        super([body.detail || `Erreur HTTP ${status}`, ...details].join(" — "));
        this.status = status;
        this.code = body.code;
    }
}

async function request(apiBaseUrl, path, { method = "GET", token, body } = {}) {
    const headers = { "Accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    const response = await fetch(`${apiBaseUrl.replace(/\/+$/, "")}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
        throw new ApiError(response.status, await response.json().catch(() => ({})));
    }
    return response.json();
}

/** POST /api/comptes : crée un compte. Renvoie {id, username}. */
export function register(apiBaseUrl, username, motDePasse) {
    return request(apiBaseUrl, "/api/comptes", { method: "POST", body: { username, motDePasse } });
}

/** POST /api/auth/login : renvoie {token, tokenType}. */
export function login(apiBaseUrl, username, motDePasse) {
    return request(apiBaseUrl, "/api/auth/login", { method: "POST", body: { username, motDePasse } });
}

/** GET /api/utilisateurs : renvoie [{id, username, connecte}]. */
export function fetchUsers(apiBaseUrl, token) {
    return request(apiBaseUrl, "/api/utilisateurs", { token });
}

/**
 * Récupère l'historique des messages échangés avec un utilisateur via l'API REST.
 *
 * @param {string} apiBaseUrl - URL de base du backend (ex: "http://localhost:8000")
 * @param {string} token - Jeton JWT Bearer
 * @param {number} targetUserId - Identifiant de l'interlocuteur
 * @returns {Promise<Array>} Liste des messages ordonnés par date
 */
export function fetchMessageHistory(apiBaseUrl, token, targetUserId) {
    return request(apiBaseUrl, `/api/messages/${targetUserId}`, { token });
}

/**
 * Client WebSocket encapsulant la gestion de connexion et les échanges en direct.
 *
 * Format conforme à la Section 4 du sujet :
 * - Message : { type: "message", destinataireId: ..., contenu: ... }
 * - Accusé de lecture : { type: "read", expediteurId: ... }
 * - Indicateur de frappe : { type: "typing", destinataireId: ..., isTyping: ... }
 */
export class ChatWebSocketClient {
    constructor() {
        this.ws = null;
        this.callbacks = {};
    }

    /**
     * Établit la connexion WebSocket en transmettant le JWT en query param.
     *
     * @param {string} wsBaseUrl - URL WS du backend (ex: "ws://localhost:8000")
     * @param {string} token - Jeton JWT Bearer
     * @param {object} callbacks - Gestionnaires d'événements ({ onOpen, onClose, onError, onMessage, onAck, onDeliveredAck, onReadAck, onTyping, onServerError })
     */
    connect(wsBaseUrl, token, callbacks = {}) {
        this.callbacks = callbacks;

        const cleanUrl = wsBaseUrl.replace(/\/+$/, "");
        const wsUrl = `${cleanUrl}/ws/messages?token=${encodeURIComponent(token)}`;

        const socket = new WebSocket(wsUrl);
        this.ws = socket;
        // Après disconnect() ou une reconnexion, les événements tardifs de l'ancienne
        // socket sont ignorés
        const isCurrent = () => this.ws === socket;

        socket.onopen = (event) => {
            if (isCurrent() && this.callbacks.onOpen) this.callbacks.onOpen(event);
        };

        socket.onclose = (event) => {
            // Le code 1008 indique un refus d'authentification par le serveur
            if (isCurrent() && this.callbacks.onClose) this.callbacks.onClose(event);
        };

        socket.onerror = (event) => {
            if (isCurrent() && this.callbacks.onError) this.callbacks.onError(event);
        };

        socket.onmessage = (event) => {
            if (!isCurrent()) return;
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case "message":
                        if (this.callbacks.onMessage) this.callbacks.onMessage(data);
                        break;
                    case "ack":
                        if (this.callbacks.onAck) this.callbacks.onAck(data);
                        break;
                    case "delivered_ack":
                        if (this.callbacks.onDeliveredAck) this.callbacks.onDeliveredAck(data);
                        break;
                    case "read_ack":
                        if (this.callbacks.onReadAck) this.callbacks.onReadAck(data);
                        break;
                    case "typing":
                        if (this.callbacks.onTyping) this.callbacks.onTyping(data);
                        break;
                    case "error":
                        if (this.callbacks.onServerError) this.callbacks.onServerError(data);
                        break;
                    default:
                        if (this.callbacks.onUnknown) this.callbacks.onUnknown(data);
                }
            } catch (err) {
                console.error("Impossible de parser le message entrant :", err);
            }
        };
    }

    /**
     * Envoie un message texte à destination d'un utilisateur.
     */
    sendMessage(destinataireId, contenu) {
        if (!this.isConnected()) {
            throw new Error("WebSocket non connecté");
        }
        this.ws.send(JSON.stringify({
            type: "message",
            destinataireId: Number(destinataireId),
            contenu: contenu,
        }));
    }

    /**
     * Notifie le serveur que les messages d'un expéditeur ont été consultés (bonus accusé de lecture).
     */
    sendRead(expediteurId) {
        if (!this.isConnected()) return;
        this.ws.send(JSON.stringify({
            type: "read",
            expediteurId: Number(expediteurId),
        }));
    }

    /**
     * Émet un indicateur de saisie à destination d'un interlocuteur (bonus).
     */
    sendTyping(destinataireId, isTyping) {
        if (!this.isConnected()) return;
        this.ws.send(JSON.stringify({
            type: "typing",
            destinataireId: Number(destinataireId),
            isTyping: Boolean(isTyping),
        }));
    }

    /**
     * Vérifie si le socket est dans l'état OPEN.
     */
    isConnected() {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    /**
     * Clôture proprement la connexion active.
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
