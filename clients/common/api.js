/**
 * Module partagé pour les appels API REST et la communication WebSocket.
 * Utilisé par les interfaces Desktop et Mobile.
 *
 * Spécifications : ROADMAP.md (§1 et §2)
 */

// TODO: Fonctions d'inscription (POST /api/comptes) et de connexion (POST /api/auth/login) à implémenter par Binôme A.
// TODO: Consultation de la liste des utilisateurs (GET /api/utilisateurs) à implémenter par Binôme A.

/**
 * Récupère l'historique des messages échangés avec un utilisateur via l'API REST.
 *
 * @param {string} apiBaseUrl - URL de base du backend (ex: "http://localhost:8000")
 * @param {string} token - Jeton JWT Bearer
 * @param {number} targetUserId - Identifiant de l'interlocuteur
 * @returns {Promise<Array>} Liste des messages ordonnés par date
 */
export async function fetchMessageHistory(apiBaseUrl, token, targetUserId) {
    const url = `${apiBaseUrl.replace(/\/+$/, "")}/api/messages/${targetUserId}`;
    const response = await fetch(url, {
        method: "GET",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Accept": "application/json",
        },
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Erreur HTTP ${response.status}`);
    }

    return response.json();
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
     * @param {object} callbacks - Gestionnaires d'événements ({ onOpen, onClose, onError, onMessage, onAck, onReadAck, onTyping })
     */
    connect(wsBaseUrl, token, callbacks = {}) {
        this.callbacks = callbacks;

        const cleanUrl = wsBaseUrl.replace(/\/+$/, "");
        const wsUrl = `${cleanUrl}/ws/messages?token=${encodeURIComponent(token)}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = (event) => {
            if (this.callbacks.onOpen) this.callbacks.onOpen(event);
        };

        this.ws.onclose = (event) => {
            // Le code 1008 indique un refus d'authentification par le serveur
            if (this.callbacks.onClose) this.callbacks.onClose(event);
        };

        this.ws.onerror = (event) => {
            if (this.callbacks.onError) this.callbacks.onError(event);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case "message":
                        if (this.callbacks.onMessage) this.callbacks.onMessage(data);
                        break;
                    case "ack":
                        if (this.callbacks.onAck) this.callbacks.onAck(data);
                        break;
                    case "read_ack":
                        if (this.callbacks.onReadAck) this.callbacks.onReadAck(data);
                        break;
                    case "typing":
                        if (this.callbacks.onTyping) this.callbacks.onTyping(data);
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
