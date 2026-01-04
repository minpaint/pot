# directory/utils/docx_cleaner.py

import logging
from docx import Document
from io import BytesIO

logger = logging.getLogger(__name__)


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
    try:
        doc = Document(BytesIO(doc_bytes))
        total_paragraphs = len(doc.paragraphs)

        # Список индексов параграфов для удаления
        paragraphs_to_remove = []

        for i, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()

            # Проверяем, является ли параграф пустым
            if not text:
                paragraphs_to_remove.append(i)
                continue

            # Проверяем, состоит ли строка только из разделителей (тире и пробелы)
            # Разрешённые символы: пробел, дефис, короткое тире, длинное тире
            if all(char in ' -–—' for char in text):
                paragraphs_to_remove.append(i)
                logger.debug(f"[remove_empty_paragraphs] Параграф {i} будет удалён: '{text}'")

        # Удаляем параграфы в обратном порядке (чтобы индексы не сбились)
        for i in reversed(paragraphs_to_remove):
            p = doc.paragraphs[i]._element
            p.getparent().remove(p)

        logger.info(f"[remove_empty_paragraphs] Удалено {len(paragraphs_to_remove)} из {total_paragraphs} параграфов")

        # Сохраняем в BytesIO
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        return buffer.getvalue()

    except Exception as e:
        logger.error(f"[remove_empty_paragraphs] Ошибка: {e}", exc_info=True)
        return doc_bytes


def remove_empty_table_rows(doc_bytes: bytes) -> bytes:
    """
    Удаляет пустые строки из таблиц в DOCX документе.

    Строка считается пустой, если все её ячейки пусты.

    Args:
        doc_bytes: DOCX документ в виде байтов

    Returns:
        Очищенный DOCX документ в виде байтов
    """
    try:
        doc = Document(BytesIO(doc_bytes))
        total_removed = 0

        for table_idx, table in enumerate(doc.tables):
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
                total_removed += 1

            if rows_to_remove:
                logger.debug(f"[remove_empty_table_rows] Таблица {table_idx}: удалено {len(rows_to_remove)} строк")

        logger.info(f"[remove_empty_table_rows] Всего удалено {total_removed} пустых строк из таблиц")

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        return buffer.getvalue()

    except Exception as e:
        logger.error(f"[remove_empty_table_rows] Ошибка: {e}", exc_info=True)
        return doc_bytes


def clean_document(doc_bytes: bytes, remove_empty_rows: bool = True) -> bytes:
    """
    Полная очистка документа: удаление пустых параграфов и строк таблиц.

    Args:
        doc_bytes: DOCX документ в виде байтов
        remove_empty_rows: Удалять ли пустые строки таблиц (по умолчанию True)

    Returns:
        Очищенный DOCX документ в виде байтов
    """
    try:
        logger.info(f"[clean_document] ===== ВЫЗОВ ФУНКЦИИ clean_document, размер документа: {len(doc_bytes)} байт =====")
        logger.debug("[clean_document] Начало очистки документа")

        # Сначала удаляем пустые параграфы
        doc_bytes = remove_empty_paragraphs(doc_bytes)
        logger.debug("[clean_document] Пустые параграфы удалены")

        # Потом удаляем пустые строки таблиц (если нужно)
        if remove_empty_rows:
            doc_bytes = remove_empty_table_rows(doc_bytes)
            logger.debug("[clean_document] Пустые строки таблиц удалены")

        logger.info("[clean_document] Документ успешно очищен")
        return doc_bytes

    except Exception as e:
        logger.error(f"[clean_document] Ошибка при очистке документа: {e}", exc_info=True)
        # В случае ошибки возвращаем оригинальный документ
        logger.warning("[clean_document] Возвращаем неочищенный документ")
        return doc_bytes
