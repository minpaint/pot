"""
Management команда для восстановления картинок вопросов quiz из бэкапа базы данных.

Использование:
    py manage.py restore_quiz_images путь_к_бэкапу.db

Команда:
1. Подключается к бэкапу базы данных (SQLite)
2. Извлекает данные о картинках из таблицы directory_question
3. Обновляет текущую базу данных, восстанавливая пути к картинкам
4. Проверяет существование файлов картинок

Опции:
    --dry-run : Только показать что будет восстановлено, не изменять БД
    --check-files : Проверить существование файлов картинок
"""

import sqlite3
import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from directory.models import Question


class Command(BaseCommand):
    help = 'Восстановление картинок вопросов quiz из бэкапа базы данных'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_db',
            type=str,
            help='Путь к файлу бэкапа базы данных (SQLite)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать изменения без применения'
        )
        parser.add_argument(
            '--check-files',
            action='store_true',
            help='Проверить существование файлов картинок'
        )
        parser.add_argument(
            '--match-by-text',
            action='store_true',
            help='Сопоставлять вопросы по тексту, а не по ID (для случаев пересоздания вопросов)'
        )

    def handle(self, *args, **options):
        backup_db_path = options['backup_db']
        dry_run = options['dry_run']
        check_files = options['check_files']
        match_by_text = options['match_by_text']

        # Проверяем существование файла бэкапа
        if not os.path.exists(backup_db_path):
            raise CommandError(f'Файл бэкапа не найден: {backup_db_path}')

        self.stdout.write(self.style.SUCCESS(f'Открываю бэкап: {backup_db_path}'))

        # Подключаемся к бэкапу
        try:
            backup_conn = sqlite3.connect(backup_db_path)
            backup_cursor = backup_conn.cursor()
        except Exception as e:
            raise CommandError(f'Ошибка подключения к бэкапу: {e}')

        # Проверяем наличие таблицы directory_question
        backup_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='directory_question'"
        )
        if not backup_cursor.fetchone():
            raise CommandError('Таблица directory_question не найдена в бэкапе')

        # Извлекаем данные о картинках из бэкапа
        self.stdout.write('Извлекаю данные о картинках из бэкапа...')
        backup_cursor.execute(
            """
            SELECT id, question_text, image
            FROM directory_question
            WHERE image IS NOT NULL AND image != ''
            ORDER BY id
            """
        )
        backup_images = backup_cursor.fetchall()

        if not backup_images:
            self.stdout.write(self.style.WARNING('В бэкапе не найдено вопросов с картинками'))
            backup_conn.close()
            return

        self.stdout.write(
            self.style.SUCCESS(f'Найдено {len(backup_images)} вопросов с картинками в бэкапе')
        )

        # Статистика
        restored_count = 0
        missing_files = []
        not_found_questions = []
        already_have_images = []

        media_root = Path(settings.MEDIA_ROOT)

        # Обрабатываем каждую запись
        for question_id, question_text, image_path in backup_images:
            # Определяем способ поиска вопроса
            if match_by_text:
                # Ищем по тексту вопроса
                questions = Question.objects.filter(question_text=question_text)
                if not questions.exists():
                    not_found_questions.append((question_id, question_text[:50]))
                    continue
                question = questions.first()
            else:
                # Ищем по ID (старый способ)
                try:
                    question = Question.objects.get(id=question_id)
                except Question.DoesNotExist:
                    not_found_questions.append((question_id, question_text[:50]))
                    continue

            # Проверяем, есть ли уже картинка
            if question.image:
                already_have_images.append((question_id, question.image.name))
                continue

            # Проверяем существование файла, если требуется
            if check_files:
                file_path = media_root / image_path
                if not file_path.exists():
                    missing_files.append((question_id, image_path))
                    continue

            # Выводим информацию
            if match_by_text:
                self.stdout.write(
                    f'  [Backup ID:{question_id} => Current ID:{question.id}] {question_text[:50]}... -> {image_path}'
                )
            else:
                self.stdout.write(
                    f'  [{question_id}] {question_text[:50]}... -> {image_path}'
                )

            # Обновляем БД если не dry-run
            if not dry_run:
                question.image = image_path
                question.save(update_fields=['image'])
                restored_count += 1
            else:
                restored_count += 1

        backup_conn.close()

        # Выводим итоговую статистику
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'Восстановлено: {restored_count}'))

        if already_have_images:
            self.stdout.write(
                self.style.WARNING(f'Уже имели картинки: {len(already_have_images)}')
            )
            if len(already_have_images) <= 10:
                for qid, img in already_have_images:
                    self.stdout.write(f'  [{qid}] {img}')

        if not_found_questions:
            self.stdout.write(
                self.style.WARNING(f'Вопросы не найдены в текущей БД: {len(not_found_questions)}')
            )
            if len(not_found_questions) <= 10:
                for qid, text in not_found_questions:
                    self.stdout.write(f'  [{qid}] {text}')

        if missing_files:
            self.stdout.write(
                self.style.ERROR(f'Файлы картинок не найдены: {len(missing_files)}')
            )
            if len(missing_files) <= 10:
                for qid, img in missing_files:
                    self.stdout.write(f'  [{qid}] {img}')

        if dry_run:
            self.stdout.write('\n' + self.style.WARNING('Режим --dry-run: изменения не применены'))
            self.stdout.write('Запустите без --dry-run для применения изменений')
        else:
            self.stdout.write('\n' + self.style.SUCCESS('Восстановление завершено!'))

        # Проверяем результат
        if not dry_run and restored_count > 0:
            self.stdout.write('\nПроверка результата:')
            total = Question.objects.count()
            with_images = Question.objects.exclude(image='').exclude(image__isnull=True).count()
            self.stdout.write(f'  Всего вопросов: {total}')
            self.stdout.write(f'  С картинками: {with_images}')
            self.stdout.write(f'  Без картинок: {total - with_images}')
