# Document Ingestion Platform

> RAG（Retrieval-Augmented Generation）および企業向けナレッジベース構築のためのドキュメント取り込みプラットフォーム。

![Python](https://img.shields.io/badge/Python-3.12+-3776AB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![License](https://img.shields.io/badge/License-MIT-green)

---

# 概要

Document Ingestion Platform は、企業で利用されるさまざまなドキュメントを統一されたデータモデルへ変換するためのドキュメント取り込みフレームワークです。

本プロジェクトは Retrieval-Augmented Generation（RAG）、ナレッジベース構築、および Large Language Model（LLM）向けのデータ生成を目的として設計されています。

解析結果は以下のシステムで利用できます。

- PostgreSQL
- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma
- OpenSearch
- Amazon Bedrock Knowledge Bases
- Azure AI Search

一般的なテキスト抽出ツールとは異なり、本プロジェクトはドキュメントの階層構造（Chapter、Section、Content）を保持したまま解析を行います。

---

# プロジェクトの目的

企業で利用される仕様書や設計書は、複数のファイル形式で管理されています。

対応フォーマット

- PDF
- Microsoft Word（DOCX）
- Microsoft PowerPoint（PPTX）
- Microsoft Excel（XLSX）

それぞれ異なる内部構造を持つため、後続処理が複雑になりがちです。

本プロジェクトでは、すべてのドキュメントを統一データモデルへ変換することを目的としています。

これにより、ファイル形式を意識せずに同一の処理フローを実現できます。

---

# 主な特徴

## 対応フォーマット

| フォーマット | 対応状況 |
|-------------|----------|
| PDF | ✅ |
| DOCX | ✅ |
| PPTX | ✅ |
| XLSX | ✅ |

---

## 統一データモデル

すべてのドキュメントは共通モデルへ変換されます。

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

フォーマットごとの差異を吸収し、後続処理を共通化できます。

---

## ドキュメント構造の保持

本文のみを抽出するのではなく、以下の階層情報を保持します。

- Chapter
- Section
- Content
- Chunk

例

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

階層構造を保持することで、RAG における検索精度を向上させます。

---

## エンタープライズ向け Pipeline

すべてのフォーマットは共通の処理フローに従います。

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

各コンポーネントは単一責務（Single Responsibility Principle）に基づいて設計されています。

---

## セマンティック Chunk

Chunk は文字数ではなく意味単位で生成されます。

```
Chapter

↓

Section

↓

Paragraph

↓

Chunk
```

文脈を保持したままベクトル化できるため、RAG の検索品質向上に有効です。

---

## Token 情報の管理

各 Chunk には以下の情報が付与されます。

- Token Count
- Chunk Index
- Page Number

Embedding や Context Window の制御に利用できます。

---

## PostgreSQL 保存

解析結果は正規化されたテーブルへ保存されます。

```
documents

↓

chapters

↓

sections

↓

contents
```

これにより、

- SQL 検索
- 全文検索
- ベクトル化

を容易に実現できます。

---

## JSON 出力

解析結果は構造化 JSON として出力されます。

```json
{
    "document": {},
    "metadata": {},
    "chapters": [],
    "sections": [],
    "contents": []
}
```

JSON は API やフロントエンド、デバッグ用途にも利用できます。

---

## ベクトルデータベース対応

Chunk は主要なベクトルデータベースで利用可能な形式で出力されます。

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

Embedding 作成後、

- pgvector
- Pinecone
- Milvus
- Weaviate
- Chroma

へそのまま登録できます。

---

# システム構成

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

             Common Components

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

# 設計方針

本プロジェクトは企業システム開発を想定し、以下の設計方針を採用しています。

## 単一責務（SRP）

各コンポーネントは一つの責務のみを持ちます。

例

```
PDFLoader

↓

PDF の読み込みのみ
```

```
HeaderFooterFilter

↓

ヘッダー・フッター除去のみ
```

```
Chunker

↓

Chunk 生成のみ
```

---

## Pipeline アーキテクチャ

すべての処理は以下の Pipeline に従います。

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

各レイヤーは独立して保守・拡張できます。

---

## 統一データモデル

すべてのフォーマットは共通モデルへ変換されます。

```
Document

├── Pages

├── Chapters

├── Sections

└── Contents
```

フォーマット依存の業務ロジックを排除できます。

---

## 拡張性

新しいフォーマットへ対応する場合は、

- Loader
- Parser
- Pipeline

を実装し、Pipeline Factory に登録するだけで対応できます。

既存コードへの影響を最小限に抑えられます。

---

# プロジェクト構成

```
document-ingestion-platform/

├── app/
├── analyzer/
├── builder/
├── filter/
│   ├── common/
│   ├── pdf/
│   ├── docx/
│   ├── pptx/
│   └── xlsx/
├── loader/
├── model/
├── normalizer/
├── parser/
├── pipeline/
├── processor/
├── router/
├── storage/
└── utils/

├── input/
├── output/

├── requirements.txt
└── README.md
```

---

# 現在の対応状況

| モジュール | 状態 |
|------------|------|
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
| Vector Database Output | ✅ |
