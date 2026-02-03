/**
 * Динамический пересчёт дат обучения при изменении start_date или program.
 */
(function() {
    'use strict';

    // Ждём загрузку DOM
    document.addEventListener('DOMContentLoaded', function() {
        const startDateInput = document.getElementById('id_start_date');
        const programSelect = document.getElementById('id_program');
        const trainingSelect = document.getElementById('id_training');
        const employeeSelect = document.getElementById('id_employee');

        if (!startDateInput) {
            return; // Не на странице редактирования
        }

        /**
         * Находит элемент для отображения readonly значения.
         * Django может использовать разные структуры:
         * - <div class="readonly">...</div>
         * - <p>...</p> внутри .field-xxx
         * - просто текст в <td>
         */
        function findReadonlyElement(fieldName) {
            const fieldDiv = document.querySelector('.field-' + fieldName);
            if (!fieldDiv) return null;

            // Пробуем разные селекторы
            let el = fieldDiv.querySelector('.readonly');
            if (el) return el;

            el = fieldDiv.querySelector('p');
            if (el) return el;

            el = fieldDiv.querySelector('div.flex-container');
            if (el) return el;

            // Для Django 4.x+ может быть просто div внутри td
            const td = fieldDiv.querySelector('td');
            if (td) {
                // Ищем первый текстовый узел или div
                const div = td.querySelector('div');
                if (div) return div;
                return td;
            }

            return fieldDiv;
        }

        // Readonly поля для дат
        const endDateField = findReadonlyElement('end_date');
        const examDateField = findReadonlyElement('exam_date');
        const practicalDateField = findReadonlyElement('practical_date');
        const protocolDateField = findReadonlyElement('protocol_date');

        function updateDates() {
            const startDate = startDateInput.value;
            if (!startDate) {
                return;
            }

            const programId = programSelect ? programSelect.value : '';
            const trainingId = trainingSelect ? trainingSelect.value : '';
            const employeeId = employeeSelect ? employeeSelect.value : '';

            // Формируем URL для AJAX запроса
            const endpoint = trainingSelect
                ? '/admin/production_training/trainingassignment/calculate-dates/'
                : '/admin/production_training/productiontraining/calculate-dates/';
            const url = new URL(window.location.origin + endpoint);
            url.searchParams.set('start_date', startDate);
            if (trainingId) {
                url.searchParams.set('training_id', trainingId);
            } else if (programId) {
                url.searchParams.set('program_id', programId);
            }
            if (employeeId) {
                url.searchParams.set('employee_id', employeeId);
            }

            // Показываем индикатор загрузки
            if (endDateField) endDateField.textContent = '...';
            if (examDateField) examDateField.textContent = '...';
            if (practicalDateField) practicalDateField.textContent = '...';
            if (protocolDateField) protocolDateField.textContent = '...';

            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        console.error('Error:', data.error);
                        return;
                    }
                    // Обновляем readonly поля
                    if (endDateField && data.end_date) {
                        endDateField.textContent = data.end_date;
                    }
                    if (examDateField && data.exam_date) {
                        examDateField.textContent = data.exam_date;
                    }
                    if (practicalDateField && data.practical_date) {
                        practicalDateField.textContent = data.practical_date;
                    }
                    if (protocolDateField && data.protocol_date) {
                        protocolDateField.textContent = data.protocol_date;
                    }
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                });
        }

        // Слушаем изменения даты начала
        startDateInput.addEventListener('change', updateDates);

        // Слушаем изменения программы
        if (programSelect) {
            programSelect.addEventListener('change', updateDates);
        }

        // Слушаем изменения курса обучения
        if (trainingSelect) {
            trainingSelect.addEventListener('change', updateDates);
        }

        // Слушаем изменения сотрудника (может влиять на график работы)
        if (employeeSelect) {
            employeeSelect.addEventListener('change', updateDates);
        }
    });
})();
