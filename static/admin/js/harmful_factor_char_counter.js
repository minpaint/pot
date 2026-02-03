/**
 * Счётчик символов для поля "Полное наименование" вредного фактора
 */
(function() {
    'use strict';

    function initCharCounter() {
        var textarea = document.getElementById('id_full_name');
        if (!textarea) return;

        var maxLength = textarea.getAttribute('maxlength') || 1000;

        // Создаём контейнер для счётчика
        var counterContainer = document.createElement('div');
        counterContainer.style.cssText = 'margin-top: 5px; font-size: 12px; color: #666;';

        var counterSpan = document.createElement('span');
        counterSpan.id = 'full_name_counter';

        counterContainer.appendChild(counterSpan);
        textarea.parentNode.insertBefore(counterContainer, textarea.nextSibling);

        function updateCounter() {
            var currentLength = textarea.value.length;
            var remaining = maxLength - currentLength;

            counterSpan.textContent = currentLength + ' / ' + maxLength + ' символов';

            if (remaining < 50) {
                counterSpan.style.color = '#e74c3c';
                counterSpan.style.fontWeight = 'bold';
            } else if (remaining < 150) {
                counterSpan.style.color = '#f39c12';
                counterSpan.style.fontWeight = 'normal';
            } else {
                counterSpan.style.color = '#27ae60';
                counterSpan.style.fontWeight = 'normal';
            }
        }

        // Обновляем счётчик при вводе
        textarea.addEventListener('input', updateCounter);
        textarea.addEventListener('keyup', updateCounter);
        textarea.addEventListener('paste', function() {
            setTimeout(updateCounter, 10);
        });

        // Инициализация счётчика
        updateCounter();
    }

    // Запуск при загрузке страницы
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCharCounter);
    } else {
        initCharCounter();
    }
})();
