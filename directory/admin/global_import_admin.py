"""
📊 Админка для единого импорта/экспорта справочников

Позволяет импортировать и экспортировать три справочника в одном Excel-файле:
- Структура (Position)
- Сотрудники (Employee)
- Оборудование (Equipment)
"""
from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import HttpResponse
from django.contrib import messages
from django.utils.html import format_html

from directory.models import Organization
from directory.forms.global_import_forms import GlobalImportForm, GlobalExportForm
from directory.services.global_import import (
    parse_workbook,
    dry_run_import,
    commit_import,
    export_all_to_workbook
)


class GlobalImportExportAdmin:
    """
    🌐 Псевдо-админка для единого импорта/экспорта

    Это не ModelAdmin, а простой класс с методами для регистрации в admin.site
    """

    def __init__(self, admin_site):
        self.admin_site = admin_site

    def get_urls(self):
        """Регистрируем URL-ы для импорта и экспорта"""
        urls = [
            path(
                'import/',
                self.admin_site.admin_view(self.import_view),
                name='global_import'
            ),
            path(
                'export/',
                self.admin_site.admin_view(self.export_view),
                name='global_export'
            ),
        ]
        return urls

    def import_view(self, request):
        """📥 Единый импорт справочников"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Финальное подтверждение импорта
                datasets_json = request.session.get('global_import_datasets')
                organization_id = request.session.get('global_import_organization_id')

                if not datasets_json:
                    messages.error(request, 'Данные для импорта не найдены. Загрузите файл заново.')
                    return redirect('admin:global_import')

                # Восстанавливаем datasets из JSON
                from tablib import Dataset
                import json

                datasets = {}
                datasets_dict = json.loads(datasets_json)
                for sheet_name, dataset_json in datasets_dict.items():
                    dataset = Dataset().load(dataset_json)
                    datasets[sheet_name] = dataset

                # Получаем организацию
                organization = None
                if organization_id:
                    try:
                        organization = Organization.objects.get(id=organization_id)
                    except Organization.DoesNotExist:
                        pass

                # Выполняем импорт
                try:
                    result = commit_import(datasets, organization=organization)

                    del request.session['global_import_datasets']
                    if 'global_import_organization_id' in request.session:
                        del request.session['global_import_organization_id']

                    if result.get('success'):
                        org_info = f' для организации "{organization.short_name_ru}"' if organization else ''
                        messages.success(
                            request,
                            format_html(
                                '✅ Импорт успешно завершен{}!<br>'
                                'Создано: <b>{}</b>, обновлено: <b>{}</b>, ошибок: <b>{}</b>',
                                org_info,
                                result['total_created'],
                                result['total_updated'],
                                result['total_errors']
                            )
                        )
                    else:
                        error_msg = result.get('error_message', 'Неизвестная ошибка')
                        messages.error(
                            request,
                            format_html(
                                '❌ Импорт завершен с ошибками:<br>{}',
                                error_msg
                            )
                        )

                except Exception as e:
                    messages.error(request, f'Критическая ошибка при импорте: {str(e)}')

                return redirect('admin:index')

            else:
                # Предпросмотр импорта
                form = GlobalImportForm(request.POST, request.FILES)

                if not form.is_valid():
                    context.update({
                        'title': 'Единый импорт справочников',
                        'subtitle': 'Импорт организационной структуры, сотрудников и оборудования из одного Excel-файла',
                        'form': form,
                    })
                    return render(request, 'admin/directory/global_import/import.html', context)

                import_file = form.cleaned_data['import_file']
                organization = form.cleaned_data['organization']

                try:
                    # Парсим файл
                    datasets = parse_workbook(import_file)

                    # Выполняем dry_run
                    preview_result = dry_run_import(datasets, organization=organization)

                    # Сохраняем данные в сессии для финального импорта
                    import json
                    datasets_dict = {}
                    for sheet_name, dataset in datasets.items():
                        datasets_dict[sheet_name] = dataset.export('json')

                    request.session['global_import_datasets'] = json.dumps(datasets_dict)
                    if organization:
                        request.session['global_import_organization_id'] = organization.id

                    context.update({
                        'title': 'Предпросмотр импорта справочников',
                        'preview_result': preview_result,
                        'datasets': datasets,
                        'organization': organization,
                    })
                    return render(request, 'admin/directory/global_import/import_preview.html', context)

                except Exception as e:
                    messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                    return redirect('admin:global_import')

        # GET запрос - показываем форму
        form = GlobalImportForm()
        context.update({
            'title': 'Единый импорт справочников',
            'subtitle': 'Импорт организационной структуры, сотрудников и оборудования из одного Excel-файла',
            'form': form,
        })
        return render(request, 'admin/directory/global_import/import.html', context)

    def export_view(self, request):
        """📤 Единый экспорт справочников"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            form = GlobalExportForm(request.POST)

            if form.is_valid():
                organization = form.cleaned_data['organization']

                # Применяем права доступа
                if not request.user.is_superuser and hasattr(request.user, 'profile'):
                    allowed_orgs = request.user.profile.organizations.all()
                    if organization and organization not in allowed_orgs:
                        messages.error(request, 'У вас нет доступа к этой организации')
                        return redirect('admin:global_export')

                try:
                    # Экспортируем данные
                    file_content = export_all_to_workbook(organization=organization)

                    # Формируем имя файла
                    if organization:
                        filename = f'export_{organization.short_name_ru}.xlsx'
                    else:
                        # Если организация не выбрана, берём первую из базы
                        first_org = Organization.objects.first()
                        if first_org:
                            filename = f'export_{first_org.short_name_ru}.xlsx'
                        else:
                            filename = 'export_all.xlsx'

                    # Отдаём файл
                    response = HttpResponse(
                        file_content,
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    response['X-Content-Type-Options'] = 'nosniff'
                    response['Content-Length'] = len(file_content)

                    return response

                except Exception as e:
                    messages.error(request, f'Ошибка при экспорте: {str(e)}')
                    return redirect('admin:global_export')

        # GET запрос или невалидная форма - показываем форму выбора
        else:
            form = GlobalExportForm()

        context.update({
            'title': 'Экспорт справочников',
            'subtitle': 'Выгрузка организационной структуры, сотрудников и оборудования в Excel-файл',
            'form': form,
        })
        return render(request, 'admin/directory/global_import/export.html', context)


def register_global_import_export(admin_site):
    """
    Регистрирует единый импорт/экспорт в админке

    Вызывается из directory/admin/__init__.py
    """
    global_admin = GlobalImportExportAdmin(admin_site)

    # Добавляем URL-ы в admin.site
    # Это делается через monkey-patching, т.к. это не ModelAdmin
    original_get_urls = admin_site.get_urls

    def get_urls_with_global_import():
        urls = original_get_urls()
        custom_urls = global_admin.get_urls()
        return custom_urls + urls

    admin_site.get_urls = get_urls_with_global_import
