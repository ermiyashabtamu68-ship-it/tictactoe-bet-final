/* app.js — the Tic-Tac-Toe Mini App. Same pattern as checkers_app:
 * polls the backend for match state, authenticates every request
 * with Telegram's signed initData since this affects real money. */

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

let pollTimer = null;
let lastBoard = null;
let mySymbol = null;
let moving = false;

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

async function submitMove(cellPosition) {
  const res = await fetch(`${API_BASE}/matches/${matchId}/move-webapp`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      cell_position: cellPosition,
      idempotency_key: crypto.randomUUID(),
    }),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body.detail || `Error ${res.status}`);
  }
  return body;
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

  if (state.board === lastBoard) return; // nothing changed, skip re-render
  lastBoard = state.board;

  boardEl.innerHTML = "";
  for (let i = 0; i < 9; i++) {
    const ch = state.board[i];

    const cell = document.createElement("div");
    cell.className = "cell";

    if (ch === "X") {
      cell.classList.add("filled");
      cell.innerHTML = `<span class="mark mark-x">✕</span>`;
    } else if (ch === "O") {
      cell.classList.add("filled");
      cell.innerHTML = `<span class="mark mark-o">○</span>`;
    } else if (myTurn) {
      cell.classList.add("selectable");
      cell.addEventListener("click", () => onCellTapped(i));
    }

    boardEl.appendChild(cell);
  }
}

async function onCellTapped(pos) {
  if (moving) return;
  moving = true;
  try {
    const newState = await submitMove(pos);
    tg.HapticFeedback.notificationOccurred("success");
    lastBoard = null;
    render(newState);
  } catch (err) {
    tg.HapticFeedback.notificationOccurred("error");
    tg.showAlert(err.message || "That move isn't allowed.");
  } finally {
    moving = false;
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
