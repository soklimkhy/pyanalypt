# PyAnalypt - Analytics Platform

> **No code. No formulas. Just your data — cleaned, analyzed, and ready.**

---

## 📋 Table of Contents

1. [Why I Built This](#-why-i-built-this)
2. [What You Can Do](#-what-you-can-do)
3. [Tech Stack](#-tech-stack)
4. [Prerequisites](#-prerequisites)
5. [Quick Start (Local)](#-quick-start-local)
6. [Running with Docker](#-running-with-docker)
7. [Setting Up AI Analysis (Ollama)](#-setting-up-ai-analysis-ollama)
8. [Features](#-features)
9. [Project Structure](#️-project-structure)
10. [Related Documentation](#-related-documentation)
11. [Troubleshooting / FAQ](#-troubleshooting--faq)
12. [Roadmap](#-roadmap)
13. [Contributing](#-contributing)
14. [License](#-license)

---

## 🧭 Why I Built This

Most data tools require you to write code. That creates a wall between business people and their own data.

**PyAnalypt** tears that wall down.

I built this for **non-technical users** — business owners, analysts, managers, and anyone who works with data but doesn't write Python or SQL. The idea is simple: you bring your data, and PyAnalypt walks you through the entire journey from raw file to actionable insight — no code required.

The backend is built with Django and Python so it's robust and extensible — but the person using it never has to know that.

---

## 🗺️ What You Can Do

Here's a real-world example of what PyAnalypt is designed for:

> *You have a messy sales spreadsheet — missing customer names, duplicate orders, weird price values, and dates in three different formats. Normally you'd hand it to a developer or spend hours in Excel. With PyAnalypt, you upload the file, let the system find the problems, fix them with a click, run an AI summary, and export a clean report — all in minutes.*

The full workflow:

| Step | What happens |
|------|-------------|
| 1. **Import** | Upload CSV, Excel, JSON, or Parquet — up to any size your server allows |
| 2. **Inspect** | Instantly see a preview, column types, row count, and summary statistics |
| 3. **Find Issues** | Auto-detect missing values, duplicates, outliers, bad encodings, and whitespace |
| 4. **Clean** | Fix issues with simple operations — no formulas, no scripts |
| 5. **Transform** | Rename columns, filter rows, reshape structure |
| 6. **Analyze** | AI generates plain-English problem statements and patterns from your data |
| 7. **Export** | Download your clean dataset as CSV, Excel, JSON, or Parquet |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | Django 6 + Django REST Framework |
| Database | PostgreSQL 16 |
| Caching | Redis 7 |
| Data processing | Pandas, scikit-learn, PyArrow |
| File formats | openpyxl (Excel), PyArrow (Parquet), lxml (XML) |
| Authentication | JWT (SimpleJWT) + Google OAuth (django-allauth) |
| AI / LLM | Ollama (local, private — your data never leaves your machine) |
| Containerization | Docker + Docker Compose |

---

## ✅ Prerequisites

Before running locally, make sure you have the following installed:

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **PostgreSQL 14+** — [postgresql.org](https://www.postgresql.org/download/)
- **Redis** — [redis.io](https://redis.io/docs/getting-started/) (or use Docker)
- **Git** — [git-scm.com](https://git-scm.com/)
- **Ollama** *(optional, for AI analysis)* — [ollama.com](https://ollama.com/)

> If you just want to get up and running quickly, skip to [Running with Docker](#-running-with-docker) — it handles PostgreSQL and Redis for you automatically.

---

## 🐳 Quick Start with Docker Hub

If you want to try PyAnalypt without setting up a development environment or cloning the source code, you can pull the official pre-built images from Docker Hub.

**1. Pull the Images**
```bash
# Backend (Django)
docker pull limkhysok/pyanalypt:latest

# Frontend (Next.js)
docker pull limkhysok/pyanalypt-frontend:latest
```

**2. Repository Links**
- **Backend Repo**: [limkhysok/pyanalypt](https://hub.docker.com/repository/docker/limkhysok/pyanalypt/general)
- **Frontend Repo**: [limkhysok/pyanalypt-frontend](https://hub.docker.com/repository/docker/limkhysok/pyanalypt-frontend/general)

---

## 🚀 Quick Start (Local Development)

**1. Clone the repository**

```bash
git clone https://github.com/limkhysok/pyanalypt.git
cd pyanalypt
```

**2. Create and activate a virtual environment**

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure your environment**

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Minimum required values in `.env`:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgres://USER:PASSWORD@localhost:5432/pyanalyptdb
ALLOWED_HOSTS=localhost,127.0.0.1
```

> See [Environment Setup (`env.md`)](./env.md) for the full list of variables.

**5. Set up the database**

```bash
python manage.py migrate
```

**6. Create an admin account**

```bash
python manage.py createsuperuser
```

**7. Run the server**

```bash
python manage.py runserver
```

The API is now live at `http://localhost:8000/api/v1/`
The Django admin panel is at `http://localhost:8000/admin/`

---

## 🐳 Running with Docker Compose

The easiest way to run the full stack (Backend + Frontend + DB + Redis) using the pre-built Docker Hub images.

**1. Create a `docker-compose.yml`**

Create a file named `docker-compose.yml` and paste:

```yaml
services:
  backend:
    image: limkhysok/pyanalypt:latest
    ports:
      - "8000:8000"
    environment:
      - DEBUG=True
      - SECRET_KEY=your-secret-key
      - DATABASE_URL=postgres://postgres:password@db:5432/pyanalyptdb
    depends_on:
      - db
      - redis

  frontend:
    image: limkhysok/pyanalypt-frontend:latest
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1/

  db:
    image: postgres:16
    environment:
      - POSTGRES_DB=pyanalyptdb
      - POSTGRES_PASSWORD=password

  redis:
    image: redis:7
```

**2. Start all services**

```bash
docker compose up -d
```

**3. Initial Setup**

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

**Stop all services**

```bash
docker compose down
```

---

## 🤖 Setting Up AI Analysis (Ollama)

The AI analysis feature (`analyze_issues`) runs entirely **locally** using Ollama — your data never gets sent to any external API.

**1. Install Ollama**

Download from [ollama.com](https://ollama.com/) and follow the installer for your OS.

**2. Pull the AI model**

```bash
ollama pull qwen2.5:7b
```

> This downloads the model (~4.5 GB). You only need to do this once. You can swap to any other Ollama-compatible model by changing `OLLAMA_MODEL` in your `.env`.

**3. Start Ollama**

```bash
ollama serve
```

Ollama runs at `http://localhost:11434` by default. That's all — PyAnalypt will connect to it automatically.

**4. Test it**

Once your server is running, send a POST request to:

```
POST /api/v1/datasets/{id}/analyze_issues/
```

And you'll get back plain-English problem statements about your dataset.

---

## ✨ Features

- **Dataset Management** — Upload, preview, paginate, and manage datasets in CSV, Excel, JSON, and Parquet formats.
- **Automated Issue Diagnostics** — Auto-detects missing values, duplicate rows, outliers, whitespace inconsistencies, and mojibake (broken text encodings).
- **Data Cleaning Suite** — Fill NAs, clip outliers, drop rows/columns, rename columns, fix encodings, and more — all via API.
- **AI-Powered Analysis** — Local LLM (via Ollama) reads your column metadata and generates 3–5 plain-English problem statements and analysis goals.
- **Flexible Export** — Download your dataset in any supported format after cleaning.
- **Authentication** — JWT-based login with email verification. Google OAuth for one-click sign-in.
- **Fully Documented API** — Every endpoint is documented in [`API_DOCS.md`](./API_DOCS.md).

---

## 🏗️ Project Structure

```
pyanalypt/
├── config/              # Django settings, WSGI, ASGI, and main URLs
├── apps/                # Core business logic
│   ├── core/            # Pandas data engine, summary stats, Ollama client
│   ├── datasets/        # Dataset upload, preview, export, AI analysis
│   ├── issues/          # Data anomaly detection and reporting
│   ├── cleaning/        # Data transformation operations
│   └── users/           # Custom AuthUser, JWT auth, Google OAuth
├── .env                 # Environment variables (never commit this)
├── Dockerfile           # Docker image configuration
├── docker-compose.yml   # Multi-container orchestration (Django + PostgreSQL + Redis)
├── manage.py            # Django management script
├── requirements.txt     # Python dependencies
└── API_DOCS.md          # Full API endpoint documentation
```

---

## 📚 Related Documentation

| Document | What it covers |
|----------|---------------|
| 📖 [API_DOCS.md](./API_DOCS.md) | All endpoints with request/response examples |
| ⚙️ [env.md](./env.md) | Full list of environment variables and how to set them |
| 🗺️ [mermaid_live.md](./mermaid_live.md) | Database schema diagrams and architecture maps |
| 🚀 [plans.md](./plans.md) | Planned features and project milestones |

---

## ❓ Troubleshooting / FAQ

**"Invalid line" warnings when starting the server**

Your `.env` file has a line that isn't in `KEY=VALUE` format. Check for comments without `#`, blank lines with spaces, or encoding issues. Each line must follow `KEY=value` exactly.

---

**Database connection error on startup**

Make sure PostgreSQL is running and the `DATABASE_URL` in your `.env` matches your actual database credentials and host. If using Docker, make sure you ran `docker compose up` first.

---

**Emails aren't being sent (verification link not arriving)**

If `EMAIL_HOST_USER` is not set in `.env`, PyAnalypt defaults to printing emails to your terminal console. Check the terminal where `runserver` is running — the verification link will be printed there.

---

**AI analysis returns "Failed to connect to Ollama"**

- Make sure Ollama is running: `ollama serve`
- Make sure you've pulled the model: `ollama pull qwen2.5:7b`
- Check `OLLAMA_API_URL` in `.env` (default: `http://localhost:11434/api/generate`)

---

**Google OAuth login isn't working**

- Make sure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` are set in `.env`
- Ensure the redirect URI in your Google Cloud Console matches exactly what's in your `.env`
- A `Site` object must exist in the Django admin (`/admin/sites/site/`) with `id=1`

---

**What file formats are supported?**

Upload and export: **CSV, Excel (.xlsx), JSON, Parquet**

---

**Is there a file size limit?**

By default Django has no hard file size limit, but your server's available memory sets the practical limit for Pandas to process the file. For most business datasets (under 100 MB), this is not an issue.

---

## 🚀 Roadmap

A short look at what's planned. Full details in [plans.md](./plans.md).

- [ ] Frontend dashboard (React) — drag-and-drop UI for all features
- [ ] Column-level transformation history and undo
- [ ] Scheduled dataset refresh from external sources (Google Sheets, S3)
- [ ] Advanced AI insights — trend detection, anomaly scoring
- [ ] Multi-user workspaces and dataset sharing
- [ ] REST API client SDK (Python + JavaScript)

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to your branch: `git push origin feat/your-feature`
5. Open a pull request

Please follow conventional commit format (`feat:`, `fix:`, `docs:`, etc.) in your commit messages.

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](./LICENSE) for details.
