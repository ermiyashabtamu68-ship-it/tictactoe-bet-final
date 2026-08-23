# TicTacToe Bet — Setup Instructions

This guide assumes NO prior server experience. Follow it in order.

## What you need before starting

- An Oracle Cloud "Always Free" VM (or any Ubuntu server with Docker)
- Your Telegram bot token (from @BotFather)
- Your Telebirr and NIB Bank details (for the deposit instructions text)
- SSH access to your server (from your phone via Termux/JuiceSSH, or a laptop)

---

## Step 1 — Install Docker on your server

SSH into your server, then run:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Log out and log back in (or restart your SSH session) for the permission change to apply.

Verify it worked:
```bash
docker --version
docker compose version
```

---

## Step 2 — Get the project onto your server

If using GitHub (recommended for a 3-person team):
```bash
git clone <your-repo-url>
cd tictactoe-bet
```

If uploading manually (e.g. via SCP), just make sure the whole `tictactoe-bet/` folder ends up on the server with its structure intact.

---

## Step 3 — Configure your environment

```bash
cp .env.example docker/.env
nano docker/.env
```

Fill in every value:
- `POSTGRES_PASSWORD` — make up a strong password
- `ADMIN_JWT_SECRET` — generate one with:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- `BOT_TOKEN` — from @BotFather
- `TELEBIRR_INSTRUCTIONS` / `NIB_BANK_INSTRUCTIONS` — your real payment details, shown to users during Deposit

Save and exit (in nano: Ctrl+O, Enter, Ctrl+X).

**Important:** `.env` must live inside the `docker/` folder (same folder as `docker-compose.yml`), not the project root — that's why we copied it there.

---

## Step 4 — Start everything

```bash
cd docker
docker compose up -d --build
```

This builds and starts 4 containers: the database, Redis, the API, and the bot.

Check everything is running:
```bash
docker compose ps
```

You should see 4 services listed as "running" or "healthy".

Check logs if anything looks wrong:
```bash
docker compose logs -f api
docker compose logs -f bot
```
(Press Ctrl+C to stop watching logs — this does not stop the services.)

---

## Step 5 — Create your admin accounts

```bash
docker compose exec api python seed_admins.py
```

Follow the prompts to create 3 accounts — one for you, Yafet, and Nahom — as planned:
- You → `super_admin`
- Yafet → `finance`
- Nahom → `support`

Write down the usernames/passwords somewhere safe (a password manager, not a text file lying around).

---

## Step 6 — Test the bot

Open Telegram, find your bot, send `/start`. You should be asked for your name and phone number, then see the main menu.

## Step 7 — Test the admin panel

Open a browser and go to:
```
http://YOUR_SERVER_IP:8000/admin-panel/
```

Log in with one of the accounts you just created.

---

## Everyday operations (after setup)

- **Restart everything:** `docker compose restart`
- **Stop everything:** `docker compose down`
- **Start again:** `docker compose up -d`
- **View logs:** `docker compose logs -f <service>` (service = api, bot, db, or redis)
- **Update code after a change:** `docker compose up -d --build`

---

## Running the tests

Tests check that money math is correct — important to run after any
code change, especially to wallet_service.py or match_service.py.

```bash
docker compose exec api pip install -r requirements-dev.txt
docker compose exec api pytest tests/ -v
```

`test_game_logic.py` checks win/draw detection (already verified
correct — see below). `test_wallet_service.py` checks that deposits,
stakes, payouts, draws, and withdrawals all move the correct amounts
of money, and specifically confirms **a match cannot be paid out
twice** — the most important test in the whole project.

**Honesty note:** these tests were written carefully and the win/draw
detection logic was independently verified to be correct, but they
have not been run against a live database yet (the environment used
to write this code has no internet access to install PostgreSQL).
Run them yourself after Step 5 of setup, and let me know immediately
if anything fails — we'll fix it together.

---

## Database backups

Back up your database regularly — this is real money data.

```bash
docker compose exec db pg_dump -U postgres tictactoe_bet > backup_$(date +%Y%m%d).sql
```

Copy these backup files off the server periodically (e.g. download to your phone/laptop).

---

## If something breaks

1. Check logs first: `docker compose logs -f api` or `docker compose logs -f bot`
2. Most errors will show a clear Python error message pointing to the file and line
3. Bring the exact error message when asking for help debugging
