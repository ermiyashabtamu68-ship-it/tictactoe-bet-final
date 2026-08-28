/* app.js — the full Nova Bet Mini App. One page, hash-based router,
 * screens for everything the bot used to do in chat (wallet, deposit,
 * withdraw, play, friends, history, profile) plus both game boards. */

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const API_BASE = window.location.origin;
const screenEl = document.getElementById("screen");
const navButtons = document.querySelectorAll(".nav-btn");

const STAKE_TIERS = ["10", "20", "50", "100"];

let me = null;          // cached /webapp/me response
let pollTimer = null;   // generic poller, cleared between screens

function authHeaders(json = true) {
  const h = { "X-Telegram-Init-Data": tg.initData || "" };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders(false) });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Error ${res.status}`);
  return body;
}

async function apiPostJson(path, data) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: authHeaders(true), body: JSON.stringify(data),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Error ${res.status}`);
  return body;
}

async function apiPostForm(path, formData) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: authHeaders(false), body: formData,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Error ${res.status}`);
  return body;
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function fmt(n) {
  return Number(n).toFixed(2);
}

/* ---------------- Router ---------------- */

function currentRoute() {
  const hash = window.location.hash.replace("#/", "") || "home";
  return hash.split("/"); // e.g. ["board", "abc-123"]
}

async function router() {
  stopPolling();
  const [route, param] = currentRoute();

  navButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.route === route));

  if (!me || !me.registered) {
    const fresh = await apiGet("/webapp/me").catch(() => ({ registered: false }));
    me = fresh;
  }

  if (!me.registered && route !== "register") {
    window.location.hash = "#/register";
    return;
  }

  switch (route) {
    case "home": return renderHome();
    case "play": return renderPlayChooseGame();
    case "friends": return renderFriends();
    case "wallet": return renderWallet();
    case "profile": return renderProfile();
    case "register": return renderRegister();
    case "board": return renderBoard(param);
    default: return renderHome();
  }
}

window.addEventListener("hashchange", router);
navButtons.forEach((btn) => {
  btn.addEventListener("click", () => { window.location.hash = `#/${btn.dataset.route}`; });
});

/* ---------------- Registration ---------------- */

function renderRegister() {
  screenEl.innerHTML = `
    <div class="card">
      <h2>👋 Welcome to Nova Bet</h2>
      <p class="center-note" style="text-align:left">Let's set up your account.</p>
      <div class="field">
        <label>Full name</label>
        <input id="reg-name" placeholder="e.g. Yafet Alemu" />
      </div>
      <div class="field">
        <label>Phone number</label>
        <input id="reg-phone" placeholder="09xxxxxxxx" />
      </div>
      <div class="error-text" id="reg-error"></div>
      <button class="btn" id="reg-submit">Create account</button>
    </div>
  `;
  document.getElementById("reg-submit").addEventListener("click", async () => {
    const full_name = document.getElementById("reg-name").value.trim();
    const phone_number = document.getElementById("reg-phone").value.trim();
    const errorEl = document.getElementById("reg-error");
    errorEl.textContent = "";
    if (!full_name || !phone_number) {
      errorEl.textContent = "Please fill in both fields.";
      return;
    }
    try {
      const fd = new FormData();
      fd.append("full_name", full_name);
      fd.append("phone_number", phone_number);
      await apiPostForm("/webapp/register", fd);
      me = await apiGet("/webapp/me");
      tg.HapticFeedback.notificationOccurred("success");
      window.location.hash = "#/home";
      router();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

/* ---------------- Home ---------------- */

async function renderHome() {
  screenEl.innerHTML = `<div class="spinner"></div>`;
  const wallet = await apiGet("/webapp/wallet").catch(() => null);

  screenEl.innerHTML = `
    <div class="card balance-hero">
      <div class="amount">${wallet ? fmt(wallet.available_balance) : "—"} ETB</div>
      <div class="label">Available balance</div>
    </div>

    <div class="grid-2">
      <div class="tile" id="home-play"><span class="tile-icon">🎮</span>Play</div>
      <div class="tile" id="home-friends"><span class="tile-icon">🎯</span>Play vs Friend</div>
      <div class="tile" id="home-deposit"><span class="tile-icon">➕</span>Deposit</div>
      <div class="tile" id="home-withdraw"><span class="tile-icon">💸</span>Withdraw</div>
    </div>

    <div class="card" style="margin-top:14px">
      <h2>📊 Stats</h2>
      <div class="stat-row"><span class="stat-label">Locked (in match/pending)</span><span class="stat-value">${wallet ? fmt(wallet.locked_balance) : "—"} ETB</span></div>
      <div class="stat-row"><span class="stat-label">Total winnings</span><span class="stat-value">${wallet ? fmt(wallet.total_winnings) : "—"} ETB</span></div>
      <div class="stat-row"><span class="stat-label">Total games</span><span class="stat-value">${wallet ? wallet.total_games : "—"}</span></div>
    </div>
  `;

  document.getElementById("home-play").addEventListener("click", () => { window.location.hash = "#/play"; });
  document.getElementById("home-friends").addEventListener("click", () => { window.location.hash = "#/friends"; });
  document.getElementById("home-deposit").addEventListener("click", () => { window.location.hash = "#/wallet"; setTimeout(() => selectWalletTab("deposit"), 0); });
  document.getElementById("home-withdraw").addEventListener("click", () => { window.location.hash = "#/wallet"; setTimeout(() => selectWalletTab("withdraw"), 0); });
}

/* ---------------- Play ---------------- */

async function renderPlayChooseGame() {
  screenEl.innerHTML = `<div class="spinner"></div>`;
  const data = await apiGet("/webapp/matchmaking/open").catch(() => ({ open_matches: [] }));
  const open = data.open_matches;

  screenEl.innerHTML = `
    ${open.length ? `
    <div class="card">
      <h2>⏳ Waiting players — join one</h2>
      ${open.map((m) => `
        <div class="list-row">
          <div>
            <div class="friend-name">${m.display_name}</div>
            <div class="friend-username">${m.game_type === "checkers" ? "🔴 Checkers" : "✕⭕ Tic-Tac-Toe"} · ${m.stake_amount} ETB</div>
          </div>
          <button class="btn" style="margin:0;width:auto;padding:8px 14px" data-join-open="${m.user_id}" data-stake="${m.stake_amount}" data-game="${m.game_type}">Join</button>
        </div>
      `).join("")}
    </div>` : ""}

    <div class="card">
      <h2>🎮 Or start a new game</h2>
      <button class="btn" id="play-ttt">✕⭕ Tic-Tac-Toe</button>
      <button class="btn secondary" id="play-checkers">🔴 Checkers</button>
    </div>
  `;
  document.getElementById("play-ttt").addEventListener("click", () => renderPlayChooseStake("tictactoe"));
  document.getElementById("play-checkers").addEventListener("click", () => renderPlayChooseStake("checkers"));

  screenEl.querySelectorAll("[data-join-open]").forEach((btn) => {
    btn.addEventListener("click", () => joinOpenMatch(btn.dataset.joinOpen, btn.dataset.stake, btn.dataset.game));
  });
}

async function joinOpenMatch(opponentId, stake, gameType) {
  screenEl.innerHTML = `<div class="spinner"></div><div class="center-note">Joining match…</div>`;
  try {
    const fd = new FormData();
    fd.append("opponent_id", opponentId);
    fd.append("stake_amount", stake);
    fd.append("game_type", gameType);
    const result = await apiPostForm("/webapp/matchmaking/join-open", fd);
    window.location.hash = `#/board/${result.match_id}`;
  } catch (err) {
    tg.showAlert(err.message || "That player is no longer available.");
    renderPlayChooseGame();
  }
}

function renderPlayChooseStake(gameType) {
  screenEl.innerHTML = `
    <div class="card">
      <h2>${gameType === "checkers" ? "🔴 Checkers" : "✕⭕ Tic-Tac-Toe"} — choose your stake</h2>
      <div class="stake-grid">
        ${STAKE_TIERS.map((s) => `<button class="stake-btn" data-stake="${s}">${s} ETB</button>`).join("")}
      </div>
      <button class="btn secondary" id="play-back">⬅️ Back</button>
    </div>
  `;
  screenEl.querySelectorAll(".stake-btn").forEach((btn) => {
    btn.addEventListener("click", () => joinQueue(gameType, btn.dataset.stake));
  });
  document.getElementById("play-back").addEventListener("click", renderPlayChooseGame);
}

async function joinQueue(gameType, stake) {
  screenEl.innerHTML = `<div class="spinner"></div><div class="center-note">Finding opponent…</div>`;
  try {
    const fd = new FormData();
    fd.append("stake_amount", stake);
    fd.append("game_type", gameType);
    const result = await apiPostForm("/webapp/matchmaking/join", fd);
    if (result.status === "matched") {
      window.location.hash = `#/board/${result.match_id}`;
      return;
    }
    renderSearching(gameType, stake);
  } catch (err) {
    screenEl.innerHTML = `
      <div class="card"><p class="error-text">${err.message}</p>
      <button class="btn secondary" id="play-back2">⬅️ Back</button></div>`;
    document.getElementById("play-back2").addEventListener("click", renderPlayChooseGame);
  }
}

function renderSearching(gameType, stake) {
  screenEl.innerHTML = `
    <div class="card" style="text-align:center">
      <div class="spinner"></div>
      <p class="center-note">🔎 Finding opponent at ${stake} ETB…</p>
      <button class="btn danger" id="cancel-search">✖️ Cancel</button>
    </div>
  `;
  let cancelled = false;
  document.getElementById("cancel-search").addEventListener("click", async () => {
    cancelled = true;
    stopPolling();
    const fd = new FormData();
    fd.append("stake_amount", stake);
    fd.append("game_type", gameType);
    await apiPostForm("/webapp/matchmaking/leave", fd).catch(() => {});
    renderPlayChooseGame();
  });

  pollTimer = setInterval(async () => {
    if (cancelled) return;
    try {
      const status = await apiGet("/webapp/matchmaking/status");
      if (status.status === "matched") {
        stopPolling();
        window.location.hash = `#/board/${status.match_id}`;
      }
    } catch (err) {
      // ignore transient errors while polling
    }
  }, 3000);
}

/* ---------------- Board (Tic-Tac-Toe + Checkers) ---------------- */

async function renderBoard(matchId) {
  screenEl.innerHTML = `<div class="spinner"></div>`;
  let state;
  try {
    state = await apiGet(`/matches/${matchId}/webapp-state`);
  } catch (err) {
    screenEl.innerHTML = `<div class="card"><p class="error-text">${err.message}</p></div>`;
    return;
  }

  const isCheckers = state.game_type === "checkers";

  screenEl.innerHTML = `
    <div id="board-status-bar">
      <span>${state.stake_amount} ETB</span>
      <span id="board-turn-label">Loading…</span>
    </div>
    <div class="center-note" id="board-debug-line" style="margin-top:-8px;margin-bottom:8px"></div>
    <div id="${isCheckers ? "checkers-board" : "tictactoe-board"}"></div>
    <div id="board-result-banner" class="hidden">
      <div id="board-result-text"></div>
      <button class="btn" id="board-close">Back to Home</button>
    </div>
  `;

  document.getElementById("board-close").addEventListener("click", () => { window.location.hash = "#/home"; });

  let lastBoard = null;
  let selected = null;
  let moving = false;

  async function submitMove(payload, endpoint) {
    const body = await apiPostJson(`/matches/${matchId}/${endpoint}`, payload);
    return body;
  }

  function renderState(s) {
    const turnLabel = document.getElementById("board-turn-label");
    const debugLine = document.getElementById("board-debug-line");
    const myTurn = s.status === "active" && s.current_turn === s.you_are;
    turnLabel.textContent = s.status !== "active" ? "Game over" : myTurn ? "Your turn" : "Opponent's turn";
    turnLabel.classList.toggle("your-turn", myTurn);
    if (debugLine) {
      debugLine.textContent = `(debug: you are ${s.you_are}, current turn is ${s.current_turn})`;
    }

    if (s.status !== "active") {
      stopPolling();
      showResult(s);
    }

    if (s.board === lastBoard && selected === null) return;
    lastBoard = s.board;

    if (isCheckers) renderCheckers(s, myTurn);
    else renderTicTacToe(s, myTurn);
  }

  function renderTicTacToe(s, myTurn) {
    const boardEl = document.getElementById("tictactoe-board");
    boardEl.innerHTML = "";
    for (let i = 0; i < 9; i++) {
      const ch = s.board[i];
      const cell = document.createElement("div");
      cell.className = "ttt-cell";
      if (ch === "X") {
        cell.innerHTML = `<span class="ttt-mark x">✕</span>`;
      } else if (ch === "O") {
        cell.innerHTML = `<span class="ttt-mark o">○</span>`;
      } else if (myTurn) {
        cell.classList.add("selectable");
        cell.addEventListener("click", () => onTttCellTapped(i, s));
      }
      boardEl.appendChild(cell);
    }
  }

  async function onTttCellTapped(pos, s) {
    if (moving) return;
    moving = true;
    try {
      const newState = await submitMove({ cell_position: pos, idempotency_key: crypto.randomUUID() }, "move-webapp");
      tg.HapticFeedback.notificationOccurred("success");
      lastBoard = null;
      renderState(newState);
    } catch (err) {
      tg.HapticFeedback.notificationOccurred("error");
      tg.showAlert(err.message || "That move isn't allowed.");
    } finally {
      moving = false;
    }
  }

  function pieceClass(ch) {
    if (ch === "x") return "ck-piece x-man";
    if (ch === "X") return "ck-piece x-king";
    if (ch === "o") return "ck-piece o-man";
    if (ch === "O") return "ck-piece o-king";
    return null;
  }

  function renderCheckers(s, myTurn) {
    const boardEl = document.getElementById("checkers-board");
    boardEl.innerHTML = "";
    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const pos = row * 8 + col;
        const ch = s.board[pos];
        const isDark = (row + col) % 2 === 1;
        const sq = document.createElement("div");
        sq.className = `ck-square ${isDark ? "dark" : "light"}`;

        if (isDark && ch !== ".") {
          const pClass = pieceClass(ch);
          if (pClass) {
            const p = document.createElement("div");
            p.className = pClass;
            sq.appendChild(p);
          }
        }
        if (selected === pos) sq.classList.add("selected");
        if (isDark && myTurn) {
          sq.classList.add("selectable");
          sq.addEventListener("click", () => onCheckersSquareTapped(pos, ch, s, myTurn));
        }
        boardEl.appendChild(sq);
      }
    }
  }

  async function onCheckersSquareTapped(pos, ch, s, myTurn) {
    const isMine = s.you_are === "X" ? (ch === "x" || ch === "X") : (ch === "o" || ch === "O");

    if (selected === null) {
      if (!isMine) { tg.HapticFeedback.notificationOccurred("error"); return; }
      selected = pos; lastBoard = null; renderState(s); return;
    }
    if (pos === selected) { selected = null; lastBoard = null; renderState(s); return; }
    if (isMine) { selected = pos; lastBoard = null; renderState(s); return; }

    const fromPos = selected;
    selected = null;
    if (moving) return;
    moving = true;
    try {
      const newState = await submitMove(
        { from_position: fromPos, to_position: pos, idempotency_key: crypto.randomUUID() },
        "checkers-move-webapp",
      );
      tg.HapticFeedback.notificationOccurred("success");
      lastBoard = null;
      renderState(newState);
    } catch (err) {
      tg.HapticFeedback.notificationOccurred("error");
      tg.showAlert(err.message || "That move isn't allowed.");
      lastBoard = null;
      renderState(s);
    } finally {
      moving = false;
    }
  }

  function showResult(s) {
    const banner = document.getElementById("board-result-banner");
    const text = document.getElementById("board-result-text");
    banner.classList.remove("hidden");
    if (s.status === "completed_draw") {
      text.textContent = "🤝 It's a draw! Stakes refunded.";
    } else if (s.you_won) {
      text.textContent = `🏆 You won! Payout: ${s.payout_amount} ETB`;
      tg.HapticFeedback.notificationOccurred("success");
    } else {
      const timedOut = s.result_reason === "timeout_forfeit";
      text.textContent = timedOut
        ? "⏱️ Your opponent ran out of time — you lost this one."
        : "❌ You lost this one. Better luck next time!";
    }
  }

  renderState(state);
  pollTimer = setInterval(async () => {
    try {
      const s = await apiGet(`/matches/${matchId}/webapp-state`);
      renderState(s);
    } catch (err) {
      // transient network hiccup — next tick will retry
    }
  }, 2000);
}

/* ---------------- Friends ---------------- */

async function renderFriends() {
  screenEl.innerHTML = `<div class="spinner"></div>`;
  const data = await apiGet("/webapp/friends").catch(() => ({ friends: [], pending_requests: [] }));

  screenEl.innerHTML = `
    <div class="card">
      <h2>➕ Add a friend</h2>
      <div class="field">
        <input id="add-friend-username" placeholder="@username or their ID" />
      </div>
      <div class="error-text" id="add-friend-error"></div>
      <button class="btn" id="add-friend-btn">Send request</button>
    </div>

    ${data.pending_requests.length ? `
    <div class="card">
      <h2>📨 Pending requests</h2>
      ${data.pending_requests.map((r) => `
        <div class="list-row">
          <span>New friend request</span>
          <span class="btn-row" style="width:auto">
            <button class="btn" style="margin:0;padding:8px 14px" data-accept="${r.request_id}">Accept</button>
            <button class="btn secondary" style="margin:0;padding:8px 14px" data-decline="${r.request_id}">Decline</button>
          </span>
        </div>
      `).join("")}
    </div>` : ""}

    <div class="card">
      <h2>👥 Your friends</h2>
      ${data.friends.length ? data.friends.map((f) => `
        <div class="list-row">
          <div>
            <div class="friend-name">${f.full_name || f.telegram_username}</div>
            <div class="friend-username">@${f.telegram_username}</div>
          </div>
          <button class="btn" style="margin:0;width:auto;padding:8px 14px" data-invite="${f.internal_id}">Invite</button>
        </div>
      `).join("") : `<p class="center-note">No friends yet — add one above.</p>`}
    </div>
  `;

  document.getElementById("add-friend-btn").addEventListener("click", async () => {
    const username = document.getElementById("add-friend-username").value.trim().replace(/^@/, "");
    const errorEl = document.getElementById("add-friend-error");
    errorEl.textContent = "";
    if (!username) { errorEl.textContent = "Enter a username."; return; }
    try {
      await apiPostForm("/webapp/friends/request", (() => { const fd = new FormData(); fd.append("friend_username", username); return fd; })());
      tg.HapticFeedback.notificationOccurred("success");
      renderFriends();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  screenEl.querySelectorAll("[data-accept]").forEach((btn) => {
    btn.addEventListener("click", () => respondFriendRequest(btn.dataset.accept, true));
  });
  screenEl.querySelectorAll("[data-decline]").forEach((btn) => {
    btn.addEventListener("click", () => respondFriendRequest(btn.dataset.decline, false));
  });
  screenEl.querySelectorAll("[data-invite]").forEach((btn) => {
    btn.addEventListener("click", () => renderInviteStakePicker(btn.dataset.invite));
  });
}

async function respondFriendRequest(requestId, accept) {
  try {
    const fd = new FormData();
    fd.append("request_id", requestId);
    fd.append("accept", accept);
    await apiPostForm("/webapp/friends/respond", fd);
    tg.HapticFeedback.notificationOccurred("success");
    renderFriends();
  } catch (err) {
    tg.showAlert(err.message);
  }
}

function renderInviteStakePicker(friendId) {
  screenEl.innerHTML = `
    <div class="card">
      <h2>🎯 Invite to play — choose game & stake</h2>
      <div class="tabs">
        <button class="tab-btn active" data-game="tictactoe">✕⭕ Tic-Tac-Toe</button>
        <button class="tab-btn" data-game="checkers">🔴 Checkers</button>
      </div>
      <div class="stake-grid">
        ${STAKE_TIERS.map((s) => `<button class="stake-btn" data-stake="${s}">${s} ETB</button>`).join("")}
      </div>
      <button class="btn secondary" id="invite-back">⬅️ Back</button>
    </div>
  `;
  let selectedGame = "tictactoe";
  screenEl.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      screenEl.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedGame = btn.dataset.game;
    });
  });
  screenEl.querySelectorAll(".stake-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const fd = new FormData();
        fd.append("friend_id", friendId);
        fd.append("stake_amount", btn.dataset.stake);
        fd.append("game_type", selectedGame);
        await apiPostForm("/webapp/friends/invite", fd);
        tg.HapticFeedback.notificationOccurred("success");
        tg.showAlert("Invite sent! Waiting for them to accept.");
        window.location.hash = "#/home";
      } catch (err) {
        tg.showAlert(err.message);
      }
    });
  });
  document.getElementById("invite-back").addEventListener("click", renderFriends);
}

/* ---------------- Wallet (overview / deposit / withdraw / history) ---------------- */

let walletTab = "overview";

function selectWalletTab(tab) {
  walletTab = tab;
  renderWallet();
}

async function renderWallet() {
  screenEl.innerHTML = `
    <div class="tabs">
      <button class="tab-btn ${walletTab === "overview" ? "active" : ""}" data-tab="overview">Overview</button>
      <button class="tab-btn ${walletTab === "deposit" ? "active" : ""}" data-tab="deposit">Deposit</button>
      <button class="tab-btn ${walletTab === "withdraw" ? "active" : ""}" data-tab="withdraw">Withdraw</button>
      <button class="tab-btn ${walletTab === "history" ? "active" : ""}" data-tab="history">History</button>
    </div>
    <div id="wallet-tab-content"><div class="spinner"></div></div>
  `;
  screenEl.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => selectWalletTab(btn.dataset.tab));
  });

  const content = document.getElementById("wallet-tab-content");
  if (walletTab === "overview") return renderWalletOverview(content);
  if (walletTab === "deposit") return renderDepositForm(content);
  if (walletTab === "withdraw") return renderWithdrawForm(content);
  if (walletTab === "history") return renderHistory(content);
}

async function renderWalletOverview(content) {
  const wallet = await apiGet("/webapp/wallet").catch(() => null);
  content.innerHTML = `
    <div class="card balance-hero">
      <div class="amount">${wallet ? fmt(wallet.available_balance) : "—"} ETB</div>
      <div class="label">Available balance</div>
    </div>
    <div class="card">
      <div class="stat-row"><span class="stat-label">Locked (in match/pending)</span><span class="stat-value">${wallet ? fmt(wallet.locked_balance) : "—"} ETB</span></div>
      <div class="stat-row"><span class="stat-label">Total winnings</span><span class="stat-value">${wallet ? fmt(wallet.total_winnings) : "—"} ETB</span></div>
      <div class="stat-row"><span class="stat-label">Total games</span><span class="stat-value">${wallet ? wallet.total_games : "—"}</span></div>
      <div class="stat-row"><span class="stat-label">Total deposits</span><span class="stat-value">${wallet ? fmt(wallet.total_deposits) : "—"} ETB</span></div>
      <div class="stat-row"><span class="stat-label">Total withdrawals</span><span class="stat-value">${wallet ? fmt(wallet.total_withdrawals) : "—"} ETB</span></div>
    </div>
  `;
}

function renderDepositForm(content) {
  content.innerHTML = `
    <div class="card">
      <h2>➕ Deposit</h2>
      <div class="field">
        <label>Payment method</label>
        <select id="dep-method">
          <option value="telebirr">📱 Telebirr</option>
          <option value="nib_bank">🏦 NIB Bank</option>
        </select>
      </div>
      <div class="field">
        <label>Amount (ETB)</label>
        <input id="dep-amount" type="number" min="25" placeholder="Minimum 25 ETB" />
      </div>
      <div class="field">
        <label>Reference number</label>
        <input id="dep-reference" placeholder="Transaction reference" />
      </div>
      <div class="field">
        <label>Payment screenshot</label>
        <div class="file-upload" id="dep-file-label">Tap to choose a screenshot</div>
        <input id="dep-file" type="file" accept="image/*" style="display:none" />
      </div>
      <div class="error-text" id="dep-error"></div>
      <button class="btn" id="dep-submit">Submit deposit</button>
    </div>
  `;
  const fileLabel = document.getElementById("dep-file-label");
  const fileInput = document.getElementById("dep-file");
  fileLabel.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) {
      fileLabel.textContent = `✅ ${fileInput.files[0].name}`;
      fileLabel.classList.add("has-file");
    }
  });

  document.getElementById("dep-submit").addEventListener("click", async () => {
    const errorEl = document.getElementById("dep-error");
    errorEl.textContent = "";
    const amount = document.getElementById("dep-amount").value.trim();
    const reference = document.getElementById("dep-reference").value.trim();
    const method = document.getElementById("dep-method").value;
    const file = fileInput.files[0];
    if (!amount || !reference || !file) {
      errorEl.textContent = "Please fill in every field and attach a screenshot.";
      return;
    }
    try {
      const fd = new FormData();
      fd.append("amount", amount);
      fd.append("payment_method", method);
      fd.append("reference_number", reference);
      fd.append("screenshot", file);
      await apiPostForm("/webapp/deposits", fd);
      tg.HapticFeedback.notificationOccurred("success");
      tg.showAlert("Deposit submitted! An admin will review it shortly.");
      selectWalletTab("overview");
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

function renderWithdrawForm(content) {
  content.innerHTML = `
    <div class="card">
      <h2>💸 Withdraw</h2>
      <div class="field">
        <label>Payment method</label>
        <select id="wd-method">
          <option value="telebirr">📱 Telebirr</option>
          <option value="nib_bank">🏦 NIB Bank</option>
        </select>
      </div>
      <div class="field">
        <label>Amount (ETB)</label>
        <input id="wd-amount" type="number" min="25" placeholder="Minimum 25 ETB" />
      </div>
      <div class="field">
        <label>Payment details</label>
        <input id="wd-details" placeholder="Phone number / account number" />
      </div>
      <div class="error-text" id="wd-error"></div>
      <button class="btn" id="wd-submit">Request withdrawal</button>
    </div>
  `;
  document.getElementById("wd-submit").addEventListener("click", async () => {
    const errorEl = document.getElementById("wd-error");
    errorEl.textContent = "";
    const amount = document.getElementById("wd-amount").value.trim();
    const details = document.getElementById("wd-details").value.trim();
    const method = document.getElementById("wd-method").value;
    if (!amount || !details) {
      errorEl.textContent = "Please fill in every field.";
      return;
    }
    try {
      const fd = new FormData();
      fd.append("amount", amount);
      fd.append("payment_method", method);
      fd.append("payment_details", details);
      await apiPostForm("/webapp/withdrawals", fd);
      tg.HapticFeedback.notificationOccurred("success");
      tg.showAlert("Withdrawal requested! An admin will process it shortly.");
      selectWalletTab("overview");
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

async function renderHistory(content) {
  const data = await apiGet("/webapp/history").catch(() => ({ matches: [] }));
  content.innerHTML = `
    <div class="card">
      <h2>📜 Match history</h2>
      ${data.matches.length ? data.matches.map((m) => {
        let pillClass = "draw", pillText = "Draw";
        if (m.status === "completed_win") { pillClass = m.you_won ? "win" : "loss"; pillText = m.you_won ? "Won" : "Lost"; }
        else if (m.status === "completed_forfeit") { pillClass = m.you_won ? "win" : "loss"; pillText = m.you_won ? "Won (forfeit)" : "Lost (forfeit)"; }
        else if (m.status === "voided") { pillClass = "pending"; pillText = "Voided"; }
        return `
          <div class="list-row">
            <div>
              <div class="friend-name">${m.game_type === "checkers" ? "🔴 Checkers" : "✕⭕ Tic-Tac-Toe"} — ${m.stake_amount} ETB</div>
              <div class="friend-username">${m.settled_at ? new Date(m.settled_at).toLocaleDateString() : ""}</div>
            </div>
            <span class="pill ${pillClass}">${pillText}</span>
          </div>
        `;
      }).join("") : `<p class="center-note">No completed matches yet.</p>`}
    </div>
  `;
}

/* ---------------- Profile ---------------- */

async function renderProfile() {
  screenEl.innerHTML = `<div class="spinner"></div>`;
  const info = await apiGet("/webapp/me").catch(() => null);
  screenEl.innerHTML = `
    <div class="card" style="text-align:center">
      <div style="font-size:44px;margin-bottom:8px">👤</div>
      <h2 style="margin-bottom:2px">${info?.full_name || "—"}</h2>
      <p class="friend-username">@${info?.telegram_username || "—"}</p>
    </div>
    <div class="card">
      <h2>🪪 Your ID</h2>
      <p class="center-note" style="text-align:left;margin-bottom:10px">
        Share this with friends so they can add you — works even if
        you don't have a Telegram username set.
      </p>
      <div class="stat-row">
        <span class="stat-value" id="profile-id-value" style="font-size:20px">${info?.telegram_user_id || "—"}</span>
        <button class="btn secondary" id="profile-id-copy" style="margin:0;width:auto;padding:8px 14px">Copy</button>
      </div>
    </div>
    <div class="card">
      <h2>❓ Need help?</h2>
      <p class="center-note" style="text-align:left">Contact support from the Telegram chat with this bot for deposit/withdrawal issues or anything else.</p>
    </div>
  `;
  const copyBtn = document.getElementById("profile-id-copy");
  if (copyBtn && info?.telegram_user_id) {
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(String(info.telegram_user_id)).catch(() => {});
      tg.HapticFeedback.notificationOccurred("success");
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
    });
  }
}

/* ---------------- Boot ---------------- */

router();
