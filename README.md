# Portfolio

Sahib Nanda's portfolio, in one repository with two apps:

| App | Stack | Purpose |
| --- | --- | --- |
| `backendPortfolio/` | Python 3.14t (free-threaded), FastAPI, gunicorn + uvicorn (uvloop, httptools), SQLite, Groq | Portfolio data API and the AI chat |
| `frontendPortfolio/` | Astro 7, React 19 (chat only), Tailwind CSS 4, TypeScript | The portfolio site |

The frontend is built from the backend's data: at build time it fetches `/details/*` and renders every section as static HTML. In the browser, it refreshes the live stats once per visit and runs the AI chat against the same API.

## Backend (`backendPortfolio/`)

Run every command from `backendPortfolio/`, using the free-threaded interpreter in `venv/`.

**Configuration:** every setting lives in `main/config/config.yaml`. Only secrets come from the environment, and all of them are required:

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEYS` | One or more comma-separated Groq keys |
| `MAIL_ACCOUNT_1_USERNAME`, `MAIL_ACCOUNT_1_PASSWORD`, `MAIL_ACCOUNT_2_USERNAME`, `MAIL_ACCOUNT_2_PASSWORD` | The SMTP accounts the mailer sends from (for Gmail, app passwords), one pair per entry under `mail.accounts`. Each mail picks them in a random order and fails over to the others. |
| `RECIPIENT_MAIL` | The one inbox every mail is sent to (yours) |

**Local development with `.env`:** put the variables above in `backendPortfolio/.env` (gitignored), one `NAME=value` per line, and run the server. `create_app()` and `gunicorn.conf.py` load that file first. It never overrides a variable that's already exported, and it's skipped when the file is missing, so production just sets real environment variables and needs no `.env`. Don't leave a variable blank in `.env`: a blank value counts as set and fails validation.

```bash
cd backendPortfolio
venv/bin/uvicorn main.app:create_app --factory --loop uvloop --http httptools --reload --port 8080
```

**Run (production, real environment variables):**

```bash
GROQ_API_KEYS="gsk_key1,gsk_key2" venv/bin/gunicorn -c gunicorn.conf.py                                   # production
GROQ_API_KEYS="gsk_..." venv/bin/uvicorn main.app:create_app --factory --loop uvloop --http httptools --reload --port 8080   # development
```

The API docs are at http://localhost:8080/docs.

**Test:**

```bash
venv/bin/python -m pytest --cov=main --cov-branch   # offline suite, 100% coverage target
venv/bin/python -m pytest -m live                    # opt-in tests against the real LeetCode, Codeforces, GitHub and Groq APIs
                                                     # the mail live test needs MAIL_ACCOUNT_1_* and RECIPIENT_MAIL
```

**Design notes:**
- Each package documents itself in its `__init__.py` docstring.
- Every response is an envelope: `{status, timestamp, data}` on success, `{status, timestamp, error, message, details}` on error.
- Rate limits are per IP, per session and global, configured under `rate_limit` in `config.yaml`.
- **Profile photo:** `/details/profile` returns `profile_image_url` (`/details/profile/image?v=<hash>`). That endpoint serves the photo from `main/package/static/pfp.jpg` with an ETag, 304 support and one-year immutable caching, and **no rate limit**. The frontend downloads it once at build time and ships optimized AVIF/WebP copies, a circular favicon and an Apple touch icon, so visitors never fetch it from the API.
- **Résumé:** `/details/professional` returns `resume_link` (`/details/resume?v=<hash>`). That endpoint serves `main/package/static/resume.pdf` inline (`Content-Disposition: inline; filename="Sahib_Nanda_Resume.pdf"`) with the same ETag, 304 support, one-year immutable caching and **no rate limit**. To update the résumé, replace the PDF and deploy: the hash, and so the link, changes with it.
- **Portfolio Agent (for `/cli`):** `POST /chats/{id}/agent/stream {message}` answers in at most one Groq call, often none, configured under `agent` in `config.yaml`:
  - A rule-based pre-check refuses known injection patterns at 0 tokens, and keywords pick which context sections to send.
  - First-turn questions are cached for 6 hours, so repeats cost 0 tokens.
  - One streamed `gpt-oss-20b` call (reasoning "low", at most 600 tokens) both answers and flags off-topic questions with a marker. The server swaps the marker for the configured fallback before the visitor sees it.
  - A daily token budget returns 503 `AGENT_BUDGET_EXHAUSTED` once it's used up.
  - It sends `step` events before the tokens and has its own `agent_message` rate limit. Chats carry an `origin` (`chat` or `cli`), so both UIs share one history.
- **Contact me:** `POST /contact {email, subject, message}` mails the message to `RECIPIENT_MAIL` through a random SMTP account from `mail.accounts`, failing over to the others, with Reply-To set to the visitor. Nothing is stored. The visitor's email is validated (syntax plus a DNS mail check) and normalized (trimmed, lowercased), and the response echoes it as `reply_to`. It's limited to 3 per hour per IP and 50 per day overall.
- It runs as one gunicorn worker with a large thread pool. The rate limiter and caches are in memory, and the GIL is disabled, so one process uses every core.

## Frontend (`frontendPortfolio/`)

Run every command from `frontendPortfolio/`.

**Configuration:** each deployment sets these as environment variables, or in a local `.env`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `PUBLIC_BACKEND_BASE_URL` | yes | The backend's base URL, for example `http://localhost:8080` or `https://api.sahibnanda.net`. Change it per deployment without touching code. |
| `PUBLIC_SITE_URL` | no | The public site URL, used for the canonical and Open Graph tags. |

The site is static, so both values are read **at build time**. Astro's `astro:env` schema validates them, and a missing or malformed URL fails the build. On Cloudflare Pages, Vercel or Netlify, changing the variable and redeploying (which rebuilds) is enough. The backend must be reachable during the build.

**Commands:**

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server (backend must be running) |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the built site on :4321 |
| `npm run check` | `astro check` (types) + Biome (lint and format) |
| `npm run format` | Apply Biome fixes |
| `npm test` | Vitest unit tests: API client, SSE stream parser, session store, chat reducer, formatting, CLI commands, autocomplete, markdown, terminal reducer |
| `npm run test:e2e` | Playwright on desktop and mobile with a mocked API: sections, ⌘K chat streaming, 401 renewal, 429 countdown, stop, reduced motion, the `/cli` terminal |
| `npm run test:dev` | Smoke test against `astro dev` (catches dev-only breakage, e.g. the chat island's React refresh preamble) |

**Structure:**
- `src/pages/index.astro`: the single page, composed from the build-time snapshot (`src/content/snapshot.ts`).
- `src/components/sections/`: static sections (hero, experience, projects, competitive programming, open source, skills, achievements, off the clock, contact).
- `src/components/islands/chat/`: the chat panel, a React island loaded by `src/scripts/chatLauncher.ts` on ⌘K or a click.
- `src/pages/cli.astro` and `src/components/islands/cli/`: the **Portfolio Agent CLI**, a Claude Code-style terminal opened from the chat panel or the `>_` link in the nav.
  - **Skills:** every skill (slash command) is declared once in the backend's `main/package/static/cli.json` and served by `GET /details/cli`. The UI reads it at build time and runs each skill locally (0 tokens). The agent gets it through the SITE context, so it can answer questions like "how many skills are in this cli?". A unit test keeps the frontend fixture in sync with the backend file.
  - **Plugins:** `core`, `portfolio`, `stats`, `agent` and `extras` (`/neofetch`, `/fortune`; off by default), managed with `/plugins enable|disable <name>`.
  - **`/config`:** an interactive panel, or `/config <key> <value>`. It sets the mode, answer length (concise/detailed), autocomplete, the AI-cost line, the accent colour and animations, saved per browser.
  - **Modes:** Shift+Tab cycles default → ⏵⏵ auto-run (the agent plans commands and runs them) → ⏸ plan mode (it shows the plan; Enter runs it, Esc cancels). Phones get a mode chip.
  - **The AI knows where it is:** prompts carry the surface (chat panel or CLI), so answers in the terminal point to commands.
  - **Other features:** a slash menu with Tab/→ completion and ghost text, ↑↓ history, Esc/Ctrl+C to stop, Ctrl+L to clear, and terminal conversations reopening from the chat's ☰ history. A safe markdown subset renderer (React elements only, http/https/mailto links) lives in `src/lib/cli/`.
- `src/lib/api/`: a typed client. Every response is validated with zod at runtime. Errors become `ApiError`, which carries the backend's status, code and `Retry-After`.
- `src/scripts/`: small vanilla scripts: the hero WebGL shader (ogl), reveals, count-ups, smooth scroll (Lenis), live stats, skill highlighting, and the rating chart (uPlot).

**Performance and accessibility:**
- Only about 10 KB of JS (gzipped) is on the critical path. The shader, chart, data refresh and chat all load lazily.
- Lighthouse scores 100/100/100/100 on desktop and 98/100/100/100 on mobile.
- Reduced motion turns off the shader animation, smooth scroll and reveals.
- The chat is a native `<dialog>`, so it traps focus and closes on Escape.

## Local development, end to end

```bash
cd backendPortfolio && GROQ_API_KEYS="gsk_..." venv/bin/uvicorn main.app:create_app --factory --port 8080
cd frontendPortfolio && echo "PUBLIC_BACKEND_BASE_URL=http://localhost:8080" > .env && npm run dev
```

## CI and contributing

- **CI** (`.github/workflows/ci.yml`) runs only on pull requests. There's no rerun after merging: `main` only accepts PRs whose checks passed on a branch already up to date with it.
  - **backend:** installs the free-threaded Python 3.14t, asserts the GIL is disabled, and runs the full pytest suite with 100% branch coverage enforced.
  - **frontend:** runs `npm ci`, the type check and lint, the Vitest unit tests, a build against a fixture API (`frontendPortfolio/tests/support/mockBackend.mjs`, serving `tests/fixtures/api/*.json`), and the Playwright e2e tests. The Playwright report is uploaded when it fails.
- **`main` is protected** by a repository ruleset:
  - no direct pushes, force-pushes or deletion;
  - every change goes through a pull request;
  - a PR needs one approval from a code owner (`.github/CODEOWNERS`) and both `backend` and `frontend` checks passing on an up-to-date branch.

  As an admin, the owner can merge their own PRs through the pull request (GitHub doesn't allow approving your own PR), but can't push to `main` directly.
- **Refreshing the CI fixtures** after the portfolio data changes: run the backend locally, then save the `data` field of each `/details/<name>` response into `frontendPortfolio/tests/fixtures/api/<name>.json`. Leave out `physical_appearance` and `basic_info` from `personality.json`.

## Deployment

Live at **https://portfolio-sahib-nanda.duckdns.org**, with the API at **https://api.portfolio-sahib-nanda.duckdns.org**. Both run on one Oracle Cloud VM (Ubuntu 26.04, x86_64, 1 GB RAM plus 2 GB swap).

- **Server:**
  - Caddy terminates HTTPS with automatic Let's Encrypt certificates, serves the static frontend from `/opt/portfolio/frontend`, and proxies the API to `127.0.0.1:8080`.
  - The backend runs as the sandboxed `portfolio` user under systemd (`portfolio-backend.service`): gunicorn with one uvloop/httptools worker on free-threaded Python 3.14.8t, installed by `uv` in `/opt/portfolio/python`.
  - Secrets live in the root-only `/etc/portfolio/backend.env`; the SQLite store in `/var/lib/portfolio`.
- **Releases:**
  - Each deploy uploads to `/opt/portfolio/releases/<sha>-<time>` (backend, with its own venv) and `/opt/portfolio/frontend-releases/<sha>-<time>`. `portfolio-activate` switches the `current` and `frontend` symlinks.
  - The backend is health-checked, and an unhealthy release is rolled back automatically. The last 3 releases of each are kept.
- **CD** (`.github/workflows/deploy.yml`): every merge to `main` (or a manual run from the Actions tab) runs these steps in order:
  1. ship the committed `backendPortfolio` and build its venv on the VM;
  2. refresh the env file from GitHub secrets;
  3. activate and health-check the backend;
  4. build the frontend against the live API and activate it;
  5. smoke-test both public URLs.

  Deploys run one at a time and are never cancelled midway.
- **GitHub configuration:**
  - secrets `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` (the VM's pinned host keys), `DEPLOY_HOST` and `DEPLOY_USER`, plus the backend variables from `.env`;
  - repository variables `PUBLIC_BACKEND_BASE_URL` and `PUBLIC_SITE_URL`.

  To rotate a secret, update it in GitHub, then rerun the Deploy workflow.
- **Rebuilding the server:** `deploy/setup-server.sh` is the idempotent one-time setup: swap, Caddy, uv with Python 3.14t, the service user, the systemd unit, the activation script and the Caddyfile. Run it with `sudo bash setup-server.sh` on a fresh VM with `uv` installed for `ubuntu`, then run the Deploy workflow.
