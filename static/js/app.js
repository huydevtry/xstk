// ─── State ───────────────────────────────────────────────────────────────────
let currentUser = null;          // { email, total_points }
let placedBets = new Set();      // match IDs đã cược trong session này

// Bảng màu avatar — hash từ tên để màu ổn định
const AVATAR_COLORS = [
    "#7c3aed","#db2777","#0891b2","#059669","#d97706",
    "#dc2626","#2563eb","#7c3aed","#0d9488","#9333ea",
];

function nameToColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

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

document.addEventListener("DOMContentLoaded", () => {
    fetchUserProfile();
    fetchUpcomingMatches();
    startTicker();
    fetchLeaderboard();
    // Refresh pool odds mỗi 30 giây
    setInterval(fetchUpcomingMatches, 30_000);
    // Refresh ticker mỗi 60 giây
    setInterval(startTicker, 60_000);
});


// ─── 1. User Profile ──────────────────────────────────────────────────────────
async function fetchUserProfile() {
    const el = document.getElementById("user-info");
    try {
        const res = await fetch("/api/v1/me");
        if (!res.ok) throw new Error();
        currentUser = await res.json();
        renderUserInfo();
    } catch {
        el.innerHTML = `<span class="text-red-400 font-medium">Lỗi kết nối Auth</span>`;
    }
}

function renderUserInfo() {
    const el = document.getElementById("user-info");
    if (!currentUser) return;
    const shortEmail = currentUser.email.split("@")[0];
    el.innerHTML = `👤 <span class="font-semibold text-white">${escapeHtml(shortEmail)}</span> | 🪙 <span class="text-yellow-400 font-bold" id="user-points">${currentUser.total_points.toLocaleString()}</span>đ`;
}

function updateDisplayedPoints(newTotal) {
    if (currentUser) currentUser.total_points = newTotal;
    const el = document.getElementById("user-points");
    if (el) el.textContent = newTotal.toLocaleString();
}


// ─── 2. Match List ────────────────────────────────────────────────────────────
async function fetchUpcomingMatches() {
    const listEl = document.getElementById("match-list");
    try {
        const res = await fetch("/api/v1/matches");
        const matches = await res.json();

        if (!matches.length) {
            listEl.innerHTML = `<div class="text-center py-12 text-gray-500 text-sm">Hiện chưa có trận đấu nào sắp diễn ra.</div>`;
            return;
        }

        // Group theo ngày
        const grouped = {};
        matches.forEach(m => {
            const d = new Date(m.start_time);
            const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
            (grouped[key] = grouped[key] || []).push(m);
        });

        const sortedDates = Object.keys(grouped).sort();
        let html = "";

        sortedDates.forEach((dateKey, idx) => {
            const dateMatches = grouped[dateKey];
            const displayDate = dateKey.split("-").reverse().join("/");
            const expanded = idx === 0;

            const matchesHtml = dateMatches.map(m => renderMatchCard(m)).join("");

            html += `
                <div class="mb-4">
                    <button onclick="toggleGroup('${dateKey}')" class="w-full flex justify-between items-center bg-gray-800/80 p-3 rounded-lg border border-gray-700 focus:outline-none mb-2 active:bg-gray-700">
                        <span class="font-bold text-emerald-400 text-sm">📅 Ngày ${displayDate} <span class="text-gray-400 text-xs font-normal">(${dateMatches.length} trận)</span></span>
                        <svg id="icon-${dateKey}" class="w-5 h-5 text-gray-400 transform transition-transform duration-200 ${expanded ? "rotate-180" : ""}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>
                    <div id="content-${dateKey}" class="${expanded ? "" : "hidden"}">
                        ${matchesHtml}
                    </div>
                </div>`;
        });

        listEl.innerHTML = html;

        // Sau khi render xong, fetch avatar stacks cho tất cả trận
        matches.forEach(m => fetchAvatarStack(m.id));

    } catch (e) {
        console.error(e);
        listEl.innerHTML = `<div class="text-center py-8 text-red-400 text-xs">Không thể tải danh sách trận đấu. Vui lòng thử lại sau!</div>`;
    }
}


// ─── 3. Render Match Card ─────────────────────────────────────────────────────
function renderMatchCard(match) {
    const timeStr = new Date(match.start_time).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    const { id, home_team, home_icon, away_team, away_icon, handicap, stakes_home, stakes_draw, stakes_away, total_pool } = match;
    const homeTeam = escapeHtml(home_team);
    const awayTeam = escapeHtml(away_team);
    const homeIconSrc = safeImageSrc(home_icon);
    const awayIconSrc = safeImageSrc(away_icon);

    // Handicap badge
    const hcSign = handicap > 0 ? "+" : "";
    const hcClass = handicap >= 0 ? "handicap-pos" : "handicap-neg";
    const hcBadge = handicap !== 0
        ? `<span class="${hcClass}">(${hcSign}${handicap})</span>`
        : "";

    // Multipliers
    const mHome  = calcMultiplier(total_pool, stakes_home);
    const mDraw  = calcMultiplier(total_pool, stakes_draw);
    const mAway  = calcMultiplier(total_pool, stakes_away);

    const betArea = placedBets.has(id)
        ? `<div class="bet-placed-badge">✅ Đã đặt cược cho trận này</div>`
        : `
            <div class="bet-btn-group" id="btn-group-${id}">
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-home-${id}" onclick="selectChoice(${id}, 'HOME', ${mHome}, ${total_pool}, ${stakes_home})">
                        <span class="bet-label">Nhà</span>
                        <span class="bet-odds" id="odds-home-${id}">x${mHome.toFixed(2)}</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-home-${id}"></div>
                </div>
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-draw-${id}" onclick="selectChoice(${id}, 'DRAW', ${mDraw}, ${total_pool}, ${stakes_draw})">
                        <span class="bet-label">Hòa</span>
                        <span class="bet-odds" id="odds-draw-${id}">x${mDraw.toFixed(2)}</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-draw-${id}"></div>
                </div>
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-away-${id}" onclick="selectChoice(${id}, 'AWAY', ${mAway}, ${total_pool}, ${stakes_away})">
                        <span class="bet-label">Khách</span>
                        <span class="bet-odds" id="odds-away-${id}">x${mAway.toFixed(2)}</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-away-${id}"></div>
                </div>
            </div>
            <div id="stake-panel-${id}" class="hidden"></div>`;

    const homeIconHtml = homeIconSrc ? `<img src="${homeIconSrc}" class="w-6 h-6 inline-block mr-2 rounded-full border border-gray-600 bg-gray-900">` : '';
    const awayIconHtml = awayIconSrc ? `<img src="${awayIconSrc}" class="w-6 h-6 inline-block ml-2 rounded-full border border-gray-600 bg-gray-900">` : '';

    return `
        <div class="bg-gray-800 border border-gray-700 hover:border-emerald-500/50 rounded-xl p-4 shadow-sm transition duration-200 mb-3 last:mb-0">
            <div class="text-center mb-2">
                <span class="text-xs bg-gray-900 text-emerald-400 font-mono font-semibold px-2 py-1 rounded">⏰ ${timeStr}</span>
            </div>

            <div class="flex items-center justify-between my-3 px-2">
                <div class="w-2/5 text-center flex flex-col items-center">
                    <div class="flex items-center justify-center mb-1">${homeIconHtml}</div>
                    <p class="text-sm font-bold text-white truncate w-full">${homeTeam} ${hcBadge}</p>
                    <span class="text-xs text-gray-400 block mt-0.5">Chủ nhà</span>
                </div>
                <div class="w-1/5 text-center text-gray-500 font-black text-sm">VS</div>
                <div class="w-2/5 text-center flex flex-col items-center">
                    <div class="flex items-center justify-center mb-1">${awayIconHtml}</div>
                    <p class="text-sm font-bold text-white truncate w-full">${awayTeam}</p>
                    <span class="text-xs text-gray-400 block mt-0.5">Khách</span>
                </div>
            </div>

            <div class="text-center text-xs text-gray-500 mb-1">
                Pool: <span class="text-yellow-400 font-semibold">${total_pool.toLocaleString()}đ</span>
            </div>

            ${betArea}
        </div>`;
}


// ─── 4. Avatar Stack ──────────────────────────────────────────────────────────
async function fetchAvatarStack(matchId) {
    try {
        const res = await fetch(`/api/v1/matches/${matchId}/bets`);
        if (!res.ok) return;
        const data = await res.json();
        ["HOME", "DRAW", "AWAY"].forEach(choice => {
            const slot = document.getElementById(`avatars-${choice.toLowerCase()}-${matchId}`);
            if (!slot) return;
            renderAvatarStack(slot, data[choice] || []);
        });
    } catch(e) {
        // Silently fail – avatar stack is non-critical
    }
}

function renderAvatarStack(container, bettors) {
    if (!bettors.length) {
        container.innerHTML = `<span class="text-gray-600 text-xs">—</span>`;
        return;
    }

    const MAX_SHOW = 5;
    const shown = bettors.slice(0, MAX_SHOW);
    const extra = bettors.length - MAX_SHOW;

    // Build từ phải sang trái (do flex-direction: row-reverse)
    let avatarsHtml = shown.map(b => {
        const rawName = String(b.name ?? "");
        const bg = nameToColor(rawName);
        const safeInitials = escapeHtml(b.initials || "??");
        const lwClass = b.is_lone_wolf ? " lone-wolf" : "";
        const lwIcon  = b.is_lone_wolf ? `<span style="position:absolute;top:-7px;right:-3px;font-size:0.6rem;line-height:1">👑</span>` : "";
        const title = escapeHtml(
            b.is_lone_wolf
                ? `${rawName} — Kẻ đi ngược đám đông! (${b.stake} đ)`
                : `${rawName} (${b.stake} đ)`
        );
        return `<div class="avatar-circle${lwClass}" style="background:${bg}" title="${title}">${lwIcon}${safeInitials}</div>`;
    }).join("");

    if (extra > 0) {
        avatarsHtml += `<div class="avatar-more">+${extra}</div>`;
    }

    container.innerHTML = `<div class="avatar-stack">${avatarsHtml}</div>`;
}


// ─── 5. Tính multiplier ───────────────────────────────────────────────────────
function calcMultiplier(pool, stakes) {
    if (!stakes || stakes === 0) return pool > 0 ? pool : 2.0;
    return pool / stakes;
}


// ─── 6. Chọn lựa (HOME / DRAW / AWAY) ────────────────────────────────────────
const matchSelections = {};  // { matchId: { choice, multiplier } }

window.selectChoice = function(matchId, choice, multiplier, totalPool, stakesOnChoice) {
    matchSelections[matchId] = { choice, multiplier };

    // Highlight button được chọn
    ["HOME", "DRAW", "AWAY"].forEach(c => {
        const btn = document.getElementById(`bet-${c.toLowerCase()}-${matchId}`);
        if (btn) btn.classList.toggle("selected", c === choice);
    });

    // Render stake panel
    renderStakePanel(matchId, choice, multiplier);
};


// ─── 7. Stake Panel ───────────────────────────────────────────────────────────
function renderStakePanel(matchId, choice, multiplier) {
    const panel = document.getElementById(`stake-panel-${matchId}`);
    const maxStake = currentUser ? currentUser.total_points : 1000;
    const defaultStake = Math.min(50, maxStake);

    panel.classList.remove("hidden");
    panel.innerHTML = `
        <div class="stake-panel">
            <label>Số điểm đặt cược</label>
            <div class="flex items-center gap-3 mt-2">
                <input type="range" class="stake-slider flex-1"
                    id="slider-${matchId}"
                    min="10" max="${maxStake}" step="10" value="${defaultStake}"
                    oninput="syncStake(${matchId}, ${multiplier}, this.value)">
                <input type="number" class="stake-input"
                    id="input-${matchId}"
                    min="10" max="${maxStake}" step="10" value="${defaultStake}"
                    oninput="syncStake(${matchId}, ${multiplier}, this.value)">
            </div>
            <div class="est-return" id="est-${matchId}">
                Ước tính nhận: <strong>${Math.floor(defaultStake * multiplier).toLocaleString()} điểm</strong>
            </div>
            <button class="confirm-bet-btn" id="confirm-btn-${matchId}"
                    onclick="confirmBet(${matchId})">
                🎯 Xác nhận đặt cược
            </button>
        </div>`;
}

window.syncStake = function(matchId, multiplier, rawVal) {
    const val = Math.max(10, Math.min(parseInt(rawVal) || 10, currentUser ? currentUser.total_points : 9999));
    document.getElementById(`slider-${matchId}`).value = val;
    document.getElementById(`input-${matchId}`).value = val;
    const est = Math.floor(val * multiplier);
    document.getElementById(`est-${matchId}`).innerHTML =
        `Ước tính nhận: <strong>${est.toLocaleString()} điểm</strong>`;
};


// ─── 8. Xác nhận cược ────────────────────────────────────────────────────────
window.confirmBet = async function(matchId) {
    const sel = matchSelections[matchId];
    if (!sel) return;

    const stakeVal = parseInt(document.getElementById(`input-${matchId}`).value) || 0;
    if (stakeVal < 10) { showToast("Số điểm tối thiểu là 10.", "error"); return; }
    if (currentUser && stakeVal > currentUser.total_points) {
        showToast("Số điểm không đủ.", "error"); return;
    }

    const btn = document.getElementById(`confirm-btn-${matchId}`);
    btn.disabled = true;
    btn.textContent = "Đang xử lý...";

    try {
        const res = await fetch("/api/v1/bets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ match_id: matchId, choice: sel.choice, stake: stakeVal }),
        });

        const data = await res.json();

        if (!res.ok) {
            showToast(data.detail || "Đặt cược thất bại.", "error");
            btn.disabled = false;
            btn.textContent = "🎯 Xác nhận đặt cược";
            return;
        }

        // Thành công
        placedBets.add(matchId);
        updateDisplayedPoints(data.remaining_points);
        showToast(`✅ Đặt cược thành công! Còn lại ${data.remaining_points.toLocaleString()} điểm.`, "success");

        // Disable toàn bộ betting area
        const stakePanel = document.getElementById(`stake-panel-${matchId}`);
        const btnGroup = document.getElementById(`btn-group-${matchId}`);
        if (stakePanel) stakePanel.innerHTML = "";
        if (btnGroup) {
            btnGroup.outerHTML = `<div class="bet-placed-badge">✅ Đã đặt cược cho trận này</div>`;
        }

        // Refresh ticker và avatar stacks
        fetchAvatarStack(matchId);
        startTicker();

    } catch (e) {
        showToast("Lỗi kết nối. Vui lòng thử lại.", "error");
        btn.disabled = false;
        btn.textContent = "🎯 Xác nhận đặt cược";
    }
};


// ─── 9. Toggle Accordion ─────────────────────────────────────────────────────
window.toggleGroup = function(dateKey) {
    const content = document.getElementById(`content-${dateKey}`);
    const icon = document.getElementById(`icon-${dateKey}`);
    content.classList.toggle("hidden");
    icon.classList.toggle("rotate-180");
};


// ─── 10. Live Ticker ──────────────────────────────────────────────────────────
async function startTicker() {
    const wrap = document.getElementById("ticker-content");
    if (!wrap) return;
    try {
        const res = await fetch("/api/v1/activity-feed");
        if (!res.ok) return;
        const activities = await res.json();
        if (!activities.length) return;

        const text = activities
            .map(a => `<span>${escapeHtml(a.text)}</span>`)
            .join(`<span class="ticker-sep">•</span>`);

        // Duplicate để loop mượt
        wrap.innerHTML = text + `<span class="ticker-sep">•••</span>` + text;

        // Reset animation
        wrap.style.animation = "none";
        wrap.offsetHeight; // reflow
        wrap.style.animation = "";
    } catch(e) {
        // Silently fail
    }
}


// ─── 11. Leaderboard (Bảng Phong Thần) ───────────────────────────────────────
async function fetchLeaderboard() {
    const el = document.getElementById("leaderboard-body");
    if (!el) return;
    try {
        const res = await fetch("/api/v1/leaderboard");
        if (!res.ok) return;
        const data = await res.json();
        renderLeaderboard(data, el);
    } catch(e) {
        // Silently fail
    }
}

function renderLeaderboard(data, container) {
    if (!data.length) {
        container.innerHTML = `<div class="text-center py-8 text-gray-500 text-sm">Chưa có dữ liệu xếp hạng.</div>`;
        return;
    }

    const BADGE_COLOR_MAP = {
        gold: "lb-badge-gold",
        purple: "lb-badge-purple",
        red: "lb-badge-red",
        gray: "lb-badge-gray",
    };

    const RANK_MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };

    container.innerHTML = data.map(entry => {
        const rankEl = RANK_MEDALS[entry.rank]
            ? `<span class="lb-rank ${entry.rank === 1 ? "top1" : entry.rank === 2 ? "top2" : "top3"}">${RANK_MEDALS[entry.rank]}</span>`
            : `<span class="lb-rank">${entry.rank}</span>`;

        const badgeHtml = entry.badge
            ? `<span class="lb-badge ${BADGE_COLOR_MAP[entry.badge.color] || ""}">${escapeHtml(entry.badge.emoji)} ${escapeHtml(entry.badge.label)}</span>`
            : "";

        const rawName = String(entry.name ?? "");
        const bg = nameToColor(rawName);
        const initials = escapeHtml(rawName.slice(0, 2).toUpperCase());

        let trendHtml;
        if (entry.trend === "up") {
            trendHtml = `<span class="lb-trend up"><span class="trend-arrow-up">↑</span> +${entry.earned_24h.toLocaleString()}</span>`;
        } else if (entry.trend === "down") {
            trendHtml = `<span class="lb-trend down">↓ Thua ${entry.streak_loss} trận</span>`;
        } else {
            trendHtml = `<span class="lb-trend neutral">— Ổn định</span>`;
        }

        return `
        <div class="lb-row">
            ${rankEl}
            <div class="lb-avatar" style="background:${bg}">${initials}</div>
            <div class="lb-info">
                <div class="lb-name">
                    <span>${escapeHtml(rawName)}</span>
                    ${badgeHtml}
                </div>
            </div>
            <div class="lb-points">
                <span class="lb-score">${entry.total_points.toLocaleString()}</span>
                ${trendHtml}
            </div>
        </div>`;
    }).join("");
}


// ─── 12. Toast Notification ───────────────────────────────────────────────────
function showToast(msg, type = "success") {
    const existing = document.getElementById("toast-container");
    if (existing) existing.remove();

    const color = type === "success" ? "bg-emerald-700 border-emerald-500" : "bg-red-800 border-red-600";
    const toast = document.createElement("div");
    toast.id = "toast-container";
    toast.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-xl border text-sm font-semibold text-white shadow-xl ${color} max-w-xs text-center`;
    toast.style.animation = "slideDown 0.25s ease";
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}
