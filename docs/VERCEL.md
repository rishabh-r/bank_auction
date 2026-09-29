# Deploying the portal to Vercel

A free way to put the site on the internet so other people can look at it.

---

## What can and cannot go on Vercel

Vercel runs **serverless functions**: short-lived, no permanent disk. That
suits the website and rules out the collector.

| Piece | Vercel? | Why |
|---|---|---|
| Web portal, JSON API | **Yes** | Read-only, touches no files |
| PostgreSQL | No | Vercel has no database; use Neon |
| Collector and scheduler | **No** | One crawl runs over an hour; functions get seconds |
| Raw document archive | No | No persistent filesystem |

So the shape is:

```
   Vercel  ── reads ──>  Neon (PostgreSQL)  <── writes ──  collector
   the website                                             (your laptop,
                                                            or a VPS later)
```

The collector keeps running wherever you run it and writes to the same
hosted database the website reads from. Your laptop being off stops new
listings arriving; it does not take the site down.

---

## 1. Create the database (Neon, free)

1. Sign up at [neon.tech](https://neon.tech) and create a project.
   Choose the **Singapore** or **Mumbai** region — closest to both your
   users and Vercel's Asian edge.
2. Copy the connection string. Take the **pooled** one, whose host
   contains `-pooler`. It looks like:

   ```
   postgresql://user:pass@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

3. Change the scheme so SQLAlchemy uses psycopg 3:

   ```
   postgresql+psycopg://user:pass@ep-xxx-pooler.../neondb?sslmode=require
   ```

Keep that string somewhere safe. It is a password.

## 2. Create the schema and load data

From your machine, pointing at Neon rather than the local database:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://...your neon url..."

.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m auction_portal crawl baanknet --limit 500
```

That creates the tables and puts real listings in them. The crawl takes
about 25 minutes at 500 URLs.

> Setting `DATABASE_URL` this way only affects that one PowerShell
> window. Close it and you are back on the local database.

## 3. Push to GitHub

If the repository has no remote yet:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git branch -M main
git push -u origin main
```

Nothing sensitive is committed — `.env`, `data/`, `.pgsql/` and `logs/`
are all ignored. Check with `git status` before pushing if you want to be
sure.

## 4. Connect Vercel

1. Go to [vercel.com](https://vercel.com), sign in with GitHub.
2. **Add New → Project**, and pick the repository.
3. Leave the framework preset as **Other**. `vercel.json` already tells
   Vercel what to do.
4. Before deploying, open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | your Neon pooled connection string |
   | `CONTACT_EMAIL` | a real address you monitor |
   | `CONTACT_URL` | `https://your-project.vercel.app/bot` |
   | `DB_SERVERLESS` | `true` |
   | `ENVIRONMENT` | `production` |

   `DB_SERVERLESS=true` matters. Without it each function instance holds
   a connection pool and Neon's connection limit is reached quickly.

5. **Deploy**. The first build takes two or three minutes.

## 5. Check it

Visit your `https://your-project.vercel.app`. Then:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_check.py https://your-project.vercel.app
.\.venv\Scripts\python.exe scripts\verify_manual.py https://your-project.vercel.app
```

Both run against the deployed site, so they check the real thing rather
than your laptop.

---

## Keeping it updated

The website is now public but **static in content** — it shows whatever
is in Neon. To add listings, run the collector against Neon:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://...your neon url..."
.\.venv\Scripts\python.exe -m auction_portal schedule
```

Leave that running and the live site keeps gaining listings. Close it and
the site stays up, simply stops growing.

Pushing to GitHub redeploys the site automatically. The database is
untouched by deployments.

---

## When to stop using this arrangement

It is a good way to show people the portal. It is not the final shape,
for one reason: **the collector depends on someone's laptop**. That is
fine for testing and wrong for a service people pay for.

The fix is a small VPS, around ₹800–2,000 a month, running
`docker-compose.yml` — website, database and collector together, always
on. See [DEPLOYMENT.md](DEPLOYMENT.md). At that point Vercel and Neon can
either stay as the public face or be dropped entirely.

---

## Things that will bite you

**Cold starts.** An idle Vercel function sleeps. The first visit after a
quiet spell takes a few seconds. Normal, and free tiers cannot avoid it.

**Free tier limits.** Neon's free tier suspends the database after
inactivity and has a storage cap. Enough for testing, not for a launch.

**The 90-day retention job will not run**, because the scheduler is not
on Vercel. Run `maintain` occasionally against Neon, or move the
collector to a server.

**Do not put the legal review off.** A site on the public internet with a
real domain is materially different from a laptop nobody can reach. See
Part E of the main document.
