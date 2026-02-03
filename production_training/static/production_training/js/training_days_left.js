/**
 * Live countdown for "days left" in the admin list.
 */
(function() {
    'use strict';

    const DAY_MS = 24 * 60 * 60 * 1000;
    const HOUR_MS = 60 * 60 * 1000;
    const MIN_MS = 60 * 1000;

    function formatCountdown(diffMs) {
        const overdue = diffMs < 0;
        const absMs = Math.abs(diffMs);

        const days = Math.floor(absMs / DAY_MS);
        const hours = Math.floor((absMs % DAY_MS) / HOUR_MS);
        const minutes = Math.floor((absMs % HOUR_MS) / MIN_MS);

        if (overdue) {
            if (days > 0) {
                return `Просрочено на ${days} дн ${hours} ч`;
            }
            if (hours > 0) {
                return `Просрочено на ${hours} ч ${minutes} мин`;
            }
            return `Просрочено на ${minutes} мин`;
        }

        if (days > 0) {
            return `${days} дн ${hours} ч`;
        }
        if (hours > 0) {
            return `${hours} ч ${minutes} мин`;
        }
        return `${minutes} мин`;
    }

    function getEndDate(endDateStr) {
        if (!endDateStr) {
            return null;
        }
        // Treat end date as end of day local time.
        const date = new Date(`${endDateStr}T23:59:59`);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function updateCountdowns(nodes) {
        const now = new Date();
        nodes.forEach((node) => {
            const endDateStr = node.getAttribute('data-end-date');
            const endDate = getEndDate(endDateStr);
            if (!endDate) {
                return;
            }
            const diffMs = endDate.getTime() - now.getTime();
            node.textContent = formatCountdown(diffMs);
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        const nodes = Array.from(document.querySelectorAll('.pt-days-left[data-end-date]'));
        if (!nodes.length) {
            return;
        }
        updateCountdowns(nodes);
        setInterval(() => updateCountdowns(nodes), 60000);
    });
})();
