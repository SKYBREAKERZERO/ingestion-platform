# Document Ingestion Platform

> 面向企业级 RAG（Retrieval-Augmented Generation）、知识库构建与文档清洗的统一文档摄取平台。  
> 将 PDF、Word、PowerPoint、Excel、TXT 与图片统一转换为结构化文档模型，并可输出 JSON、写入 PostgreSQL RAG Schema v3，后续接入 Embedding 与 Qdrant 向量检索。

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RAG%20Schema%20v3-336791)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20Store-DC244C)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![Windows](https://img.shields.io/badge/Windows-Desktop-0078D6)

---

## 目录

- [项目简介](#项目简介)
- [核心目标](#核心目标)
- [当前能力](#当前能力)
- [支持格式](#支持格式)
- [总体架构](#总体架构)
- [文档处理 Pipeline](#文档处理-pipeline)
- [统一文档模型](#统一文档模型)
- [JSON 输出结构](#json-输出结构)
- [PostgreSQL RAG Schema v3](#postgresql-rag-schema-v3)
- [RAG 数据一致性设计](#rag-数据一致性设计)
- [Embedding 与 Qdrant](#embedding-与-qdrant)
- [GUI 功能](#gui-功能)
- [快速开始](#快速开始)
- [PostgreSQL 初始化](#postgresql-初始化)
- [运行方式](#运行方式)
- [配置说明](#配置说明)
- [项目目录](#项目目录)
- [PyInstaller 打包](#pyinstaller-打包)
- [测试](#测试)
- [设计原则](#设计原则)
- [注意事项](#注意事项)
- [后续演进方向](#后续演进方向)

---

# 项目简介

**Document Ingestion Platform** 是一个面向企业级知识库、RAG、LLM 应用和文档数据治理场景的统一文档摄取平台。

企业文档通常来自多种来源：

- PDF
- Microsoft Word
- Microsoft PowerPoint
- Microsoft Excel
- TXT
- 图片 / 扫描件

这些格式的数据结构完全不同。  
本项目通过统一 Router、Pipeline、Parser、Analyzer、Hierarchy Builder、Chunker 和 Storage 层，将不同来源的文件标准化为统一的文档结构：

```text
Document
├── Pages
├── Chapters
├── Sections
└── Contents / Chunks
```

最终可用于：

```text
原始文档
    ↓
文档清洗 / 结构解析
    ↓
统一 Document Model
    ↓
Structured JSON
    ↓
PostgreSQL RAG Schema v3
    ↓
Embedding
    ↓
Qdrant
    ↓
RAG / Knowledge Base / LLM
```

---

# 核心目标

本项目不是单纯的“文本提取器”。

核心目标是：

> **尽可能保留原始文档的结构、章节关系、页面定位与语义上下文，并输出稳定、可追踪、可重复导入的 RAG 数据。**

主要解决以下问题：

- 不同文件格式的数据结构不统一
- 文档标题、章节、子章节关系难以保持
- 页眉、页脚、空白页、噪声文本影响检索
- 简单字符切片破坏语义完整性
- 重复导入导致 Chunk ID 或数据库记录不稳定
- 文档变更后旧向量可能残留
- Embedding 任务状态不可追踪
- PostgreSQL 与向量数据库之间容易出现数据不一致

---

# 当前能力

| 模块 | 状态 |
|---|---|
| PDF Loader / Parser | ✅ |
| DOCX Loader / Parser | ✅ |
| PPTX Loader / Parser | ✅ |
| Legacy PPT 转换 | ✅ Windows + Microsoft PowerPoint |
| XLSX Loader / Parser | ✅ |
| TXT Loader / Parser | ✅ |
| PNG / JPG / JPEG 图片 Pipeline | ✅ |
| OCR 相关依赖 | ✅ RapidOCR / ONNX Runtime |
| Unicode Normalization | ✅ |
| Header / Footer Filter | ✅ |
| Page / Slide / Sheet Filter | ✅ |
| Paragraph / Table / Shape / Row Filter | ✅ |
| Title Detection / Join / Normalize | ✅ |
| Structure Analyzer | ✅ |
| Section Hierarchy Builder | ✅ |
| Content Filter | ✅ |
| Chunker | ✅ |
| Token Counter | ✅ |
| JSON Builder | ✅ |
| JSON → PostgreSQL | ✅ |
| PostgreSQL RAG Schema v3 | ✅ |
| Schema 初始化 / 非破坏升级 | ✅ |
| Embedding 状态管理 | ✅ |
| BGE-M3 Dense Embedding 模块 | ✅ |
| Qdrant Vector Store 模块 | ✅ |
| Stale Vector Delete Queue | ✅ |
| Windows GUI | ✅ |
| PyInstaller OneFile GUI Build | ✅ |

---

# 支持格式

当前 `FormatRouter` / `PipelineFactory` 正式注册：

| 格式 | 扩展名 | Pipeline | 备注 |
|---|---|---|---|
| PDF | `.pdf` | `PDFPipeline` | 支持结构提取与扫描件处理链路 |
| Word | `.docx` | `DOCXPipeline` | 使用 python-docx |
| Excel | `.xlsx` | `XLSXPipeline` | 使用 openpyxl |
| PowerPoint | `.pptx` | `PPTXPipeline` | 使用 python-pptx |
| Legacy PowerPoint | `.ppt` | `PPTPipeline` | 先转换为临时 `.pptx` |
| Text | `.txt` | `TXTPipeline` | 结构化文本处理 |
| Image | `.png` | `ImagePipeline` | OCR / 图像文本解析 |
| Image | `.jpg` | `ImagePipeline` | OCR / 图像文本解析 |
| Image | `.jpeg` | `ImagePipeline` | OCR / 图像文本解析 |

## Legacy `.ppt` 要求

`.ppt` 是旧版二进制 PowerPoint 格式。

当前实现使用 Windows COM 自动化：

```text
.ppt
  ↓
Microsoft PowerPoint COM
  ↓
temporary .pptx
  ↓
PPTXPipeline
```

因此需要：

- Windows
- Microsoft PowerPoint 已安装
- `pywin32`

如果机器没有 Microsoft PowerPoint，`.ppt` 无法转换。

---

# 总体架构

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
             ┌───────────────┬───────┼────────┬───────────┐
             ▼               ▼       ▼        ▼           ▼
          PDFPipeline    DOCXPipeline PPTX   XLSX       Image/TXT
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
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
             ┌─────────────┐                 ┌──────────────┐
             │ JSON Builder│                 │ PostgreSQL   │
             └──────┬──────┘                 │ RAG Schema v3│
                    │                        └───────┬──────┘
                    ▼                                │
             Structured JSON                         ▼
                                             Embedding Worker
                                                    │
                                                    ▼
                                                  Qdrant
                                                    │
                                                    ▼
                                                   RAG
```

---

# 文档处理 Pipeline

不同格式内部实现不同，但总体遵循相同的处理思想：

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

## 主要处理组件

### Loader

负责读取原始文件，尽量保留：

- Page / Slide / Sheet 信息
- Paragraph
- Table
- Shape
- Text Block
- Image / OCR Result
- 原始顺序信息

### Normalizer

负责统一字符和文本表现：

```text
Unicode
全角 / 半角
特殊字符
空白
换行
控制字符
```

### Filter

不同格式使用不同过滤器。

例如：

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

### Structure Analyzer

负责从原始文档中识别结构信息：

```text
Chapter
Section
Subsection
Title
Body
```

并结合：

- Title Detector
- Title Joiner
- Title Normalizer
- Section Hierarchy Builder

生成统一层级。

### Chunker

Chunk 不只是固定字符数硬切分。

优先保留：

```text
Chapter
  ↓
Section
  ↓
Content
  ↓
Semantic Chunk
```

从而减少语义断裂。

### Token Counter

每个 Chunk 保存：

- `token_count`
- `chunk_index`
- `page_number`
- `sort_order`

当前 Token Count 主要作为 RAG / Chunk Budget 的估算与控制字段。

---

# 统一文档模型

所有格式最终统一为：

```text
Document
├── metadata
├── pages[]
├── chapters[]
├── sections[]
└── contents[]
```

## Document

主要信息包括：

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

# JSON 输出结构

`JsonBuilder` 输出：

```json
{
  "document": {
    "document_id": "example-document-id",
    "file_name": "example.pdf",
    "file_type": "pdf",
    "created_at": "2026-08-31T00:00:00+00:00"
  },
  "metadata": {},
  "chapters": [],
  "sections": [],
  "contents": [],
  "vector_records": []
}
```

## `vector_records`

JSON Builder 可以额外生成适用于后续向量处理的记录：

```json
{
  "id": "chunk-xxxxxxxxxxxxxxxxxxxxxxxx",
  "text": "Chunk text...",
  "metadata": {
    "document_id": "doc-id",
    "file_name": "example.pdf",
    "document_type": "pdf",
    "chapter_id": "1",
    "chapter_title": "Chapter 1",
    "section_id": "1.1",
    "section_title": "Section 1.1",
    "page_number": 15,
    "chunk_index": 0,
    "token_count": 168
  }
}
```

`vector_records` 只负责构建向量输入数据结构：

> **不会在 JSON Builder 阶段生成 Embedding。**

---

# PostgreSQL RAG Schema v3

当前 PostgreSQL Schema 版本：

```text
RAG_SCHEMA_VERSION = 3
RAG_SCHEMA_NAME    = rag-schema-v3
```

Schema Manager：

```text
app/storage/schema_manager.py
```

负责：

- 创建全新 RAG Schema
- 升级旧数据库缺失字段
- 创建必要索引
- 避免重复创建等价 B-Tree Index
- 创建 `rag_chunks` View
- 记录 Schema Version
- 审计旧重复索引
- 不主动删除业务数据

---

## Schema 对象

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

文档主表。

主要字段：

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

唯一约束：

```text
UNIQUE(document_id)
```

---

## `chapters`

章节表。

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

唯一约束：

```text
UNIQUE(document_id, chapter_id)
```

外键：

```text
document_id
    → documents.document_id
    ON DELETE CASCADE
```

---

## `sections`

章节层级表。

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

唯一约束：

```text
UNIQUE(document_id, section_id)
```

---

## `contents`

RAG Chunk 主表。

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

唯一约束：

```text
UNIQUE(document_id, section_id, chunk_index)
```

其中：

> `contents.id` 是数据库中稳定的 Chunk 主键，可作为后续向量系统中的稳定引用 ID。

---

## `embeddings`

Embedding / Vector 映射表。

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

唯一约束：

```text
UNIQUE(content_id, model_name, model_version)
```

外键：

```text
content_id
    → contents.id
    ON DELETE CASCADE
```

该表用于描述 PostgreSQL Chunk、Embedding 模型版本与 Qdrant Point 之间的映射关系，并为后续一致性审计提供结构基础。

---

## `vector_delete_queue`

用于保存需要从向量数据库清理的旧 Chunk。

```text
id
content_id
document_id
reason
queued_at
processed_at
last_error
```

唯一约束：

```text
UNIQUE(content_id)
```

典型原因：

```text
STALE_CONTENT
```

---

## `schema_version`

记录当前 RAG Schema 版本：

```text
component
version
name
applied_at
```

当前：

```text
component = document_ingestion_rag
version   = 3
name      = rag-schema-v3
```

---

# RAG Indexes

Schema Manager 当前维护 / 复用以下逻辑索引：

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

Schema Manager 会先检查 PostgreSQL 中是否已经存在**等价索引**。

如果已经存在：

```text
不会重复创建
```

这样可以避免历史版本中重复索引不断累积。

---

# `rag_chunks` View

RAG Schema v3 创建统一读取 View：

```text
public.rag_chunks
```

该 View 将：

```text
documents
chapters
sections
contents
```

组合为面向 RAG 的 Chunk 读取结构。

主要字段：

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

RAG 查询层建议优先基于：

```sql
SELECT *
FROM public.rag_chunks;
```

而不是在应用层反复自行拼接四张结构表。

---

# RAG 数据一致性设计

RAG Schema v3 不再采用简单的：

```text
DELETE old chunks
INSERT new chunks
```

而是使用稳定 Upsert 逻辑。

## Stable Chunk Identity

Chunk 逻辑唯一键：

```text
document_id
+
section_id
+
chunk_index
```

对应：

```sql
UNIQUE(document_id, section_id, chunk_index)
```

同一个逻辑 Chunk 重复导入时：

```text
尽量保留原 contents.id
```

避免向量引用因为重新导入全部变化。

---

## `content_hash`

每个 Chunk 保存 SHA-256：

```text
content_hash
```

用于判断当前正文是否发生变化。

---

## Embedding 状态

当前状态模型：

```text
PENDING
PROCESSING
COMPLETED
FAILED
```

典型生命周期：

```text
PENDING
   ↓ Worker Claim
PROCESSING
   ↓ Embedding + Vector Write Success
COMPLETED
```

失败时：

```text
PROCESSING
   ↓
FAILED
```

可重新 Reset：

```text
FAILED / PROCESSING
   ↓
PENDING
```

---

## 内容变化自动重新向量化

如果已存在 Chunk 的关键内容发生变化，例如：

```text
content_hash
chapter_id
page_number
token_count
sort_order
```

PostgreSQL Storage 会将其重置：

```text
embedding_status = PENDING
embedding_started_at = NULL
embedded_at = NULL
embedding_error = NULL
embedding_retry_count = 0
```

正文 Hash 变化时：

```text
embedded_content_hash = NULL
```

从而防止：

```text
PostgreSQL 已是新文本
但 Qdrant 仍然使用旧向量
```

---

## Stale Chunk 删除

当重新导入后，旧 Chunk 已不再存在：

```text
旧 contents.id
      ↓
先写入 vector_delete_queue
      ↓
再删除 contents
```

目的：

```text
PostgreSQL
与
Qdrant
保持最终一致
```

避免产生 Qdrant orphan vector。

---

# Embedding 与 Qdrant

项目中已经拆分：

```text
app/embedding/
├── embedding_client.py
├── embedding_repository.py
├── embedding_service.py
└── embedding_worker.py

app/vector/
├── base.py
└── qdrant_store.py
```

---

## Embedding Client

默认模型：

```text
BAAI/bge-m3
```

默认 Dense Vector 维度：

```text
1024
```

默认：

```text
normalize_embeddings = True
```

用于 Cosine Similarity。

---

## Embedding Worker

Worker 负责：

```text
PostgreSQL contents
        ↓
Claim PENDING
        ↓
PROCESSING
        ↓
EmbeddingService
        ↓
Dense Vector
        ↓
Vector Store
        ↓
COMPLETED
```

支持：

- Batch 处理
- Retry 状态
- Stale PROCESSING Recovery
- Dry Run
- 错误隔离
- Worker Stop
- `PENDING / PROCESSING / COMPLETED / FAILED`

---

## Qdrant

当前 Qdrant 默认配置思想：

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

架构原则：

```text
PostgreSQL
    =
Source of Truth

Qdrant
    =
Vector Search Index
```

完整正文和业务结构以 PostgreSQL 为准。

Qdrant 主要保存：

```text
Vector
+
content_id
document_id
section_id
page_number
chunk_index
token_count
model_name
```

等检索 Metadata。

---

# GUI 功能

GUI 主入口：

```text
app/gui/application.py
```

开发环境推荐通过模块方式启动：

```powershell
python -m app.gui.application
```

不要直接：

```powershell
python app\gui\application.py
```

因为项目使用：

```python
from app....
```

作为顶层 Package Import。

---

## GUI 主要页面

```text
Document Conversion
JSON → PostgreSQL
PostgreSQL Settings
```

### Document Conversion

支持：

- 选择多个文档
- 自动识别格式
- 统一 Pipeline
- Generate JSON
- Save to PostgreSQL
- 批处理进度
- 日志与错误展示

### JSON → PostgreSQL

用于将本平台生成的 Structured JSON 再导入 PostgreSQL。

流程：

```text
Existing JSON
    ↓
读取 PostgreSQL Settings 当前 Scope / Database
    ↓
整批校验 JSON project_code
    ↓
Rebuild Document
    ↓
PostgresStorage（固定写入当前 Settings Database）
    ↓
RAG Schema v3
```

`JSON → PostgreSQL` 页面不再提供第二套数据库选择。目标由 `PostgreSQL Settings` 唯一控制：`21MM → rag_21mm`、`24MM → rag_24mm`、`Common → rag`。如果批量 JSON 中任意文件的 `project_code` 与当前 Scope 不一致，整批在写入前拒绝；Common 模式可兼容旧版没有 `project_code` 的通用 JSON，并在导入时标记为 `COMMON`。

### PostgreSQL Settings

支持：

- Host
- Port
- Database
- User
- Password
- Connect Timeout
- Test Connection
- 保存非敏感数据库配置
- 初始化 / 升级 RAG Database

按钮：

```text
Initialize / Upgrade RAG Database
```

实际调用：

```python
SchemaManager.ensure_schema()
```

---

# 快速开始

## 1. Clone

```powershell
git clone https://github.com/SKYBREAKERZERO/ingestion-platform.git
cd ingestion-platform
```

---

## 2. 创建虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell Execution Policy 阻止激活，可先为当前用户配置合适的执行策略。

---

## 3. 安装依赖

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

主要依赖包括：

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

# PostgreSQL 初始化

默认配置：

```text
Host:     127.0.0.1
Port:     5432
Database: rag
User:     postgres
```

密码通过：

```text
POSTGRES_PASSWORD
```

环境变量提供。

PowerShell 临时设置：

```powershell
$env:POSTGRES_PASSWORD = "your-password"
```

当前用户永久环境变量示例：

```powershell
[Environment]::SetEnvironmentVariable(
    "POSTGRES_PASSWORD",
    "your-password",
    "User"
)
```

重新打开 PowerShell 后生效。

---

## 手工测试数据库

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d rag
```

---

## GUI 一键初始化

启动：

```powershell
python -m app.gui.application
```

进入：

```text
PostgreSQL Settings
```

依次：

```text
Test PostgreSQL Connection
        ↓
Initialize / Upgrade RAG Database
```

初始化成功后应得到：

```text
Tables: 7/7
Views:  1/1
RAG Schema v3 ready
```

---

## SQL 验证

```sql
\dt public.*
```

应包含：

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

查看 View：

```sql
\dv public.*
```

应包含：

```text
rag_chunks
```

查看版本：

```sql
SELECT *
FROM public.schema_version;
```

---

# 运行方式

## GUI

推荐：

```powershell
python -m app.gui.application
```

---

## 批量 CLI / Main

`app/main.py` 会读取：

```text
config/config.yaml
```

并处理：

```text
input/
```

目录中的受支持文件。

启动：

```powershell
python -m app.main
```

默认：

```text
input/
    ↓
PipelineRouter
    ↓
按格式执行
    ↓
output/*.json
    +
PostgreSQL
```

Main 当前：

```text
recursive = false
continue_on_error = true
```

即：

- 默认不递归子目录
- 单个文件失败不会阻止其他文件继续处理

---

# 配置说明

默认：

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

---

## JSON Only

如果只希望生成 JSON：

```yaml
output:
  save_json: true

database:
  enabled: false
```

---

## Database Only

如果只写 PostgreSQL：

```yaml
output:
  save_json: false

database:
  enabled: true
```

至少必须启用一个输出目标：

```text
JSON
或
PostgreSQL
```

否则应用会拒绝启动。

---

# 日志

默认目录：

```text
logs/
```

默认日志：

```text
logs/application.log
```

GUI 也有自己的日志输出路径和界面日志。

日志会记录：

- 文件处理开始 / 结束
- Pipeline
- Pages / Chapters / Sections / Contents 数量
- PostgreSQL 写入
- 错误信息
- Batch 汇总

---

# 项目目录

```text
document-ingestion-platform/
│
├── app/
│   │
│   ├── analyzer/
│   │   ├── structure_analyzer.py
│   │   ├── title_detector.py
│   │   ├── title_joiner.py
│   │   └── title_normalizer.py
│   │
│   ├── builder/
│   │   └── json_builder.py
│   │
│   ├── config/
│   │   └── config_loader.py
│   │
│   ├── converter/
│   │   └── ppt_converter.py
│   │
│   ├── database/
│   │   └── connection.py
│   │
│   ├── embedding/
│   │   ├── embedding_client.py
│   │   ├── embedding_repository.py
│   │   ├── embedding_service.py
│   │   └── embedding_worker.py
│   │
│   ├── filter/
│   │   ├── common/
│   │   │   └── content_filter.py
│   │   ├── pdf/
│   │   │   ├── header_footer_filter.py
│   │   │   └── page_filter.py
│   │   ├── docx/
│   │   │   ├── paragraph_filter.py
│   │   │   └── table_filter.py
│   │   ├── pptx/
│   │   │   ├── shape_filter.py
│   │   │   └── slide_filter.py
│   │   └── xlsx/
│   │       ├── row_filter.py
│   │       └── sheet_filter.py
│   │
│   ├── gui/
│   │   ├── application.py
│   │   └── application_backup.py
│   │
│   ├── loader/
│   │   ├── base_loader.py
│   │   ├── pdf_loader.py
│   │   ├── docx_loader.py
│   │   ├── pptx_loader.py
│   │   ├── xlsx_loader.py
│   │   ├── txt_loader.py
│   │   ├── image_loader.py
│   │   └── loader_factory.py
│   │
│   ├── model/
│   │   ├── block.py
│   │   ├── chapter.py
│   │   ├── content.py
│   │   ├── document.py
│   │   ├── page.py
│   │   └── section.py
│   │
│   ├── normalizer/
│   │   └── unicode_normalizer.py
│   │
│   ├── parser/
│   │   ├── pdf_parser.py
│   │   ├── docx_parser.py
│   │   ├── pptx_parser.py
│   │   ├── xlsx_parser.py
│   │   ├── txt_parser.py
│   │   ├── image_parser.py
│   │   └── structured_text_parser.py
│   │
│   ├── pipeline/
│   │   ├── ingestion_pipeline.py
│   │   ├── pipeline_factory.py
│   │   ├── pdf_pipeline.py
│   │   ├── docx_pipeline.py
│   │   ├── pptx_pipeline.py
│   │   ├── ppt_pipeline.py
│   │   ├── xlsx_pipeline.py
│   │   ├── txt_pipeline.py
│   │   └── image_pipeline.py
│   │
│   ├── processor/
│   │   ├── chunker.py
│   │   ├── deduplicator.py
│   │   ├── heading_merger.py
│   │   ├── section_hierarchy.py
│   │   ├── sort_order_assigner.py
│   │   ├── title_sentence_corrector.py
│   │   └── token_counter.py
│   │
│   ├── router/
│   │   ├── format_router.py
│   │   └── pipeline_router.py
│   │
│   ├── storage/
│   │   ├── postgres_storage.py
│   │   └── schema_manager.py
│   │
│   ├── utils/
│   │   ├── exceptions.py
│   │   └── runtime_path.py
│   │
│   ├── validator/
│   │   └── document_validator.py
│   │
│   ├── vector/
│   │   ├── base.py
│   │   └── qdrant_store.py
│   │
│   └── main.py
│
├── config/
│   └── config.yaml
│
├── input/
│   └── .gitkeep
│
├── output/
│   └── .gitkeep
│
├── logs/
│   └── .gitkeep
│
├── tests/
│   ├── test_analyzer.py
│   ├── test_database.py
│   ├── test_loader.py
│   ├── test_model.py
│   ├── test_pipeline.py
│   └── test_title_detector.py
│
├── document_ingestion.spec
├── requirements.txt
├── README.md
├── README-EN.md
├── README-JP.md
└── .gitignore
```

---

# PyInstaller 打包

当前 Spec：

```text
document_ingestion.spec
```

正确构建命令：

```powershell
python -m PyInstaller --clean --noconfirm .\document_ingestion.spec
```

不是：

```powershell
python -m PyInstaller DataConsole.spec
```

---

## Build Entry

Spec 当前入口：

```text
app/gui/application.py
```

最终 EXE：

```text
DocumentIngestion.exe
```

配置：

```text
OneFile
Windows GUI
console=False
upx=False
```

---

## PyInstaller 已显式收集

包括：

```text
ttkbootstrap
Pillow
PyMuPDF
python-docx
python-pptx
openpyxl
psycopg
PyYAML
RapidOCR
ONNX Runtime
pywin32 / PowerPoint COM
```

---

## EXE 当前不打包 Embedding / Vector AI 模块

`document_ingestion.spec` 当前明确排除：

```text
torch
transformers
sentence_transformers
qdrant_client
```

因此：

> **当前桌面 EXE 的定位是文档转换、JSON、PostgreSQL 与 Schema 管理，不包含本地 Embedding / Qdrant 运行时。**

如果未来需要将 Embedding Worker 与 Qdrant 一并集成进 EXE，需要调整 Spec 并评估：

- EXE 体积
- Torch
- Transformers
- SentenceTransformer model
- CUDA / CPU runtime
- Qdrant Client
- 模型缓存目录

---

# 测试

项目已包含基础测试：

```text
tests/
```

执行：

```powershell
python -m pytest
```

建议至少覆盖：

```text
Loader
Parser
Analyzer
Title Detector
Pipeline
Database
Schema Manager
PostgresStorage
Embedding Repository
Vector Store
```

---

# 设计原则

## 1. Single Responsibility Principle

每个组件尽量只承担一个职责。

例如：

```text
PDFLoader
    → 读取 PDF

HeaderFooterFilter
    → 清理页眉页脚

StructureAnalyzer
    → 分析结构

Chunker
    → Chunk 切分

PostgresStorage
    → PostgreSQL 数据持久化

SchemaManager
    → Schema 初始化 / Upgrade
```

---

## 2. Router / Factory 解耦

Main 与 GUI 不直接写死：

```text
.pdf -> PDFPipeline
.docx -> DOCXPipeline
```

而是通过：

```text
FormatRouter
    ↓
PipelineFactory
```

统一选择。

---

## 3. Unified Document Model

后续 Storage / JSON / Embedding 不关心输入来源。

```text
PDF
DOCX
PPTX
XLSX
TXT
Image
   ↓
统一 Document
```

---

## 4. PostgreSQL Is Source of Truth

RAG 业务结构、Chunk 正文和状态以 PostgreSQL 为准。

```text
PostgreSQL
    =
Source of Truth
```

Qdrant 负责：

```text
Vector Search Index
```

---

## 5. Non-Destructive Schema Upgrade

`SchemaManager.ensure_schema()` 不进行：

```text
DROP TABLE
TRUNCATE
DELETE business data
```

升级原则：

```text
缺表 → CREATE
缺字段 → ALTER ADD
缺索引 → CREATE
等价索引存在 → REUSE
旧重复索引 → AUDIT ONLY
```

---

## 6. Idempotent / Stable Data Import

文档重复导入通过 Upsert：

```text
Document
Chapter
Section
Content
```

尽量避免产生无意义的全量新 ID。

---

# 安全与运维注意事项

## PostgreSQL 密码

不要将密码写入：

```text
config.yaml
Git
README
源码
```

使用：

```text
POSTGRES_PASSWORD
```

环境变量。

---

## `.gitignore`

当前项目已经忽略：

```text
.venv/
__pycache__/
input/*
output/*
logs/*
.env
build/
dist/
*.log
```

不要将真实企业文档、生成的大量 JSON、数据库密码和模型缓存提交到 GitHub。

---

## 数据库管理

RAG 核心表：

```text
documents
chapters
sections
contents
embeddings
vector_delete_queue
schema_version
```

不建议通过普通数据库管理器随意：

```sql
UPDATE contents ...
DELETE FROM contents ...
```

因为这可能绕过：

```text
content_hash
embedding_status
vector_delete_queue
Qdrant cleanup
```

生产管理工具应采用 RAG-aware 的写入 / 删除逻辑。

---

# 推荐工作流

## 文档首次导入

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

---

## 文档更新

```text
Updated Document
    ↓
Re-ingestion
    ↓
Upsert same logical chunks
    ↓
Changed chunks → PENDING
    ↓
Removed chunks → vector_delete_queue
    ↓
Embedding / Vector refresh
```

---

## RAG 查询

推荐：

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
完整正文 + Chapter + Section Metadata
  ↓
LLM Context
```

---

# 后续演进方向

建议继续完善：

- `embeddings` 映射表与 Worker 的完整持久化闭环
- `vector_delete_queue` Worker
- PostgreSQL ↔ Qdrant 一致性 Audit
- Qdrant orphan vector 自动扫描
- Embedding Model Version Migration
- Hybrid Search
  - Dense Vector
  - PostgreSQL Full Text Search
- Reranker
- Metadata Filter
- RAG API
- FastAPI Service
- OpenTelemetry
- Prometheus Metrics
- Structured Logging
- DLQ / Retry Policy
- Background Worker Service
- Docker Compose
  - PostgreSQL
  - Qdrant
  - Worker
- CI / GitHub Actions
- Schema migration test
- Large document benchmark
- Retrieval quality evaluation

---

# 开发常用命令

## 启动 GUI

```powershell
python -m app.gui.application
```

## 启动批处理

```powershell
python -m app.main
```

## PostgreSQL

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d rag
```

## 查看表

```sql
\dt public.*
```

## 查看 View

```sql
\dv public.*
```

## 查看 RAG Schema Version

```sql
SELECT *
FROM public.schema_version;
```

## 查看 Embedding 状态

```sql
SELECT
    embedding_status,
    COUNT(*)
FROM public.contents
GROUP BY embedding_status
ORDER BY embedding_status;
```

## 查看待向量化 Chunk

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

## 查看待删除 Vector

```sql
SELECT *
FROM public.vector_delete_queue
WHERE processed_at IS NULL
ORDER BY id;
```

## 打包

```powershell
python -m PyInstaller --clean --noconfirm .\document_ingestion.spec
```

---

# Repository

GitHub:

```text
https://github.com/SKYBREAKERZERO/ingestion-platform
```

---

# Summary

Document Ingestion Platform 当前已经从单纯的“文件解析 / JSON 导出工具”演进为：

```text
Enterprise Document Ingestion
        +
Structured Document Cleaning
        +
Unified Document Model
        +
RAG Schema v3
        +
Embedding State Management
        +
Vector Lifecycle Foundation
```

其核心数据链路为：

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

**PostgreSQL 作为 Source of Truth，Qdrant 作为 Vector Search Index。**  
通过稳定 Chunk Identity、`content_hash`、Embedding 状态与 `vector_delete_queue`，为后续企业级 RAG 数据一致性和向量生命周期管理提供基础。


## Common / Generic Document Mode

The GUI processing-scope selector supports `21MM`, `24MM`, and `Common`.

- `21MM` / `24MM`: specification-document mode with dictionary-driven specification classification.
- `Common`: general-purpose mode for news, meeting documents, screenshots, reports and other non-specification material. It uses the same parsing/chunking/JSON/PostgreSQL schema but does not assign specification taxonomy fields.
- PostgreSQL Settings shows one `Database` field. The selected scope remembers its own database name; the default is `rag`.
- In JSON-only mode, output files are separated into `21MM`, `24MM`, or `COMMON` folders.
