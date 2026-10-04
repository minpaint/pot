"""
⚙️ Views для отслеживания асинхронных задач генерации документов.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView
from django.urls import reverse
from urllib.parse import quote

from directory.models import GenerationJob


class GenerationJobAccessMixin:
    """Ограничивает доступ к задачам автора (или суперпользователю)."""

    def get_queryset(self):
        qs = GenerationJob.objects.all()
        if not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        return qs


# Страница, откуда запускается генерация: тип задачи → (имя URL, подпись кнопки «Назад»)
JOB_BACK_LINKS = {
    'siz_cards_bulk': ('directory:siz:mass_generation', 'Карточки СИЗ'),
    'siz_cards_org': ('directory:siz:mass_generation', 'Карточки СИЗ'),
    'instruction_journal_unified': ('directory:documents:instruction_journal', 'Журнал инструктажей'),
    'instruction_journal_by_sub': ('directory:documents:instruction_journal', 'Журнал инструктажей'),
    'ot_card_bulk': ('directory:ot_card:mass_generation', 'Личные карточки по ОТ'),
    'periodic_protocol': ('directory:documents:periodic_protocol', 'Проверка знаний'),
    'periodic_protocol_by_sub': ('directory:documents:periodic_protocol', 'Проверка знаний'),
    'periodic_certificates': ('directory:documents:periodic_protocol', 'Проверка знаний'),
    'periodic_certificates_by_sub': ('directory:documents:periodic_protocol', 'Проверка знаний'),
    'admin_hiring_generate': ('admin:directory_employeehiring_changelist', 'Приёмы на работу'),
}


class GenerationJobListView(LoginRequiredMixin, GenerationJobAccessMixin, ListView):
    model = GenerationJob
    template_name = 'directory/generation_jobs/list.html'
    context_object_name = 'jobs'
    paginate_by = 30


class GenerationJobDetailView(LoginRequiredMixin, GenerationJobAccessMixin, DetailView):
    model = GenerationJob
    template_name = 'directory/generation_jobs/detail.html'
    context_object_name = 'job'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target = JOB_BACK_LINKS.get(self.object.job_type)
        if target:
            context['back_url'] = reverse(target[0])
            context['back_label'] = target[1]
        return context


class GenerationJobStatusView(LoginRequiredMixin, GenerationJobAccessMixin, DetailView):
    """JSON-эндпоинт для AJAX-polling прогресса."""
    model = GenerationJob

    def get(self, request, *args, **kwargs):
        job = self.get_object()
        return JsonResponse({
            'id': job.id,
            'status': job.status,
            'status_display': job.get_status_display(),
            'progress_current': job.progress_current,
            'progress_total': job.progress_total,
            'progress_percent': job.progress_percent,
            'is_finished': job.is_finished,
            'error_message': job.error_message,
            'result_filename': job.result_filename,
            'download_url': reverse('directory:generation_job_download', args=[job.id])
                             if job.status == 'done' and job.result_file else '',
        })


class GenerationJobDownloadView(LoginRequiredMixin, GenerationJobAccessMixin, DetailView):
    model = GenerationJob

    def get(self, request, *args, **kwargs):
        job = self.get_object()
        if job.status != 'done' or not job.result_file:
            raise Http404('Файл недоступен')

        filename = job.result_filename or f'job_{job.id}.bin'
        filename_encoded = quote(filename)

        try:
            file_path = job.result_file.path
            with open(file_path, 'rb') as f:
                content = f.read()
        except (OSError, ValueError):
            raise Http404('Файл не найден на диске')

        resp = HttpResponse(content, content_type=job.content_type or 'application/octet-stream')
        resp['Content-Length'] = len(content)
        resp['Content-Disposition'] = f'attachment; filename="document"; filename*=UTF-8\'\'{filename_encoded}'
        return resp
