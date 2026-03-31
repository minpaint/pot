# directory/utils/docx_cleaner.py

import logging
import re
import zipfile
from io import BytesIO

from docx import Document

logger = logging.getLogger(__name__)


def remove_headers_footers(doc_bytes: bytes) -> bytes:
    """
    Полностью удаляет все колонтитулы из DOCX на уровне ZIP/XML.

    Удаляет:
    - Файлы word/header*.xml и word/footer*.xml
    - Ссылки <w:headerReference> и <w:footerReference> из document.xml
    - Связи (relationships) на header/footer файлы из word/_rels/document.xml.rels
    """
    try:
        in_buf = BytesIO(doc_bytes)
        out_buf = BytesIO()

        with zipfile.ZipFile(in_buf, 'r') as zin, \
             zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as zout:

            for item in zin.infolist():
                data = zin.read(item.filename)

                # Пропускаем файлы header*.xml и footer*.xml
                name = item.filename
                if re.match(r'word/(header|footer)\d*\.xml$', name):
                    logger.debug(f"[remove_headers_footers] Удалён файл: {name}")
                    continue

                # Из document.xml убираем <w:headerReference> и <w:footerReference>
                if name == 'word/document.xml':
                    text = data.decode('utf-8')
                    text = re.sub(r'<w:headerReference[^/]*/>', '', text)
                    text = re.sub(r'<w:footerReference[^/]*/>', '', text)
                    data = text.encode('utf-8')

                # Из relationships убираем связи на header/footer
                if name == 'word/_rels/document.xml.rels':
                    text = data.decode('utf-8')
                    text = re.sub(
                        r'<Relationship[^>]*(header|footer)[^>]*/>\s*',
                        '', text, flags=re.IGNORECASE
                    )
                    data = text.encode('utf-8')

                zout.writestr(item, data)

        out_buf.seek(0)
        return out_buf.getvalue()

    except Exception as e:
        logger.error(f"[remove_headers_footers] Ошибка: {e}", exc_info=True)
        return doc_bytes


def _remove_marker_from_paragraph(paragraph, marker='__KEEP_EMPTY__'):
    """
    Удаляет маркер из параграфа, сохраняя форматирование.
    Заменяет маркер на пробел нулевой ширины, чтобы параграф не стал пустым.

    Args:
        paragraph: Параграф из которого нужно удалить маркер
        marker: Маркер для удаления
    """
    # Пробел нулевой ширины (Zero Width Space) - невидимый символ
    # который не отображается, но предотвращает удаление пустого параграфа
    ZERO_WIDTH_SPACE = '\u200B'

    for run in paragraph.runs:
        if marker in run.text:
            # Заменяем маркер на пробел нулевой ширины
            run.text = run.text.replace(marker, ZERO_WIDTH_SPACE)


def remove_empty_paragraphs(doc_bytes: bytes) -> bytes:
    """
    Удаляет пустые параграфы из DOCX документа (body, headers, footers).

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

        # Удаляем пустые параграфы из body
        total_paragraphs = len(doc.paragraphs)
        paragraphs_to_remove = []

        for i, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()

            # Проверяем наличие маркера __KEEP_EMPTY__
            if '__KEEP_EMPTY__' in text:
                # Удаляем маркер из текста, сохраняя форматирование
                _remove_marker_from_paragraph(paragraph)
                logger.debug(f"[remove_empty_paragraphs] Body параграф {i} сохранён с маркером keep_empty")
                continue

            # Проверяем, является ли параграф пустым
            if not text:
                paragraphs_to_remove.append(i)
                continue

            # Проверяем, состоит ли строка только из разделителей (тире и пробелы)
            # Разрешённые символы: пробел, дефис, короткое тире, длинное тире
            if all(char in ' -–—' for char in text):
                paragraphs_to_remove.append(i)
                logger.debug(f"[remove_empty_paragraphs] Body параграф {i} будет удалён: '{text}'")

        # Удаляем параграфы в обратном порядке (чтобы индексы не сбились)
        for i in reversed(paragraphs_to_remove):
            p = doc.paragraphs[i]._element
            p.getparent().remove(p)

        logger.info(f"[remove_empty_paragraphs] Удалено {len(paragraphs_to_remove)} из {total_paragraphs} параграфов из body")

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
        # Удаляем колонтитулы на уровне ZIP (до python-docx, чтобы он их не создал заново)
        doc_bytes = remove_headers_footers(doc_bytes)

        # Удаляем пустые параграфы из body
        doc_bytes = remove_empty_paragraphs(doc_bytes)

        # Удаляем пустые строки таблиц (если нужно)
        if remove_empty_rows:
            doc_bytes = remove_empty_table_rows(doc_bytes)

        return doc_bytes

    except Exception as e:
        logger.error(f"[clean_document] Ошибка при очистке документа: {e}", exc_info=True)
        # В случае ошибки возвращаем оригинальный документ
        return doc_bytes
