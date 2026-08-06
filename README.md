# Document Ingestion Platform

> 面向企业级 RAG（Retrieval-Augmented Generation）和知识库构建的统一文档摄取平台。

![Python](https://img.shields.io/badge/Python-3.12+-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![License](https://img.shields.io/badge/License-MIT-green)

---

# 项目简介

Document Ingestion Platform 是一个面向企业级知识库、RAG（Retrieval-Augmented Generation）以及大语言模型（LLM）应用开发的文档摄取平台。

它能够将企业中不同格式的文档统一解析为标准的数据结构，并生成适用于：

- PostgreSQL
- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma
- OpenSearch
- Amazon Bedrock Knowledge Base
- Azure AI Search

等知识库系统的数据。

与传统仅提取纯文本的解析器不同，本项目完整保留文档的层级结构，使模型能够理解文档之间的逻辑关系。

---

# 项目目标

企业文档通常来自多个来源：

- PDF
- Microsoft Word（DOCX）
- Microsoft PowerPoint（PPTX）
- Microsoft Excel（XLSX）

不同格式拥有完全不同的数据结构。

本项目的目标是：

**将所有格式统一转换为一种标准文档模型（Unified Document Model）。**

无论来源是什么，最终都能够得到一致的数据结构。

---

# 核心特性

## 支持格式

| 格式 | 状态 |
|------|------|
| PDF | ✅ 已支持 |
| DOCX | ✅ 已支持 |
| PPTX | ✅ 已支持 |
| XLSX | ✅ 已支持 |

---

## 统一数据模型

所有文档最终都会转换为统一的数据模型：

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

这样后续所有处理流程无需关心原始文件格式。

---

## 保留文档结构

解析过程中不会仅保留正文，而是完整保留：

- Chapter（章节）
- Section（节）
- Content（正文）
- Chunk（语义分块）

例如：

```
Document

├── Chapter 1
│
│   ├── Section 1.1
│   ├── Section 1.2
│   └── Section 1.3
│
├── Chapter 2
│
│   ├── Section 2.1
│   └── Section 2.2
│
└── Contents
```

这种层级结构能够显著提升 RAG 检索质量。

---

## 企业级 Pipeline

每种格式均采用统一 Pipeline：

```
Load

↓

Normalize

↓

Filter

↓

Parse

↓

Hierarchy Builder

↓

Content Filter

↓

Chunk

↓

Token Counter

↓

JSON Builder

↓

PostgreSQL
```

所有模块均遵循单一职责原则，可独立维护、替换和测试。

---

## 语义 Chunk

Chunk 并不是简单按照字符数切分。

而是遵循：

```
Chapter

↓

Section

↓

Paragraph

↓

Chunk
```

最大程度保证语义完整性。

---

## Token 统计

每个 Chunk 自动统计：

- Token 数量
- Chunk Index
- Page Number

方便：

- Embedding
- RAG
- Token Budget
- Context Window 控制

---

## PostgreSQL 存储

解析完成后自动保存到 PostgreSQL：

```
documents

↓

chapters

↓

sections

↓

contents
```

支持：

- SQL 查询
- 全文检索
- 后续向量化

---

## JSON 输出

每个文档都会生成标准 JSON：

```json
{
    "document": {},
    "metadata": {},
    "chapters": [],
    "sections": [],
    "contents": []
}
```

JSON 保留完整文档层级，可直接用于：

- 调试
- API
- 前端展示
- 二次开发

---

## 面向向量数据库

Chunk 输出格式符合主流向量数据库要求：

```json
{
    "id":"chunk-001",

    "text":"...",

    "metadata":{

        "document_id":"spec.pdf",

        "chapter_id":"2",

        "section_id":"2.1",

        "page":15,

        "chunk_index":0,

        "token_count":168
    }
}
```

可直接用于：

- OpenAI Embedding
- Amazon Titan Embedding
- BGE
- E5
- Jina Embedding

随后写入：

- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma

---

# 系统架构

```
                 +----------------------+
                 |     输入文档         |
                 +----------------------+

            PDF  DOCX  PPTX  XLSX

                     │

                     ▼

             Pipeline Factory

                     │

      ┌────────┬────────┬────────┬────────┐

      ▼        ▼        ▼        ▼

    PDF     DOCX     PPTX     XLSX

  Pipeline Pipeline Pipeline Pipeline

      └────────┴────────┴────────┘

                     │

                     ▼

              通用处理组件

                 Loader

                   │

                   ▼

               Normalizer

                   │

                   ▼

                 Filter

                   │

                   ▼

                 Parser

                   │

                   ▼

        Section Hierarchy Builder

                   │

                   ▼

             Content Filter

                   │

                   ▼

                 Chunker

                   │

                   ▼

             Token Counter

                   │

                   ▼

              JSON Builder

                   │

                   ▼

           PostgreSQL Storage
```

---

# 设计原则

本项目遵循企业级软件设计原则。

## 单一职责原则（SRP）

每个模块仅负责一个功能。

例如：

```
PDFLoader

↓

仅负责读取 PDF
```

```
HeaderFooterFilter

↓

仅负责删除页眉页脚
```

```
Chunker

↓

仅负责 Chunk 切分
```

模块之间互不耦合。

---

## Pipeline 架构

所有文档均采用：

```
Loader

↓

Filter

↓

Parser

↓

Processor

↓

Storage
```

每一层均可独立维护。

---

## 统一文档模型

所有格式最终统一转换为：

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

无需针对不同格式编写不同业务逻辑。

---

## 可扩展设计

新增一种文档格式通常仅需实现：

- Loader
- Parser
- Pipeline

并注册到 Pipeline Factory。

无需修改现有业务代码。

---

# 项目目录

```
document-ingestion-platform/

├── app/
│
├── analyzer/
├── builder/
├── filter/
│   ├── common/
│   ├── pdf/
│   ├── docx/
│   ├── pptx/
│   └── xlsx/
│
├── loader/
├── model/
├── normalizer/
├── parser/
├── pipeline/
├── processor/
├── router/
├── storage/
└── utils/
│
├── input/
├── output/
│
├── requirements.txt
└── README.md
```

---

# 当前功能

| 模块 | 状态 |
|------|------|
| PDF Loader | ✅ |
| DOCX Loader | ✅ |
| PPTX Loader | ✅ |
| XLSX Loader | ✅ |
| PDF Parser | ✅ |
| DOCX Parser | ✅ |
| PPTX Parser | ✅ |
| XLSX Parser | ✅ |
| Chunk | ✅ |
| Token Counter | ✅ |
| PostgreSQL | ✅ |
| JSON Builder | ✅ |
| 向量数据库输出 | ✅ |

