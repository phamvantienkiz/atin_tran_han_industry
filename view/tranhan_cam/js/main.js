import { api } from './api.js';
import { CameraCard } from './camera-card.js';
import { DatasetPage } from './dataset-page.js';
import { drawCardOverlay } from './overlay.js';
import { parseZoneJson } from './zone-editor.js';

const gridEl = document.getElementById('camera-grid');
const pageLiveEl = document.getElementById('page-live');
const pageDatasetEl = document.getElementById('page-dataset');
const liveControlsEl = document.getElementById('live-controls');
const nvrStatusEl = document.getElementById('nvr-status');
const nvrHostLabel = document.getElementById('nvr-host-label');
const recGlobalPill = document.getElementById('rec-global-pill');
const recGlobalText = document.getElementById('rec-global-text');
const toastEl = document.getElementById('toast');

const briefModal = document.getElementById('brief-modal');
const focusModal = document.getElementById('focus-modal');
const focusTitle = document.getElementById('focus-modal-title');
const focusSub = document.getElementById('focus-modal-sub');
const focusImg = document.getElementById('focus-img');
const focusDownload = document.getElementById('focus-download');
const btnFocusRecord = document.getElementById('btn-focus-record');
const btnFocusRecordLabel = document.getElementById('btn-focus-record-label');
const recordMenu = document.getElementById('record-menu');

const camModal = document.getElementById('cam-modal');
const camForm = document.getElementById('cam-form');
const camModalTitle = document.getElementById('cam-modal-title');
const camIdInput = document.getElementById('cam-id');
const camChannelInput = document.getElementById('cam-channel');
const camNameInput = document.getElementById('cam-name');
const camNoteInput = document.getElementById('cam-note');
const camModeInput = document.getElementById('cam-mode');
const camSubtypeInput = document.getElementById('cam-subtype');
const camExtraTools = document.getElementById('cam-extra-tools');
const camZoneJson = document.getElementById('cam-zone-json');
const btnDeleteCam = document.getElementById('btn-delete-cam');
const btnImportZone = document.getElementById('btn-import-zone');

let cards = {};
let layoutCount = Number(localStorage.getItem('tranhan_grid_layout') || 4);
let currentPage = 'live';
let toastTimer = null;
let focusCam = null;
let focusSubtype = 0;
let focusRetries = 0;
let focusStreamTimer = null;
let activeJobs = [];
let hadActiveJobs = false;

const datasetPage = new DatasetPage(
  document.getElementById('videos-grid'),
  document.getElementById('frames-grid'),
  showToast,
);

function formatSec(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

function switchPage(page) {
  currentPage = page === 'dataset' ? 'dataset' : 'live';
  document.querySelectorAll('[data-page]').forEach((btn) => {
    btn.setAttribute('aria-selected', String(btn.dataset.page === currentPage));
  });
  pageLiveEl.classList.toggle('hidden', currentPage !== 'live');
  liveControlsEl.classList.toggle('hidden', currentPage !== 'live');
  pageDatasetEl.classList.toggle('hidden', currentPage !== 'dataset');
  if (currentPage === 'dataset') {
    datasetPage.refresh();
  } else {
    requestAnimationFrame(() => Object.values(cards).forEach((c) => drawCardOverlay(c)));
  }
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.add('hidden'), 3000);
}

function setLayout(n) {
  layoutCount = n;
  localStorage.setItem('tranhan_grid_layout', String(n));
  gridEl.dataset.layout = String(n);
  document.querySelectorAll('.topbar [data-layout]').forEach((btn) => {
    btn.setAttribute('aria-selected', String(Number(btn.dataset.layout) === n));
  });
  renderEmptySlots();
  requestAnimationFrame(() => Object.values(cards).forEach((c) => drawCardOverlay(c)));
}

function renderEmptySlots() {
  gridEl.querySelectorAll('.empty-slot').forEach((el) => el.remove());
  const camCount = Object.keys(cards).length;
  for (let i = camCount; i < layoutCount; i++) {
    const slot = document.createElement('div');
    slot.className = 'empty-slot';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-subtle';
    btn.textContent = 'Thêm camera';
    btn.addEventListener('click', () => openCamModal(null));
    slot.appendChild(btn);
    gridEl.appendChild(slot);
  }
}

function openFocusModal(cam) {
  focusCam = cam;
  focusRetries = 0;
  focusTitle.textContent = cam.name;
  focusSub.textContent = cam.note ? `Kênh ${cam.channel} · ${cam.note}` : `Kênh ${cam.channel}`;
  focusDownload.href = `/api/cameras/${cam.id}/snapshot.jpg`;
  focusDownload.download = `${cam.id}-snapshot.jpg`;
  recordMenu.classList.add('hidden');
  btnFocusRecord.setAttribute('aria-expanded', 'false');

  // Pause grid stream for this camera so NVR main-stream opens cleanly
  cards[cam.id]?.stopStream();

  focusModal.classList.remove('hidden');
  syncRecordUi();
  setFocusSubtype(0, 150);
}

function setFocusSubtype(subtype, delayMs = 0) {
  if (!focusCam) return;
  focusSubtype = subtype;
  focusRetries = 0;
  clearTimeout(focusStreamTimer);
  document.querySelectorAll('[data-focus-sub]').forEach((btn) => {
    btn.setAttribute('aria-selected', String(Number(btn.dataset.focusSub) === subtype));
  });
  focusImg.removeAttribute('src');
  const camId = focusCam.id;
  focusStreamTimer = setTimeout(() => {
    if (!focusCam || focusCam.id !== camId) return;
    focusImg.src = `/api/cameras/${camId}/mjpeg?subtype=${subtype}&t=${Date.now()}`;
  }, delayMs);
}

focusImg.addEventListener('load', () => {
  focusRetries = 0;
});

focusImg.addEventListener('error', () => {
  if (!focusCam || focusModal.classList.contains('hidden')) return;
  if (focusRetries >= 2) return;
  focusRetries += 1;
  const camId = focusCam.id;
  const sub = focusSubtype;
  clearTimeout(focusStreamTimer);
  focusStreamTimer = setTimeout(() => {
    if (!focusCam || focusCam.id !== camId) return;
    focusImg.src = `/api/cameras/${camId}/mjpeg?subtype=${sub}&retry=${focusRetries}&t=${Date.now()}`;
  }, 450);
});

function syncRecordUi() {
  if (activeJobs.length > 0) {
    const first = activeJobs[0];
    recGlobalPill.classList.remove('hidden');
    recGlobalText.textContent = `Đang ghi CH ${first.channel} · còn ${formatSec(first.remaining_sec)}`;
  } else {
    recGlobalPill.classList.add('hidden');
  }

  if (!focusCam) return;
  const job = activeJobs.find((j) => j.cam_id === focusCam.id);
  if (job) {
    btnFocusRecord.classList.remove('btn-primary');
    btnFocusRecord.classList.add('btn-recording');
    btnFocusRecordLabel.textContent = `Dừng · ${formatSec(job.remaining_sec)}`;
    recordMenu.classList.add('hidden');
    btnFocusRecord.setAttribute('aria-expanded', 'false');
  } else {
    btnFocusRecord.classList.add('btn-primary');
    btnFocusRecord.classList.remove('btn-recording');
    btnFocusRecordLabel.textContent = 'Record';
  }
}

async function pollActiveRecords() {
  try {
    activeJobs = await api.activeRecords();
    if (hadActiveJobs && activeJobs.length === 0) {
      showToast('Đã hoàn tất ghi hình video');
      if (currentPage === 'dataset') datasetPage.refresh();
    }
    hadActiveJobs = activeJobs.length > 0;
    syncRecordUi();
  } catch (_) {}
}

function closeFocusModal() {
  const closedCamId = focusCam?.id;
  clearTimeout(focusStreamTimer);
  focusModal.classList.add('hidden');
  recordMenu.classList.add('hidden');
  btnFocusRecord.setAttribute('aria-expanded', 'false');
  focusImg.removeAttribute('src');
  focusCam = null;
  if (closedCamId) {
    cards[closedCamId]?.startStream();
  }
}

function openCamModal(card) {
  if (card) {
    camModalTitle.textContent = `Cài đặt · ${card.cam.name}`;
    camIdInput.value = card.cam.id;
    camChannelInput.value = card.cam.channel;
    camNameInput.value = card.cam.name;
    camNoteInput.value = card.cam.note || '';
    camModeInput.value = card.cam.mode || 'mjpeg';
    camSubtypeInput.value = String(card.cam.subtype ?? 1);
    camZoneJson.value = JSON.stringify(card.cam.zone || []);
    camExtraTools.classList.remove('hidden');
    btnDeleteCam.classList.remove('hidden');
  } else {
    camModalTitle.textContent = 'Thêm camera';
    camIdInput.value = '';
    camChannelInput.value = '';
    camNameInput.value = '';
    camNoteInput.value = '';
    camModeInput.value = 'mjpeg';
    camSubtypeInput.value = '1';
    camExtraTools.classList.add('hidden');
    btnDeleteCam.classList.add('hidden');
  }
  camModal.classList.remove('hidden');
}

async function reloadCameras() {
  Object.values(cards).forEach((c) => c.destroy());
  const cams = await api.cameras();
  cams.sort((a, b) => a.channel - b.channel);
  gridEl.innerHTML = '';
  cards = {};

  for (const cam of cams) {
    const card = new CameraCard(cam, {
      onEditCam: (c) => openCamModal(c),
      onFocusCam: (c) => openFocusModal(c),
      onNotify: showToast,
    });
    cards[cam.id] = card;
    gridEl.appendChild(card.el);
  }
  renderEmptySlots();

  if (cams.length > 0) {
    const firstProbe = await api.probeCamera(cams[0].id).catch(() => ({ online: false }));
    nvrStatusEl.classList.toggle('online', Boolean(firstProbe.online));
    nvrStatusEl.classList.toggle('offline', !firstProbe.online);
  }
}

// Event listeners
document.querySelectorAll('[data-page]').forEach((btn) => {
  btn.addEventListener('click', () => switchPage(btn.dataset.page));
});

btnFocusRecord.addEventListener('click', async (e) => {
  e.stopPropagation();
  if (!focusCam) return;
  const active = activeJobs.find((j) => j.cam_id === focusCam.id);
  if (active) {
    btnFocusRecord.disabled = true;
    try {
      await api.stopRecord(focusCam.id);
      showToast('Đã dừng ghi hình và lưu video MP4');
      await pollActiveRecords();
    } catch (err) {
      showToast(err.message);
    } finally {
      btnFocusRecord.disabled = false;
    }
    return;
  }
  const willOpen = recordMenu.classList.contains('hidden');
  recordMenu.classList.toggle('hidden', !willOpen);
  btnFocusRecord.setAttribute('aria-expanded', String(willOpen));
});

document.querySelectorAll('[data-rec-min]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    if (!focusCam) return;
    const minutes = Number(btn.dataset.recMin);
    recordMenu.classList.add('hidden');
    btnFocusRecord.setAttribute('aria-expanded', 'false');
    btnFocusRecord.disabled = true;
    try {
      await api.startRecord(focusCam.id, minutes, focusSubtype);
      showToast(`Bắt đầu ghi ${focusCam.name} (${minutes} phút)`);
      await pollActiveRecords();
    } catch (err) {
      showToast(err.message);
    } finally {
      btnFocusRecord.disabled = false;
    }
  });
});

document.addEventListener('click', (e) => {
  if (!recordMenu.classList.contains('hidden') && !e.target.closest('.record-menu-wrap')) {
    recordMenu.classList.add('hidden');
    btnFocusRecord.setAttribute('aria-expanded', 'false');
  }
});

document.getElementById('btn-reload-dataset').addEventListener('click', () => {
  datasetPage.refresh();
});

document.querySelectorAll('.topbar [data-layout]').forEach((btn) => {
  btn.addEventListener('click', () => setLayout(Number(btn.dataset.layout)));
});

document.querySelectorAll('[data-focus-sub]').forEach((btn) => {
  btn.addEventListener('click', () => setFocusSubtype(Number(btn.dataset.focusSub)));
});

document.getElementById('btn-refresh-all').addEventListener('click', () => {
  Object.values(cards).forEach((c) => {
    c.startStream();
    c.refreshProbe();
  });
  showToast('Đang kết nối lại toàn bộ camera');
});

document.getElementById('btn-brief').addEventListener('click', () => {
  briefModal.classList.remove('hidden');
});

document.getElementById('btn-add-cam').addEventListener('click', () => openCamModal(null));

document.querySelectorAll('[data-close]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const id = btn.dataset.close;
    if (id === 'focus-modal') closeFocusModal();
    else document.getElementById(id).classList.add('hidden');
  });
});

document.querySelectorAll('.modal').forEach((modal) => {
  modal.addEventListener('click', (e) => {
    if (e.target !== modal) return;
    if (modal.id === 'focus-modal') closeFocusModal();
    else modal.classList.add('hidden');
  });
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (!focusModal.classList.contains('hidden')) closeFocusModal();
  briefModal.classList.add('hidden');
  camModal.classList.add('hidden');
});

camForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = camIdInput.value;
  const payload = {
    channel: Number(camChannelInput.value),
    name: camNameInput.value.trim(),
    note: camNoteInput.value.trim(),
    mode: camModeInput.value,
    subtype: Number(camSubtypeInput.value),
  };

  const submitBtn = camForm.querySelector('button[type="submit"]');
  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Đang lưu...';
    }
    if (id) {
      await api.updateCamera(id, payload);
      showToast(`Đã cập nhật ${payload.name}`);
    } else {
      await api.addCamera(payload);
      showToast(`Đã thêm ${payload.name}`);
    }
    camModal.classList.add('hidden');
    await reloadCameras();
  } catch (err) {
    showToast(err.message);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Lưu thay đổi';
    }
  }
});

btnDeleteCam.addEventListener('click', async () => {
  const id = camIdInput.value;
  if (!id) return;
  try {
    await api.deleteCamera(id);
    camModal.classList.add('hidden');
    showToast('Đã xóa camera');
    await reloadCameras();
  } catch (err) {
    showToast(err.message);
  }
});

btnImportZone.addEventListener('click', async () => {
  const id = camIdInput.value;
  if (!id) return;
  try {
    const pts = parseZoneJson(camZoneJson.value.trim());
    if (pts.length < 3) throw new Error('Zone cần tối thiểu 3 điểm');
    await api.saveZone(id, pts);
    showToast('Đã import vùng giám sát');
    camModal.classList.add('hidden');
    await reloadCameras();
  } catch (err) {
    showToast(`Lỗi Zone JSON: ${err.message}`);
  }
});

window.addEventListener('resize', () => {
  Object.values(cards).forEach((c) => drawCardOverlay(c));
});

async function init() {
  try {
    const cfg = await api.config();
    if (cfg.nvr_host) nvrHostLabel.textContent = cfg.nvr_host;
  } catch (_) {}
  setLayout(layoutCount);
  await reloadCameras();
  await pollActiveRecords();
  setInterval(pollActiveRecords, 1000);
}

init();
