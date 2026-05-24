# -*- coding: utf-8 -*-
"""
Модуль генерации .docx через шаблоны docxtpl.
Шаблоны: template_contract.docx, template_act.docx (в корне проекта).
"""

import os
import calendar
from datetime import date
from io import BytesIO

from num2words import num2words
from docxtpl import DocxTemplate
from docx import Document
from docxcompose.composer import Composer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates_docx')
TEMPLATE_CONTRACT = os.path.join(TEMPLATES_DIR, 'template_contract.docx')
TEMPLATE_ACT = os.path.join(TEMPLATES_DIR, 'template_act.docx')

MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def format_date_full(d):
    return f"{d.day:02d} {MONTHS_GEN[d.month]} {d.year} года"


def format_date_short(d):
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def format_date_medium(d):
    """01 сентября 2025 — для заголовка акта"""
    return f"{d.day:02d} {MONTHS_GEN[d.month]} {d.year}"


def last_day_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def _kopecks_word(n):
    if 11 <= n % 100 <= 14:
        return "копеек"
    r = n % 10
    if r == 1:
        return "копейка"
    if 2 <= r <= 4:
        return "копейки"
    return "копеек"


def amount_words(amount):
    """400.50 → '400 (Четыреста бел. руб. 50 копеек)'"""
    rubles = int(amount)
    kopecks = round((amount - rubles) * 100)
    w = num2words(rubles, lang='ru')
    full = f"{rubles},{kopecks:02d}" if kopecks else str(rubles)
    return f"{full} ({w} бел. руб. {kopecks:02d} {_kopecks_word(kopecks)})"


def amount_words_short(amount):
    """400 → '400 (четыреста) бел. руб.'"""
    rubles = int(amount)
    w = num2words(rubles, lang='ru')
    return f"{rubles} ({w}) бел. руб."


def _client_context(c):
    """Превращает dict клиента в контекст для шаблона."""
    return {
        'client_org_name':          c['org_name'][:1].upper() + c['org_name'][1:] if c.get('org_name') else '',
        'client_director_name':     c['director_name'],
        'client_director_initials': c['director_initials'],
        'client_director_position': c.get('director_position', 'директор'),
        'client_director_basis':    c['director_basis'],
        'client_unp':               c['unp'],
        'client_okpo':              c.get('okpo', ''),
        'client_address':           c['address'],
        'client_account':           c['account'],
        'client_bank':              c['bank'],
        'client_bank_branch':       c.get('bank_branch', ''),
        'client_bic':               c['bic'],
        'client_bank_city':         c.get('bank_city', 'г. Минск'),
        'client_phone':             c['phone'],
        'client_email':             c['email'],
    }


def _render(template_path, context, to_file, filename):
    tpl = DocxTemplate(template_path)
    tpl.render(context)
    if to_file:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)
        tpl.save(path)
        return path
    else:
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
        return buf, filename


def build_contract(contract_num, contract_date, client_dict, monthly_amount, service_desc,
                   to_file=False):
    context = {
        'contract_num':       contract_num,
        'contract_date_full': format_date_full(contract_date),
        'service_desc':       service_desc,
        'monthly_amount_str': amount_words_short(monthly_amount),
        **_client_context(client_dict),
    }
    filename = f"Договор №{contract_num.replace('/', '-')} {client_dict['org_name_short']}.docx"
    return _render(TEMPLATE_CONTRACT, context, to_file, filename)


def build_act(contract_num, contract_date, act_date, client_dict, amount, service_desc,
              to_file=False):
    context = {
        'contract_num':        contract_num,
        'contract_date_short': format_date_medium(contract_date),
        'contract_date_full':  format_date_full(contract_date),
        'act_date_full':       format_date_full(act_date),
        'service_desc':        service_desc,
        'amount_str':          amount_words(amount),
        **_client_context(client_dict),
    }
    filename = (
        f"Акт №{contract_num.replace('/', '-')} "
        f"{act_date.year}-{act_date.month:02d} "
        f"{client_dict['org_name_short']}.docx"
    )
    return _render(TEMPLATE_ACT, context, to_file, filename)


def build_envelopes(clients_data, to_file=False):
    """
    Лист 1 — шильдики адресатов (2 колонки).
    Лист 2 — шильдики отправителя (2 колонки, то же кол-во).
    Пунктирные линии разреза.
    """
    from docx.shared import Mm, Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    SENDER_LINES = [
        "ИП Мингинович",
        "Александр Георгиевич",
        "220017, г. Минск,",
        "ул. Неманская, 25, кв.227",
    ]
    COLS = 2
    CELL_W = 95   # мм
    CELL_H = 60   # мм
    FONT = 16

    def twips(mm):
        return int(mm * 56.693)

    def set_dashed_border(cell):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        for old in tcPr.findall(qn('w:tcBorders')):
            tcPr.remove(old)
        tcBorders = OxmlElement('w:tcBorders')
        for side in ('top', 'left', 'bottom', 'right'):
            el = OxmlElement(f'w:{side}')
            el.set(qn('w:val'), 'dashed')
            el.set(qn('w:sz'), '8')
            el.set(qn('w:space'), '0')
            el.set(qn('w:color'), '888888')
            tcBorders.append(el)
        tcPr.append(tcBorders)

    def set_cell_margins(cell, top=3, left=4, bottom=3, right=4):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        for old in tcPr.findall(qn('w:tcMar')):
            tcPr.remove(old)
        tcMar = OxmlElement('w:tcMar')
        for side, mm in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
            el = OxmlElement(f'w:{side}')
            el.set(qn('w:w'), str(twips(mm)))
            el.set(qn('w:type'), 'dxa')
            tcMar.append(el)
        tcPr.append(tcMar)

    def set_row_height(row, mm):
        tr = row._tr
        trPr = tr.get_or_add_trPr()
        for old in trPr.findall(qn('w:trHeight')):
            trPr.remove(old)
        trH = OxmlElement('w:trHeight')
        trH.set(qn('w:val'), str(twips(mm)))
        trH.set(qn('w:hRule'), 'atLeast')
        trPr.append(trH)

    def p(cell, parts, sb=0, sa=0):
        para = cell.add_paragraph()
        para.paragraph_format.space_before = Pt(sb)
        para.paragraph_format.space_after = Pt(sa)
        for text, bold, pt in parts:
            r = para.add_run(text)
            r.bold = bold
            r.font.size = Pt(pt)
        return para

    def fill_recipient(cell, client):
        set_cell_margins(cell)
        org = client['org_name_short'][:1].upper() + client['org_name_short'][1:]
        p0 = cell.paragraphs[0]
        p0.paragraph_format.space_before = Pt(0)
        p0.paragraph_format.space_after = Pt(2)
        r = p0.add_run("Кому:")
        r.bold = True
        r.font.size = Pt(FONT)
        p(cell, [(org, False, FONT)], sb=0, sa=3)
        p(cell, [("Куда:  ", True, FONT), (client['address'], False, FONT)], sb=0, sa=0)

    def fill_sender(cell):
        set_cell_margins(cell)
        p0 = cell.paragraphs[0]
        p0.paragraph_format.space_before = Pt(0)
        p0.paragraph_format.space_after = Pt(2)
        r = p0.add_run("От:")
        r.bold = True
        r.font.size = Pt(FONT)
        for line in SENDER_LINES:
            p(cell, [(line, False, FONT)], sb=0, sa=0)

    def make_table(doc, n_cells, fill_fn):
        """Создаёт таблицу 2 колонки × ceil(n/2) строк и заполняет ячейки через fill_fn(cell, idx)."""
        import math
        rows = math.ceil(n_cells / COLS)
        table = doc.add_table(rows=rows, cols=COLS)
        table.style = 'Table Grid'
        for r_idx in range(rows):
            set_row_height(table.rows[r_idx], CELL_H)
            for c_idx in range(COLS):
                idx = r_idx * COLS + c_idx
                cell = table.rows[r_idx].cells[c_idx]
                cell.width = Mm(CELL_W)
                set_dashed_border(cell)
                if idx < n_cells:
                    fill_fn(cell, idx)

    doc = Document()
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(10)
    section.right_margin = Mm(10)
    section.top_margin = Mm(10)
    section.bottom_margin = Mm(10)
    doc.styles['Normal'].paragraph_format.space_before = Pt(0)
    doc.styles['Normal'].paragraph_format.space_after = Pt(0)

    n = len(clients_data)

    # Лист 1: адресаты
    make_table(doc, n, lambda cell, i: fill_recipient(cell, clients_data[i]))

    # Лист 2: отправители
    doc.add_page_break()
    make_table(doc, n, lambda cell, i: fill_sender(cell))

    filename = "Шильдики_для_конвертов.docx"
    if to_file:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)
        doc.save(path)
        return path
    else:
        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf, filename


def build_acts_combined(acts_params, filename, to_file=False):
    """
    Объединяет несколько актов в один .docx файл.

    acts_params — список dict с ключами:
        contract_num, contract_date, act_date, client_dict, amount, service_desc

    Возвращает (BytesIO, filename) или сохраняет файл если to_file=True.
    """
    docs = []
    for p in acts_params:
        buf, _ = build_act(
            p['contract_num'], p['contract_date'], p['act_date'],
            p['client_dict'], p['amount'], p['service_desc'],
            to_file=False,
        )
        docs.append(Document(buf))

    if not docs:
        raise ValueError("Нет актов для объединения")

    # Ensure a page break between acts
    for doc in docs[:-1]:
        doc.add_page_break()

    # Первый документ — основа, остальные добавляем с разрывом страницы
    master = docs[0]
    if len(docs) > 1:
        composer = Composer(master)
        for doc in docs[1:]:
            composer.append(doc)

    buf = BytesIO()
    master.save(buf)
    buf.seek(0)

    if to_file:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, 'wb') as f:
            f.write(buf.read())
        return path
    else:
        buf.seek(0)
        return buf, filename
