/**
 * Logique d'interface commune aux clients « bureau » et « mobile ».
 *
 * Les deux pages ont les mêmes identifiants d'éléments mais une mise en page différente.
 * Répartition REST / WebSocket (énoncé §3) :
 * - REST : création de compte, connexion, liste des utilisateurs (présence), historique ;
 * - WebSocket : envoi et réception des messages, accusés, indicateur de saisie.
 */

import { ChatWebSocketClient, fetchMessageHistory, fetchUsers, login, register } from "./api.js";

const STATUS_LABEL = { envoye: "✓ envoyé", livre: "✓✓ livré", lu: "✓✓ lu" };
const USERS_REFRESH_MS = 5000;
const RECONNECT_DELAY_MS = 3000;

/**
 * @param {object} hooks - onConversationOpened / onConversationClosed : utilisés par la
 *   page mobile pour basculer entre la liste des contacts et la conversation.
 */
export function initChat({ onConversationOpened = () => {}, onConversationClosed = () => {} } = {}) {
    const $ = (id) => document.getElementById(id);
    const client = new ChatWebSocketClient();
    const state = {
        apiBase: "",
        token: null,
        me: null, // {id, username}
        users: [],
        contactId: null,
        unread: {}, // expediteurId -> nombre de messages non lus
        loggedOut: true,
        usersTimer: null,
        typingTimer: null,
        lastTypingSent: 0,
    };

    // Servie par FastAPI (/clients/...), la page connaît déjà l'adresse du serveur
    $("server").value = location.protocol.startsWith("http") ? location.origin : "http://localhost:8000";

    // ---------- Journal : montre ce qui passe par REST et par WebSocket ----------

    function log(text, isError = false) {
        const li = document.createElement("li");
        li.textContent = `${new Date().toLocaleTimeString()} — ${text}`;
        if (isError) li.className = "error";
        $("log").prepend(li);
    }

    // ---------- Authentification (REST) ----------

    async function authenticate(createAccount) {
        const username = $("username").value.trim();
        const password = $("password").value;
        state.apiBase = $("server").value.trim().replace(/\/+$/, "");
        showAuthMessage("");
        try {
            if (createAccount) {
                await register(state.apiBase, username, password);
                log(`Compte « ${username} » créé (POST /api/comptes → 201)`);
            }
            const { token } = await login(state.apiBase, username, password);
            log("Connexion réussie (POST /api/auth/login → JWT reçu)");
            state.token = token;
            state.me = { username };
            await startSession();
        } catch (err) {
            showAuthMessage(err.message, true);
        }
    }

    function showAuthMessage(text, isError = false) {
        $("authMessage").textContent = text;
        $("authMessage").className = isError ? "error" : "";
    }

    async function startSession() {
        state.loggedOut = false;
        $("authView").hidden = true;
        $("chatView").hidden = false;
        await refreshUsers();
        $("meLabel").textContent = `${state.me.username} (#${state.me.id})`;
        connectWs();
        state.usersTimer = setInterval(refreshUsers, USERS_REFRESH_MS);
    }

    function logout(reason = "") {
        state.loggedOut = true;
        clearInterval(state.usersTimer);
        client.disconnect();
        Object.assign(state, { token: null, me: null, users: [], contactId: null, unread: {} });
        $("messages").replaceChildren();
        $("chatView").hidden = true;
        $("authView").hidden = false;
        $("password").value = "";
        onConversationClosed();
        showAuthMessage(reason, Boolean(reason));
        log("Déconnecté");
    }

    // ---------- Liste des utilisateurs et présence (REST, rafraîchie toutes les 5 s) ----------

    async function refreshUsers() {
        try {
            state.users = await fetchUsers(state.apiBase, state.token);
        } catch (err) {
            if (err.status === 401 && !state.loggedOut) logout("Session expirée : reconnectez-vous.");
            return;
        }
        if (state.loggedOut) return; // réponse arrivée après une déconnexion
        state.me = state.users.find((u) => u.username === state.me.username) ?? state.me;
        renderUsers();
        renderConversationHeader();
    }

    function renderUsers() {
        const others = state.users.filter((u) => u.id !== state.me.id);
        const items = others.map((u) => {
            const li = document.createElement("li");
            const button = document.createElement("button");
            button.className = u.id === state.contactId ? "contact active" : "contact";
            button.onclick = () => openConversation(u.id);

            const dot = document.createElement("span");
            dot.className = u.connecte ? "dot online" : "dot";
            const name = document.createElement("span");
            name.className = "name";
            name.textContent = u.username;
            const presence = document.createElement("small");
            presence.textContent = u.connecte ? "en ligne" : "hors ligne";
            button.append(dot, name, presence);

            if (state.unread[u.id]) {
                const badge = document.createElement("span");
                badge.className = "unread";
                badge.textContent = state.unread[u.id];
                button.append(badge);
            }
            li.append(button);
            return li;
        });
        if (items.length === 0) {
            const li = document.createElement("li");
            li.className = "hint";
            li.textContent = "Aucun autre utilisateur. Créez un 2e compte sur l'autre appareil.";
            items.push(li);
        }
        $("userList").replaceChildren(...items);
    }

    // ---------- Conversation ----------

    function contact() {
        return state.users.find((u) => u.id === state.contactId);
    }

    function renderConversationHeader() {
        const c = contact();
        $("emptyState").hidden = Boolean(c);
        $("conversation").hidden = !c;
        if (!c) return;
        $("contactName").textContent = c.username;
        $("contactPresence").textContent = c.connecte ? "en ligne" : "hors ligne";
        $("contactPresence").className = c.connecte ? "online" : "";
    }

    async function openConversation(userId) {
        state.contactId = userId;
        state.unread[userId] = 0;
        $("messages").replaceChildren();
        $("typing").textContent = "";
        $("composerError").textContent = "";
        renderUsers();
        renderConversationHeader();
        onConversationOpened();
        await loadHistory();
        $("messageInput").focus();
    }

    function closeConversation() {
        state.contactId = null;
        renderUsers();
        renderConversationHeader();
        onConversationClosed();
    }

    async function loadHistory() {
        const contactId = state.contactId;
        try {
            const history = await fetchMessageHistory(state.apiBase, state.token, contactId);
            if (contactId !== state.contactId) return; // l'utilisateur a changé de contact
            $("messages").replaceChildren();
            history.forEach(appendMessage);
            log(`Historique chargé (GET /api/messages/${contactId}) : ${history.length} message(s)`);
            client.sendRead(contactId);
        } catch (err) {
            log(`Erreur historique : ${err.message}`, true);
        }
    }

    function appendMessage(m) {
        const mine = m.expediteurId === state.me.id;
        const li = document.createElement("li");
        li.className = mine ? "msg mine" : "msg theirs";
        li.dataset.id = m.id;

        const text = document.createElement("div");
        text.textContent = m.contenu; // textContent : pas d'injection HTML possible
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = new Date(m.dateEnvoi).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        if (mine) {
            const status = document.createElement("span");
            status.className = "status";
            meta.append(" · ", status);
        }
        li.append(text, meta);
        if (mine) setStatus(li, m.statut);

        $("messages").append(li);
        li.scrollIntoView({ block: "end" });
    }

    function setStatus(li, statut) {
        const status = li.querySelector(".status");
        if (!status || status.dataset.statut === "lu") return; // « lu » est l'état final
        status.textContent = STATUS_LABEL[statut] ?? statut;
        status.dataset.statut = statut;
    }

    function updateStatuses(messageIds, statut) {
        for (const id of messageIds) {
            const li = $("messages").querySelector(`[data-id="${id}"]`);
            if (li) setStatus(li, statut);
        }
    }

    function setComposerEnabled(enabled) {
        $("messageInput").disabled = !enabled;
        $("btnSend").disabled = !enabled;
    }

    // ---------- Canal temps réel (WebSocket) ----------

    function connectWs() {
        setWsStatus("connexion…", "");
        const wsBase = state.apiBase.replace(/^http/, "ws"); // http → ws, https → wss
        client.connect(wsBase, state.token, {
            onOpen: () => {
                setWsStatus("connecté", "online");
                setComposerEnabled(true);
                log("WebSocket ouvert (/ws/messages)");
                refreshUsers();
                if (state.contactId) loadHistory(); // rattrape ce qui a été reçu pendant la coupure
            },
            onClose: (event) => {
                setWsStatus("déconnecté", "");
                setComposerEnabled(false);
                if (state.loggedOut) return;
                if (event.code === 1008) {
                    log("WebSocket refusé (code 1008) : jeton invalide ou expiré", true);
                    logout("Session expirée : reconnectez-vous.");
                    return;
                }
                log(`WebSocket fermé (code ${event.code}), nouvelle tentative dans 3 s`, true);
                setTimeout(() => state.loggedOut || connectWs(), RECONNECT_DELAY_MS);
            },
            onMessage: (m) => {
                log(`Message #${m.id} reçu en direct de #${m.expediteurId} (WebSocket)`);
                if (m.expediteurId === state.contactId) {
                    $("typing").textContent = "";
                    appendMessage(m);
                    client.sendRead(m.expediteurId);
                } else {
                    state.unread[m.expediteurId] = (state.unread[m.expediteurId] ?? 0) + 1;
                }
                refreshUsers(); // l'expéditeur vient d'agir : sa présence a pu changer depuis le dernier rafraîchissement
            },
            onAck: (m) => {
                log(`Accusé serveur : message #${m.id} enregistré, statut « ${m.statut} »`);
                if (m.destinataireId === state.contactId) appendMessage(m);
            },
            onDeliveredAck: (d) => {
                log(`Message(s) ${d.messageIds.join(", ")} livré(s) à #${d.destinataireId}`);
                updateStatuses(d.messageIds, "livre");
            },
            onReadAck: (r) => {
                log(`Message(s) ${r.messageIds.join(", ")} lu(s) par #${r.readerId}`);
                updateStatuses(r.messageIds, "lu");
            },
            onTyping: (t) => {
                if (t.expediteurId !== state.contactId) return;
                clearTimeout(state.typingTimer);
                $("typing").textContent = t.isTyping ? `${contact()?.username} est en train d'écrire…` : "";
                if (t.isTyping) state.typingTimer = setTimeout(() => ($("typing").textContent = ""), 3000);
            },
            onServerError: (e) => {
                const text = e.code === "RATE_LIMITED"
                    ? `Trop de messages : réessayez dans ${e.retryAfter} s (anti-spam)`
                    : typeof e.detail === "string" ? e.detail : "Message refusé par le serveur";
                $("composerError").textContent = text;
                log(`Erreur ${e.code} : ${text}`, true);
            },
        });
    }

    function setWsStatus(text, className) {
        $("wsStatus").textContent = `Temps réel : ${text}`;
        $("wsStatus").className = className;
    }

    function sendMessage(event) {
        event.preventDefault();
        const text = $("messageInput").value.trim();
        if (!text || !state.contactId || !client.isConnected()) return;
        $("composerError").textContent = "";
        client.sendMessage(state.contactId, text);
        client.sendTyping(state.contactId, false);
        state.lastTypingSent = 0;
        $("messageInput").value = "";
    }

    function notifyTyping() {
        // Au plus une trame « typing » par seconde
        const now = Date.now();
        if (state.contactId && client.isConnected() && now - state.lastTypingSent > 1000) {
            client.sendTyping(state.contactId, true);
            state.lastTypingSent = now;
        }
    }

    // ---------- Branchement des événements ----------

    $("authForm").addEventListener("submit", (e) => {
        e.preventDefault();
        authenticate(e.submitter?.id === "btnRegister");
    });
    $("btnLogout").addEventListener("click", () => logout());
    $("btnBack")?.addEventListener("click", closeConversation);
    $("sendForm").addEventListener("submit", sendMessage);
    $("messageInput").addEventListener("input", notifyTyping);
}
