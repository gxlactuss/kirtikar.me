# Backend Technical Study Guide: SIH-090 Listing Factory

> **Audience**: Computer engineering student / junior backend engineer.  
> **Goal**: Provide a complete, rigorous, and code-accurate walkthrough of the entire backend so you can understand every line, debug issues independently, and rebuild this architecture from scratch without AI assistance.  
> **Single Source of Truth**: The active codebase at `backend/` in branch `feature/backend`.

---

## Table of Contents

1. [Section 1 — What This Backend Is](#section-1--what-this-backend-is)
2. [Section 2 — Architecture](#section-2--architecture)
3. [Section 3 — Complete Folder Tree](#section-3--complete-folder-tree)
4. [Section 4 — Every File Walkthrough](#section-4--every-file-walkthrough)
5. [Section 5 — FastAPI Implementation](#section-5--fastapi-implementation)
6. [Section 6 — Pydantic Validation & Schemas](#section-6--pydantic-validation--schemas)
7. [Section 7 — Database & SQLAlchemy 2.0 ORM](#section-7--database--sqlalchemy-20-orm)
8. [Section 8 — Alembic Migrations](#section-8--alembic-migrations)
9. [Section 9 — Authentication & Identity Architecture](#section-9--authentication--identity-architecture)
10. [Section 10 — Media Storage & File Streaming](#section-10--media-storage--file-streaming)
11. [Section 11 — Listing Lifecycle State Machine](#section-11--listing-lifecycle-state-machine)
12. [Section 12 — Deterministic Pipeline Runner](#section-12--deterministic-pipeline-runner)
13. [Section 13 — Test Suite Architecture](#section-13--test-suite-architecture)
14. [Section 14 — Configuration & Environment Settings](#section-14--configuration--environment-settings)
15. [Section 15 — Dependencies (Line-by-Line)](#section-15--dependencies-line-by-line)
16. [Section 16 — Runtime & Deployment Operations](#section-16--runtime--deployment-operations)
17. [Section 17 — Important Design Decisions](#section-17--important-design-decisions)
18. [Section 18 — How Everything Connects (End-to-End Scenarios)](#section-18--how-everything-connects-end-to-end-scenarios)
19. [Section 19 — Concepts You Need to Master (Syllabus)](#section-19--concepts-you-need-to-master-syllabus)
20. [Section 20 — "Can I Rebuild This?" Reconstruction Roadmap](#section-20--can-i-rebuild-this-reconstruction-roadmap)
21. [Section 21 — Structured Code Reading Map](#section-21--structured-code-reading-map)
22. [Section 22 — Self-Assessment Questions & Answers](#section-22--self-assessment-questions--answers)

---

## Section 1 — What This Backend Is

### 1.1 The High-Level Mission
The project is a **seller-side publishing portal** specifically engineered for marginalized rural artisans (such as Madhubani painters, terracotta potters, handloom weavers) who lack digital literacy, English fluency, or e-commerce cataloging skills.

The backend service is called the **Listing Factory**. It acts as an automated, multi-modal assembly line that ingests crude raw media (smartphone photos and vernacular voice notes) from an artisan's mobile device, extracts structured product attributes, drafts copy, recommends fair market pricing, validates confidence, presents human-in-the-loop review screens, and ultimately publishes the listing to decentralized commerce networks like **ONDC (Open Network for Digital Commerce)**.

### 1.2 System Boundaries: What the Backend Does vs. Does NOT Do
A critical engineering discipline is recognizing **system boundaries**:

* **What the Backend DOES Do**:
  1. Authenticates artisans via verified mobile phone numbers using Firebase Auth and issues session JWTs.
  2. Maintains persistent artisan profiles and product catalog records in PostgreSQL.
  3. Validates, streams, and secures uploaded raw media (photos and voice notes) on local storage.
  4. Enforces a strict, deterministic state machine governing product listing transitions (`queued` → `processing` → `needs_attention` ↔ `ready` → `published`).
  5. Orchestrates a 5-stage sequential processing pipeline (`ImageStage` → `SpeechStage` → `FactSheetStage` → `PriceStage` → `ConfidenceStage`) with isolated retry policies.
  6. Exposes RESTful endpoints for mobile clients to query pipeline status, review generated product copy, approve suggestions, and record explicit consent.
  7. Formats canonical listings and dispatches them to external commerce channels via adapter interfaces.

* **What the Backend DOES NOT Do**:
  1. **Not a consumer marketplace**: Consumers do not browse or buy items on this server. There is no shopping cart, consumer payment gateway (Razorpay/Stripe checkout for buyers), or order fulfillment tracking.
  2. **Not an SMS gateway**: The backend does not send SMS OTPs directly; mobile devices talk to Firebase Phone Auth to prove ownership of the phone number.
  3. **Not a frontend client**: The backend does not render HTML/CSS templates or manage client-side UI animations. It is a pure JSON API with multipart upload support.

### 1.3 Team & Ecosystem Boundaries

```
[ Artisan Mobile App ]  ──(Phone OTP)──► [ Firebase Auth ]
         │                                       │ (Verified ID Token)
         ├───────────────────────────────────────┼───────────────┐
         │                                       ▼               │
         │ (HTTP REST / JWT)             [ FastAPI Backend ]     │
         ▼                               (Listing Factory)       │
┌─────────────────────────┐                      │               │
│ • Local draft queue     │                      ├── Storage     │
│ • Camera / Audio record │                      ├── PostgreSQL  │
│ • Offline storage       │                      └── Pipeline    │
│ • Read-back playback    │                              │       │
└─────────────────────────┘                              ▼       │
                                                 [ ONDC Network ]◄┘
                                                 (Marketplace BAP/BPP)
```

1. **Where the Mobile App ends & Backend begins**:
   - The mobile app runs on the artisan's phone. It records audio notes in regional languages (e.g., Hindi, Maithili), captures product photos, and queues drafts locally if offline.
   - When network connectivity is established, the mobile app obtains a Firebase ID token via phone OTP, exchanges it with `POST /api/v1/auth/firebase` for a backend JWT, and pushes the drafts and media files to `/api/v1/listings`.

2. **Where AI/ML Teammates begin**:
   - In production, AI/ML models (vision models for craft categorization, Whisper/Conformer models for ASR speech-to-text, LLMs for copywriting, and market pricing regressors) will execute inside worker stations or external AI microservices.
   - The backend defines the **Pipeline Stage Contract** (`PipelineStage` Protocol, `PipelineContext`, `StageResult`). Currently, deterministic mock stages exist in `app/services/pipeline/stages/`. The ML teammates simply replace the internals of `run(context)` with real model inference calls without modifying the pipeline orchestrator or state machine.

3. **Where ONDC begins**:
   - ONDC is an open network connecting buyers and sellers via Beckn protocol. The backend's responsibility stops at creating a valid seller-side catalog item (`bpp/catalog`) and triggering publication via the `PublishingAdapter`. External ONDC Buyer Apps (Paytm, Mystore, Magicpin) handle consumer discovery, purchasing, and settlement.

### 1.4 The User / Listing Flow in Simple Terms
1. **Artisan logs in**: Enters phone number on mobile app, receives SMS OTP, taps verify. App is logged in.
2. **Artisan creates item**: Snaps 1 or 2 photos of a handmade saree or painting, presses a microphone button, and speaks for 20 seconds explaining the cloth, natural dyes, and village tradition. Taps "Upload".
3. **Factory processes**: The server receives photos and voice note. The pipeline analyzes the image, transcribes the voice note, generates an English/Hindi product title and description, suggests an initial price of ₹1,500, and checks confidence score.
4. **Artisan reviews (Human-in-the-loop)**: The app fetches the draft. The artisan listens to an audio read-back of the generated description. The artisan accepts or rejects optional AI suggestions (e.g., "Add material: Natural mineral pigments").
5. **Artisan consents**: The artisan checks boxes agreeing to display their personal photo and artisan story.
6. **Publish**: The artisan taps "Publish". The item is converted to ONDC format and published to the network.

### 1.5 The Technical Request Flow
1. `POST /api/v1/auth/firebase` with `{ "id_token": "<firebase_jwt>" }`. Verified by Firebase Admin SDK. Backend resolves or creates `sellers` row in PostgreSQL and returns an application JWT signed with `HS256`.
2. `POST /api/v1/listings` with `Authorization: Bearer <jwt>` and `{ "client_item_id": "<client_uuid>" }`. Creates a row in `listings` table with state `queued`. Idempotent on composite key `(seller_id, client_item_id)`.
3. `POST /api/v1/listings/{id}/media` with `multipart/form-data`. Streams chunks to disk at `media/<listing_id>/<uuid>.<ext>`, verifies MIME/size, and creates records in `media` table referencing `listing_id`.
4. `PipelineRunner.run(listing_id)` executes:
   - Sets state `queued` → `processing`.
   - Executes `ImageStage`: validates image media exists, sets `context.image_output`.
   - Executes `SpeechStage`: validates voice note exists, sets `context.speech_output`.
   - Executes `FactSheetStage`: combines vision + speech outputs into structured metadata.
   - Executes `PriceStage`: computes fair price range and recommendation.
   - Executes `ConfidenceStage`: validates all fields and scores quality (threshold >= 0.70).
   - If any check fails or is missing media, state halts at `needs_attention`.
   - If all stages succeed, state transitions to `ready`.
5. Mobile client polls `GET /api/v1/listings/{id}/status` and retrieves generated metadata via `GET /api/v1/listings/{id}/readback`.
6. Artisan submits review via `POST /api/v1/listings/{id}/approval` (`approved: true` keeps state `ready`; `approved: false` transitions back to `needs_attention`).
7. Artisan gives consent via `POST /api/v1/listings/{id}/consent`.
8. Artisan calls `POST /api/v1/listings/{id}/publish`. State machine transitions `ready` → `published` (terminal state).

---

## Section 2 — Architecture

### 2.1 High-Level Architecture Diagram

```
                        ┌─────────────────────────────────────────┐
                        │           Artisan Mobile App            │
                        └────────────────────┬────────────────────┘
                                             │ HTTP / Bearer JWT
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI HTTP Service                                    │
│                                                                                        │
│  ┌────────────────────┐     ┌─────────────────────┐     ┌───────────────────────────┐  │
│  │   Authentication   │     │  Input Validation   │     │     CORS Middleware       │  │
│  │  (HTTPBearer, JWT) │     │ (Pydantic Schemas)  │     │   (Configured Origins)    │  │
│  └─────────┬──────────┘     └──────────┬──────────┘     └─────────────┬─────────────┘  │
│            │                           │                              │                │
│            ▼                           ▼                              ▼                │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                  API Routers                                     │  │
│  │     /health   |   /api/v1/auth   |   /api/v1/seller   |   /api/v1/listings       │  │
│  └──────────────────────────────────────┬───────────────────────────────────────────┘  │
│                                         │                                              │
│                                         ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                 Service Layer                                    │  │
│  │                                                                                  │  │
│  │   ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────────┐   │  │
│  │   │    Auth Service    │   │  Listing Service   │   │  Media Storage Service │   │  │
│  │   │  (Identity sync,   │   │  (State machine,   │   │  (MIME checks, chunk   │   │  │
│  │   │   JWT issuance)    │   │   ownership checks)│   │   streaming, disk I/O) │   │  │
│  │   └─────────┬──────────┘   └─────────┬──────────┘   └───────────┬────────────┘   │  │
│  │             │                        │                          │                │  │
│  │             ▼                        ▼                          │                │  │
│  │   ┌──────────────────────────────────────────────┐              │                │  │
│  │   │           Pipeline Runner Subsystem          │              │                │  │
│  │   │                                              │              │                │  │
│  │   │  [Image] ➔ [Speech] ➔ [FactSheet] ➔ [Price] ➔│              │                │  │
│  │   │                     [Confidence]             │              │                │  │
│  │   └──────────────────────┬───────────────────────┘              │                │  │
│  │                          │                                      │                │  │
│  │                          ▼                                      │                │  │
│  │   ┌──────────────────────────────────────────────┐              │                │  │
│  │   │          Publishing Adapter Subsystem        │              │                │  │
│  │   │    PublishingAdapter Protocol ➔ ONDC Adapter │              │                │  │
│  │   └──────────────────────┬───────────────────────┘              │                │  │
│  └──────────────────────────┼──────────────────────────────────────┼────────────────┘  │
│                             │                                      │                   │
└─────────────────────────────┼──────────────────────────────────────┼───────────────────┘
                              │                                      │
                              ▼                                      ▼
               ┌──────────────────────────────┐       ┌──────────────────────────────┐
               │    PostgreSQL Persistence    │       │     Local Media Storage      │
               │   (SQLAlchemy 2.0 Models &   │       │   (Filesystem: ./media/...   │
               │      Alembic Migrations)     │       │     isolated per listing)    │
               └──────────────────────────────┘       └──────────────────────────────┘
```

### 2.2 Component Interaction & Data Flows

#### Flow 1: Authentication & Token Issuance
```
Client                 FastAPI Route          Auth Service          Firebase Admin SDK       PostgreSQL
  │                          │                     │                         │                    │
  │── POST /auth/firebase ──►│                     │                         │                    │
  │   { id_token }           │── authenticate ────►│                         │                    │
  │                          │                     │── verify_id_token ─────►│                    │
  │                          │                     │◄─ claims (uid, phone) ──│                    │
  │                          │                     │                                              │
  │                          │                     │── SELECT seller BY firebase_uid/phone ──────►│
  │                          │                     │◄─ (seller record or none) ───────────────────│
  │                          │                     │                                              │
  │                          │                     │── [If new] INSERT INTO sellers ─────────────►│
  │                          │                     │◄─ committed seller entity ───────────────────│
  │                          │                     │                                              │
  │                          │                     │── create_access_token(seller.id)             │
  │                          │◄─ (jwt, seller) ────│                                              │
  │◄─ 200 OK + JWT ──────────│                     │                                              │
```

#### Flow 2: Media Upload with Protection
```
Client                 Route (Upload)          MediaStorage Service           Filesystem         PostgreSQL
  │                          │                          │                         │                   │
  │── POST /{id}/media ─────►│                          │                         │                   │
  │   (multipart/form-data)  │── save_media_upload ────►│                         │                   │
  │                          │                          │── validate listing_id   │                   │
  │                          │                          │── validate MIME & ext   │                   │
  │                          │                          │── stream 64KB chunks ──►│                   │
  │                          │                          │   (check size <= 10MB)  │                   │
  │                          │◄─ StoredMediaResult ─────│                         │                   │
  │                          │                                                                        │
  │                          │── SELECT listing BY id ───────────────────────────────────────────────►│
  │                          │   [Ownership Check: db_listing.seller_id == current_seller.id]         │
  │                          │── INSERT INTO media (metadata, storage_path) ─────────────────────────►│
  │                          │◄─ commit OK ───────────────────────────────────────────────────────────│
  │◄─ 200 OK (uploaded) ─────│                                                                        │
  │                          │ [On DB Error: delete_stored_file() from disk to prevent orphans]       │
```

#### Flow 3: Deterministic Pipeline Execution
```
PipelineRunner               Stage Sequence                     Context                Database
      │                             │                              │                       │
      │── 1. Guard check ─────────────────────────────────────────────────────────────────►│
      │   (state must be queued or needs_attention)                                        │
      │── 2. Transition state ────────────────────────────────────────────────────────────►│
      │   (state = processing)                                                             │
      │                                                            │                       │
      │── 3. ImageStage.run() ─────►│                              │                       │
      │◄─ StageResult.ok ───────────│── save ImageStageOutput ────►│                       │
      │                                                            │                       │
      │── 4. SpeechStage.run() ────►│                              │                       │
      │◄─ StageResult.ok ───────────│── save SpeechStageOutput ───►│                       │
      │                                                            │                       │
      │── 5. FactSheetStage.run() ─►│                              │                       │
      │◄─ StageResult.ok ───────────│── save FactSheetOutput ─────►│                       │
      │                                                            │                       │
      │── 6. PriceStage.run() ─────►│                              │                       │
      │◄─ StageResult.ok ───────────│── save PriceStageOutput ────►│                       │
      │                                                            │                       │
      │── 7. ConfidenceStage.run() ►│                              │                       │
      │◄─ StageResult.ok ───────────│── save ConfidenceOutput ────►│                       │
      │                                                                                    │
      │── 8. All stages passed ───────────────────────────────────────────────────────────►│
      │   (state = ready)                                                                  │
      │                                                                                    │
      │ [If any stage returns needs_attention or retries exhausted:                        │
      │   Runner immediately halts loop and transitions listing state = needs_attention]   │
```

---

## Section 3 — Complete Folder Tree

Here is the exact source-controlled directory layout of `backend/`:

```
backend/
├── alembic/                               # Database migrations root
│   ├── env.py                             # Alembic runtime environment script
│   ├── script.py.mako                     # Template for generating new revision scripts
│   └── versions/                          # Schema revision scripts
│       ├── 0001_domain_tables.py          # Baseline migration: all 6 core domain tables
│       └── 0002_firebase_authentication.py # Migration: adds firebase_uid & phone_number
├── alembic.ini                            # Alembic CLI configuration
├── app/                                   # Application root package
│   ├── __init__.py                        # Application package marker
│   ├── main.py                            # ASGI app instantiation & router registration
│   ├── api/                               # HTTP Presentation Layer
│   │   ├── __init__.py                    # API package marker
│   │   ├── v1.py                          # Router aggregator for /api/v1 prefix
│   │   └── routes/                        # Concrete route modules
│   │       ├── __init__.py                # Routes package marker
│   │       ├── auth.py                    # POST /api/v1/auth/firebase
│   │       ├── health.py                  # GET /health
│   │       ├── listings.py                # CRUD, status, review, consent, publish
│   │       ├── media.py                   # POST /api/v1/listings/{id}/media upload
│   │       └── seller.py                  # GET & PUT /api/v1/seller profile
│   ├── core/                              # Cross-Cutting Infrastructure
│   │   ├── __init__.py                    # Core package marker
│   │   ├── config.py                      # Pydantic BaseSettings environment loader
│   │   ├── firebase.py                    # Firebase Admin SDK verification service
│   │   ├── phone.py                       # E.164 phone normalization utilities
│   │   └── security.py                    # Application JWT encoding/decoding & get_current_seller
│   ├── db/                                # Database Connectivity Layer
│   │   ├── __init__.py                    # DB package marker
│   │   ├── base.py                        # DeclarativeBase definition
│   │   └── session.py                     # SQLAlchemy Engine, SessionLocal, get_db generator
│   ├── models/                            # SQLAlchemy 2.0 ORM Entities (Database schema)
│   │   ├── __init__.py                    # Model registry exporting all tables
│   │   ├── approval.py                    # ListingApproval entity (artisan review records)
│   │   ├── consent.py                     # ListingConsent entity (photo & story permission)
│   │   ├── listing.py                     # Listing entity (core catalog item)
│   │   ├── media.py                       # Media entity (metadata for photos/audio)
│   │   ├── seller.py                      # Seller entity (artisan profile & auth identity)
│   │   └── suggestion.py                  # Suggestion entity (AI suggestions & approvals)
│   ├── schemas/                           # Pydantic Schemas (HTTP DTOs & Serialization)
│   │   ├── __init__.py                    # Schema registry
│   │   ├── approval.py                    # ListingApprovalRequest & ListingApprovalResponse
│   │   ├── auth.py                        # FirebaseAuthRequest & AuthTokenResponse
│   │   ├── consent.py                     # ListingConsentRequest & ListingConsentResponse
│   │   ├── enums.py                       # ListingState & MediaType string enums
│   │   ├── health.py                      # HealthResponse
│   │   ├── listing.py                     # ListingCreate, Response, Status, Attention, Readback
│   │   ├── media.py                       # MediaUploadResponse
│   │   ├── preview.py                     # ListingPreviewResponse & ListingPublishResponse
│   │   ├── seller.py                      # SellerResponse & SellerUpdateRequest
│   │   └── suggestion.py                  # SuggestionItem, Lists, and Approval DTOs
│   ├── services/                          # Domain Business Logic Layer
│   │   ├── __init__.py                    # Services package marker
│   │   ├── auth.py                        # Firebase identity resolution & user creation
│   │   ├── listing.py                     # State machine transitions & ownership queries
│   │   ├── media_storage.py               # Local media validation, chunk streaming, disk storage
│   │   ├── pipeline/                      # Cataloging Pipeline Subsystem
│   │   │   ├── __init__.py                # Pipeline public API exports
│   │   │   ├── context.py                 # PipelineContext & structured stage outputs
│   │   │   ├── result.py                  # StageResult, StageStatus, PipelineResult
│   │   │   ├── runner.py                  # PipelineRunner orchestrator & retry loop
│   │   │   ├── stage.py                   # PipelineStage Protocol interface
│   │   │   └── stages/                    # Concrete deterministic stage implementations
│   │   │       ├── __init__.py            # Stages package marker
│   │   │       ├── confidence.py          # Quality confidence evaluation stage
│   │   │       ├── fact_sheet.py          # Vision + Speech synthesis stage
│   │   │       ├── image.py               # Image validation & analysis stage
│   │   │       ├── price.py               # Fair price recommendation stage
│   │   │       └── speech.py              # Speech transcription stage
│   │   └── publishing/                    # Multi-Channel Publishing Subsystem
│   │       ├── __init__.py                # Publishing exports
│   │       ├── base.py                    # CanonicalListing, Validation, PublishingAdapter Protocol
│   │       └── ondc.py                    # ONDCPublishingAdapter implementation
│   └── workers/                           # Background Task Package
│       └── __init__.py                    # Async background job placeholders
├── tests/                                 # Pytest Verification Suite
│   ├── __init__.py                        # Tests package marker
│   ├── test_api_v1.py                     # End-to-end HTTP contract tests for all routes
│   ├── test_auth.py                       # Firebase auth, phone normalization, JWT, security tests
│   ├── test_health.py                     # Health endpoint verification
│   ├── test_listing.py                    # Listing persistence, state transitions, ownership tests
│   ├── test_media.py                      # Media MIME, path traversal, size streaming, disk tests
│   ├── test_migration.py                  # Alembic migration discovery and offline SQL generation
│   ├── test_models.py                     # Database column nullability, FKs, cascades, indexes
│   ├── test_pipeline.py                   # Pipeline runner, stages, retries, error recovery tests
│   └── test_publishing.py                # Publishing adapter protocol and ONDC mock tests
├── .env.example                           # Example environment variables template
├── .gitignore                             # Git ignore rules for virtualenv, media, caches
├── README.md                              # Repository overview & quickstart guide
└── requirements.txt                       # Explicit pinned dependencies
```

### 3.4 Why This Folder Separation Matters
* **Separation of Concerns (SoC)**:
  - `api/`: Only understands HTTP concepts (requests, status codes, query parameters, header extraction). It never does raw SQL queries or direct file I/O.
  - `services/`: Contains pure business logic. `PipelineRunner` or `transition_listing` can be invoked from an API route, a CLI command, or a background worker without changing a single line of code.
  - `models/` vs `schemas/`: Prevents database implementation details (such as internal foreign keys or password hashes) from leaking to client responses, and prevents untrusted client JSON from mutating database records directly without validation.
  - `core/`: Houses singleton services (Firebase Admin, Config, Security) required across multiple layers.

---

## Section 4 — Every File Walkthrough

This is the definitive reference for every file in the backend.

---

### Root Configuration Files

#### `backend/requirements.txt`
* **Purpose**: Declares the exact third-party Python packages required to run and test the application.
* **Why it exists**: Ensures deterministic, reproducible dependency installation across development, CI/CD, and production environments.
* **Dependencies**: Read by `pip` or `uv`.
* **Contents**:
  - `fastapi>=0.115.0`: ASGI web framework.
  - `uvicorn[standard]>=0.30.0`: High-performance ASGI web server.
  - `pydantic>=2.8.0`: Data parsing and validation library.
  - `pydantic-settings>=2.4.0`: Environment variable parsing into typed Python settings.
  - `sqlalchemy>=2.0.30`: Python SQL toolkit and Object-Relational Mapper (ORM).
  - `psycopg2-binary>=2.9.9`: PostgreSQL database adapter for Python.
  - `alembic>=1.13.0`: Database schema migration tool.
  - `pytest>=8.0.0`: Automated test execution framework.
  - `httpx>=0.27.0`: HTTP client used by FastAPI's `TestClient` for synchronous route tests.
  - `python-multipart>=0.0.9`: Required by Starlette/FastAPI to parse `multipart/form-data` uploads.
  - `firebase-admin>=7.0.0`: Google Firebase Admin SDK for cryptographic token verification.
  - `PyJWT>=2.8.0`: RFC 7519 JSON Web Token signing and decoding library.

#### `backend/.env.example`
* **Purpose**: Serves as a sanitized blueprint for configuring environment variables.
* **Why it exists**: Developers copy this to `.env` to configure local secrets without accidentally checking production credentials into Git.
* **Important Settings**: Declares `PROJECT_NAME`, `DATABASE_URL`, `JWT_SECRET`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `MEDIA_STORAGE_DIR`, `MAX_MEDIA_UPLOAD_SIZE`, and `CORS_ORIGINS`.

#### `backend/alembic.ini`
* **Purpose**: Global configuration file for the Alembic migration engine.
* **Why it exists**: Tells the `alembic` CLI command where the migration scripts live (`script_location = alembic`) and sets up Python standard logging for database operations.

---

### Application Entry Point

#### `backend/app/main.py`
* **Purpose**: Creates the root FastAPI application instance and wires global middleware and routers.
* **Why it exists**: Serves as the ASGI entry point for Uvicorn (`uvicorn app.main:app`).
* **Imports**: `FastAPI`, `CORSMiddleware`, `health_router`, `api_v1_router`, `settings`.
* **Important Objects**:
  - `app`: The central `FastAPI` instance configured with title, version, and OpenAPI docs paths (`/docs`, `/redoc`, `/openapi.json`).
* **Logic**:
  1. Instantiates `FastAPI`.
  2. Inspects `settings.CORS_ORIGINS`. If configured, mounts `CORSMiddleware` with `allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]`.
  3. Mounts `health_router` at root level (`/health`).
  4. Mounts `api_v1_router` at `/api/v1`.
* **Inputs/Outputs**: Receives incoming ASGI HTTP events; dispatches to routers; emits ASGI responses.

---

### Core Infrastructure (`backend/app/core/`)

#### `backend/app/core/config.py`
* **Purpose**: Centralized, type-safe application configuration management.
* **Why it exists**: Avoids `os.environ.get()` calls scattered across the codebase. Centralizes defaults, type coercion, and validation in one place.
* **Dependencies**: `pydantic_settings.BaseSettings`, `pydantic.field_validator`.
* **Important Classes**:
  - `Settings(BaseSettings)`: Encapsulates all config variables.
* **Key Attributes**:
  - `DATABASE_URL`: PostgreSQL connection string (defaults to `postgresql+psycopg2://postgres:postgres@localhost:5432/listing_factory`).
  - `JWT_SECRET`: Secret key for HMAC-SHA256 signing of application tokens.
  - `JWT_ALGORITHM`: Algorithmic suite (`HS256`).
  - `ACCESS_TOKEN_EXPIRE_MINUTES`: Expiration window (60 minutes).
  - `FIREBASE_SERVICE_ACCOUNT_JSON`: Optional raw JSON string containing Firebase private key credentials.
  - `FIREBASE_SERVICE_ACCOUNT_PATH`: Optional filesystem path to a service account JSON file.
  - `MEDIA_STORAGE_DIR`: Path to store uploaded files (`./media`).
  - `MAX_MEDIA_UPLOAD_SIZE`: Maximum upload size in bytes (`10 * 1024 * 1024` = 10 MB).
  - `PIPELINE_MAX_STAGE_ATTEMPTS`: Maximum retry attempts for a pipeline stage (`3`).
  - `CORS_ORIGINS`: Allowed origins list.
* **Validators**:
  - `assemble_cors_origins`: Allows `CORS_ORIGINS` to be provided in `.env` as either a JSON list `["http://localhost:3000"]` or a comma-separated string `"http://localhost:3000,http://localhost:5173"`.

#### `backend/app/core/phone.py`
* **Purpose**: Canonical normalization and validation of telephone numbers.
* **Why it exists**: Artisans or mobile clients submit phone numbers in varied formats (`+91 98765-43210`, `+1 (415) 555-2671`). To guarantee database unique constraints work reliably and prevent duplicate accounts, numbers must be converted to standard E.164 form (`+<country_code><digits>`).
* **Important Functions**:
  - `normalize_phone_number(raw_phone: str) -> str`:
    1. Validates that the input is a non-empty string.
    2. Checks for a leading `+` (international country code is strictly required).
    3. Strips formatting characters (spaces, dashes, parentheses, dots).
    4. Validates that all remaining characters are decimal digits.
    5. Validates E.164 length constraints: total digits must be between 7 and 15.
    6. Returns canonical `+<digits>`.
* **Failure Modes**: Raises `ValueError` with clear messages if malformed, missing `+`, or containing letters.

#### `backend/app/core/firebase.py`
* **Purpose**: Integrates with the Firebase Admin SDK to cryptographically verify Google Firebase ID tokens generated by mobile phone authentication.
* **Why it exists**: Offloads SMS OTP verification to Firebase while keeping the backend entirely stateless and secure.
* **Custom Exceptions**:
  - `FirebaseAuthenticationError`: Base class.
  - `FirebaseTokenMissingError`, `FirebaseTokenInvalidError`, `FirebaseTokenExpiredError`, `FirebaseTokenRevokedError`, `FirebasePhoneMissingError`.
* **Important Functions**:
  - `initialize_firebase() -> firebase_admin.App`: Initializes the singleton Firebase Admin SDK instance. Implements a three-tier fallback:
    1. If `FIREBASE_SERVICE_ACCOUNT_JSON` is populated, parses the JSON string and initializes credentials.
    2. Else if `FIREBASE_SERVICE_ACCOUNT_PATH` points to an existing file, initializes from file.
    3. Otherwise attempts Google Default Application Credentials (`firebase_admin.initialize_app()`).
  - `verify_firebase_id_token(id_token: str) -> Dict[str, Any]`:
    1. Validates non-empty string.
    2. Calls `fb_auth.verify_id_token(token, check_revoked=True)`.
    3. Extracts verified subject ID (`uid`).
    4. Extracts authoritative verified phone claim (`phone_number` or claims in `firebase.identities.phone`).
    5. Rejects tokens lacking phone claims via `FirebasePhoneMissingError`.
    6. Runs `normalize_phone_number` on the phone claim.
    7. Returns `{ "uid": uid, "phone_number": normalized_phone, "claims": decoded_token }`.

#### `backend/app/core/security.py`
* **Purpose**: Issues application-level JWTs and provides the FastAPI security dependency for protecting API routes.
* **Why it exists**: The client only talks to Firebase during login. Subsequent API calls use an application JWT issued by this backend, giving us full control over token revocation, expiration, and payload contents.
* **Important Objects & Functions**:
  - `bearer_scheme = HTTPBearer(auto_error=True)`: FastAPI security scheme extracting the `Authorization: Bearer <token>` header.
  - `create_access_token(seller_id: Union[str, uuid.UUID], expires_delta: Optional[timedelta] = None) -> str`: Creates a signed JWT with claims:
    - `sub`: String representation of the seller's UUID.
    - `iat`: Timestamp issued at (UTC).
    - `exp`: Timestamp of expiration (defaults to 60 minutes).
  - `decode_access_token(token: str) -> Dict[str, Any]`: Verifies cryptographic signature using `settings.JWT_SECRET` and algorithm `settings.JWT_ALGORITHM`. Raises `HTTPException(401)` on expiration or signature tampering.
  - `get_current_seller(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)) -> Seller`:
    - FastAPI dependency injected into route functions.
    - Decodes JWT.
    - Parses `sub` into a `uuid.UUID`.
    - Queries PostgreSQL: `db.query(Seller).filter(Seller.id == seller_uuid).first()`.
    - If seller doesn't exist, raises `HTTPException(401, detail="Seller not found")`.
    - Returns the attached SQLAlchemy `Seller` instance.

---

### Database Connectivity Layer (`backend/app/db/`)

#### `backend/app/db/base.py`
* **Purpose**: Defines the SQLAlchemy 2.0 DeclarativeBase class.
* **Why it exists**: In SQLAlchemy 2.0, all domain models inherit from `class Base(DeclarativeBase)`. This registers them to a shared `Base.metadata` collection used for table creation and Alembic autogeneration.

#### `backend/app/db/session.py`
* **Purpose**: Configures the PostgreSQL connection engine and session factory.
* **Why it exists**: Provides isolated, request-scoped database sessions with deterministic cleanup.
* **Important Objects & Functions**:
  - `engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)`: Creates the database engine. `pool_pre_ping=True` sends a lightweight "ping" query before using a pooled connection, recovering from severed connections without crashing requests.
  - `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`: Factory producing new `Session` objects.
  - `get_db() -> Generator[Session, None, None]`:
    - Generator dependency yielding a database session.
    - Wrapped in a `try ... finally` block ensuring `db.close()` is called when the HTTP request finishes, preventing connection leaks.

---

### Domain Models (`backend/app/models/`)

All models inherit from `app.db.base.Base` and use SQLAlchemy 2.0 type annotations (`Mapped[...]` and `mapped_column(...)`). All primary keys are UUIDs generated server-side via `func.gen_random_uuid()` in PostgreSQL or Python's `uuid.uuid4`.

#### `backend/app/models/__init__.py`
* **Purpose**: Central package registry importing all model classes (`Seller`, `Listing`, `Media`, `ListingConsent`, `Suggestion`, `ListingApproval`).
* **Why it exists**: Ensures that when Alembic or the app imports `app.models`, all tables are loaded into `Base.metadata`.

#### `backend/app/models/seller.py`
* **Table**: `sellers`
* **Purpose**: Represents an artisan registered on the portal.
* **Columns**:
  - `id`: `Uuid`, Primary Key, default `uuid.uuid4`.
  - `name`: `String(255)`, nullable=False, default `""`.
  - `language`: `String(32)`, nullable=False, default `"hi"`.
  - `cluster`: `String(255)`, nullable=True (e.g. "Madhubani Craft Cluster").
  - `ondc_seller_id`: `String(255)`, nullable=True, Unique.
  - `firebase_uid`: `String(128)`, nullable=True, Unique, Indexed.
  - `phone_number`: `String(32)`, nullable=True, Unique, Indexed.
  - `created_at`: `DateTime(timezone=True)`, server default `now()`.
  - `updated_at`: `DateTime(timezone=True)`, onupdate `now()`.
* **Relationships**:
  - `listings`: 1-to-many relationship with `Listing`. Configured with `cascade="all, delete-orphan"` and `passive_deletes=True`.

#### `backend/app/models/listing.py`
* **Table**: `listings`
* **Purpose**: Represents an individual product publication unit progressing through the factory.
* **Columns**:
  - `id`: `Uuid`, Primary Key.
  - `seller_id`: `Uuid`, ForeignKey(`sellers.id`, ondelete="CASCADE"), Indexed, nullable=False.
  - `client_item_id`: `String(255)`, nullable=False. (The UUID generated offline on the mobile phone).
  - `state`: PostgreSQL native enum `listing_state` (`queued`, `processing`, `needs_attention`, `ready`, `published`), default `queued`, Indexed.
  - `created_at`, `updated_at`: Timestamps with timezone.
* **Constraints**:
  - `UniqueConstraint("seller_id", "client_item_id", name="uq_listings_seller_client_item")`: Prevents duplicate listings if the mobile client retries an upload.
* **Relationships**:
  - `seller`: Many-to-one back-reference to `Seller`.
  - `media`: 1-to-many with `Media`.
  - `suggestions`: 1-to-many with `Suggestion`.
  - `consent`: 1-to-1 with `ListingConsent` (`uselist=False`).
  - `approval`: 1-to-1 with `ListingApproval` (`uselist=False`).

#### `backend/app/models/media.py`
* **Table**: `media`
* **Purpose**: Stores metadata and storage coordinates for uploaded raw photos and voice notes.
* **Columns**:
  - `id`: `Uuid`, Primary Key (matches the file UUID on disk).
  - `listing_id`: `Uuid`, ForeignKey(`listings.id`, ondelete="CASCADE"), Indexed.
  - `media_type`: Native enum `media_type` (`image`, `audio`).
  - `original_filename`: `String(512)`, nullable=True. Sanitized client filename.
  - `storage_path`: `String(1024)`, nullable=True. Relative path on disk (e.g. `listing-uuid/media-uuid.jpg`).
  - `mime_type`: `String(128)`, nullable=True (e.g. `image/jpeg`).
  - `file_size_bytes`: `BigInteger`, nullable=True. Total byte count.
  - `created_at`, `updated_at`: Timestamps.

#### `backend/app/models/consent.py`
* **Table**: `listing_consents`
* **Purpose**: Records explicit legal consent given by the artisan for publishing their face/photo and artisan biographical story.
* **Columns**:
  - `id`: `Uuid`, Primary Key.
  - `listing_id`: `Uuid`, ForeignKey(`listings.id`, ondelete="CASCADE"), Unique, Indexed.
  - `photo_consent`: `Boolean`, default False, nullable=False.
  - `story_consent`: `Boolean`, default False, nullable=False.
  - `created_at`, `updated_at`: Timestamps.

#### `backend/app/models/suggestion.py`
* **Table**: `suggestions`
* **Purpose**: Holds AI-generated non-binding recommendations (e.g. suggested craft tags, care instructions) for artisan review.
* **Columns**:
  - `id`: `Uuid`, Primary Key.
  - `listing_id`: `Uuid`, ForeignKey(`listings.id`, ondelete="CASCADE"), Indexed.
  - `field`: `String(255)`, nullable=False (e.g. "material", "technique").
  - `value`: `Text`, nullable=False.
  - `reason`: `Text`, nullable=True (explains why AI suggested it).
  - `approved`: `Boolean`, nullable=True (`None` = pending review, `True` = accepted, `False` = rejected).

#### `backend/app/models/approval.py`
* **Table**: `listing_approvals`
* **Purpose**: Records the artisan's final review decision after listening to the audio read-back.
* **Columns**:
  - `id`: `Uuid`, Primary Key.
  - `listing_id`: `Uuid`, ForeignKey(`listings.id`, ondelete="CASCADE"), Unique, Indexed.
  - `approved`: `Boolean`, nullable=False.
  - `approved_at`: `DateTime(timezone=True)`, nullable=True.

---

### Pydantic Schemas (`backend/app/schemas/`)

Pydantic models define the public HTTP contract. All request schemas specify `model_config = ConfigDict(extra="forbid")` to reject unrecognized or malicious JSON fields.

#### `backend/app/schemas/enums.py`
* `ListingState(str, Enum)`: `"queued"`, `"processing"`, `"needs_attention"`, `"ready"`, `"published"`.
* `MediaType(str, Enum)`: `"image"`, `"audio"`.

#### `backend/app/schemas/health.py`
* `HealthResponse`: `{ status: str, service: str, version: str }`.

#### `backend/app/schemas/auth.py`
* `FirebaseAuthRequest`: `{ id_token: str }`.
* `AuthTokenResponse`: `{ access_token: str, token_type: "bearer", seller: SellerResponse }`.

#### `backend/app/schemas/seller.py`
* `SellerResponse`: Output DTO containing `id`, `name`, `language`, `cluster`, `ondc_seller_id`, `phone_number`.
* `SellerUpdateRequest`: Input DTO for updating `name`, `language`, `cluster`.

#### `backend/app/schemas/listing.py`
* `ListingCreateRequest`: `{ client_item_id: str }`.
* `ListingResponse`: `{ id: str, client_item_id: str, state: ListingState }`.
* `ListingListResponse`: `{ items: List[ListingResponse] }`.
* `ListingStatusResponse`: `{ listing_id: str, state: ListingState }`.
* `ListingAttentionResponse`: `{ listing_id: str, needs_attention: bool, question: Optional[str], field: Optional[str] }`.
* `ListingReadbackResponse`: Holds localized read-back data (`listing_id`, `language`, `title`, `description`, `price`, `audio_url`).

#### `backend/app/schemas/media.py`
* `MediaUploadResponse`: `{ id: str, listing_id: str, media_type: MediaType, status: "uploaded" }`.

#### `backend/app/schemas/approval.py`
* `ListingApprovalRequest`: `{ approved: bool }`.
* `ListingApprovalResponse`: `{ listing_id: str, approved: bool, state: ListingState }`.

#### `backend/app/schemas/suggestion.py`
* `SuggestionItem`: Single suggestion DTO.
* `ListingSuggestionsResponse`: `{ items: List[SuggestionItem] }`.
* `SuggestionApprovalRequest`: `{ approved: bool }`.
* `SuggestionApprovalResponse`: `{ listing_id: str, suggestion_id: str, approved: bool }`.

#### `backend/app/schemas/consent.py`
* `ListingConsentRequest`: `{ photo: bool, story: bool }`.
* `ListingConsentResponse`: `{ listing_id: str, photo: bool, story: bool, ready_to_publish: bool }`.

#### `backend/app/schemas/preview.py`
* `ListingPreviewResponse`: `{ listing_id: str, title: str, description: str, price: Optional[float], image_urls: List[str] }`.
* `ListingPublishResponse`: `{ listing_id: str, state: ListingState, preview_url: Optional[str] }`.

---

### Services & Logic Layer (`backend/app/services/`)

#### `backend/app/services/auth.py`
* **Purpose**: Implements the business logic for verified phone login and seller resolution.
* **Key Function**: `authenticate_firebase_user(id_token: str, db: Session) -> Tuple[str, Seller]`
* **Identity Conflict Safety Rules**:
  1. Verifies token with `verify_firebase_id_token(id_token)`. Gets `firebase_uid` and `phone_number`.
  2. Queries DB for existing seller by `firebase_uid`.
  3. Queries DB for existing seller by `phone_number`.
  4. **Safety Check A**: If seller found by UID, verify their registered phone matches the token's phone. If different, raise `HTTPException(401, "Identity conflict...")`.
  5. **Safety Check B**: If phone exists on a *different* seller record, raise `HTTPException(401, "Identity conflict...")`.
  6. **Linkage**: If seller found by phone but `firebase_uid` was not set, safely link `seller.firebase_uid = firebase_uid`.
  7. **Creation**: If neither exists, insert a brand new `Seller` entity with default language `"hi"`.
  8. Generates and returns `(access_token, seller)`.

#### `backend/app/services/listing.py`
* **Purpose**: Manages listing creation, seller ownership checks, and state transitions.
* **Key Constants**:
  - `VALID_STATE_TRANSITIONS`: Dictionary mapping each `ListingState` to allowed next states:
    - `queued` → `{processing}`
    - `processing` → `{needs_attention, ready}`
    - `needs_attention` → `{processing, ready}`
    - `ready` → `{published, needs_attention}`
    - `published` → `set()` (Terminal!)
* **Key Functions**:
  - `get_listing_for_seller(db: Session, listing_id: str, seller_id: uuid.UUID) -> Listing`:
    - Parses UUID. Queries listing.
    - If not found or `listing.seller_id != seller_id`, raises `ListingNotFoundError()` (HTTP 404).
    - Returning 404 instead of 403 on foreign listings prevents attacker enumeration of other sellers' listing UUIDs.
  - `create_or_get_listing(db: Session, seller_id: uuid.UUID, client_item_id: str) -> Listing`:
    - Idempotent creation: first queries `(seller_id, client_item_id)`. If exists, returns it immediately.
    - If not, inserts new listing in `queued` state. Catches concurrent race condition `IntegrityError` and gracefully falls back to returning the winner of the race.
  - `transition_listing(db: Session, listing: Listing, new_state: ListingState) -> Listing`:
    - Calls `validate_state_transition`.
    - If valid, updates `listing.state = new_state` and `listing.updated_at = utcnow()`. Commits to database.

#### `backend/app/services/media_storage.py`
* **Purpose**: Validates, sanitizes, and streams uploaded media to the filesystem.
* **Security & Reliability Implementations**:
  - `SAFE_LISTING_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")`: Rejects listing IDs containing path traversal tokens (`..`, `/`, `\`).
  - `get_listing_storage_dir(listing_id: str) -> Path`: Resolves absolute path and explicitly asserts `target_dir.relative_to(base_dir)` to mathematically guarantee no path traversal outside `MEDIA_STORAGE_DIR`.
  - Strict MIME Allowlists:
    - Images: `image/jpeg`, `image/jpg`, `image/png`, `image/webp`, `image/heic`, `image/heif`.
    - Audio: `audio/mpeg`, `audio/mp3`, `audio/wav`, `audio/x-wav`, `audio/mp4`, `audio/m4a`, `audio/aac`, `audio/ogg`, `audio/webm`.
  - Extension Allowlist & Mismatch Check: Rejects `.exe`, `.sh`, or `.html` disguised as audio/image.
  - Server-Controlled UUID Filenames: Ignores client filename for disk storage. Writes as `<media_uuid>.<safe_ext>`.
  - Chunk-by-Chunk Streaming: Reads incoming file stream in 64 KB chunks. Tracks cumulative bytes. If `total_bytes > settings.MAX_MEDIA_UPLOAD_SIZE` (10 MB), immediately closes file, deletes partial file from disk, and raises `HTTPException(413, "File exceeds maximum allowed upload size")`.
  - Empty File Rejection: 0-byte uploads are deleted and raise `HTTPException(400)`.

---

### Pipeline Subsystem (`backend/app/services/pipeline/`)

#### `backend/app/services/pipeline/stage.py`
* **Purpose**: Defines the `PipelineStage` Protocol using `typing.Protocol` and `@runtime_checkable`.
* **Interface**:
  ```python
  @runtime_checkable
  class PipelineStage(Protocol):
      name: str
      def run(self, context: PipelineContext) -> StageResult: ...
  ```

#### `backend/app/services/pipeline/context.py`
* **Purpose**: Contains the shared data bag (`PipelineContext`) passed down the sequential stage pipeline.
* **Dataclasses**:
  - `ImageStageOutput`: `image_count`, `image_paths`, `detected_labels`, `dimensions`.
  - `SpeechStageOutput`: `audio_path`, `transcript`, `language`, `duration_seconds`.
  - `FactSheetOutput`: `title`, `craft_type`, `material`, `story_summary`, `attributes`.
  - `PriceStageOutput`: `currency`, `min_price`, `max_price`, `recommended_price`, `confidence`.
  - `ConfidenceStageOutput`: `overall_score`, `is_confident`, `confidence_by_stage`.
  - `PipelineContext`: Holds `listing_id`, `seller_id`, `media: List[Media]`, references to all stage outputs, and tracking dictionaries (`stage_attempts`, `stage_results`).

#### `backend/app/services/pipeline/result.py`
* **Purpose**: Defines return types and factory helpers for stage and pipeline execution.
* **Types**:
  - `StageStatus(str, Enum)`: `success`, `needs_attention`, `failure`.
  - `StageResult`: Holds `status`, `output`, `reason`, `metadata`. Factory methods: `StageResult.ok(...)`, `StageResult.attention(reason=...)`, `StageResult.fail(reason=...)`.
  - `PipelineResult`: Final outcome holding `listing_id`, `final_state`, `stage_results`, `success`, `reason`.

#### `backend/app/services/pipeline/runner.py`
* **Purpose**: Sequential pipeline orchestrator.
* **Class**: `PipelineRunner(stages=None, max_stage_attempts=3)`
* **Execution Logic (`run`)**:
  1. Checks listing state: only `queued` or `needs_attention` can enter processing. Rejects `published`, `ready`, or active `processing` with `InvalidStateTransitionError`.
  2. Transitions listing state to `processing` in DB.
  3. Loads `media` records from DB.
  4. Initializes `PipelineContext`.
  5. Iterates through stages sequentially (`image` → `speech` → `fact_sheet` → `price` → `confidence`).
  6. **Per-Stage Isolated Retry Loop** (`attempt = 1 .. max_stage_attempts`):
     - Calls `stage.run(context)`.
     - Catches unhandled exceptions and wraps them into `StageResult.fail()`.
     - If `res.status == StageStatus.success`: breaks retry loop and proceeds to next stage. Earlier stages are NEVER rerun during downstream retries!
     - If `res.status == StageStatus.needs_attention`: Immediately stops pipeline, sets DB state to `needs_attention`, and returns `PipelineResult(success=False)`. No retries for attention!
     - If `res.status == StageStatus.failure`:
       - If `attempt < max_attempts`: logs warning, increments attempt counter, and retries the same stage.
       - If attempts exhausted: sets DB state to `needs_attention`, returns `PipelineResult(success=False)`.
  7. If all stages finish with `success`: transitions listing state in DB to `ready`. Returns `PipelineResult(success=True)`.

#### Concrete Stages (`app/services/pipeline/stages/`)
* `image.py` (`ImageStage`): **[LIVE INTEGRATED]** Connects directly to `ImageStation` (`app/services/vision/`). Filters `context.media` for `MediaType.image` (halts with `StageResult.attention("At least one image is required")` if missing). Evaluates blur (Laplacian $\ge 30$ with Canny fallback) and lighting (Otsu ROI brightness 55–185). Strips color casts, segments foreground via IS-Net ONNX, scales craft to 80% canvas coverage on pure white background with ground shadow, generates thumbnail, and populates `context.image_output` (with graceful fallback for synthetic DB test fixtures).
* `speech.py` (`SpeechStage`): Filters `context.media` for `MediaType.audio`. If none exist, returns `StageResult.attention("Voice note audio is required")`. Else populates `context.speech_output` with transcript and language.
* `fact_sheet.py` (`FactSheetStage`): Validates prerequisites (`image_output` and `speech_output`). Synthesizes artisan craft title, story summary, and material attributes into `context.fact_sheet_output`.
* `price.py` (`PriceStage`): Validates prerequisite (`fact_sheet_output`). Produces fair pricing recommendation (e.g. ₹1,200 to ₹1,800, recommended ₹1,500) into `context.price_output`.
* `confidence.py` (`ConfidenceStage`): Validates all 4 prior stage outputs. Evaluates overall confidence score against threshold (`0.70`). If score < 0.70, halts with `needs_attention`. Else marks `is_confident = True` and populates `context.confidence_output`.

---

### Publishing Subsystem (`backend/app/services/publishing/`)

#### `backend/app/services/publishing/base.py`
* **Purpose**: Defines channel-agnostic publishing contracts.
* **Dataclasses**:
  - `CanonicalListing`: Frozen immutable representation of a normalized product ready for distribution (`id`, `title`, `description`, `price`, `currency`, `category`, `materials`, `dimensions`, `media_urls`, `attributes`).
  - `PublicationValidationResult`: `{ is_valid: bool, channel: str, errors: List[str], warnings: List[str] }`.
  - `PublicationResult`: `{ success: bool, channel: str, external_id: Optional[str], status: str, message: Optional[str], details: Dict }`.
* **Protocol**:
  - `PublishingAdapter(Protocol)`: Defines properties `channel_name` and methods `validate(listing)` and `publish(listing)`.

#### `backend/app/services/publishing/ondc.py`
* **Class**: `ONDCPublishingAdapter`
* **Logic**:
  - `channel_name`: Returns `"ondc"`.
  - `validate(listing)`: Asserts title is non-empty, description is non-empty, price is positive. Issues warning if media URLs are empty.
  - `publish(listing)`: If validation fails, returns `PublicationResult(success=False, status="validation_failed")`. Otherwise returns `PublicationResult(success=True, external_id="ondc-item-<id>", status="published")`.

---

### Database Migrations (`backend/alembic/`)

#### `backend/alembic/env.py`
* **Purpose**: Configures the migration engine.
* **Logic**:
  - Adds `backend/` root to `sys.path`.
  - Imports `settings` and sets `sqlalchemy.url` dynamically from `settings.DATABASE_URL`.
  - Imports `app.models` so all entities register with `Base.metadata`.
  - Sets `target_metadata = Base.metadata`.
  - Defines `run_migrations_offline()` and `run_migrations_online()`.

#### `backend/alembic/versions/0001_domain_tables.py`
* **Revision**: `0001_domain_tables` (Revises: `None`)
* **Operations**:
  1. Creates native PostgreSQL ENUMs: `listing_state` and `media_type`.
  2. Creates tables: `sellers`, `listings`, `media`, `listing_consents`, `suggestions`, `listing_approvals`.
  3. Creates indexes on `listings.seller_id`, `listings.state`, `media.listing_id`, `listing_consents.listing_id`, `suggestions.listing_id`, `listing_approvals.listing_id`.
  4. Creates unique constraints: `uq_sellers_ondc_seller_id`, `uq_listings_seller_client_item`, `uq_listing_consents_listing_id`, `uq_listing_approvals_listing_id`.
* **Downgrade**: Drops indexes, tables, and ENUM types in reverse dependency order.

#### `backend/alembic/versions/0002_firebase_authentication.py`
* **Revision**: `0002_firebase_authentication` (Revises: `0001_domain_tables`)
* **Operations**:
  1. Adds `firebase_uid` column (`String(128)`) to `sellers`.
  2. Adds `phone_number` column (`String(32)`) to `sellers`.
  3. Adds unique constraints: `uq_sellers_firebase_uid`, `uq_sellers_phone_number`.
  4. Adds indexes on `sellers.firebase_uid` and `sellers.phone_number`.
* **Downgrade**: Drops indexes, constraints, and columns.

---

## Section 5 — FastAPI Implementation

### 5.1 Architecture of a Request
When an HTTP request arrives at `http://localhost:8000/api/v1/listings`, FastAPI handles it through a defined pipeline:

```
1. Socket / ASGI Layer (Uvicorn)
      │
2. CORSMiddleware
      │ (Checks Origin, handles pre-flight OPTIONS)
3. Router Matching
      │ (Matches prefix /api/v1 and path /listings)
4. Dependencies Resolution
      ├── get_db: Creates SessionLocal(), yields db
      └── get_current_seller: Reads Authorization header, decodes JWT, queries db
5. Request Body Parsing & Validation
      │ (Parses raw JSON bytes, validates against ListingCreateRequest)
      │ [On failure: halts with HTTP 422 Unprocessable Entity]
6. Route Handler Function Execution
      │ (Executes create_listing in app/api/routes/listings.py)
7. Service Layer Invocation
      │ (create_or_get_listing in app/services/listing.py)
8. Response Serialization & Validation
      │ (Converts return object into ListingResponse schema)
9. Dependency Teardown
      │ (finally block in get_db executes db.close())
10. ASGI Serialization to HTTP response
```

### 5.2 Dependency Injection (`Depends`)
FastAPI uses **Dependency Injection (DI)**. Instead of route functions creating their own database connections or decoding auth tokens manually, they declare dependencies as function parameters:

```python
@router.post("")
def create_listing(
    payload: ListingCreateRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingResponse:
```
* **Why this is powerful**:
  1. **Clean Code**: Routes don't contain boilerplate auth or session setup.
  2. **Testability**: In test suites, dependencies can be replaced instantly using `app.dependency_overrides[get_db] = override_get_db`. The test suite runs against in-memory SQLite without changing a single line of application code!

### 5.3 Complete API v1 Route Catalog

| Method | Route Path | Auth Required? | Input Schema / Form | Output Schema | Status Code |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | No | None | `HealthResponse` | `200 OK` |
| `POST` | `/api/v1/auth/firebase` | No | `FirebaseAuthRequest` | `AuthTokenResponse` | `200 OK` |
| `GET` | `/api/v1/seller` | Yes (`Bearer`) | None | `SellerResponse` | `200 OK` |
| `PUT` | `/api/v1/seller` | Yes (`Bearer`) | `SellerUpdateRequest` | `SellerResponse` | `200 OK` |
| `POST` | `/api/v1/listings` | Yes (`Bearer`) | `ListingCreateRequest` | `ListingResponse` | `200 OK` |
| `GET` | `/api/v1/listings` | Yes (`Bearer`) | None | `ListingListResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}` | Yes (`Bearer`) | Path: `id` | `ListingResponse` | `200 OK` |
| `POST` | `/api/v1/listings/{id}/media` | Yes (`Bearer`) | `file: UploadFile`, `media_type: Form` | `MediaUploadResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}/status` | Yes (`Bearer`) | Path: `id` | `ListingStatusResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}/attention` | Yes (`Bearer`) | Path: `id` | `ListingAttentionResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}/readback` | Yes (`Bearer`) | Path: `id` | `ListingReadbackResponse` | `200 OK` |
| `POST` | `/api/v1/listings/{id}/approval` | Yes (`Bearer`) | `ListingApprovalRequest` | `ListingApprovalResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}/suggestions` | Yes (`Bearer`) | Path: `id` | `ListingSuggestionsResponse` | `200 OK` |
| `POST` | `/api/v1/listings/{id}/suggestions/{s_id}/approval` | Yes (`Bearer`) | `SuggestionApprovalRequest` | `SuggestionApprovalResponse` | `200 OK` |
| `POST` | `/api/v1/listings/{id}/consent` | Yes (`Bearer`) | `ListingConsentRequest` | `ListingConsentResponse` | `200 OK` |
| `POST` | `/api/v1/listings/{id}/publish` | Yes (`Bearer`) | Path: `id` | `ListingPublishResponse` | `200 OK` |
| `GET` | `/api/v1/listings/{id}/preview` | Yes (`Bearer`) | Path: `id` | `ListingPreviewResponse` | `200 OK` |

### 5.4 HTTP Status Codes Used
* `200 OK`: Successful synchronous operation.
* `400 Bad Request`: Invalid state transition, empty file upload, or malformed listing ID format.
* `401 Unauthorized`: Missing Bearer token, invalid token signature, expired token, or Firebase token verification failure.
* `403 Forbidden`: Authenticated seller attempting an action on a listing owned by another seller (in media uploads).
* `404 Not Found`: Target listing does not exist or does not belong to the requesting seller.
* `413 Content Too Large`: Uploaded file exceeds 10 MB limit.
* `415 Unsupported Media Type`: Uploaded file has disallowed MIME type or extension.
* `422 Unprocessable Entity`: Request body violates Pydantic schema validation.
* `500 Internal Server Error`: Unhandled database error or unexpected filesystem failure.

---

## Section 6 — Pydantic Validation & Schemas

### 6.1 Schemas vs. Models vs. Database Records
Beginners often confuse these three layers:

```
Client JSON Payload
       │
       ▼ (Pydantic Schema validates & deserializes)
  Pydantic Schema Object (In-memory Python DTO)
       │
       ▼ (Domain service logic transforms)
  SQLAlchemy ORM Model (Python object mapped to DB table)
       │
       ▼ (Session.commit() translates to SQL INSERT/UPDATE)
  PostgreSQL Row (Binary record stored on disk)
```

1. **Pydantic Schema** (`app/schemas/`):
   - Validates incoming HTTP JSON data and defines outgoing HTTP JSON responses.
   - Operates in memory. Rejects bad data before database queries are made.
   - Example: `ListingCreateRequest(client_item_id="item-001")`.

2. **SQLAlchemy ORM Model** (`app/models/`):
   - Maps Python classes to PostgreSQL relational database tables.
   - Tracks entity state (clean, dirty, deleted), foreign key relationships, and table schema definitions.
   - Example: `Listing(id=UUID(...), seller_id=UUID(...), state=ListingState.queued)`.

3. **Database Record**:
   - The actual row stored in PostgreSQL storage blocks inside table `listings`.

### 6.2 Strict Schema Protection
All request schemas in this project configure:
```python
model_config = ConfigDict(extra="forbid")
```
If a client sends `{ "client_item_id": "123", "isAdmin": True }`, Pydantic immediately rejects the request with HTTP 422: `Extra inputs are not permitted`. This protects against mass-assignment vulnerabilities.

---

## Section 7 — Database & SQLAlchemy 2.0 ORM

### 7.1 Relational Schema Summary Table

| Table Name | Primary Key | Foreign Keys & Cascades | Unique Constraints | Indexes | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sellers` | `id` (UUID) | None | `ondc_seller_id`, `firebase_uid`, `phone_number` | `firebase_uid`, `phone_number` | Artisan profiles & credentials |
| `listings` | `id` (UUID) | `seller_id` ➔ `sellers.id` (`CASCADE`) | `(seller_id, client_item_id)` | `seller_id`, `state` | Product pipeline entries |
| `media` | `id` (UUID) | `listing_id` ➔ `listings.id` (`CASCADE`) | None | `listing_id` | Photo & audio metadata |
| `listing_consents` | `id` (UUID) | `listing_id` ➔ `listings.id` (`CASCADE`) | `listing_id` | `listing_id` | Artisan privacy consents |
| `suggestions` | `id` (UUID) | `listing_id` ➔ `listings.id` (`CASCADE`) | None | `listing_id` | AI recommended tags |
| `listing_approvals` | `id` (UUID) | `listing_id` ➔ `listings.id` (`CASCADE`) | `listing_id` | `listing_id` | Review approval logs |

### 7.2 Relational Entity Relationship Diagram

```
┌─────────────────────────────────┐
│             sellers             │
├─────────────────────────────────┤
│ PK  id               UUID       │
│     name             VARCHAR    │
│     language         VARCHAR    │
│     cluster          VARCHAR    │
│ UQ  ondc_seller_id   VARCHAR    │
│ UQ  firebase_uid     VARCHAR    │
│ UQ  phone_number     VARCHAR    │
│     created_at       TIMESTAMPTZ│
│     updated_at       TIMESTAMPTZ│
└────────────────┬────────────────┘
                 │ 1
                 │
                 │ 0..N (CASCADE DELETE)
                 ▼
┌─────────────────────────────────┐
│            listings             │
├─────────────────────────────────┤
│ PK  id               UUID       │
│ FK  seller_id        UUID       │──────┐
│     client_item_id   VARCHAR    │      │
│     state            ENUM       │      │
│     created_at       TIMESTAMPTZ│      │
│     updated_at       TIMESTAMPTZ│      │
│ UQ(seller_id, client_item_id)   │      │
└───────┬───────────────┬─────────┘      │
        │               │                │
        │ 0..N          │ 1..1           │ 1..1
        ▼               ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│    media     │ │ listing_     │ │ listing_         │
│              │ │ consents     │ │ approvals        │
├──────────────┤ ├──────────────┤ ├──────────────────┤
│ PK id   UUID │ │ PK id   UUID │ │ PK id       UUID │
│ FK list_id   │ │ FK list_id UQ│ │ FK list_id  UQ   │
│    type ENUM │ │  photo_cons B│ │    approved BOOL │
│    path TEXT │ │  story_cons B│ │    approved_at TZ│
└──────────────┘ └──────────────┘ └──────────────────┘
```

### 7.3 Why UUIDs Instead of Auto-Incrementing Integers?
1. **Offline Generation on Mobile**: Artisans often work in rural areas with spotty cellular reception. The mobile phone can generate a UUIDv4 locally, use it to organize photos in local SQLite storage, and sync to the server without asking the server for the next ID.
2. **Security / Anti-Enumeration**: Auto-incrementing IDs (`/listings/1`, `/listings/2`) allow attackers to discover total listing counts and scrape every listing sequentially. UUIDs (`/listings/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d`) are cryptographically unguessable.

### 7.4 Cascading Deletes (`CASCADE`)
Every child table references `listings.id` with `ondelete="CASCADE"`. If a listing is deleted, PostgreSQL automatically removes all associated `media`, `suggestions`, `consents`, and `approvals` in the database engine itself. This guarantees that orphaned child records can never accumulate.

---

## Section 8 — Alembic Migrations

### 8.1 What Alembic Does
Databases are stateful. While Git tracks changes to code files, it does not modify live database tables. Alembic bridges this gap:
* It reads migration scripts in `alembic/versions/`.
* It records the current schema revision in a special database table named `alembic_version`.
* When you run `alembic upgrade head`, it compares the database's version against the newest script and applies the exact SQL commands needed to bring the schema up to date.

### 8.2 The Migration History in This Project
1. **Revision `0001_domain_tables`**:
   - Baseline migration. Creates tables `sellers`, `listings`, `media`, `listing_consents`, `suggestions`, `listing_approvals`, and enums `listing_state`, `media_type`.
2. **Revision `0002_firebase_authentication`**:
   - Modifies `sellers` table to add `firebase_uid` and `phone_number` columns along with unique constraints and indexes to support phone authentication.

### 8.3 Offline SQL Generation
In secure production environments, developers are rarely allowed direct database admin access. Alembic supports **offline mode**:
```bash
alembic upgrade head --sql
```
This generates raw, reviewable SQL statements without connecting to a live database. We test this capability in `tests/test_migration.py:test_migration_sql_generation_offline`.

---

## Section 9 — Authentication & Identity Architecture

### 9.1 Two-Tier Authentication Architecture
```
[ Artisan Phone ] ──1. Enters Phone──► [ Firebase Phone Auth ]
        │                                      │
        │◄─────── 2. Receives SMS OTP ─────────┤
        │                                      │
        │──────── 3. Submits OTP ─────────────►│
        │◄─────── 4. Returns Firebase Token ───┘
        │
        │── 5. POST /api/v1/auth/firebase { id_token } ──► [ FastAPI Backend ]
        │                                                         │
        │                                                 6. Verifies token
        │                                                 7. Finds or creates Seller
        │                                                 8. Generates App JWT (HS256)
        │◄─────── 9. Returns { access_token, seller } ────────────┘
        │
        │── 10. GET /api/v1/seller (Authorization: Bearer <app_jwt>) ──► ...
```

### 9.2 Why Not Pass the Firebase Token on Every Request?
1. **Performance**: Cryptographically validating a third-party Firebase ID token requires checking Google's public key certificates. Doing this on every single API request adds latency and network overhead.
2. **Domain Coupling**: Firebase knows about Google user accounts, but has no concept of our internal `sellers.id`, seller language, or ONDC registration.
3. **Control**: An application JWT contains our own internal `seller.id` in the `sub` claim. We decide its lifetime and signing algorithm.

### 9.3 Identity Conflict Safety (Preventing Account Hijacking)
Consider what could happen if an artisan changes their phone number or logs in from another account. The authentication service (`app/services/auth.py`) implements strict conflict checks:
* If Firebase UID `UID_A` attempts to log in with phone `PHONE_X`, but the database has `UID_A` registered under `PHONE_Y`, the request is rejected with HTTP 401.
* If phone `PHONE_X` is presented by `UID_NEW`, but `PHONE_X` is already bound to `UID_ORIGINAL`, the request is rejected with HTTP 401.
* These checks prevent malicious attackers from linking their own Firebase accounts to an artisan's existing seller profile.

---

## Section 10 — Media Storage & File Streaming

### 10.1 Storage Layout on Disk
Files are saved under `MEDIA_STORAGE_DIR` (defaults to `./media`). Each listing receives its own isolated subdirectory:
```
media/
├── 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/       <-- Listing UUID
│   ├── 11111111-aaaa-bbbb-cccc-dddddddddddd.jpg  <-- Media UUID . safe extension
│   └── 22222222-aaaa-bbbb-cccc-dddddddddddd.wav
└── f47ac10b-58cc-4372-a567-0e02b2c3d479/
    └── 33333333-aaaa-bbbb-cccc-dddddddddddd.jpg
```

### 10.2 Defense in Depth: Security Controls
1. **Path Traversal Prevention**:
   - Attackers might submit a `listing_id` like `../../etc/passwd`.
   - `validate_listing_id` tests against regex `^[a-zA-Z0-9_\-]+$`.
   - `get_listing_storage_dir` resolves the path and calls `target_dir.relative_to(base_dir)`. If the path attempts to break out of the media directory, a `ValueError` is caught and HTTP 400 is raised.
2. **Server-Controlled Naming**:
   - A client filename `hack.php` is completely ignored for storage. The file is written using `uuid.uuid4()`.
3. **MIME & Extension Double-Check**:
   - Both the declared HTTP `Content-Type` header AND the client file extension are verified against conservative allowlists.
4. **Chunk-by-Chunk Streaming**:
   - Naive FastAPI code often calls `await file.read()`. For a 2 GB file, this reads 2 GB directly into server RAM, crashing the process with an Out-of-Memory (OOM) error.
   - Our implementation reads 64 KB chunks:
     ```python
     while True:
         chunk = await file.read(chunk_size)
         if not chunk: break
         total_bytes += len(chunk)
         if total_bytes > settings.MAX_MEDIA_UPLOAD_SIZE:
             f.close()
             delete_stored_file(dest_path)
             raise HTTPException(413, "File exceeds maximum allowed upload size")
         f.write(chunk)
     ```
5. **Disk Cleanup on Database Failure**:
   - If the file is successfully written to disk, but the database INSERT into `media` fails, the exception handler immediately calls `delete_stored_file(dest_path)` to ensure zero orphaned files remain on disk.

---

## Section 11 — Listing Lifecycle State Machine

### 11.1 Allowed State Transitions

```
                    ┌─────────────┐
                    │   queued    │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ processing  │
                    └──────┬──────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐
    │ needs_attention │◄───────►│      ready      │
    └────────┬────────┘         └────────┬────────┘
             │                           │
             │                           ▼
             │ (retry pipeline) ┌─────────────────┐
             └─────────────────►│    published    │ (TERMINAL)
                                └─────────────────┘
```

### 11.2 Transition Matrix Table

| From State | Allowed Target States | Disallowed Target States | Triggered By |
| :--- | :--- | :--- | :--- |
| `queued` | `processing` | `needs_attention`, `ready`, `published` | `PipelineRunner.run()` start |
| `processing` | `needs_attention`, `ready` | `queued`, `published` | Pipeline stages completion / halt |
| `needs_attention` | `processing`, `ready` | `queued`, `published` | Pipeline restart or manual review fix |
| `ready` | `published`, `needs_attention` | `queued`, `processing` | `publish_listing()` or rejection in review |
| `published` | *None (Terminal)* | All transitions disallowed | Cannot be reprocessed or re-published |

### 11.3 Code Location & Enforcement
* Defined in `app/services/listing.py` via `VALID_STATE_TRANSITIONS`.
* Calling an illegal transition (e.g. attempting to publish a `queued` listing) immediately raises `InvalidStateTransitionError` (HTTP 400 Bad Request).

---

## Section 12 — Deterministic Pipeline Runner

### 12.1 The 5 Pipeline Stations

```
PipelineContext ──► [ 1. ImageStage ]
                          │
                          ▼ (context.image_output)
                    [ 2. SpeechStage ]
                          │
                          ▼ (context.speech_output)
                    [ 3. FactSheetStage ]
                          │
                          ▼ (context.fact_sheet_output)
                    [ 4. PriceStage ]
                          │
                          ▼ (context.price_output)
                    [ 5. ConfidenceStage ]
                          │
                          ▼ (threshold check >= 0.70)
                    Listing State = 'ready'
```

1. **`ImageStage`**:
   - Scans context media for `MediaType.image`.
   - Halts with `needs_attention` if no images are attached.
   - Produces `ImageStageOutput` containing detected labels and dimensions.
2. **`SpeechStage`**:
   - Scans context media for `MediaType.audio`.
   - Halts with `needs_attention` if no voice note is attached.
   - Produces `SpeechStageOutput` with transcript, language code, and duration.
3. **`FactSheetStage`**:
   - Requires `image_output` and `speech_output`.
   - Synthesizes product copy: title, craft tradition, materials, and origin attributes into `FactSheetOutput`.
4. **`PriceStage`**:
   - Requires `fact_sheet_output`.
   - Recommends fair market pricing bounds (`min_price`, `max_price`, `recommended_price`).
5. **`ConfidenceStage`**:
   - Gatekeeper station. Evaluates quality across all stages.
   - If confidence score < 0.70, halts pipeline and transitions listing to `needs_attention`.
   - If >= 0.70, marks `is_confident = True`.

### 12.2 Isolated Stage Retries
* If an external API call (e.g. Speech-to-text service) experiences a network hiccup, the runner catches the failure and retries **only that stage** up to `PIPELINE_MAX_STAGE_ATTEMPTS` (3 times).
* **Earlier stages are not re-executed!** If `ImageStage` took 2 seconds and succeeded, downstream retries on `SpeechStage` do not waste resources re-analyzing the image.
* **Immediate Halt on `needs_attention`**: If a stage fails due to missing media or low confidence, it is **never retried**. Retrying a missing image 3 times would be pointless. The runner immediately stops and marks the listing as `needs_attention`.

---

## Section 13 — Test Suite Architecture

### 13.1 Test Directory Structure & Coverage Breakdown

| Test File | Tests | Focus Area | Key Edge Cases Tested |
| :--- | :---: | :--- | :--- |
| `test_health.py` | 1 | Basic service health | Validates root `/health` returns 200 without DB dependency. |
| `test_api_v1.py` | 13 | OpenAPI contract validation | Validates all 14 v1 paths, request validation, 422 errors. |
| `test_models.py` | 13 | Database persistence & metadata | Table columns, nullability, FK cascades, unique constraints, SQLite in-memory CRUD. |
| `test_migration.py` | 2 | Alembic migration chain | Discovers all revisions up to 0002; generates offline SQL. |
| `test_auth.py` | 18 | Phone normalization, Firebase, JWT | E.164 parsing, token forgery, expiration, seller identity conflicts, profile isolation. |
| `test_media.py` | 25 | Media upload & disk storage | MIME validation, size streaming (10MB limit), path traversal, server UUID naming, atomic disk cleanup. |
| `test_listing.py` | 46 | State machine & listing service | All valid & invalid state transitions, idempotent creation, seller ownership isolation. |
| `test_pipeline.py` | 25 | 5-stage pipeline runner | Authoritative stage order, output flow, isolated retries, needs_attention halts, state guards. |
| `test_publishing.py` | 4 | Publishing adapter subsystem | `PublishingAdapter` protocol enforcement, ONDC validation and mock publication. |

**Total Test Count**: **147 tests**, 100% passing.

### 13.2 Fixture Strategy
* Tests run in complete isolation using thread-safe, in-memory SQLite databases:
  ```python
  engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
  ```
* We hook the SQLite connection event to enforce foreign key constraints:
  ```python
  @event.listens_for(engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA foreign_keys=ON")
      cursor.close()
  ```
* FastAPI's `app.dependency_overrides` injects the test database session into routes cleanly.

### 13.3 Known Areas with Weak or Missing Coverage
Based strictly on repository inspection:
1. **Background Asynchronous Worker Integration**: `app/workers/__init__.py` is currently a placeholder. The pipeline runner is currently invoked synchronously; an async worker queue (e.g., Celery, ARQ, or FastAPI BackgroundTasks) has not yet been hooked up to HTTP endpoints.
2. **Real AI/ML Model Endpoints**: `ImageStage` (`app/services/pipeline/stages/image.py`) is now **live integrated** with `ImageStation` (IS-Net ONNX, OpenCV, Pillow). Downstream stages (`SpeechStage`, `FactSheetStage`, `PriceStage`, `ConfidenceStage`) remain deterministic mocks ready for speech/LLM integration.

---

## Section 14 — Configuration & Environment Settings

| Variable Name | Type | Default Value | Purpose | Development vs Production Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `PROJECT_NAME` | `str` | `"Listing Factory API"` | Service name displayed in Swagger docs and `/health`. | Identical. |
| `VERSION` | `str` | `"0.1.0"` | SemVer release version. | Identical. |
| `ENVIRONMENT` | `str` | `"development"` | Environment indicator. | In production, should be set to `"production"`. |
| `DATABASE_URL` | `str` | `postgresql+psycopg2://...` | Connection URI for SQLAlchemy. | In dev: local Docker PostgreSQL. In prod: managed RDS/Cloud SQL. |
| `JWT_SECRET` | `str` | `"replace-with-a-secure..."` | HMAC secret key used to sign application JWTs. | **CRITICAL**: In prod, must be a secure random 256-bit string from a secret vault. |
| `JWT_ALGORITHM` | `str` | `"HS256"` | JWT signing algorithm. | Standard HMAC SHA-256. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `60` | Token expiration duration. | Determines session duration before re-authentication is required. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | `str` | `None` | Inline JSON string containing service account credentials. | Ideal for container environments (12-factor app config). |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | `str` | `None` | Filesystem path to Firebase credentials JSON file. | Alternative option for local dev mounts. |
| `MEDIA_STORAGE_DIR` | `str` | `"./media"` | Target directory for uploaded files. | In prod: must be mounted to persistent storage (e.g. AWS EBS, EFS, or Docker volume). |
| `MAX_MEDIA_UPLOAD_SIZE` | `int` | `10485760` (10MB) | Max upload limit in bytes. | Rejects oversized files chunk-by-chunk to prevent disk exhaustion. |
| `PIPELINE_MAX_STAGE_ATTEMPTS` | `int` | `3` | Max retry attempts per pipeline stage. | Governs transient failure tolerance. |
| `CORS_ORIGINS` | `list` | `["*"]` | Allowed web origins. | In prod: must be restricted to specific frontend domains. |

---

## Section 15 — Dependencies (Line-by-Line)

1. **`fastapi>=0.115.0`**: Modern, fast Python web framework based on standard type hints. Powers routing, dependency injection, and OpenAPI doc generation.
2. **`uvicorn[standard]>=0.30.0`**: Lightning-fast ASGI server implementation built on `uvloop` and `httptools`. Serves the HTTP traffic.
3. **`pydantic>=2.8.0`**: High-performance Rust-backed data validation and serialization library. Validates all API payloads.
4. **`pydantic-settings>=2.4.0`**: Parses and validates environment variables from `.env` into typed Python dataclasses.
5. **`sqlalchemy>=2.0.30`**: Python's enterprise ORM. Manages database tables, relationships, transactions, and SQL generation using modern type annotations.
6. **`psycopg2-binary>=2.9.9`**: C-based PostgreSQL database driver allowing SQLAlchemy to communicate with PostgreSQL.
7. **`alembic>=1.13.0`**: Schema migration engine for SQLAlchemy. Tracks schema revisions and generates upgrade/downgrade scripts.
8. **`pytest>=8.0.0`**: Test runner for executing unit and integration tests.
9. **`httpx>=0.27.0`**: Next-generation HTTP client. Required by FastAPI's `TestClient` to make in-process test requests.
10. **`python-multipart>=0.0.9`**: Streaming multipart parser. Required by FastAPI to handle `UploadFile` and `File(...)` forms.
11. **`firebase-admin>=7.0.0`**: Official Google SDK. Verifies Firebase phone auth tokens cryptographically against Google public keys.
12. **`PyJWT>=2.8.0`**: Encodes and decodes application-level JWTs for authenticated sessions.

---

## Section 16 — Runtime & Deployment Operations

### 16.1 Local Development Startup
1. Ensure PostgreSQL is running:
   ```bash
   docker run --name postgres-dev -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=listing_factory -p 5432:5432 -d postgres:16-alpine
   ```
2. Activate virtual environment and run migrations:
   ```bash
   cd backend
   source .venv/bin/activate
   alembic upgrade head
   ```
3. Start Uvicorn with auto-reload:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

### 16.2 Production Deployment Architecture
* **Process Manager / ASGI Server**: Run Uvicorn behind a production reverse proxy (Nginx or AWS ALB):
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
  ```
* **Persistent Media Volume**: Because media is saved to the local filesystem (`MEDIA_STORAGE_DIR`), running inside Docker or Kubernetes requires mounting a **Persistent Volume** (EFS, Ceph, or a shared persistent disk) at `/media`. Otherwise, restarting a container would wipe out all artisan media!

---

## Section 17 — Important Design Decisions

### Decision 1: FastAPI over Flask / Django
* **Why Made**: High concurrency via ASGI, automatic OpenAPI/Swagger documentation generation, native Pydantic validation, and clean dependency injection.
* **Alternative Avoided**: Django is bloated with ORM and template engines we don't need; Flask requires numerous unmaintained third-party plugins for typed schemas.
* **Consequence**: Python 3.10+ type annotations are mandatory throughout the codebase.

### Decision 2: PostgreSQL with SQLAlchemy 2.0
* **Why Made**: E-commerce cataloging requires strict data integrity, foreign key cascades, and unique constraints. SQLAlchemy 2.0 provides modern, fully type-checked declarative models.
* **Alternative Avoided**: MongoDB/NoSQL lacks foreign key cascade enforcement and allows accidental data corruption.
* **Consequence**: Schema changes require explicit Alembic migrations.

### Decision 3: Firebase for Phone Auth, Application JWT for API Calls
* **Why Made**: Handling international SMS OTP delivery, telecom carrier compliance, and rate limiting is notoriously difficult. Firebase offloads OTP management. Using our own JWT for subsequent calls prevents third-party vendor lock-in on internal APIs.
* **Alternative Avoided**: Rolling our own SMS gateway or requiring passwords (unusable for illiterate artisans).
* **Consequence**: Backend must maintain the Firebase Admin SDK and handle identity synchronization safely.

### Decision 4: Local Media Storage with Strict Validation
* **Why Made**: Keeps the project self-contained and cost-effective without cloud vendor lock-in (e.g. AWS S3).
* **Alternative Avoided**: Storing base64 encoded images directly in the database (which balloons database size and destroys cache efficiency).
* **Consequence**: Production deployments must manage persistent disk volumes.

### Decision 5: Explicit 5-State Machine
* **Why Made**: Clear, finite state lifecycle (`queued` → `processing` → `needs_attention` ↔ `ready` → `published`) prevents half-processed items from appearing in public marketplace listings.
* **Alternative Avoided**: Ad-hoc boolean flags like `is_processed=True`, `is_approved=False` scattered across database columns.
* **Consequence**: Invalid state jumps are rejected immediately with HTTP 400.

---

## Section 18 — How Everything Connects (End-to-End Scenarios)

### Scenario A: New Seller Authenticates
1. Mobile app exchanges SMS OTP with Firebase; receives Firebase ID token.
2. Mobile app calls `POST /api/v1/auth/firebase` with `{ "id_token": "..." }`.
3. In `app/api/routes/auth.py`, `authenticate_firebase()` is invoked.
4. It calls `authenticate_firebase_user(id_token, db)` in `app/services/auth.py`.
5. `verify_firebase_id_token` in `app/core/firebase.py` verifies the cryptographic signature and returns `phone_number = "+919876543210"` and `uid = "fb-user-123"`.
6. `authenticate_firebase_user` checks DB. No seller matches.
7. Instantiates `Seller(firebase_uid="fb-user-123", phone_number="+919876543210")`. Adds to DB and commits.
8. Calls `create_access_token(seller.id)` in `app/core/security.py`, which returns an HMAC-signed JWT.
9. Route returns `AuthTokenResponse` with the JWT and seller profile.

### Scenario B: Seller Creates a Listing
1. Mobile app makes request `POST /api/v1/listings` with header `Authorization: Bearer <jwt>` and body `{"client_item_id": "mobile-draft-1"}`.
2. `get_current_seller` dependency in `app/core/security.py` decodes JWT and loads `Seller` from DB.
3. Route calls `create_or_get_listing()` in `app/services/listing.py`.
4. Service queries `listings` for `(seller_id, client_item_id)`.
5. Not found. Creates `Listing(seller_id=seller.id, client_item_id="mobile-draft-1", state=ListingState.queued)`. Commits.
6. Returns `ListingResponse(id="...", client_item_id="mobile-draft-1", state="queued")`.

### Scenario C: Seller Uploads Media
1. Mobile app calls `POST /api/v1/listings/{listing_id}/media` with `multipart/form-data` containing `file` and `media_type="image"`.
2. Route calls `save_media_upload()` in `app/services/media_storage.py`.
3. Validates MIME (`image/jpeg`) and extension (`.jpg`).
4. Generates a new UUID: `media_id = uuid.uuid4()`.
5. Streams file in 64 KB chunks to `media/<listing_id>/<media_id>.jpg`. Verifies size <= 10 MB.
6. In `app/api/routes/media.py`, queries `Listing`. Verifies `listing.seller_id == current_seller.id`.
7. Inserts record into `media` table referencing `listing_id` and storage path. Commits.
8. Returns `MediaUploadResponse(id=media_id, status="uploaded")`.

### Scenario D & E: Pipeline Executes to Ready
1. Service invokes `PipelineRunner.run(listing_id, db, seller_id)`.
2. State guard checks: current state is `queued`. Allowed! Transitions `state = processing` in DB.
3. Loads associated `Media` rows. Builds `PipelineContext`.
4. `ImageStage.run(context)` finds image. Stores `ImageStageOutput`.
5. `SpeechStage.run(context)` finds audio note. Transcribes and stores `SpeechStageOutput`.
6. `FactSheetStage.run(context)` combines vision + speech into `FactSheetOutput`.
7. `PriceStage.run(context)` calculates ₹1,500 into `PriceStageOutput`.
8. `ConfidenceStage.run(context)` evaluates score = 0.95 (>= 0.70 threshold). Stores `ConfidenceStageOutput`.
9. All stages completed successfully. Runner calls `transition_listing(db, listing, ListingState.ready)`. Listing is now ready for review!

### Scenario F: Pipeline Encounters Missing Media (`needs_attention`)
1. Artisan created listing and uploaded voice note, but forgot to upload a photo.
2. `PipelineRunner.run(listing_id, db)` starts. Transitions to `processing`.
3. `ImageStage.run(context)` executes: finds no image in `context.media`.
4. Stage returns `StageResult.attention("At least one image is required")`.
5. Runner catches `StageStatus.needs_attention`. It immediately halts the loop without retrying!
6. Calls `transition_listing(db, listing, ListingState.needs_attention)`.
7. Returns `PipelineResult(success=False, final_state=needs_attention, reason="At least one image is required")`.
8. When the mobile app polls `GET /api/v1/listings/{id}/attention`, it learns that an image is missing and prompts the artisan to snap a picture.

### Scenario G & H: Review Approval, Consent, and Publishing
1. Artisan listens to audio read-back. Approves generated description via `POST /api/v1/listings/{id}/approval` (`{"approved": true}`). State remains `ready`.
2. Artisan grants photo and story permissions via `POST /api/v1/listings/{id}/consent`.
3. Artisan taps "Publish to ONDC". Mobile calls `POST /api/v1/listings/{id}/publish`.
4. Route calls `transition_listing(db, listing, ListingState.published)`.
5. State is updated to `published` in DB. This is a terminal state; no further transitions are allowed.
6. Returns `ListingPublishResponse(listing_id=id, state="published")`.

---

## Section 19 — Concepts You Need to Master (Syllabus)

### 1. Python Advanced Foundations
* **`typing.Protocol` & `@runtime_checkable`**: Structural subtyping (duck typing checked at runtime). Used in `app/services/pipeline/stage.py` and `app/services/publishing/base.py`.
* **Context Managers (`try ... finally`, `with`)**: Guaranteeing resource cleanup. Used in `get_db()` and `open(...)` chunk streaming.
* **Pathlib (`pathlib.Path`)**: Modern, platform-independent filesystem manipulation. Resolving paths and preventing path traversal in `media_storage.py`.
* **Generator Functions (`yield`)**: Functions that produce values lazily. Used for FastAPI session dependency injection.

### 2. FastAPI
* **Dependency Injection (`Depends`)**: Decoupling resource acquisition from route logic.
* **APIRouter & Modular Routing**: Splitting APIs across prefix routes and aggregating them.
* **HTTP Error Handling (`HTTPException`)**: Returning clean, standardized RFC 7807 error responses.
* **Multipart Forms (`UploadFile`, `File`, `Form`)**: Handling streaming binary file uploads.

### 3. Pydantic 2.0
* **Data Parsing vs Type Checking**: Coercing strings, integers, and UUIDs automatically.
* **ConfigDict & Extra Forbid**: Preventing unwanted fields from entering application logic.
* **Field Validators**: Custom pre-processing and sanitation logic.

### 4. SQLAlchemy 2.0 & PostgreSQL
* **Declarative Mapping (`Mapped[...]`, `mapped_column`)**: Modern type-safe table definitions.
* **Foreign Key Constraints & Cascading**: Enforcing relational integrity at the database engine level.
* **Transactions, `commit()`, and `rollback()`**: Ensuring ACID guarantees across multiple database operations.
* **Session Lifecycles**: Understanding when an object is transient, pending, persistent, or detached.

### 5. Security & Authentication
* **JSON Web Tokens (JWT)**: Cryptographic claims, HMAC SHA-256 signatures, expiration windows, and subject mapping.
* **Third-Party Delegated Authentication**: Verifying external asymmetric tokens (Firebase Admin SDK) and issuing internal symmetric tokens.
* **Path Traversal Protection**: Guarding against directory escape attacks in user-supplied filenames.

---

## Section 20 — "Can I Rebuild This?" Reconstruction Roadmap

If you had to recreate this backend from scratch on a blank machine, follow these 10 chronological milestones:

1. **Milestone 1 — Scaffold & Dependencies**:
   - Create Python virtual environment. Install `fastapi`, `uvicorn`, `pydantic-settings`, `pytest`.
   - Setup `app/main.py` and `GET /health`. Verify with `TestClient`.
2. **Milestone 2 — Pydantic Contract**:
   - Define domain enums (`ListingState`, `MediaType`).
   - Define all request and response schemas in `app/schemas/`.
3. **Milestone 3 — Database Engine & Base**:
   - Install `sqlalchemy`, `psycopg2-binary`, `alembic`.
   - Create `app/db/base.py` and `app/db/session.py`. Configure session generator `get_db()`.
4. **Milestone 4 — SQLAlchemy Domain Models**:
   - Create `Seller`, `Listing`, `Media`, `ListingConsent`, `Suggestion`, `ListingApproval` models.
   - Configure foreign keys with `ondelete="CASCADE"` and bidirectional relationships.
5. **Milestone 5 — Database Migrations**:
   - Initialize Alembic (`alembic init alembic`).
   - Configure `alembic/env.py` to import `Base.metadata` and `settings.DATABASE_URL`.
   - Create and test migrations `0001` and `0002`.
6. **Milestone 6 — Phone Authentication & Security**:
   - Write E.164 normalization in `app/core/phone.py`.
   - Integrate `firebase-admin` in `app/core/firebase.py`.
   - Implement JWT issuance and `get_current_seller` dependency in `app/core/security.py`.
   - Wire `POST /api/v1/auth/firebase` and test conflict safety.
7. **Milestone 7 — Secure Media Storage**:
   - Implement chunk-by-chunk streaming, MIME allowlists, and path traversal guards in `app/services/media_storage.py`.
   - Connect `POST /api/v1/listings/{id}/media` to save files and persist `Media` metadata.
8. **Milestone 8 — Listing Service & State Machine**:
   - Implement explicit state transition graph and `transition_listing()` in `app/services/listing.py`.
   - Connect CRUD and status endpoints with strict seller ownership verification.
9. **Milestone 9 — Deterministic Pipeline Runner**:
   - Define `PipelineStage` Protocol, `PipelineContext`, and `StageResult`.
   - Implement 5 sequential stages (`Image`, `Speech`, `FactSheet`, `Price`, `Confidence`).
   - Implement `PipelineRunner` with isolated stage retries and immediate halts on `needs_attention`.
10. **Milestone 10 — Full Test Validation**:
    - Write unit and integration tests for every layer using isolated in-memory SQLite fixtures.
    - Confirm 100% pass rate.

---

## Section 21 — Structured Code Reading Map

To study this repository without getting overwhelmed, read the files in this precise order:

1. **The Contract**:
   - Read `backend/app/schemas/enums.py` (understand `ListingState` and `MediaType`).
   - Read `backend/app/schemas/listing.py` (understand what data enters and leaves listings).
2. **The Database**:
   - Read `backend/app/db/base.py` and `backend/app/db/session.py`.
   - Read `backend/app/models/seller.py` and `backend/app/models/listing.py`.
   - Notice the foreign keys and unique constraints.
3. **The Configuration**:
   - Read `backend/app/core/config.py` and `.env.example`.
4. **Authentication Flow**:
   - Read `backend/app/core/phone.py` (simple regex normalization).
   - Read `backend/app/core/firebase.py` (how Firebase tokens are verified).
   - Read `backend/app/core/security.py` (how app JWTs are issued and checked).
   - Read `backend/app/services/auth.py` (how conflict safety is enforced).
   - Read `backend/app/api/routes/auth.py` and `tests/test_auth.py`.
5. **Media Storage**:
   - Read `backend/app/services/media_storage.py`. Notice the chunk reading and path traversal checks.
   - Read `backend/app/api/routes/media.py` and `tests/test_media.py`.
6. **State Machine & Listings**:
   - Read `backend/app/services/listing.py`. Study `VALID_STATE_TRANSITIONS`.
   - Read `backend/app/api/routes/listings.py` and `tests/test_listing.py`.
7. **The Pipeline Runner**:
   - Read `backend/app/services/pipeline/stage.py` (the Protocol).
   - Read `backend/app/services/pipeline/context.py` (the dataclasses).
   - Read `backend/app/services/pipeline/result.py` (results and statuses).
   - Read `backend/app/services/pipeline/stages/*.py` (the 5 stations).
   - Read `backend/app/services/pipeline/runner.py` (the retry loop and state transition).
   - Read `tests/test_pipeline.py`.
8. **App Assembly**:
   - Read `backend/app/api/v1.py` and `backend/app/main.py`.

---

## Section 22 — Self-Assessment Questions & Answers

Test your understanding by attempting these questions before checking the answers at the end.

### Level 1 — Basic Knowledge
1. What are the 5 exact states of the listing state machine?
2. Which HTTP status code is returned if a client uploads an empty (0-byte) file?
3. What is the difference between `Pydantic BaseModel` and `SQLAlchemy Base`?
4. What algorithm is used to sign the application JWT?

### Level 2 — Architectural Understanding
5. Why does the application issue its own JWT instead of requiring the client to pass the Firebase ID token for all subsequent requests?
6. Why does `get_listing_for_seller()` return HTTP 404 instead of HTTP 403 when an authenticated seller requests a listing belonging to someone else?
7. In the pipeline runner, why is `needs_attention` not retried, while `failure` is retried?

### Level 3 — Request Tracing
8. Trace what happens if an artisan uploads a 15 MB image. Where is it caught, what file operations happen, and what status code is returned?
9. Trace what happens if a mobile client calls `create_listing` twice with the exact same `client_item_id`. Does it create two database rows?

### Level 4 — Debugging & Edge Cases
10. If an attacker submits `listing_id = "../../etc/passwd"` to `POST /listings/{listing_id}/media`, what two separate security mechanisms prevent the server from writing outside the media folder?
11. If `SpeechStage` fails on attempt 1 with a transient timeout, does `ImageStage` run again during attempt 2? Why or why not?

### Level 5 — Advanced Architecture
12. Why are all primary keys in this system `UUID`s instead of auto-incrementing integers? What specific mobile offline capability does this unlock?
13. Explain the identity conflict check: what happens if an existing seller with phone `+919876543210` logs in with a Firebase account that returns phone `+911111111111`?

---

### Answer Key (Check Only After Answering!)

* **Answer 1**: `queued`, `processing`, `needs_attention`, `ready`, `published`.
* **Answer 2**: HTTP `400 Bad Request`. Handled in `media_storage.py:211`.
* **Answer 3**: Pydantic validates in-memory HTTP JSON payloads entering/leaving API routes; SQLAlchemy defines relational database schema, tracks persistence state, and issues SQL queries.
* **Answer 4**: HMAC-SHA256 (`HS256`), configured in `app/core/config.py`.
* **Answer 5**: Validating Firebase ID tokens requires verifying external Google public keys over the network, adding latency. Issuing our own JWT makes API requests fast, self-contained, stateless, and decouples our database entity model from Firebase.
* **Answer 6**: Security through anti-enumeration. Returning 403 ("Forbidden") confirms to an attacker that the target listing UUID exists. Returning 404 ("Not Found") reveals nothing about whether the UUID exists or not.
* **Answer 7**: `failure` represents transient system errors (e.g. temporary network timeout contacting an external speech service) which may succeed on a subsequent try. `needs_attention` represents an intentional human-intervention signal (e.g. no photo was uploaded, or AI confidence was too low); retrying 3 times without human input would produce the exact same failure and waste compute.
* **Answer 8**: The file stream is read in 64 KB chunks in `save_media_upload`. When cumulative bytes exceed `10 * 1024 * 1024` (10 MB), the loop breaks, the file handle is closed, `delete_stored_file` unlinks the partial file from disk, and `HTTPException(413, "File exceeds maximum allowed upload size")` is raised.
* **Answer 9**: No. `create_or_get_listing` first checks `(seller_id, client_item_id)`. If found, it returns the existing listing immediately. Even in a race condition, the database table has `UniqueConstraint("seller_id", "client_item_id")`, causing the losing request to rollback and return the existing row.
* **Answer 10**: (1) `validate_listing_id` validates against regex `^[a-zA-Z0-9_\-]+$`, which rejects dots and slashes. (2) `get_listing_storage_dir` resolves the path and calls `target_dir.relative_to(base_dir)`. If the path escaped `MEDIA_STORAGE_DIR`, Python raises a `ValueError` which triggers HTTP 400.
* **Answer 11**: No. The pipeline maintains an isolated retry loop around each individual stage. `ImageStage` succeeded and stored its output in `context.image_output`. Only `SpeechStage.run(context)` is re-invoked on attempt 2.
* **Answer 12**: UUIDs can be generated offline by the mobile phone client without asking the server for the next ID sequence. This allows the artisan to capture photos and queue drafts in rural offline environments, using the UUID to link photos locally before syncing.
* **Answer 13**: `authenticate_firebase_user` detects that the verified phone number from the token does not match the seller's registered phone number, rejects the login, and raises `HTTPException(401, "Identity conflict: verified phone number does not match registered phone number")`.
