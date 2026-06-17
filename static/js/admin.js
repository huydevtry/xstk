const state = {
    overview: null,
    settings: {
        points_enabled: true,
    },
    users: [],
    matches: [],
    rechargeRequests: [],
    userSearch: "",
    activeTab: "overview",
    toastTimer: null,
};

document.addEventListener("DOMContentLoaded", () => {
    bindTabs();
    bindActions();
    document.getElementById("match-form")?.addEventListener("submit", saveMatch);
    document.getElementById("csv-import-form")?.addEventListener("submit", importMatchesCsv);
    fetchInitialData();
});

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[ch]));
}

function safeImageSrc(value) {
    const src = String(value ?? "").trim();
    if (!src) return "";
    if (src.startsWith("/") || /^https?:\/\//i.test(src)) return escapeHtml(src);
    return "";
}

function safeCssColor(value) {
    const color = String(value ?? "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString("vi-VN");
}

function formatCoins(value) {
    return `${formatNumber(value)}đ`;
}

function formatDateTime(value) {
    if (!value) return "Chưa có dữ liệu";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Không hợp lệ";
    return new Intl.DateTimeFormat("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
    }).format(date);
}

function normalizeMatchStatus(value) {
    const raw = typeof value === "string"
        ? value
        : value && typeof value === "object" && "value" in value
            ? value.value
            : value;
    return String(raw || "").toLowerCase();
}

function renderMiniAvatar({ avatar_url, avatar_color, initials }) {
    const avatarSrc = safeImageSrc(avatar_url);
    if (avatarSrc) {
        return `<img src="${avatarSrc}" alt="" class="h-6 w-6 rounded-full border border-emerald-500/30 object-cover">`;
    }
    return `<span class="inline-flex h-6 w-6 items-center justify-center rounded-full border border-emerald-500/30 text-[10px] font-black text-white" style="background:${safeCssColor(avatar_color)}">${escapeHtml(initials || "??")}</span>`;
}

function bindTabs() {
    document.querySelectorAll("[data-tab-target]").forEach(btn => {
        btn.addEventListener("click", () => setActiveTab(btn.dataset.tabTarget));
    });
}

function setActiveTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll("[data-tab-target]").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.tabTarget === tabName);
    });
    document.querySelectorAll("[data-tab-panel]").forEach(panel => {
        panel.classList.toggle("hidden", panel.dataset.tabPanel !== tabName);
    });
}

function bindActions() {
    document.getElementById("refresh-overview")?.addEventListener("click", refreshAll);
    document.getElementById("quick-refresh-users")?.addEventListener("click", () => fetchUsers(""));
    document.getElementById("refresh-users")?.addEventListener("click", () => fetchUsers(state.userSearch));
    document.getElementById("refresh-recharge")?.addEventListener("click", fetchRechargeRequests);
    document.getElementById("save-settings")?.addEventListener("click", saveSettings);
    document.getElementById("cancel-edit-btn")?.addEventListener("click", resetMatchForm);

    const searchInput = document.getElementById("user-search");
    let debounceTimer = null;
    searchInput?.addEventListener("input", event => {
        state.userSearch = event.target.value.trim();
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => fetchUsers(state.userSearch), 250);
    });
}

async function refreshAll() {
    await Promise.all([
        fetchOverview(),
        fetchSettings(),
        fetchUsers(state.userSearch),
        fetchRechargeRequests(),
        fetchMatches(),
    ]);
}

async function fetchInitialData() {
    await Promise.all([
        fetchMe(),
        refreshAll(),
    ]);
}

async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.detail || `Lỗi ${res.status}`);
    }
    return data;
}

async function fetchMe() {
    try {
        const data = await fetchJson("/api/v1/me");
        document.getElementById("user-info").innerHTML = `
            <div class="flex items-center gap-2">
                ${renderMiniAvatar(data)}
                <div class="min-w-0">
                    <div class="truncate font-semibold text-white">${escapeHtml(data.display_name || data.email.split("@")[0])}</div>
                    <div class="truncate text-[11px] text-slate-400">${escapeHtml(data.email)}</div>
                </div>
            </div>
        `;
    } catch (err) {
        showToast(err.message || "Không thể tải thông tin admin.", "error");
        document.getElementById("user-info").textContent = "Lỗi xác thực";
    }
}

async function fetchOverview() {
    try {
        state.overview = await fetchJson("/api/v1/admin/overview");
        renderOverview();
    } catch (err) {
        showToast(err.message || "Không thể tải tổng quan.", "error");
    }
}

function renderOverview() {
    if (!state.overview) return;
    const metrics = [
        { label: "Tổng user", value: formatNumber(state.overview.total_users), tone: "text-emerald-300" },
        { label: "Tổng điểm", value: formatCoins(state.overview.total_points), tone: "text-amber-300" },
        { label: "Trận đang mở", value: formatNumber(state.overview.upcoming_matches), tone: "text-sky-300" },
        { label: "Lịch sử báo nhà", value: formatNumber(state.overview.total_bets), tone: "text-pink-300" },
    ];

    document.getElementById("overview-metrics").innerHTML = metrics.map(metric => `
        <div class="metric-card rounded-3xl p-5">
            <div class="text-xs uppercase tracking-[0.2em] text-slate-400">${metric.label}</div>
            <div class="mt-4 text-3xl font-black ${metric.tone}">${metric.value}</div>
        </div>
    `).join("");

    renderOverviewUsers();
    renderOverviewFeatures();
}

function renderOverviewUsers() {
    const list = document.getElementById("overview-user-list");
    const items = state.users.slice(0, 5);
    if (!items.length) {
        list.innerHTML = `<div class="rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-4 text-sm text-slate-400">Chưa có người dùng nào.</div>`;
        return;
    }

    list.innerHTML = items.map(user => `
        <div class="rounded-2xl border border-slate-800 bg-slate-950/50 px-4 py-3">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                    <div class="truncate font-semibold text-white">${escapeHtml(user.display_name || user.email.split("@")[0])}</div>
                    <div class="truncate text-xs text-slate-400">${escapeHtml(user.email)}</div>
                </div>
                <div class="text-right">
                    <div class="text-sm font-bold text-amber-300">${formatCoins(user.total_points)}</div>
                    <div class="text-[11px] text-slate-500">${user.bet_count} Lịch sử báo nhà</div>
                </div>
            </div>
        </div>
    `).join("");
}

function renderOverviewFeatures() {
    const container = document.getElementById("overview-features");
    const enabled = Boolean(state.settings.points_enabled);
    container.innerHTML = `
        <div class="rounded-2xl border ${enabled ? "border-emerald-500/30 bg-emerald-500/8" : "border-rose-500/25 bg-rose-500/8"} px-4 py-4">
            <div class="flex items-center justify-between gap-3">
                <div>
                    <div class="font-semibold text-white">Nap / doi diem</div>
                    <div class="mt-1 text-sm text-slate-400">${enabled ? "Dang hien dong thoi block nap diem va doi diem tren profile." : "Dang an dong thoi block nap diem va doi diem tren profile."}</div>
                </div>
                <span class="rounded-full px-3 py-1 text-xs font-semibold ${enabled ? "bg-emerald-500/15 text-emerald-200" : "bg-rose-500/15 text-rose-200"}">
                    ${enabled ? "Dang bat" : "Dang tat"}
                </span>
            </div>
        </div>
    `;
}
function renderFeaturePills() {
    const container = document.getElementById("feature-status");
    const enabled = Boolean(state.settings.points_enabled);
    container.innerHTML = `
        <span class="rounded-full border px-3 py-1 ${enabled ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200" : "border-rose-500/30 bg-rose-500/10 text-rose-200"}">
            Nap / doi diem: ${enabled ? "Bat" : "Tat"}
        </span>
    `;
}
function renderSettings() {
    const list = document.getElementById("settings-list");
    const enabled = Boolean(state.settings.points_enabled);
    list.innerHTML = `
        <div class="rounded-2xl border border-slate-800 bg-slate-950/50 px-4 py-4">
            <div class="flex items-center justify-between gap-4">
                <div>
                    <div class="font-semibold text-white">Bat block nap / doi diem</div>
                    <div class="mt-1 text-sm text-slate-400">Bat/tat dong thoi phan nap diem va doi diem tren trang profile.</div>
                </div>
                <button type="button" class="switch shrink-0" data-setting-key="points_enabled" data-enabled="${enabled}">
                    <span class="switch-track block h-7 w-12 rounded-full bg-slate-700 p-1 transition">
                        <span class="switch-thumb block h-5 w-5 rounded-full bg-white transition"></span>
                    </span>
                </button>
            </div>
        </div>
    `;
    list.querySelectorAll("[data-setting-key]").forEach(btn => {
        btn.addEventListener("click", () => {
            state.settings.points_enabled = !state.settings.points_enabled;
            renderSettings();
            renderFeaturePills();
            renderOverviewFeatures();
        });
    });
}
