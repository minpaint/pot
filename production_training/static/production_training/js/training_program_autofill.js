/**
 * Автоподстановка программы обучения по выбранным типу обучения и профессии.
 *
 * Если для выбранной комбинации существует ровно одна активная программа —
 * подставляет её в поле "Программа обучения". Если программ несколько или
 * не найдено ни одной — оставляет выбор пользователю.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var trainingTypeEl = document.getElementById('id_training_type');
        var professionEl = document.getElementById('id_profession');
        var programEl = document.getElementById('id_program');

        if (!trainingTypeEl || !professionEl || !programEl) {
            return; // Не на этой странице
        }

        function lookupProgram() {
            var trainingTypeId = trainingTypeEl.value;
            var professionId = professionEl.value;

            if (!trainingTypeId || !professionId) {
                return;
            }

            var params = new URLSearchParams({
                training_type_id: trainingTypeId,
                profession_id: professionId,
            });

            fetch('/production-training/program-lookup/?' + params.toString(), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    if (data.program_id) {
                        programEl.value = data.program_id;
                    }
                })
                .catch(function() {});
        }

        trainingTypeEl.addEventListener('change', lookupProgram);
        professionEl.addEventListener('change', lookupProgram);
    });
})();
