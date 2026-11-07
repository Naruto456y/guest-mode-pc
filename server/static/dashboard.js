// Панель управления: периодически запрашивает /api/dashboard_data
// и обновляет статус/процессы/лог, а также отправляет команды по кнопкам.

let streaming = false;
// Белый список, который сейчас редактирует человек на сайте. Держим его
// отдельно от данных, которые присылает агент, чтобы при автообновлении
// раз в 3 секунды не затирать то, что человек ещё не сохранил.
let whitelistDraft = null;

function toast(text, kind) {
    let box = document.getElementById("toasts");
    if (!box) {
        box = document.createElement("div");
        box.id = "toasts";
        document.body.appendChild(box);
    }
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " toast-" + kind : "");
    el.textContent = text;
    box.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

async function sendControl(url, body, formData) {
    try {
        const opts = { method: "POST" };
        if (formData) {
            opts.body = formData;
        } else if (body !== undefined) {
            opts.headers = { "Content-Type": "application/json" };
            opts.body = JSON.stringify(body);
        }
        const resp = await fetch(url, opts);
        if (resp.ok) {
            toast("Команда отправлена ✓", "ok");
        } else {
            // Показываем причину от сервера, а не только код ошибки
            let detail = "";
            try { detail = (await resp.clone().json()).detail || ""; } catch (e) {}
            toast("Ошибка " + resp.status + (detail ? ": " + detail : ""), "bad");
        }
        return resp;
    } catch (e) {
        toast("Не удалось отправить команду: " + e, "bad");
        return null;
    }
}

function sendMessageBox() {
    const text = document.getElementById("message-text").value.trim();
    sendControl("/control/prank/message_box", text ? { text } : {});
    document.getElementById("message-text").value = "";
}

function sendOpenUrl() {
    const url = document.getElementById("open-url-text").value.trim();
    if (!url) {
        toast("Введите адрес ссылки", "bad");
        return;
    }
    sendControl("/control/open_url", { url });
}

// Картинка экрана на открытой вкладке (у каждой вкладки своя)
function screenImg() {
    return document.getElementById(currentTab === "remote" ? "remote-screen" : "screenshot");
}

function toggleStream() {
    streaming = !streaming;
    document.querySelectorAll(".stream-toggle").forEach((btn) => {
        btn.textContent = streaming ? "⏹ Выключить трансляцию" : "▶️ Включить трансляцию";
    });
    sendControl(streaming ? "/control/start_stream" : "/control/stop_stream");
    // Поток держим только в видимой картинке, чтобы не тянуть два потока сразу
    ["screenshot", "remote-screen"].forEach((id) => {
        const img = document.getElementById(id);
        img.src = streaming && img === screenImg() ? "/stream.mjpeg?t=" + Date.now() : "/screenshot.jpg?t=" + Date.now();
    });
}

// ===================== Вкладки =====================
let currentTab = "guest";

function showTab(name) {
    currentTab = name;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.getElementById("tab-guest").hidden = name !== "guest";
    document.getElementById("tab-remote").hidden = name !== "remote";
    if (streaming) {
        // Переносим поток трансляции в картинку открытой вкладки
        document.getElementById(name === "remote" ? "screenshot" : "remote-screen").src = "/screenshot.jpg?t=" + Date.now();
        screenImg().src = "/stream.mjpeg?t=" + Date.now();
    }
    try { localStorage.setItem("tab", name); } catch (e) {}
}

// ===================== Управление ПК =====================
function remote(params) {
    return sendControl("/control/remote", params);
}

function screenClick(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    const mode = document.querySelector("input[name=click-mode]:checked").value;
    remote({ action: "click_at", x, y, button: mode === "right" ? "right" : "left", double: mode === "double" });
}

function moveMouse(dx, dy) {
    const step = parseInt(document.getElementById("move-step").value, 10);
    remote({ action: "move", dx: dx * step, dy: dy * step });
}

function hotkey(combo) {
    remote({ action: "hotkey", combo });
}

async function typeText(withEnter) {
    const input = document.getElementById("type-text");
    if (!input.value) return toast("Введите текст", "bad");
    const resp = await remote({ action: "type", text: input.value });
    if (resp && resp.ok) {
        input.value = "";
        if (withEnter) hotkey("enter");
    }
}

function openApp(name) {
    const input = document.getElementById("app-name");
    name = name || input.value.trim();
    if (!name) return toast("Введите название программы", "bad");
    remote({ action: "open_app", name });
    input.value = "";
}

function search(engine) {
    const query = document.getElementById("search-text").value.trim();
    if (!query) return toast("Введите, что найти", "bad");
    remote({ action: "search", query, engine });
}

async function uploadFile() {
    const input = document.getElementById("upload-file");
    if (!input.files.length) return toast("Выберите файл", "bad");
    const form = new FormData();
    form.append("file", input.files[0]);
    const resp = await sendControl("/control/upload", undefined, form);
    if (resp && resp.ok) input.value = "";
}

function badge(el, text, ok) {
    el.textContent = text;
    el.classList.toggle("badge-ok", ok === true);
    el.classList.toggle("badge-bad", ok === false);
}

function renderWhitelist(processes, allowedFromAgent) {
    if (whitelistDraft === null) {
        // Первая загрузка — берём то, что агент сейчас реально разрешает
        whitelistDraft = new Set((allowedFromAgent || []).map((n) => n.toLowerCase()));
    }

    // Уникальные имена процессов: и те, что сейчас запущены, и те, что
    // уже отмечены в черновике (даже если программа сейчас не открыта)
    const names = new Set(whitelistDraft);
    processes.forEach((p) => names.add(p.name.toLowerCase()));
    const filter = (document.getElementById("whitelist-filter")?.value || "").trim().toLowerCase();

    const container = document.getElementById("whitelist-editor");
    container.innerHTML = "";
    Array.from(names).sort((a, b) => ruName(a).localeCompare(ruName(b), "ru")).forEach((name) => {
        if (filter && !name.includes(filter) && !ruName(name).toLowerCase().includes(filter)) return;
        const label = document.createElement("label");
        label.className = "whitelist-item";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = whitelistDraft.has(name);
        checkbox.onchange = () => {
            if (checkbox.checked) {
                whitelistDraft.add(name);
            } else {
                whitelistDraft.delete(name);
            }
        };
        label.appendChild(checkbox);
        const title = document.createElement("span");
        title.textContent = ruName(name);
        const sub = document.createElement("small");
        sub.className = "exe-name";
        sub.textContent = name;
        label.appendChild(title);
        label.appendChild(sub);
        container.appendChild(label);
    });
}

function addWhitelistInput() {
    const input = document.getElementById("whitelist-add-text");
    const name = input.value.trim().toLowerCase();
    if (!name) return;
    if (whitelistDraft === null) whitelistDraft = new Set();
    whitelistDraft.add(name);
    input.value = "";
    renderWhitelist([], null);
}

let lastProcesses = [];

function allowAllRunning() {
    if (whitelistDraft === null) whitelistDraft = new Set();
    lastProcesses.forEach((p) => whitelistDraft.add(p.name.toLowerCase()));
    renderWhitelist(lastProcesses, null);
    toast("Все запущенные программы отмечены — не забудьте сохранить", "ok");
}

function clearEvents() {
    sendControl("/control/clear_events").then(refresh);
}

function fmtAgo(ts) {
    if (!ts) return "—";
    const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
    return s < 60 ? s + " с назад" : Math.floor(s / 60) + " мин назад";
}

async function saveWhitelist() {
    if (whitelistDraft === null) return;
    await sendControl("/control/whitelist", { processes: Array.from(whitelistDraft) });
}

async function refresh() {
    try {
        const resp = await fetch("/api/dashboard_data");
        if (resp.status === 401) {
            window.location.href = "/login";
            return;
        }
        const data = await resp.json();

        badge(document.getElementById("status-online"), data.online ? "ПК онлайн" : "ПК офлайн", data.online);
        badge(document.getElementById("status-dry-run"), data.dry_run ? "ТЕСТОВЫЙ РЕЖИМ (DRY_RUN)" : "БОЕВОЙ РЕЖИМ", data.dry_run ? true : false);
        badge(document.getElementById("status-mode"), data.mode === "locked" ? "Заблокирован" : "Обычный режим", data.mode !== "locked");
        badge(document.getElementById("status-blocking"), data.blocking_enabled ? "Блокировка приложений: ВКЛ" : "Блокировка приложений: выкл", !data.blocking_enabled);
        lastProcesses = data.processes;
        const lockEl = document.getElementById("status-lock");
        lockEl.hidden = data.lock_remaining == null;
        lockEl.textContent = "⏳ Окно пароля: " + data.lock_remaining + " с до выключения";
        const extra = document.getElementById("status-extra");
        const parts = [];
        if (data.streaming) parts.push("🔴 трансляция");
        (data.pranks_active || []).forEach((x) => parts.push("🎭 " + x));
        extra.hidden = parts.length === 0;
        extra.textContent = parts.join(" · ");
        document.getElementById("status-seen").textContent = "Связь: " + fmtAgo(data.last_seen);
        document.title = (data.online ? "🟢 " : "🔴 ") + "Гостевой режим ПК";
        document.getElementById("status-queue").textContent = "Команд в очереди: " + data.queue_length;

        const procList = document.getElementById("process-list");
        procList.innerHTML = "";
        const groups = new Map();
        data.processes.forEach((p) => {
            const key = p.name.toLowerCase();
            groups.set(key, (groups.get(key) || 0) + 1);
        });
        Array.from(groups.entries())
            .sort((a, b) => ruName(a[0]).localeCompare(ruName(b[0]), "ru"))
            .forEach(([name, count]) => {
                const li = document.createElement("li");
                li.textContent = ruName(name) + (count > 1 ? " ×" + count : "");
                const sub = document.createElement("small");
                sub.className = "exe-name";
                sub.textContent = name;
                li.appendChild(sub);
                procList.appendChild(li);
            });

        renderWhitelist(data.processes, data.allowed_processes);

        const eventList = document.getElementById("event-list");
        eventList.innerHTML = "";
        data.events.forEach((ev) => {
            const li = document.createElement("li");
            li.className = "event-" + ev.level;
            li.textContent = `[${ev.time}] ${ev.message}`;
            eventList.appendChild(li);
        });

        // Пока идёт трансляция, картинку не трогаем — она сама обновляется
        // кадрами из /stream.mjpeg, перезапись src каждые 3 сек её бы рвала
        if (!streaming) {
            const img = screenImg();
            img.src = "/screenshot.jpg?t=" + data.screenshot_at;
            document.getElementById("screenshot-time").textContent = data.screenshot_at
                ? "Обновлено: " + new Date(data.screenshot_at * 1000).toLocaleTimeString()
                : "Скриншотов ещё не было";
        } else {
            document.getElementById("screenshot-time").textContent = "🔴 Идёт живая трансляция";
        }
    } catch (e) {
        console.error("Не удалось обновить панель:", e);
    }
}

try { if (localStorage.getItem("tab") === "remote") showTab("remote"); } catch (e) {}
refresh();
setInterval(refresh, 3000);
