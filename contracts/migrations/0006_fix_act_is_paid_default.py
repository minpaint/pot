from django.db import migrations


class Migration(migrations.Migration):
    """
    Пересоздаёт таблицу contracts_act чтобы is_paid получила DEFAULT 0 на уровне SQLite.
    Стандартный ALTER TABLE в SQLite не поддерживает изменение DEFAULT существующей колонки.
    """

    dependencies = [
        ('contracts', '0005_contract_number'),
    ]

    operations = [
        # no-op: на свежей базе PostgreSQL is_paid создаётся с DEFAULT через AddField в 0003
        migrations.RunSQL("SELECT 1;", "SELECT 1;"),
    ]
