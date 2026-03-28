# Certificate Verification System

Web app that detects fake certificates by scanning QR codes, extracting URLs from PDFs/images via OCR, and validating links. Built as a final year B.E. project.

## What it does

- Upload a certificate (PDF or image)
- System extracts embedded links from PDF, decodes QR codes, or runs OCR to find URLs
- Validates each URL by making parallel HTTP requests
- Reports whether the certificate is valid or fake based on link accessibility
- Full user system with admin dashboard, verification history, and audit trail

## How verification works

**PDFs:** Extracts hyperlinks from pages + scans text for URLs using regex. Validates each URL concurrently.

**Images:** Tries QR code decoding (pyzbar) first. If no QR found, runs Tesseract OCR to extract text and find URLs.

A certificate is marked **valid** if any extracted URL returns HTTP 200.

## Tech Stack

- **Backend**: Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF
- **Database**: SQLite
- **QR**: pyzbar
- **OCR**: Tesseract (pytesseract)
- **PDF**: PyMuPDF (fitz)
- **Image**: Pillow
- **URL Validation**: requests + concurrent.futures (ThreadPoolExecutor)

## Project Structure

```
app.py            # Flask app (routes, auth, verification logic)
models.py         # SQLAlchemy models (User, VerificationHistory, Verification)
forms.py          # WTForms (Login, Registration, Profile)
qr_scanner.py     # Verification engine (QR + OCR + URL validation)
requirements.txt  # Dependencies
templates/        # Jinja2 HTML templates (12 files)
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Requires [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed.

Default admin: dmin / dmin

## Impact

Reduced manual certificate verification time by 95%.

## License

MIT
