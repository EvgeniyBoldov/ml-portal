from __future__ import annotations

import json
from typing import Dict, List, Any, Optional
from celery import shared_task
from app.core.config import settings
from app.core.s3 import get_object, put_object
from app.core.db import SessionLocal
from app.core.metrics import rag_ingest_stage_duration, rag_ingest_errors_total
from .shared import log, RetryableError, task_metrics

@shared_task(name="app.tasks.ocr_tables.process", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_ocr_tables(self, document_id: str, source_key: str, original_filename: str) -> Dict[str, Any]:
    """
    Process PDF for OCR and table extraction
    """
    with task_metrics("ocr_tables.process", "ocr"):
        session = SessionLocal()
        try:
            # Load PDF from S3
            obj = get_object(settings.S3_BUCKET_RAG, source_key)
            pdf_content = obj.read()
            
            # Process OCR if needed
            ocr_text = ""
            ocr_meta = {}
            try:
                ocr_text, ocr_meta = _extract_ocr_text(pdf_content)
                log.info(f"OCR extracted {len(ocr_text)} characters")
            except Exception as e:
                log.warning(f"OCR extraction failed: {e}")
                rag_ingest_errors_total.labels(stage="ocr", error_type="extraction_failed").inc()
            
            # Extract tables
            tables = []
            try:
                tables = _extract_tables(pdf_content)
                log.info(f"Extracted {len(tables)} tables")
            except Exception as e:
                log.warning(f"Table extraction failed: {e}")
                rag_ingest_errors_total.labels(stage="tables", error_type="extraction_failed").inc()
            
            # Combine results
            result = {
                "document_id": document_id,
                "ocr_text": ocr_text,
                "ocr_meta": ocr_meta,
                "tables": tables,
                "processing_method": "ocr_tables"
            }
            
            # Save enhanced canonical
            canonical_key = f"{document_id}/canonical_enhanced.json"
            canonical_data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            put_object(settings.S3_BUCKET_RAG, canonical_key, canonical_data, content_type="application/json; charset=utf-8")
            
            return result
            
        except Exception as e:
            log.error(f"OCR/tables processing failed: {e}")
            rag_ingest_errors_total.labels(stage="ocr_tables", error_type="processing_failed").inc()
            raise RetryableError(f"OCR/tables processing failed: {e}")
        finally:
            session.close()

def _extract_ocr_text(pdf_content: bytes) -> tuple[str, Dict[str, Any]]:
    """Extract text using OCR from PDF images"""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        
        # Convert PDF to images
        images = convert_from_bytes(pdf_content, dpi=300)
        
        text_parts = []
        meta = {
            "pages": len(images),
            "method": "pytesseract",
            "dpi": 300,
            "lang": "rus+eng"
        }
        
        for i, image in enumerate(images):
            # OCR each page
            page_text = pytesseract.image_to_string(image, lang='rus+eng')
            text_parts.append(page_text)
            
            # Log progress
            if i % 10 == 0:
                log.info(f"OCR processed page {i+1}/{len(images)}")
        
        full_text = '\n\n'.join(text_parts)
        
        return full_text, meta
        
    except ImportError:
        log.warning("OCR dependencies not available")
        return "", {"error": "OCR dependencies not available"}
    except Exception as e:
        log.error(f"OCR extraction failed: {e}")
        return "", {"error": str(e)}

def _extract_tables(pdf_content: bytes) -> List[Dict[str, Any]]:
    """Extract tables from PDF using multiple methods"""
    import io
    tables = []
    
    # Method 1: pdfplumber (simple tables)
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_tables = page.extract_tables()
                for table_num, table in enumerate(page_tables):
                    if table and len(table) > 1:
                        # Convert to structured format
                        table_data = {
                            "page": page_num + 1,
                            "table": table_num + 1,
                            "rows": len(table),
                            "cols": len(table[0]) if table else 0,
                            "data": table,
                            "method": "pdfplumber"
                        }
                        tables.append(table_data)
    except ImportError:
        log.warning("pdfplumber not available for table extraction")
    except Exception as e:
        log.warning(f"pdfplumber table extraction failed: {e}")
    
    # Method 2: camelot (advanced tables)
    try:
        import camelot
        import io
        
        # Extract tables using camelot
        camelot_tables = camelot.read_pdf(io.BytesIO(pdf_content), pages='all')
        
        for i, table in enumerate(camelot_tables):
            if table.df is not None and not table.df.empty:
                table_data = {
                    "page": table.page,
                    "table": i + 1,
                    "rows": len(table.df),
                    "cols": len(table.df.columns),
                    "data": table.df.values.tolist(),
                    "method": "camelot",
                    "accuracy": table.accuracy
                }
                tables.append(table_data)
    except ImportError:
        log.warning("camelot not available for table extraction")
    except Exception as e:
        log.warning(f"camelot table extraction failed: {e}")
    
    # Method 3: tabula (Java-based)
    try:
        import tabula
        import io
        
        # Extract tables using tabula
        tabula_tables = tabula.read_pdf(io.BytesIO(pdf_content), pages='all', multiple_tables=True)
        
        for i, table in enumerate(tabula_tables):
            if table is not None and not table.empty:
                table_data = {
                    "page": 1,  # tabula doesn't provide page info easily
                    "table": i + 1,
                    "rows": len(table),
                    "cols": len(table.columns),
                    "data": table.values.tolist(),
                    "method": "tabula"
                }
                tables.append(table_data)
    except ImportError:
        log.warning("tabula not available for table extraction")
    except Exception as e:
        log.warning(f"tabula table extraction failed: {e}")
    
    return tables

def _convert_table_to_markdown(table_data: List[List[str]]) -> str:
    """Convert table data to Markdown format"""
    if not table_data or len(table_data) < 2:
        return ""
    
    # Create header
    header = "| " + " | ".join(str(cell or "") for cell in table_data[0]) + " |"
    separator = "| " + " | ".join("---" for _ in table_data[0]) + " |"
    
    # Create rows
    rows = []
    for row in table_data[1:]:
        row_str = "| " + " | ".join(str(cell or "") for cell in row) + " |"
        rows.append(row_str)
    
    return "\n".join([header, separator] + rows)

@shared_task(name="app.tasks.ocr_tables.enhance_canonical", bind=True)
def enhance_canonical_with_ocr_tables(self, document_id: str, canonical_key: str) -> Dict[str, Any]:
    """
    Enhance existing canonical file with OCR and table data
    """
    with task_metrics("ocr_tables.enhance_canonical", "enhance"):
        try:
            # Load existing canonical
            obj = get_object(settings.S3_BUCKET_RAG, canonical_key)
            canonical_data = json.loads(obj.read().decode("utf-8"))
            
            # Get original PDF
            source_key = f"{document_id}/origin.pdf"  # Assuming PDF extension
            pdf_obj = get_object(settings.S3_BUCKET_RAG, source_key)
            pdf_content = pdf_obj.read()
            
            # Extract OCR and tables
            ocr_text, ocr_meta = _extract_ocr_text(pdf_content)
            tables = _extract_tables(pdf_content)
            
            # Enhance canonical data
            enhanced_data = {
                **canonical_data,
                "ocr_text": ocr_text,
                "ocr_meta": ocr_meta,
                "extracted_tables": tables,
                "enhanced_at": "2024-01-01T00:00:00Z"  # Would use actual timestamp
            }
            
            # Save enhanced canonical
            enhanced_key = f"{document_id}/canonical_enhanced.json"
            enhanced_json = json.dumps(enhanced_data, ensure_ascii=False).encode("utf-8")
            put_object(settings.S3_BUCKET_RAG, enhanced_key, enhanced_json, content_type="application/json; charset=utf-8")
            
            return {
                "document_id": document_id,
                "enhanced": True,
                "ocr_chars": len(ocr_text),
                "tables_count": len(tables)
            }
            
        except Exception as e:
            log.error(f"Canonical enhancement failed: {e}")
            rag_ingest_errors_total.labels(stage="enhance", error_type="enhancement_failed").inc()
            raise RetryableError(f"Canonical enhancement failed: {e}")
