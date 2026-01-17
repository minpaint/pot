import datetime
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from directory.models import Employee, Organization
from directory.utils.declension import decline_phrase

from production_training.models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    TrainingProgram,
    TrainingProgramSection,
    TrainingEntryType,
    TrainingProgramEntry,
    TrainingRoleType,
    ProductionTraining,
)

logger = logging.getLogger(__name__)

NS = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL_NS = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def excel_serial_to_date(value):
    if value in (None, ''):
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    # Excel serial date (1900-based)
    base = datetime.date(1899, 12, 30)
    return base + datetime.timedelta(days=int(val))


def parse_workbook(path):
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = []
        for sheet in wb.findall('main:sheets/main:sheet', NS):
            sheets.append((
                sheet.attrib['name'],
                sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            ))

        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rid_to_target = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels.findall('rel:Relationship', REL_NS)}

        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            sst = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in sst.findall('main:si', NS):
                texts = [t.text or '' for t in si.findall('.//main:t', NS)]
                shared.append(''.join(texts))

        return z, sheets, rid_to_target, shared


def parse_sheet(z, sheet_path, shared):
    root = ET.fromstring(z.read(sheet_path))
    rows = defaultdict(dict)
    for c in root.findall('.//main:c', NS):
        ref = c.attrib.get('r')
        ctype = c.attrib.get('t')
        v = c.find('main:v', NS)
        if v is None:
            continue
        val = v.text or ''
        if ctype == 's':
            try:
                val = shared[int(val)]
            except Exception:
                pass
        col = ''.join([ch for ch in ref if ch.isalpha()])
        row = int(''.join([ch for ch in ref if ch.isdigit()]))
        rows[row][col] = val
    return rows


def get_sheet_path(sheets, rid_to_target, sheet_name):
    for name, rid in sheets:
        if name == sheet_name:
            target = rid_to_target.get(rid)
            return f"xl/{target}" if target else None
    return None


def iter_column(rows, col):
    for r in sorted(rows.keys()):
        val = rows[r].get(col)
        if val is None:
            continue
        yield r, str(val).strip()


class Command(BaseCommand):
    help = 'Импортирует справочники и программы обучения из Excel (xlsm)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default='learning/Обучение на производстве_Сфера Торговый дом.xlsm',
            help='Путь к Excel файлу (xlsm)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = options['path']
        z, sheets, rid_to_target, shared = parse_workbook(path)

        professions_path = get_sheet_path(sheets, rid_to_target, 'Профессии (данные)')
        base_path = get_sheet_path(sheets, rid_to_target, 'База')
        roles_path = get_sheet_path(sheets, rid_to_target, 'Ответственные (данные)')
        diary_retrain_path = get_sheet_path(sheets, rid_to_target, '4. Дневник (переподготовка)')
        diary_prepare_path = get_sheet_path(sheets, rid_to_target, '4.1 Дневник (подготовка)')

        if not professions_path or not base_path or not roles_path:
            raise ValueError('Не найдены обязательные листы в Excel файле')

        base_rows = parse_sheet(z, professions_path, shared)
        self._import_professions(base_rows)

        base_rows = parse_sheet(z, base_path, shared)

        role_rows = parse_sheet(z, roles_path, shared)
        self._import_role_types(role_rows)

        retrain_type = self._get_or_create_training_type('retraining', 'Переподготовка')
        prepare_type = self._get_or_create_training_type('preparation', 'Подготовка')

        entry_type = self._get_or_create_entry_type('practice', 'Производственное обучение')

        if diary_retrain_path:
            retrain_rows = parse_sheet(z, diary_retrain_path, shared)
            self._import_program_from_diary(
                retrain_rows,
                retrain_type,
                entry_type,
                'Дневник (переподготовка)'
            )

        if diary_prepare_path:
            prepare_rows = parse_sheet(z, diary_prepare_path, shared)
            self._import_program_from_diary(
                prepare_rows,
                prepare_type,
                entry_type,
                'Дневник (подготовка)'
            )

        self._import_training_records(base_rows)

        self.stdout.write(self.style.SUCCESS('Импорт завершен'))

    def _get_or_create_training_type(self, code, name_ru):
        obj, _ = TrainingType.objects.get_or_create(
            code=code,
            defaults={'name_ru': name_ru, 'is_active': True}
        )
        return obj

    def _get_or_create_entry_type(self, code, name):
        obj, _ = TrainingEntryType.objects.get_or_create(
            code=code,
            defaults={'name': name, 'is_active': True}
        )
        return obj

    def _import_professions(self, rows):
        created = 0
        for _, value in iter_column(rows, 'A'):
            if value == 'Профессия' or not value:
                continue
            genitive = rows.get(_, {}).get('B', '').strip()
            if not genitive:
                genitive = decline_phrase(value, 'gent')
            obj, was_created = TrainingProfession.objects.get_or_create(
                name_ru_nominative=value,
                name_ru_genitive=genitive,
                defaults={'is_active': True}
            )
            if was_created:
                created += 1
        self.stdout.write(f'Профессии обучения: создано {created}')

    def _import_role_types(self, rows):
        role_names = set()
        for cell in ('A2', 'A3', 'C7', 'G7', 'I7'):
            col = ''.join([c for c in cell if c.isalpha()])
            row = int(''.join([c for c in cell if c.isdigit()]))
            val = rows.get(row, {}).get(col, '').strip()
            if val:
                role_names.add(val)

        created = 0
        for name in sorted(role_names):
            code = slugify(name)
            obj, was_created = TrainingRoleType.objects.get_or_create(
                code=code,
                defaults={'name': name, 'is_active': True}
            )
            if was_created:
                created += 1
        self.stdout.write(f'Роли обучения: создано {created}')

    def _extract_profession_from_rows(self, rows):
        for row in rows.values():
            for value in row.values():
                text = str(value)
                if '«' in text and '»' in text:
                    match = re.search(r'«([^»]+)»', text)
                    if match:
                        return match.group(1).strip()
        return None

    def _get_or_create_profession(self, name):
        if not name:
            return TrainingProfession.objects.first()
        genitive = decline_phrase(name, 'gent')
        obj, _ = TrainingProfession.objects.get_or_create(
            name_ru_nominative=name,
            name_ru_genitive=genitive,
            defaults={'is_active': True}
        )
        return obj

    def _import_program_from_diary(self, rows, training_type, entry_type, program_title):
        profession_name = self._extract_profession_from_rows(rows)
        profession = self._get_or_create_profession(profession_name)

        grade = self._extract_grade(rows)

        program, _ = TrainingProgram.objects.get_or_create(
            name=program_title,
            training_type=training_type,
            profession=profession,
            defaults={
                'qualification_grade': grade,
                'is_active': True,
            }
        )

        section, _ = TrainingProgramSection.objects.get_or_create(
            program=program,
            title=program_title,
            defaults={'order': 1}
        )

        header_row = self._find_header_row(rows)
        if not header_row:
            return

        order = 1
        for r in range(header_row + 1, max(rows.keys()) + 1):
            row = rows.get(r, {})
            texts = self._extract_topic_texts(row)
            if not texts:
                continue

            hours = self._parse_hours(row.get('D'))
            for text in texts:
                TrainingProgramEntry.objects.get_or_create(
                    section=section,
                    entry_type=entry_type,
                    topic=text,
                    defaults={'hours': hours, 'order': order}
                )
                order += 1

        self.stdout.write(f'Программа {program_title}: записей {order - 1}')

    def _find_header_row(self, rows):
        for r, cols in rows.items():
            for v in cols.values():
                text = str(v)
                if 'Раздел' in text and 'работ' in text:
                    return r
        return None

    def _extract_topic_texts(self, row):
        texts = []
        for col in ('C', 'E', 'F', 'G'):
            value = str(row.get(col, '')).strip()
            if not value:
                continue
            if value.isdigit():
                continue
            if value in ('№ п/п', 'Дата', 'Количество часов', 'Раздел (тема, вид выполняемых работ)'):
                continue
            texts.append(value)
        return texts

    def _parse_hours(self, value):
        if value in (None, ''):
            return Decimal('0')
        try:
            return Decimal(str(value).replace(',', '.'))
        except Exception:
            return Decimal('0')

    def _extract_grade(self, rows):
        for row in rows.values():
            for value in row.values():
                text = str(value)
                if 'КВАЛИФИКАЦИОННЫЙ' in text:
                    match = re.search(r'(\d+)', text)
                    if not match:
                        continue
                    grade_number = int(match.group(1))
                    label_ru = text.strip()
                    grade, _ = TrainingQualificationGrade.objects.get_or_create(
                        grade_number=grade_number,
                        label_ru=label_ru,
                        defaults={'is_active': True}
                    )
                    return grade
        return None

    def _import_training_records(self, rows):
        created = 0
        for r, marker in iter_column(rows, 'A'):
            if marker.lower() != 'a':
                continue
            full_name = str(rows.get(r, {}).get('C', '')).strip()
            if not full_name:
                continue
            employee = Employee.objects.filter(full_name_nominative=full_name).first()
            if not employee:
                self.stdout.write(self.style.WARNING(
                    f'Сотрудник не найден: {full_name} (строка {r})'
                ))
                continue

            prior_qualification = str(rows.get(r, {}).get('I', '')).strip()
            training_type_code = 'retraining' if prior_qualification else 'preparation'
            training_type = TrainingType.objects.filter(code=training_type_code).first()
            profession = TrainingProfession.objects.first()

            education_level_name = str(rows.get(r, {}).get('G', '')).strip()
            if education_level_name and not employee.education_level:
                employee.education_level = education_level_name
                employee.save(update_fields=['education_level'])

            start_date = excel_serial_to_date(rows.get(r, {}).get('R'))
            if not start_date:
                start_date = excel_serial_to_date(rows.get(r, {}).get('B'))
            end_date = excel_serial_to_date(rows.get(r, {}).get('T'))

            training, was_created = ProductionTraining.objects.get_or_create(
                employee=employee,
                organization=employee.organization,
                profession=profession,
                training_type=training_type,
                defaults={
                    'subdivision': employee.subdivision,
                    'department': employee.department,
                    'current_position': employee.position,
                    'prior_qualification': prior_qualification,
                    'start_date': start_date,
                    'end_date': end_date,
                    'registration_number': str(rows.get(r, {}).get('K', '')).strip(),
                    'protocol_number': str(rows.get(r, {}).get('L', '')).strip(),
                    'issue_date': excel_serial_to_date(rows.get(r, {}).get('M')),
                    'status': 'draft',
                }
            )
            if was_created:
                created += 1

        self.stdout.write(f'Карточки обучения: создано {created}')
