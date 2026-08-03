/**
 * Автоподстановка текущей должности сотрудника при выборе в поле "employee"
 * на странице "Сотрудник на обучении" (TrainingAssignment).
 */
(function($) {
    'use strict';

    $(document).ready(function() {
        var $employeeSelect = $('#id_employee');
        var $positionSelect = $('#id_current_position');

        if (!$employeeSelect.length || !$positionSelect.length) {
            return; // Не на этой странице
        }

        function updateCurrentPosition() {
            var employeeId = $employeeSelect.val();
            if (!employeeId) {
                return;
            }

            $.ajax({
                url: '/admin/production_training/trainingassignment/employee-position/',
                data: { employee_id: employeeId },
                dataType: 'json'
            }).done(function(data) {
                if (data.error || !data.position_id) {
                    return;
                }
                var option = new Option(data.position_text, data.position_id, true, true);
                $positionSelect.append(option).trigger('change');
            });
        }

        $employeeSelect.on('change', updateCurrentPosition);
    });
})(django.jQuery);
