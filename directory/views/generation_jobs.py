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


class GenerationJobListView(LoginRequiredMixin, GenerationJobAccessMixin, ListView):
    model = GenerationJob
    template_name = 'directory/generation_jobs/list.html'
    context_object_name = 'jobs'
    paginate_by = 30


class GenerationJobDetailView(LoginRequiredMixin, GenerationJobAccessMixin, DetailView):
    model = GenerationJob
    template_name = 'directory/generation_jobs/detail.html'
    context_object_name = 'job'


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
