(() => {
  const directive = /::preview\{file=["']\/data\/hermes\/generated\/([A-Za-z0-9][A-Za-z0-9._-]*\.html)["']\}/g;
  let scheduled = false;
  let quotaStatus = null;
  let quotaRefreshAt = 0;
  let nativeQuotaRenderer = null;

  function preview(file) {
    const wrapper = document.createElement('span');
    wrapper.className = 'hermes-rich-preview';
    const frame = document.createElement('iframe');
    frame.className = 'hermes-rich-preview-frame';
    frame.title = file.startsWith('weather-') ? 'Wetterübersicht' : 'Routenübersicht';
    frame.loading = 'lazy';
    frame.src = new URL(`assistant-previews/${encodeURIComponent(file)}`, document.baseURI).href;
    wrapper.appendChild(frame);
    return wrapper;
  }

  function replaceTextNode(node) {
    const value = node.nodeValue || '';
    directive.lastIndex = 0;
    if (!directive.test(value)) return;
    directive.lastIndex = 0;
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    for (const match of value.matchAll(directive)) {
      if (match.index > cursor) fragment.append(value.slice(cursor, match.index));
      fragment.append(preview(match[1]));
      cursor = match.index + match[0].length;
    }
    if (cursor < value.length) fragment.append(value.slice(cursor));
    node.replaceWith(fragment);
  }

  function scan() {
    scheduled = false;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest('script,style,textarea,pre,code,iframe,.hermes-rich-preview')) {
          return NodeFilter.FILTER_REJECT;
        }
        return node.nodeValue && node.nodeValue.includes('::preview{file=')
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(replaceTextNode);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(scan);
  }

  function quotaEnabled() {
    const preference = document.getElementById('settingsShowQuotaChip');
    return window._showQuotaChip === true || preference?.checked === true;
  }

  function remainingPercent(windowData) {
    const remainingRaw = windowData?.remaining_percent;
    const remaining = Number(remainingRaw);
    if (remainingRaw !== null && remainingRaw !== '' && Number.isFinite(remaining)) {
      return Math.max(0, Math.min(100, Math.round(remaining)));
    }
    const usedRaw = windowData?.used_percent;
    const used = Number(usedRaw);
    return usedRaw !== null && usedRaw !== '' && Number.isFinite(used)
      ? Math.max(0, Math.min(100, Math.round(100 - used))) : null;
  }

  function quotaKind(windowData) {
    const seconds = Number(windowData?.limit_window_seconds);
    const label = String(windowData?.label || '').toLowerCase();
    if ((seconds >= 14400 && seconds <= 21600) || label.includes('5') || label.includes('session')) return '5h';
    if (seconds >= 432000 || label.includes('week') || label.includes('wöch')) return 'W';
    return null;
  }

  function quotaWindows(status) {
    const direct = status?.account_limits?.windows;
    if (Array.isArray(direct)) return direct;
    const pooled = status?.account_limits?.pool?.best_remaining_by_window;
    return Array.isArray(pooled) ? pooled : [];
  }

  function ensureQuotaStrip() {
    let strip = document.getElementById('hermesQuotaStrip');
    if (strip) return strip;
    const nativeChip = document.getElementById('providerQuotaChip');
    const modelChip = document.getElementById('composerModelChip');
    const anchor = nativeChip || modelChip;
    if (!anchor?.parentNode) return null;
    strip = document.createElement('span');
    strip.id = 'hermesQuotaStrip';
    strip.className = 'hermes-quota-strip';
    strip.setAttribute('aria-live', 'polite');
    anchor.parentNode.insertBefore(strip, anchor.nextSibling);
    return strip;
  }

  function renderQuotaStrip(status) {
    if (arguments.length) quotaStatus = status || null;
    const enabled = quotaEnabled();
    document.body.classList.toggle('hermes-addon-quota-enabled', enabled);
    const strip = ensureQuotaStrip();
    if (!strip) return;
    if (!enabled || !quotaStatus) {
      strip.hidden = true;
      return;
    }

    const values = new Map();
    quotaWindows(quotaStatus).forEach((windowData) => {
      const kind = quotaKind(windowData);
      const remaining = remainingPercent(windowData);
      if (kind && remaining !== null && !values.has(kind)) values.set(kind, remaining);
    });
    const entries = ['5h', 'W'].filter((kind) => values.has(kind));
    if (!entries.length) {
      strip.hidden = true;
      return;
    }

    strip.replaceChildren(...entries.map((kind) => {
      const item = document.createElement('span');
      const value = values.get(kind);
      item.className = `hermes-quota-item hermes-quota-${value > 50 ? 'good' : value > 20 ? 'medium' : 'low'}`;
      item.title = `${kind === '5h' ? '5-Stunden-Limit' : 'Wochenlimit'}: ${value}% frei`;
      item.setAttribute('aria-label', item.title);
      const key = document.createElement('b');
      key.textContent = kind;
      const percent = document.createElement('span');
      percent.textContent = `${value}%`;
      item.append(key, percent);
      return item;
    }));
    strip.title = entries.map((kind) => `${kind}: ${values.get(kind)}% frei`).join(' · ');
    strip.hidden = false;
  }

  function hookQuotaRenderer() {
    if (nativeQuotaRenderer || typeof window.renderProviderQuotaIndicator !== 'function') return;
    nativeQuotaRenderer = window.renderProviderQuotaIndicator;
    window.renderProviderQuotaIndicator = function renderProviderQuotaIndicatorWithCompactStrip(status) {
      const result = nativeQuotaRenderer.apply(this, arguments);
      renderQuotaStrip(status);
      return result;
    };
  }

  function syncQuota() {
    hookQuotaRenderer();
    renderQuotaStrip();
    if (!quotaEnabled() || typeof window.refreshProviderQuotaIndicator !== 'function') return;
    const now = Date.now();
    if (!quotaStatus || now - quotaRefreshAt >= 300000) {
      quotaRefreshAt = now;
      Promise.resolve(window.refreshProviderQuotaIndicator()).catch(() => {});
    }
  }

  const style = document.createElement('style');
  style.textContent = `
    .hermes-rich-preview{display:block;width:100%;margin:12px 0;clear:both}
    .hermes-rich-preview-frame{display:block;width:100%;height:510px;border:1px solid color-mix(in srgb,currentColor 20%,transparent);border-radius:18px;background:transparent;box-shadow:0 12px 34px #0003}
    .hermes-quota-strip{display:inline-flex;align-items:center;gap:5px;height:27px;padding:0 7px;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:9px;background:color-mix(in srgb,currentColor 5%,transparent);font-size:11px;line-height:1;white-space:nowrap;vertical-align:middle;flex:0 0 auto}
    .hermes-quota-strip[hidden]{display:none!important}
    .hermes-quota-item{display:inline-flex;align-items:center;gap:3px}
    .hermes-quota-item+ .hermes-quota-item{padding-left:6px;border-left:1px solid color-mix(in srgb,currentColor 16%,transparent)}
    .hermes-quota-item b{font-size:9px;letter-spacing:.02em;opacity:.7}
    .hermes-quota-item>span{font-weight:700;font-variant-numeric:tabular-nums}
    .hermes-quota-good>span{color:#35d49a}.hermes-quota-medium>span{color:#f5ba45}.hermes-quota-low>span{color:#ff6978}
    .hermes-addon-quota-enabled #providerQuotaChip,.hermes-addon-quota-enabled #composerMobileQuotaAction{display:none!important}
    @media(max-width:600px){.hermes-rich-preview-frame{height:440px;border-radius:14px}.hermes-quota-strip{height:25px;padding:0 6px;gap:4px}.hermes-quota-item+ .hermes-quota-item{padding-left:5px}}
  `;
  document.head.appendChild(style);
  new MutationObserver(schedule).observe(document.body, {childList: true, subtree: true, characterData: true});
  document.addEventListener('change', (event) => {
    if (event.target?.id !== 'settingsShowQuotaChip') return;
    setTimeout(() => {
      quotaStatus = null;
      quotaRefreshAt = 0;
      syncQuota();
    }, 0);
  });
  setInterval(syncQuota, 5000);
  schedule();
  syncQuota();
  setTimeout(syncQuota, 500);
  setTimeout(syncQuota, 1500);
})();
