# directory/models/quiz.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import random
import uuid

try:
    from model_utils.models import TimeStampedModel
except ModuleNotFoundError:
    class TimeStampedModel(models.Model):
        """Fallback replacement if django-model-utils is unavailable."""

        created = models.DateTimeField(auto_now_add=True)
        modified = models.DateTimeField(auto_now=True)

        class Meta:
            abstract = True


class QuizCategory(TimeStampedModel):
    """Раздел/тема экзамена (например, "Общие вопросы по охране труда")"""

    name = models.CharField(
        max_length=200,
        verbose_name=_("Название раздела"),
        help_text=_("Например: Общие вопросы по охране труда")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Описание"),
        help_text=_("Краткое описание раздела")
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_("Порядок сортировки"),
        help_text=_("Меньшее число - выше в списке")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активна"),
        help_text=_("Показывать ли этот раздел пользователям")
    )

    class Meta:
        verbose_name = _("📚 Раздел")
        verbose_name_plural = _("📚 Разделы")
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_questions_count(self):
        """Количество вопросов в разделе"""
        return self.questions.filter(is_active=True).count()


class QuizCategoryOrder(models.Model):
    """
    Промежуточная модель для связи Quiz и QuizCategory с порядком сортировки.
    Позволяет устанавливать индивидуальный порядок разделов для каждого экзамена.
    """
    quiz = models.ForeignKey(
        'Quiz',
        on_delete=models.CASCADE,
        verbose_name=_("Экзамен")
    )
    category = models.ForeignKey(
        QuizCategory,
        on_delete=models.CASCADE,
        verbose_name=_("Раздел")
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_("Порядок в экзамене"),
        help_text=_("Порядок отображения раздела в данном экзамене (меньшее число = выше)")
    )

    class Meta:
        verbose_name = _("🔢 Раздел в экзамене")
        verbose_name_plural = _("🔢 Разделы в экзамене")
        ordering = ['order', 'category__name']
        unique_together = [['quiz', 'category']]

    def __str__(self):
        return f"{self.quiz.title} - {self.category.name} (порядок: {self.order})"


class Quiz(TimeStampedModel):
    """Экзамен/тест по охране труда"""

    title = models.CharField(
        max_length=200,
        verbose_name=_("Название экзамена")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Описание")
    )
    categories = models.ManyToManyField(
        QuizCategory,
        through='QuizCategoryOrder',
        related_name='quizzes',
        blank=True,
        verbose_name=_("Разделы экзамена"),
        help_text=_("Выберите разделы, которые входят в этот экзамен")
    )

    # Настройки для экзамена
    questions_per_category = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name=_("Вопросов из каждого раздела"),
        help_text=_("[УСТАРЕЛО] Сколько случайных вопросов взять из КАЖДОГО раздела для итогового экзамена"),
        editable=False  # Скрываем из админки, но не удаляем из БД
    )
    exam_total_questions = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        verbose_name=_("Всего вопросов в экзамене"),
        help_text=_("Общее количество вопросов. Они будут распределены равномерно по всем разделам экзамена.")
    )
    use_adaptive_selection = models.BooleanField(
        default=False,
        verbose_name=_("Адаптивный подбор вопросов"),
        help_text=_(
            "Учитывать прогресс пользователя: приоритет вопросам с ошибками, "
            "затем новым вопросам, меньше - уже правильно отвеченным"
        )
    )
    exam_time_limit = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(360)],
        verbose_name=_("Лимит времени (минуты)"),
        help_text=_("Сколько минут даётся на прохождение экзамена")
    )
    exam_allowed_incorrect = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        verbose_name=_("Допустимые ошибки"),
        help_text=_("Экзамен завершается при достижении лимита неправильных ответов. 0 — без ограничения.")
    )
    random_order = models.BooleanField(
        default=True,
        verbose_name=_("Случайный порядок вопросов")
    )
    show_correct_answer = models.BooleanField(
        default=True,
        verbose_name=_("Показывать правильный ответ сразу"),
        help_text=_("Показывать правильность ответа после каждого вопроса")
    )
    allow_skip = models.BooleanField(
        default=True,
        verbose_name=_("Разрешить пропускать вопросы")
    )

    # Статистика
    attempts_count = models.IntegerField(
        default=0,
        verbose_name=_("Количество попыток")
    )

    # Назначение экзаменов пользователям
    assigned_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='assigned_quizzes',
        verbose_name=_("Назначен пользователям"),
        help_text=_("Оставьте пустым, чтобы экзамен был доступен всем")
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен")
    )

    class Meta:
        verbose_name = _("📝 Экзамен")
        verbose_name_plural = _("📝 Экзамены")
        ordering = ['-created']

    def __str__(self):
        return self.title

    def is_available_for_user(self, user):
        """Проверить, доступен ли экзамен для пользователя"""
        # Если нет назначенных пользователей, экзамен доступен всем
        if self.assigned_users.count() == 0:
            return True
        # Иначе проверяем, есть ли пользователь в списке назначенных
        return self.assigned_users.filter(id=user.id).exists()

    def get_questions_for_category(self, category):
        """Получить все вопросы для тренировки по разделу"""
        questions = Question.objects.filter(
            category=category,
            is_active=True
        ).order_by('order', 'id')

        if self.random_order:
            questions = list(questions)
            random.shuffle(questions)

        return questions

    def get_questions_for_exam(self, user=None):
        """Получить вопросы для итогового экзамена с РАВНОМЕРНЫМ распределением из всех разделов

        Алгоритм:
        1. Определяем количество активных категорий
        2. Распределяем exam_total_questions пропорционально между всеми категориями
        3. Базовое количество = exam_total_questions // количество_категорий
        4. Остаток распределяем по первым категориям (+1 вопрос)
        5. Если use_adaptive_selection=True и передан user:
           - Внутри каждой категории приоритизируем:
             * Вопросы с неправильными ответами (вес 3)
             * Новые вопросы, на которые не отвечал (вес 2)
             * Вопросы с правильными ответами (вес 1)

        Args:
            user: Пользователь для адаптивного подбора (опционально)

        Пример:
        - 15 категорий, exam_total_questions = 20
        - Базовое количество = 20 // 15 = 1 вопрос на категорию
        - Остаток = 20 % 15 = 5 вопросов
        - Первые 5 категорий получат по 2 вопроса (1 базовый + 1 бонусный)
        - Остальные 10 категорий получат по 1 вопросу
        - Итого: 5*2 + 10*1 = 20 вопросов из всех 15 категорий
        """
        # Получаем активные категории с активными вопросами
        categories = list(self.categories.filter(
            is_active=True,
            questions__is_active=True
        ).distinct().order_by('quizcategoryorder__order', 'name'))

        total_categories = len(categories)
        if total_categories == 0:
            return []

        max_questions = self.exam_total_questions

        # ПРОПОРЦИОНАЛЬНОЕ РАСПРЕДЕЛЕНИЕ
        # Базовое количество вопросов на категорию
        base_questions_per_category = max_questions // total_categories

        # Остаток вопросов, которые нужно распределить
        remainder = max_questions % total_categories

        questions = []

        for i, category in enumerate(categories):
            # Все категории получают базовое количество
            questions_to_take = base_questions_per_category

            # Первые N категорий получают по +1 вопросу (где N = remainder)
            if i < remainder:
                questions_to_take += 1

            # Если вдруг получилось 0 вопросов (очень много категорий), берем хотя бы 1
            if questions_to_take == 0 and i < max_questions:
                questions_to_take = 1

            # Берем все доступные вопросы из категории
            category_questions = list(Question.objects.filter(
                category=category,
                is_active=True
            ))

            if not category_questions:
                continue

            # Не берем больше, чем есть в категории
            questions_to_take = min(questions_to_take, len(category_questions))

            if questions_to_take > 0:
                # АДАПТИВНЫЙ ПОДБОР: учитываем прогресс пользователя
                if self.use_adaptive_selection and user:
                    selected = self._adaptive_select_questions(
                        category_questions, questions_to_take, user, category
                    )
                else:
                    # Стандартный случайный выбор
                    selected = random.sample(category_questions, questions_to_take)

                questions.extend(selected)

        # Перемешиваем финальный список (если включено)
        if self.random_order:
            random.shuffle(questions)

        return questions

    def _adaptive_select_questions(self, category_questions, count, user, category):
        """Адаптивный выбор вопросов на основе прогресса пользователя

        Args:
            category_questions: Список вопросов из категории
            count: Сколько вопросов нужно выбрать
            user: Пользователь
            category: Категория

        Returns:
            Список выбранных вопросов
        """
        # Импортируем здесь, чтобы избежать циклических импортов
        from .quiz import UserAnswer, QuizAttempt

        # Получаем все ответы пользователя по этому квизу и категории
        user_answers = UserAnswer.objects.filter(
            attempt__user=user,
            attempt__quiz=self,
            question__category=category,
            is_skipped=False
        ).select_related('question')

        # Группируем по вопросам: какие правильно, какие нет
        incorrect_question_ids = set()
        correct_question_ids = set()

        for answer in user_answers:
            if answer.is_correct:
                correct_question_ids.add(answer.question_id)
            else:
                incorrect_question_ids.add(answer.question_id)

        # Разделяем вопросы на 3 группы с весами
        questions_with_weights = []

        for question in category_questions:
            if question.id in incorrect_question_ids:
                # Вопросы с ошибками - высокий приоритет (вес 3)
                weight = 3
            elif question.id in correct_question_ids:
                # Вопросы с правильными ответами - низкий приоритет (вес 1)
                weight = 1
            else:
                # Новые вопросы - средний приоритет (вес 2)
                weight = 2

            questions_with_weights.append((question, weight))

        # Взвешенный случайный выбор
        # Создаем список, где каждый вопрос повторяется weight раз
        weighted_pool = []
        for question, weight in questions_with_weights:
            weighted_pool.extend([question] * weight)

        # Выбираем случайные вопросы из взвешенного пула
        # Используем set для исключения дубликатов
        selected = []
        remaining_pool = weighted_pool.copy()

        while len(selected) < count and remaining_pool:
            # Выбираем случайный вопрос
            chosen = random.choice(remaining_pool)

            # Если его ещё нет в выбранных - добавляем
            if chosen not in selected:
                selected.append(chosen)

            # Удаляем ВСЕ копии этого вопроса из пула
            remaining_pool = [q for q in remaining_pool if q.id != chosen.id]

        return selected

    def get_total_questions_for_category(self, category):
        """Количество вопросов в конкретном разделе"""
        return Question.objects.filter(category=category, is_active=True).count()

    def get_total_questions_for_exam(self):
        """Общее количество вопросов для итогового экзамена с учетом равномерного распределения

        Возвращает реальное количество вопросов, которое будет в экзамене,
        с учетом того, что вопросы распределяются равномерно между всеми категориями.
        """
        # Получаем активные категории с активными вопросами
        categories = list(self.categories.filter(
            is_active=True,
            questions__is_active=True
        ).distinct())

        total_categories = len(categories)
        if total_categories == 0:
            return 0

        max_questions = self.exam_total_questions

        # Базовое количество вопросов на категорию
        base_questions_per_category = max_questions // total_categories
        remainder = max_questions % total_categories

        total = 0

        for i, category in enumerate(categories):
            # Вычисляем, сколько вопросов должна дать эта категория
            questions_to_take = base_questions_per_category
            if i < remainder:
                questions_to_take += 1

            if questions_to_take == 0 and i < max_questions:
                questions_to_take = 1

            # Проверяем, сколько реально есть вопросов в категории
            questions_count = Question.objects.filter(
                category=category,
                is_active=True
            ).count()

            # Берем минимум из того, что планировали и что есть
            total += min(questions_to_take, questions_count)

        return total

    def get_exam_categories(self):
        """Получить список разделов, которые входят в экзамен с учетом порядка"""
        return self.categories.filter(
            is_active=True,
            questions__is_active=True
        ).distinct().order_by('quizcategoryorder__order', 'name')


class Question(TimeStampedModel):
    """Вопрос экзамена"""

    category = models.ForeignKey(
        QuizCategory,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name=_("Раздел")
    )
    question_text = models.TextField(
        verbose_name=_("Текст вопроса")
    )
    image = models.ImageField(
        upload_to='quiz/questions/',
        blank=True,
        null=True,
        verbose_name=_("Изображение"),
        help_text=_("Иллюстрация к вопросу")
    )
    explanation = models.TextField(
        blank=True,
        verbose_name=_("Пояснение"),
        help_text=_("Объяснение правильного ответа")
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_("Порядок"),
        help_text=_("Для сортировки вопросов")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен")
    )

    class Meta:
        verbose_name = _("❓ Вопрос")
        verbose_name_plural = _("❓ Вопросы")
        ordering = ['category', 'order', 'id']

    def __str__(self):
        return f"Вопрос #{self.id}: {self.question_text[:50]}..."

    def save(self, *args, **kwargs):
        """
        Переопределяем save для сохранения PNG с прозрачностью.

        Django/Pillow по умолчанию может конвертировать PNG изображения,
        теряя альфа-канал (прозрачность). Этот метод предотвращает это.
        """
        # Сохраняем модель как обычно - Django сам обработает загрузку изображения
        # ImageField не конвертирует изображения автоматически, он просто сохраняет файл как есть
        super().save(*args, **kwargs)

    @property
    def text(self):
        """Алиас для question_text для обратной совместимости"""
        return self.question_text

    def get_answers(self):
        """Получить все варианты ответов"""
        return self.answers.all()

    def get_correct_answer(self):
        """Получить правильный ответ"""
        return self.answers.filter(is_correct=True).first()


class Answer(TimeStampedModel):
    """Вариант ответа на вопрос"""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name=_("Вопрос")
    )
    answer_text = models.TextField(
        verbose_name=_("Текст ответа")
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=_("Правильный ответ")
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_("Порядок"),
        help_text=_("Порядок отображения ответа")
    )

    class Meta:
        verbose_name = _("💬 Ответ")
        verbose_name_plural = _("💬 Ответы")
        ordering = ['question', 'order', 'id']

    def __str__(self):
        correct_mark = " ✓" if self.is_correct else ""
        return f"{self.answer_text[:50]}{correct_mark}"

    @property
    def text(self):
        """Алиас для answer_text для обратной совместимости"""
        return self.answer_text


class QuizAttempt(TimeStampedModel):
    """Попытка прохождения экзамена"""

    FAILURE_NONE = ''
    FAILURE_TIMEOUT = 'timeout'
    FAILURE_INCORRECT = 'incorrect_limit'

    FAILURE_REASONS = [
        (FAILURE_NONE, _('Успешно завершено')),
        (FAILURE_TIMEOUT, _('Время вышло')),
        (FAILURE_INCORRECT, _('Превышен лимит ошибок')),
    ]

    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_ABANDONED = 'abandoned'

    STATUSES = [
        (STATUS_IN_PROGRESS, _('В процессе')),
        (STATUS_COMPLETED, _('Завершена')),
        (STATUS_ABANDONED, _('Прервана')),
    ]

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name=_("Экзамен")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
        verbose_name=_("Пользователь")
    )
    category = models.ForeignKey(
        QuizCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='training_attempts',
        verbose_name=_("Раздел тренировки"),
        help_text=_("Указывается только для тренировок по разделам. NULL = итоговый экзамен")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUSES,
        default=STATUS_IN_PROGRESS,
        verbose_name=_("Статус")
    )

    # Результаты
    total_questions = models.IntegerField(
        default=0,
        verbose_name=_("Всего вопросов")
    )
    correct_answers = models.IntegerField(
        default=0,
        verbose_name=_("Правильных ответов")
    )
    skipped_questions = models.IntegerField(
        default=0,
        verbose_name=_("Пропущено вопросов")
    )
    incorrect_answers = models.IntegerField(
        default=0,
        verbose_name=_("Неправильных ответов")
    )
    score_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Результат (%)")
    )
    passed = models.BooleanField(
        default=False,
        verbose_name=_("Тест пройден")
    )
    time_limit_seconds = models.IntegerField(
        default=0,
        verbose_name=_("Лимит времени (сек)"),
        help_text=_("Сохраняем настройку на момент начала попытки")
    )
    allowed_incorrect_answers = models.IntegerField(
        default=0,
        verbose_name=_("Лимит ошибок"),
        help_text=_("Сохраняем настройку на момент начала попытки")
    )
    max_questions = models.IntegerField(
        default=0,
        verbose_name=_("Лимит вопросов"),
        help_text=_("Сохраняем настройку на момент начала попытки")
    )
    failure_reason = models.CharField(
        max_length=20,
        choices=FAILURE_REASONS,
        default=FAILURE_NONE,
        verbose_name=_("Причина завершения")
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Начало")
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Завершение")
    )

    class Meta:
        verbose_name = _("📊 Попытка прохождения")
        verbose_name_plural = _("📊 Попытки прохождения")
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} ({self.get_status_display()})"

    def is_exam_mode(self):
        """Определить, является ли попытка экзаменом (True) или тренировкой (False)

        Логика:
        - Если category указана → тренировка по разделу
        - Иначе → итоговый экзамен
        """
        return self.category is None

    def calculate_score(self):
        """Пересчитать результат и статус

        Логика определения типа:
        - Если category указана → тренировка по разделу
        - Иначе → итоговый экзамен
        """
        if self.total_questions > 0:
            self.score_percentage = (self.correct_answers / self.total_questions) * 100
        else:
            self.score_percentage = 0

        if self.is_exam_mode():
            # Итоговый экзамен: строгие правила
            self.passed = (
                self.failure_reason == self.FAILURE_NONE
                and (self.allowed_incorrect_answers == 0 or self.incorrect_answers <= self.allowed_incorrect_answers)
            )
        else:
            # Тренировка: показываем только статистику, без оценки "пройдено/не пройдено"
            # Но для совместимости с БД сохраняем passed=True если все ответы правильные
            self.passed = self.total_questions > 0 and self.correct_answers == self.total_questions
        self.save()

class UserAnswer(TimeStampedModel):
    """Ответ пользователя на вопрос"""

    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='user_answers',
        verbose_name=_("Попытка")
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name=_("Вопрос")
    )
    selected_answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Выбранный ответ"),
        help_text=_("NULL если вопрос пропущен")
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=_("Правильно")
    )
    is_skipped = models.BooleanField(
        default=False,
        verbose_name=_("Пропущен")
    )
    answered_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Время ответа")
    )

    class Meta:
        verbose_name = _("✍️ Ответ пользователя")
        verbose_name_plural = _("✍️ Ответы пользователей")
        ordering = ['answered_at']
        unique_together = ['attempt', 'question']

    def __str__(self):
        return f"{self.attempt.user.username} - Вопрос #{self.question.id}"


class QuizAccessToken(TimeStampedModel):
    """Токен для временного доступа к экзамену"""

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_("Токен доступа")
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='access_tokens',
        verbose_name=_("Экзамен")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_access_tokens',
        verbose_name=_("Пользователь"),
        help_text=_("Пользователь, которому предоставлен доступ")
    )

    # Временные ограничения
    valid_from = models.DateTimeField(
        verbose_name=_("Действителен с"),
        help_text=_("Начало периода доступа")
    )
    valid_until = models.DateTimeField(
        verbose_name=_("Действителен до"),
        help_text=_("Окончание периода доступа")
    )

    # Состояние использования
    is_used = models.BooleanField(
        default=False,
        verbose_name=_("Использован"),
        help_text=_("Токен становится использованным после первого запуска экзамена")
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Дата использования")
    )

    # Настройки поведения токена
    require_login = models.BooleanField(
        default=True,
        verbose_name=_("Требовать авторизацию"),
        help_text=_("Должен ли пользователь авторизоваться для использования токена")
    )
    allow_resume = models.BooleanField(
        default=True,
        verbose_name=_("Разрешить продолжение"),
        help_text=_("Может ли пользователь продолжить экзамен после перерыва")
    )
    max_attempts = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("Максимум попыток"),
        help_text=_("Сколько раз можно начать экзамен по этому токену")
    )
    current_attempts = models.IntegerField(
        default=0,
        verbose_name=_("Текущее количество попыток")
    )

    # Дополнительная информация
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_quiz_tokens',
        verbose_name=_("Создал токен")
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Описание"),
        help_text=_("Дополнительная информация о токене")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен"),
        help_text=_("Можно деактивировать токен досрочно")
    )

    class Meta:
        verbose_name = _("🔑 Токен доступа к экзамену")
        verbose_name_plural = _("🔑 Токены доступа к экзаменам")
        ordering = ['-created']
        unique_together = [['quiz', 'user']]

    def __str__(self):
        return f"Токен для {self.user.username} - {self.quiz.title}"

    def is_valid(self):
        """Проверка валидности токена"""
        if not self.is_active:
            return False, _("Токен деактивирован")

        # Проверяем is_used только если НЕ разрешено возобновление
        # Если allow_resume = True, пользователь может вернуться по токену для продолжения
        if self.is_used and not self.allow_resume:
            return False, _("Токен уже был использован")

        now = timezone.now()
        if now < self.valid_from:
            return False, _("Токен еще не активен")

        if now > self.valid_until:
            return False, _("Срок действия токена истек")

        return True, _("Токен действителен")

    def mark_as_used(self):
        """Отметить токен как использованный"""
        if not self.is_used:
            self.is_used = True
            self.used_at = timezone.now()
            self.save(update_fields=['is_used', 'used_at'])

    def get_access_url(self):
        """Получить полный URL для доступа к экзамену"""
        from django.urls import reverse
        return reverse('directory:quiz:token_access', kwargs={'token': self.token})


class QuizQuestionOrder(models.Model):
    """Порядок вопросов для конкретной попытки экзамена

    Хранит порядок вопросов в БД вместо сессии,
    что позволяет возобновлять экзамен после перерыва.
    """

    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='question_orders',
        verbose_name=_("Попытка")
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name=_("Вопрос")
    )
    order = models.IntegerField(
        verbose_name=_("Порядковый номер"),
        help_text=_("Позиция вопроса в экзамене (начинается с 0)")
    )

    class Meta:
        verbose_name = _("🔢 Порядок вопроса")
        verbose_name_plural = _("🔢 Порядок вопросов")
        unique_together = [['attempt', 'order'], ['attempt', 'question']]
        ordering = ['attempt', 'order']
        indexes = [
            models.Index(fields=['attempt', 'order']),
        ]

    def __str__(self):
        return f"Попытка #{self.attempt.id} - Вопрос {self.order + 1}"
