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
| `npm test` | Vitest unit tests: API client, SSE stream parser, session store, chat reducer, formatting |
| `npm run test:e2e` | Playwright on desktop and mobile with a mocked API: sections, ⌘K chat streaming, 401 renewal, 429 countdown, stop, reduced motion |

**Structure:**
- `src/pages/index.astro`: the single page, composed from the build-time snapshot (`src/content/snapshot.ts`).
- `src/components/sections/`: static sections (hero, experience, projects, competitive programming, open source, skills, achievements, off the clock, contact).
- `src/components/islands/chat/`: the chat panel, a React island loaded by `src/scripts/chatLauncher.ts` on ⌘K or a click.
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

- **CI** (`.github/workflows/ci.yml`) runs on every pull request and every push to `main`:
  - **backend:** installs the free-threaded Python 3.14t, asserts the GIL is disabled, and runs the full pytest suite with 100% branch coverage enforced.
  - **frontend:** runs `npm ci`, the type check and lint, the Vitest unit tests, a build against a fixture API (`frontendPortfolio/tests/support/mockBackend.mjs`, serving `tests/fixtures/api/*.json`), and the Playwright e2e tests. The Playwright report is uploaded when it fails.
- **`main` is protected** by a repository ruleset:
  - no direct pushes, force-pushes or deletion;
  - every change goes through a pull request;
  - a PR needs one approval from a code owner (`.github/CODEOWNERS`) and both `backend` and `frontend` checks passing on an up-to-date branch.

  As an admin, the owner can merge their own PRs through the pull request (GitHub doesn't allow approving your own PR), but can't push to `main` directly.
- **Refreshing the CI fixtures** after the portfolio data changes: run the backend locally, then save the `data` field of each `/details/<name>` response into `frontendPortfolio/tests/fixtures/api/<name>.json`. Leave out `physical_appearance` and `basic_info` from `personality.json`.
