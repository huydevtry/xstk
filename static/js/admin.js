document.addEventListener("DOMContentLoaded", () => {
    fetchMe();
    fetchMatches();
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

async function fetchMe() {
    try {
        const res = await fetch("/api/v1/me");
        if (res.ok) {
            const data = await res.json();
            document.getElementById("user-info").innerText = `${data.email} | Admin`;
        } else {
            document.getElementById("user-info").innerText = `Lỗi xác thực`;
        }
    } catch (err) {
        console.error(err);
    }
}

async function fetchMatches() {
    try {
        const res = await fetch("/api/v1/admin/matches");
        if (!res.ok) {
            const err = await res.json();
            document.getElementById("admin-match-list").innerHTML = `<div class="p-4 bg-red-900/50 text-red-400 rounded-xl border border-red-800">Lỗi: ${escapeHtml(err.detail || 'Không thể tải danh sách')}</div>`;
            return;
        }
        const matches = await res.json();
        renderMatches(matches);
    } catch (err) {
        console.error(err);
    }
}

function renderMatches(matches) {
    const list = document.getElementById("admin-match-list");
    list.innerHTML = "";

    if (matches.length === 0) {
        list.innerHTML = '<div class="text-center text-gray-500 py-8">Không có trận đấu nào.</div>';
        return;
    }

    matches.forEach(m => {
        const isFinished = m.status === 'finished';
        const card = document.createElement("div");
        card.className = "bg-gray-800 p-4 rounded-xl border border-gray-700 flex flex-col md:flex-row justify-between items-center gap-4";
        const homeIconSrc = safeImageSrc(m.home_icon);
        const awayIconSrc = safeImageSrc(m.away_icon);
        const homeIconHtml = homeIconSrc ? `<img src="${homeIconSrc}" class="w-5 h-5 inline-block mr-1 rounded-full">` : '';
        const awayIconHtml = awayIconSrc ? `<img src="${awayIconSrc}" class="w-5 h-5 inline-block ml-1 rounded-full">` : '';
        const homeTeam = escapeHtml(m.home_team);
        const awayTeam = escapeHtml(m.away_team);
        const status = escapeHtml(m.status);

        let html = `
            <div class="flex-1 w-full">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-xs ${isFinished ? 'text-gray-500 bg-gray-900' : 'text-emerald-400 bg-emerald-950'} px-2 py-0.5 rounded border ${isFinished ? 'border-gray-700' : 'border-emerald-800'}">${status}</span>
                    <span class="text-xs text-gray-400">ID: ${m.id} | Kèo chấp: ${m.handicap}</span>
                </div>
                <div class="flex justify-between items-center font-bold text-lg">
                    <div class="w-2/5 text-right flex items-center justify-end">${homeIconHtml}${homeTeam}</div>
                    <div class="w-1/5 text-center text-gray-500">${isFinished ? `${m.home_score} - ${m.away_score}` : 'vs'}</div>
                    <div class="w-2/5 text-left flex items-center justify-start">${awayTeam}${awayIconHtml}</div>
                </div>
            </div>
        `;

        if (!isFinished) {
            html += `
            <div class="flex gap-2 w-full md:w-auto mt-2 md:mt-0 items-center justify-center">
                <input type="number" id="home-score-${m.id}" placeholder="H" class="w-16 bg-gray-900 border border-gray-700 text-white px-2 py-2 rounded text-center" min="0">
                <span class="text-gray-500">-</span>
                <input type="number" id="away-score-${m.id}" placeholder="A" class="w-16 bg-gray-900 border border-gray-700 text-white px-2 py-2 rounded text-center" min="0">
                <button onclick="resolveMatch(${m.id})" class="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded font-semibold transition-colors whitespace-nowrap ml-2">Giải Trận</button>
            </div>
            `;
        }

        card.innerHTML = html;
        list.appendChild(card);
    });
}

async function resolveMatch(id) {
    const homeScoreInput = document.getElementById(`home-score-${id}`);
    const awayScoreInput = document.getElementById(`away-score-${id}`);
    
    if (!homeScoreInput || !awayScoreInput || homeScoreInput.value === "" || awayScoreInput.value === "") {
        alert("Vui lòng nhập tỉ số cho cả hai đội!");
        return;
    }

    const home_score = parseInt(homeScoreInput.value);
    const away_score = parseInt(awayScoreInput.value);

    if (confirm(`Bạn có chắc muốn giải trận đấu này với tỉ số: ${home_score} - ${away_score}?`)) {
        try {
            const res = await fetch(`/api/v1/admin/resolve-match/${id}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ home_score, away_score })
            });
            const data = await res.json();
            if (res.ok) {
                alert(`Thành công! Kết quả kèo: ${data.winning_choice}`);
                fetchMatches();
            } else {
                alert(`Lỗi: ${data.detail}`);
            }
        } catch (err) {
            console.error(err);
            alert("Đã xảy ra lỗi hệ thống.");
        }
    }
}

async function syncMatches() {
    const btn = document.getElementById("sync-btn");
    btn.disabled = true;
    const oldHtml = btn.innerHTML;
    btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Đang đồng bộ...`;

    try {
        const res = await fetch("/api/v1/admin/sync-matches", { method: "POST" });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.message);
            fetchMatches();
        } else {
            alert(`Lỗi: ${data.detail}`);
        }
    } catch (err) {
        console.error(err);
        alert("Đã xảy ra lỗi hệ thống khi đồng bộ.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    }
}
