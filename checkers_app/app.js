/* app.js — the checkers Mini App. Talks to the same backend the bot
 * uses, but authenticates every request with Telegram's signed
 * initData instead of a plain user id, since this affects real money. */

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const API_BASE = window.location.origin;
const params = new URLSearchParams(window.location.search);
const matchId = params.get("match_id");

const boardEl = document.getElementById("board");
const turnLabel = document.getElementById("turn-label");
const stakeLabel = document.getElementById("stake-label");
const resultBanner = document.getElementById("result-banner");
const resultText = document.getElementById("result-text");
const closeBtn = document.getElementById("close-btn");

let selected = null;   // currently selected square index (0-63), or null
let pollTimer = null;
let lastBoard = null;  // avoid re-rendering identical state (prevents flicker)
let mySymbol = null;   // "X" or "O"

closeBtn.addEventListener("click", () => tg.close());

function authHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": tg.initData || "",
  };
}

async function fetchState() {
  const res = await fetch(`${API_BASE}/matches/${matchId}/webapp-state`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Error ${res.status}`);
  }
  return res.json();
}

async function submitMove(fromPos, toPos) {
  const res = await fetch(`${API_BASE}/matches/${matchId}/checkers-move-webapp`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      from_position: fromPos,
      to_position: toPos,
      idempotency_key: crypto.randomUUID(),
    }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body.detail || `Error ${res.status}`);
  }
  return body;
}

function pieceClass(ch) {
  if (ch === "x") return "piece x-man";
  if (ch === "X") return "piece x-king";
  if (ch === "o") return "piece o-man";
  if (ch === "O") return "piece o-king";
  return null;
}

function render(state) {
  mySymbol = state.you_are;

  stakeLabel.textContent = `${state.stake_amount} ETB`;

  if (state.status !== "active") {
    stopPolling();
    showResult(state);
  }

  const myTurn = state.status === "active" && state.current_turn === mySymbol;
  turnLabel.textContent = state.status !== "active"
    ? "Game over"
    : myTurn ? "Your turn" : "Opponent's turn";
  turnLabel.classList.toggle("your-turn", myTurn);

  if (state.board === lastBoard && selected === null) return; // nothing changed, skip re-render
  lastBoard = state.board;

  boardEl.innerHTML = "";
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const pos = row * 8 + col;
      const ch = state.board[pos];
      const isDark = (row + col) % 2 === 1;

      const sq = document.createElement("div");
      sq.className = `square ${isDark ? "dark" : "light"}`;
      sq.dataset.pos = pos;

      if (isDark && ch !== ".") {
        const pClass = pieceClass(ch);
        if (pClass) {
          const p = document.createElement("div");
          p.className = pClass;
          sq.appendChild(p);
        }
      }

      if (selected === pos) {
        sq.classList.add("selected");
      }

      if (isDark && myTurn) {
        sq.classList.add("selectable");
        sq.addEventListener("click", () => onSquareTapped(pos, ch, state));
      }

      boardEl.appendChild(sq);
    }
  }
}

async function onSquareTapped(pos, ch, state) {
  const isMine = mySymbol === "X" ? (ch === "x" || ch === "X") : (ch === "o" || ch === "O");

  if (selected === null) {
    if (!isMine) {
      tg.HapticFeedback.notificationOccurred("error");
      return;
    }
    selected = pos;
    lastBoard = null; // force re-render to show highlight
    render(state);
    return;
  }

  if (pos === selected) {
    selected = null;
    lastBoard = null;
    render(state);
    return;
  }

  if (isMine) {
    // Switch selection to the other piece
    selected = pos;
    lastBoard = null;
    render(state);
    return;
  }

  // Attempt the move
  const fromPos = selected;
  selected = null;
  try {
    const newState = await submitMove(fromPos, pos);
    tg.HapticFeedback.notificationOccurred("success");
    lastBoard = null;
    render(newState);
  } catch (err) {
    tg.HapticFeedback.notificationOccurred("error");
    tg.showAlert(err.message || "That move isn't allowed.");
    lastBoard = null;
    render(state);
  }
}

function showResult(state) {
  resultBanner.classList.remove("hidden");
  if (state.status === "completed_draw") {
    resultText.textContent = "🤝 It's a draw! Stakes refunded.";
  } else if (state.you_won) {
    resultText.textContent = `🏆 You won! Payout: ${state.payout_amount} ETB`;
    tg.HapticFeedback.notificationOccurred("success");
  } else {
    const timedOut = state.result_reason === "timeout_forfeit";
    resultText.textContent = timedOut
      ? "⏱️ Your opponent ran out of time — you lost this one."
      : "❌ You lost this one. Better luck next time!";
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function tick() {
  try {
    const state = await fetchState();
    render(state);
  } catch (err) {
    turnLabel.textContent = "Connection error";
  }
}

async function main() {
  if (!matchId) {
    turnLabel.textContent = "No match specified.";
    return;
  }
  await tick();
  pollTimer = setInterval(tick, 2000);
}

main();
