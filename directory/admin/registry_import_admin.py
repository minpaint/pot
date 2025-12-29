"""
📊 Админка для импорта реестра сотрудников

Позволяет импортировать сотрудников из иерархического Excel-файла
"""
from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import HttpResponse
from django.contrib import messages
from django.utils.html import format_html
import json

from directory.models import Organization
from directory.forms.registry_import_forms import RegistryImportForm
from directory.services.registry_import import (
    parse_registry_file,
    import_registry_data,
    dry_run_import
)


class RegistryImportAdmin:
    """
    📥 Псевдо-админка для импорта реестра сотрудников

    Это не ModelAdmin, а простой класс с методами для регистрации в admin.site
    """

    def __init__(self, admin_site):
        self.admin_site = admin_site

    def get_urls(self):
        """Регистрируем URL-ы для импорта"""
        urls = [
            path(
                'registry-import/',
                self.admin_site.admin_view(self.import_view),
                name='registry_import'
            ),
        ]
        return urls

    def import_view(self, request):
        """📥 Импорт реестра сотрудников"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Финальное подтверждение импорта
                parse_result_json = request.session.get('registry_import_parse_result')
                organization_id = request.session.get('registry_import_organization_id')
                update_existing = request.session.get('registry_import_update_existing', False)

                if not parse_result_json or not organization_id:
                    messages.error(request, 'Данные для импорта не найдены. Загрузите файл заново.')
                    return redirect('admin:registry_import')

                try:
                    organization = Organization.objects.get(id=organization_id)
                except Organization.DoesNotExist:
                    messages.error(request, 'Организация не найдена')
                    return redirect('admin:registry_import')

                # Восстанавливаем parse_result из JSON
                from directory.services.registry_import import RegistryParseResult
                parse_result = RegistryParseResult()

                data = json.loads(parse_result_json)
                parse_result.organization = data['organization']
                parse_result.header_row = data['header_row']
                parse_result.rows_data = data['rows_data']
                parse_result.errors = data.get('errors', [])
                parse_result.total_rows = data['total_rows']
                parse_result.employees_count = data['employees_count']
                parse_result.subdivisions_count = data['subdivisions_count']
                parse_result.departments_count = data['departments_count']
                parse_result.positions_count = data['positions_count']

                # Выполняем импорт
                try:
                    result = import_registry_data(
                        parse_result,
                        organization,
                        update_existing=update_existing
                    )

                    # Очищаем сессию
                    del request.session['registry_import_parse_result']
                    del request.session['registry_import_organization_id']
                    if 'registry_import_update_existing' in request.session:
                        del request.session['registry_import_update_existing']

                    if result.success:
                        messages.success(
                            request,
                            format_html(
                                '✅ Импорт реестра успешно завершён!<br>'
                                'Создано сотрудников: <b>{}</b><br>'
                                'Обновлено сотрудников: <b>{}</b><br>'
                                'Создано подразделений: <b>{}</b><br>'
                                'Создано отделов: <b>{}</b><br>'
                                'Создано должностей: <b>{}</b>',
                                result.employees_created,
                                result.employees_updated,
                                result.subdivisions_created,
                                result.departments_created,
                                result.positions_created
                            )
                        )
                    else:
                        error_details = '<br>'.join([
                            f'Строка {e["row"]}: {e.get("fio", "")}: {e["error"]}'
                            for e in result.errors[:10]
                        ])
                        messages.error(
                            request,
                            format_html(
                                '❌ Импорт завершён с ошибками:<br>{}',
                                error_details
                            )
                        )

                except Exception as e:
                    messages.error(request, f'Критическая ошибка при импорте: {str(e)}')

                return redirect('admin:index')

            else:
                # Предпросмотр импорта
                form = RegistryImportForm(request.POST, request.FILES)

                if not form.is_valid():
                    context.update({
                        'title': 'Импорт реестра сотрудников',
                        'subtitle': 'Загрузите Excel-файл с иерархическим реестром сотрудников',
                        'form': form,
                    })
                    return render(request, 'admin/directory/registry_import/import.html', context)

                import_file = form.cleaned_data['import_file']
                organization = form.cleaned_data['organization']
                update_existing = form.cleaned_data['update_existing']

                try:
                    # Парсим файл
                    parse_result = parse_registry_file(import_file, organization)

                    # Определяем организацию для импорта
                    if organization:
                        final_organization = organization
                    else:
                        # Пытаемся найти организацию по названию из файла
                        try:
                            final_organization = Organization.objects.get(
                                short_name_ru=parse_result.organization
                            )
                        except Organization.DoesNotExist:
                            messages.error(
                                request,
                                f'Организация "{parse_result.organization}" не найдена в базе. '
                                f'Создайте её или выберите другую организацию вручную.'
                            )
                            return redirect('admin:registry_import')

                    # Выполняем dry_run
                    preview = dry_run_import(parse_result, final_organization)

                    # Сохраняем parse_result в сессии для финального импорта
                    parse_result_dict = {
                        'organization': parse_result.organization,
                        'header_row': parse_result.header_row,
                        'rows_data': parse_result.rows_data,
                        'errors': parse_result.errors,
                        'total_rows': parse_result.total_rows,
                        'employees_count': parse_result.employees_count,
                        'subdivisions_count': parse_result.subdivisions_count,
                        'departments_count': parse_result.departments_count,
                        'positions_count': parse_result.positions_count,
                    }

                    request.session['registry_import_parse_result'] = json.dumps(
                        parse_result_dict,
                        default=str  # Для сериализации дат
                    )
                    request.session['registry_import_organization_id'] = final_organization.id
                    request.session['registry_import_update_existing'] = update_existing

                    context.update({
                        'title': 'Предпросмотр импорта реестра',
                        'preview': preview,
                        'organization': final_organization,
                        'update_existing': update_existing,
                    })
                    return render(request, 'admin/directory/registry_import/import_preview.html', context)

                except Exception as e:
                    messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                    return redirect('admin:registry_import')

        # GET запрос - показываем форму
        form = RegistryImportForm()
        context.update({
            'title': 'Импорт реестра сотрудников',
            'subtitle': 'Загрузите Excel-файл с иерархическим реестром сотрудников',
            'form': form,
        })
        return render(request, 'admin/directory/registry_import/import.html', context)


def register_registry_import(admin_site):
    """
    Регистрирует импорт реестра в админке

    Вызывается из directory/admin/__init__.py
    """
    registry_admin = RegistryImportAdmin(admin_site)

    # Добавляем URL-ы в admin.site через monkey-patching
    original_get_urls = admin_site.get_urls

    def get_urls_with_registry_import():
        urls = original_get_urls()
        custom_urls = registry_admin.get_urls()
        return custom_urls + urls

    admin_site.get_urls = get_urls_with_registry_import
