(function () {
    if (typeof window === "undefined") return;

    const tauntRotators = new Map();
    const baseFetchUpcomingMatches = fetchUpcomingMatches;

    window.formatCoins = function formatCoinsClean(value) {
        return `${Number(value || 0).toLocaleString()}d`;
    };

    window.choiceLabel = function choiceLabelClean(choice) {
        return { HOME: "Chu nha", DRAW: "Hoa", AWAY: "Khach" }[choice] || choice;
    };

    function tauntRotatorKey(matchId, choice) {
        return `${matchId}:${choice}`;
    }

    function clearTauntRotator(matchId, choice) {
        const key = tauntRotatorKey(matchId, choice);
        const timer = tauntRotators.get(key);
        if (timer) {
            window.clearInterval(timer);
            tauntRotators.delete(key);
        }
    }

    function clearAllTauntRotators() {
        tauntRotators.forEach(timer => window.clearInterval(timer));
        tauntRotators.clear();
    }

    function renderTauntBubble(slot, entry) {
        if (!slot || !entry) return;
        const displayName = escapeHtml(entry.display_name || entry.name || entry.initials || "User");
        const tauntText = escapeHtml(entry.taunt_text || "");
        slot.innerHTML = `
            <div class="taunt-bubble">
                <div class="taunt-name">${displayName}</div>
                <div class="taunt-text">${tauntText}</div>
            </div>
        `;
    }

    function renderTauntSlot(container, bettors) {
        const slotId = container?.id?.replace("avatars-", "taunt-");
        const slot = slotId ? document.getElementById(slotId) : null;
        if (!slot || !container?.id) return;

        const parts = container.id.split("-");
        const choice = (parts[1] || "").toUpperCase();
        const matchId = parts[2];
        clearTauntRotator(matchId, choice);

        const taunts = bettors.filter(entry => String(entry.taunt_text || "").trim());
        if (!taunts.length) {
            slot.innerHTML = "";
            slot.classList.remove("has-taunt");
            return;
        }

        slot.classList.add("has-taunt");
        let index = 0;
        renderTauntBubble(slot, taunts[index]);

        if (taunts.length === 1) return;

        const timer = window.setInterval(() => {
            index = (index + 1) % taunts.length;
            renderTauntBubble(slot, taunts[index]);
        }, 3000);
        tauntRotators.set(tauntRotatorKey(matchId, choice), timer);
    }

    function renderChoiceBlock(matchId, totalPool, status, minStake, choice, label, stakeValue, clickable) {
        const choiceId = choice.toLowerCase();
        const tauntSlot = `<div class="taunt-slot" id="taunt-${choiceId}-${matchId}"></div>`;
        const avatars = `<div class="avatar-stack-row" id="avatars-${choiceId}-${matchId}"></div>`;

        if (clickable) {
            return `
                <div class="bet-choice-block">
                    ${tauntSlot}
                    <button class="bet-btn w-full" id="bet-${choiceId}-${matchId}" onclick="selectChoice(${matchId}, '${choice}', ${totalPool}, ${stakeValue}, '${status}', ${minStake ?? "null"})">
                        <span class="bet-label">${label}</span>
                    </button>
                    ${avatars}
                </div>
            `;
        }

        return `
            <div class="bet-choice-block">
                ${tauntSlot}
                <div class="bet-choice-caption">${label}</div>
                ${avatars}
            </div>
        `;
    }

    window.fetchUpcomingMatches = async function fetchUpcomingMatchesWithTaunt() {
        clearAllTauntRotators();
        return baseFetchUpcomingMatches();
    };

    window.fetchAvatarStack = async function fetchAvatarStackWithTaunt(matchId) {
        try {
            const res = await fetch(`/api/v1/matches/${matchId}/bets`, NO_CACHE_FETCH_OPTIONS);
            if (!res.ok) return;
            const data = await res.json();
            ["HOME", "DRAW", "AWAY"].forEach(choice => {
                const slot = document.getElementById(`avatars-${choice.toLowerCase()}-${matchId}`);
                if (!slot) return;
                renderAvatarStack(slot, data[choice] || []);
            });
        } catch (error) {
            // Non-critical UI.
        }
    };

    window.renderAvatarStack = function renderAvatarStackWithTaunt(container, bettors) {
        renderTauntSlot(container, bettors);

        if (!bettors.length) {
            container.innerHTML = `<span class="text-gray-400 text-xs">-</span>`;
            return;
        }

        const MAX_SHOW = 5;
        const shown = bettors.slice(0, MAX_SHOW);
        const extra = bettors.length - MAX_SHOW;

        let avatarsHtml = shown.map(b => {
            const rawName = String(b.name ?? "");
            const lwClass = b.is_lone_wolf ? " lone-wolf" : "";
            const lwIcon = b.is_lone_wolf ? `<span style="position:absolute;top:-7px;right:-3px;font-size:0.6rem;line-height:1">!</span>` : "";
            const title = escapeHtml(
                b.is_lone_wolf
                    ? `${rawName} - Lone wolf (${formatCoins(b.stake)})`
                    : `${rawName} (${formatCoins(b.stake)})`
            );
            const avatar = renderBettorAvatar(b, "w-full h-full");
            return `<div class="avatar-circle${lwClass}" title="${title}">${lwIcon}${avatar}</div>`;
        }).join("");

        if (extra > 0) {
            avatarsHtml += `<div class="avatar-more">+${extra}</div>`;
        }

        container.innerHTML = `<div class="avatar-stack">${avatarsHtml}</div>`;
    };

    window.renderMatchCard = function renderMatchCardWithTaunt(match) {
        const timeStr = new Date(match.start_time).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
        const { id, home_team, home_icon, away_team, away_icon, handicap, stakes_home, stakes_draw, stakes_away, total_pool } = match;
        const status = String(match.status || "upcoming");
        const isLive = isLiveMatch(match);
        const hasPlaced = placedBets.has(id);
        const canBet = status === "upcoming" && !hasPlaced;
        const endTimeStr = match.end_time ? new Date(match.end_time).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "-";
        const homeTeam = escapeHtml(home_team);
        const awayTeam = escapeHtml(away_team);
        const homeIconSrc = safeImageSrc(home_icon);
        const awayIconSrc = safeImageSrc(away_icon);
        const minStake = match.min_stake;
        const minStakeHint = minStake ? `Toi thieu ${formatCoins(minStake)}` : "Nguoi dau mo pool tu do";

        const hcSign = handicap > 0 ? "+" : "";
        const hcClass = handicap >= 0 ? "handicap-pos" : "handicap-neg";
        const hcBadge = handicap !== 0 ? `<span class="${hcClass}">(${hcSign}${handicap})</span>` : "";

        const choiceGrid = `
            <div class="bet-btn-group" id="btn-group-${id}">
                ${renderChoiceBlock(id, total_pool, status, minStake, "HOME", "Nha", stakes_home, canBet)}
                ${renderChoiceBlock(id, total_pool, status, minStake, "DRAW", "Hoa", stakes_draw, canBet)}
                ${renderChoiceBlock(id, total_pool, status, minStake, "AWAY", "Khach", stakes_away, canBet)}
            </div>
        `;

        const betArea = canBet
            ? `
                ${choiceGrid}
                <div class="mt-2 text-center text-[11px] text-slate-500">${escapeHtml(minStakeHint)}</div>
                <div id="stake-panel-${id}" class="hidden"></div>
            `
            : `
                ${hasPlaced ? `<div class="bet-placed-badge">Da dat cuoc cho tran nay</div>` : ""}
                ${choiceGrid}
                <div id="stake-panel-${id}" class="hidden"></div>
            `;

        const homeIconHtml = homeIconSrc ? `<img src="${homeIconSrc}" class="w-6 h-6 inline-block mr-2 rounded-full border border-slate-200 bg-white">` : "";
        const awayIconHtml = awayIconSrc ? `<img src="${awayIconSrc}" class="w-6 h-6 inline-block ml-2 rounded-full border border-slate-200 bg-white">` : "";
        const liveBadge = isLive ? `
            <span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-bold text-rose-600">
                <span class="live-dot"></span>
                LIVE
            </span>` : "";

        return `
            <div class="bg-white border border-slate-200 hover:border-sky-300 rounded-2xl p-3 sm:p-4 shadow-sm transition duration-200 mb-3 last:mb-0">
                <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2 flex-wrap">
                        ${liveBadge}
                        <span class="text-xs bg-sky-50 text-sky-700 font-mono font-semibold px-2 py-1 rounded-full border border-sky-100">${timeStr}</span>
                        <span class="text-xs bg-rose-50 text-rose-700 font-mono font-semibold px-2 py-1 rounded-full border border-rose-100">KT ${endTimeStr}</span>
                    </div>
                    <button type="button"
                        class="inline-flex items-center gap-1 text-xs bg-white text-slate-600 border border-slate-200 hover:border-sky-300 hover:text-sky-700 px-2.5 py-1 rounded-full transition-colors shadow-sm"
                        onclick="openMatchDetail(${id})"
                        title="Xem chi tiet tran">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M11 16h2M12 8v4m0 8a8 8 0 100-16 8 8 0 000 16z"/>
                        </svg>
                        <span>Chi tiet</span>
                    </button>
                </div>

                <div class="flex items-center justify-between my-3 px-2">
                    <div class="w-2/5 text-center flex flex-col items-center">
                        <div class="flex items-center justify-center mb-1">${homeIconHtml}</div>
                        <p class="text-sm font-bold text-slate-900 truncate w-full">${homeTeam} ${hcBadge}</p>
                        <span class="text-xs text-slate-500 block mt-0.5">Chu nha</span>
                    </div>
                    <div class="w-1/5 text-center text-slate-400 font-black text-sm">VS</div>
                    <div class="w-2/5 text-center flex flex-col items-center">
                        <div class="flex items-center justify-center mb-1">${awayIconHtml}</div>
                        <p class="text-sm font-bold text-slate-900 truncate w-full">${awayTeam}</p>
                        <span class="text-xs text-slate-500 block mt-0.5">Khach</span>
                    </div>
                </div>

                <div class="text-center text-xs text-slate-500 mb-1">
                    Pool: <span class="text-[#D3af37] font-semibold">${formatCoins(total_pool)}</span>
                </div>

                ${betArea}
            </div>
        `;
    };

    window.selectChoice = function selectChoiceWithTaunt(matchId, choice, totalPool, stakesOnChoice, matchStatus = "upcoming", minStake = null) {
        if (String(matchStatus).toLowerCase() !== "upcoming") return;
        matchSelections[matchId] = { choice, totalPool, stakesOnChoice, status: matchStatus, minStake };

        ["HOME", "DRAW", "AWAY"].forEach(currentChoice => {
            const btn = document.getElementById(`bet-${currentChoice.toLowerCase()}-${matchId}`);
            if (btn) btn.classList.toggle("selected", currentChoice === choice);
        });

        renderStakePanel(matchId, choice, totalPool, stakesOnChoice, minStake);
    };

    window.pickStake = function pickStakeWithTaunt(matchId, totalPool, stakesOnChoice, value) {
        syncStake(matchId, totalPool, stakesOnChoice, value);
    };

    window.syncStake = function syncStakeWithTaunt(matchId, totalPool, stakesOnChoice, rawVal) {
        const input = document.getElementById(`input-${matchId}`);
        if (!input) return;
        const selection = matchSelections[matchId] || {};
        const maxStake = currentUser ? Number(currentUser.total_points || 0) : 9999;
        const value = normalizeStakeValue(rawVal, selection.minStake, maxStake);
        input.value = value;

        const estEl = document.getElementById(`est-${matchId}`);
        if (estEl) {
            estEl.innerHTML = `Uoc tinh nhan: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, value))}</strong>`;
        }
    };

    window.updateBetTauntCounter = function updateBetTauntCounter(matchId) {
        const input = document.getElementById(`taunt-${matchId}`);
        const counter = document.getElementById(`taunt-count-${matchId}`);
        if (!input || !counter) return;
        counter.textContent = `${input.value.length}/30`;
        counter.classList.toggle("text-rose-500", input.value.length > 27);
        counter.classList.toggle("text-slate-400", input.value.length <= 27);
    };

    window.renderStakePanel = function renderStakePanelWithTaunt(matchId, choice, totalPool, stakesOnChoice, minStake = null) {
        const panel = document.getElementById(`stake-panel-${matchId}`);
        const selection = matchSelections[matchId] || {};
        const matchStatus = selection.status || "upcoming";
        if (!panel || String(matchStatus).toLowerCase() !== "upcoming") return;

        const maxStake = currentUser ? Number(currentUser.total_points || 0) : 1000;
        const effectiveMin = getEffectiveMinStake(minStake ?? selection.minStake);
        const quickOptions = buildQuickStakeOptions(minStake, maxStake);
        const defaultStake = Math.max(effectiveMin, Math.min(quickOptions[0] || effectiveMin, maxStake));
        const defaultTaunt = String(currentUser?.default_taunt || "");

        panel.classList.remove("hidden");
        if (maxStake < effectiveMin) {
            panel.innerHTML = `
                <div class="stake-panel">
                    <label>So diem dat cuoc</label>
                    <div class="text-sm text-rose-600 mt-2">Tran nay dang yeu cau toi thieu ${formatCoins(effectiveMin)}. Hien tai ban co ${formatCoins(maxStake)}.</div>
                </div>`;
            return;
        }

        const chips = quickOptions.map(value => `
            <button type="button" class="stake-chip" onclick="pickStake(${matchId}, ${totalPool}, ${stakesOnChoice}, ${value})">
                ${formatCoins(value)}
            </button>
        `).join("");

        panel.innerHTML = `
            <div class="stake-panel">
                <label>So diem dat cuoc</label>
                <div class="mt-2 text-xs text-slate-500">
                    ${effectiveMin > 1 ? `Toi thieu hien tai: ${formatCoins(effectiveMin)}.` : "Chua co ai dat, ban duoc mo pool tu do."}
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                    ${chips}
                </div>
                <div class="mt-3">
                    <input type="number" class="stake-input w-full"
                        id="input-${matchId}"
                        min="${effectiveMin}" max="${maxStake}" step="1" value="${defaultStake}"
                        oninput="syncStake(${matchId}, ${totalPool}, ${stakesOnChoice}, this.value)">
                </div>
                <div class="mt-3">
                    <label>Cau gay cho tran nay</label>
                    <textarea
                        id="taunt-${matchId}"
                        class="stake-taunt-input mt-2"
                        rows="2"
                        maxlength="30"
                        placeholder="Them 1 cau gay ngan gon..."
                        oninput="updateBetTauntCounter(${matchId})"
                    >${escapeHtml(defaultTaunt)}</textarea>
                    <div class="mt-1 flex items-center justify-end text-xs text-slate-400">
                        <span id="taunt-count-${matchId}">${defaultTaunt.length}/30</span>
                    </div>
                </div>
                <div class="est-return" id="est-${matchId}">
                    Uoc tinh nhan: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, defaultStake))}</strong>
                </div>
                <button class="confirm-bet-btn" id="confirm-btn-${matchId}" onclick="confirmBet(${matchId})">
                    Xac nhan dat cuoc
                </button>
            </div>
        `;

        window.updateBetTauntCounter(matchId);
    };

    window.confirmBet = async function confirmBetWithTaunt(matchId) {
        const selection = matchSelections[matchId];
        if (!selection || String(selection.status || "upcoming").toLowerCase() !== "upcoming") return;

        const input = document.getElementById(`input-${matchId}`);
        const tauntInput = document.getElementById(`taunt-${matchId}`);
        const effectiveMin = getEffectiveMinStake(selection.minStake);
        const stakeVal = parseInt(input?.value || "0", 10) || 0;
        const tauntText = String(tauntInput?.value || "").trim();

        if (stakeVal < effectiveMin) {
            showToast(`So diem toi thieu la ${formatCoins(effectiveMin)}.`, "error");
            return;
        }
        if (currentUser && stakeVal > currentUser.total_points) {
            showToast("So diem khong du.", "error");
            return;
        }
        if (tauntText.length > 30) {
            showToast("Cau gay toi da 30 ky tu.", "error");
            return;
        }

        const confirmLines = [
            `Xac nhan dat ${formatCoins(stakeVal)} cho cua ${choiceLabel(selection.choice)}?`,
        ];
        if (tauntText) confirmLines.push(`Cau gay: "${tauntText}"`);
        if (!window.confirm(confirmLines.join("\n"))) return;

        const btn = document.getElementById(`confirm-btn-${matchId}`);
        if (!btn) return;
        btn.disabled = true;
        btn.textContent = "Dang xu ly...";

        try {
            const res = await fetch("/api/v1/bets", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    match_id: matchId,
                    choice: selection.choice,
                    stake: stakeVal,
                    taunt_text: tauntText || null,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showToast(data.detail || "Dat cuoc that bai.", "error");
                btn.disabled = false;
                btn.textContent = "Xac nhan dat cuoc";
                return;
            }

            placedBets.add(matchId);
            updateDisplayedPoints(data.remaining_points);
            showToast(`Dat cuoc thanh cong. Con lai ${formatCoins(data.remaining_points)}.`, "success");
            matchDetailCache.delete(matchId);
            try {
                await fetchUpcomingMatches();
                startTicker();
            } catch (refreshError) {
                console.error(refreshError);
            }
        } catch (error) {
            showToast("Loi ket noi. Vui long thu lai.", "error");
            btn.disabled = false;
            btn.textContent = "Xac nhan dat cuoc";
        }
    };
})();
