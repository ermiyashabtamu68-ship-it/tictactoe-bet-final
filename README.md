# TicTacToe Bet

A Telegram bot where two players stake equal amounts and play
Tic-Tac-Toe for real money. The platform takes a fixed 5 ETB fee per
completed match; the winner takes the rest.

## Where to start

- **First time setup?** → Read `SETUP.md` — full step-by-step guide,
  written for someone with no server experience.
- **Want to understand the security model?** → Read `SECURITY.md`.
- **Team roles:**
  - Yafet — Finance (approve/reject deposits & withdrawals)
  - Nahom — Support (users, moderation)
  - You — Bug fixes / technical

## Project structure

```
tictactoe-bet/
├── db/migrations/       Database schema (run automatically on first start)
├── api/                 FastAPI backend — all business logic lives here
│   ├── app/
│   │   ├── models/       Database table definitions
│   │   ├── services/      Wallet, matchmaking, game, user logic
│   │   ├── routes/         API endpoints (what the bot/admin panel call)
│   │   └── core/            Database/Redis connections, auth, rate limiting
│   ├── tests/            Unit tests
│   └── seed_admins.py    Run once to create your 3 admin accounts
├── bot/                  Telegram bot — the buttons/screens players see
│   └── handlers/          One file per feature (play, deposit, withdraw, etc.)
├── admin/                Admin web panel (plain HTML/CSS/JS, no build step)
├── docker/                Docker setup — how everything runs together
├── .env.example            Copy to docker/.env and fill in your real values
├── SETUP.md                 Full setup instructions
└── SECURITY.md                Security measures and known limitations
```

## How the pieces talk to each other

```
Telegram player
      ↓
   Bot (bot/)  ──HTTP──►  API (api/)  ◄──HTTP──  Admin Panel (admin/)
                              ↓
                        PostgreSQL + Redis
```

The bot and admin panel never touch the database directly — they
only ever talk to the API, which is the single source of truth and
the only place business rules (money, game rules) are enforced.

## Core rules (as decided)

- Stakes: 10 / 20 / 50 / 100 ETB
- Platform fee: 5 ETB per completed match
- Winner payout: total pot − 5 ETB
- Draw: full refund to both players, no fee
- Move timeout: 45 seconds → forfeit, opponent wins
- Registration: name + phone number (no KYC/age checks, per decision)

## Status

Built module by module, checked for correctness at each step. See
`SECURITY.md` section 7 for an honest list of what still needs
attention before a wider launch (HTTPS, KYC if your license requires
it, geo-restriction, live database testing).
