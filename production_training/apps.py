from django.apps import AppConfig


class ProductionTrainingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'production_training'
    verbose_name = '🎓 Обучение на производстве'
