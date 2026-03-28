try:
    import fitz  # PyMuPDF for handling PDFs
except ImportError:
    try:
        import pymupdf as fitz  # Alternative import name
    except ImportError:
        from PyMuPDF import fitz  # Another possible import

import re  # To detect URLs in text
from pyzbar.pyzbar import decode
from PIL import Image
import tempfile
import os
import pytesseract
import requests
from urllib.parse import urlparse
from requests.exceptions import RequestException
import concurrent.futures

# Configure Tesseract path
if os.name == 'nt':  # Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def is_valid_url(url, timeout=5):
    """
    Check if a URL is valid and leads to a functional webpage.
    Returns True if the URL returns a successful status code, False otherwise.
    """
    # Ensure URL has a proper protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Parse the URL to check if it has a valid domain
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            return False
        
        # Try to get the webpage with a timeout
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        
        # Check if the response status code indicates success
        return response.status_code < 400
    except RequestException:
        return False

def validate_urls(urls_list):
    """
    Validate a list of URLs using parallel requests to improve performance.
    Returns a list of valid URLs.
    """
    if not urls_list:
        return []
    
    valid_urls = []
    
    # Use a thread pool to check URLs concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all URL validation tasks
        future_to_url = {executor.submit(is_valid_url, url): url for url in urls_list}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if future.result():
                    valid_urls.append(url)
            except Exception:
                # Skip any URLs that caused exceptions
                pass
                
    return valid_urls

def verify_certificate(file):
    filename = file.filename.lower()

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdirname:
        temp_path = os.path.join(tmpdirname, filename)
        file.save(temp_path)  # Save file regardless of type

        if filename.endswith('.pdf'):
            # Open the PDF and search for links and text
            pdf_document = fitz.open(temp_path)
            links = []
            text_with_urls = []

            # Loop through all pages in the PDF and extract links
            for page_num in range(pdf_document.page_count):
                page = pdf_document[page_num]
                
                # Search for explicit links
                links_on_page = page.get_links()
                for link in links_on_page:
                    uri = link.get('uri', None)
                    if uri:
                        links.append(uri)
                
                # Search for URLs in the text
                text = page.get_text("text")
                # Fixed regex pattern with correct character class syntax
                urls_in_text = re.findall(r'(?:https?://)?[-\w]+(?:\.[-\w]+)+(?:/[-\w./?=%&]*)?', text)
                text_with_urls.extend(urls_in_text)

            # Clean up by closing the PDF
            pdf_document.close()

            # Validate all found links
            valid_links = validate_urls(links)
            valid_text_urls = validate_urls(text_with_urls)
            
            # Determine certificate validity based on link validation
            if valid_links or valid_text_urls:
                return {
                    "status": "valid",
                    "details": "Valid links found",
                    "links": valid_links,
                    "urls_in_text": valid_text_urls
                }
            elif links or text_with_urls:
                return {
                    "status": "invalid",
                    "details": "Links found but none are valid (not accessible web pages)",
                    "links": links,
                    "urls_in_text": text_with_urls
                }
            else:
                return {"status": "invalid", "details": "No links or URLs found in the PDF"}

        else:
            # Handle image files
            try:
                img = Image.open(temp_path)
                
                # First try to decode QR codes
                decoded_objects = decode(img)
                if decoded_objects:
                    qr_data = []
                    valid_qr_urls = []
                    
                    for obj in decoded_objects:
                        data = obj.data.decode("utf-8")
                        qr_data.append(data)
                        
                        # Check if QR contains a URL
                        if re.match(r'(?:https?://)?[-\w]+(?:\.[-\w]+)+(?:/[-\w./?=%&]*)?', data):
                            if is_valid_url(data):
                                valid_qr_urls.append(data)
                    
                    if valid_qr_urls:
                        return {
                            "status": "valid",
                            "details": "Valid URLs found in QR code",
                            "urls_in_text": valid_qr_urls
                        }
                    else:
                        return {
                            "status": "invalid",
                            "details": "QR code found but contains no valid URLs",
                            "urls_in_text": qr_data
                        }
                
                # If no QR code found, try OCR to extract text and find URLs
                text = pytesseract.image_to_string(img)
                # Fixed regex pattern with correct character class syntax
                urls_in_text = re.findall(r'(?:https?://)?[-\w]+(?:\.[-\w]+)+(?:/[-\w./?=%&]*)?', text)
                
                # Validate extracted URLs
                valid_urls = validate_urls(urls_in_text)
                
                if valid_urls:
                    return {
                        "status": "valid",
                        "details": "Valid URLs found in image",
                        "urls_in_text": valid_urls
                    }
                elif urls_in_text:
                    return {
                        "status": "invalid",
                        "details": "URLs found in image but none are valid",
                        "urls_in_text": urls_in_text
                    }
                else:
                    return {"status": "invalid", "details": "No URLs or QR codes found in the image"}
                    
            except Exception as e:
                return {"status": "error", "details": f"Error processing file: {str(e)}"}
