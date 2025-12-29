# directory/management/commands/copy_siz_norms_by_position_name.py
"""
Команда для копирования норм СИЗ между должностями с одинаковым названием
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from directory.models import Position, SIZNorm


class Command(BaseCommand):
    help = 'Копирует нормы СИЗ с одной должности на все должности с таким же названием'

    def add_arguments(self, parser):
        parser.add_argument(
            'position_name',
            type=str,
            help='Название должности (например, "Грузчик")'
        )
        parser.add_argument(
            '--source-id',
            type=int,
            help='ID должности-источника (если не указан, берется первая должность с нормами)'
        )
        parser.add_argument(
            '--organization',
            type=str,
            help='Фильтр по организации (короткое название)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать, что будет сделано, но не применять изменения'
        )

    def handle(self, *args, **options):
        position_name = options['position_name']
        source_id = options.get('source_id')
        org_filter = options.get('organization')
        dry_run = options['dry_run']

        self.stdout.write(f"\nПоиск должностей с названием: {position_name}\n")

        # Получаем все должности с таким названием
        positions = Position.objects.filter(position_name=position_name)

        if org_filter:
            positions = positions.filter(organization__short_name_ru__icontains=org_filter)
            self.stdout.write(f"  Фильтр по организации: {org_filter}\n")

        total_positions = positions.count()
        self.stdout.write(f"  Найдено должностей: {total_positions}\n")

        if total_positions == 0:
            self.stdout.write(self.style.ERROR("ОШИБКА: Должности не найдены"))
            return

        # Определяем должность-источник
        if source_id:
            source_position = positions.filter(id=source_id).first()
            if not source_position:
                self.stdout.write(self.style.ERROR(f"ОШИБКА: Должность с ID={source_id} не найдена"))
                return
        else:
            # Ищем первую должность с нормами
            source_position = None
            for pos in positions:
                if SIZNorm.objects.filter(position=pos).exists():
                    source_position = pos
                    break

            if not source_position:
                self.stdout.write(self.style.ERROR("ОШИБКА: Не найдено ни одной должности с нормами СИЗ"))
                return

        # Получаем нормы СИЗ с должности-источника
        source_norms = SIZNorm.objects.filter(position=source_position).select_related('siz')
        norms_count = source_norms.count()

        self.stdout.write(f"\nДолжность-источник:")
        self.stdout.write(f"  ID: {source_position.id}")
        self.stdout.write(f"  Название: {source_position.position_name}")
        self.stdout.write(f"  Организация: {source_position.organization.short_name_ru}")
        self.stdout.write(f"  Количество норм СИЗ: {norms_count}\n")

        if norms_count == 0:
            self.stdout.write(self.style.ERROR("ОШИБКА: У должности-источника нет норм СИЗ"))
            return

        # Показываем нормы
        self.stdout.write("  Нормы СИЗ:")
        for norm in source_norms:
            condition_str = f" (при условии: {norm.condition})" if norm.condition else ""
            self.stdout.write(f"    - {norm.siz.name} x{norm.quantity}{condition_str}")

        # Копируем нормы на остальные должности
        target_positions = positions.exclude(id=source_position.id)
        copied_count = 0
        skipped_count = 0

        self.stdout.write(f"\nКопирование норм на {target_positions.count()} должностей:\n")

        if not dry_run:
            with transaction.atomic():
                for target_pos in target_positions:
                    # Проверяем, есть ли уже нормы
                    existing_norms = SIZNorm.objects.filter(position=target_pos).count()

                    if existing_norms > 0:
                        self.stdout.write(
                            f"  >> {target_pos.organization.short_name_ru} (ID={target_pos.id}): "
                            f"Пропущено (уже есть {existing_norms} норм)"
                        )
                        skipped_count += 1
                        continue

                    # Копируем нормы
                    for norm in source_norms:
                        SIZNorm.objects.create(
                            position=target_pos,
                            siz=norm.siz,
                            quantity=norm.quantity,
                            condition=norm.condition,
                            order=norm.order
                        )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK {target_pos.organization.short_name_ru} (ID={target_pos.id}): "
                            f"Скопировано {norms_count} норм"
                        )
                    )
                    copied_count += 1
        else:
            # Сухой прогон - просто показываем, что будет сделано
            for target_pos in target_positions:
                existing_norms = SIZNorm.objects.filter(position=target_pos).count()

                if existing_norms > 0:
                    self.stdout.write(
                        f"  >> {target_pos.organization.short_name_ru} (ID={target_pos.id}): "
                        f"Пропущено (уже есть {existing_norms} норм)"
                    )
                    skipped_count += 1
                else:
                    self.stdout.write(
                        f"  [БУДЕТ] {target_pos.organization.short_name_ru} (ID={target_pos.id}): "
                        f"Будет скопировано {norms_count} норм"
                    )
                    copied_count += 1

        # Итоги
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Итоги:")
        if dry_run:
            self.stdout.write(f"  Будет скопировано на должностей: {copied_count}")
        else:
            self.stdout.write(f"  Скопировано на должностей: {copied_count}")
        self.stdout.write(f"  Пропущено (уже есть нормы): {skipped_count}")
        self.stdout.write(f"  Всего норм СИЗ на должность: {norms_count}")
        self.stdout.write(f"{'='*60}\n")

        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Нормы СИЗ успешно скопированы!"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "!! ТЕСТОВЫЙ РЕЖИМ - Для применения изменений запустите команду без флага --dry-run"
                )
            )
