---
title: Kirtikar API
emoji: 🏺
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: true
short_description: Always-on backend for the kirtikar.me demo
---

<!--
The block above is Hugging Face Space metadata and must stay at the very top
of this file: a Docker Space reads `app_port` from it to decide which port to
route to, and the Space will not build without it. It is inert everywhere
else, including in this repository.
-->

# Listing Factory Backend

The **Listing Factory** is a single FastAPI service powering the seller-side publishing portal for marginalized artisans.

> **Architecture Context**: This system is **not** an e-commerce marketplace; orders and payments are handled externally via ONDC. This backend service manages the middle-tier publishing lifecycle pipeline (local queue sync, image/speech station integration, listing/fact-sheet generation, price advisory, confidence evaluation, artisan review/approval, and ONDC publishing).

---

## Prerequisites

- Python 3.10+ (or [uv](https://docs.astral.sh/uv/))
- PostgreSQL — for staging and production. **Not needed for local development:**
  set `DATABASE_URL` to the SQLite file below and everything, migrations included,
  runs with no database server installed.

---

## Getting Started

### 1. Environment Setup

Create and activate a virtual environment:

```bash
cd backend

# Using standard venv:
python3 -m venv .venv
source .venv/bin/activate

# Or using uv:
uv venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
# Or with uv:
uv pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Review and adjust variables in `.env` as needed for your local environment (e.g. database connection string, secrets, CORS origins).

#### Choosing a database

`DATABASE_URL` decides where data goes, and there is no automatic fallback: point
it at a server that is not running and every request fails with a 500.

```bash
# Local development, no server to install or keep running:
DATABASE_URL="sqlite:///./local_dev.db"

# Staging / production:
DATABASE_URL="postgresql+psycopg2://USER:PASSWORD@HOST:5432/listing_factory"
```

Set it in `.env` rather than exporting it in a shell. A value that exists only in
one terminal is lost the moment that terminal or the server is restarted, and the
API then silently falls back to whatever `.env` says.

Create or update the schema with `alembic upgrade head` (see
[Database Migrations](#database-migrations-alembic)). Run it against SQLite too:
the schema is never created implicitly at startup.

---

## Running the Application

Start the local development server with Uvicorn:

```bash
uvicorn app.main:app --reload
```

The service will run at `http://127.0.0.1:8000`.

### Interactive API Documentation

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI JSON**: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

---

## API Endpoints (v1 Contract)

All business endpoints live under `/api/v1` and currently return deterministic contract stubs.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health check |
| `POST` | `/api/v1/auth/firebase` | Authenticate with Firebase ID token and obtain application JWT |
| `GET` | `/api/v1/seller` | Fetch authenticated seller profile (Bearer token) |
| `PUT` | `/api/v1/seller` | Update profile fields (name, language, cluster) for authenticated seller |
| `POST` | `/api/v1/listings` | Create / queue a new listing item |
| `GET` | `/api/v1/listings` | List seller listings |
| `GET` | `/api/v1/listings/{listing_id}` | Get specific listing details |
| `POST` | `/api/v1/listings/{listing_id}/media` | Multipart upload for media (`image` / `audio`) |
| `GET` | `/api/v1/listings/{listing_id}/status` | Get listing processing state in pipeline |
| `GET` | `/api/v1/listings/{listing_id}/attention` | Fetch attention/intervention details |
| `GET` | `/api/v1/listings/{listing_id}/readback` | Fetch generated details for read-back review |
| `POST` | `/api/v1/listings/{listing_id}/approval` | Submit artisan review approval/correction |
| `GET` | `/api/v1/listings/{listing_id}/suggestions` | Fetch suggested additions |
| `POST` | `/api/v1/listings/{listing_id}/suggestions/{suggestion_id}/approval` | Approve or reject an individual suggestion |
| `POST` | `/api/v1/listings/{listing_id}/consent` | Record consent for publishing artisan photo & story |
| `POST` | `/api/v1/listings/{listing_id}/publish` | Trigger listing publication |
| `GET` | `/api/v1/listings/{listing_id}/preview` | Fetch read-only listing preview |
| `POST` | `/api/v1/voice/demo` | Interactive Voice-to-Catalog multimodal demonstration endpoint |

### Key Contract Enums

- **`ListingState`**: `queued`, `processing`, `needs_attention`, `ready`, `published`
- **`MediaType`**: `image`, `audio`

---

## 🎙️ Multimodal Voice-to-Catalog CLI Tool

You can test the entire multimodal cataloging pipeline directly from the command line using [`test_voice_cli.py`](file:///home/kaustubh/Desktop/codes/SIH-090-Project-Ctrl-Alt-Delete-main/backend/test_voice_cli.py):

```bash
# 1. Test with an existing voice recording (.wav, .mp3, .m4a) and export JSON:
python3 test_voice_cli.py --file /path/to/voice_note.wav --output listing.json

# 2. Record live speech from your microphone for 10 seconds:
python3 test_voice_cli.py --record --seconds 10

# 3. Test with the built-in synthetic craft sample:
python3 test_voice_cli.py
```

---

## Persistent Domain Models

The persistence layer defines six core SQLAlchemy 2.x domain tables registered with `Base.metadata`:

1. **`sellers`**: Artisan profiles (`id`, `name`, `language`, `cluster`, `ondc_seller_id`, timestamps).
2. **`listings`**: Core publishing items (`id`, `seller_id`, `client_item_id`, `state`, timestamps) with unique `(seller_id, client_item_id)`.
3. **`media`**: Metadata for uploaded photos and voice notes (`id`, `listing_id`, `media_type`, `storage_path`, timestamps).
4. **`listing_consents`**: Seller consent decisions (`photo_consent`, `story_consent`, timestamps) with unique `listing_id`.
5. **`suggestions`**: AI/system proposed additions (`field`, `value`, `reason`, `approved`, timestamps).
6. **`listing_approvals`**: Seller approval records after read-back review (`approved`, `approved_at`, timestamps) with unique `listing_id`.

> **Persistence Status**: Core authentication, seller profiles, media uploads, and listing state management are persisted in PostgreSQL. Downstream AI generation endpoints (`readback`, `suggestions`, `consent`, `preview`) operate on persisted listing entities while returning contract stubs until integrated with asynchronous background pipeline processing.

---

## Database Migrations (Alembic)

Database schema migrations are managed via Alembic in `backend/alembic/versions/`. Domain models are registered via `app.models` onto `Base.metadata`.

**Migrations must run on SQLite as well as PostgreSQL.** SQLite cannot `ALTER` a
constraint in place, so any migration that adds or drops one has to go through
`op.batch_alter_table`, which rebuilds the table; `env.py` also sets
`render_as_batch` for SQLite so autogenerated migrations do the same. Without
this, `alembic upgrade head` aborts part way and leaves a **partly built schema**
that looks fine — the API starts, then fails per request on the first column the
aborted migration never added. `tests/test_migration_sqlite.py` guards both the
chain and the resulting schema.

### Running Migrations

To apply migrations against a live database:

```bash
alembic upgrade head
```

To generate static SQL for offline review or execution (without connecting to PostgreSQL):

```bash
alembic upgrade head --sql
```

To downgrade schema changes:

```bash
alembic downgrade base
```

---

## Running Tests

Run the full regression test suite with pytest (**160 / 160 passed - 100%**):

```bash
pytest -v
```

Run just the pipeline and publishing test suite:

```bash
pytest tests/test_pipeline.py tests/test_publishing.py -v
```

Tests run independently without requiring a running PostgreSQL instance or live API keys (using in-memory SQLite and deterministic synthetic fallbacks).

---

## 🎨 AI/ML Subsystems Integration

> 📖 **Complete Technical Handover**: For an in-depth walkthrough of the ONNX models, OpenCV gatekeeper, 3 output asset generation, audio ingestion modes, and Mermaid architecture diagrams, see [**`HANDOVER_VISION_VOICE.md`**](HANDOVER_VISION_VOICE.md).

### 1. Vision Station (`app/services/vision/`)
- **Engine**: `ImageStation` (powered by `isnet-general-use` ONNX segmentation).
- **Stage**: `app/services/pipeline/stages/image.py` (`ImageStage`).
- **Pipeline Flow**:
  1. **Quality Gatekeeper**: Evaluates blur via Laplacian variance ($\ge 30$) with Canny fallback, and lighting via Otsu ROI brightness (dark floor 55, bright ceiling 185).
  2. **Color Restoration**: Strips warm tungsten casts via Gray-World white balancing.
  3. **Background Removal**: Isolates handicraft foreground using IS-Net model weights in `app/services/vision/.models/`.
  4. **Studio Framing**: Centers product with $\le 1\text{px}$ error and scales to **80% canvas coverage** on a pure white background with a soft contact shadow.
  5. **Deliverables**: Produces $1024 \times 1024$ primary listing image (`_clean.jpg`), $256 \times 256$ thumbnail (`_thumb.jpg`), and transparent PNG cutout (`_cutout.png`).

### 2. Voice Station (`app/services/voice/`)
- **Engine**: `VoiceStation` calling Sarvam AI (`speech-to-text-translate` model `saaras:v3`).
- **Stage**: `app/services/pipeline/stages/speech.py` (`SpeechStage`).
- **Pipeline Flow**:
  1. Validates audio format, size, and applies storage path traversal guards.
  2. Ingests artisan speech in regional Indic dialects (Hindi, Marathi, Bengali, Hinglish, etc.).
  3. Direct neural translation into structured English transcript (`SpeechStageOutput`).
  4. Preserves deterministic synthetic fallback for offline test environments.

### 3. Fact Sheet Extraction (`app/services/llm/`)
- **Engine**: `GeminiExtractor` powered by Google Gemini Flash (`gemini-3.5-flash`).
- **Stage**: `app/services/pipeline/stages/fact_sheet.py` (`FactSheetStage`).
- **Pipeline Flow**:
  1. Grammar-constrained JSON decoding via native `response_schema` and `response_mime_type: "application/json"`.
  2. Extracts high-converting title, craft category, authentic materials, cultural backstory, and dominant colors.
  3. Identifies missing commercial fields (`missing_fields: ['dimensions', 'price']`) without hallucinating values.
  4. Transient error resilience with automated backoff retry on HTTP 503/429 spikes.

### 4. Fair Pricing Advisor (`app/services/pipeline/stages/price.py`)
- Automatically adopts stated price if the artisan explicitly mentioned it in the voice note.
- If price is omitted, generates market benchmark bounds (`recommended_price`, `min_price`, `max_price`).
- Flags missing values to generate suggestion DB records for artisan review.

### 5. Multi-Channel Syndication Adapters (`app/services/publishing/`)
All adapters implement the `PublishingAdapter` protocol with validation and publication contracts:
- **ONDC Adapter** (`app/services/publishing/ondc.py`): Formats canonical listing into Beckn protocol catalog items (`bpp_id`, `item_id`).
- **Meta Commerce Adapter** (`app/services/publishing/meta.py`): Formats canonical listing for WhatsApp Business Catalog and Facebook Shops.
- **Google Merchant Center Adapter** (`app/services/publishing/google.py`): Generates Content API for Shopping feeds with `identifier_exists: false` exemption for handmade Indian crafts.
