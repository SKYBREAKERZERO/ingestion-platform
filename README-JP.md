# Document Ingestion Platform

> エンタープライズ向け RAG（Retrieval-Augmented Generation）、ナレッジベース、LLM アプリケーションのための統合ドキュメント取り込み・クレンジング・構造化プラットフォームです。

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RAG%20Schema%20v3-336791)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20Store-DC244C)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![Windows](https://img.shields.io/badge/Windows-Desktop-0078D6)

---

## 目次

- [概要](#概要)
- [プロジェクトの目的](#プロジェクトの目的)
- [現在の機能](#現在の機能)
- [対応フォーマット](#対応フォーマット)
- [全体アーキテクチャ](#全体アーキテクチャ)
- [ドキュメント処理 Pipeline](#ドキュメント処理-pipeline)
- [統一ドキュメントモデル](#統一ドキュメントモデル)
- [JSON 出力](#json-出力)
- [PostgreSQL RAG Schema v3](#postgresql-rag-schema-v3)
- [Schema 管理](#schema-管理)
- [RAG データ整合性](#rag-データ整合性)
- [Embedding ライフサイクル](#embedding-ライフサイクル)
- [Qdrant 連携](#qdrant-連携)
- [GUI](#gui)
- [クイックスタート](#クイックスタート)
- [PostgreSQL 初期化](#postgresql-初期化)
- [起動方法](#起動方法)
- [設定](#設定)
- [プロジェクト構成](#プロジェクト構成)
- [PyInstaller ビルド](#pyinstaller-ビルド)
- [テスト](#テスト)
- [設計原則](#設計原則)
- [運用上の注意](#運用上の注意)
- [推奨ワークフロー](#推奨ワークフロー)
- [今後の拡張](#今後の拡張)

---

# 概要

**Document Ingestion Platform** は、以下の用途を想定したエンタープライズ向けドキュメント取り込み基盤です。

- RAG
- 社内ナレッジベース
- LLM アプリケーション
- 文書クレンジング
- 文書構造解析
- JSON 変換
- PostgreSQL 保存
- Embedding 処理
- Vector Search

企業文書は一般的に複数の形式で存在します。

- PDF
- Microsoft Word
- Microsoft PowerPoint
- Microsoft Excel
- TXT
- 画像 / スキャン文書

各フォーマットは内部構造が異なるため、本プロジェクトでは以下の共通アーキテクチャで標準化します。

```text
入力ファイル
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

最終的な統一モデルは以下です。

```text
Document
├── Pages
├── Chapters
├── Sections
└── Contents / Chunks
```

---

# プロジェクトの目的

本プロジェクトは単純なテキスト抽出ツールではありません。

目的は次のとおりです。

> 元文書の章・節・ページ・順序・意味構造を可能な限り保持し、RAG に適した安定したデータへ変換すること。

主な課題：

- フォーマットごとの構造差
- 章・節構造の消失
- ヘッダー / フッター等のノイズ
- 空ページ・低価値ページ
- 単純文字分割による意味破壊
- 再取り込み時の Chunk ID 不安定化
- 文書更新後の古い Vector 残留
- Embedding 状態の追跡不足
- PostgreSQL と Vector DB の不整合

---

# 現在の機能

| モジュール | 状態 |
|---|---|
| PDF Loader / Parser | ✅ |
| DOCX Loader / Parser | ✅ |
| PPTX Loader / Parser | ✅ |
| Legacy PPT 変換 | ✅ Windows + Microsoft PowerPoint |
| XLSX Loader / Parser | ✅ |
| TXT Loader / Parser | ✅ |
| PNG / JPG / JPEG Image Pipeline | ✅ |
| OCR 関連 | ✅ RapidOCR / ONNX Runtime |
| Unicode 正規化 | ✅ |
| Header / Footer Filter | ✅ |
| Page / Slide / Sheet Filter | ✅ |
| Paragraph / Table / Shape / Row Filter | ✅ |
| Title Detection | ✅ |
| Title Join | ✅ |
| Title Normalize | ✅ |
| Structure Analyzer | ✅ |
| Section Hierarchy Builder | ✅ |
| Content Filter | ✅ |
| Chunker | ✅ |
| Token Counter | ✅ |
| JSON Builder | ✅ |
| JSON → PostgreSQL | ✅ |
| PostgreSQL RAG Schema v3 | ✅ |
| Schema 初期化 | ✅ |
| 非破壊 Schema Upgrade | ✅ |
| Embedding 状態管理 | ✅ |
| BGE-M3 Embedding モジュール | ✅ |
| Qdrant Vector Store | ✅ |
| Vector Delete Queue | ✅ |
| Windows GUI | ✅ |
| PyInstaller OneFile GUI Build | ✅ |

---

# 対応フォーマット

現在の `FormatRouter` / `PipelineFactory` は以下をサポートしています。

| フォーマット | 拡張子 | Pipeline | 備考 |
|---|---|---|---|
| PDF | `.pdf` | `PDFPipeline` | PDF 構造解析 |
| Word | `.docx` | `DOCXPipeline` | python-docx |
| Excel | `.xlsx` | `XLSXPipeline` | openpyxl |
| PowerPoint | `.pptx` | `PPTXPipeline` | python-pptx |
| Legacy PowerPoint | `.ppt` | `PPTPipeline` | `.pptx` へ変換 |
| Text | `.txt` | `TXTPipeline` | 構造化テキスト処理 |
| Image | `.png` | `ImagePipeline` | OCR |
| Image | `.jpg` | `ImagePipeline` | OCR |
| Image | `.jpeg` | `ImagePipeline` | OCR |

## Legacy `.ppt`

旧形式 `.ppt` は Windows COM を利用します。

```text
.ppt
  ↓
Microsoft PowerPoint COM
  ↓
temporary .pptx
  ↓
PPTXPipeline
```

必要条件：

- Windows
- Microsoft PowerPoint
- `pywin32`

---

# 全体アーキテクチャ

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
                 ┌───────────────────┼────────────────────┐
                 ▼                   ▼                    ▼
              PDF/DOCX            PPT/XLSX            TXT/Image
              Pipelines            Pipelines            Pipelines
                 └───────────────────┼────────────────────┘
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

# ドキュメント処理 Pipeline

フォーマットごとに内部実装は異なりますが、概念上は共通処理フローを使用します。

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

元ファイルから以下の情報を取得します。

- Page / Slide / Sheet
- Paragraph
- Table
- Shape
- Text Block
- Image
- OCR 結果
- 元の並び順

## Normalizer

以下を正規化します。

```text
Unicode
全角 / 半角
空白
改行
制御文字
特殊文字
```

## Filter

例：

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

## Structure Analyzer

以下を検出します。

```text
Chapter
Section
Subsection
Title
Body
```

関連コンポーネント：

- Title Detector
- Title Joiner
- Title Normalizer
- Section Hierarchy Builder

## Chunker

単純な固定文字数分割だけではなく、可能な限り意味構造を維持します。

```text
Chapter
  ↓
Section
  ↓
Content
  ↓
Semantic Chunk
```

## Token Counter

各 Chunk では以下を管理します。

```text
token_count
chunk_index
page_number
sort_order
```

用途：

- Embedding
- RAG Context Budget
- Retrieval Analysis
- Context Window Control

---

# 統一ドキュメントモデル

すべての入力形式は最終的に以下へ統一されます。

```text
Document
├── metadata
├── pages[]
├── chapters[]
├── sections[]
└── contents[]
```

## Document

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

# JSON 出力

`JsonBuilder` は構造化 JSON を生成します。

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

Embedding 用の入力データ構造も生成できます。

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

JSON Builder 自体は Embedding を生成しません。

---

# PostgreSQL RAG Schema v3

現在の Schema Version：

```text
RAG_SCHEMA_VERSION = 3
RAG_SCHEMA_NAME    = rag-schema-v3
```

Schema 定義管理：

```text
app/storage/schema_manager.py
```

現在の構造：

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

文書マスターテーブル。

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

Unique：

```text
UNIQUE(document_id)
```

---

## `chapters`

章テーブル。

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

Unique：

```text
UNIQUE(document_id, chapter_id)
```

---

## `sections`

節階層テーブル。

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

Unique：

```text
UNIQUE(document_id, section_id)
```

---

## `contents`

RAG Chunk の中心テーブルです。

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

論理 Unique：

```text
UNIQUE(document_id, section_id, chunk_index)
```

`contents.id` は PostgreSQL 上の安定した Chunk 主キーです。

Vector 側の安定参照 ID として利用可能な設計です。

---

## `embeddings`

Embedding / Vector マッピングテーブル。

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

Unique：

```text
UNIQUE(content_id, model_name, model_version)
```

Foreign Key：

```text
content_id
    → contents.id
    ON DELETE CASCADE
```

---

## `vector_delete_queue`

古い Vector を削除するための Queue です。

```text
id
content_id
document_id
reason
queued_at
processed_at
last_error
```

Unique：

```text
UNIQUE(content_id)
```

代表的な reason：

```text
STALE_CONTENT
```

---

## `schema_version`

RAG Schema のバージョンを管理します。

```text
component
version
name
applied_at
```

現在：

```text
component = document_ingestion_rag
version   = 3
name      = rag-schema-v3
```

---

# Schema 管理

`SchemaManager.ensure_schema()` は以下を担当します。

- 初回 Schema 作成
- 非破壊 Upgrade
- 不足 Column の追加
- 不足 Index の作成
- 等価 Index の再利用
- `rag_chunks` View 作成
- Schema Version 記録
- Legacy Duplicate Index の Audit
- 業務データを破壊しない Upgrade

基本方針：

```text
Table がない     → CREATE
Column がない    → ALTER ADD
Index がない     → CREATE
等価 Index がある → REUSE
旧重複 Index      → AUDIT
業務データ         → PRESERVE
```

Schema 定義の Single Source of Truth として `SchemaManager` を利用します。

---

# RAG Indexes

現在の主要 Index：

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

PostgreSQL 内に等価 Index が存在する場合は再利用します。

---

# `rag_chunks` View

RAG Schema v3 は以下の View を作成します。

```text
public.rag_chunks
```

この View は：

```text
documents
chapters
sections
contents
```

を統合して、RAG 向け Chunk 形式で提供します。

代表フィールド：

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

推奨参照：

```sql
SELECT *
FROM public.rag_chunks;
```

---

# RAG データ整合性

RAG Schema v3 では、単純な全 DELETE / 全 INSERT ではなく、安定した Upsert を重視します。

## Stable Chunk Identity

Chunk の論理キー：

```text
document_id
+
section_id
+
chunk_index
```

DB 制約：

```sql
UNIQUE(document_id, section_id, chunk_index)
```

同一論理 Chunk を再取り込みする場合、可能な限り既存 `contents.id` を維持します。

---

## `content_hash`

各 Chunk に：

```text
content_hash
```

を保存します。

本文が変化したかどうかを検出するために使用します。

---

## 内容更新時

Embedding に影響するフィールドが変化した場合、状態を再設定します。

例：

```text
content_hash
chapter_id
page_number
token_count
sort_order
```

変更された Chunk：

```text
embedding_status = PENDING
embedding_started_at = NULL
embedded_at = NULL
embedding_error = NULL
embedding_retry_count = 0
```

本文 Hash が変わった場合：

```text
embedded_content_hash = NULL
```

これにより、

```text
PostgreSQL = 新本文
Qdrant     = 旧 Vector
```

という不整合を防止します。

---

## Stale Chunk 削除

再取り込み後に不要になった旧 Chunk：

```text
old contents.id
      ↓
vector_delete_queue に登録
      ↓
PostgreSQL から削除
      ↓
Vector Cleanup Worker
      ↓
Qdrant Point 削除
```

目的：

```text
Orphan Vector を作らない
```

---

# Embedding ライフサイクル

現在の Status：

```text
PENDING
PROCESSING
COMPLETED
FAILED
```

通常：

```text
PENDING
   ↓ claim
PROCESSING
   ↓ embedding + vector write
COMPLETED
```

失敗：

```text
PROCESSING
   ↓
FAILED
```

Retry / Recovery：

```text
FAILED / stale PROCESSING
   ↓
PENDING
```

---

# Embedding / Qdrant モジュール

Embedding 関連：

```text
app/embedding/
├── embedding_client.py
├── embedding_repository.py
├── embedding_service.py
└── embedding_worker.py
```

Vector 関連：

```text
app/vector/
├── base.py
└── qdrant_store.py
```

## Default Embedding Model

```text
BAAI/bge-m3
```

Dense Dimension：

```text
1024
```

Cosine Similarity を前提として正規化 Vector を利用できます。

---

# Qdrant 連携

代表的なローカル設定：

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

設計ルール：

```text
PostgreSQL
    =
Source of Truth

Qdrant
    =
Vector Search Index
```

PostgreSQL：

- 正式本文
- 文書構造
- Chunk Metadata
- Embedding Status

Qdrant：

- Vector
- Point ID
- 検索用 Metadata

---

# GUI

GUI Entry：

```text
app/gui/application.py
```

開発時の推奨起動：

```powershell
python -m app.gui.application
```

以下の直接実行は推奨しません。

```powershell
python app\gui\application.py
```

本プロジェクトでは `app` を Top-level Package として Import しているためです。

---

## GUI メイン画面

```text
Document Conversion
JSON → PostgreSQL
PostgreSQL Settings
```

### Document Conversion

主な機能：

- 複数ファイル選択
- 自動 Format Routing
- 構造化変換
- JSON 保存
- PostgreSQL 保存
- Progress 表示
- Error 表示
- Batch 処理

### JSON → PostgreSQL

```text
Structured JSON
    ↓
Validate
    ↓
Document Model 再構築
    ↓
PostgresStorage
    ↓
RAG Schema v3
```

### PostgreSQL Settings

設定項目：

- Host
- Port
- Database
- User
- Password
- Connect Timeout
- Test Connection
- Schema Initialization / Upgrade

Schema ボタン：

```text
Initialize / Upgrade RAG Database
```

内部：

```python
SchemaManager.ensure_schema()
```

---

# クイックスタート

## Clone

```powershell
git clone https://github.com/SKYBREAKERZERO/ingestion-platform.git
cd ingestion-platform
```

## Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Install

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

主な依存：

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

# PostgreSQL 初期化

代表設定：

```text
Host:     127.0.0.1
Port:     5432
Database: rag
User:     postgres
```

Password：

```text
POSTGRES_PASSWORD
```

PowerShell：

```powershell
$env:POSTGRES_PASSWORD = "your-password"
```

接続確認：

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d rag
```

---

## GUI から初期化

```powershell
python -m app.gui.application
```

画面操作：

```text
PostgreSQL Settings
        ↓
Test PostgreSQL Connection
        ↓
Initialize / Upgrade RAG Database
```

成功時：

```text
RAG Schema v3 ready
Tables: 7/7
Views:  1/1
```

---

## SQL 確認

Table：

```sql
\dt public.*
```

期待：

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

View：

```sql
\dv public.*
```

期待：

```text
rag_chunks
```

Version：

```sql
SELECT *
FROM public.schema_version;
```

---

# 起動方法

## GUI

```powershell
python -m app.gui.application
```

## Batch / Main

```powershell
python -m app.main
```

`app.main` は：

```text
config/config.yaml
```

を読み込み、

```text
input/
```

配下の対象ファイルを処理します。

---

# 設定

例：

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

JSON または PostgreSQL の最低どちらか一つを有効化する必要があります。

---

# プロジェクト構成

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

# PyInstaller ビルド

Spec：

```text
document_ingestion.spec
```

Build：

```powershell
python -m PyInstaller --clean --noconfirm .\document_ingestion.spec
```

GUI Entry：

```text
app/gui/application.py
```

生成：

```text
DocumentIngestion.exe
```

現在の特徴：

```text
OneFile
Windows GUI
console=False
upx=False
```

現在の Desktop EXE では大規模 AI / Vector Runtime を除外しています。

```text
torch
transformers
sentence_transformers
qdrant_client
```

したがって、現状の EXE は主に：

- Document Conversion
- JSON
- PostgreSQL
- Schema Management

を担当します。

Embedding / Qdrant を EXE に含める場合は Spec の変更が必要です。

---

# テスト

```powershell
python -m pytest
```

推奨 Coverage：

- Loader
- Parser
- Analyzer
- Title Detector
- Pipeline
- PostgreSQL
- SchemaManager
- PostgresStorage
- Embedding Repository
- Vector Store

---

# 設計原則

## Single Responsibility

各コンポーネントは責務を分離します。

```text
PDFLoader
    → PDF Read

HeaderFooterFilter
    → Header / Footer 除去

StructureAnalyzer
    → 文書構造解析

Chunker
    → Chunk 分割

PostgresStorage
    → RAG Data Persistence

SchemaManager
    → Schema 初期化 / Upgrade
```

## Router / Factory

```text
FormatRouter
    ↓
PipelineFactory
```

により、フォーマット判定を共通化します。

## Unified Document Model

すべての Format を共通 Business Model に統一します。

## PostgreSQL as Source of Truth

```text
PostgreSQL
    =
Canonical Data

Qdrant
    =
Vector Retrieval Index
```

## Non-Destructive Upgrade

通常の Upgrade で：

```text
DROP TABLE
TRUNCATE
DELETE business data
```

を行わない設計です。

## Stable Import

同一論理データの再取り込み時には、可能な限り既存 ID を維持します。

---

# 運用上の注意

## Password

以下へ DB Password を保存しないでください。

- `config.yaml`
- Git
- README
- Source Code

環境変数：

```text
POSTGRES_PASSWORD
```

を利用してください。

## Git 管理

Commit 非推奨：

- `.venv/`
- `__pycache__/`
- 実際の社内文書
- 大量生成 JSON
- Logs
- Password Files
- Model Cache
- Build Output

## RAG Core Tables

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

Generic CRUD Tool から安易に：

```sql
UPDATE contents ...
DELETE FROM contents ...
```

を実行すると、

```text
content_hash
embedding_status
vector_delete_queue
Qdrant cleanup
```

の整合性ルールを回避する可能性があります。

---

# 推奨ワークフロー

## 初回取り込み

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

## 文書更新

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
Embedding / Vector Refresh
```

## RAG 検索

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
本文 + Chapter + Section Metadata
  ↓
LLM Context
```

---

# よく使う SQL

Embedding Status：

```sql
SELECT
    embedding_status,
    COUNT(*)
FROM public.contents
GROUP BY embedding_status
ORDER BY embedding_status;
```

Pending Chunk：

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

Vector Delete Queue：

```sql
SELECT *
FROM public.vector_delete_queue
WHERE processed_at IS NULL
ORDER BY id;
```

RAG View：

```sql
SELECT *
FROM public.rag_chunks
LIMIT 100;
```

---

# 今後の拡張

候補：

- `embeddings` Mapping Persistence の完全化
- `vector_delete_queue` Worker
- PostgreSQL ↔ Qdrant 整合性 Audit
- Orphan Vector Detection
- Embedding Model Version Migration
- Hybrid Search
  - Dense Vector
  - PostgreSQL Full Text Search
- Reranker
- Metadata Filter
- FastAPI RAG API
- OpenTelemetry
- Prometheus Metrics
- Structured Logging
- Worker Service 化
- Docker Compose
  - PostgreSQL
  - Qdrant
  - Worker
- GitHub Actions CI
- Schema Migration Test
- Large Document Benchmark
- Retrieval Quality Evaluation

---

# Repository

```text
https://github.com/SKYBREAKERZERO/ingestion-platform
```

---

# Summary

Document Ingestion Platform は単純な文書変換ツールから、Enterprise RAG Ingestion 基盤へ拡張されています。

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

コアフロー：

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

**PostgreSQL を Source of Truth、Qdrant を Vector Search Index として扱う設計です。**
