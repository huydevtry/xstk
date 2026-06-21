(function () {
    if (typeof window === "undefined") return;

    const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";
    const tauntRotators = new Map();
    const baseFetchUpcomingMatches = fetchUpcomingMatches;
    const matchCardsById = new Map();
    const betEditSelections = new Map();
    const tauntRotationState = new Map();
    const TAUNT_PAGE_SIZE = 3;
    const TAUNT_ROTATE_MS = 5000;
    const TAUNT_ROTATE_OFFSETS = { HOME: 0, DRAW: 1400, AWAY: 2800 };

    function escapeAttr(value) {
        return escapeHtml(value).replace(/\n/g, "&#10;");
    }

    function pluralGoal(count) {
        return `${count} bàn`;
    }

    function buildHandicapTooltip(homeName, awayName, handicap) {
        const h = Number(handicap) || 0;
        const home = String(homeName || "Chủ nhà");
        const away = String(awayName || "Khách");
        if (h === 0) {
            return [
                "Đồng banh.",
                `${home} thắng: Chủ nhà ăn.`,
                "Hòa: cửa Hòa ăn.",
                `${away} thắng: Khách ăn.`,
            ].join("\n");
        }

        const favorite = h < 0 ? home : away;
        const underdog = h < 0 ? away : home;
        const favoriteChoice = h < 0 ? "Chủ nhà" : "Khách";
        const underdogChoice = h < 0 ? "Khách" : "Chủ nhà";
        const absH = Math.abs(h);
        const whole = Math.floor(absH);
        const fraction = Math.round((absH - whole) * 100);

        if (fraction === 25) {
            const exactLine = whole === 0
                ? `Hòa: ${favoriteChoice} thua 50%, ${underdogChoice} ăn 50%.`
                : `${favorite} thắng cách biệt đúng ${pluralGoal(whole)}: ${favoriteChoice} thua 50%, ${underdogChoice} ăn 50%.`;
            return [
                `${favorite} chấp ${underdog} ${whole ? `${whole}.25` : "0.25"} trái.`,
                `${favorite} thắng cách biệt từ ${pluralGoal(whole + 1)}: ${favoriteChoice} ăn đủ.`,
                exactLine,
                `Còn lại: ${underdogChoice} ăn đủ.`,
            ].join("\n");
        }

        if (fraction === 50) {
            return [
                `${favorite} chấp ${underdog} ${whole ? `${whole}.5` : "0.5"} trái.`,
                `${favorite} thắng cách biệt từ ${pluralGoal(whole + 1)}: ${favoriteChoice} ăn đủ.`,
                `Còn lại: ${underdogChoice} ăn đủ.`,
            ].join("\n");
        }

        if (fraction === 75) {
            return [
                `${favorite} chấp ${underdog} ${whole ? `${whole}.75` : "0.75"} trái.`,
                `${favorite} thắng cách biệt từ ${pluralGoal(whole + 2)}: ${favoriteChoice} ăn đủ.`,
                `${favorite} thắng cách biệt đúng ${pluralGoal(whole + 1)}: ${favoriteChoice} ăn 50%, ${underdogChoice} thua 50%.`,
                `Còn lại: ${underdogChoice} ăn đủ.`,
            ].join("\n");
        }

        return [
            `${favorite} chấp ${underdog} ${absH} trái.`,
            `${favorite} thắng cách biệt trên ${pluralGoal(whole)}: ${favoriteChoice} ăn.`,
            `${favorite} thắng cách biệt đúng ${pluralGoal(whole)}: cửa Hòa ăn.`,
            `${favorite} không đạt mốc trên: ${underdogChoice} ăn.`,
        ].join("\n");
    }

    // Trả về mô tả handicap: dùng từ tiếng Việt thuần cho 0.25/0.5/0.75, còn lại dùng số
    function formatHandicapText(homeName, awayName, handicap) {
        if (!handicap || handicap === 0) {
            return "Đồng banh";
        }
        const absHc = Math.abs(handicap);
        const whole = Math.floor(absHc);
        const fraction = Math.round((absHc - whole) * 100);

        let hcStr;
        if (fraction === 0) {
            hcStr = `${whole} trái`;
        } else if (whole === 0 && fraction === 25) {
            hcStr = "1/4 trái";
        } else if (whole === 0 && fraction === 50) {
            hcStr = "nửa trái";
        } else if (whole === 0 && fraction === 75) {
            hcStr = "3/4 trái";
        } else {
            // Số lẻ phức tạp: dùng số thuần để tránh từ ghép ngô nghê
            hcStr = `${absHc} trái`;
        }

        return handicap < 0
            ? `<strong>${escapeHtml(homeName)}</strong> chấp <strong>${escapeHtml(awayName)}</strong> ${hcStr}`
            : `<strong>${escapeHtml(awayName)}</strong> chấp <strong>${escapeHtml(homeName)}</strong> ${hcStr}`;
    }

    window.formatCoins = function formatCoinsClean(value) {
        return `${Number(value || 0).toLocaleString()}d`;
    };

    window.choiceLabel = function choiceLabelClean(choice) {
        return { HOME: "Chủ nhà", DRAW: "Hòa", AWAY: "Khách" }[choice] || choice;
    };

    function isTwoWayHandicap(handicap) {
        return Number(handicap || 0) % 1 !== 0;
    }

    function allowedChoicesForMatch(match) {
        return isTwoWayHandicap(match?.handicap) ? ["HOME", "AWAY"] : ["HOME", "DRAW", "AWAY"];
    }

    function renderBetEditChoiceButton(matchId, choice, selected) {
        return `
            <button
                type="button"
                class="bet-edit-choice${selected ? " selected" : ""}"
                id="edit-choice-${choice.toLowerCase()}-${matchId}"
                onclick="selectBetEditChoice(${matchId}, '${choice}')"
            >
                ${escapeHtml(choiceLabel(choice))}
            </button>
        `;
    }

    function setChoiceActiveState(matchId, selectedChoice) {
        ["HOME", "DRAW", "AWAY"].forEach(choice => {
            const choiceId = choice.toLowerCase();
            const btn = document.getElementById(`bet-${choiceId}-${matchId}`);
            const caption = btn?.closest(".bet-choice-block")?.querySelector(".bet-choice-caption")
                || document.querySelector(`#avatars-${choiceId}-${matchId}`)?.closest(".bet-choice-block")?.querySelector(".bet-choice-caption");
            if (btn) btn.classList.toggle("selected", choice === selectedChoice);
            if (caption) caption.classList.toggle("selected", choice === selectedChoice);
        });
    }

    function lockPlacedBetButtons(matchId) {
        ["HOME", "DRAW", "AWAY"].forEach(choice => {
            const btn = document.getElementById(`bet-${choice.toLowerCase()}-${matchId}`);
            if (!btn) return;
            btn.disabled = true;
            btn.removeAttribute("onclick");
            btn.classList.add("bet-btn-locked");
        });
    }

    function ensureEditActionButton(matchId) {
        const actions = document.querySelector(`#avatars-home-${matchId}`)?.closest(".bg-white")?.querySelector(".match-card-actions");
        if (!actions || actions.querySelector(".match-card-edit-btn")) return;
        actions.insertAdjacentHTML("afterbegin", `
            <button type="button"
                class="match-card-action-btn match-card-edit-btn"
                onclick="toggleBetEditor(${matchId})"
                title="Sửa cửa đặt và câu gáy">
                Sửa cược
            </button>
        `);
    }

    function closeBetPanel(matchId) {
        const panel = document.getElementById(`stake-panel-${matchId}`);
        if (!panel) return;
        panel.innerHTML = "";
        panel.dataset.mode = "";
        panel.classList.add("hidden");
    }

    function formatVNTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "-";
        return date.toLocaleTimeString("vi-VN", {
            timeZone: APP_TIME_ZONE,
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function tauntRotatorKey(matchId, choice) {
        return `${matchId}:${choice}`;
    }

    function clearTauntRotator(matchId, choice) {
        const key = tauntRotatorKey(matchId, choice);
        const timers = tauntRotators.get(key);
        if (timers) {
            if (timers.timeout) window.clearTimeout(timers.timeout);
            if (timers.interval) window.clearInterval(timers.interval);
            tauntRotators.delete(key);
        }
    }

    function clearAllTauntRotators() {
        tauntRotators.forEach(timers => {
            if (timers.timeout) window.clearTimeout(timers.timeout);
            if (timers.interval) window.clearInterval(timers.interval);
        });
        tauntRotators.clear();
    }

    function visibleMatchIdsWithTaunts() {
        const ids = new Set();
        document.querySelectorAll("[id^='avatars-home-'], [id^='avatars-draw-'], [id^='avatars-away-']").forEach(slot => {
            const matchId = slot.id.split("-")[2];
            if (matchId) ids.add(Number(matchId));
        });
        return [...ids];
    }

    async function refreshVisibleTauntSlots() {
        const matchIds = visibleMatchIdsWithTaunts();
        await Promise.all(matchIds.map(matchId => fetchAvatarStack(matchId)));
    }

    function tauntPageEntries(taunts, startIndex) {
        const count = Math.min(TAUNT_PAGE_SIZE, taunts.length);
        return Array.from({ length: count }, (_, offset) => taunts[(startIndex + offset) % taunts.length]);
    }

    function tauntSignature(taunts) {
        return taunts
            .map(entry => `${entry.id || entry.user_id || entry.name || entry.display_name || entry.initials || ""}:${entry.taunt_text || ""}`)
            .join("|");
    }

    function renderTauntEntry(entry) {
        const displayName = escapeHtml(entry.display_name || entry.name || entry.initials || "User");
        const rawTauntText = String(entry.taunt_text || "");
        const tauntText = escapeHtml(rawTauntText);

        // Avatar mini: ảnh hoặc initials với màu
        const avatarSrc = safeImageSrc(entry.avatar_url);
        const avatarBg = safeCssColor(entry.avatar_color);
        const initials = escapeHtml(entry.initials || displayName.slice(0, 2).toUpperCase() || "?");
        const avatarHtml = avatarSrc
            ? `<img src="${avatarSrc}" alt="" class="taunt-avatar-mini" style="object-fit:cover;">`
            : `<span class="taunt-avatar-mini" style="background:${avatarBg}">${initials}</span>`;

        return `
            <div class="taunt-chat-row" title="${escapeAttr(`${entry.display_name || entry.name || entry.initials || "User"}: ${rawTauntText}`)}">
                ${avatarHtml}
                <div class="taunt-bubble">
                    <div class="taunt-name">${displayName}</div>
                    <div class="taunt-text">${tauntText}</div>
                </div>
            </div>
        `;
    }

    function renderTauntBubble(slot, entries) {
        if (!slot || !entries?.length) return;
        slot.innerHTML = entries.map(renderTauntEntry).join("");
    }

    function renderTauntSlot(container, bettors) {
        const slotId = container?.id?.replace("avatars-", "taunt-");
        const slot = slotId ? document.getElementById(slotId) : null;
        if (!slot || !container?.id) return;

        const parts = container.id.split("-");
        const choice = (parts[1] || "").toUpperCase();
        const matchId = parts[2];
        const key = tauntRotatorKey(matchId, choice);

        const taunts = bettors.filter(entry => String(entry.taunt_text || "").trim());
        if (!taunts.length) {
            slot.innerHTML = "";
            slot.classList.remove("has-taunt");
            clearTauntRotator(matchId, choice);
            tauntRotationState.delete(key);
            return;
        }

        slot.classList.add("has-taunt");
        const signature = tauntSignature(taunts);
        const previousState = tauntRotationState.get(key);
        const hasActiveTimer = tauntRotators.has(key);
        const canKeepTimer = previousState?.signature === signature && hasActiveTimer && slot.innerHTML.trim();
        let index = previousState?.signature === signature
            ? previousState.index % taunts.length
            : 0;
        tauntRotationState.set(key, { index, signature });

        const renderCurrentPage = () => {
            renderTauntBubble(slot, tauntPageEntries(taunts, index));
        };
        renderCurrentPage();

        if (taunts.length <= TAUNT_PAGE_SIZE) {
            clearTauntRotator(matchId, choice);
            return;
        }

        if (canKeepTimer) return;

        clearTauntRotator(matchId, choice);

        const rotatePage = () => {
            index = (index + 1) % taunts.length;
            tauntRotationState.set(key, { index, signature });
            renderCurrentPage();
        };
        const offset = TAUNT_ROTATE_OFFSETS[choice] ?? 0;
        const timeout = window.setTimeout(() => {
            rotatePage();
            const interval = window.setInterval(rotatePage, TAUNT_ROTATE_MS);
            tauntRotators.set(key, { interval });
        }, TAUNT_ROTATE_MS + offset);
        tauntRotators.set(key, { timeout });
    }

    function renderPoolBlock(totalPool, stakesHome, stakesDraw, stakesAway, isOddHandicap) {
        const pool = Number(totalPool) || 0;
        const home = Number(stakesHome) || 0;
        const draw = Number(stakesDraw) || 0;
        const away = Number(stakesAway) || 0;

        if (pool === 0) {
            return `
                <div class="pool-block pool-block-empty">
                    <span class="pool-empty-icon">Pool</span>
                    <span class="pool-empty-text">Chưa có ai góp quỹ, vào trước để mở pool.</span>
                </div>`;
        }

        const homePct = Math.round((home / pool) * 100);
        const drawPct = isOddHandicap ? 0 : Math.round((draw / pool) * 100);
        const awayPct = 100 - homePct - drawPct;

        const barHome  = homePct > 0 ? `<div class="pool-bar-seg pool-bar-home"  style="width:${homePct}%"  title="Nhà ${homePct}%"></div>` : "";
        const barDraw  = (!isOddHandicap && drawPct > 0) ? `<div class="pool-bar-seg pool-bar-draw"  style="width:${drawPct}%"  title="Hòa ${drawPct}%"></div>` : "";
        const barAway  = awayPct > 0 ? `<div class="pool-bar-seg pool-bar-away"  style="width:${awayPct}%" title="Khách ${awayPct}%"></div>` : "";

        const breakdownHome = `
            <div class="pool-side pool-side-home">
                <span class="pool-side-label">NHÀ</span>
                <span class="pool-side-pct">${homePct}%</span>
                <span class="pool-side-amt">${formatCoins(home)}</span>
            </div>`;
        const breakdownDraw = !isOddHandicap ? `
            <div class="pool-side pool-side-draw">
                <span class="pool-side-label">HÒA</span>
                <span class="pool-side-pct">${drawPct}%</span>
                <span class="pool-side-amt">${formatCoins(draw)}</span>
            </div>` : "";
        const breakdownAway = `
            <div class="pool-side pool-side-away">
                <span class="pool-side-label">KHÁCH</span>
                <span class="pool-side-pct">${awayPct}%</span>
                <span class="pool-side-amt">${formatCoins(away)}</span>
            </div>`;

        return `
            <div class="pool-block">
                <div class="pool-total-row">
                    <span class="pool-total-label">tổng quỹ</span>
                    <span class="pool-total-amount">${formatCoins(pool)}</span>
                </div>
                <div class="pool-bar">${barHome}${barDraw}${barAway}</div>
                <div class="pool-breakdown${isOddHandicap ? " pool-breakdown-2col" : ""}">
                    ${breakdownHome}${breakdownDraw}${breakdownAway}
                </div>
            </div>`;
    }

    function renderChoiceBlock(matchId, totalPool, status, minStake, choice, label, stakeValue, clickable, selectedChoice = null) {
        const choiceId = choice.toLowerCase();
        const avatars = `<div class="avatar-stack-row" id="avatars-${choiceId}-${matchId}"></div>`;
        const tauntSlot = `<div class="taunt-slot taunt-slot-compact" id="taunt-${choiceId}-${matchId}"></div>`;
        const choiceAmount = `<span class="bet-choice-amount">${formatCoins(stakeValue)}</span>`;
        const isSelected = selectedChoice === choice;

        if (clickable) {
            return `
                <div class="bet-choice-block">
                    <button class="bet-btn w-full${isSelected ? " selected" : ""}" id="bet-${choiceId}-${matchId}" onclick="selectChoice(${matchId}, '${choice}', ${totalPool}, ${stakeValue}, '${status}', ${minStake ?? "null"})">
                        <span class="bet-label">${label}</span>
                        ${choiceAmount}
                    </button>
                    ${avatars}
                    ${tauntSlot}
                </div>
            `;
        }

        return `
            <div class="bet-choice-block">
                <div class="bet-choice-caption${isSelected ? " selected" : ""}">
                    <span>${label}</span>
                    ${choiceAmount}
                </div>
                ${avatars}
                ${tauntSlot}
            </div>
        `;
    }

    window.fetchUpcomingMatches = async function fetchUpcomingMatchesWithTaunt() {
        if (visibleMatchIdsWithTaunts().length) {
            await refreshVisibleTauntSlots();
            return;
        }
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
        const timeStr = formatVNTime(match.start_time);
        const { id, home_team, home_icon, away_team, away_icon, handicap, stakes_home, stakes_draw, stakes_away, total_pool } = match;
        matchCardsById.set(Number(id), match);
        const status = String(match.status || "upcoming");
        const isLive = isLiveMatch(match);
        const hasPlaced = placedBets.has(id);
        const myBet = myBetsByMatchId.get(Number(id)) || null;
        const canBet = status === "upcoming" && !hasPlaced;
        const canEditBet = status === "upcoming" && hasPlaced && Boolean(myBet);
        const selectedChoice = hasPlaced && myBet ? myBet.choice : null;
        const endTimeStr = match.end_time ? formatVNTime(match.end_time) : "-";
        const homeTeam = escapeHtml(home_team);
        const awayTeam = escapeHtml(away_team);
        const homeIconSrc = safeImageSrc(home_icon);
        const awayIconSrc = safeImageSrc(away_icon);
        const minStake = match.min_stake;
        const minStakeHint = minStake ? `Tối thiểu ${formatCoins(minStake)}` : "Người đầu mở pool tự do";
        // Kèo chấp lẻ (0.5, 1.5, ...) không có kết quả hòa
        const isOddHandicap = isTwoWayHandicap(handicap);

        const choiceGrid = `
            <div class="bet-btn-group" id="btn-group-${id}">
                ${renderChoiceBlock(id, total_pool, status, minStake, "HOME", "Nhà", stakes_home, canBet, selectedChoice)}
                ${!isOddHandicap ? renderChoiceBlock(id, total_pool, status, minStake, "DRAW", "Hòa", stakes_draw, canBet, selectedChoice) : ""}
                ${renderChoiceBlock(id, total_pool, status, minStake, "AWAY", "Khách", stakes_away, canBet, selectedChoice)}
            </div>
        `;

        const betArea = canBet
            ? `
                ${choiceGrid}
                <div class="mt-2 text-center text-[11px] text-slate-500">${escapeHtml(minStakeHint)}</div>
                <div id="stake-panel-${id}" class="hidden"></div>
            `
            : hasPlaced && myBet
            ? `
                ${choiceGrid}
                <div id="stake-panel-${id}" class="hidden"></div>
            `
            : `
                ${choiceGrid}
                <div id="stake-panel-${id}" class="hidden"></div>
            `;

        const homeIconHtml = homeIconSrc ? `<img src="${homeIconSrc}" class="w-5 h-5 inline-block rounded-full border border-slate-200 bg-white">` : "";
        const awayIconHtml = awayIconSrc ? `<img src="${awayIconSrc}" class="w-5 h-5 inline-block rounded-full border border-slate-200 bg-white">` : "";
        const liveBadge = isLive ? `
            <span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-bold text-rose-600">
                <span class="live-dot"></span>
                LIVE
            </span>` : "";

        const handicapText = formatHandicapText(home_team, away_team, handicap);
        const handicapTooltip = buildHandicapTooltip(home_team, away_team, handicap);

        return `
            <div class="bg-white border border-slate-200 hover:border-sky-300 rounded-2xl p-3 sm:p-4 shadow-sm transition duration-200 mb-3 last:mb-0">
                <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2 flex-wrap">
                        ${liveBadge}
                        <span class="match-time-block">⏰ ${timeStr} <span class="match-time-sep">→</span> ${endTimeStr}</span>
                    </div>
                    <div class="match-card-actions">
                        ${canEditBet ? `
                            <button type="button"
                                class="match-card-action-btn match-card-edit-btn"
                                onclick="toggleBetEditor(${id})"
                                title="Sửa cửa đặt và câu gáy">
                                Sửa cược
                            </button>
                        ` : ""}
                        <button type="button"
                            class="match-card-action-btn"
                            onclick="openMatchDetail(${id})"
                            title="Xem chi tiết trận">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M11 16h2M12 8v4m0 8a8 8 0 100-16 8 8 0 000 16z"/>
                            </svg>
                            <span>Chi tiết</span>
                        </button>
                    </div>
                </div>

                <div class="flex items-center justify-between my-2 px-1">
                    <div class="w-2/5 text-center flex flex-col items-center">
                        <div class="flex items-center justify-center mb-1">${homeIconHtml}</div>
                        <p class="text-[13px] font-bold text-slate-900 truncate w-full">${homeTeam}</p>
                        <span class="text-[10px] text-slate-500 block mt-0.5">Chủ nhà</span>
                    </div>
                    <div class="w-1/5 text-center text-slate-400 font-black text-xs">VS</div>
                    <div class="w-2/5 text-center flex flex-col items-center">
                        <div class="flex items-center justify-center mb-1">${awayIconHtml}</div>
                        <p class="text-[13px] font-bold text-slate-900 truncate w-full">${awayTeam}</p>
                        <span class="text-[10px] text-slate-500 block mt-0.5">Khách</span>
                    </div>
                </div>

                <div class="match-handicap-info" tabindex="0" data-tooltip="${escapeAttr(handicapTooltip)}">
                    <span class="match-handicap-icon">i</span>
                    <span>${handicapText}</span>
                </div>

                ${renderPoolBlock(total_pool, stakes_home, stakes_draw, stakes_away, isOddHandicap)}

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
            estEl.innerHTML = `Ước tính nhận: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, value))}</strong>`;
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

    window.closeBetEditor = function closeBetEditor(matchId) {
        closeBetPanel(matchId);
    };

    window.closeBetTauntEditor = window.closeBetEditor;

    window.selectBetEditChoice = function selectBetEditChoice(matchId, choice) {
        const match = matchCardsById.get(Number(matchId)) || {};
        if (!allowedChoicesForMatch(match).includes(choice)) return;
        betEditSelections.set(Number(matchId), choice);

        ["HOME", "DRAW", "AWAY"].forEach(currentChoice => {
            const btn = document.getElementById(`edit-choice-${currentChoice.toLowerCase()}-${matchId}`);
            if (btn) btn.classList.toggle("selected", currentChoice === choice);
        });
    };

    window.renderBetEditor = function renderBetEditor(matchId, bet) {
        const panel = document.getElementById(`stake-panel-${matchId}`);
        if (!panel || !bet) return;
        const match = matchCardsById.get(Number(matchId)) || {};
        const tauntText = String(bet.taunt_text || "");
        const selectedChoice = betEditSelections.get(Number(matchId)) || bet.choice;
        const choiceButtons = allowedChoicesForMatch(match)
            .map(choice => renderBetEditChoiceButton(matchId, choice, choice === selectedChoice))
            .join("");

        betEditSelections.set(Number(matchId), selectedChoice);
        panel.dataset.mode = "edit-bet";
        panel.classList.remove("hidden");
        panel.innerHTML = `
            <div class="stake-panel bet-edit-panel">
                <div class="bet-editor-head">
                    <div>
                        <label>Sửa cược</label>
                        <div class="bet-editor-meta">Stake giữ nguyên ${formatCoins(bet.stake)}</div>
                    </div>
                    <button
                        type="button"
                        class="bet-editor-close"
                        onclick="closeBetEditor(${matchId})"
                    >
                        Ẩn
                    </button>
                </div>
                <div class="bet-edit-choice-grid">${choiceButtons}</div>
                <div class="mt-2">
                    <textarea
                        id="taunt-${matchId}"
                        class="stake-taunt-input stake-taunt-input-compact"
                        rows="1"
                        maxlength="30"
                        placeholder="Thêm 1 câu gáy ngắn gọn..."
                        oninput="updateBetTauntCounter(${matchId})"
                    >${escapeHtml(tauntText)}</textarea>
                    <div class="mt-1 flex items-center justify-end text-xs text-slate-400">
                        <span id="taunt-count-${matchId}">${tauntText.length}/30</span>
                    </div>
                </div>
                <button class="confirm-bet-btn bet-edit-save-btn" id="save-bet-btn-${matchId}" onclick="saveBetEdit(${matchId})">
                    Lưu thay đổi
                </button>
            </div>
        `;
        window.updateBetTauntCounter(matchId);
    };

    window.renderBetTauntEditor = window.renderBetEditor;

    window.toggleBetEditor = async function toggleBetEditor(matchId) {
        const panel = document.getElementById(`stake-panel-${matchId}`);
        if (!panel) return;
        if (panel.dataset.mode === "edit-bet" && !panel.classList.contains("hidden")) {
            closeBetEditor(matchId);
            return;
        }

        let bet = myBetsByMatchId.get(Number(matchId)) || null;
        if (!bet) {
            await fetchMyBetState();
            bet = myBetsByMatchId.get(Number(matchId)) || null;
        }
        if (!bet) {
            showToast("Không tìm thấy lệnh cược của bạn.", "error");
            return;
        }
        renderBetEditor(matchId, bet);
    };

    window.toggleBetTauntEditor = window.toggleBetEditor;

    window.saveBetEdit = async function saveBetEdit(matchId) {
        const input = document.getElementById(`taunt-${matchId}`);
        const btn = document.getElementById(`save-bet-btn-${matchId}`);
        const existingBet = myBetsByMatchId.get(Number(matchId)) || null;
        if (!input || !btn || !existingBet) return;

        const match = matchCardsById.get(Number(matchId)) || {};
        const selectedChoice = betEditSelections.get(Number(matchId)) || existingBet.choice;
        if (!allowedChoicesForMatch(match).includes(selectedChoice)) {
            showToast("Cửa cược không hợp lệ cho kèo này.", "error");
            return;
        }

        const tauntText = String(input.value || "").trim();
        if (tauntText.length > 30) {
            showToast("Câu gáy tối đa 30 ký tự.", "error");
            return;
        }

        btn.disabled = true;
        btn.textContent = "Đang lưu...";

        try {
            const res = await fetch(`/api/v1/bets/${matchId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    choice: selectedChoice,
                    taunt_text: tauntText || null,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showToast(data.detail || "Không lưu được cược.", "error");
                btn.disabled = false;
                btn.textContent = "Lưu thay đổi";
                return;
            }

            upsertMyBetState({
                ...existingBet,
                ...data,
                match_id: Number(matchId),
                choice: data.choice || selectedChoice,
                taunt_text: data.taunt_text ?? null,
                can_edit_taunt: true,
                match_status: "upcoming",
            });
            setChoiceActiveState(matchId, data.choice || selectedChoice);
            matchDetailCache.delete(matchId);
            window.MatchDetailModal?.resetCache?.();
            await fetchAvatarStack(matchId);
            showToast("Đã cập nhật cược.", "success");
            closeBetEditor(matchId);
        } catch (error) {
            showToast("Lỗi kết nối. Vui lòng thử lại.", "error");
            btn.disabled = false;
            btn.textContent = "Lưu thay đổi";
        }
    };

    window.saveBetTaunt = window.saveBetEdit;

    window.renderStakePanel = function renderStakePanelWithTaunt(matchId, choice, totalPool, stakesOnChoice, minStake = null) {
        const panel = document.getElementById(`stake-panel-${matchId}`);
        const selection = matchSelections[matchId] || {};
        const matchStatus = selection.status || "upcoming";
        if (!panel || String(matchStatus).toLowerCase() !== "upcoming") return;

        const maxStake = currentUser ? Number(currentUser.total_points || 0) : 1000;
        const effectiveMin = getEffectiveMinStake(minStake ?? selection.minStake);
        const defaultTaunt = String(currentUser?.default_taunt || "");

        panel.classList.remove("hidden");
        if (maxStake < effectiveMin) {
            panel.innerHTML = `
                <div class="stake-panel">
                    <label>Số điểm đặt cược</label>
                    <div class="text-sm text-rose-600 mt-2">Trận này yêu cầu tối thiểu ${formatCoins(effectiveMin)}. Hiện bạn có ${formatCoins(maxStake)}.</div>
                </div>`;
            return;
        }

        const tauntBlock = `
            <div class="bet-taunt-compact">
                <label>Câu gáy cho trận này</label>
                <textarea
                    id="taunt-${matchId}"
                    class="stake-taunt-input stake-taunt-input-compact"
                    rows="1"
                    maxlength="30"
                    placeholder="Thêm 1 câu gáy ngắn gọn..."
                    oninput="updateBetTauntCounter(${matchId})"
                >${escapeHtml(defaultTaunt)}</textarea>
                <div class="mt-1 flex items-center justify-end text-xs text-slate-400">
                    <span id="taunt-count-${matchId}">${defaultTaunt.length}/30</span>
                </div>
            </div>`;

        // Khi đã có người đặt: số tiền cố định, không cho chọn lại
        const isFixedStake = minStake !== null && minStake !== undefined;
        if (isFixedStake) {
            const fixedStake = effectiveMin;
            panel.innerHTML = `
                <div class="stake-panel">
                    <div class="fixed-stake-display">
                        <div class="fixed-stake-label">Stake cố định</div>
                        <div class="fixed-stake-amount">${formatCoins(fixedStake)}</div>
                    </div>
                    <input type="hidden" id="input-${matchId}" value="${fixedStake}">
                    ${tauntBlock}
                    <div class="est-return" id="est-${matchId}">
                        Ước tính nhận: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, fixedStake))}</strong>
                    </div>
                    <button class="confirm-bet-btn" id="confirm-btn-${matchId}" onclick="confirmBet(${matchId})">
                        Xác nhận đặt cược
                    </button>
                </div>
            `;
            window.updateBetTauntCounter(matchId);
            return;
        }

        // Người đầu tiên: tự do chọn số tiền
        const quickOptions = buildQuickStakeOptions(minStake, maxStake);
        const defaultStake = Math.max(effectiveMin, Math.min(quickOptions[0] || effectiveMin, maxStake));
        const chips = quickOptions.map(value => `
            <button type="button" class="stake-chip" onclick="pickStake(${matchId}, ${totalPool}, ${stakesOnChoice}, ${value})">
                ${formatCoins(value)}
            </button>
        `).join("");

        panel.innerHTML = `
            <div class="stake-panel">
                <label>Số điểm đặt cược</label>
                <div class="bet-panel-hint">Bạn mở pool, stake này sẽ là mức chung.</div>
                <div class="bet-stake-row">
                    ${chips}
                </div>
                <div class="bet-input-row">
                    <input type="number" class="stake-input w-full"
                        id="input-${matchId}"
                        min="${effectiveMin}" max="${maxStake}" step="1" value="${defaultStake}"
                        oninput="syncStake(${matchId}, ${totalPool}, ${stakesOnChoice}, this.value)">
                </div>
                ${tauntBlock}
                <div class="est-return" id="est-${matchId}">
                    Ước tính nhận: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, defaultStake))}</strong>
                </div>
                <button class="confirm-bet-btn" id="confirm-btn-${matchId}" onclick="confirmBet(${matchId})">
                    Xác nhận đặt cược
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
            showToast(`Số điểm tối thiểu là ${formatCoins(effectiveMin)}.`, "error");
            return;
        }
        if (currentUser && stakeVal > currentUser.total_points) {
            showToast("Số điểm không đủ.", "error");
            return;
        }
        if (tauntText.length > 30) {
            showToast("Câu gáy tối đa 30 ký tự.", "error");
            return;
        }

        const confirmLines = [
            `Xác nhận đặt ${formatCoins(stakeVal)} cho cửa ${choiceLabel(selection.choice)}?`,
        ];
        if (tauntText) confirmLines.push(`Câu gáy: "${tauntText}"`);
        if (!window.confirm(confirmLines.join("\n"))) return;

        const btn = document.getElementById(`confirm-btn-${matchId}`);
        if (!btn) return;
        btn.disabled = true;
        btn.textContent = "Đang xử lý...";

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
                showToast(data.detail || "Đặt cược thất bại.", "error");
                btn.disabled = false;
                btn.textContent = "Xác nhận đặt cược";
                return;
            }

            placedBets.add(matchId);
            upsertMyBetState({
                ...data,
                match_id: Number(matchId),
                choice: selection.choice,
                stake: stakeVal,
                taunt_text: data.taunt_text ?? (tauntText || null),
                match_status: "upcoming",
                can_edit_taunt: true,
            });
            setChoiceActiveState(matchId, selection.choice);
            lockPlacedBetButtons(matchId);
            ensureEditActionButton(matchId);
            closeBetPanel(matchId);
            delete matchSelections[matchId];
            updateDisplayedPoints(data.remaining_points);
            showToast(`Đặt cược thành công. Còn lại ${formatCoins(data.remaining_points)}.`, "success");
            matchDetailCache.delete(matchId);
            try {
                await fetchAvatarStack(matchId);
                startTicker();
            } catch (refreshError) {
                console.error(refreshError);
            }
        } catch (error) {
            showToast("Lỗi kết nối. Vui lòng thử lại.", "error");
            btn.disabled = false;
            btn.textContent = "Xác nhận đặt cược";
        }
    };
})();
