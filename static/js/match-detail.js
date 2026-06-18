(() => {
    const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";
    const NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };
    const cache = new Map();

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>\"']/g, ch => ({
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

    function formatCoins(value) {
        return `${Number(value || 0).toLocaleString()}đ`;
    }

    function formatVNDateTime(value) {
        if (!value) return "—";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "—";
        return date.toLocaleString("vi-VN", {
            timeZone: APP_TIME_ZONE,
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function choiceLabel(choice) {
        return { HOME: "Chủ nhà", DRAW: "Hòa", AWAY: "Khách" }[choice] || choice || "Không rõ";
    }

    function renderBettorAvatar(bettor, className = "w-7 h-7") {
        const avatarSrc = safeImageSrc(bettor.avatar_url);
        if (avatarSrc) {
            return `<img src="${avatarSrc}" alt="" class="${className} rounded-full object-cover border border-slate-200 flex-shrink-0">`;
        }
        return `<span class="${className} rounded-full border border-slate-200 flex items-center justify-center text-[11px] font-black text-white flex-shrink-0" style="background:${safeCssColor(bettor.avatar_color)}">${escapeHtml(bettor.initials || "??")}</span>`;
    }

    function summaryTile(label, value, valueClass) {
        return `
            <div class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                <div class="text-[11px] uppercase tracking-wide text-slate-500">${escapeHtml(label)}</div>
                <div class="mt-1 text-sm font-black ${valueClass}">${escapeHtml(value)}</div>
            </div>`;
    }

    function getOutcomeBadgeClass(outcome) {
        return {
            WIN: "border-emerald-200 bg-emerald-50 text-emerald-700",
            LOSE: "border-rose-200 bg-rose-50 text-rose-700",
            REFUND: "border-amber-200 bg-amber-50 text-amber-700",
            PENDING: "border-slate-200 bg-slate-50 text-slate-600",
        }[outcome] || "border-slate-200 bg-slate-50 text-slate-600";
    }

    function choiceBarClass(choice) {
        return {
            HOME: "bg-emerald-500",
            DRAW: "bg-sky-500",
            AWAY: "bg-pink-500",
        }[choice] || "bg-emerald-500";
    }

    function getChoiceState(choiceKey, settlement) {
        if (!settlement?.result_published) {
            return {
                label: "Chờ kết quả",
                badgeClass: "border-slate-200 bg-slate-50 text-slate-600",
            };
        }
        if (settlement.refunded) {
            return {
                label: "Hoàn điểm",
                badgeClass: "border-amber-200 bg-amber-50 text-amber-700",
            };
        }
        if (settlement.winning_choice === choiceKey) {
            return {
                label: "Cửa thắng",
                badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
            };
        }
        return {
            label: "Cửa thua",
            badgeClass: "border-rose-200 bg-rose-50 text-rose-700",
        };
    }

    function renderBettorList(list) {
        if (!list.length) {
            return `<div class="text-xs text-slate-500 italic">Chưa có ai vào cửa này.</div>`;
        }
        return list.map(bettor => {
            const title = escapeHtml(
                bettor.is_lone_wolf
                    ? `${bettor.name} - cú đi ngược đám đông (${formatCoins(bettor.stake)})`
                    : `${bettor.name} (${formatCoins(bettor.stake)})`
            );
            const wolfBadge = bettor.is_lone_wolf
                ? `<span class="ml-auto text-[10px] font-bold text-amber-600">khác biệt</span>`
                : "";
            const outcomeClass = getOutcomeBadgeClass(bettor.outcome);
            const rewardText = escapeHtml(bettor.reward_label || "");
            const quote = bettor.quote ? `<div class="mt-1 text-[11px] leading-snug italic text-slate-500">${escapeHtml(bettor.quote)}</div>` : "";
            return `
                <div class="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" title="${title}">
                    ${renderBettorAvatar(bettor)}
                    <div class="min-w-0 flex-1">
                        <div class="flex min-w-0 items-center gap-2">
                            <div class="truncate text-sm font-semibold text-slate-900">${escapeHtml(bettor.name)}</div>
                            <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${outcomeClass}">${escapeHtml(bettor.outcome_label || "Chờ kết quả")}</span>
                        </div>
                        <div class="text-[11px] text-slate-500">${formatVNDateTime(bettor.created_at)}</div>
                        ${quote}
                    </div>
                    <div class="shrink-0 text-right">
                        <div class="text-sm font-black text-[#D3af37]">${formatCoins(bettor.stake)}</div>
                        <div class="text-[11px] text-[#D3af37]">${rewardText}</div>
                    </div>
                    ${wolfBadge}
                </div>`;
        }).join("");
    }

    function renderChoiceColumn(choiceStat, pct, settlement) {
        const list = choiceStat.bettors || [];
        const state = getChoiceState(choiceStat.key, settlement);
        return `
            <section class="rounded-xl border border-slate-200 bg-white p-4 flex flex-col gap-3 shadow-sm">
                <div class="flex items-center justify-between gap-2">
                    <div>
                        <div class="text-xs uppercase tracking-wide text-slate-500">${escapeHtml(choiceLabel(choiceStat.key))}</div>
                        <div class="text-sm font-semibold text-slate-900">${choiceStat.count} người</div>
                    </div>
                    <div class="text-right">
                        <div class="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${state.badgeClass}">${escapeHtml(state.label)}</div>
                        <div class="text-xs text-slate-500">Tỷ trọng</div>
                        <div class="text-sm font-black text-[#D3af37]">${pct.toFixed(1)}%</div>
                    </div>
                </div>
                <div class="h-2 overflow-hidden rounded-full bg-slate-100">
                    <div class="h-full rounded-full ${choiceBarClass(choiceStat.key)}" style="width:${Math.max(4, pct)}%"></div>
                </div>
                <div class="text-xs text-slate-500">${formatCoins(choiceStat.stake)} trong quỹ</div>
                <div class="max-h-56 space-y-2 overflow-y-auto pr-1">${renderBettorList(list)}</div>
            </section>`;
    }

    function renderMatchDetail(detail) {
        const body = document.getElementById("match-detail-body");
        const titleEl = document.getElementById("match-detail-title");
        const subtitleEl = document.getElementById("match-detail-subtitle");
        const quoteEl = document.getElementById("match-detail-quote");
        if (!body || !titleEl || !subtitleEl || !quoteEl) return;

        const match = detail.match || {};
        const pool = detail.pool || {};
        const settlement = detail.settlement || {};
        const bettors = detail.bettors || {};
        const myBet = detail.my_bet;
        const totalPool = Number(pool.total_pool || 0);
        const resultPublished = Boolean(settlement.result_published);
        const isOddHandicap = (match.handicap ?? 0) % 1 !== 0;
        const choiceStats = [
            { key: "HOME", stake: Number(pool.home_stakes || 0), count: Number(pool.home_count || 0), bettors: bettors.HOME || [] },
            { key: "DRAW", stake: Number(pool.draw_stakes || 0), count: Number(pool.draw_count || 0), bettors: bettors.DRAW || [] },
            { key: "AWAY", stake: Number(pool.away_stakes || 0), count: Number(pool.away_count || 0), bettors: bettors.AWAY || [] },
        ];

        titleEl.textContent = `${match.home_team} vs ${match.away_team}`;
        subtitleEl.textContent = resultPublished
            ? `Kèo chấp ${match.handicap ?? 0} | Tỷ số ${settlement.score || `${match.home_score ?? 0}-${match.away_score ?? 0}`} | Sau kèo ${settlement.adjusted_score || "--"}`
            : settlement.is_finished
            ? `Kèo chấp ${match.handicap ?? 0} | Kết thúc ${formatVNDateTime(match.end_time)} | Chờ kết quả`
            : `Kèo chấp ${match.handicap ?? 0} | Bắt đầu ${formatVNDateTime(match.start_time)} | Kết thúc ${formatVNDateTime(match.end_time)} | Trạng thái ${match.status}`;
        quoteEl.textContent = settlement.headline_quote || "Dữ liệu trận đã sẵn sàng. Hãy xem kỹ bảng chia cửa bên dưới.";

        const homePct = totalPool > 0 ? (choiceStats[0].stake / totalPool) * 100 : 0;
        const drawPct = totalPool > 0 ? (choiceStats[1].stake / totalPool) * 100 : 0;
        const awayPct = totalPool > 0 ? (choiceStats[2].stake / totalPool) * 100 : 0;
        const summaryGridCols = isOddHandicap ? "grid-cols-2 md:grid-cols-3" : "grid-cols-2 md:grid-cols-4";
        const choiceGridCols = isOddHandicap ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1 md:grid-cols-3";

        body.innerHTML = `
            <div class="grid ${summaryGridCols} gap-3">
                ${summaryTile("Tổng quỹ", formatCoins(totalPool), "text-[#D3af37]")}
                ${summaryTile("Chủ nhà", formatCoins(choiceStats[0].stake), "text-[#D3af37]")}
                ${!isOddHandicap ? summaryTile("Hòa", formatCoins(choiceStats[1].stake), "text-[#D3af37]") : ""}
                ${summaryTile("Khách", formatCoins(choiceStats[2].stake), "text-[#D3af37]")}
            </div>

            ${resultPublished ? `
                <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
                    ${summaryTile("Kết quả", settlement.score || `${match.home_score ?? 0}-${match.away_score ?? 0}`, "text-[#D3af37]")}
                    ${summaryTile("Sau kèo", settlement.adjusted_score || "--", "text-[#D3af37]")}
                    ${summaryTile("Người thắng", String(Number(settlement.winner_count || 0)), "text-[#D3af37]")}
                    ${summaryTile(settlement.refunded ? "Hoàn điểm" : "Cửa thắng", settlement.refunded ? String(Number(settlement.refund_count || 0)) : choiceLabel(settlement.winning_choice), "text-[#D3af37]")}
                </div>
            ` : settlement.is_finished ? `
                <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    Trận đã kết thúc và đang chờ công bố kết quả chính thức.
                </div>
            ` : ""}

            <div class="grid ${choiceGridCols} gap-3">
                ${renderChoiceColumn(choiceStats[0], homePct, settlement)}
                ${!isOddHandicap ? renderChoiceColumn(choiceStats[1], drawPct, settlement) : ""}
                ${renderChoiceColumn(choiceStats[2], awayPct, settlement)}
            </div>

            <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="mb-3 flex items-center justify-between gap-3">
                    <div>
                        <div class="text-xs uppercase tracking-wide text-slate-500">Cửa của bạn</div>
                        <div class="text-sm font-semibold text-slate-900">${myBet ? choiceLabel(myBet.choice) : "Chưa vào cửa"}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-xs text-slate-500">điểm đã vào</div>
                        <div class="text-lg font-black text-[#D3af37]">${myBet ? formatCoins(myBet.stake) : "0đ"}</div>
                        ${myBet ? `<div class="text-[11px] text-[#D3af37]">${escapeHtml(myBet.reward_label || myBet.outcome_label || "")}</div>` : ""}
                    </div>
                </div>
                ${myBet ? `<div class="text-xs text-slate-500">${escapeHtml(myBet.quote || "Vào đúng cửa thì uống trà, vào lệch cửa thì ngồi ngẫm đời.")}</div>` : `<div class="text-xs text-slate-500">Chưa đặt cược vẫn xem được quỹ và danh sách để cân nhắc cửa vào.</div>`}
            </div>`;
    }

    async function open(matchId, options = {}) {
        const modal = document.getElementById("match-detail-modal");
        const body = document.getElementById("match-detail-body");
        if (!modal || !body) return;

        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden";
        body.innerHTML = `
            <div class="flex items-center justify-center py-12 text-slate-500">
                <div class="animate-pulse">Đang tải chi tiết trận...</div>
            </div>`;

        try {
            const forceFresh = Boolean(options.forceFresh);
            const cached = forceFresh ? null : cache.get(matchId);
            const response = cached ? null : await fetch(`/api/v1/matches/${matchId}/detail`, NO_CACHE_FETCH_OPTIONS);
            if (response && !response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = cached || await response.json();
            if (!cached) cache.set(matchId, data);
            renderMatchDetail(data);
        } catch (error) {
            console.error(error);
            body.innerHTML = `
                <div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    Không thể tải chi tiết trận lúc này.
                </div>`;
        }
    }

    function close() {
        const modal = document.getElementById("match-detail-modal");
        if (modal) modal.classList.add("hidden");
        document.body.style.overflow = "";
    }

    function bindModalEvents() {
        const modal = document.getElementById("match-detail-modal");
        if (!modal || modal.dataset.bound === "1") return;
        modal.dataset.bound = "1";
        modal.addEventListener("click", event => {
            if (event.target && event.target.id === "match-detail-modal") {
                close();
            }
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") close();
        });
    }

    document.addEventListener("DOMContentLoaded", bindModalEvents);

    window.MatchDetailModal = {
        open,
        close,
        resetCache() {
            cache.clear();
        },
    };
    window.openMatchDetail = function(matchId, forceFresh = false) {
        return open(matchId, { forceFresh });
    };
    window.closeMatchDetail = close;
})();
