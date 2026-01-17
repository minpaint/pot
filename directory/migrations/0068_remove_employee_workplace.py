from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0067_add_prior_qualification_and_workplace'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='employee',
            name='workplace',
        ),
    ]
