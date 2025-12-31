from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0055_add_adaptive_selection'),
    ]

    operations = [
        migrations.AddField(
            model_name='documenttemplatetype',
            name='show_in_hiring',
            field=models.BooleanField(
                default=True,
                verbose_name=_('Показывать при приеме'),
                help_text=_('Определяет, отображается ли тип документа в списке для скачивания при приеме на работу'),
            ),
        ),
    ]
