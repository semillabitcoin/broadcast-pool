const API = '';
let currentData = { txs: [], current_height: 0 };
let currentSort = { field: null, asc: true };
let histSort = { field: null, asc: true };
let currentStatus = {};
let lang = localStorage.getItem('bp-lang') || 'es';
let unit = localStorage.getItem('bp-unit') || 'btc';
let activeTab = 'pool';
let currentNpub = '';
let vaultDecrypted = [];
let vaultSort = { field: null, asc: true };

const i18n = {
  es: {
    title: 'Broadcast Pool',
    subtitle: 'Proxy Electrum con broadcast programado de transacciones',
    net: 'Red', height: 'Altura', mtp: 'MTP', retained: 'Retenidas',
    scheduled: 'Programadas', connections: 'Conexiones', upstream: 'Upstream',
    change: 'Cambiar', host: 'Host', port: 'Puerto', connect: 'Conectar',
    cancel: 'Cancelar', reconnecting: 'Reconectando...',
    aaPrefix: 'Auto agenda transacciones pendientes a la altura de bloque', aaGap: 'y con', aaSuffix1: 'bloque entre cada transacci\u00f3n', aaSuffixN: 'bloques entre cada transacci\u00f3n',
    assign: 'Agendar', importTx: 'Importar TX',
    pasteHex: 'Pega el hex de una transaccion firmada',
    wallet: 'Wallet', import_btn: 'Importar', importing: 'Importando...',
    other: 'Otro',
    noTxTitle: 'Sin transacciones',
    noTxDesc: 'Conecta Sparrow o Liana a umbrel.local:50005 y envia una transaccion',
    thTxid: 'TxID', thType: 'Tipo', thWallet: 'Wallet', thAmount: 'Monto',
    thFeeRate: 'Fee rate', thCoinAge: 'Edad moneda', thStatus: 'Estado',
    thTarget: 'Retransmitir en', thActions: 'Acciones', thBlock: 'Bloque',
    confirmed_title: 'Retransmitidas \u00faltimo bloque',
    st_pending: 'pendiente', st_scheduled: 'programada', st_broadcasting: 'retransmitida',
    st_confirmed: 'confirmada', st_failed: 'fallida', st_replaced: 'reemplazada', st_abandoned: 'abandonada',
    st_rotating: ['Retransmitida', 'esperando', 'confirmación'],
    emit: 'Emitir ahora', delete: 'Eliminar', retry: 'Reintentar',
    emitConfirm: 'Emitir esta transaccion ahora?',
    deleteConfirm: 'Eliminar esta transaccion? Los UTXOs quedaran libres.',
    enterBase: 'Introduce un bloque base',
    pasteAlert: 'Pega el hex de la transaccion',
    datePicker: 'Fecha objetivo', calcBlock: 'Calcular bloque', close: 'Cerrar',
    dateFuture: 'La fecha debe ser futura',
    blocks: 'bloques', bl: 'bl',
    tabPool: 'Pool', tabSettings: 'Ajustes', tabVault: 'B\u00f3veda',
    setUpstream: 'Conexi\u00f3n a servidor Electrum', setVault: 'B\u00f3veda cifrada (Nostr)',
    setPrefs: 'Preferencias', setLang: 'Idioma', setUnit: 'Unidad', setPort: 'Puerto',
    setNpubHelp: 'Las transacciones confirmadas se purgan despu\u00e9s de 1 bloque. Puedes almacenarlas cifradas para su posterior an\u00e1lisis dejando un npub.',
    setNpubHelp2: 'Solo t\u00fa podr\u00e1s descifrarlas localmente con Alby, Nos2x u otra extensi\u00f3n de navegador NIP-07.',
    setNpubWarn: 'Nota: valora no usar tu npub principal. Usa un npub burner que no asocie tu nym a la actividad de tx bitcoin.',
    testConn: 'Verificar conexi\u00f3n',
    save: 'Guardar', saved: 'Guardado',
    vaultNoNpub: 'Configura tu npub', vaultNoNpubDesc: 'Ve a Ajustes y pega tu npub para activar la b\u00f3veda cifrada',
    vaultNoExt: 'Extensi\u00f3n NIP-07 requerida', vaultNoExtDesc: 'Instala Alby o nos2x para descifrar la b\u00f3veda',
    vaultDecrypting: 'Descifrando...', vaultDecrypted: 'entradas descifradas',
    footerMade: 'Hecho en la madriguera de <a href="https://semillabitcoin.com" target="_blank">Semilla Bitcoin</a>',
    footerInspired: 'Inspirado en la propuesta Broadcast Pool de Craig Raw.',
    hexCopied: 'hex copiado', txidCopied: 'txid copiado',
    copyHex: 'Copiar tx hex', copyTxid: 'Copiar txid',
    mtpLag: 'MTP lag', mtpPassed: 'MTP ya paso esta fecha',
    mtpWill: 'MTP la alcanzara en',
  },
  en: {
    title: 'Broadcast Pool',
    subtitle: 'Electrum proxy with scheduled transaction broadcast',
    net: 'Network', height: 'Height', mtp: 'MTP', retained: 'Retained',
    scheduled: 'Scheduled', connections: 'Connections', upstream: 'Upstream',
    change: 'Change', host: 'Host', port: 'Port', connect: 'Connect',
    cancel: 'Cancel', reconnecting: 'Reconnecting...',
    aaPrefix: 'Schedule pending transactions at blockheight', aaGap: 'with', aaSuffix1: 'block between each tx', aaSuffixN: 'blocks between each tx',
    assign: 'Assign', importTx: 'Import TX',
    pasteHex: 'Paste the hex of a signed transaction',
    wallet: 'Wallet', import_btn: 'Import', importing: 'Importing...',
    other: 'Other',
    noTxTitle: 'No transactions',
    noTxDesc: 'Connect Sparrow or Liana to umbrel.local:50005 and send a transaction',
    thTxid: 'TxID', thType: 'Type', thWallet: 'Wallet', thAmount: 'Amount',
    thFeeRate: 'Fee rate', thCoinAge: 'Coin age', thStatus: 'Status',
    thTarget: 'Broadcast at', thActions: 'Actions', thBlock: 'Block',
    confirmed_title: 'Broadcast last block',
    st_pending: 'pending', st_scheduled: 'scheduled', st_broadcasting: 'broadcast',
    st_confirmed: 'confirmed', st_failed: 'failed', st_replaced: 'replaced', st_abandoned: 'abandoned',
    st_rotating: ['Broadcasted', 'waiting', 'confirmation'],
    emit: 'Broadcast now', delete: 'Delete', retry: 'Retry',
    emitConfirm: 'Broadcast this transaction now?',
    deleteConfirm: 'Delete this transaction? UTXOs will be freed.',
    enterBase: 'Enter a base block',
    pasteAlert: 'Paste the transaction hex',
    datePicker: 'Target date', calcBlock: 'Calculate block', close: 'Close',
    dateFuture: 'Date must be in the future',
    blocks: 'blocks', bl: 'bl',
    tabPool: 'Pool', tabSettings: 'Settings', tabVault: 'Vault',
    setUpstream: 'Electrum server connection', setVault: 'Encrypted vault (Nostr)',
    setPrefs: 'Preferences', setLang: 'Language', setUnit: 'Unit', setPort: 'Port',
    setNpubHelp: 'Confirmed transactions are purged after 1 block. You can store them encrypted for later analysis by setting an npub.',
    setNpubHelp2: 'Only you will be able to decrypt them locally with Alby, Nos2x or another NIP-07 browser extension.',
    setNpubWarn: 'Note: consider not using your main npub. Use a burner npub that doesn\'t link your nym to Bitcoin tx activity.',
    testConn: 'Test connection',
    save: 'Save', saved: 'Saved',
    vaultNoNpub: 'Set up your npub', vaultNoNpubDesc: 'Go to Settings and paste your npub to enable the encrypted vault',
    vaultNoExt: 'NIP-07 extension required', vaultNoExtDesc: 'Install Alby or nos2x to decrypt the vault',
    vaultDecrypting: 'Decrypting...', vaultDecrypted: 'entries decrypted',
    footerInspired: 'Inspired by Craig Raw\'s Broadcast Pool proposal.',
    footerMade: 'Made in <a href="https://semillabitcoin.com" target="_blank">Semilla Bitcoin</a>\'s rabbit hole',
    hexCopied: 'hex copied', txidCopied: 'txid copied',
    copyHex: 'Copy tx hex', copyTxid: 'Copy txid',
    mtpLag: 'MTP lag', mtpPassed: 'MTP already passed this date',
    mtpWill: 'MTP will reach it in',
  },
};

function t(key) { return i18n[lang][key] || key; }

function toggleLang() {
  lang = lang === 'es' ? 'en' : 'es';
  localStorage.setItem('bp-lang', lang);
  applyLang();
  renderTable(currentData.txs, currentData.current_height);
}

function applyLang() {
  document.getElementById('page-title').textContent = t('title');
  document.getElementById('page-subtitle').textContent = t('subtitle');
  // Header toggles
  const lb = document.getElementById('lang-btn'); if (lb) lb.textContent = lang === 'es' ? 'EN' : 'ES';

  // Tab labels
  document.getElementById('tab-btn-pool').textContent = t('tabPool');
  document.getElementById('tab-btn-settings').textContent = t('tabSettings');
  document.getElementById('tab-btn-vault').textContent = t('tabVault');

  document.getElementById('lbl-net').textContent = t('net');
  document.getElementById('lbl-height').textContent = t('height');
  document.getElementById('lbl-mtp').textContent = t('mtp');
  document.getElementById('lbl-retained').textContent = t('retained');
  document.getElementById('lbl-scheduled').textContent = t('scheduled');
  document.getElementById('lbl-connections').textContent = t('connections');
  document.getElementById('lbl-upstream').textContent = t('upstream');
  document.getElementById('btn-import').textContent = t('importTx');

  // Settings tab
  document.getElementById('set-title-upstream').textContent = t('setUpstream');
  document.getElementById('set-title-vault').textContent = t('setVault');
  document.getElementById('set-title-prefs').textContent = t('setPrefs');
  document.getElementById('set-npub-help').textContent = t('setNpubHelp');
  document.getElementById('set-npub-help2').textContent = t('setNpubHelp2');
  document.getElementById('set-npub-warn').textContent = t('setNpubWarn');
  document.getElementById('btn-test-conn').textContent = t('testConn');
  document.getElementById('set-lbl-port').textContent = t('setPort');
  document.getElementById('set-lbl-lang').textContent = t('setLang');
  document.getElementById('set-lbl-unit').textContent = t('setUnit');
  document.getElementById('btn-save-settings').textContent = t('save');

  // Vault tab
  document.getElementById('vault-no-npub-title').textContent = t('vaultNoNpub');
  document.getElementById('vault-no-npub-desc').textContent = t('vaultNoNpubDesc');
  document.getElementById('vault-no-ext-title').textContent = t('vaultNoExt');
  document.getElementById('vault-no-ext-desc').textContent = t('vaultNoExtDesc');

  document.getElementById('lbl-aa-prefix').textContent = t('aaPrefix');
  document.getElementById('lbl-aa-gap').textContent = t('aaGap');
  updateAaSuffix();
  document.getElementById('btn-assign').textContent = t('assign');

  document.getElementById('import-label-text').textContent = t('pasteHex') + ':';
  document.getElementById('import-wallet-label').textContent = t('wallet') + ':';
  document.getElementById('btn-do-import').textContent = t('import_btn');
  document.getElementById('btn-cancel-import').textContent = t('cancel');

  document.getElementById('empty-title').textContent = t('noTxTitle');
  document.getElementById('empty-desc').textContent = t('noTxDesc');

  document.getElementById('th-txid').textContent = t('thTxid');
  document.getElementById('th-type').textContent = t('thType');
  document.getElementById('th-wallet').textContent = t('thWallet');
  document.getElementById('th-amount').textContent = t('thAmount');
  document.getElementById('th-feerate').textContent = t('thFeeRate');
  document.getElementById('th-coinage').textContent = t('thCoinAge');
  document.getElementById('th-status').textContent = t('thStatus');
  document.getElementById('th-target').textContent = t('thTarget');
  document.getElementById('th-actions').textContent = t('thActions');

  document.getElementById('btn-rescan').title = lang === 'es'
    ? 'Re-escanear dependencias y actualizar fee rates'
    : 'Re-scan dependencies and refresh fee rates';
  document.getElementById('confirmed-heading').innerHTML = `<span id="history-arrow" class="history-arrow">${historyOpen ? '›' : '›'}</span> ${t('confirmed_title')}`;
  document.getElementById('footer-inspired').textContent = t('footerInspired');
  document.getElementById('footer-made').innerHTML = t('footerMade') + ' 🕳️🐇';
  const ub = document.getElementById('unit-btn'); if (ub) ub.textContent = unit === 'btc' ? 'BTC' : 'sats';

  const targetTip = lang === 'es'
    ? 'Bloque en el que se retransmitira la tx a la red Bitcoin'
    : 'Block at which the tx will be broadcast to the Bitcoin network';
  document.getElementById('th-target').title = targetTip;
}

async function fetchJSON(url, opts) {
  const resp = await fetch(API + url, opts);
  return resp.json();
}

async function refresh() {
  if (activeTab !== 'pool') return;

  const active = document.activeElement;
  const hasDatePicker = document.querySelector('[id^="datepicker-"]');
  const isEditing = hasDatePicker || (active && (active.classList.contains('target-input') || active.tagName === 'TEXTAREA'));

  try {
    const [txData, statusData] = await Promise.all([
      fetchJSON('/api/txs'),
      fetchJSON('/api/status'),
    ]);
    currentData = txData;
    currentStatus = statusData;
    currentNpub = statusData.npub || '';
    updateStatus(statusData);
    updateVaultTabVisibility();
    if (!isEditing) {
      renderTable(txData.txs, txData.current_height);
    }
  } catch (e) {
    console.error('Refresh error:', e);
  }
}

function updateStatus(s) {
  document.getElementById('s-height').textContent = s.current_height ? s.current_height.toLocaleString() : '--';
  document.getElementById('s-retained').textContent = s.pending + s.scheduled;
  document.getElementById('s-scheduled').textContent = s.scheduled;
  document.getElementById('s-connections').textContent = s.connections;
  const netEl = document.getElementById('s-network');
  const net = s.network || '--';
  netEl.textContent = net;
  if (net === 'signet') {
    netEl.style.color = 'var(--signet)';
  } else if (net === 'testnet' || net === 'testnet4') {
    netEl.style.color = 'var(--testnet)';
  } else {
    netEl.style.color = 'var(--text)';
  }
  document.getElementById('s-upstream').textContent = s.upstream_host + ':' + s.upstream_port + (s.upstream_ssl ? ' (SSL)' : '');

  if (s.current_mtp) {
    const mtpDate = new Date(s.current_mtp * 1000);
    const lagMin = Math.round((Date.now() - mtpDate.getTime()) / 60000);
    document.getElementById('s-mtp').textContent = mtpDate.toLocaleString();
    const mtpTip = lang === 'es'
      ? `Median Time Past: mediana de los timestamps de los ultimos 11 bloques.\nEs el reloj de Bitcoin para timelocks.\nLag actual: ${lagMin} min respecto al reloj del sistema.\nUnix: ${s.current_mtp}`
      : `Median Time Past: median of last 11 block timestamps.\nBitcoin's clock for timelocks.\nCurrent lag: ${lagMin} min vs system clock.\nUnix: ${s.current_mtp}`;
    document.getElementById('s-mtp').title = mtpTip;
    document.getElementById('lbl-mtp').title = mtpTip;
  } else {
    document.getElementById('s-mtp').textContent = '--';
  }

  const aaBase = document.getElementById('aa-base');
  if (!aaBase.value && s.current_height) {
    aaBase.value = s.current_height + 6;
  }
}

// --- Settings ---

function showSettings() {
  fetchJSON('/api/settings').then(s => {
    document.getElementById('set-host').value = s.upstream_host;
    document.getElementById('set-port').value = s.upstream_port;
    document.getElementById('set-ssl').checked = s.upstream_ssl;
    document.getElementById('settings-panel').style.display = 'block';
    document.getElementById('settings-msg').textContent = '';
  });
}

function hideSettings() {
  document.getElementById('settings-panel').style.display = 'none';
}

async function saveSettings() {
  const host = document.getElementById('set-host').value.trim();
  const port = parseInt(document.getElementById('set-port').value);
  const useSsl = document.getElementById('set-ssl').checked;
  if (!host || !port) { alert('Host y puerto requeridos'); return; }

  const result = await fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upstream_host: host, upstream_port: port, upstream_ssl: useSsl }),
  });

  if (result.ok) {
    document.getElementById('settings-msg').textContent = 'Reconectando...';
    setTimeout(() => { hideSettings(); refresh(); }, 2000);
  } else {
    alert('Error: ' + (result.error || 'Unknown'));
  }
}

// --- Table ---

function renderTable(txs, height) {
  const table = document.getElementById('tx-table');
  const empty = document.getElementById('empty-state');
  const tbody = document.getElementById('tx-body');
  const confirmedSection = document.getElementById('confirmed-section');
  const confirmedBody = document.getElementById('confirmed-body');

  const historyStatuses = new Set(['confirmed', 'replaced', 'abandoned']);
  const activeTxs = txs.filter(tx => !historyStatuses.has(tx.status));
  const confirmedTxs = txs.filter(tx => historyStatuses.has(tx.status));

  // Active table
  if (!activeTxs.length && !confirmedTxs.length) {
    table.style.display = 'none';
    empty.style.display = 'block';
    confirmedSection.style.display = 'none';
    return;
  }

  empty.style.display = 'none';

  if (activeTxs.length) {
    table.style.display = 'table';
    const sorted = orderWithDependencies(applySorting(activeTxs));
    tbody.innerHTML = sorted.map(tx => renderActiveRow(tx, height)).join('');
    sorted.forEach(tx => {
      const okBtn = document.getElementById('ok-' + tx.txid_full);
      if (okBtn) {
        const input = document.getElementById('blk-' + tx.txid_full);
        const original = tx.target_block ? String(tx.target_block) : '';
        okBtn.style.display = (input && input.value !== original) ? 'inline-block' : 'none';
      }
    });
  } else {
    table.style.display = 'none';
  }

  // Confirmed table
  if (confirmedTxs.length) {
    confirmedSection.style.display = 'block';
    applyHistoryState();

    // Populate wallet filter dynamically
    const walletSelect = document.getElementById('hist-filter-wallet');
    const currentWalletFilter = walletSelect.value;
    const wallets = [...new Set(confirmedTxs.map(tx => shortWallet(tx.wallet_label)).filter(w => w !== '--'))];
    const walletOpts = `<option value="" id="hf-all-wallets">${lang==='es'?'Todas las wallets':'All wallets'}</option>` +
      wallets.map(w => `<option value="${w}" ${w===currentWalletFilter?'selected':''}>${w}</option>`).join('');
    walletSelect.innerHTML = walletOpts;

    // Apply filters
    const typeFilter = document.getElementById('hist-filter-type').value;
    const statusFilter = document.getElementById('hist-filter-status').value;
    const walletFilter = walletSelect.value;

    let filtered = confirmedTxs;
    if (typeFilter) filtered = filtered.filter(tx => tx.tx_tags && tx.tx_tags.includes(typeFilter));
    if (walletFilter) filtered = filtered.filter(tx => shortWallet(tx.wallet_label) === walletFilter);
    if (statusFilter) filtered = filtered.filter(tx => tx.status === statusFilter);

    // Totals row
    const totalAmount = filtered.reduce((s, tx) => s + (tx.amount_sats || 0), 0);
    const totalFees = filtered.reduce((s, tx) => s + (tx.fee_sats > 0 ? tx.fee_sats : 0), 0);
    const avgFeeRate = filtered.filter(tx => tx.fee_rate > 0).length > 0
      ? (filtered.reduce((s, tx) => s + (tx.fee_rate > 0 ? tx.fee_rate : 0), 0) / filtered.filter(tx => tx.fee_rate > 0).length).toFixed(1)
      : '--';
    const txCount = filtered.length;

    filtered = applyHistSorting(filtered);

    const totalsRow = `<tr class="totals-row">
      <td>${txCount} txs</td>
      <td></td>
      <td></td>
      <td class="mono cell-amount">${formatBTC(totalAmount)}</td>
      <td>${avgFeeRate !== '--' ? avgFeeRate + ' avg' : '--'}</td>
      <td class="mono cell-amount">${formatBTC(totalFees)}</td>
      <td></td>
      <td></td>
      <td></td>
    </tr>`;

    confirmedBody.innerHTML = totalsRow + filtered.map(tx => {
      const target = tx.target_block;
      const conf = tx.confirmed_block;
      let targetStr, deltaStr;

      const retxTitle = lang === 'es'
        ? 'Bloque en que se retransmitio a la red. La confirmacion ocurre en el siguiente bloque (+1) o posteriores.'
        : 'Block when broadcast to network. Confirmation happens in the next block (+1) or later.';

      if (tx.locktime && tx.locktime.type === 'timestamp' && !target) {
        targetStr = `<span style="font-size:11px" title="MTP">MTP</span>`;
      } else {
        targetStr = target ? `<span title="${retxTitle}">${target.toLocaleString()}</span>` : '--';
      }

      if (target && conf) {
        const delta = conf - target;
        if (delta <= 1) {
          // 0 or +1 is expected (broadcast at block N, confirmed at N or N+1)
          deltaStr = `<span style="color:var(--green)">${delta === 0 ? '0' : '+' + delta}</span>`;
        } else if (delta <= 3) {
          deltaStr = `<span style="color:var(--orange)">+${delta}</span>`;
        } else {
          deltaStr = `<span style="color:var(--red)">+${delta}</span>`;
        }
      } else {
        deltaStr = '--';
      }

      const errorTitle = (tx.error_message && (tx.status === 'replaced' || tx.status === 'abandoned'))
        ? tx.error_message : '';
      const errorNote = '';

      return `<tr>
        <td class="mono txid-copy" title="${t('copyTxid')}" onclick="copyTx('${tx.txid_full}','confirmed')">${tx.txid}</td>
        <td class="cell-tags">${formatTags(tx.tx_tags)}</td>
        <td title="${escapeHTML(tx.wallet_label)}">${escapeHTML(shortWallet(tx.wallet_label))}</td>
        <td class="mono cell-amount">${formatBTC(tx.amount_sats)}</td>
        <td>${tx.fee_rate > 0 ? tx.fee_rate + ' sat/vB' : '--'}</td>
        <td class="mono cell-amount">${tx.fee_sats > 0 ? formatBTC(tx.fee_sats) : '--'}</td>
        <td><span title="${errorTitle}">${badgeHTML(tx.status)}</span></td>
        <td class="mono">${conf ? conf.toLocaleString() : '--'}</td>
        <td class="mono">${deltaStr}</td>
      </tr>`;
    }).join('');
  } else {
    confirmedSection.style.display = 'none';
  }

  return;
}

function renderActiveRow(tx, height) {
  const editable = tx.status === 'pending' || tx.status === 'scheduled';
  const val = tx.target_block || '';
  const coinAge = coinAgeHTML(tx, height);
  const blocksRem = tx.blocks_remaining != null ? tx.blocks_remaining.toLocaleString() : '';

  const isMtpScheduled = tx.status === 'scheduled' && !tx.target_block
    && tx.locktime && tx.locktime.type === 'timestamp';
  const isBlockScheduled = tx.status === 'scheduled' && tx.target_block;
  const isPending = tx.status === 'pending';

  let targetCell;
  if (isMtpScheduled) {
    // MTP scheduled: show date + pencil to edit
    targetCell = `<div class="target-cell">
      <span style="font-size:12px;color:var(--green)">MTP: ${tx.locktime.date}</span>
      <span class="target-edit" onclick="unschedule('${tx.txid_full}')" title="${lang==='es'?'Modificar':'Edit'}">&#9998;</span>
    </div>`;
  } else if (isBlockScheduled) {
    // Block scheduled: show block + remaining + pencil to edit
    const remTag = blocksRem ? `<span class="target-rem">(${blocksRem} ${t('bl')})</span>` : '';
    targetCell = `<div class="target-cell">
      <span class="mono">${Number(val).toLocaleString()}</span>
      ${remTag}
      <span class="target-edit" onclick="unschedule('${tx.txid_full}')" title="${lang==='es'?'Modificar':'Edit'}">&#9998;</span>
    </div>`;
  } else if (isPending || editable) {
    // Pending: input + OK + calendar
    targetCell = `<div class="target-cell">
      <input class="target-input" type="text" inputmode="numeric" pattern="[0-9]*"
        id="blk-${tx.txid_full}" value="${val}" placeholder="--"
        oninput="onTargetInput('${tx.txid_full}')"
        onkeydown="if(event.key==='Enter')schedule('${tx.txid_full}')">
      <button class="target-ok" id="ok-${tx.txid_full}" onclick="schedule('${tx.txid_full}')">OK</button>
      <button class="target-cal" onclick="showDatePicker('${tx.txid_full}')" title="Fecha">&#128197;</button>
    </div>`;
  } else {
    const nowTag = `<span class="target-rem">(${lang==='es'?'ahora':'now'})</span>`;
    targetCell = val
      ? `<div class="target-cell"><span class="mono">${Number(val).toLocaleString()}</span> ${nowTag}</div>`
      : '--';
  }

  const isBroadcast = tx.status === 'broadcasting' || tx.status === 'confirmed';

  return `<tr>
    <td class="mono txid-copy" title="${isBroadcast ? t('copyTxid') : t('copyHex')}" onclick="copyTx('${tx.txid_full}','${tx.status}')">${tx._depth > 0 ? depPrefix(tx) + tx.txid_full.slice(0, 16 - tx._depth * 2) + '...' : tx.txid}</td>
    <td class="cell-tags">${formatTags(tx.tx_tags)}</td>
    <td title="${escapeHTML(tx.wallet_label)}">${escapeHTML(shortWallet(tx.wallet_label))}</td>
    <td class="mono cell-amount">${formatBTC(tx.amount_sats)}</td>
    <td>${tx.fee_rate > 0 ? tx.fee_rate + ' sat/vB' : '--'}</td>
    <td>${coinAge}</td>
    <td class="cell-status">${badgeHTML(tx.status, tx.txid_full)}${locktimeLock(tx)}</td>
    <td class="cell-target">${targetCell}</td>
    <td class="cell-actions">${buildActions(tx)}</td>
  </tr>`;
}

function onTargetInput(txid) {
  const input = document.getElementById('blk-' + txid);
  const okBtn = document.getElementById('ok-' + txid);
  if (!input || !okBtn) return;
  // Show OK only if there's a value
  okBtn.style.display = input.value.trim() ? 'inline-block' : 'none';
}

// --- Helpers ---

async function copyTx(txid, status) {
  const broadcast = status === 'confirmed' || status === 'broadcasting';
  let text, label;

  if (broadcast) {
    text = txid;
    label = t('txidCopied');
  } else {
    const data = await fetchJSON(`/api/txs/${txid}`);
    text = data.raw_hex || txid;
    label = t('hexCopied');
  }

  // Fallback for non-HTTPS contexts (Umbrel via Tailscale)
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    const el = document.querySelector(`[onclick*="${txid}"]`);
    if (el) {
      const orig = el.textContent;
      el.textContent = label;
      setTimeout(() => { el.textContent = orig; }, 800);
    }
  } catch (e) {
    console.warn('Copy failed:', e);
  }
}

function escapeHTML(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function formatBTC(sats) {
  if (!sats) return '--';
  if (unit === 'sats') {
    return `<span class="amt-num">${sats.toLocaleString()}</span><span class="amt-unit">sats</span>`;
  }
  const btc = sats / 1e8;
  const str = btc.toFixed(8);
  const [whole, dec] = str.split('.');
  const padded = dec.slice(0, 7).padEnd(7, '0');
  return `<span class="amt-whole">${whole}</span><span class="amt-dot">.</span><span class="amt-dec">${padded}</span><span class="amt-unit">BTC</span>`;
}

function toggleUnit() {
  unit = unit === 'btc' ? 'sats' : 'btc';
  localStorage.setItem('bp-unit', unit);
  const ub = document.getElementById('unit-btn'); if (ub) ub.textContent = unit === 'btc' ? 'BTC' : 'sats';
  renderTable(currentData.txs, currentData.current_height);
}

function shortWallet(label) {
  if (!label) return '--';
  const parts = label.split(/[\s\/]/);
  return parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
}

const TAG_SHORT = {
  'consolidacion': 'cons.',
  'barrido': 'barrido',
  'pago': 'pago',
  'lotes': 'lotes',
  'simple': 'simple',
};
const TAG_FULL = {
  'consolidacion': { es: 'Consolidacion: multiples UTXOs agrupados en la entrada', en: 'Consolidation: multiple UTXOs grouped in the input' },
  'barrido': { es: 'Barrido: 1 entrada, 1 salida', en: 'Sweep: 1 input, 1 output' },
  'pago': { es: 'Pago: 2 salidas (destino + cambio)', en: 'Payment: 2 outputs (destination + change)' },
  'lotes': { es: 'Lotes: mas de 2 salidas (batch payment)', en: 'Batch: more than 2 outputs' },
  'simple': { es: 'Simple', en: 'Simple' },
};

function formatTags(tags) {
  if (!tags || !tags.length) return '--';
  const short = tags.map(t => TAG_SHORT[t] || t).join(', ');
  const full = tags.map(t => (TAG_FULL[t] || {})[lang] || t).join('\n');
  return `<span title="${full}">${short}</span>`;
}

let rotatingIndex = 0;

function badgeHTML(status, txid) {
  const statusMap = {
    pending: t('st_pending'),
    scheduled: t('st_scheduled'),
    broadcasting: t('st_broadcasting'),
    confirmed: t('st_confirmed'),
    failed: t('st_failed'),
    replaced: t('st_replaced'),
    abandoned: t('st_abandoned'),
  };

  if (status === 'broadcasting') {
    const words = t('st_rotating');
    const word = words[rotatingIndex % words.length];
    return `<span class="badge badge-broadcasting">${word}</span>`;
  }

  if (status === 'failed' && txid) {
    return `<span class="badge badge-failed badge-clickable" onclick="retryFailedTx('${txid}')" title="${lang==='es'?'Click para verificar y reintentar':'Click to verify and retry'}">${statusMap[status]}</span>`;
  }

  return `<span class="badge badge-${status}">${statusMap[status] || status}</span>`;
}

function locktimeLock(tx) {
  if (!tx.locktime) return '';
  const lt = tx.locktime;

  // Only show if locktime is future
  const height = currentStatus.current_height || 0;
  const mtp = currentStatus.current_mtp || 0;

  if (lt.type === 'timestamp' && mtp && mtp > lt.value) return '';
  if (lt.type === 'block' && height && height >= lt.value) return '';

  const id = 'lock-' + tx.txid_full;
  let detail;
  if (lt.type === 'timestamp') {
    detail = `MTP: ${lt.date}`;
  } else {
    detail = `${lang === 'es' ? 'Bloque' : 'Block'}: ${lt.value.toLocaleString()}`;
  }

  return ` <span class="lock-icon" onclick="document.getElementById('${id}').classList.toggle('open')">&#128274;<span class="lock-detail" id="${id}">${detail}</span></span>`;
}

function dependencyTag(tx) {
  if (!tx.depends_on) return '';
  const parentStatus = tx.depends_on.status;
  const parentShort = tx.depends_on.txid_short;
  const resolved = parentStatus === 'confirmed' || parentStatus === 'broadcasting';

  if (resolved) return ''; // Parent already broadcast, no need to show

  const tip = lang === 'es'
    ? `CPFP: depende de ${parentShort} (${parentStatus}). Se retransmitira la madre primero.`
    : `CPFP: depends on ${parentShort} (${parentStatus}). Parent will be broadcast first.`;

  return ` <span class="dep-tag" title="${tip}">&#128279;</span>`;
}

function depPrefix(tx) {
  const indent = '&nbsp;&nbsp;'.repeat(Math.max(0, tx._depth - 1));
  const dep = tx.depends_on;
  const parentMissing = dep && (dep.status === 'unknown' || dep.status === 'confirmed' || dep.status === 'abandoned' || dep.status === 'replaced');
  const parentInPool = dep && !parentMissing;

  let tip, cls;
  if (!dep) {
    tip = '?';
    cls = 'dep-missing';
  } else if (parentInPool) {
    tip = (lang === 'es' ? 'Depende de ' : 'Depends on ') + dep.txid_short;
    cls = '';
  } else {
    tip = (lang === 'es' ? 'Depende de ' : 'Depends on ') + dep.txid_short + (lang === 'es' ? ' (no esta en BP)' : ' (not in BP)');
    cls = 'dep-missing';
  }

  return `<span class="dep-indent ${cls}" title="${tip}">${indent}↳ </span>`;
}

function coinAgeHTML(tx, currentHeight) {
  const age = tx.oldest_coin_age;
  if (age == null) return '--';

  // Estimate date: age blocks * ~10 min each
  const minutesAgo = age * 10;
  const approxDate = new Date(Date.now() - minutesAgo * 60000);
  const humanDuration = humanizeDuration(minutesAgo);
  const dateStr = approxDate.toLocaleDateString('es-ES', { year: 'numeric', month: 'short', day: 'numeric' });

  return `<span title="Confirmada ~${dateStr} (hace ${humanDuration})">${age.toLocaleString()} bl</span>`;
}

function humanizeDuration(totalMinutes) {
  const days = Math.floor(totalMinutes / 1440);
  const years = Math.floor(days / 365);
  const months = Math.floor((days % 365) / 30);
  const remainDays = days % 30;

  const parts = [];
  if (years > 0) parts.push(years + (years === 1 ? ' año' : ' años'));
  if (months > 0) parts.push(months + (months === 1 ? ' mes' : ' meses'));
  if (remainDays > 0 && years === 0) parts.push(remainDays + (remainDays === 1 ? ' dia' : ' dias'));
  if (parts.length === 0) {
    const hours = Math.floor(totalMinutes / 60);
    if (hours > 0) return hours + (hours === 1 ? ' hora' : ' horas');
    return Math.round(totalMinutes) + ' min';
  }
  return parts.join(', ');
}

function buildActions(tx) {
  const btns = [];
  if (tx.status === 'pending' || tx.status === 'scheduled') {
    btns.push(`<span class="action-icon send" onclick="broadcastNow('${tx.txid_full}')" title="${t('emit')}"><svg class="plane-icon" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></span>`);
    btns.push(`<span class="action-icon delete" onclick="deleteTx('${tx.txid_full}')" title="${t('delete')}"><svg class="x-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></span>`);
  }
  if (tx.status === 'failed') {
    btns.push(`<span class="action-icon send" onclick="retryTx('${tx.txid_full}')" title="${t('retry')}"><svg class="plane-icon" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></span>`);
    btns.push(`<span class="action-icon delete" onclick="deleteTx('${tx.txid_full}')" title="${t('delete')}"><svg class="x-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></span>`);
  }
  return btns.join('');
}

// --- Actions ---

async function schedule(txid) {
  const input = document.getElementById('blk-' + txid);
  if (!input) return;
  const block = parseInt(input.value);
  if (!block) return;

  const height = currentStatus.current_height || 0;

  if (height && block <= height) {
    // Target block is now or past — ask to broadcast immediately
    if (confirm(t('emitConfirm'))) {
      const result = await fetchJSON(`/api/txs/${txid}/broadcast-now`, { method: 'POST' });
      if (result.error) alert('Error: ' + result.error);
    }
  } else {
    await fetchJSON(`/api/txs/${txid}/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_block: block }),
    });
  }
  refresh();
}

async function broadcastNow(txid) {
  if (!confirm(t('emitConfirm'))) return;
  const result = await fetchJSON(`/api/txs/${txid}/broadcast-now`, { method: 'POST' });
  if (result.error) alert('Error: ' + result.error);
  refresh();
}

async function deleteTx(txid) {
  if (!confirm(t('deleteConfirm'))) return;
  await fetchJSON(`/api/txs/${txid}`, { method: 'DELETE' });
  refresh();
}

async function unschedule(txid) {
  await fetchJSON(`/api/txs/${txid}/unschedule`, { method: 'POST' });
  refresh();
}

async function retryTx(txid) {
  await broadcastNow(txid);
}

async function retryFailedTx(txid) {
  const msg = lang === 'es'
    ? 'Verificar en la blockchain y reintentar?'
    : 'Check blockchain and retry?';
  if (!confirm(msg)) return;

  const result = await fetchJSON(`/api/txs/${txid}/retry`, { method: 'POST' });
  if (result.ok) {
    const actionMsg = {
      confirmed: lang === 'es' ? 'Ya estaba confirmada' : 'Already confirmed',
      in_mempool: lang === 'es' ? 'Encontrada en mempool' : 'Found in mempool',
      rebroadcast: lang === 'es' ? 'Retransmitida' : 'Rebroadcast',
    };
    alert(actionMsg[result.action] || result.message);
  } else {
    alert('Error: ' + (result.message || result.error));
  }
  refresh();
}

async function autoAssign() {
  const base = parseInt(document.getElementById('aa-base').value);
  const offset = parseInt(document.getElementById('aa-offset').value) || 1;
  if (!base) { alert(t('enterBase')); return; }

  const result = await fetchJSON('/api/txs/auto-assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_block: base, offset }),
  });
  if (result.assigned !== undefined) refresh();
}

// --- Scan dependencies ---

async function rescanAll() {
  const btn = document.getElementById('btn-rescan');
  btn.style.opacity = '0.5';
  btn.disabled = true;

  const [deps] = await Promise.all([
    fetchJSON('/api/txs/scan-dependencies', { method: 'POST' }),
    fetchJSON('/api/txs/resolve-inputs', { method: 'POST' }),
  ]);

  btn.style.opacity = '1';
  btn.disabled = false;

  const msg = lang === 'es'
    ? `Escaneo completo. ${deps.found} dependencias detectadas.`
    : `Scan complete. ${deps.found} dependencies detected.`;
  alert(msg);
  refresh();
}

// --- Import ---

function toggleImport() {
  const panel = document.getElementById('import-panel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  document.getElementById('import-msg').textContent = '';
}

async function importTx() {
  const hex = document.getElementById('import-hex').value.trim();
  const label = document.getElementById('import-wallet').value;
  if (!hex) { alert(t('pasteAlert')); return; }

  const msgEl = document.getElementById('import-msg');
  msgEl.textContent = t('importing');
  msgEl.style.color = 'var(--text-muted)';

  const result = await fetchJSON('/api/txs/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_hex: hex, wallet_label: label }),
  });

  if (result.ok) {
    msgEl.style.color = 'var(--green)';
    msgEl.textContent = result.message;
    document.getElementById('import-hex').value = '';
    setTimeout(() => { toggleImport(); refresh(); }, 1500);
  } else {
    msgEl.style.color = 'var(--red)';
    msgEl.textContent = 'Error: ' + result.error;
  }
}

// --- Date picker ---

function showDatePicker(txid) {
  const existing = document.getElementById('datepicker-' + txid);
  if (existing) { existing.remove(); return; }

  // Find the tx data to check for locktime
  const tx = currentData.txs.find(t => t.txid_full === txid);
  const hasTimestampLock = tx && tx.locktime && tx.locktime.type === 'timestamp';

  let mtpButton = '';
  if (hasTimestampLock) {
    mtpButton = `<button class="small success" onclick="scheduleAtMtp('${txid}')" title="${tx.locktime.date}">
      ${lang === 'es' ? 'Emitir en MTP' : 'Broadcast at MTP'} (${tx.locktime.date})
    </button>`;
  }

  const row = document.getElementById('blk-' + txid).closest('tr');
  const picker = document.createElement('tr');
  picker.id = 'datepicker-' + txid;
  picker.innerHTML = `<td colspan="9" style="background:var(--bg-card);padding:12px;border-bottom:1px solid var(--border)">
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
      ${mtpButton}
      <span style="border-left:1px solid var(--border);height:20px" ${hasTimestampLock ? '' : 'hidden'}></span>
      <label style="font-size:13px;color:var(--text-muted)">${t('datePicker')}:</label>
      <input type="datetime-local" id="date-${txid}" class="inline-edit" style="width:220px">
      <button class="small" onclick="dateToBlock('${txid}')">${t('calcBlock')}</button>
      <span id="date-result-${txid}" style="font-size:13px;color:var(--text-muted)"></span>
      <button class="small secondary" onclick="document.getElementById('datepicker-${txid}').remove()">${t('close')}</button>
    </div>
  </td>`;
  row.after(picker);
}

async function scheduleAtMtp(txid) {
  const result = await fetchJSON(`/api/txs/${txid}/schedule-mtp`, { method: 'POST' });
  const picker = document.getElementById('datepicker-' + txid);
  if (picker) picker.remove();
  if (result.error) {
    alert('Error: ' + result.error);
  }
  refresh();
}

function dateToBlock(txid) {
  const dateInput = document.getElementById('date-' + txid);
  if (!dateInput.value) return;

  const targetDate = new Date(dateInput.value);
  const resultEl = document.getElementById('date-result-' + txid);

  fetchJSON('/api/status').then(s => {
    const now = new Date();
    const diffMinutes = (targetDate - now) / 60000;

    if (diffMinutes < 0) {
      resultEl.textContent = t('dateFuture');
      resultEl.style.color = 'var(--red)';
      return;
    }

    const blocksAhead = Math.ceil(diffMinutes / 10);
    const targetBlock = s.current_height + blocksAhead;

    const targetEpoch = Math.floor(targetDate.getTime() / 1000);
    const mtpLag = s.current_mtp ? (Math.floor(now.getTime() / 1000) - s.current_mtp) : 0;
    const mtpLagMin = Math.round(mtpLag / 60);

    document.getElementById('blk-' + txid).value = targetBlock;
    onTargetInput(txid); // Show OK button

    let info = `~${blocksAhead} ${t('blocks')} → ${t('thTarget').toLowerCase()} ${targetBlock.toLocaleString()}`;
    if (s.current_mtp) {
      info += ` | ${t('mtpLag')}: ${mtpLagMin} min`;
      if (targetEpoch < s.current_mtp) {
        info += ` | ${t('mtpPassed')}`;
        resultEl.style.color = 'var(--green)';
      } else {
        const mtpBlocksNeeded = Math.ceil((targetEpoch - s.current_mtp) / 600);
        info += ` | ${t('mtpWill')} ~${mtpBlocksNeeded} ${t('bl')}`;
        resultEl.style.color = 'var(--text-muted)';
      }
    }
    resultEl.textContent = info;
  });
}

// --- Dependency ordering ---

function orderWithDependencies(txs) {
  // Build tree and flatten with depth levels
  const result = [];
  const childrenMap = {};  // parent_txid -> [child_txs]
  const hasParent = new Set();

  for (const tx of txs) {
    if (tx.depends_on && tx.depends_on.txid) {
      const pid = tx.depends_on.txid;
      if (!childrenMap[pid]) childrenMap[pid] = [];
      childrenMap[pid].push(tx);
      hasParent.add(tx.txid_full);
    }
  }

  function addWithChildren(tx, depth) {
    tx._depth = depth;
    result.push(tx);
    if (childrenMap[tx.txid_full]) {
      for (const child of childrenMap[tx.txid_full]) {
        addWithChildren(child, depth + 1);
      }
    }
  }

  // Roots first (no parent)
  for (const tx of txs) {
    if (!hasParent.has(tx.txid_full)) {
      addWithChildren(tx, 0);
    }
  }

  // Orphans (parent not in active list)
  for (const tx of txs) {
    if (!result.includes(tx)) {
      tx._depth = 1;
      result.push(tx);
    }
  }

  return result;
}

// --- Sorting ---

function sortBy(field) {
  if (currentSort.field === field) {
    currentSort.asc = !currentSort.asc;
  } else {
    currentSort.field = field;
    currentSort.asc = true;
  }

  // Update arrows
  document.querySelectorAll('.sort-arrow').forEach(el => el.textContent = '');
  const arrow = document.getElementById('sort-' + field);
  if (arrow) arrow.textContent = currentSort.asc ? ' \u25B2' : ' \u25BC';

  renderTable(currentData.txs, currentData.current_height);
}

function applySorting(txs) {
  if (!currentSort.field) return txs;

  const sorted = [...txs];
  const f = currentSort.field;
  const dir = currentSort.asc ? 1 : -1;

  sorted.sort((a, b) => {
    let va = a[f];
    let vb = b[f];

    // Special: tx_tags is an array, sort by first tag or empty
    if (f === 'tx_tags') {
      va = (va && va.length) ? va[0] : '';
      vb = (vb && vb.length) ? vb[0] : '';
    }

    // Nulls go last
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;

    if (typeof va === 'string') return va.localeCompare(vb) * dir;
    return (va - vb) * dir;
  });

  return sorted;
}

// --- History toggle ---
let historyOpen = localStorage.getItem('bp-history-open') === 'true';

function toggleHistory() {
  historyOpen = !historyOpen;
  localStorage.setItem('bp-history-open', historyOpen);
  applyHistoryState();
}

function applyHistoryState() {
  const table = document.getElementById('confirmed-table');
  const arrow = document.getElementById('history-arrow');
  const filters = document.getElementById('hist-filters');
  if (table) table.style.display = historyOpen ? 'table' : 'none';
  if (arrow) arrow.style.transform = historyOpen ? 'rotate(90deg)' : 'rotate(0deg)';
  if (filters) filters.style.display = historyOpen ? 'flex' : 'none';
}

// --- Init ---
applyLang();
applyHistoryState();
refresh();
setInterval(refresh, 5000);

// --- History sorting ---

function sortHistBy(field) {
  if (histSort.field === field) {
    histSort.asc = !histSort.asc;
  } else {
    histSort.field = field;
    histSort.asc = true;
  }

  document.querySelectorAll('[id^="hsort-"]').forEach(el => el.textContent = '');
  const arrow = document.getElementById('hsort-' + field);
  if (arrow) arrow.textContent = histSort.asc ? ' \u25B2' : ' \u25BC';

  renderTable(currentData.txs, currentData.current_height);
}

function applyHistSorting(txs) {
  if (!histSort.field) return txs;

  const sorted = [...txs];
  const f = histSort.field;
  const dir = histSort.asc ? 1 : -1;

  sorted.sort((a, b) => {
    let va = a[f];
    let vb = b[f];

    if (f === 'tx_tags') {
      va = (va && va.length) ? va[0] : '';
      vb = (vb && vb.length) ? vb[0] : '';
    }

    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;

    if (typeof va === 'string') return va.localeCompare(vb) * dir;
    return (va - vb) * dir;
  });

  return sorted;
}

// Update broadcasting badges text every 2s
setInterval(() => {
  rotatingIndex = (rotatingIndex + 1) % 3;
  const words = t('st_rotating');
  document.querySelectorAll('.badge-broadcasting').forEach(el => {
    el.textContent = words[rotatingIndex % words.length];
  });
}, 2000);

// --- Tab switching ---

function switchTab(name) {
  activeTab = name;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const btn = document.querySelector(`[data-tab="${name}"]`);
  const content = document.getElementById('tab-' + name);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');

  if (name === 'settings') loadSettingsTab();
  if (name === 'vault') loadVault();
  if (name !== 'vault') clearVault();
}

function updateVaultTabVisibility() {
  const btn = document.getElementById('tab-btn-vault');
  if (btn) btn.style.display = currentNpub ? 'block' : 'none';
}

// --- Settings tab ---

async function loadSettingsTab() {
  const s = await fetchJSON('/api/settings');
  document.getElementById('set-host').value = s.upstream_host || '';
  document.getElementById('set-port').value = s.upstream_port || '';
  document.getElementById('set-ssl').checked = s.upstream_ssl || false;
  document.getElementById('set-npub').value = s.npub || '';
  document.getElementById('set-lang').value = lang;
  document.getElementById('set-unit').value = unit;

  // npub field lock
  const npubInput = document.getElementById('set-npub');
  const npubChangeBtn = document.getElementById('btn-npub-change');
  if (s.npub) {
    npubInput.readOnly = true;
    npubInput.style.opacity = '0.6';
    npubChangeBtn.style.display = 'inline-block';
    npubChangeBtn.textContent = lang === 'es' ? 'Cambiar' : 'Change';
  } else {
    npubInput.readOnly = false;
    npubInput.style.opacity = '1';
    npubChangeBtn.style.display = 'none';
  }

  // Discover Umbrel servers
  discoverUpstreams();
}

async function testUpstreamConnection() {
  const host = document.getElementById('set-host').value.trim();
  const port = parseInt(document.getElementById('set-port').value);
  const useSsl = document.getElementById('set-ssl').checked;
  const el = document.getElementById('upstream-status');

  if (!host || !port) {
    el.textContent = lang === 'es' ? 'Introduce host y puerto' : 'Enter host and port';
    el.style.color = 'var(--red)';
    return;
  }

  el.textContent = lang === 'es' ? 'Verificando...' : 'Checking...';
  el.style.color = 'var(--text-muted)';

  try {
    const result = await fetchJSON('/api/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, ssl: useSsl }),
    });

    if (result.ok) {
      const netName = result.network && result.network !== 'unknown'
        ? ' — ' + result.network.charAt(0).toUpperCase() + result.network.slice(1) : '';
      el.textContent = (lang === 'es' ? 'Conectado' : 'Connected') + netName;
      el.style.color = 'var(--green)';
    } else {
      el.textContent = (lang === 'es' ? 'Error: ' : 'Error: ') + result.error;
      el.style.color = 'var(--red)';
    }
  } catch {
    el.textContent = lang === 'es' ? 'Sin conexión' : 'Disconnected';
    el.style.color = 'var(--red)';
  }
}

async function discoverUpstreams() {
  const container = document.getElementById('discovered-servers');
  container.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${lang==='es'?'Buscando servidores Electrum locales...':'Discovering local Electrum servers...'}</span>`;

  try {
    const data = await fetchJSON('/api/discover-upstreams');
    const online = data.servers.filter(s => s.online);

    if (online.length === 0) {
      container.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${lang==='es'?'No se detectaron servidores Electrum en la red local':'No Electrum servers detected on local network'}</span>`;
      return;
    }

    const label = lang === 'es' ? 'Servidores Electrum locales encontrados:' : 'Local Electrum servers found:';
    const buttons = online.map(s => {
      const net = s.network && s.network !== 'unknown'
        ? s.network.charAt(0).toUpperCase() + s.network.slice(1) : '';
      const netColor = s.network === 'signet' ? 'var(--signet)' : s.network === 'testnet' ? 'var(--testnet)' : 'var(--text)';
      return `<button class="small secondary" style="margin:2px 4px 2px 0;font-size:12px" onclick="selectUpstream('${s.host}',${s.port},${s.ssl})" title="${s.server_version}">
        \u{1F7E2} ${s.name} <span style="color:${netColor}">${net}</span> (${s.host}:${s.port})
      </button>`;
    }).join('');

    container.innerHTML = `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="font-size:12px;color:var(--text-muted)">${label}</span>${buttons}
    </div>`;
  } catch {
    container.innerHTML = '';
  }
}

function unlockNpubField() {
  const msg = lang === 'es'
    ? 'Si cambias la npub, se borrará la bóveda de transacciones ya cifradas. Las nuevas transacciones se cifrarán con la nueva npub.\n\n¿Deseas continuar?'
    : 'If you change the npub, the existing encrypted vault will be deleted. New transactions will be encrypted with the new npub.\n\nDo you want to continue?';

  if (!confirm(msg)) return;

  const npubInput = document.getElementById('set-npub');
  const npubChangeBtn = document.getElementById('btn-npub-change');
  npubInput.readOnly = false;
  npubInput.style.opacity = '1';
  npubInput.value = '';
  npubInput.focus();
  npubChangeBtn.style.display = 'none';
  npubInput._vaultCleared = true; // flag to clear vault on save
}

function updateAaSuffix() {
  const val = parseInt(document.getElementById('aa-offset').value) || 0;
  document.getElementById('lbl-aa-suffix').textContent = val === 1 ? t('aaSuffix1') : t('aaSuffixN');
}

function selectUpstream(host, port, ssl) {
  document.getElementById('set-host').value = host;
  document.getElementById('set-port').value = port;
  document.getElementById('set-ssl').checked = ssl;
}

async function saveAllSettings() {
  const host = document.getElementById('set-host').value.trim();
  const port = parseInt(document.getElementById('set-port').value);
  const useSsl = document.getElementById('set-ssl').checked;
  const npub = document.getElementById('set-npub').value.trim();
  const newLang = document.getElementById('set-lang').value;
  const newUnit = document.getElementById('set-unit').value;

  if (!host || !port || isNaN(port)) {
    document.getElementById('settings-msg').textContent = lang === 'es' ? 'Host y puerto requeridos' : 'Host and port required';
    document.getElementById('settings-msg').style.color = 'var(--red)';
    return;
  }

  // Save upstream + npub to server
  const result = await fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upstream_host: host, upstream_port: port, upstream_ssl: useSsl, npub }),
  });

  if (result.error) {
    document.getElementById('settings-msg').textContent = 'Error: ' + result.error;
    document.getElementById('settings-msg').style.color = 'var(--red)';
    return;
  }

  // Show what was saved
  console.log('Settings saved:', result);

  // Save preferences locally
  if (newLang !== lang) {
    lang = newLang;
    localStorage.setItem('bp-lang', lang);
    applyLang();
  }
  if (newUnit !== unit) {
    unit = newUnit;
    localStorage.setItem('bp-unit', unit);
  }

  currentNpub = npub;
  updateVaultTabVisibility();

  // If npub was changed via unlock, clear the vault
  const npubInput = document.getElementById('set-npub');
  if (npubInput._vaultCleared) {
    await fetchJSON('/api/vault/clear', { method: 'POST' });
    npubInput._vaultCleared = false;
  }

  // Lock npub field if set
  if (npub) {
    npubInput.readOnly = true;
    npubInput.style.opacity = '0.6';
    document.getElementById('btn-npub-change').style.display = 'inline-block';
    document.getElementById('btn-npub-change').textContent = lang === 'es' ? 'Cambiar' : 'Change';
  } else {
    npubInput.readOnly = false;
    npubInput.style.opacity = '1';
    document.getElementById('btn-npub-change').style.display = 'none';
  }

  document.getElementById('settings-msg').textContent = t('saved') + ' — ' + host + ':' + port + (useSsl ? ' (SSL)' : '');
  document.getElementById('settings-msg').style.color = 'var(--green)';
  setTimeout(() => { document.getElementById('settings-msg').textContent = ''; }, 4000);
}

// --- Vault tab ---

async function loadVault() {
  vaultDecrypted = [];

  const noNpub = document.getElementById('vault-no-npub');
  const noExt = document.getElementById('vault-no-extension');
  const content = document.getElementById('vault-content');

  if (!currentNpub) {
    noNpub.style.display = 'block';
    noExt.style.display = 'none';
    content.style.display = 'none';
    return;
  }

  if (!window.nostr || !window.nostr.nip44) {
    noNpub.style.display = 'none';
    noExt.style.display = 'block';
    content.style.display = 'none';
    return;
  }

  noNpub.style.display = 'none';
  noExt.style.display = 'none';
  content.style.display = 'block';

  const lockBtn = document.getElementById('vault-lock-btn');
  lockBtn.textContent = '\u{1F512}';  // 🔒 locked
  lockBtn.classList.remove('unlocked');
  lockBtn.title = lang === 'es' ? 'Descifrando...' : 'Decrypting...';
  document.getElementById('vault-status').textContent = t('vaultDecrypting');

  try {
    const data = await fetchJSON('/api/vault');
    const entries = data.entries || [];

    for (const entry of entries) {
      try {
        const plaintext = await window.nostr.nip44.decrypt(entry.ephem_pubkey, entry.payload);
        const parsed = JSON.parse(plaintext);
        parsed._vault_id = entry.id;
        vaultDecrypted.push(parsed);
      } catch (e) {
        console.warn('Vault decrypt failed for entry', entry.id, e);
      }
    }

    const msg = `${vaultDecrypted.length} / ${entries.length} ${t('vaultDecrypted')}`;
    document.getElementById('vault-status').textContent = msg;

    if (vaultDecrypted.length > 0) {
      lockBtn.textContent = '\u{1F513}';  // 🔓 unlocked
      lockBtn.classList.add('unlocked');
      lockBtn.title = lang === 'es' ? 'Desbloqueada. Click para re-descifrar.' : 'Unlocked. Click to re-decrypt.';
    } else {
      lockBtn.textContent = '\u{1F512}';  // 🔒 locked
      lockBtn.title = lang === 'es' ? 'Click para descifrar' : 'Click to decrypt';
    }

    // Populate wallet filter
    const wallets = [...new Set(vaultDecrypted.map(e => e.wallet).filter(Boolean))];
    const ws = document.getElementById('vault-filter-wallet');
    ws.innerHTML = `<option value="">${lang==='es'?'Todas las wallets':'All wallets'}</option>` +
      wallets.map(w => `<option value="${w}">${w}</option>`).join('');

    renderVaultTable();
  } catch (e) {
    document.getElementById('vault-status').textContent = 'Error: ' + e.message;
    lockBtn.textContent = '\u{1F512}';
    lockBtn.classList.remove('unlocked');
    lockBtn.title = lang === 'es' ? 'Click para reintentar' : 'Click to retry';
  }
}

function clearVault() {
  vaultDecrypted = [];
  const body = document.getElementById('vault-body');
  if (body) body.innerHTML = '';
}

function renderVaultTable() {
  let filtered = [...vaultDecrypted];

  const typeF = document.getElementById('vault-filter-type').value;
  const walletF = document.getElementById('vault-filter-wallet').value;
  if (typeF) filtered = filtered.filter(e => e.tx_type === typeF);
  if (walletF) filtered = filtered.filter(e => e.wallet === walletF);

  // Sort
  if (vaultSort.field) {
    const f = vaultSort.field;
    const dir = vaultSort.asc ? 1 : -1;
    filtered.sort((a, b) => {
      let va = a[f], vb = b[f];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'string') return va.localeCompare(vb) * dir;
      return (va - vb) * dir;
    });
  }

  // Totals
  const totalAmount = filtered.reduce((s, e) => s + (e.amount_sats || 0), 0);
  const totalFees = filtered.reduce((s, e) => s + (e.fee_sats > 0 ? e.fee_sats : 0), 0);

  const tbody = document.getElementById('vault-body');
  const totalsRow = `<tr class="totals-row">
    <td>${filtered.length} txs</td><td></td><td></td>
    <td class="mono cell-amount">${formatBTC(totalAmount)}</td>
    <td></td>
    <td class="mono cell-amount">${formatBTC(totalFees)}</td>
    <td></td><td></td><td></td>
  </tr>`;

  tbody.innerHTML = totalsRow + filtered.map(e => {
    const delta = (e.target_block && e.confirmed_block) ? e.confirmed_block - e.target_block : null;
    let deltaStr = '--';
    if (delta !== null) {
      if (delta <= 1) deltaStr = `<span style="color:var(--green)">${delta===0?'0':'+'+delta}</span>`;
      else if (delta <= 3) deltaStr = `<span style="color:var(--orange)">+${delta}</span>`;
      else deltaStr = `<span style="color:var(--red)">+${delta}</span>`;
    }

    return `<tr>
      <td class="mono txid-copy" onclick="navigator.clipboard.writeText('${e.txid}')">${e.txid ? e.txid.slice(0,16)+'...' : '--'}</td>
      <td class="cell-tags">${e.tx_type || '--'}</td>
      <td>${e.wallet || '--'}</td>
      <td class="mono cell-amount">${formatBTC(e.amount_sats)}</td>
      <td>${e.fee_rate > 0 ? (Math.round(e.fee_rate * 100) / 100) + ' sat/vB' : '--'}</td>
      <td class="mono cell-amount">${e.fee_sats > 0 ? formatBTC(e.fee_sats) : '--'}</td>
      <td>${badgeHTML(e.status || 'confirmed')}</td>
      <td class="mono">${e.confirmed_block ? e.confirmed_block.toLocaleString() : '--'}</td>
      <td class="mono">${deltaStr}</td>
    </tr>`;
  }).join('');
}

function sortVaultBy(field) {
  if (vaultSort.field === field) vaultSort.asc = !vaultSort.asc;
  else { vaultSort.field = field; vaultSort.asc = true; }
  renderVaultTable();
}
