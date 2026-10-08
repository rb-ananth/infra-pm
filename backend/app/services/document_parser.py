import hashlib
from typing import Any, BinaryIO
from io import BytesIO
from pypdf import PdfReader
from openpyxl import load_workbook

class DocumentParser:
    @staticmethod
    def calculate_sha256(file_stream: BinaryIO) -> str:
        sha256_hash = hashlib.sha256()
        for byte_block in iter(lambda: file_stream.read(4096), b""):
            sha256_hash.update(byte_block)
        file_stream.seek(0)
        return sha256_hash.hexdigest()

class PdfParser:
    @staticmethod
    def parse(file_stream: BinaryIO) -> list[dict[str, Any]]:
        chunks = []
        reader = PdfReader(file_stream)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                chunks.append({
                    "chunk_index": i,
                    "content": text.strip(),
                    "content_hash": content_hash,
                    "page_number": i + 1,
                })
        file_stream.seek(0)
        return chunks

class ExcelParser:
    @staticmethod
    def parse(file_stream: BinaryIO) -> list[dict[str, Any]]:
        chunks = []
        wb = load_workbook(filename=BytesIO(file_stream.read()), data_only=True)
        chunk_idx = 0
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if not any(cell is not None and str(cell).strip() != "" for cell in row):
                    continue
                row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
                content_hash = hashlib.sha256(row_str.encode('utf-8')).hexdigest()
                chunks.append({
                    "chunk_index": chunk_idx,
                    "content": row_str,
                    "content_hash": content_hash,
                    "sheet_name": sheet_name,
                    "row_start": row_idx,
                    "row_end": row_idx,
                })
                chunk_idx += 1
        file_stream.seek(0)
        return chunks
