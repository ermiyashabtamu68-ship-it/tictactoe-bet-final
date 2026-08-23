# Security Documentation — TicTacToe Bet

This document explains every security measure built into the
platform, in plain language, and honestly notes what still needs
attention before real money is at stake at scale.

---

## 1. Money safety

**Every balance change goes through one file** (`wallet_service.py`).
Nothing else in the codebase is allowed to touch a wallet's numbers
directly. This means there's only one place bugs involving money can
hide, and one place to check.

**Idempotency keys prevent double-processing.** Every deposit
approval, withdrawal, stake lock, and payout has a unique key tied to
the specific event (e.g. `payout:{match_id}:{user_id}`). If the same
action is attempted twice — a double-click, a network retry, a bug —
the database itself rejects the second attempt. This is what makes
**"a match cannot be settled twice"** actually true, not just a
promise.

**Row-level locking prevents race conditions.** When two things try
to change the same wallet or match at the exact same moment (e.g.
two players tapping simultaneously), the database locks that row so
one operation finishes completely before the other starts. This
stops "lost update" bugs where two changes overwrite each other
incorrectly.

**Balances can never go negative.** Database-level constraints
(`CHECK (available_balance >= 0)`) enforce this as a hard floor, not
just application logic that could be bypassed by a bug elsewhere.

**Admin balance edits are always audited.** There is no code path
for an admin to directly set a number in someone's wallet. The only
function that allows a manual adjustment (`admin_adjust_balance`)
requires a reason and always creates a permanent, attributed record.

---

## 2. Game integrity

**The server is the only authority.** The Telegram bot never
calculates who won, whose turn it is, or whether a move is legal —
it only displays whatever `match_service.py` (running on the
server) decides. A tampered or fake Telegram client cannot cheat,
because the server independently re-validates every move against
what's actually stored in the database.

**Every move is checked against real rules:**
- Is the match still active?
- Is it actually this player's turn?
- Is the target cell empty?
- Has this exact move request been seen before (idempotency key)?

**Timeouts are enforced server-side**, via a background task that
runs every 5 seconds — not by trusting the client to report "my
opponent went silent."

---

## 3. Authentication

**Users** are identified by Telegram user ID (which cannot be
spoofed within Telegram's own platform) combined with a registered
name and phone number, not just their changeable Telegram username.

**Admins** log in with a username and bcrypt-hashed password (never
stored in plain text) and receive a signed JWT token that expires
after 12 hours. Every admin action re-checks this token.

**Role-based permissions** restrict sensitive actions: only accounts
with the `finance` role (or `super_admin`) can approve deposits or
withdrawals, so a support-only account physically cannot move money
even if compromised.

---

## 4. Rate limiting

- Admin login: limited to 5 attempts per minute per IP address, to
  block password-guessing.
- Game moves: limited to 30 per minute per IP, to block move-spam
  abuse.
- All other endpoints: a general 100/minute default.

Rate limits are tracked in Redis, so they work correctly even if you
later scale to multiple API servers.

---

## 5. Audit logging

Every sensitive admin action (approving/rejecting a deposit or
withdrawal, suspending a user, adjusting a balance) writes a
permanent row to `audit_logs`, recording who did it, when, and why.
These rows are never edited or deleted by the application.

---

## 6. What is deliberately manual (by design, not a gap)

Deposit and withdrawal approval require a human to check the real
Telebirr/bank account — this is intentional, not a missing feature.
Screenshots and reference numbers alone are never trusted or
auto-approved.

---

## 7. Known limitations — be aware of these

Being direct about what still needs attention:

- **KYC and age verification are not enforced.** Per your explicit
  decision, only name + phone number are collected at registration.
  The database has fields for age/KYC status if you want to add real
  checks later, but nothing currently blocks underage or unverified
  users. If your license requires this, it needs to be added before
  wider launch.
- **Geographic restriction is not enforced.** The `country_code`
  field exists but nothing currently checks or blocks non-Ethiopian
  users.
- **Wallet tests have not been run against a live database yet**
  (written and logically verified, but not executed — see SETUP.md).
  Run them yourself early and report any failures.
- **HTTPS is not configured yet.** The setup as given runs over
  plain HTTP. Before handling real user traffic (especially admin
  logins and payment screenshots), put a reverse proxy like Caddy or
  Nginx in front with a free HTTPS certificate (e.g. via Let's
  Encrypt) — otherwise login tokens and data travel unencrypted.
- **The CORS policy is wide open** (`allow_origins=["*"]`) for ease
  of local testing. Before going live, restrict this to your actual
  admin panel domain only.
- **No automated backup schedule** — SETUP.md shows the manual
  backup command, but nothing runs it automatically. Consider adding
  a scheduled task (cron) for daily backups.

---

## Reporting a problem

If you or Nahom/Yafet notice anything that looks like a security
issue (money not matching, a way to bypass a check, etc.), stop and
document exactly what happened before doing anything else — the
audit_logs and wallet_transactions tables will have the full history
needed to investigate.
