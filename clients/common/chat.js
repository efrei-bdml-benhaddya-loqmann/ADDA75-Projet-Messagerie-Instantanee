/**
 * Logique d'interface commune aux clients « bureau » et « mobile ».
 *
 * Les deux pages ont les mêmes identifiants d'éléments mais une mise en page différente.
 * Répartition REST / WebSocket (énoncé §3) :
 * - REST : création de compte, connexion, liste des utilisateurs (présence), historique ;
 * - WebSocket : envoi et réception des messages, accusés, indicateur de saisie.
 */

import { ChatWebSocketClient, fetchMessageHistory, fetchUsers, login, register } from "./api.js";

// Libellés d'iMessage, affichés sous le dernier message envoyé
const STATUS_LABEL = { envoye: "Envoyé", livre: "Distribué", lu: "Lu" };
const STATUS_RANK = { envoye: 0, livre: 1, lu: 2 };
// Comme iMessage : un nouvel horodatage centré après une heure sans message
const TIME_GAP_MS = 60 * 60 * 1000;
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
        messages: [], // messages de la conversation ouverte, dans l'ordre chronologique
        unread: {}, // expediteurId -> nombre de messages non lus
        loggedOut: true,
        wsConnected: false,
        infoOpen: false, // panneau d'informations sur le contact
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
        $("meLabel").textContent = state.me.username;
        $("meLabel").title = `Identifiant #${state.me.id}`;
        $("meAvatar")?.replaceChildren(initials(state.me.username));
        connectWs();
        state.usersTimer = setInterval(refreshUsers, USERS_REFRESH_MS);
    }

    function logout(reason = "") {
        state.loggedOut = true;
        clearInterval(state.usersTimer);
        client.disconnect();
        Object.assign(state, { token: null, me: null, users: [], contactId: null, messages: [], unread: {} });
        $("messages").replaceChildren();
        setInfoOpen(false);
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

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text; // textContent : pas d'injection HTML possible
        return node;
    }

    /** Initiales affichées dans l'avatar, comme un contact sans photo dans iMessage. */
    function initials(username) {
        const parts = username.split(/[\s._-]+/).filter(Boolean);
        return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join("");
    }

    function presenceText(user) {
        return user.connecte ? "En ligne" : "Hors ligne";
    }

    function renderUsers() {
        const others = state.users.filter((u) => u.id !== state.me.id);
        const items = others.map((u) => {
            const li = document.createElement("li");
            const button = el("button", u.id === state.contactId ? "contact active" : "contact");
            button.onclick = () => openConversation(u.id);

            // Point bleu d'iMessage pour une conversation non lue
            const unread = el("span", state.unread[u.id] ? "unread-dot visible" : "unread-dot");
            if (state.unread[u.id]) unread.title = `${state.unread[u.id]} message(s) non lu(s)`;
            const text = el("span", "row-text");
            text.append(
                el("span", "name", u.username),
                el("span", u.connecte ? "presence online" : "presence", presenceText(u)),
            );
            button.append(unread, el("span", "avatar", initials(u.username)), text, el("span", "chevron", "›"));
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
        $("contactAvatar").textContent = initials(c.username);
        $("contactPresence").textContent = presenceText(c);
        $("contactPresence").className = c.connecte ? "presence online" : "presence";
        renderInfo();
    }

    // ---------- Panneau d'informations sur le contact ----------

    function setInfoOpen(open) {
        state.infoOpen = open;
        $("infoPanel").hidden = !open;
        $("btnContactInfo").setAttribute("aria-expanded", String(open));
        renderInfo();
    }

    function formatDate(date) {
        return date.toLocaleString("fr-FR", {
            weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        });
    }

    /** Groupe de lignes « libellé — valeur », au style des listes groupées d'iOS. */
    function infoGroup(title, rows, footnote) {
        const section = el("section", "info-section");
        if (title) section.append(el("h3", "info-title", title));
        const group = el("div", "form-group");
        for (const [label, value, className] of rows) {
            const row = el("div", "form-row");
            row.append(el("span", "info-label", label), el("span", `info-value ${className ?? ""}`, value));
            group.append(row);
        }
        section.append(group);
        if (footnote) section.append(el("p", "form-footnote", footnote));
        return section;
    }

    /**
     * Uniquement des données réelles : le contact (GET /api/utilisateurs), l'historique chargé
     * (GET /api/messages/{id}, puis complété en direct par le WebSocket) et l'état du canal.
     */
    function renderInfo() {
        const c = contact();
        if (!state.infoOpen || !c) return;
        $("infoAvatar").textContent = initials(c.username);
        $("infoName").textContent = c.username;
        $("infoPresence").textContent = presenceText(c);
        $("infoPresence").className = c.connecte ? "presence online" : "presence";

        const msgs = state.messages;
        const mine = msgs.filter((m) => m.expediteurId === state.me.id);
        const count = (statut) => String(mine.filter((m) => m.statut === statut).length);
        const sections = [
            infoGroup("Conversation", msgs.length === 0 ? [["Messages", "Aucun message"]] : [
                ["Messages échangés", String(msgs.length)],
                ["Envoyés", String(mine.length)],
                ["Reçus", String(msgs.length - mine.length)],
                ["Premier message", formatDate(new Date(msgs[0].dateEnvoi))],
                ["Dernier message", formatDate(new Date(msgs.at(-1).dateEnvoi))],
            ]),
            infoGroup("Vos messages", [
                ["Lus", count("lu")],
                ["Distribués, non lus", count("livre")],
                ["En attente de distribution", count("envoye")],
            ], "« Distribué » : remis à l'appareil du contact. « En attente » : stocké sur le serveur jusqu'à sa reconnexion."),
            infoGroup("Détails techniques", [
                ["Identifiant", `#${c.id}`],
                ["Historique (REST)", `GET /api/messages/${c.id}`, "mono"],
                ["Temps réel", state.wsConnected ? "WebSocket connecté" : "WebSocket déconnecté", state.wsConnected ? "online-text" : ""],
            ], "Les messages transitent par le serveur : ils sont enregistrés en base de données puis retransmis en temps réel par WebSocket. Ils ne sont pas chiffrés de bout en bout."),
        ];
        $("infoBody").replaceChildren(...sections);
    }

    async function openConversation(userId) {
        state.contactId = userId;
        state.unread[userId] = 0;
        state.messages = [];
        renderThread();
        $("typing").hidden = true;
        $("composerError").textContent = "";
        renderUsers();
        renderConversationHeader();
        onConversationOpened();
        await loadHistory();
        $("messageInput").focus();
    }

    function closeConversation() {
        setInfoOpen(false);
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
            state.messages = history;
            renderThread();
            log(`Historique chargé (GET /api/messages/${contactId}) : ${history.length} message(s)`);
            client.sendRead(contactId);
        } catch (err) {
            log(`Erreur historique : ${err.message}`, true);
        }
    }

    function addMessage(m) {
        state.messages.push(m);
        renderThread();
    }

    /** Horodatage centré façon iMessage : « Aujourd'hui 14:21 », « Hier 09:05 », « lun. 7 sept. 12:08 ». */
    function timestampRow(date) {
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        const day = date.toDateString() === now.toDateString() ? "Aujourd'hui"
            : date.toDateString() === yesterday.toDateString() ? "Hier"
            : date.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
        const li = el("li", "timestamp");
        li.append(el("strong", "", day), ` ${date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`);
        return li;
    }

    /**
     * Redessine la conversation : bulles regroupées par expéditeur (la « queue » n'est que sur
     * la dernière bulle d'un groupe), horodatages après une heure de silence, et statut sous le
     * dernier message envoyé uniquement, comme dans iMessage.
     */
    function renderThread() {
        const msgs = state.messages;
        const lastMine = msgs.findLastIndex((m) => m.expediteurId === state.me?.id);
        const items = [];
        msgs.forEach((m, i) => {
            const date = new Date(m.dateEnvoi);
            const prev = msgs[i - 1];
            const next = msgs[i + 1];
            const breakBefore = !prev || date - new Date(prev.dateEnvoi) > TIME_GAP_MS;
            const breakAfter = !next || new Date(next.dateEnvoi) - date > TIME_GAP_MS;
            if (breakBefore) items.push(timestampRow(date));

            const mine = m.expediteurId === state.me.id;
            const first = breakBefore || prev.expediteurId !== m.expediteurId;
            const last = breakAfter || next.expediteurId !== m.expediteurId;
            const bubble = el("li", `msg ${mine ? "mine" : "theirs"}${first ? " first" : ""}${last ? " tail" : ""}`, m.contenu);
            bubble.title = date.toLocaleString("fr-FR");
            items.push(bubble);

            if (i === lastMine) items.push(el("li", "receipt", STATUS_LABEL[m.statut] ?? m.statut));
        });
        $("messages").replaceChildren(...items);
        scrollToBottom();
        renderInfo();
    }

    function scrollToBottom() {
        $("thread").scrollTop = $("thread").scrollHeight;
    }

    function updateStatuses(messageIds, statut) {
        for (const m of state.messages) {
            // Un statut ne recule jamais (« lu » est l'état final)
            if (messageIds.includes(m.id) && STATUS_RANK[statut] > STATUS_RANK[m.statut]) m.statut = statut;
        }
        renderThread();
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
                state.wsConnected = true;
                setWsStatus("connecté", "online");
                setComposerEnabled(true);
                log("WebSocket ouvert (/ws/messages)");
                refreshUsers();
                if (state.contactId) loadHistory(); // rattrape ce qui a été reçu pendant la coupure
            },
            onClose: (event) => {
                state.wsConnected = false;
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
                    $("typing").hidden = true;
                    addMessage(m);
                    client.sendRead(m.expediteurId);
                } else {
                    state.unread[m.expediteurId] = (state.unread[m.expediteurId] ?? 0) + 1;
                }
                refreshUsers(); // l'expéditeur vient d'agir : sa présence a pu changer depuis le dernier rafraîchissement
            },
            onAck: (m) => {
                log(`Accusé serveur : message #${m.id} enregistré, statut « ${m.statut} »`);
                if (m.destinataireId === state.contactId) addMessage(m);
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
                // Bulle « … » animée d'iMessage
                clearTimeout(state.typingTimer);
                $("typing").hidden = !t.isTyping;
                $("typing").title = `${contact()?.username} est en train d'écrire…`;
                if (t.isTyping) {
                    scrollToBottom();
                    state.typingTimer = setTimeout(() => ($("typing").hidden = true), 3000);
                }
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
        $("wsStatus").className = `ws-status ${className}`;
        renderInfo();
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
    $("btnContactInfo").addEventListener("click", () => setInfoOpen(!state.infoOpen));
    $("btnCloseInfo").addEventListener("click", () => setInfoOpen(false));
    $("sendForm").addEventListener("submit", sendMessage);
    $("messageInput").addEventListener("input", notifyTyping);
}
