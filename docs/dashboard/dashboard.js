const DEFAULT_DATASET = 'data/sample_runs.json';

function resolveDatasetUrl() {
  const params = new URLSearchParams(window.location.search);
  const dataParam = params.get('data');
  if (!dataParam) {
    return DEFAULT_DATASET;
  }
  try {
    const url = new URL(dataParam, window.location.href);
    return url.href;
  } catch (error) {
    console.warn('Invalid data parameter, falling back to default dataset.', error);
    return DEFAULT_DATASET;
  }
}

async function loadDataset(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`Failed to load dataset (${response.status} ${response.statusText})`);
  }
  return response.json();
}

function formatNumber(value, fractionDigits = 2) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits });
}

function renderOverview(payload) {
  const root = document.getElementById('runs-root');
  const count = document.getElementById('run-count');
  const generated = document.getElementById('generated-at');
  if (root) root.textContent = payload.runs_root || '—';
  if (count) count.textContent = payload.run_count ?? 0;
  if (generated) generated.textContent = payload.generated_at || '—';
}

function renderStackTable(payload) {
  const tableBody = document.querySelector('#stack-table tbody');
  if (!tableBody) {
    return;
  }

  tableBody.innerHTML = '';
  const stacks = Array.isArray(payload.stacks) ? payload.stacks : [];

  if (stacks.length === 0) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.textContent = 'No stack data available.';
    cell.colSpan = 6;
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }

  stacks.forEach((entry) => {
    const row = document.createElement('tr');
    const stackCell = document.createElement('th');
    stackCell.scope = 'row';
    stackCell.textContent = entry.stack ?? '—';
    row.appendChild(stackCell);

    const runCount = document.createElement('td');
    runCount.textContent = entry.run_count ?? 0;
    row.appendChild(runCount);

    const sizeDelta = document.createElement('td');
    sizeDelta.textContent = formatNumber(entry.avg_size_delta_pct);
    row.appendChild(sizeDelta);

    const buildDelta = document.createElement('td');
    buildDelta.textContent = formatNumber(entry.avg_build_delta_seconds);
    row.appendChild(buildDelta);

    const bestRun = document.createElement('td');
    bestRun.textContent = entry.best_run_id || '—';
    row.appendChild(bestRun);

    const bestRule = document.createElement('td');
    bestRule.textContent = entry.best_rule_id || '—';
    row.appendChild(bestRule);

    tableBody.appendChild(row);
  });
}

function summariseOriginal(original) {
  if (!original) {
    return '—';
  }
  const size = formatNumber(original.size_mb);
  const layers = original.layers ?? '—';
  const seconds = formatNumber(original.build_seconds);
  return `${size} MB • ${layers} layers • ${seconds} s`;
}

function summariseBestCandidate(candidate) {
  if (!candidate) {
    return 'No candidates';
  }
  const label = candidate.rule_id;
  const size = formatNumber(candidate.size_mb);
  const delta = formatNumber(candidate.size_delta_pct);
  return `${label} → ${size} MB (${delta}% vs original)`;
}

function createReportLinks(paths) {
  if (!paths) {
    return '—';
  }
  const links = [];
  if (paths.report_markdown) {
    const anchor = document.createElement('a');
    anchor.href = paths.report_markdown;
    anchor.textContent = 'Markdown';
    anchor.target = '_blank';
    anchor.rel = 'noreferrer noopener';
    links.push(anchor);
  }
  if (paths.report_html) {
    const anchor = document.createElement('a');
    anchor.href = paths.report_html;
    anchor.textContent = 'HTML';
    anchor.target = '_blank';
    anchor.rel = 'noreferrer noopener';
    links.push(anchor);
  }
  if (links.length === 0) {
    return '—';
  }
  const fragment = document.createDocumentFragment();
  links.forEach((link, index) => {
    if (index > 0) {
      fragment.append(', ');
    }
    fragment.append(link);
  });
  return fragment;
}

function renderRunCards(payload) {
  const grid = document.getElementById('run-grid');
  const template = document.getElementById('run-card-template');
  if (!grid || !(template instanceof HTMLTemplateElement)) {
    return;
  }

  grid.innerHTML = '';
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  if (runs.length === 0) {
    grid.textContent = 'No runs found in this dataset.';
    return;
  }

  runs.forEach((run) => {
    const instance = template.content.firstElementChild.cloneNode(true);
    instance.querySelector('[data-run-id]').textContent = run.run_id;
    instance.querySelector('[data-stack]').textContent = `${run.stack} (${run.mode})`;
    instance.querySelector('[data-project]').textContent = run.project_name ?? '—';
    instance.querySelector('[data-created]').textContent = run.created_at ?? '—';
    instance.querySelector('[data-original]').textContent = summariseOriginal(run.original);
    instance.querySelector('[data-best]').textContent = summariseBestCandidate(run.best_candidate);

    const assistNode = instance.querySelector('[data-assist]');
    assistNode.textContent = run.assist_summary || '—';

    const reportsNode = instance.querySelector('[data-reports]');
    const reportLinks = createReportLinks(run.paths);
    if (reportLinks instanceof DocumentFragment) {
      reportsNode.innerHTML = '';
      reportsNode.appendChild(reportLinks);
    } else {
      reportsNode.textContent = reportLinks;
    }

    const airgapTag = instance.querySelector('[data-airgap]');
    const llmTag = instance.querySelector('[data-llm]');
    if (airgapTag) {
      airgapTag.classList.toggle('visible', run.environment?.airgap_enabled === true);
    }
    if (llmTag) {
      llmTag.classList.toggle('visible', run.environment?.llm_enabled === true);
    }

    grid.appendChild(instance);
  });
}

async function initialise() {
  const datasetUrl = resolveDatasetUrl();
  const statusBanner = document.createElement('div');
  statusBanner.className = 'status-banner';
  statusBanner.textContent = `Loading dataset: ${datasetUrl}`;
  document.body.prepend(statusBanner);

  try {
    const payload = await loadDataset(datasetUrl);
    statusBanner.textContent = `Loaded dataset: ${datasetUrl}`;
    renderOverview(payload);
    renderStackTable(payload);
    renderRunCards(payload);
  } catch (error) {
    console.error(error);
    statusBanner.textContent = `Failed to load dataset: ${error.message}`;
    statusBanner.classList.add('error');
  }
}

initialise();
