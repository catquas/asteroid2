// --- Chart.js line graph ---

document.addEventListener("DOMContentLoaded", () => {
  const dataScript = document.querySelector("#line-graph-data");
  const canvas = document.querySelector("#time-series-chart");
  if (!dataScript || !canvas || typeof Chart === "undefined") {
    return;
  }

  const lineGraph = JSON.parse(dataScript.textContent);
  new Chart(canvas, {
    type: "line",
    data: lineGraph,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
      },
    },
  });
});

// --- Lazy parent_report detail expansion ---

// Plus button on a parent_report summary row loads that parent_report's report rows from the API.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-toggle-details]");
  if (!button) {
    return;
  }

  const parentReport = button.dataset.rowParentReport;
  const isExpanded = button.getAttribute("aria-expanded") === "true";
  const summaryRow = button.closest("tr");
  const icon = button.querySelector(".expand-icon");
  const removeDetailRows = () => {
    document.querySelectorAll(`[data-detail-row="${parentReport}"]`).forEach((row) => {
      row.remove();
    });
  };
  const setExpanded = (expanded) => {
    button.setAttribute("aria-expanded", String(expanded));
    if (icon) {
      icon.textContent = expanded ? "-" : "+";
    }
  };

  if (isExpanded) {
    removeDetailRows();
    setExpanded(false);
    return;
  }

  if (!parentReport || !summaryRow || button.disabled) {
    return;
  }

  button.disabled = true;
  removeDetailRows();
  
  try {
    const response = await fetch("/api/parent-report-details", {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: parentReport,
    });

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }

    const html = await response.text();
    summaryRow.insertAdjacentHTML("afterend", html);
    setExpanded(true);
  } catch (error) {
    console.error("Failed to load parent_report details", error);
  } finally {
    button.disabled = false;
  }
});
