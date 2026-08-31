# Document Ingestion Platform

> An enterprise-grade unified document ingestion, cleaning, structuring, and RAG preparation platform for knowledge bases and LLM applications.

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RAG%20Schema%20v3-336791)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20Store-DC244C)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![Windows](https://img.shields.io/badge/Windows-Desktop-0078D6)

---

## Table of Contents

- [Overview](#overview)
- [Project Goals](#project-goals)
- [Current Capabilities](#current-capabilities)
- [Supported Formats](#supported-formats)
- [High-Level Architecture](#high-level-architecture)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Unified Document Model](#unified-document-model)
- [JSON Output](#json-output)
- [PostgreSQL RAG Schema v3](#postgresql-rag-schema-v3)
- [Schema Management](#schema-management)
- [RAG Data Consistency](#rag-data-consistency)
- [Embedding Lifecycle](#embedding-lifecycle)
- [Qdrant Integration](#qdrant-integration)
- [GUI](#gui)
- [Quick Start](#quick-start)
- [PostgreSQL Initialization](#postgresql-initialization)
- [Running the Application](#running-the-application)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [PyInstaller Build](#pyinstaller-build)
- [Testing](#testing)
- [Design Principles](#design-principles)
- [Operational Notes](#operational-notes)
- [Recommended Workflow](#recommended-workflow)
- [Roadmap](#roadmap)

---

# Overview

**Document Ingestion Platform** is an enterprise-oriented ingestion platform for:

- Retrieval-Augmented Generation (RAG)
- Enterprise knowledge bases
- LLM applications
- Structured document extraction
- Document cleaning
- Document normalization
- PostgreSQL-based document storage
- Embedding workflows
- Vector retrieval systems

Enterprise documents are commonly distributed across different formats:

- PDF
- Microsoft Word
- Microsoft PowerPoint
- Microsoft Excel
- TXT
- Images and scanned documents

Each format has a different internal representation.

The platform standardizes them through a common processing architecture:

```text
Source File
   ↓
Format Router
   ↓
Pipeline Factory
   ↓
Loader
   ↓
Normalizer
   ↓
Filter
   ↓
Parser
   ↓
Structure Analyzer
   ↓
Hierarchy Builder
   ↓
Chunker
   ↓
Token Counter
   ↓
Unified Document Model
   ↓
JSON / PostgreSQL
   ↓
Embedding
   ↓
Qdrant
   ↓
RAG
```

The unified document model is:

```text
Document
├── Pages
├── Chapters
├── Sections
└── Contents / Chunks
```

---

# Project Goals

This project is not intended to be a plain-text extraction utility.

Its primary goal is to preserve as much useful document structure as possible while preparing stable, traceable data for downstream RAG workloads.

Key goals include:

- Preserve chapter and section hierarchy
- Keep page / slide / sheet context
- Remove repetitive noise such as headers and footers
- Normalize text across source formats
- Preserve source ordering
- Create stable semantic chunks
- Track token counts
- Produce deterministic JSON
- Provide PostgreSQL as the canonical data source
- Support repeatable ingestion
- Detect content changes through hashes
- Track embedding state
- Prevent stale vector accumulation
- Provide a foundation for PostgreSQL ↔ Qdrant consistency

---

# Current Capabilities

| Module | Status |
|---|---|
| PDF Loader / Parser | ✅ |
| DOCX Loader / Parser | ✅ |
| PPTX Loader / Parser | ✅ |
| Legacy PPT conversion | ✅ Windows + Microsoft PowerPoint |
| XLSX Loader / Parser | ✅ |
| TXT Loader / Parser | ✅ |
| PNG / JPG / JPEG Image Pipeline | ✅ |
| OCR integration | ✅ RapidOCR / ONNX Runtime |
| Unicode normalization | ✅ |
| Header / Footer filtering | ✅ |
| Page / Slide / Sheet filtering | ✅ |
| Paragraph / Table / Shape / Row filtering | ✅ |
| Title detection | ✅ |
| Title joining | ✅ |
| Title normalization | ✅ |
| Structure analysis | ✅ |
| Section hierarchy construction | ✅ |
| Content filtering | ✅ |
| Chunking | ✅ |
| Token counting | ✅ |
| JSON building | ✅ |
| JSON → PostgreSQL import | ✅ |
| PostgreSQL RAG Schema v3 | ✅ |
| Schema initialization | ✅ |
| Non-destructive schema upgrade | ✅ |
| Embedding state management | ✅ |
| BGE-M3 embedding module | ✅ |
| Qdrant vector store module | ✅ |
| Vector delete queue | ✅ |
| Windows GUI | ✅ |
| PyInstaller OneFile GUI build | ✅ |

---

# Supported Formats

The current `FormatRouter` and `PipelineFactory` support:

| Format | Extension | Pipeline | Notes |
|---|---|---|---|
| PDF | `.pdf` | `PDFPipeline` | Structured PDF ingestion |
| Word | `.docx` | `DOCXPipeline` | Uses python-docx |
| Excel | `.xlsx` | `XLSXPipeline` | Uses openpyxl |
| PowerPoint | `.pptx` | `PPTXPipeline` | Uses python-pptx |
| Legacy PowerPoint | `.ppt` | `PPTPipeline` | Converted to `.pptx` |
| Text | `.txt` | `TXTPipeline` | Structured text processing |
| Image | `.png` | `ImagePipeline` | OCR / text extraction |
| Image | `.jpg` | `ImagePipeline` | OCR / text extraction |
| Image | `.jpeg` | `ImagePipeline` | OCR / text extraction |

## Legacy `.ppt`

Legacy `.ppt` files are converted using Windows COM automation:

```text
.ppt
  ↓
Microsoft PowerPoint COM
  ↓
temporary .pptx
  ↓
PPTXPipeline
```

Requirements:

- Windows
- Microsoft PowerPoint installed
- `pywin32`

---

# High-Level Architecture

```text
                         ┌────────────────────────┐
                         │      Input Files       │
                         │ PDF DOCX PPTX PPT XLSX │
                         │ TXT PNG JPG JPEG       │
                         └───────────┬────────────┘
                                     │
                                     ▼
                         ┌────────────────────────┐
                         │      FormatRouter      │
                         └───────────┬────────────┘
                                     │
                                     ▼
                         ┌────────────────────────┐
                         │     PipelineFactory    │
                         └───────────┬────────────┘
                                     │
                ┌────────────────────┼─────────────────────┐
                ▼                    ▼                     ▼
             PDF/DOCX             PPT/XLSX             TXT/Image
             Pipelines             Pipelines             Pipelines
                └────────────────────┼─────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ Loader / Normalizer  │
                          │ Filter / Parser      │
                          │ Analyzer             │
                          │ Hierarchy Builder    │
                          │ Chunker              │
                          │ Token Counter        │
                          └──────────┬───────────┘
                                     │
                                     ▼
                           ┌──────────────────┐
                           │ Unified Document │
                           │      Model       │
                           └────────┬─────────┘
                                    │
                       ┌────────────┴────────────┐
                       ▼                         ▼
                Structured JSON          PostgreSQL RAG v3
                                               │
                                               ▼
                                        Embedding Worker
                                               │
                                               ▼
                                             Qdrant
                                               │
                                               ▼
                                              RAG
```

---

# Document Processing Pipeline

Different formats have specialized internals, but the overall processing model is consistent:

```text
Load
  ↓
Normalize
  ↓
Filter
  ↓
Parse
  ↓
Analyze Structure
  ↓
Title Detect / Join / Normalize
  ↓
Section Hierarchy Builder
  ↓
Content Filter
  ↓
Chunk
  ↓
Token Counter
  ↓
Document Validation
  ↓
JSON Builder
  ↓
PostgreSQL Storage
```

## Loader

The loader layer reads source documents and preserves relevant information such as:

- Page number
- Slide number
- Sheet name
- Paragraphs
- Tables
- Shapes
- Text blocks
- Images
- OCR output
- Original ordering

## Normalizer

Normalization includes:

```text
Unicode normalization
Full-width / half-width normalization
Whitespace cleanup
Line-break normalization
Control-character cleanup
Special-character normalization
```

## Filters

Format-specific filters remove low-value or repetitive content.

Examples:

```text
PDF
├── HeaderFooterFilter
└── PageFilter

DOCX
├── ParagraphFilter
└── TableFilter

PPTX
├── ShapeFilter
└── SlideFilter

XLSX
├── RowFilter
└── SheetFilter
```

## Structure Analysis

The analyzer detects:

```text
Chapter
Section
Subsection
Title
Body
```

and works with:

- Title Detector
- Title Joiner
- Title Normalizer
- Section Hierarchy Builder

## Chunking

Chunking is designed to preserve semantic boundaries.

Preferred order:

```text
Chapter
  ↓
Section
  ↓
Content
  ↓
Semantic Chunk
```

## Token Counting

Chunk metadata includes:

- `token_count`
- `chunk_index`
- `page_number`
- `sort_order`

These fields help with:

- Embedding
- RAG context budgeting
- Retrieval diagnostics
- Context window control

---

# Unified Document Model

All supported source formats are converted into a common model:

```text
Document
├── metadata
├── pages[]
├── chapters[]
├── sections[]
└── contents[]
```

## Document

Typical fields:

```text
document_id
file_name
file_type
metadata
pages
chapters
sections
contents
```

## Chapter

```text
chapter_id
title_jp
title_en
sort_order
metadata
```

## Section

```text
section_id
chapter_id
parent_section_id
title_jp
title_en
level
sort_order
page_number
metadata
```

## Content / Chunk

```text
chapter_id
section_id
text
page_number
chunk_index
token_count
sort_order
metadata
```

---

# JSON Output

`JsonBuilder` produces a structured representation:

```json
{
  "document": {
    "document_id": "example-document-id",
    "file_name": "example.pdf",
    "file_type": "pdf"
  },
  "metadata": {},
  "chapters": [],
  "sections": [],
  "contents": [],
  "vector_records": []
}
```

## Vector Records

Vector records are prepared for downstream embedding workflows:

```json
{
  "id": "chunk-xxxxxxxxxxxxxxxx",
  "text": "Chunk text...",
  "metadata": {
    "document_id": "doc-id",
    "file_name": "example.pdf",
    "chapter_id": "1",
    "section_id": "1.1",
    "page_number": 15,
    "chunk_index": 0,
    "token_count": 168
  }
}
```

The JSON builder prepares data only.

It does **not** generate embeddings itself.

---

# PostgreSQL RAG Schema v3

Current schema version:

```text
RAG_SCHEMA_VERSION = 3
RAG_SCHEMA_NAME    = rag-schema-v3
```

The schema is managed by:

```text
app/storage/schema_manager.py
```

Current schema:

```text
public
├── documents
├── chapters
├── sections
├── contents
├── embeddings
├── vector_delete_queue
├── schema_version
└── rag_chunks          [VIEW]
```

---

## `documents`

Document master table.

Main fields:

```text
id
document_id
file_name
file_type
title
module
document_type
version
company
category
source_file
language
source_hash
metadata
created_at
updated_at
```

Unique constraint:

```text
UNIQUE(document_id)
```

---

## `chapters`

Chapter table.

```text
id
document_id
chapter_id
title_jp
title_en
sort_order
metadata
created_at
updated_at
```

Unique constraint:

```text
UNIQUE(document_id, chapter_id)
```

---

## `sections`

Section hierarchy table.

```text
id
document_id
chapter_id
section_id
parent_section_id
title_jp
title_en
level
sort_order
page_number
metadata
created_at
updated_at
```

Unique constraint:

```text
UNIQUE(document_id, section_id)
```

---

## `contents`

Primary RAG chunk table.

```text
id
document_id
chapter_id
section_id
content
page_number
chunk_index
token_count
sort_order
metadata

content_hash

embedding_status
embedding_started_at
embedded_at
embedding_model
embedding_version
embedded_content_hash
embedding_error
embedding_retry_count

created_at
updated_at
```

Logical uniqueness:

```text
UNIQUE(document_id, section_id, chunk_index)
```

`contents.id` is the stable PostgreSQL chunk primary key.

It is intended to be reusable as a stable reference for downstream vector systems.

---

## `embeddings`

Embedding / vector mapping table.

```text
id
content_id
model_name
model_version
vector_dimension
qdrant_collection
qdrant_point_id
content_hash
created_at
updated_at
```

Unique constraint:

```text
UNIQUE(content_id, model_name, model_version)
```

Foreign key:

```text
content_id
    → contents.id
    ON DELETE CASCADE
```

---

## `vector_delete_queue`

Stores vector deletion tasks for stale chunks.

```text
id
content_id
document_id
reason
queued_at
processed_at
last_error
```

Unique constraint:

```text
UNIQUE(content_id)
```

Typical reason:

```text
STALE_CONTENT
```

---

## `schema_version`

Tracks schema version:

```text
component
version
name
applied_at
```

Current value:

```text
component = document_ingestion_rag
version   = 3
name      = rag-schema-v3
```

---

# Schema Management

`SchemaManager.ensure_schema()` is responsible for:

- Initial schema creation
- Non-destructive schema upgrade
- Adding missing columns
- Creating missing indexes
- Reusing equivalent indexes
- Creating the `rag_chunks` view
- Recording schema version
- Auditing duplicate legacy indexes
- Avoiding destructive business-data operations

Upgrade philosophy:

```text
Missing table    → CREATE
Missing column   → ALTER ADD
Missing index    → CREATE
Equivalent index → REUSE
Legacy duplicate → AUDIT
Business data    → PRESERVE
```

The schema manager should be treated as the canonical schema definition.

---

# RAG Indexes

Current logical indexes include:

```text
uq_documents_document_id

uq_chapters_document_chapter

uq_sections_document_section
idx_sections_document_chapter
idx_sections_parent

uq_contents_document_section_chunk
idx_contents_document_order
idx_contents_embedding_queue
idx_contents_embedding_stale

uq_embeddings_content_model_version
idx_embeddings_content

uq_vector_delete_queue_content
idx_vector_delete_queue_pending
```

Equivalent PostgreSQL indexes are reused rather than duplicated.

---

# `rag_chunks` View

RAG Schema v3 creates:

```text
public.rag_chunks
```

This view combines:

```text
documents
chapters
sections
contents
```

into a RAG-oriented chunk representation.

Representative fields:

```text
content_id
document_id
file_name
file_type

chapter_id
chapter_title_jp
chapter_title_en
chapter_title

section_id
parent_section_id
section_title_jp
section_title_en
section_title
section_level

page_number
chunk_index
sort_order
token_count

content
content_hash

embedding_status
embedding_started_at
embedded_at
embedding_model
embedding_version
embedded_content_hash
embedding_retry_count
embedding_error

created_at
updated_at
```

Recommended read path:

```sql
SELECT *
FROM public.rag_chunks;
```

---

# RAG Data Consistency

RAG Schema v3 is designed around stable upsert behavior rather than blindly deleting and reinserting all chunks.

## Stable Chunk Identity

Logical chunk identity:

```text
document_id
+
section_id
+
chunk_index
```

represented by:

```sql
UNIQUE(document_id, section_id, chunk_index)
```

Re-importing the same logical chunk should preserve the existing `contents.id` whenever possible.

---

## Content Hash

Every chunk has:

```text
content_hash
```

The hash is used to determine whether the source content has changed.

---

## Content Change Handling

When important chunk data changes, the embedding lifecycle is reset.

Typical fields affecting the embedding state include:

```text
content_hash
chapter_id
page_number
token_count
sort_order
```

Changed chunks are reset to:

```text
embedding_status = PENDING
embedding_started_at = NULL
embedded_at = NULL
embedding_error = NULL
embedding_retry_count = 0
```

If the body content changes:

```text
embedded_content_hash = NULL
```

This prevents PostgreSQL from claiming that a new chunk is already represented by an old vector.

---

## Stale Chunk Deletion

When a previous chunk no longer exists after re-ingestion:

```text
old contents.id
      ↓
enqueue vector_delete_queue
      ↓
delete PostgreSQL chunk
      ↓
vector cleanup worker
      ↓
delete Qdrant point
```

This protects against orphan vectors.

---

# Embedding Lifecycle

Current states:

```text
PENDING
PROCESSING
COMPLETED
FAILED
```

Typical lifecycle:

```text
PENDING
   ↓ claim
PROCESSING
   ↓ embedding + vector write
COMPLETED
```

Failure:

```text
PROCESSING
   ↓
FAILED
```

Retry / recovery can return a failed or stale record to:

```text
PENDING
```

---

# Embedding and Qdrant

Embedding code is organized under:

```text
app/embedding/
├── embedding_client.py
├── embedding_repository.py
├── embedding_service.py
└── embedding_worker.py
```

Vector storage:

```text
app/vector/
├── base.py
└── qdrant_store.py
```

## Default Embedding Model

Default model:

```text
BAAI/bge-m3
```

Dense dimension:

```text
1024
```

Normalized embedding vectors are suitable for cosine similarity.

---

# Qdrant Integration

Typical local configuration:

```text
URL:
http://127.0.0.1:6333

Collection:
document_chunks

Dimension:
1024

Distance:
COSINE
```

Architecture rule:

```text
PostgreSQL
    =
Source of Truth

Qdrant
    =
Vector Search Index
```

PostgreSQL stores:

- Canonical text
- Document structure
- Chunk metadata
- Embedding state

Qdrant stores:

- Vector
- Point ID
- Search metadata

---

# GUI

GUI entry point:

```text
app/gui/application.py
```

Recommended development command:

```powershell
python -m app.gui.application
```

Do not use:

```powershell
python app\gui\application.py
```

because the project imports `app` as a top-level package.

---

## Main GUI Pages

```text
Document Conversion
JSON → PostgreSQL
PostgreSQL Settings
```

### Document Conversion

Supports:

- Multi-file selection
- Automatic format routing
- Structured conversion
- JSON output
- PostgreSQL storage
- Progress reporting
- Error display
- Batch processing

### JSON → PostgreSQL

Workflow:

```text
Structured JSON
    ↓
Validate
    ↓
Rebuild Document Model
    ↓
PostgresStorage
    ↓
RAG Schema v3
```

### PostgreSQL Settings

Supports:

- Host
- Port
- Database
- User
- Password
- Connect timeout
- Test connection
- Schema initialization / upgrade

Main schema button:

```text
Initialize / Upgrade RAG Database
```

which invokes:

```python
SchemaManager.ensure_schema()
```

---

# Quick Start

## Clone

```powershell
git clone https://github.com/SKYBREAKERZERO/ingestion-platform.git
cd ingestion-platform
```

## Create Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Install Dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Typical dependencies include:

```text
PyMuPDF
python-docx
python-pptx
openpyxl
Pillow
OpenCV
RapidOCR
ONNX Runtime
psycopg 3
Pydantic v2
PyYAML
ttkbootstrap
sentence-transformers
torch
qdrant-client
pywin32
```

---

# PostgreSQL Initialization

Typical local settings:

```text
Host:     127.0.0.1
Port:     5432
Database: rag
User:     postgres
```

Password should be supplied through:

```text
POSTGRES_PASSWORD
```

Example:

```powershell
$env:POSTGRES_PASSWORD = "your-password"
```

Test PostgreSQL:

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d rag
```

---

## Initialize Through GUI

Start:

```powershell
python -m app.gui.application
```

Then:

```text
PostgreSQL Settings
        ↓
Test PostgreSQL Connection
        ↓
Initialize / Upgrade RAG Database
```

Expected result:

```text
RAG Schema v3 ready
Tables: 7/7
Views:  1/1
```

---

## Verify with SQL

Tables:

```sql
\dt public.*
```

Expected:

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

View:

```sql
\dv public.*
```

Expected:

```text
rag_chunks
```

Schema version:

```sql
SELECT *
FROM public.schema_version;
```

---

# Running the Application

## GUI

```powershell
python -m app.gui.application
```

## Batch / Main

```powershell
python -m app.main
```

The main application reads:

```text
config/config.yaml
```

and processes input files from:

```text
input/
```

---

# Configuration

Typical configuration:

```yaml
application:
  name: "Document Ingestion Platform"
  environment: "development"

runtime:
  input_directory: "input"
  output_directory: "output"
  log_directory: "logs"

output:
  save_json: true

database:
  enabled: true
  host: "127.0.0.1"
  port: 5432
  database: "rag"
  user: "postgres"
  password_env: "POSTGRES_PASSWORD"
  connect_timeout: 10

chunk:
  max_length: 1000

logging:
  level: "INFO"
  file_name: "application.log"
```

## JSON Only

```yaml
output:
  save_json: true

database:
  enabled: false
```

## PostgreSQL Only

```yaml
output:
  save_json: false

database:
  enabled: true
```

At least one output target must be enabled.

---

# Project Structure

```text
document-ingestion-platform/
│
├── app/
│   ├── analyzer/
│   ├── builder/
│   ├── config/
│   ├── converter/
│   ├── database/
│   ├── embedding/
│   │   ├── embedding_client.py
│   │   ├── embedding_repository.py
│   │   ├── embedding_service.py
│   │   └── embedding_worker.py
│   ├── filter/
│   │   ├── common/
│   │   ├── pdf/
│   │   ├── docx/
│   │   ├── pptx/
│   │   └── xlsx/
│   ├── gui/
│   │   ├── application.py
│   │   └── application_backup.py
│   ├── loader/
│   ├── model/
│   ├── normalizer/
│   ├── parser/
│   ├── pipeline/
│   ├── processor/
│   ├── router/
│   ├── storage/
│   │   ├── postgres_storage.py
│   │   └── schema_manager.py
│   ├── utils/
│   ├── validator/
│   ├── vector/
│   │   ├── base.py
│   │   └── qdrant_store.py
│   └── main.py
│
├── config/
│   └── config.yaml
├── input/
├── output/
├── logs/
├── tests/
├── document_ingestion.spec
├── requirements.txt
├── README.md
├── README-EN.md
├── README-JP.md
└── .gitignore
```

---

# PyInstaller Build

Spec file:

```text
document_ingestion.spec
```

Build:

```powershell
python -m PyInstaller --clean --noconfirm .\document_ingestion.spec
```

GUI entry:

```text
app/gui/application.py
```

Expected executable:

```text
DocumentIngestion.exe
```

Current build characteristics:

```text
OneFile
Windows GUI
console=False
upx=False
```

The current desktop build explicitly excludes large AI/vector runtime components such as:

```text
torch
transformers
sentence_transformers
qdrant_client
```

Therefore the current EXE is focused on:

- Document conversion
- JSON generation
- PostgreSQL storage
- Schema management

Embedding / Qdrant execution remains a Python-runtime concern unless the spec is changed.

---

# Testing

Run tests:

```powershell
python -m pytest
```

Recommended coverage:

- Loader
- Parser
- Analyzer
- Title detection
- Pipeline
- PostgreSQL
- SchemaManager
- PostgresStorage
- Embedding repository
- Vector store

---

# Design Principles

## Single Responsibility

Each component should have a focused responsibility.

Examples:

```text
PDFLoader
    → Reads PDF

HeaderFooterFilter
    → Removes repeated headers / footers

StructureAnalyzer
    → Analyzes hierarchy

Chunker
    → Splits content

PostgresStorage
    → Persists RAG records

SchemaManager
    → Owns schema initialization and upgrades
```

## Router / Factory Decoupling

Application code does not need to hard-code format decisions.

```text
FormatRouter
    ↓
PipelineFactory
```

## Unified Document Model

All source formats converge into one business model.

## PostgreSQL as Source of Truth

```text
PostgreSQL
    =
Canonical data

Qdrant
    =
Vector retrieval index
```

## Non-Destructive Schema Upgrade

The schema manager should not perform destructive operations such as:

```text
DROP TABLE
TRUNCATE
DELETE business data
```

unless explicitly intended outside the normal upgrade path.

## Stable Import

Repeated ingestion should update existing logical records where possible instead of producing arbitrary new identities.

---

# Operational Notes

## Password Security

Do not commit database passwords into:

- `config.yaml`
- Git
- README
- Source code

Use environment variables such as:

```text
POSTGRES_PASSWORD
```

## Git Hygiene

Do not commit:

- `.venv/`
- `__pycache__/`
- Real enterprise documents
- Generated bulk JSON
- Logs
- Password files
- Model caches
- Build output

## RAG Table Safety

Core RAG tables:

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

Avoid manually modifying them through generic CRUD tools without understanding the consequences.

For example:

```sql
UPDATE contents ...
DELETE FROM contents ...
```

may bypass:

```text
content_hash
embedding_status
vector_delete_queue
Qdrant cleanup
```

---

# Recommended Workflow

## First Ingestion

```text
Input Document
    ↓
Document Conversion
    ↓
Structured JSON
    ↓
PostgreSQL
    ↓
contents.embedding_status = PENDING
    ↓
Embedding Worker
    ↓
Qdrant
    ↓
COMPLETED
```

## Document Update

```text
Updated Document
    ↓
Re-ingestion
    ↓
Stable Upsert
    ↓
Changed chunks → PENDING
    ↓
Removed chunks → vector_delete_queue
    ↓
Embedding / Vector refresh
```

## RAG Retrieval

```text
Question
  ↓
Query Embedding
  ↓
Qdrant Similarity Search
  ↓
content_id
  ↓
PostgreSQL rag_chunks
  ↓
Full text + hierarchy metadata
  ↓
LLM context
```

---

# Useful SQL

Embedding status:

```sql
SELECT
    embedding_status,
    COUNT(*)
FROM public.contents
GROUP BY embedding_status
ORDER BY embedding_status;
```

Pending chunks:

```sql
SELECT
    id,
    document_id,
    section_id,
    chunk_index,
    embedding_status
FROM public.contents
WHERE embedding_status = 'PENDING'
ORDER BY id
LIMIT 100;
```

Pending vector deletions:

```sql
SELECT *
FROM public.vector_delete_queue
WHERE processed_at IS NULL
ORDER BY id;
```

RAG view:

```sql
SELECT *
FROM public.rag_chunks
LIMIT 100;
```

---

# Roadmap

Potential next steps:

- Complete `embeddings` mapping persistence lifecycle
- Dedicated `vector_delete_queue` worker
- PostgreSQL ↔ Qdrant consistency audit
- Orphan vector detection
- Embedding model version migration
- Hybrid retrieval
  - Dense vector search
  - PostgreSQL full-text search
- Reranking
- Metadata filtering
- FastAPI RAG API
- OpenTelemetry
- Prometheus metrics
- Structured logging
- Worker service mode
- Docker Compose
  - PostgreSQL
  - Qdrant
  - Worker
- GitHub Actions CI
- Schema migration tests
- Large-document benchmarks
- Retrieval quality evaluation

---

# Repository

```text
https://github.com/SKYBREAKERZERO/ingestion-platform
```

---

# Summary

Document Ingestion Platform has evolved from a simple document conversion utility into a foundation for enterprise RAG ingestion:

```text
Enterprise Document Ingestion
        +
Document Cleaning
        +
Unified Document Model
        +
PostgreSQL RAG Schema v3
        +
Embedding State Management
        +
Vector Lifecycle Foundation
```

Core architecture:

```text
Document
   ↓
Clean / Parse / Analyze
   ↓
Chapter / Section / Chunk
   ↓
JSON
   ↓
PostgreSQL RAG Schema v3
   ↓
Embedding
   ↓
Qdrant
   ↓
RAG
```

**PostgreSQL is treated as the Source of Truth, while Qdrant is treated as the vector search index.**
