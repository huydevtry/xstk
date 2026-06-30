(() => {
    const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";
    const NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };
    const state = {
        matches: [],
        filter: "all",
        query: "",
        didOpenDeepLink: false,
    };

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
        const flagMatch = src.match(/flagcdn\.com\/(?:[a-z0-9]+\/)?([a-z0-9-]+)\.(?:png|webp|jpg|jpeg|svg)/i);
        if (flagMatch) return escapeHtml(`https://flagcdn.com/w320/${flagMatch[1].toLowerCase()}.webp`);
        if (src.startsWith("/") || /^https?:\/\//i.test(src)) return escapeHtml(src);
        return "";
    }

    function getVNDateParts(value) {
        if (!value) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return Object.fromEntries(
            new Intl.DateTimeFormat("en-CA", {
                timeZone: APP_TIME_ZONE,
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
                hourCycle: "h23",
            }).formatToParts(date)
                .filter(part => part.type !== "literal")
                .map(part => [part.type, part.value])
        );
    }

    function formatDateTime(value) {
        if (!value) return "Chưa rõ";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "Chưa rõ";
        return date.toLocaleString("vi-VN", {
            timeZone: APP_TIME_ZONE,
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function formatTimeRange(match) {
        const start = getVNDateParts(match.start_time);
        const end = getVNDateParts(match.end_time);
        if (!start) return "Chưa rõ giờ";
        return end ? `${start.hour}:${start.minute} - ${end.hour}:${end.minute}` : `${start.hour}:${start.minute}`;
    }

    function formatDateLabel(value) {
        const parts = getVNDateParts(value);
        if (!parts) return "Chưa rõ ngày";
        return `${parts.day}/${parts.month}/${parts.year}`;
    }

    function statusValue(match) {
        return String(match?.status || "upcoming").toLowerCase();
    }

    function statusLabel(status) {
        return {
            upcoming: "Sắp diễn ra",
            live: "Đang đá",
            finished: "Đã xong",
        }[status] || status;
    }

    function statusBadgeClass(status) {
        return {
            upcoming: "border-sky-200 bg-sky-50 text-sky-700",
            live: "border-rose-200 bg-rose-50 text-rose-700",
            finished: "border-emerald-200 bg-emerald-50 text-emerald-700",
        }[status] || "border-slate-200 bg-slate-50 text-slate-600";
    }

    function teamIcon(icon, name, className = "h-7 w-10") {
        const src = safeImageSrc(icon);
        if (src) {
            return `<img src="${src}" alt="" class="${className} rounded-none border border-slate-200 bg-white object-contain shadow-sm">`;
        }
        return `<span class="${className} inline-flex items-center justify-center rounded-none border border-slate-200 bg-slate-100 text-xs font-black text-slate-500">${escapeHtml(String(name || "?").slice(0, 1).toUpperCase())}</span>`;
    }

    function scoreLabel(match) {
        const status = statusValue(match);
        if (match.result_published) {
            return match.display_score || `${Number(match.home_score ?? 0)}-${Number(match.away_score ?? 0)}`;
        }
        if (status === "finished") return "Chờ kết quả";
        if (status === "live") return `${Number(match.home_score ?? 0)}-${Number(match.away_score ?? 0)}`;
        return "VS";
    }

    function penaltyMeta(match) {
        if (!match.penalty_score) return "";
        return `
            <span class="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700">
                Pen ${escapeHtml(match.penalty_score)}
            </span>`;
    }

    function advancementHtml(match) {
        const advancement = match.advancing_team;
        if (!match.result_published) return "";
        if (!advancement) {
            return `
                <span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
                    Chưa xác định đội đi tiếp
                </span>`;
        }
        const label = advancement.decided_by === "penalties" ? "Đi tiếp sau pen" : "Đi tiếp";
        return `
            <span class="inline-flex max-w-full items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                ${teamIcon(advancement.icon, advancement.team, "h-3.5 w-5")}
                <span class="truncate">${escapeHtml(advancement.team)}</span>
                <span class="text-emerald-500">·</span>
                <span>${label}</span>
            </span>`;
    }

    function sortMatches(matches) {
        const weight = { live: 0, upcoming: 1, finished: 2 };
        return [...matches].sort((a, b) => {
            const aStatus = statusValue(a);
            const bStatus = statusValue(b);
            const statusDiff = (weight[aStatus] ?? 9) - (weight[bStatus] ?? 9);
            if (statusDiff !== 0) return statusDiff;
            const aTime = new Date(a.start_time || 0).getTime();
            const bTime = new Date(b.start_time || 0).getTime();
            if (aStatus === "finished") return bTime - aTime;
            return aTime - bTime;
        });
    }

    function filteredMatches() {
        const query = state.query.trim().toLowerCase();
        return sortMatches(state.matches).filter(match => {
            const status = statusValue(match);
            if (state.filter !== "all" && status !== state.filter) return false;
            if (!query) return true;
            return [match.home_team, match.away_team]
                .map(value => String(value || "").toLowerCase())
                .some(value => value.includes(query));
        });
    }

    function renderCounts() {
        const counts = state.matches.reduce((acc, match) => {
            acc.all += 1;
            const status = statusValue(match);
            if (status in acc) acc[status] += 1;
            return acc;
        }, { all: 0, upcoming: 0, live: 0, finished: 0 });

        Object.entries(counts).forEach(([key, value]) => {
            const el = document.getElementById(`match-count-${key}`);
            if (el) el.textContent = String(value);
        });
    }

    function renderFilters() {
        document.querySelectorAll("[data-match-filter]").forEach(button => {
            const active = button.dataset.matchFilter === state.filter;
            button.className = `match-filter-btn rounded-xl px-3 py-2 text-sm font-semibold transition ${
                active ? "bg-sky-600 text-white shadow-sm" : "text-slate-500 hover:bg-slate-50 hover:text-sky-700"
            }`;
        });
    }

    function compactScoreParts(match) {
        const status = statusValue(match);
        if (match.result_published || status === "live") {
            return {
                home: String(Number(match.home_score ?? 0)),
                away: String(Number(match.away_score ?? 0)),
                separator: "-",
            };
        }
        if (status === "finished") {
            return { home: "?", away: "?", separator: "-" };
        }
        return { home: "", away: "", separator: "VS" };
    }

    function spacedScore(value) {
        return String(value || "").replace(/\s*-\s*/g, " - ");
    }

    function matchRoundLabel(match) {
        return match.round_label
            || match.round
            || match.stage_label
            || match.stage
            || (match.result_published ? "Completed" : formatTimeRange(match));
    }

    function renderScoreboardCard(match) {
        const status = statusValue(match);
        const resultPublished = Boolean(match.result_published);
        const score = compactScoreParts(match);
        const homeWon = resultPublished && match.advancing_team?.side === "HOME";
        const awayWon = resultPublished && match.advancing_team?.side === "AWAY";
        const penaltyLine = match.penalty_score ? `Penalties: ${spacedScore(match.penalty_score)}` : "";
        const roundLabel = matchRoundLabel(match);

        return `
            <article class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm transition hover:border-sky-200 sm:px-6">
                <button type="button" onclick="openMatchDetail(${Number(match.id)}, true)" class="block w-full text-left" title="Xem chi tiết">
                    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusBadgeClass(status)}">${escapeHtml(statusLabel(status))}</span>
                            ${status === "live" ? `<span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-2 py-1 text-[11px] font-bold text-rose-600"><span class="h-2 w-2 rounded-full bg-rose-500 animate-pulse"></span>LIVE</span>` : ""}
                        </div>
                        ${advancementHtml(match)}
                    </div>

                    <div class="grid grid-cols-[minmax(0,1fr)_minmax(104px,auto)_minmax(0,1fr)] items-start gap-3 sm:gap-6">
                        <div class="min-w-0 text-center">
                            <div class="mb-3 flex justify-center">${teamIcon(match.home_icon, match.home_team, "h-12 w-16 sm:h-14 sm:w-20")}</div>
                            <div class="truncate text-base font-semibold ${homeWon ? "text-emerald-700" : "text-slate-950"} sm:text-lg">${escapeHtml(match.home_team || "?")}</div>
                        </div>

                        <div class="text-center">
                            <div class="grid grid-cols-[1fr_auto_1fr] items-center gap-4 text-5xl font-light leading-none text-slate-900 sm:gap-8 sm:text-6xl">
                                <span class="min-w-[1.2ch] text-right">${escapeHtml(score.home)}</span>
                                <span class="text-4xl text-slate-500 sm:text-5xl">${escapeHtml(score.separator)}</span>
                                <span class="min-w-[1.2ch] text-left">${escapeHtml(score.away)}</span>
                            </div>
                            <div class="mt-4 min-h-[3rem] text-sm font-medium leading-6 text-slate-600 sm:text-base">
                                ${penaltyLine ? `<div>${escapeHtml(penaltyLine)}</div>` : ""}
                                <div>${escapeHtml(roundLabel)}</div>
                            </div>
                            <div class="mt-2 text-[11px] font-medium text-slate-400">
                                ${escapeHtml(formatTimeRange(match))} &middot; Kèo ${Number(match.handicap || 0)}
                            </div>
                        </div>

                        <div class="min-w-0 text-center">
                            <div class="mb-3 flex justify-center">${teamIcon(match.away_icon, match.away_team, "h-12 w-16 sm:h-14 sm:w-20")}</div>
                            <div class="truncate text-base font-semibold ${awayWon ? "text-emerald-700" : "text-slate-950"} sm:text-lg">${escapeHtml(match.away_team || "?")}</div>
                        </div>
                    </div>
                </button>
            </article>`;
    }

    function renderMatchCard(match) {
        const status = statusValue(match);
        const resultPublished = Boolean(match.result_published);
        const score = scoreLabel(match);
        const homeWon = resultPublished && match.advancing_team?.side === "HOME";
        const awayWon = resultPublished && match.advancing_team?.side === "AWAY";
        const scoreClass = status === "live"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : resultPublished
                ? "border-slate-200 bg-slate-950 text-white"
                : "border-slate-200 bg-white text-slate-500";

        return `
            <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-sky-200">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div class="min-w-0 flex-1">
                        <div class="mb-3 flex flex-wrap items-center gap-2">
                            <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${statusBadgeClass(status)}">${escapeHtml(statusLabel(status))}</span>
                            ${status === "live" ? `<span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-2 py-1 text-[11px] font-bold text-rose-600"><span class="h-2 w-2 rounded-full bg-rose-500 animate-pulse"></span>LIVE</span>` : ""}
                            ${penaltyMeta(match)}
                            ${advancementHtml(match)}
                        </div>
                        <div class="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3">
                            <div class="min-w-0 text-right">
                                <div class="flex items-center justify-end gap-2">
                                    <span class="truncate text-sm font-black ${homeWon ? "text-emerald-700" : "text-slate-900"}">${escapeHtml(match.home_team || "?")}</span>
                                    ${teamIcon(match.home_icon, match.home_team)}
                                </div>
                                <div class="mt-1 text-[11px] font-medium text-slate-400">Chủ nhà</div>
                            </div>
                            <button type="button" onclick="openMatchDetail(${Number(match.id)}, true)" class="rounded-2xl border px-4 py-2 text-center font-black ${scoreClass} transition hover:border-sky-300" title="Xem chi tiết">
                                <span class="block text-base">${escapeHtml(score)}</span>
                            </button>
                            <div class="min-w-0 text-left">
                                <div class="flex items-center gap-2">
                                    ${teamIcon(match.away_icon, match.away_team)}
                                    <span class="truncate text-sm font-black ${awayWon ? "text-emerald-700" : "text-slate-900"}">${escapeHtml(match.away_team || "?")}</span>
                                </div>
                                <div class="mt-1 text-[11px] font-medium text-slate-400">Khách</div>
                            </div>
                        </div>
                    </div>
                    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500 lg:w-64 lg:flex-col lg:items-start lg:justify-center">
                        <div><span class="font-semibold text-slate-700">Giờ:</span> ${escapeHtml(formatTimeRange(match))}</div>
                        <div><span class="font-semibold text-slate-700">Kèo:</span> ${Number(match.handicap || 0)}</div>
                        <div><span class="font-semibold text-slate-700">Bắt đầu:</span> ${escapeHtml(formatDateTime(match.start_time))}</div>
                    </div>
                </div>
            </article>`;
    }

    function groupMatches(matches) {
        return matches.reduce((groups, match) => {
            const parts = getVNDateParts(match.start_time);
            const key = parts ? `${parts.year}-${parts.month}-${parts.day}` : "unknown";
            if (!groups[key]) groups[key] = [];
            groups[key].push(match);
            return groups;
        }, {});
    }

    function renderTimeline() {
        const timeline = document.getElementById("match-timeline");
        const empty = document.getElementById("match-page-empty");
        if (!timeline || !empty) return;

        const matches = filteredMatches();
        empty.classList.toggle("hidden", matches.length > 0);
        if (!matches.length) {
            timeline.innerHTML = "";
            return;
        }

        const groups = groupMatches(matches);
        timeline.innerHTML = Object.entries(groups).map(([, items]) => `
            <section class="space-y-3">
                <div class="sticky top-[4.5rem] z-10 rounded-2xl border border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <div class="text-sm font-black text-slate-900">${escapeHtml(formatDateLabel(items[0]?.start_time))}</div>
                            <div class="text-xs text-slate-400">${items.length} trận</div>
                        </div>
                        <div class="text-xs font-semibold text-slate-500">${escapeHtml(statusLabel(statusValue(items[0])))}</div>
                    </div>
                </div>
                <div class="space-y-3">
                    ${items.map(renderScoreboardCard).join("")}
                </div>
            </section>
        `).join("");
    }

    function renderUpdatedTime() {
        const el = document.getElementById("match-page-updated");
        if (!el) return;
        el.textContent = `Cập nhật ${new Date().toLocaleTimeString("vi-VN", {
            timeZone: APP_TIME_ZONE,
            hour: "2-digit",
            minute: "2-digit",
        })}`;
    }

    function renderPage() {
        renderCounts();
        renderFilters();
        renderTimeline();
        renderUpdatedTime();
    }

    function showError(message) {
        const el = document.getElementById("match-page-error");
        if (!el) return;
        el.textContent = message;
        el.classList.remove("hidden");
    }

    function clearError() {
        const el = document.getElementById("match-page-error");
        if (!el) return;
        el.textContent = "";
        el.classList.add("hidden");
    }

    async function fetchSchedule() {
        clearError();
        try {
            const res = await fetch("/api/v1/matches/schedule", NO_CACHE_FETCH_OPTIONS);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            state.matches = Array.isArray(data) ? data : [];
            renderPage();
            openDeepLinkedMatch();
        } catch (error) {
            console.error("fetchSchedule error:", error);
            const timeline = document.getElementById("match-timeline");
            if (timeline) timeline.innerHTML = "";
            showError("Không thể tải lịch trận đấu lúc này.");
        }
    }

    function openDeepLinkedMatch() {
        if (state.didOpenDeepLink) return;
        const matchParam = new URLSearchParams(window.location.search).get("match");
        const matchId = Number(matchParam);
        if (!Number.isFinite(matchId) || !state.matches.some(match => Number(match.id) === matchId)) return;
        state.didOpenDeepLink = true;
        window.history.replaceState(null, "", window.location.pathname);
        window.setTimeout(() => window.openMatchDetail?.(matchId, true), 150);
    }

    function bindEvents() {
        document.querySelectorAll("[data-match-filter]").forEach(button => {
            button.addEventListener("click", () => {
                state.filter = button.dataset.matchFilter || "all";
                renderPage();
            });
        });

        document.getElementById("match-search")?.addEventListener("input", event => {
            state.query = event.currentTarget.value || "";
            renderTimeline();
        });

        document.getElementById("refresh-match-schedule")?.addEventListener("click", fetchSchedule);
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindEvents();
        renderFilters();
        fetchSchedule();
        window.setInterval(fetchSchedule, 60_000);
    });
})();
