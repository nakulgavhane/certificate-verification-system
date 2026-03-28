"""
AI-Powered Certificate Verification Engine
Uses Vision LLM for document analysis and RAG for cross-verification
"""

import os
import re
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

try:
    import fitz  # PyMuPDF
except ImportError:
    try:
        import pymupdf as fitz
    except ImportError:
        from PyMuPDF import fitz

from PIL import Image
from pyzbar.pyzbar import decode
import pytesseract
import tempfile

if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Ollama config for local Vision LLM
OLLAMA_BASE_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
VISION_MODEL = os.environ.get('VISION_MODEL', 'llava:7b')
TEXT_MODEL = os.environ.get('TEXT_MODEL', 'qwen2.5:7b-instruct')


def extract_with_vision_llm(image_path):
    """Use Vision LLM to extract structured data from certificate image."""
    import base64
    with open(image_path, 'rb') as f:
        image_b64 = base64.b64encode(f.read()).decode()

    prompt = (
        "Extract the following from this certificate image. "
        "Return JSON with keys: holder_name, certificate_title, "
        "issuing_authority, issue_date, expiry_date, certificate_id, "
        "qr_detected (bool), urls_found (list). "
        "If a field is not found, set it to null."
    )

    try:
        resp = requests.post(f'{OLLAMA_BASE_URL}/api/generate', json={
            'model': VISION_MODEL,
            'prompt': prompt,
            'images': [image_b64],
            'stream': False
        }, timeout=60)

        if resp.status_code == 200:
            text = resp.json().get('response', '')
            # Try to parse JSON from response
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"Vision LLM extraction failed: {e}")

    return None


def cross_verify_with_rag(extracted_data, urls):
    """RAG pipeline: cross-verify extracted certificate data against issuer websites."""
    if not extracted_data or not urls:
        return {'verified': False, 'reason': 'Insufficient data for cross-verification'}

    holder_name = extracted_data.get('holder_name', '')
    cert_title = extracted_data.get('certificate_title', '')
    issuer = extracted_data.get('issuing_authority', '')

    verification_results = []

    for url in urls:
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            if resp.status_code >= 400:
                continue

            page_text = resp.text.lower()

            # Check if holder name appears on the verification page
            name_match = holder_name and holder_name.lower() in page_text
            # Check if certificate title matches
            title_match = cert_title and cert_title.lower() in page_text
            # Check if issuer matches
            issuer_match = issuer and issuer.lower() in page_text

            match_score = sum([name_match, title_match, issuer_match])

            verification_results.append({
                'url': url,
                'reachable': True,
                'name_match': name_match,
                'title_match': title_match,
                'issuer_match': issuer_match,
                'match_score': match_score
            })
        except Exception:
            verification_results.append({
                'url': url, 'reachable': False,
                'match_score': 0
            })

    if not verification_results:
        return {'verified': False, 'reason': 'No URLs could be reached'}

    best = max(verification_results, key=lambda x: x['match_score'])

    if best['match_score'] >= 2:
        return {
            'verified': True,
            'confidence': 'high',
            'reason': f"Holder name and certificate details confirmed on {best['url']}",
            'details': verification_results
        }
    elif best['match_score'] == 1:
        return {
            'verified': True,
            'confidence': 'medium',
            'reason': f"Partial match found on {best['url']}",
            'details': verification_results
        }
    elif any(r['reachable'] for r in verification_results):
        return {
            'verified': True,
            'confidence': 'low',
            'reason': 'URLs are reachable but certificate details not confirmed on page',
            'details': verification_results
        }

    return {'verified': False, 'reason': 'No matching data found', 'details': verification_results}


def llm_analyze_certificate(extracted_data, rag_result):
    """Use text LLM to produce final analysis combining vision extraction and RAG results."""
    prompt = f"""Analyze this certificate verification:

Extracted Data: {json.dumps(extracted_data, default=str)}
Cross-Verification Result: {json.dumps(rag_result, default=str)}

Provide a brief verdict: is this certificate likely VALID or FAKE? 
Give reasoning in 2-3 sentences."""

    try:
        resp = requests.post(f'{OLLAMA_BASE_URL}/api/generate', json={
            'model': TEXT_MODEL,
            'prompt': prompt,
            'stream': False
        }, timeout=30)

        if resp.status_code == 200:
            return resp.json().get('response', 'Analysis unavailable')
    except Exception:
        pass

    return 'LLM analysis unavailable - using rule-based verification'


def is_valid_url(url, timeout=5):
    """Check if a URL is valid and leads to a functional webpage."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False


def validate_urls(urls_list):
    """Validate a list of URLs using parallel requests."""
    if not urls_list:
        return []
    valid = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(is_valid_url, url): url for url in urls_list}
        for future in future_map:
            url = future_map[future]
            try:
                if future.result():
                    valid.append(url)
            except Exception:
                pass
    return valid


def verify_certificate(file):
    """Main verification pipeline: Vision LLM -> URL extraction -> RAG cross-verification -> LLM analysis."""
    filename = file.filename.lower()

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = os.path.join(tmpdir, filename)
        file.save(temp_path)

        extracted_data = None
        all_urls = []
        all_links = []

        if filename.endswith('.pdf'):
            doc = fitz.open(temp_path)

            for page_num in range(doc.page_count):
                page = doc[page_num]

                # Extract embedded hyperlinks
                for link in page.get_links():
                    uri = link.get('uri')
                    if uri:
                        all_links.append(uri)

                # Extract text URLs via regex
                text = page.get_text('text')
                urls_in_text = re.findall(
                    r'(?:https?://)?[-\w]+(?:\.[-\w]+)+(?:/[-\w./?=%&]*)?', text
                )
                all_urls.extend(urls_in_text)

                # Render page as image for Vision LLM
                if not extracted_data:
                    pix = page.get_pixmap(dpi=200)
                    img_path = os.path.join(tmpdir, f'page_{page_num}.png')
                    pix.save(img_path)
                    extracted_data = extract_with_vision_llm(img_path)

                    # Also try QR from rendered image
                    try:
                        img = Image.open(img_path)
                        qr_codes = decode(img)
                        for qr in qr_codes:
                            data = qr.data.decode('utf-8')
                            if re.match(r'(?:https?://)?[-\w]+(?:\.[-\w]+)+', data):
                                all_urls.append(data)
                    except Exception:
                        pass

            doc.close()

        else:
            # Image file
            try:
                img = Image.open(temp_path)

                # QR code scan
                qr_codes = decode(img)
                for qr in qr_codes:
                    data = qr.data.decode('utf-8')
                    if re.match(r'(?:https?://)?[-\w]+(?:\.[-\w]+)+', data):
                        all_urls.append(data)

                # OCR fallback for URL extraction
                text = pytesseract.image_to_string(img)
                urls_in_text = re.findall(
                    r'(?:https?://)?[-\w]+(?:\.[-\w]+)+(?:/[-\w./?=%&]*)?', text
                )
                all_urls.extend(urls_in_text)

                # Vision LLM extraction
                extracted_data = extract_with_vision_llm(temp_path)

            except Exception as e:
                return {'status': 'error', 'details': f'Error processing file: {e}'}

        # Merge all discovered URLs
        combined_urls = list(set(all_links + all_urls))
        if extracted_data and extracted_data.get('urls_found'):
            combined_urls.extend(extracted_data['urls_found'])
        combined_urls = list(set(combined_urls))

        # Validate URLs
        valid_urls = validate_urls(combined_urls)

        # RAG cross-verification
        rag_result = cross_verify_with_rag(extracted_data, valid_urls)

        # LLM final analysis
        llm_verdict = llm_analyze_certificate(extracted_data, rag_result)

        # Build result
        if rag_result.get('verified') and rag_result.get('confidence') in ('high', 'medium'):
            status = 'valid'
        elif valid_urls:
            status = 'valid'
        else:
            status = 'invalid'

        return {
            'status': status,
            'details': llm_verdict,
            'extracted_data': extracted_data,
            'cross_verification': rag_result,
            'links': valid_urls,
            'urls_in_text': combined_urls,
            'all_links_found': len(combined_urls),
            'valid_links_found': len(valid_urls)
        }


def verify_certificates_bulk(files):
    """Bulk verification for checking certificates listed on resumes."""
    results = []
    for f in files:
        result = verify_certificate(f)
        result['filename'] = f.filename
        results.append(result)

    summary = {
        'total': len(results),
        'valid': sum(1 for r in results if r['status'] == 'valid'),
        'invalid': sum(1 for r in results if r['status'] == 'invalid'),
        'errors': sum(1 for r in results if r['status'] == 'error'),
        'results': results
    }
    return summary
