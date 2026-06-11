"""
Проверка прав доступа к media-файлам (горизонтальная изоляция).

Без этой проверки любой залогиненный пользователь мог бы скачать документ
чужой организации, угадав путь (`/media/medical_referrals/.../referral_<id>_<ФИО>.docx`).

Сопоставление путь файла → организация-владелец:
  medical_referrals/    -> MedicalReferral.document            -> employee.organization
  medical_certificates/ -> EmployeeMedicalExamination.cert     -> employee.organization
  generated_documents/  -> GeneratedDocument.document_file      -> employee.organization
  generation_jobs/      -> GenerationJob.result_file            -> владелец (FK user, орг нет)
  document_templates/   -> бланки без ПДн                       -> достаточно логина
  quiz/                 -> картинки вопросов                    -> логин или токен-режим экзамена

Используется из protected_media() в urls.py.
"""
from directory.utils.permissions import AccessControlHelper


def can_access_media(request, path):
    """
    Возвращает True, если пользователю можно отдать media-файл по пути `path`
    (путь относительно MEDIA_ROOT, т.е. часть URL после /media/).
    """
    user = request.user

    # Картинки квизов нужны на exam.* поддомене в токен-режиме (пользователь НЕ залогинен).
    if path.startswith('quiz/'):
        return user.is_authenticated or bool(request.session.get('quiz_token_mode', False))

    # Всё остальное — только аутентифицированным.
    if not user.is_authenticated:
        return False

    # Суперпользователь видит всё.
    if user.is_superuser:
        return True

    # Файлы фоновых задач генерации привязаны к запустившему их пользователю
    # (у модели нет FK на организацию) — отдаём только владельцу.
    if path.startswith('generation_jobs/'):
        from directory.models import GenerationJob
        return GenerationJob.objects.filter(result_file=path, user=user).exists()

    # Файлы с ПДн — проверяем организацию связанного сотрудника.
    org = _resolve_owner_org(path)
    if org is not None:
        accessible = AccessControlHelper.get_accessible_organizations(user, request)
        return accessible.filter(id=org.id).exists()

    # document_templates/ (бланки без ПДн) и прочие нечувствительные media —
    # достаточно факта аутентификации.
    return True


def _resolve_owner_org(path):
    """
    Для путей с персональными данными возвращает организацию-владельца файла
    либо None, если префикс не относится к ПДн-файлам или объект не найден
    (осиротевший файл — доступ будет запрещён вызывающей стороной).
    """
    if path.startswith('medical_referrals/'):
        from deadline_control.models import MedicalReferral
        obj = (MedicalReferral.objects
               .select_related('employee__organization')
               .filter(document=path).first())
        return obj.employee.organization if obj else _DENY

    if path.startswith('medical_certificates/'):
        from deadline_control.models import EmployeeMedicalExamination
        obj = (EmployeeMedicalExamination.objects
               .select_related('employee__organization')
               .filter(medical_certificate=path).first())
        return obj.employee.organization if obj else _DENY

    if path.startswith('generated_documents/'):
        from directory.models import GeneratedDocument
        obj = (GeneratedDocument.objects
               .select_related('employee__organization')
               .filter(document_file=path).first())
        return obj.employee.organization if obj else _DENY

    return None


# Маркер «это ПДн-файл, но владелец не найден» — отличаем от «не ПДн-префикс» (None).
class _Deny:
    """Сентинел: ПДн-файл без найденного владельца → доступ запретить."""
    id = -1  # ни одна организация не имеет такой id → accessible.filter(id=-1) пуст


_DENY = _Deny()
