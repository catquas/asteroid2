const form = document.querySelector("#filters");

// --- Filter auto-submit and series keyboard navigation ---

// Top filter bar: submit changed filters and support series keyboard shortcuts.
if (form) {
  const closingSelect = form.querySelector('select[name="closing"]');

  // Most controls submit the filter form as soon as the user changes them.
  form.querySelectorAll("[data-submit-on-change]").forEach((select) => {
    select.addEventListener("change", () => {
      // Year/month changes can make the current closing invalid, so disable the
      // old closing select before submitting and let the server choose a valid one.
      if ((select.name === "year" || select.name === "month") && closingSelect) {
        closingSelect.disabled = true;
      }

      form.requestSubmit();
    });
  });

  const handleSeriesShortcut = (event) => {
    // Ctrl+Alt+P/N jumps to the previous/next series when that link exists.
    if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }

    const key = event.key.toLowerCase();
    const code = event.code;
    const direction = key === "p" || code === "KeyP" ? "prev" : key === "n" || code === "KeyN" ? "next" : "";
    if (!direction) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const seriesLink = form.querySelector(`a[data-series-nav="${direction}"]`);
    if (!seriesLink) {
      return;
    }

    window.location.assign(seriesLink.href);
  };

  window.addEventListener("keydown", handleSeriesShortcut, true);
}

// --- Lazy sample-detail expansion ---

// Sample detail table: load or clear grouped detail rows.
document.addEventListener("click", async (event) => {
  // Detail rows are requested only when a summarized sample detail row expands.
  const button = event.target.closest("[data-toggle-details]");
  if (!button) {
    return;
  }

  const detailGroup = button.dataset.detailGroup;
  const isExpanded = button.getAttribute("aria-expanded") === "true";
  const summaryRow = button.closest("tr");
  const icon = button.querySelector(".expand-icon");
  const removeDetailRows = () => {
    // Clear any rows previously inserted for this summary group.
    document.querySelectorAll(`[data-detail-row="${detailGroup}"]`).forEach((row) => {
      row.remove();
    });
  };
  const setExpanded = (expanded) => {
    // Keep the visual +/- icon and accessibility state in sync.
    button.setAttribute("aria-expanded", String(expanded));
    if (icon) {
      icon.textContent = expanded ? "-" : "+";
    }
  };
  const syncLoadedDetailSelects = () => {
    // If the summary ATYP value changed before expansion, copy it into the
    // newly loaded detail rows.
    const summarySelect = summaryRow?.querySelector("[data-summary-atyp-select]");
    if (!summarySelect) {
      return;
    }

    document.querySelectorAll(`[data-detail-row="${detailGroup}"] [data-atyp-flag-select]`).forEach((detailSelect) => {
      detailSelect.value = summarySelect.value;
      detailSelect.dataset.currentValue = summarySelect.value;
      updateMismatchState(detailSelect);
    });
  };

  if (isExpanded) {
    removeDetailRows();
    setExpanded(false);
    return;
  }

  if (!detailGroup || !summaryRow || button.disabled) {
    return;
  }

  button.disabled = true;
  removeDetailRows();

  try {
    const response = await fetch("/api/sample-detail-details", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reptstate: button.dataset.rowReptstate || "",
        ui: button.dataset.rowUi || "",
        flag: button.dataset.rowFlag || "",
        is_knr: button.dataset.rowIsKnr === "true",
        detail_group: detailGroup,
      }),
    });

    if (!response.ok) {
      throw new Error(`Sample detail rows failed: ${response.status}`);
    }

    const html = await response.text();
    summaryRow.insertAdjacentHTML("afterend", html);
    syncLoadedDetailSelects();
    setExpanded(true);
  } catch (error) {
    console.error(error);
    setExpanded(false);
  } finally {
    button.disabled = false;
  }
});

const estCalcData = document.querySelector("#estCalcData");
const estCalcState = estCalcData ? JSON.parse(estCalcData.textContent) : null;

const updateMismatchState = (target) => {
  // Yellow highlight means the selected ATYP value no longer matches the
  // original value from the CSV.
  // alert(target.value)
  // alert(target.dataset.origflag)
  target.classList.toggle("is-atyp-mismatch", target.value !== (target.dataset.origflag || ""));
};

// --- ATYP recalculation ---

// Sample detail table: recalculate Estimate Comparison when ATYP changes.
document.addEventListener("change", (event) => {
  // ATYP dropdown changes are handled without a full page reload.
  const select = event.target.closest("[data-atyp-flag-select]");
  if (!select || !estCalcState) {
    return;
  }
  // alert(select.value)

  const previousValue = select.dataset.currentValue;
  if (select.value === previousValue) {
    return;
  }
  const rollbackValue = previousValue ?? select.value;
  const numberFormatter = new Intl.NumberFormat("en-US");
  // Sample detail row values are stored as data attributes, so parse them at
  // the edge before updating the in-browser estimate state.
  const parseRowNumber = (value) => Number.parseInt(value || "0", 10) || 0;
  const percentFormatter = (numerator, denominator) => `${(numerator / denominator * 100).toFixed(1)}%`;
  const formatRecalcValue = (value, percent) => {
    if (value === undefined || value === null) {
      return "";
    }
    const formattedValue = numberFormatter.format(value);
    return percent ? `${formattedValue} [${percent}]` : formattedValue;
  };

  select.disabled = true;
  const ensureNewRecalcRow = () => {
    // The server returns recalculated values, but the browser creates the
    // visible N-Recalc row on demand the first time it is needed.
    const table = document.querySelector("[data-estimate-comparison-table]");
    const loTolRow = table?.querySelector('[data-estimate-row="lo-tol"]');
    if (!table || !loTolRow) {
      return null;
    }

    const existingRow = table.querySelector('[data-estimate-row="n-recalc"]');
    if (existingRow) {
      return existingRow;
    }

    const headerCells = [...table.querySelectorAll("thead th")];
    const row = document.createElement("tr");
    row.className = "is-new-recalc";
    row.dataset.estimateRow = "n-recalc";

    headerCells.forEach((headerCell, index) => {
      if (index === 0) {
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = "N-Recalc";
        row.append(heading);
        return;
      }

      const column = headerCell.textContent.trim().toLowerCase();
      const cell = document.createElement("td");
      if (["est", "otm", "oty"].includes(column)) {
        cell.dataset.nRecalcCell = column;
      }
      row.append(cell);
    });

    loTolRow.after(row);
    return row;
  };
  const applyFlagContribution = (flag, direction) => {
    // Remove the previous flag's row contribution, then add the new flag's
    // contribution. "X" rows intentionally do not affect the totals.
    const rowPm = parseRowNumber(select.dataset.rowPm);
    const rowCm = parseRowNumber(select.dataset.rowCm);
    const rowWpm = parseRowNumber(select.dataset.rowWpm);
    const rowWcm = parseRowNumber(select.dataset.rowWcm);

    if (flag === "A") {
      estCalcState.apm += direction * rowPm;
      estCalcState.acm += direction * rowCm;
    } else if (flag === "T") {
      estCalcState.twpm += direction * rowWpm;
      estCalcState.twcm += direction * rowWcm;
    }
  };
  const recalculateEstimate = () => {
    // Reproduce the estimate formula locally so ATYP edits update the visible
    // Estimate Comparison table without a server round trip.
    const link = estCalcState.twpm === 0 ? 1 : estCalcState.twcm / estCalcState.twpm;
    const newcm = Math.round((estCalcState.pm - estCalcState.apm) * link) + estCalcState.acm + estCalcState.bdf;
    const pm = estCalcState.pm || 1;
    const py = estCalcState.py || 1;
    const otm = newcm - pm;
    const oty = newcm - py;

    // alert(link + ' newcm: ' + newcm + ' pm ' + pm + ' ' + estCalcState.apm)
    // alert(JSON.stringify(estCalcState))

    return {
      n_recalc_cm: newcm,
      n_recalc_otm: otm,
      n_recalc_oty: oty,
      n_recalc_otm_percent: percentFormatter(otm, pm),
      n_recalc_oty_percent: percentFormatter(oty, py),
    };
  };
  const syncDetailSelects = () => {
    // When a summarized row changes, mirror that value into its hidden
    // detail rows so expanding the group does not show stale values.
    const detailGroup = select.dataset.detailGroup;
    if (!select.matches("[data-summary-atyp-select]") || !detailGroup) {
      return;
    }

    document.querySelectorAll(`[data-detail-row="${detailGroup}"] [data-atyp-flag-select]`).forEach((detailSelect) => {
      detailSelect.value = select.value;
      detailSelect.dataset.currentValue = select.value;
      updateMismatchState(detailSelect);
    });
  };

  try {
    applyFlagContribution(previousValue, -1);
    applyFlagContribution(select.value, 1);
    const data = recalculateEstimate();
    ensureNewRecalcRow();
    // Fill only the N-Recalc cells the local calculator knows how to compute.
    [
      ["est", formatRecalcValue(data.n_recalc_cm)],
      ["otm", formatRecalcValue(data.n_recalc_otm, data.n_recalc_otm_percent)],
      ["oty", formatRecalcValue(data.n_recalc_oty, data.n_recalc_oty_percent)],
    ].forEach(([column, value]) => {
      const cell = document.querySelector(`[data-n-recalc-cell="${column}"]`);
      if (cell && value !== undefined) {
        cell.textContent = value;
      }
    });

    select.dataset.currentValue = select.value;
    updateMismatchState(select);
    syncDetailSelects();
    select.blur();
  } catch (error) {
    // If local calculation fails, restore the last known good select value.
    applyFlagContribution(select.value, -1);
    applyFlagContribution(previousValue, 1);
    select.value = rollbackValue;
    console.error(error);
  } finally {
    select.disabled = false;
  }
});

const lineGraphCanvas = document.querySelector("#lineGraph");
const lineGraphData = document.querySelector("#lineGraphData");
const lineGraphLegend = document.querySelector("#lineGraphLegend");

// --- Main chart rendering ---

// Graph section: render Chart.js and build its clickable legend.
if (lineGraphCanvas && lineGraphData && window.Chart) {
  // The server embeds chart JSON in a script tag; Chart.js uses it to draw the
  // time series without another network request.
  const chartData = JSON.parse(lineGraphData.textContent);

  const chart = new Chart(lineGraphCanvas, {
    type: "line",
    data: {
      labels: chartData.labels,
      datasets: chartData.datasets.map((dataset) => ({
        ...dataset,
        backgroundColor: dataset.borderColor,
        borderWidth: dataset.borderDash ? 2 : 4,
        pointBackgroundColor: dataset.borderColor,
        pointBorderColor: "#ffffff",
        pointBorderWidth: dataset.borderDash ? 0 : 2,
        pointRadius: dataset.borderDash ? 0 : 4,
        pointHoverRadius: dataset.borderDash ? 0 : 6,
        spanGaps: false,
        tension: 0.2,
      })),
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      interaction: {
        intersect: false,
        mode: "index",
      },
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
          ticks: {
            color: "#637083",
            font: {
              weight: "700",
            },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 20,
          },
        },
        y: {
          grid: {
            color: "#e5eaf1",
          },
          ticks: {
            color: "#637083",
            font: {
              weight: "700",
            },
          },
        },
      },
    },
  });

  if (lineGraphLegend) {
    // Custom legend buttons let one click toggle a logical group, such as both
    // tolerance-band lines together.
    const legendItems = [
      { label: "Benchmark", datasetIndexes: [0] },
      { label: "Estimates", datasetIndexes: [1] },
      { label: "Tolerance", datasetIndexes: [2, 3] },
    ];

    legendItems.forEach((item) => {
      const dataset = chart.data.datasets[item.datasetIndexes[0]];
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chart-legend-button";
      button.setAttribute("aria-pressed", "true");

      const swatch = document.createElement("i");
      swatch.className = `legend-swatch${dataset.borderDash ? " is-dotted" : ""}`;
      swatch.style.setProperty("--swatch-color", dataset.borderColor);

      const label = document.createElement("span");
      label.textContent = item.label;

      button.append(swatch, label);
      button.addEventListener("click", () => {
        const isVisible = item.datasetIndexes.some((index) => chart.isDatasetVisible(index));
        item.datasetIndexes.forEach((index) => {
          chart.setDatasetVisibility(index, !isVisible);
        });
        chart.update();

        button.setAttribute("aria-pressed", String(!isVisible));
        button.classList.toggle("is-hidden", isVisible);
      });

      lineGraphLegend.append(button);
    });
  }
}

const sampleHistoryGraphCanvas = document.querySelector("#sampleHistoryGraph");
const sampleHistoryGraphData = document.querySelector("#sampleHistoryGraphData");

// --- Sample-history chart rendering ---

// Sample History page: each filtered CSV row is one prior-month-to-current-month segment.
if (sampleHistoryGraphCanvas && sampleHistoryGraphData && window.Chart) {
  const chartData = JSON.parse(sampleHistoryGraphData.textContent);

  new Chart(sampleHistoryGraphCanvas, {
    type: "line",
    data: {
      labels: chartData.labels,
      datasets: chartData.datasets.map((dataset, index) => {
        const color = chartData.colors[index % chartData.colors.length];
        return {
          ...dataset,
          borderColor: color,
          backgroundColor: color,
          borderWidth: 3,
          pointBackgroundColor: color,
          pointBorderColor: "#ffffff",
          pointBorderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          spanGaps: false,
          tension: 0,
        };
      }),
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      interaction: {
        intersect: false,
        mode: "index",
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          reverse: true,
          labels: {
            boxWidth: 16,
            color: "#30415d",
            font: {
              weight: "700",
            },
          },
        },
      },
      scales: {
        x: {
          offset: true,
          grid: {
            display: false,
          },
          ticks: {
            color: "#637083",
            font: {
              weight: "700",
            },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
          },
        },
        y: {
          grace: "10%",
          grid: {
            color: "#e5eaf1",
          },
          ticks: {
            color: "#637083",
            font: {
              weight: "700",
            },
          },
        },
      },
    },
  });
}
window.addEventListener('keydown', function(event) {
    if (event.key === 'PageDown' || event.code === 'PageDown') {
        
        const sampleDetailEl = document.getElementById('sample-detail-section');
        // Target scroll position threshold (<= 5 covers minor trackpad bouncing)
        if (window.scrollY <= 5 && sampleDetailEl) {
            event.preventDefault(); 
            
            if (sampleDetailEl) {
                // Get the element's distance from the top of the viewport
                const elementTop = sampleDetailEl.getBoundingClientRect().top;
                
                // Combine it with current scroll, then subtract your offset (e.g., 100px)
                const offset = 100; 
                const targetPosition = elementTop + window.scrollY - offset;
                
                // Scroll to the calculated position
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'auto' // 'auto' = instant jump, 'smooth' = slightly slower
                });
            }
        }
    }
});

document.addEventListener("click", (event) => {
  // ATYP dropdown changes are handled without a full page reload.
  if (event.target.id == 'show-hide-otm') {
    document.querySelectorAll('span.default-val:has(~ span)').forEach(el => el.classList.toggle('hiddenit'));
    document.querySelectorAll('span.otm-val').forEach(el => el.classList.toggle('hiddenit'));
  }
});


// ******************************************************************************************************************* 
// // SECTION TO SHOW EASILY WHAT I JUST CLICKED ON WITH VIMIUM-C
// *******************************************************************************************************************


const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const activeSleepElements = new WeakSet();
const originalStyles = new WeakMap();

// CRITICAL FIX: Use "capture: true" to intercept the click before ANY other script sees it
document.addEventListener("click", async (event) => {
  const target = event.target.closest("a, button, input[type='submit'], input[type='button']");
  if (!target) return;

  // If the element has already slept, let it proceed to other scripts natively
  if (activeSleepElements.has(target)) {
    activeSleepElements.delete(target);
    return; // Do NOT call preventDefault or stopPropagation on the second pass
  }

  // 1. Prevent the browser default action
  event.preventDefault();

  // 2. Prevent custom JS listeners (like your lazy-expand script) from firing on this first pass
  event.stopImmediatePropagation();

  // Flag the element as sleeping
  activeSleepElements.add(target);

  // Cache original styles
  originalStyles.set(target, {
    backgroundColor: target.style.backgroundColor,
    color: target.style.color
  });

  // Apply visual feedback styles
  target.style.backgroundColor = "yellow";
  target.style.color = "red";

  // Pause execution for 2 seconds
  await sleep(900);

  // Restore the original styles
  const cached = originalStyles.get(target);
  if (cached) {
    target.style.backgroundColor = cached.backgroundColor;
    target.style.color = cached.color;
    originalStyles.delete(target);
  }

  // Re-trigger the click event. It will pass cleanly through both scripts now.
  target.click();
}, { capture: true }); // Capturing ensures this runs before the lazy expansion script

// Global form submission handler remains unchanged
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (activeSleepElements.has(form)) {
    activeSleepElements.delete(form);
    return;
  }
  event.preventDefault();
  activeSleepElements.add(form);
  originalStyles.set(form, { backgroundColor: form.style.backgroundColor });
  form.style.backgroundColor = "yellow";
  await sleep(900);
  const cached = originalStyles.get(form);
  if (cached) {
    form.style.backgroundColor = cached.backgroundColor;
    originalStyles.delete(form);
  }
  form.submit();
});

/*
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Keeps track of elements currently undergoing the 2-second sleep delay
const activeSleepElements = new WeakSet();
// Map to securely cache the original styles for each element
const originalStyles = new WeakMap();

document.addEventListener("click", async (event) => {
  // Find the closest actionable element (link, button, or submit input)
  const target = event.target.closest("a, button, input[type='submit'], input[type='button']");
  if (!target) return;

  // If the element has already slept, allow the default behavior to execute natively
  if (activeSleepElements.has(target)) {
    activeSleepElements.delete(target);
    return;
  }

  // Intercept the initial click and flag the element
  event.preventDefault();
  activeSleepElements.add(target);

  // Cache original styles before altering them
  originalStyles.set(target, {
    backgroundColor: target.style.backgroundColor,
    color: target.style.color
  });

  // Apply visual feedback styles securely
  target.style.backgroundColor = "yellow";
  target.style.color = "red";

  // Pause execution for 2 seconds
  await sleep(2000);

  // Restore the original styles from the cache
  const cached = originalStyles.get(target);
  if (cached) {
    target.style.backgroundColor = cached.backgroundColor;
    target.style.color = cached.color;
    originalStyles.delete(target); // Clean up the Map
  }

  // Re-trigger the click event. The flag above ensures it skips prevention this time.
  target.click();
});

// Global form submission handler to catch standard form inputs
document.addEventListener("submit", async (event) => {
  const form = event.target;

  if (activeSleepElements.has(form)) {
    activeSleepElements.delete(form);
    return;
  }

  event.preventDefault();
  activeSleepElements.add(form);

  originalStyles.set(form, {
    backgroundColor: form.style.backgroundColor
  });

  form.style.backgroundColor = "yellow";

  await sleep(2000);

  const cached = originalStyles.get(form);
  if (cached) {
    form.style.backgroundColor = cached.backgroundColor;
    originalStyles.delete(form);
  }

  form.submit();
});
*/