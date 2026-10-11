from io import BytesIO

from openpyxl import Workbook

from app.services.document_parser import ExcelParser


def test_excel_parser_groups_rows_and_repeats_headers():
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "S-Curve Data"

    worksheet.append(["Date", "Planned Percentage"])
    worksheet.append(["2026-04-30", 5])
    worksheet.append(["2026-05-31", 12])
    worksheet.append(["2026-06-30", 22])
    worksheet.append(["2026-07-31", 35])
    worksheet.append(["2026-08-31", 50])
    worksheet.append(["2026-09-30", 66])

    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    stream.seek(0)

    chunks = ExcelParser.parse(stream)

    assert len(chunks) == 2

    first, second = chunks

    assert first["chunk_index"] == 0
    assert first["sheet_name"] == "S-Curve Data"
    assert first["row_start"] == 2
    assert first["row_end"] == 6
    assert "Columns: Date | Planned Percentage" in first["content"]
    assert "Excel row 2: Date: 2026-04-30 | Planned Percentage: 5" in first["content"]
    assert "Excel row 6: Date: 2026-08-31 | Planned Percentage: 50" in first["content"]

    assert second["chunk_index"] == 1
    assert second["sheet_name"] == "S-Curve Data"
    assert second["row_start"] == 7
    assert second["row_end"] == 7
    assert "Columns: Date | Planned Percentage" in second["content"]
    assert "Excel row 7: Date: 2026-09-30 | Planned Percentage: 66" in second["content"]

    assert first["content_hash"]
    assert second["content_hash"]
