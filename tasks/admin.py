# -*- coding: utf-8 -*-
from django.contrib import admin
from django.utils.html import format_html

from .models import TaskList, TaskItem


class TaskItemInline(admin.TabularInline):
    model = TaskItem
    extra = 1
    fields = ('text', 'priority', 'due_date', 'is_done', 'done_at', 'order')
    readonly_fields = ('done_at',)


@admin.register(TaskList)
class TaskListAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'color_preview',
                    'progress', 'is_archived', 'created_by', 'created_at')
    list_filter = ('organization', 'is_archived')
    search_fields = ('title', 'organization__short_name_ru')
    readonly_fields = ('created_at', 'created_by')
    inlines = [TaskItemInline]
    list_per_page = 30

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Цвет')
    def color_preview(self, obj):
        return format_html(
            '<span style="display:inline-block;width:20px;height:20px;'
            'border-radius:4px;background:{};border:1px solid #ddd;"></span>',
            obj.color,
        )

    @admin.display(description='Прогресс')
    def progress(self, obj):
        total = obj.total_count
        done = obj.done_count
        if total == 0:
            return '—'
        pct = int(done / total * 100)
        color = '#28a745' if pct == 100 else ('#ffc107' if pct > 0 else '#dc3545')
        return format_html(
            '<span style="font-weight:600;color:{}">{}/{} ({}%)</span>',
            color, done, total, pct,
        )


@admin.register(TaskItem)
class TaskItemAdmin(admin.ModelAdmin):
    list_display = ('text', 'task_list', 'priority', 'due_date', 'is_done', 'done_at')
    list_filter = ('is_done', 'priority', 'task_list__organization')
    search_fields = ('text', 'task_list__title')
    list_per_page = 50
