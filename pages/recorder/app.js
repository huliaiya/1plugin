const bridge = window.AstrBotPluginPage;

let bridgeReady = false;
let pluginContext = null;

const DEBUG = new URLSearchParams(window.location.search).has('debug');

const viewDataLoaded = { dashboard: false, search: false, export: false };
const dataCache = { platforms: null, stats: null };

let echartsLoaded = false;
let echartsLoading = false;

let currentViewName = '';

function log(...args) {
  if (DEBUG) console.log('[FoxToolbox]', ...args);
}

function logError(...args) {
  console.error('[FoxToolbox]', ...args);
}

async function apiGet(endpoint, params) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }
  log('apiGet:', endpoint, params);
  const result = await bridge.apiGet(endpoint, params);
  log('apiGet response:', endpoint, result);
  return result;
}

async function apiPost(endpoint, body) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }
  log('apiPost:', endpoint, body);
  const result = await bridge.apiPost(endpoint, body);
  log('apiPost response:', endpoint, result);
  return result;
}

function extractData(response) {
  if (response && typeof response === 'object') {
    if ('success' in response) {
      if (response.success) {
        return response.data;
      } else {
        throw new Error(response.error || '请求失败');
      }
    }
    if ('code' in response && (response.code === 500 || response.code >= 400)) {
      throw new Error(response.message || '请求失败');
    }
  }
  return response;
}

function showInitError(message) {
  const main = document.querySelector('.main-content');
  if (main) {
    const existing = document.getElementById('initError');
    if (existing) existing.remove();
    const div = document.createElement('div');
    div.id = 'initError';
    div.style.cssText = 'padding:2rem;text-align:center;color:#e74c3c;';
    const safeMsg = escapeHtml(message);
    div.innerHTML = `<h3>⚠️ 初始化失败</h3><p>${safeMsg}</p><p style="color:#999;font-size:0.85rem;">请确保 AstrBot 版本支持 Plugin Pages 功能（v4.23+），并刷新页面重试。</p>`;
    main.prepend(div);
  }
}

let _echartsWaiters = [];

function loadEcharts() {
  if (echartsLoaded) return Promise.resolve();
  if (echartsLoading) {
    // 返回一个 Promise，避免创建多个 setInterval 轮询
    return new Promise((resolve, reject) => {
      _echartsWaiters.push({ resolve, reject });
    });
  }
  echartsLoading = true;
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js';
    script.onload = () => {
      echartsLoaded = true;
      echartsLoading = false;
      window.addEventListener('resize', handleChartResize);
      // 解析所有等待中的 Promise
      _echartsWaiters.forEach(w => w.resolve());
      _echartsWaiters = [];
      resolve();
    };
    script.onerror = () => {
      echartsLoading = false;
      const err = new Error('ECharts 加载失败');
      // 拒绝所有等待中的 Promise
      _echartsWaiters.forEach(w => w.reject(err));
      _echartsWaiters = [];
      reject(err);
    };
    document.head.appendChild(script);
  });
}

function showSkeletonSlot(el, type) {
  if (!el) return;
  el.classList.add('skeleton-slot');
  let html = '';
  if (type === 'stat-value') {
    html = '<div class="skeleton skeleton-inline" style="width:60px;height:28px;"></div>';
  } else if (type === 'chart') {
    html = '<div class="skeleton skeleton-chart"></div>';
  } else if (type === 'messages') {
    html = Array.from({ length: 5 }, () => '<div class="skeleton skeleton-card"></div>').join('');
  } else if (type === 'line') {
    html = Array.from({ length: 3 }, () => '<div class="skeleton skeleton-line"></div>').join('');
  }
  el.innerHTML = html;
}

function clearSkeletonSlot(el) {
  if (!el) return;
  el.classList.remove('skeleton-slot');
}

function showSectionError(containerId, message, retryFn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = `<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">${escapeHtml(message)}</span>${retryFn ? '<button class="btn btn-outline btn-sm retry-btn">重试</button>' : ''}</div>`;
  if (retryFn) {
    container.querySelector('.retry-btn')?.addEventListener('click', retryFn);
  }
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function formatShortTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  });
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatFileSize(size) {
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
  if (size < 1024 * 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + ' MB';
  return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function getPlatformIcon(platform) {
  const icons = {
    'telegram': 'TG', 'discord': 'DC',
    'qq_official': 'QQ', 'qq_private': 'QQ', 'wechat': 'WX'
  };
  return escapeHtml(icons[platform] || platform || '');
}

function formatMessageType(type) {
  const labels = { 'group': '群聊', 'private': '私聊', 'channel': '频道', 'forum': '论坛' };
  return escapeHtml(labels[type] || type || '其他');
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, maxLen = 100) {
  if (!str) return '';
  if (str.length <= maxLen) return str;
  return str.substring(0, maxLen) + '...';
}

function parseTimeRangeClient(timeRange) {
  const now = new Date();
  let start, end;
  switch (timeRange) {
    case 'today':
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
      break;
    case 'yesterday': {
      const y = new Date(now);
      y.setDate(now.getDate() - 1);
      start = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 0, 0, 0);
      end = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 23, 59, 59);
      break;
    }
    case 'last7d':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'last30d':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'week':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'month':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    default:
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
  }
  return { start: start.getTime(), end: end.getTime() };
}

const timeRangeLabels = {
  'today': '今日', 'yesterday': '昨日', 'last7d': '最近7天',
  'last30d': '最近30天', 'week': '最近7天', 'month': '最近30天'
};

function formatTimestampStr(ts) {
  const date = new Date(ts);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}:${s}`;
}

// ========== Init & Router ==========

async function init() {
  if (!bridge) {
    logError('window.AstrBotPluginPage is not available');
    showInitError('Bridge SDK 未加载 (window.AstrBotPluginPage 未定义)');
    return;
  }

  try {
    pluginContext = await bridge.ready();
    bridgeReady = true;
    log('Bridge ready, context:', pluginContext);
  } catch (e) {
    logError('bridge.ready() failed:', e);
    showInitError(`Bridge 初始化失败: ${e.message || e}`);
    return;
  }

  try {
    initRouter();
    initDashboard();
    initSearch();
    initExport();
    initImport();
    initModal();
    initNavToggle();
    window.addEventListener('beforeunload', cleanupAllCharts);
    navigateToDefault();
  } catch (e) {
    logError('init failed:', e);
    showInitError(`初始化失败: ${e.message || e}`);
  }
}

function initRouter() {
  window.addEventListener('hashchange', handleHashChange);
}

function handleHashChange() {
  const hash = window.location.hash.slice(1) || 'dashboard';
  switchView(hash);
}

function navigateToDefault() {
  const hash = window.location.hash.slice(1) || 'dashboard';
  switchView(hash);
}

function switchView(viewName) {
  if (currentViewName === viewName) return;
  currentViewName = viewName;

  document.querySelectorAll('.view').forEach(v => {
    v.classList.remove('active', 'fade-in');
  });
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));

  const view = document.getElementById(`view-${viewName}`);
  if (view) {
    view.classList.add('active');
    requestAnimationFrame(() => view.classList.add('fade-in'));
  } else {
    const dashView = document.getElementById('view-dashboard');
    dashView.classList.add('active');
    requestAnimationFrame(() => dashView.classList.add('fade-in'));
    viewName = 'dashboard';
    currentViewName = 'dashboard';
  }

  const navLink = document.querySelector(`.nav-link[data-view="${viewName}"]`);
  if (navLink) navLink.classList.add('active');

  if (viewName === 'dashboard') loadDashboardData();
  else if (viewName === 'search') loadSearchData();
  else if (viewName === 'export') loadExportData();
}

function initNavToggle() {
  document.getElementById('navToggle')?.addEventListener('click', () => {
    document.getElementById('navLinks')?.classList.toggle('show');
  });
}

// ========== Dashboard ==========

let timelineChart = null;
let platformChart = null;
let contentTypeChart = null;
let platformDetailChart = null;
let senderChart = null;
let groupChart = null;
let currentTimeRange = 'last30d';
let dashboardLoading = false;

function initDashboard() {
  initDashboardSkeletons();

  document.querySelectorAll('.time-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTimeRange = btn.dataset.range;
      updateTimeRangeDisplay(currentTimeRange);
      await loadRankingData();
    });
  });
}

function initDashboardSkeletons() {
  document.querySelectorAll('.stat-value').forEach(el => {
    if (el.textContent === '-') {
      el.innerHTML = '<div class="skeleton skeleton-inline" style="width:60px;height:28px;"></div>';
      el.classList.add('loading');
    }
  });
  document.querySelectorAll('.chart-box').forEach(el => {
    el.innerHTML = '<div class="skeleton skeleton-chart"></div>';
    el.classList.add('loading');
  });
}

function clearStatSkeleton(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('loading');
  }
}

function clearChartSkeleton(id) {
  const el = document.getElementById(id);
  const chartMap = { timelineChart, platformChart, contentTypeChart, platformDetailChart, senderChart, groupChart };
  const instance = chartMap[id];
  if (instance) {
    instance.dispose();
    if (id === 'timelineChart') timelineChart = null;
    else if (id === 'platformChart') platformChart = null;
    else if (id === 'contentTypeChart') contentTypeChart = null;
    else if (id === 'platformDetailChart') platformDetailChart = null;
    else if (id === 'senderChart') senderChart = null;
    else if (id === 'groupChart') groupChart = null;
  }
  if (el) {
    el.classList.remove('loading');
    el.innerHTML = '';
  }
}

async function loadDashboardData(force = false) {
  if (dashboardLoading) return;
  if (viewDataLoaded.dashboard && !force) return;
  dashboardLoading = true;

  if (force) initDashboardSkeletons();

  loadEcharts().catch(() => {});

  loadPlatforms(false).catch(() => {});

  try {
    const [statsResult, timelineResult, contentTypesResult, platformsDetailResult] = await Promise.all([
      apiGet('stats').catch(e => { logError('stats failed:', e); return null; }),
      apiGet('stats/timeline', { interval: 'day' }).catch(e => { logError('timeline failed:', e); return null; }),
      apiGet('stats/content-types').catch(e => { logError('content-types failed:', e); return null; }),
      apiGet('stats/platforms').catch(e => { logError('platforms detail failed:', e); return null; }),
    ]);

    if (statsResult) {
      try {
        const stats = extractData(statsResult);
        dataCache.stats = stats;
        updateStatsCards(stats);
        await loadEcharts().catch(() => {});
        clearChartSkeleton('platformChart');
        updatePlatformChart(stats.platform_stats);
      } catch (e) {
        logError('Failed to process stats:', e);
        document.querySelectorAll('.stat-value.loading').forEach(el => {
          el.innerHTML = '<span class="error-text-sm">加载失败</span>';
        });
      }
    } else {
      document.querySelectorAll('.stat-value.loading').forEach(el => {
        el.innerHTML = '<span class="error-text-sm">无数据</span>';
      });
    }

    if (timelineResult) {
      try {
        const timelineData = extractData(timelineResult);
        await loadEcharts().catch(() => {});
        clearChartSkeleton('timelineChart');
        updateTimelineChart(timelineData?.points || []);
      } catch (e) {
        logError('Failed to process timeline:', e);
        clearChartSkeleton('timelineChart');
      }
    } else {
      clearChartSkeleton('timelineChart');
    }

    if (contentTypesResult) {
      try {
        const ctData = extractData(contentTypesResult);
        await loadEcharts().catch(() => {});
        clearChartSkeleton('contentTypeChart');
        updateContentTypeChart(ctData?.types || []);
      } catch (e) {
        logError('Failed to process content types:', e);
        clearChartSkeleton('contentTypeChart');
      }
    } else {
      clearChartSkeleton('contentTypeChart');
    }

    if (platformsDetailResult) {
      try {
        const pdData = extractData(platformsDetailResult);
        await loadEcharts().catch(() => {});
        clearChartSkeleton('platformDetailChart');
        updatePlatformDetailChart(pdData?.platforms || []);
        updatePlatformDetailTable(pdData?.platforms || []);
      } catch (e) {
        logError('Failed to process platform detail:', e);
        clearChartSkeleton('platformDetailChart');
      }
    } else {
      clearChartSkeleton('platformDetailChart');
    }

    updateTimeRangeDisplay(currentTimeRange);
    await loadRankingData();
    viewDataLoaded.dashboard = true;
  } catch (e) {
    logError('Failed to load dashboard data:', e);
  } finally {
    dashboardLoading = false;
  }
}

async function loadRankingData() {
  const [senderResult, groupResult] = await Promise.all([
    apiGet('stats/senders', { limit: 10, time: currentTimeRange }).catch(e => { logError('sender ranking failed:', e); return null; }),
    apiGet('stats/groups', { limit: 10, time: currentTimeRange }).catch(e => { logError('group ranking failed:', e); return null; }),
  ]);

  if (!echartsLoaded) {
    await loadEcharts().catch(() => {});
  }

  if (senderResult) {
    try {
      const senderData = extractData(senderResult);
      clearChartSkeleton('senderChart');
      updateSenderChart(senderData.senders);
    } catch (e) {
      logError('Failed to process sender ranking:', e);
      clearChartSkeleton('senderChart');
    }
  }
  if (groupResult) {
    try {
      const groupData = extractData(groupResult);
      clearChartSkeleton('groupChart');
      updateGroupChart(groupData.groups);
    } catch (e) {
      logError('Failed to process group ranking:', e);
      clearChartSkeleton('groupChart');
    }
  }
}

function updateStatsCards(stats) {
  const el = (id) => document.getElementById(id);
  const setVal = (id, val) => { const e = el(id); if (e) { e.textContent = val; e.classList.remove('loading'); } };
  setVal('totalCount', formatNumber(stats.total_count));
  setVal('groupCount', formatNumber(stats.group_message_count));
  setVal('privateCount', formatNumber(stats.private_message_count));
  setVal('platformCount', stats.platform_count);
}

function updateTimeRangeDisplay(timeRange) {
  const el = document.getElementById('timeRangeInfo');
  if (!el) return;
  const { start, end } = parseTimeRangeClient(timeRange);
  const label = timeRangeLabels[timeRange] || timeRange;
  el.innerHTML = `<span class="time-range-label">${label}</span> <span class="time-range-separator">|</span> <span class="time-range-value">${formatTimestampStr(start)} ~ ${formatTimestampStr(end)}</span>`;
}

function ensureChart(id) {
  const el = document.getElementById(id);
  return el ? echarts.init(el) : null;
}

function handleChartResize() {
  timelineChart?.resize();
  platformChart?.resize();
  contentTypeChart?.resize();
  platformDetailChart?.resize();
  senderChart?.resize();
  groupChart?.resize();
}

function cleanupAllCharts() {
  if (timelineChart) { timelineChart.dispose(); timelineChart = null; }
  if (platformChart) { platformChart.dispose(); platformChart = null; }
  if (contentTypeChart) { contentTypeChart.dispose(); contentTypeChart = null; }
  if (platformDetailChart) { platformDetailChart.dispose(); platformDetailChart = null; }
  if (senderChart) { senderChart.dispose(); senderChart = null; }
  if (groupChart) { groupChart.dispose(); groupChart = null; }
  window.removeEventListener('resize', handleChartResize);
  _echartsWaiters = [];
}

function updateTimelineChart(points) {
  if (!echartsLoaded) return;
  if (!timelineChart) timelineChart = ensureChart('timelineChart');
  if (!timelineChart || !points?.length) return;

  timelineChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['总消息', '群聊', '私聊'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: points.map(p => p.date), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value' },
    series: [
      { name: '总消息', type: 'line', data: points.map(p => p.count), smooth: true, areaStyle: { opacity: 0.3 } },
      { name: '群聊', type: 'line', data: points.map(p => p.group_count), smooth: true },
      { name: '私聊', type: 'line', data: points.map(p => p.private_count), smooth: true }
    ]
  });
}

function updatePlatformChart(platformStats) {
  if (!echartsLoaded) return;
  if (!platformChart) platformChart = ensureChart('platformChart');
  if (!platformChart || !platformStats) return;

  const data = Object.entries(platformStats).map(([name, value]) => ({
    name: getPlatformIcon(name), value
  }));

  platformChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: '5%', top: 'center' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false, position: 'center' },
      emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
      labelLine: { show: false },
      data
    }]
  });
}

function updateSenderChart(senders) {
  if (!echartsLoaded) return;
  if (!senderChart) senderChart = ensureChart('senderChart');
  if (!senderChart || !senders?.length) return;

  senderChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: senders.map(s => truncate(s.sender_name || s.sender_id, 15)).reverse(), axisLabel: { width: 100, overflow: 'truncate' } },
    series: [{ type: 'bar', data: senders.map(s => s.count).reverse(), itemStyle: { color: '#ba68c8', borderRadius: [0, 4, 4, 0] } }]
  });
}

function updateGroupChart(groups) {
  if (!echartsLoaded) return;
  if (!groupChart) groupChart = ensureChart('groupChart');
  if (!groupChart || !groups?.length) return;

  groupChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: groups.map(g => truncate(g.group_id, 20)).reverse(), axisLabel: { width: 100, overflow: 'truncate' } },
    series: [{ type: 'bar', data: groups.map(g => g.count).reverse(), itemStyle: { color: '#4dd0e1', borderRadius: [0, 4, 4, 0] } }]
  });
}

function updateContentTypeChart(types) {
  if (!echartsLoaded) return;
  if (!contentTypeChart) contentTypeChart = ensureChart('contentTypeChart');
  if (!contentTypeChart || !types?.length) return;

  const data = types.map(t => ({ name: t.label, value: t.count }));
  const colors = ['#f06292', '#ba68c8', '#64b5f6', '#4fc3f7', '#4dd0e1', '#81c784', '#aed581', '#ffb74d', '#ff8a65', '#e57373', '#f06292', '#ba68c8', '#64b5f6', '#4dd0e1', '#81c784', '#ffb74d'];

  contentTypeChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: '5%', top: 'center', textStyle: { fontSize: 11 } },
    color: colors,
    series: [{
      type: 'pie', radius: ['35%', '65%'], center: ['35%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
      label: { show: false, position: 'center' },
      emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
      labelLine: { show: false },
      data
    }]
  });
}

function updatePlatformDetailChart(platforms) {
  if (!echartsLoaded) return;
  if (!platformDetailChart) platformDetailChart = ensureChart('platformDetailChart');
  if (!platformDetailChart || !platforms?.length) return;

  const names = platforms.map(p => truncate(p.platform_name || p.platform, 12));
  platformDetailChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['群聊', '私聊', '频道'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [
      { name: '群聊', type: 'bar', stack: 'total', data: platforms.map(p => p.group_count), itemStyle: { color: '#64b5f6' } },
      { name: '私聊', type: 'bar', stack: 'total', data: platforms.map(p => p.private_count), itemStyle: { color: '#f06292' } },
      { name: '频道', type: 'bar', stack: 'total', data: platforms.map(p => p.channel_count), itemStyle: { color: '#81c784' } },
    ]
  });
}

function updatePlatformDetailTable(platforms) {
  const tbody = document.getElementById('platformDetailBody');
  if (!tbody) return;
  if (!platforms?.length) {
    tbody.innerHTML = '<tr><td colspan="13" style="padding:16px;text-align:center;color:#999;">暂无数据</td></tr>';
    return;
  }
  tbody.innerHTML = platforms.map(p => {
    const fmt = n => n > 0 ? formatNumber(n) : '<span style="color:#555;">0</span>';
    return `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
      <td style="padding:8px;">${escapeHtml(p.platform_name || p.platform)}</td>
      <td style="padding:8px;text-align:right;font-weight:600;">${formatNumber(p.total)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.group_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.private_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.channel_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.image_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.video_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.voice_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.document_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.audio_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.archive_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.code_count)}</td>
      <td style="padding:8px;text-align:right;">${fmt(p.other_file_count)}</td>
    </tr>`;
  }).join('');
}

// ========== Search ==========

let searchFilters = { limit: 50, offset: 0, order: 'desc' };
let totalMessages = 0;
let advancedVisible = false;
let searchLoading = false;

function initSearch() {
  const keywordInput = document.getElementById('keywordInput');
  if (keywordInput) {
    let timer;
    keywordInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        searchFilters.keyword = keywordInput.value.trim();
        searchFilters.offset = 0;
        loadMessages();
      }, 300);
    });
  }

  const bindSelect = (id, key) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => {
      searchFilters[key] = el.value;
      searchFilters.offset = 0;
      if (id === 'platformFilter') {
        loadGroups(el.value);
        loadSenders(el.value);
      }
      loadMessages();
    });
  };

  bindSelect('platformFilter', 'platform');
  bindSelect('typeFilter', 'message_type');
  bindSelect('orderFilter', 'order');

  const limitEl = document.getElementById('limitFilter');
  if (limitEl) limitEl.addEventListener('change', () => {
    searchFilters.limit = parseInt(limitEl.value);
    searchFilters.offset = 0;
    loadMessages();
  });

  document.getElementById('toggleAdvancedBtn')?.addEventListener('click', () => {
    advancedVisible = !advancedVisible;
    document.getElementById('advancedFilters').style.display = advancedVisible ? 'flex' : 'none';
    document.getElementById('toggleAdvancedBtn').textContent = advancedVisible ? '收起筛选' : '展开更多筛选';
  });

  document.getElementById('refreshBtn')?.addEventListener('click', () => loadMessages());
  document.getElementById('exportResultsBtn')?.addEventListener('click', () => {
    window.location.hash = '#export';
    exportFilters = { ...searchFilters };
    displayExportFilters();
  });
}

async function loadSearchData(force = false) {
  if (viewDataLoaded.search && !force) return;

  const listEl = document.getElementById('messageList');
  if (listEl && !listEl.querySelector('.message-card')) {
    listEl.innerHTML = Array.from({ length: 5 }, () => '<div class="skeleton skeleton-card"></div>').join('');
  }

  await loadPlatforms(force);
  await loadMessages();
  viewDataLoaded.search = true;
}

async function loadPlatforms(force = false) {
  if (dataCache.platforms && !force) {
    populatePlatformSelects(dataCache.platforms);
    return;
  }
  try {
    const raw = await apiGet('platforms');
    const data = extractData(raw);
    dataCache.platforms = data;
    populatePlatformSelects(data);
  } catch (e) {
    logError('Failed to load platforms:', e);
  }
}

function populatePlatformSelects(data) {
  const selects = ['platformFilter', 'exportPlatform'];
  selects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const currentVal = el.value;
    el.innerHTML = '<option value="">全部平台</option>';
    data.platforms.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = getPlatformIcon(p);
      el.appendChild(opt);
    });
    el.value = currentVal;
  });
}

async function loadGroups(platform) {
  try {
    const raw = await apiGet('groups', { platform, limit: 100 });
    const data = extractData(raw);
    const el = document.getElementById('groupFilter');
    if (!el) return;
    el.innerHTML = '<option value="">全部群组</option>';
    data.groups.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = truncate(g.id, 30);
      el.appendChild(opt);
    });
  } catch (e) {
    logError('Failed to load groups:', e);
  }
}

async function loadSenders(platform) {
  try {
    const raw = await apiGet('senders', { platform, limit: 100 });
    const data = extractData(raw);
    const el = document.getElementById('senderFilter');
    if (!el) return;
    el.innerHTML = '<option value="">全部发送者</option>';
    data.senders.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = truncate(s.name, 30);
      el.appendChild(opt);
    });
  } catch (e) {
    logError('Failed to load senders:', e);
  }
}

async function loadMessages() {
  if (searchLoading) return;
  searchLoading = true;

  const listEl = document.getElementById('messageList');
  if (listEl && !listEl.querySelector('.skeleton') && !listEl.querySelector('.message-card')) {
    listEl.innerHTML = '<div class="section-loading"><span class="inline-spinner"></span>加载消息...</div>';
  }

  try {
    const groupEl = document.getElementById('groupFilter');
    const senderEl = document.getElementById('senderFilter');
    const startEl = document.getElementById('startTimeInput');
    const endEl = document.getElementById('endTimeInput');

    if (groupEl?.value) searchFilters.group_id = groupEl.value;
    else delete searchFilters.group_id;
    if (senderEl?.value) searchFilters.sender_id = senderEl.value;
    else delete searchFilters.sender_id;
    if (startEl?.value) searchFilters.start_time = new Date(startEl.value).getTime();
    else delete searchFilters.start_time;
    if (endEl?.value) searchFilters.end_time = new Date(endEl.value).getTime();
    else delete searchFilters.end_time;

    const raw = await apiGet('messages', searchFilters);
    const data = extractData(raw);
    totalMessages = data.pagination.total;
    renderMessages(data.messages);
    renderPagination(data.pagination);
  } catch (e) {
    logError('Failed to load messages:', e);
    showMessageError(e.message || String(e));
  } finally {
    searchLoading = false;
  }
}

function renderMessages(messages) {
  const container = document.getElementById('messageList');
  if (!container) return;
  if (!messages.length) {
    container.innerHTML = '<p class="text-center text-muted">暂无消息记录</p>';
    return;
  }
  container.innerHTML = messages.map(msg => `
    <div class="message-card" data-id="${msg.id}">
      <div class="message-header">
        <span class="message-time">${formatShortTime(msg.timestamp)}</span>
        <span class="message-platform">${getPlatformIcon(msg.platform)}</span>
        <span class="message-type">${formatMessageType(msg.message_type)}</span>
        <span class="message-sender">${escapeHtml(msg.sender_name || msg.sender_id)}</span>
      </div>
      <div class="message-content">${escapeHtml(truncate(msg.message_str, 200))}</div>
      <div class="message-actions">
        <a data-action="detail" data-id="${msg.id}">查看详情</a>
        <a data-action="context" data-id="${msg.id}">查看上下文</a>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('[data-action="detail"]').forEach(a => {
    a.addEventListener('click', (e) => { e.stopPropagation(); showMessageDetail(parseInt(a.dataset.id)); });
  });
  container.querySelectorAll('[data-action="context"]').forEach(a => {
    a.addEventListener('click', (e) => { e.stopPropagation(); showMessageContext(parseInt(a.dataset.id)); });
  });
  container.querySelectorAll('.message-card').forEach(card => {
    card.addEventListener('click', () => showMessageDetail(parseInt(card.dataset.id)));
  });
}

function showMessageError(error) {
  const container = document.getElementById('messageList');
  if (container) container.innerHTML = `<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">加载失败: ${escapeHtml(error)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`;
  container.querySelector('.retry-btn')?.addEventListener('click', () => loadMessages());
}

function renderPagination(pagination) {
  const container = document.getElementById('pagination');
  if (!container) return;
  const { total, limit, offset } = pagination;
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  if (totalPages <= 1) {
    container.innerHTML = `<span class="pagination-info">共 ${total} 条记录</span>`;
    return;
  }

  container.innerHTML = `
    <button class="pagination-btn ${currentPage <= 1 ? 'disabled' : ''}" id="prevPage" ${currentPage <= 1 ? 'disabled' : ''}>上一页</button>
    <span class="pagination-info">第 ${currentPage}/${totalPages} 页，共 ${total} 条</span>
    <button class="pagination-btn ${currentPage >= totalPages ? 'disabled' : ''}" id="nextPage" ${currentPage >= totalPages ? 'disabled' : ''}>下一页</button>
  `;

  document.getElementById('prevPage')?.addEventListener('click', () => {
    if (currentPage > 1) { searchFilters.offset = (currentPage - 2) * searchFilters.limit; loadMessages(); }
  });
  document.getElementById('nextPage')?.addEventListener('click', () => {
    if (currentPage < totalPages) { searchFilters.offset = currentPage * searchFilters.limit; loadMessages(); }
  });
}

// ========== Modal ==========

function initModal() {
  const modal = document.getElementById('messageModal');
  document.getElementById('modalClose')?.addEventListener('click', hideModal);
  modal?.addEventListener('click', (e) => { if (e.target === modal) hideModal(); });
}

function showModal(content) {
  const body = document.getElementById('modalBody');
  if (body) body.innerHTML = content;
  document.getElementById('messageModal')?.classList.add('show');
}

function hideModal() {
  document.getElementById('messageModal')?.classList.remove('show');
}

async function showMessageDetail(messageId) {
  showModal(`<div class="section-loading"><span class="inline-spinner"></span>加载消息详情...</div>`);
  try {
    const raw = await apiGet('message/detail', { id: messageId });
    const msg = extractData(raw);
    showModal(`
      <div class="detail-section">
        <div class="detail-row"><span class="detail-label">时间:</span><span class="detail-value">${formatTime(msg.timestamp)}</span></div>
        <div class="detail-row"><span class="detail-label">平台:</span><span class="detail-value">${getPlatformIcon(msg.platform)}</span></div>
        <div class="detail-row"><span class="detail-label">发送者:</span><span class="detail-value">${escapeHtml(msg.sender_name || msg.sender_id)}</span></div>
        <div class="detail-row"><span class="detail-label">消息类型:</span><span class="detail-value">${formatMessageType(msg.message_type)}</span></div>
        ${msg.group_id ? `<div class="detail-row"><span class="detail-label">群组:</span><span class="detail-value">${escapeHtml(msg.group_id)}</span></div>` : ''}
        <div class="detail-row"><span class="detail-label">内容:</span><span class="detail-value">${escapeHtml(msg.message_str) || '[非文本消息]'}</span></div>
      </div>
      ${msg.message_chain?.length ? `
      <div class="detail-section mt-2">
        <h4>消息链</h4>
        ${msg.message_chain.map(c => `<div class="chain-item"><span class="chain-type">${escapeHtml(c.type)}</span>${c.text ? escapeHtml(c.text) : ''}${c.url ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">[链接]</a>` : ''}${c.local_path ? `<span class="chain-media">[本地文件: ${escapeHtml(c.local_path)}]</span>` : ''}</div>`).join('')}
      </div>` : ''}
      ${msg.raw_message ? `
      <div class="detail-section mt-2">
        <h4>原始消息</h4>
        <pre class="raw-message">${escapeHtml(typeof msg.raw_message === 'string' ? msg.raw_message : JSON.stringify(msg.raw_message, null, 2))}</pre>
      </div>` : ''}
      <div class="detail-actions mt-2">
        <button class="btn" onclick="showMessageContext(${messageId})">查看上下文</button>
      </div>
    `);
  } catch (e) {
    logError('Failed to load message detail:', e);
    showModal(`<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">加载失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`);
    document.querySelector('#messageModal .retry-btn')?.addEventListener('click', () => showMessageDetail(messageId));
  }
}

async function showMessageContext(messageId) {
  showModal(`<div class="section-loading"><span class="inline-spinner"></span>加载消息上下文...</div>`);
  try {
    const raw = await apiGet('message/context', { id: messageId, before: 5, after: 5 });
    const data = extractData(raw);
    const allMsgs = [...(data.before || []), data.target, ...(data.after || [])].filter(Boolean);
    showModal(`
      <div class="detail-section">
        <h4>消息上下文</h4>
        <div class="context-messages">
          ${allMsgs.map(m => `
            <div class="context-msg ${m.id === messageId ? 'context-target' : ''}">
              <span class="context-time">${formatShortTime(m.timestamp)}</span>
              <span class="context-sender">${escapeHtml(m.sender_name || m.sender_id)}</span>
              <span class="context-content">${escapeHtml(truncate(m.message_str, 100)) || '[非文本]'}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `);
  } catch (e) {
    logError('Failed to load message context:', e);
    showModal(`<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">加载失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`);
    document.querySelector('#messageModal .retry-btn')?.addEventListener('click', () => showMessageContext(messageId));
  }
}

// ========== Export ==========

let exportFilters = {};
let selectedExportFormat = 'json';

function initExport() {
  document.querySelectorAll('.format-option').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.format-option').forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      selectedExportFormat = opt.dataset.format;
    });
  });

  document.getElementById('includeMedia')?.addEventListener('change', (e) => {
    document.getElementById('mediaNote').style.display = e.target.checked ? 'block' : 'none';
  });

  document.getElementById('startExport')?.addEventListener('click', startExport);
}

async function loadExportData(force = false) {
  if (viewDataLoaded.export && !force) return;
  await loadPlatforms(force);
  displayExportFilters();
  viewDataLoaded.export = true;
}

function displayExportFilters() {
  const el = document.getElementById('currentFilters');
  if (!el) return;
  const parts = [];
  if (exportFilters.keyword) parts.push(`关键词: ${escapeHtml(exportFilters.keyword)}`);
  if (exportFilters.platform) parts.push(`平台: ${escapeHtml(exportFilters.platform)}`);
  if (exportFilters.message_type) parts.push(`类型: ${formatMessageType(exportFilters.message_type)}`);
  el.innerHTML = parts.length ? `<div class="filter-tags">${parts.map(p => `<span class="filter-tag">${p}</span>`).join('')}</div>` : '<p class="text-muted">无筛选条件，将导出全部消息</p>';
}

async function startExport() {
  const filters = {
    time: document.getElementById('exportTime')?.value || undefined,
    platform: document.getElementById('exportPlatform')?.value || undefined,
    message_type: document.getElementById('exportType')?.value || undefined,
    start_time: document.getElementById('exportStartTime')?.value ? new Date(document.getElementById('exportStartTime').value).getTime() : undefined,
    end_time: document.getElementById('exportEndTime')?.value ? new Date(document.getElementById('exportEndTime').value).getTime() : undefined,
    keyword: document.getElementById('exportKeyword')?.value?.trim() || undefined,
    ...exportFilters,
  };

  Object.keys(filters).forEach(k => filters[k] === undefined && delete filters[k]);

  const options = {
    include_chain: document.getElementById('includeChain')?.checked ?? true,
    include_raw: document.getElementById('includeRaw')?.checked ?? false,
    include_media: document.getElementById('includeMedia')?.checked ?? false,
  };

  try {
    const raw = await apiPost('export', { format: selectedExportFormat, filters, options });
    const task = extractData(raw);
    document.getElementById('startExport').disabled = true;
    pollExportStatus(task.task_id);
  } catch (e) {
    logError('Export failed:', e);
    alert('导出失败: ' + (e.message || e));
  }
}

async function pollExportStatus(taskId) {
  const progressEl = document.getElementById('exportProgress');
  if (progressEl) {
    progressEl.style.display = 'block';
    progressEl.innerHTML = '<p><span class="inline-spinner"></span>导出中，请稍候...</p>';
  }

  const poll = async () => {
    try {
      const raw = await apiGet('export/status', { task_id: taskId });
      const task = extractData(raw);

      if (task.status === 'completed') {
        const sizeStr = task.file_size ? formatFileSize(task.file_size) : '';
        const sizeInfo = sizeStr ? ` (${sizeStr})` : '';
        if (progressEl) progressEl.innerHTML = `<p>✅ 导出完成！共 ${task.actual_count || 0} 条记录${sizeInfo}</p><button id="downloadLink" class="btn btn-success">下载文件</button>`;
        document.getElementById('downloadLink')?.addEventListener('click', (e) => {
          e.preventDefault();
          downloadExportFile(taskId);
        });
        document.getElementById('startExport').disabled = false;
      } else if (task.status === 'failed') {
        if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">❌</span><span class="error-text">导出失败: ${escapeHtml(task.error)}</span></div>`;
        document.getElementById('startExport').disabled = false;
      } else {
        const progressInfo = task.progress ? ` - ${escapeHtml(task.progress)}` : '';
        if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>导出中...${progressInfo}</p>`;
        setTimeout(poll, 2000);
      }
    } catch (e) {
      logError('Poll export status failed:', e);
      if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">查询状态失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`;
      progressEl.querySelector('.retry-btn')?.addEventListener('click', () => pollExportStatus(taskId));
      document.getElementById('startExport').disabled = false;
    }
  };

  await poll();
}

async function downloadExportFile(taskId) {
  if (!bridge || !bridgeReady) {
    alert('Bridge SDK 未就绪，无法下载');
    return;
  }
  const progressEl = document.getElementById('exportProgress');
  try {
    const statusResult = await apiGet('export/status', { task_id: taskId });
    const taskData = extractData(statusResult);
    const fileSize = taskData.file_size || 0;
    const filename = taskData.filename || '';
    if (fileSize > 50 * 1024 * 1024) {
      if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>正在下载 ${formatFileSize(fileSize)}，请勿关闭页面...</p>`;
      await bridge.download('export/download', { task_id: taskId }, filename);
      if (progressEl) progressEl.innerHTML = `<p>✅ 下载已开始，请查看浏览器下载栏</p>`;
    } else {
      if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>正在准备下载...</p>`;
      const result = await apiGet('export/download_data', { task_id: taskId });
      if (!result || !result.base64) {
        throw new Error('未获取到文件数据');
      }
      const binaryStr = atob(result.base64);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: result.mimetype || 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = result.filename || 'download.bin';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (progressEl) progressEl.innerHTML = `<p>✅ 下载已开始</p>`;
    }
  } catch (e) {
    logError('download failed:', e);
    if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">❌</span><span class="error-text">下载失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`;
    progressEl.querySelector('.retry-btn')?.addEventListener('click', () => downloadExportFile(taskId));
  }
}

// ========== Import ==========

let selectedFile = null;
let importMode = 'merge';

function initImport() {
  const uploadArea = document.getElementById('uploadArea');
  const fileInput = document.getElementById('importFile');

  uploadArea?.addEventListener('click', () => fileInput?.click());
  uploadArea?.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
  uploadArea?.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
  uploadArea?.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
  });
  fileInput?.addEventListener('change', () => {
    if (fileInput.files.length) handleFileSelect(fileInput.files[0]);
  });

  document.querySelectorAll('input[name="importMode"]').forEach(r => {
    r.addEventListener('change', () => { importMode = r.value; });
  });

  document.getElementById('startImport')?.addEventListener('click', startImport);
}

function handleFileSelect(file) {
  selectedFile = file;
  const infoEl = document.getElementById('fileInfo');
  if (infoEl) {
    infoEl.style.display = 'block';
    infoEl.innerHTML = `<p>已选择: <strong>${escapeHtml(file.name)}</strong> (${formatFileSize(file.size)})</p>`;
  }
}

async function startImport() {
  if (!selectedFile) {
    alert('请先选择文件');
    return;
  }

  const CHUNK_THRESHOLD = 50 * 1024 * 1024;
  const progressEl = document.getElementById('importProgress');
  if (progressEl) {
    progressEl.style.display = 'block';
    progressEl.innerHTML = '<p><span class="inline-spinner"></span>导入中，请稍候...</p>';
  }
  document.getElementById('startImport').disabled = true;

  try {
    if (selectedFile.size > CHUNK_THRESHOLD) {
      await chunkedImport(selectedFile, importMode, progressEl);
    } else {
      await simpleImport(selectedFile, importMode, progressEl);
    }
  } catch (e) {
    logError('import failed:', e);
    if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">❌</span><span class="error-text">导入失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function simpleImport(file, mode, progressEl) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }

  const result = await bridge.upload(`import/upload?mode=${encodeURIComponent(mode)}`, file);
  log('simple import result:', result);

  if (progressEl) progressEl.innerHTML = '<p><span class="inline-spinner"></span>文件上传完成，处理中...</p>';

  const data = extractData(result);
  const taskId = data?.task_id;
  if (taskId) {
    pollImportStatus(taskId, progressEl);
  } else {
    if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成</p>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function chunkedImport(file, mode, progressEl) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }

  const initRaw = await apiPost('import/init', {
    filename: file.name,
    file_size: file.size,
    mode: mode,
  });
  const initData = extractData(initRaw);
  const { session_id, total_chunks, chunk_size } = initData;

  if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>分片上传中 (0/${total_chunks})...</p>`;

  for (let i = 0; i < total_chunks; i++) {
    const start = i * chunk_size;
    const end = Math.min(start + chunk_size, file.size);
    const chunk = file.slice(start, end);

    const chunkResult = await bridge.upload(`import/chunk/${session_id}/${i}`, chunk);
    if (chunkResult && typeof chunkResult === 'object' && chunkResult.success === false) {
      throw new Error(chunkResult.error || `分片 ${i + 1} 上传失败`);
    }
    log(`chunk ${i} uploaded`);

    if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>分片上传中 (${i + 1}/${total_chunks})...</p>`;
  }

  const completeRaw = await apiPost('import/complete', { session_id });
  const completeData = extractData(completeRaw);
  const taskId = completeData?.task_id;
  if (taskId) {
    pollImportStatus(taskId, progressEl);
  } else {
    if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成</p>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function pollImportStatus(taskId, progressEl) {
  const poll = async () => {
    try {
      const raw = await apiGet('import/status', { task_id: taskId });
      const task = extractData(raw);

      if (task.status === 'completed') {
        if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成！共导入 ${task.imported || 0} 条，跳过 ${task.skipped || 0} 条</p>`;
        document.getElementById('startImport').disabled = false;
      } else if (task.status === 'failed') {
        if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">❌</span><span class="error-text">导入失败: ${escapeHtml(task.error)}</span></div>`;
        document.getElementById('startImport').disabled = false;
      } else {
        const processed = task.processed || 0;
        const total = task.total_records || '?';
        if (progressEl) progressEl.innerHTML = `<p><span class="inline-spinner"></span>导入中... (${processed}/${total})</p>`;
        setTimeout(poll, 2000);
      }
    } catch (e) {
      logError('Poll import status failed:', e);
      if (progressEl) progressEl.innerHTML = `<div class="section-error"><span class="error-icon">⚠️</span><span class="error-text">查询状态失败: ${escapeHtml(e.message || e)}</span><button class="btn btn-outline btn-sm retry-btn">重试</button></div>`;
      progressEl.querySelector('.retry-btn')?.addEventListener('click', () => pollImportStatus(taskId, progressEl));
      document.getElementById('startImport').disabled = false;
    }
  };

  await poll();
}

init();
