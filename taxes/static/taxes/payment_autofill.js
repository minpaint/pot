// При выборе вида платежа и месяца подставляет сумму = остаток на конец месяца.
(function () {
  function balances() {
    var el = document.getElementById("tax-balances");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function autofill(row) {
    var data = balances();
    if (!data) return;
    var kind = row.querySelector('select[name$="-kind"]');
    var month = row.querySelector('select[name$="-period_month"]');
    var amount = row.querySelector('input[name$="-amount"]');
    if (!kind || !month || !amount || !kind.value || !month.value) return;
    if (amount.value !== "" && amount.dataset.auto !== "1") return;
    var item = data[month.value];
    if (!item) return;
    var value = parseFloat(item[kind.value]);
    if (isNaN(value)) return;
    amount.value = (value > 0 ? value : 0).toFixed(2);
    amount.dataset.auto = "1";
  }

  document.addEventListener("change", function (e) {
    var name = e.target.name || "";
    if (name.indexOf("payments-") !== 0 || name.indexOf("__prefix__") !== -1) return;
    if (/-(kind|period_month)$/.test(name)) autofill(e.target.closest("tr"));
  });

  document.addEventListener("input", function (e) {
    var name = e.target.name || "";
    if (name.indexOf("payments-") === 0 && /-amount$/.test(name)) {
      e.target.dataset.auto = "0";
    }
  });
})();
