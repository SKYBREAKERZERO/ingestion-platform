工具将任意企业文档转换为统一，JSON，并导入 PostgreSQL，为 RAG 提供标准数据源。

支持：
PDF
DOCX
XLSX
PPTX
TXT
Markdown

项目目录：
document-ingestion-platform/
│
├── app/
│   ├── config/
│   │      settings.py
│   │
│   ├── loader/
│   │      base_loader.py
│   │      pdf_loader.py
│   │      docx_loader.py
│   │      excel_loader.py
│   │      ppt_loader.py
│   │      loader_factory.py
│   │
│   ├── analyzer/
│   │      metadata.py
│   │      layout.py
│   │      classifier.py
│   │
│   ├── parser/
│   │      base_parser.py
│   │      generic_parser.py
│   │      toyota_parser.py
│   │      aws_parser.py
│   │
│   ├── model/
│   │      document.py
│   │      chapter.py
│   │      section.py
│   │      content.py
│   │
│   ├── chunk/
│   │      chunker.py
│   │
│   ├── database/
│   │      db.py
│   │      repositories/
│   │
│   ├── service/
│   │      import_service.py
│   │
│   ├── utils/
│   │
│   └── main.py
│
├── sql/
│
├── input/
│
├── output/
│
├── tests/
│
├── requirements.txt
│
└── README.md