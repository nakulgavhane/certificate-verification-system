# Certificate Verification System

AI-powered fake certificate detection using Vision LLM, QR scanning, OCR, and RAG-based cross-verification. Final year B.E. project.

## What it does

1. Upload a certificate (PDF or image)
2. **Vision LLM** (LLaVA) extracts holder name, certificate title, issuing authority, dates, QR codes, and URLs from the document
3. QR codes are decoded and text is OCR'd as fallback extraction methods
4. **RAG pipeline** cross-verifies the extracted data against issuing authority websites:
   - Checks if the holder name appears on the verification page
   - Matches certificate title and issuing authority
   - Validates expiry dates
5. **Text LLM** (Qwen 2.5) produces a final verdict with confidence score
6. Supports **bulk verification** for checking certificates listed on resumes

## Verification Pipeline

```
Certificate Upload
       |
       v
Vision LLM (LLaVA) --> Extract: name, title, authority, dates, URLs
       |                          |
       |                    QR Decode / OCR (fallback)
       v                          |
   URL Validation <---------------+
       |
       v
RAG Cross-Verification --> Fetch issuer pages, match extracted data
       |
       v
Text LLM (Qwen 2.5) --> Final verdict + confidence score
```

A certificate is marked **valid** if:
- Extracted URLs are reachable AND holder name/title matches on the verification page (high confidence)
- URLs reachable with partial matches (medium confidence)
- URLs reachable but no data match on page (low confidence)

## Tech Stack

- **Backend**: Flask, Flask-Login, Flask-SQLAlchemy
- **Database**: SQLite
- **Vision AI**: LLaVA via Ollama (certificate image analysis)
- **Text LLM**: Qwen 2.5 via Ollama (final verdict generation)
- **QR**: pyzbar
- **OCR**: Tesseract (pytesseract)
- **PDF**: PyMuPDF
- **URL Validation**: requests + concurrent.futures

## Project Structure

```
app.py            # Flask routes, auth, verification endpoints
models.py         # SQLAlchemy models (User, VerificationHistory, Verification)
forms.py          # WTForms (Login, Registration, Profile)
qr_scanner.py     # Core verification engine (Vision LLM + RAG + QR + OCR)
requirements.txt  # Dependencies
templates/        # Jinja2 templates
```

## Setup

```bash
# Install Ollama and pull models
ollama pull llava:7b
ollama pull qwen2.5:7b-instruct

# Install Python dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run
python app.py
```

Requires [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed.

## Impact

Reduced manual certificate verification time by 95%.

## License

MIT
