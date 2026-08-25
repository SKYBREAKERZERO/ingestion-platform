FORMAT EXTENSION BUNDLE
=======================

Adds:
- TXT
- PNG
- JPG
- JPEG
- legacy PPT

Copy files into the same relative paths in your project.

Install:
    python -m pip install -r requirements_format_additions.txt

Python test first:
    python -m app.gui.application

Notes:
1. PNG/JPG/JPEG:
   Uses RapidOCR + ONNX Runtime.
   No separate Tesseract installation is required.

2. Legacy PPT:
   Requires Microsoft PowerPoint installed on the target Windows computer.
   Uses pywin32 COM automation to convert .ppt -> temporary .pptx,
   then reuses the existing PPTXPipeline.
   The temporary .pptx is deleted automatically.

3. Final OneFile EXE:
   Do NOT rebuild the final EXE yet.
   First verify TXT, image OCR, and PPT in Python mode.
   Then update the PyInstaller spec to collect RapidOCR models,
   ONNX Runtime, and pywin32 pieces.
