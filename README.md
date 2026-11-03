# Seatbelt

A safety layer between AI agents and PayPal payments. (Work in progress, built for the PayPal AI Hackathon.)

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env              # macOS/Linux: cp .env.example .env
```

## Verify

```bash
pytest
python scripts/smoke_test.py
```

## Configuration

All settings come from environment variables or `.env`; see `.env.example`.
The project targets the PayPal sandbox and refuses `PAYPAL_ENV=live` unless `ALLOW_LIVE=true`.