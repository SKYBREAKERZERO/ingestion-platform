# Document Ingestion Platform

> An enterprise-grade document ingestion platform for Retrieval-Augmented Generation (RAG), Knowledge Base construction, and Large Language Model (LLM) applications.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![License](https://img.shields.io/badge/License-MIT-green)

---

# Overview

Document Ingestion Platform is an enterprise-oriented document parsing framework designed for Retrieval-Augmented Generation (RAG), Knowledge Base construction, and Large Language Model (LLM) applications.

The platform converts heterogeneous enterprise documents into a unified structured data model suitable for:

- PostgreSQL
- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma
- OpenSearch
- Amazon Bedrock Knowledge Bases
- Azure AI Search

Unlike traditional document parsers that only extract plain text, this project preserves the hierarchical structure of documents, enabling downstream systems to understand the semantic relationships between chapters, sections, and contents.

---

# Project Goals

Enterprise documents are commonly distributed across multiple formats:

- PDF
- Microsoft Word (DOCX)
- Microsoft PowerPoint (PPTX)
- Microsoft Excel (XLSX)

Each format has a completely different internal structure.

The goal of this project is to:

**Convert all supported document formats into a unified document model.**

Regardless of the original file format, every document is represented using the same data structure.

---

# Key Features

## Supported Formats

| Format | Status |
|----------|--------|
| PDF | ✅ Supported |
| DOCX | ✅ Supported |
| PPTX | ✅ Supported |
| XLSX | ✅ Supported |

---

## Unified Data Model

All documents are normalized into the same document model.

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

This allows downstream components to process every document consistently without caring about its original format.

---

## Preserved Document Hierarchy

Instead of extracting plain text only, the parser preserves:

- Chapters
- Sections
- Contents
- Semantic Chunks

Example:

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

Preserving document hierarchy significantly improves retrieval quality in RAG applications.

---

## Enterprise Processing Pipeline

Every supported format follows the same processing pipeline.

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

Each stage follows the Single Responsibility Principle and can be independently tested, maintained, or replaced.

---

## Semantic Chunking

Chunks are generated based on document semantics rather than fixed character counts.

Chunk boundaries follow:

```
Chapter

↓

Section

↓

Paragraph

↓

Chunk
```

This minimizes context fragmentation while preserving semantic integrity.

---

## Token Statistics

Each generated chunk records:

- Token Count
- Chunk Index
- Page Number

These statistics simplify:

- Embedding generation
- RAG retrieval
- Token budget management
- Context window optimization

---

## PostgreSQL Storage

Parsed documents are automatically normalized into relational tables.

```
documents

↓

chapters

↓

sections

↓

contents
```

The resulting schema supports:

- SQL queries
- Full-text search
- Vectorization workflows

---

## JSON Export

Every parsed document is exported as structured JSON.

```json
{
    "document": {},
    "metadata": {},
    "chapters": [],
    "sections": [],
    "contents": []
}
```

The exported JSON preserves the complete document hierarchy and can be directly consumed by:

- APIs
- Front-end applications
- Debugging tools
- Secondary processing pipelines

---

## Vector Database Ready

Chunk-level outputs follow a structure compatible with mainstream vector databases.

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

These records can be embedded using:

- OpenAI Embeddings
- Amazon Titan Embeddings
- BGE
- E5
- Jina Embeddings

and stored directly in:

- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma

---

# System Architecture

```
                 +----------------------+
                 |   Input Documents    |
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

            Common Processing Components

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

# Design Principles

This project follows enterprise software engineering practices.

## Single Responsibility Principle (SRP)

Every component is responsible for exactly one task.

Examples:

```
PDFLoader

↓

Load PDF files only
```

```
HeaderFooterFilter

↓

Remove headers and footers only
```

```
Chunker

↓

Generate semantic chunks only
```

This design minimizes coupling between modules.

---

## Pipeline Architecture

Every document is processed through the same layered architecture.

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

Each layer can evolve independently.

---

## Unified Document Model

Regardless of the original format, every parser produces the same document model.

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

This eliminates format-specific business logic.

---

## Extensible Design

Supporting a new document format typically requires implementing only:

- Loader
- Parser
- Pipeline

and registering the pipeline in the Pipeline Factory.

Existing business logic remains unchanged.

---

# Project Structure

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

# Current Capabilities

| Module | Status |
|---------|--------|
| PDF Loader | ✅ |
| DOCX Loader | ✅ |
| PPTX Loader | ✅ |
| XLSX Loader | ✅ |
| PDF Parser | ✅ |
| DOCX Parser | ✅ |
| PPTX Parser | ✅ |
| XLSX Parser | ✅ |
| Semantic Chunking | ✅ |
| Token Counter | ✅ |
| PostgreSQL Storage | ✅ |
| JSON Builder | ✅ |
| Vector Database Output | ✅ |
