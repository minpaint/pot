# directory/utils/docx_cleaner.py

from docx import Document
from io import BytesIO


def remove_empty_paragraphs(doc_bytes: bytes) -> bytes:
    """
    Удаляет пустые параграфы из DOCX документа.

    Параграф считается пустым, если:
    - Не содержит текста
    - Или содержит только пробелы, тире и дефисы

    Args:
        doc_bytes: DOCX документ в виде байтов

    Returns:
        Очищенный DOCX документ в виде байтов
    """
    doc = Document(BytesIO(doc_bytes))

    # Список индексов параграфов для удаления
    paragraphs_to_remove = []

    for i, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()

        # Проверяем, является ли параграф пустым или содержит только разделители
        if not text or text in ['', '-', '—', '–', ' - ', ' — ', ' – ']:
            paragraphs_to_remove.append(i)

    # Удаляем параграфы в обратном порядке (чтобы индексы не сбились)
    for i in reversed(paragraphs_to_remove):
        p = doc.paragraphs[i]._element
        p.getparent().remove(p)

    # Сохраняем в BytesIO
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer.getvalue()


def remove_empty_table_rows(doc_bytes: bytes) -> bytes:
    """
    Удаляет пустые строки из таблиц в DOCX документе.

    Строка считается пустой, если все её ячейки пусты.

    Args:
        doc_bytes: DOCX документ в виде байтов

    Returns:
        Очищенный DOCX документ в виде байтов
    """
    doc = Document(BytesIO(doc_bytes))

    for table in doc.tables:
        rows_to_remove = []

        for i, row in enumerate(table.rows):
            # Проверяем все ячейки в строке
            all_empty = True
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text and cell_text not in ['', '-', '—', '–']:
                    all_empty = False
                    break

            if all_empty:
                rows_to_remove.append(i)

        # Удаляем строки в обратном порядке
        for i in reversed(rows_to_remove):
            table._tbl.remove(table.rows[i]._tr)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer.getvalue()


def clean_document(doc_bytes: bytes, remove_empty_rows: bool = True) -> bytes:
    """
    Полная очистка документа: удаление пустых параграфов и строк таблиц.

    Args:
        doc_bytes: DOCX документ в виде байтов
        remove_empty_rows: Удалять ли пустые строки таблиц (по умолчанию True)

    Returns:
        Очищенный DOCX документ в виде байтов
    """
    # Сначала удаляем пустые параграфы
    doc_bytes = remove_empty_paragraphs(doc_bytes)

    # Потом удаляем пустые строки таблиц (если нужно)
    if remove_empty_rows:
        doc_bytes = remove_empty_table_rows(doc_bytes)

    return doc_bytes
