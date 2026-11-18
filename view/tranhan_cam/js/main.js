import { api } from './api.js';
import { CameraCard } from './camera-card.js';
import { drawCardOverlay } from './overlay.js';
import { parseZoneJson } from './zone-editor.js';

const gridEl = document.getElementById('camera-grid');
const nvrStatusEl = document.getElementById('nvr-status');
const nvrHostLabel = document.getElementById('nvr-host-label');
const toastEl = document.getElementById('toast');

const briefModal = document.getElementById('brief-modal');
const focusModal = document.getElementById('focus-modal');
const focusTitle = document.getElementById('focus-modal-title');
const focusSub = document.getElementById('focus-modal-sub');
const focusImg = document.getElementById('focus-img');
const focusDownload = document.getElementById('focus-download');

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
let toastTimer = null;
let focusCam = null;

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
  focusTitle.textContent = cam.name;
  focusSub.textContent = cam.note ? `Kênh ${cam.channel} · ${cam.note}` : `Kênh ${cam.channel}`;
  focusDownload.href = `/api/cameras/${cam.id}/snapshot.jpg`;
  focusDownload.download = `${cam.id}-snapshot.jpg`;
  setFocusSubtype(0);
  focusModal.classList.remove('hidden');
}

function setFocusSubtype(subtype) {
  if (!focusCam) return;
  document.querySelectorAll('[data-focus-sub]').forEach((btn) => {
    btn.setAttribute('aria-selected', String(Number(btn.dataset.focusSub) === subtype));
  });
  focusImg.src = `/api/cameras/${focusCam.id}/mjpeg?subtype=${subtype}&t=${Date.now()}`;
}

function closeFocusModal() {
  focusModal.classList.add('hidden');
  focusImg.removeAttribute('src');
  focusCam = null;
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
}

init();
