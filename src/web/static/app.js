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
let discoveredServers = [];

const i18n = {
  es: {
    title: 'Broadcast Pool',
    subtitle: 'Proxy Electrum con retransmisi\u00f3n programada de transacciones Bitcoin',
    net: 'Red', height: 'Altura', mtp: 'MTP', retained: 'Retenidas',
    scheduled: 'Programadas', connections: 'Conexiones', upstream: 'Upstream',
    connectionsTip: 'Wallets conectadas a Broadcast Pool en este momento',
    change: 'Cambiar', host: 'Host', port: 'Puerto', connect: 'Conectar',
    cancel: 'Cancelar', reconnecting: 'Reconectando...',
    importTx: 'Introducir TX ✍️',
    poolActionsLabel: 'Pool:',
    poolImportHeader: 'Importar',
    poolExportHeader: 'Exportar',
    presentPastWarn: '⚠ Esta tx tiene un nLockTime ya alcanzado. Emitirla deja una huella detectable en la cadena (anti-fee-sniping fingerprint). ¿Continuar?',
    lockIconPastTip: 'nLockTime ya alcanzado — la tx puede emitirse pero deja huella detectable en cadena',
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
    st_confirmed: 'confirmada', st_failed: 'fallida', st_replaced: 'reemplazada', st_abandoned: 'abandonada', st_expired: 'expirada',
    st_rotating: ['Retransmitida', 'esperando', 'confirmación'],
    emit: 'Emitir ahora', delete: 'Eliminar', retry: 'Reintentar',
    emitConfirm: 'Emitir esta transaccion ahora?',
    deleteConfirm: 'Eliminar esta transaccion? Los UTXOs quedaran libres.',
    pasteAlert: 'Pega el hex de la transaccion',
    datePicker: 'Fecha objetivo', calcBlock: 'Calcular bloque', close: 'Cerrar',
    dateFuture: 'La fecha debe ser futura',
    blocks: 'bloques', bl: 'bl',
    tabPool: 'Pool', tabSettings: 'Ajustes', tabVault: 'B\u00f3veda', tabHowto: 'C\u00f3mo funciona',
    setUpstream: '1. Conecta Broadcast Pool a un servidor Electrum',
    setUpstreamDesc: 'BP reenvía las txs a través de este servidor. También consulta altura de bloque y MTP para evaluar locktimes.',
    setVault: '3. B\u00f3veda cifrada (Nostr)',
    setPrefs: '4. Otras preferencias', setBehavior: '2. Comportamiento de Broadcast Pool',
    setBehaviorScopeNote: 'Estas reglas solo aplican a txs interceptadas a trav\u00e9s del proxy Electrum. Las introducidas manualmente (Importar TX \u270d\ufe0f) siempre quedan en Pendiente.', setLang: 'Idioma', setUnit: 'Unidad', setPort: 'Puerto',
    setNpubHelp: 'BP purga las txs confirmadas tras 1 bloque. Configura un npub para archivarlas cifradas \u2014 solo descifrable con una extensi\u00f3n NIP-07 (Alby, nos2x).',
    setNpubWarn: 'Nota: usa un npub burner \u2014 no asocies tu nym principal a tu actividad de tx bitcoin.',
    testConn: 'Verificar conexi\u00f3n',
    save: 'Guardar', saved: 'Guardado',
    connecting: 'Conectando...', connected: 'Conectado',
    connectBtn: 'Conectar', useServer: 'Usar este servidor',
    currentUpstream: 'Conectado a:', noServers: 'No se detectaron servidores Electrum en la red local',
    searchingServers: 'Buscando servidores Electrum locales...',
    localServers: 'Servidores Electrum locales encontrados:',
    hostPortRequired: 'Introduce host y puerto',
    checking: 'Verificando...', disconnected: 'Sin conexi\u00f3n',
    npubSaved: 'npub guardada', npubCleared: 'npub eliminada',
    saveNpub: 'Guardar',
    removeNpub: 'Quitar',
    removeNpubConfirm: '⚠ Vas a eliminar la npub configurada y la BÓVEDA cifrada asociada. Las txs archivadas se borran sin posibilidad de recuperación. ¿Continuar?',
    copied: 'copiado',
    subAutoFuture: '2.1 Auto programar tx con nLockTime futuro',
    subAutoFutureDesc: 'BP detecta nLockTime futuro (altura de bloque ≥ tip+1, o timestamp aún no rebasado por el MTP) y agenda la tx para retransmitir cuando se alcance el bloque o MTP indicado.<br><em>Activo por defecto.</em>',
    subAutoFutureToggle: 'Activar auto-programación de nLockTime futuro',
    subAutoPresentPast: '2.2 Auto transmitir con nLockTime presente o pasado',
    subAutoPresentPastDesc: 'Cuando la tx tiene nLockTime ≠ 0 y su condición ya está cumplida (altura ≤ tip actual, o MTP ya rebasado), BP la retransmite al instante al upstream sin requerir clic manual. Coincide con el patrón anti-fee-sniping de Sparrow/Core/Electrum, donde el locktime ≈ tip. Activarlo simularía comportamiento normal de Electrum Server para tx con nLockTime ≠ 0.<br><em>Desactivado por defecto.</em>',
    subAutoPresentPastToggle: 'Activar auto-transmisión para nLockTime presente o pasado',
    subAutoZero: '2.3 Auto transmitir con nLockTime = 0',
    subAutoZeroDesc: 'Cuando la tx llega con <code class="kbd-mono">nLockTime = 0</code> (sin restricción temporal), BP la retransmite al instante. Si lo dejas desactivado queda en Pendiente para que la dispares manualmente o la combines con un trigger por precio.<br><em>Desactivado por defecto.</em>',
    subAutoZeroToggle: 'Activar auto-transmisión para nLockTime = 0',
    subPrice: '2.4 Retransmisión por precio',
    subLiana: '2.5 Altura de bloque virtual',
    lianaDesc: 'Algunas wallets (p.ej. Liana) fijan el nLockTime al bloque actual sin permitir cambiarlo. BP puede reportarles una altura virtual mayor para que firmen con nLockTime futuro. Configura el offset y activa la funci\u00f3n antes de crear cada tx de ciclado.<br><em>Desactivado por defecto.</em>',
    lianaOffset: 'Offset',
    lianaBump: 'Avance por tx firmada',
    lianaBumpLabel: 'bloques que avanza la altura virtual por cada tx recibida en ella',
    lianaDisableAt: 'Auto-desactivar',
    lianaDisableAtTemplate: 'en bloque {n} (faltan {k} bloques)',
    lianaDisableAtPassed: 'pendiente — se desactivará en el próximo bloque',
    lianaEnabled: 'Activar altura virtual (se desactiva en 12 bloques reales)',
    lianaEnabledActive: 'Activar altura virtual (se desactiva en bloque {n})',
    priceDesc: 'Retransmite txs al cruzar un umbral de precio de BTC. \u00datil para enviar colateral ante una liquidaci\u00f3n inminente.<br><em>Desactivado por defecto.</em>',
    priceEnabled: 'Activar retransmisi\u00f3n por precio',
    priceSource: 'Fuente', priceNone: 'Seleccionar...', priceCustom: 'Or\u00e1culo local',
    priceSchedule: 'Retransmitir si BTC', priceBelow: 'cae por debajo de', priceAbove: 'sube por encima de',
    priceExpiry: 'Caduca', priceExpired: 'expirada',
    poolExport: 'Exportar pool', poolImport: 'Importar pool',
    exportModalTitle: 'Exportar pool',
    exportModalHelp: 'Elige c\u00f3mo cifrar el archivo. El export incluye solo transacciones activas (pending + scheduled).',
    exportMethodPassphrase: 'Passphrase', exportMethodNip44: 'NIP-44 (tu npub)',
    exportMethodNone: 'Sin cifrar (texto plano)',
    exportNoneWarn: '⚠ El archivo contendrá tus transacciones firmadas en claro. Cualquiera con acceso podrá verlas y retransmitirlas.',
    exportNoneAck: 'Entiendo y quiero exportar sin cifrar',
    exportNoneAckRequired: 'Marca la casilla de confirmación',
    exportPassphrasePlaceholder: 'Passphrase (m\u00edn 8)',
    exportPassphraseConfirmPlaceholder: 'Confirma passphrase',
    exportPassphraseWarn: '\u26a0 Si pierdes la passphrase, el archivo es irrecuperable.',
    exportNip44Help: 'Se cifrar\u00e1 con la npub configurada en BP. Para descifrar al importar necesitar\u00e1s una extensi\u00f3n NIP-07 (Alby, nos2x).',
    exportNip44NoNpub: 'No tienes npub configurada. Config\u00farala en la secci\u00f3n B\u00f3veda.',
    btnCancel: 'Cancelar', btnDownload: 'Descargar', btnAnalyze: 'Analizar', btnImport: 'Importar',
    importModalTitle: 'Importar pool',
    importModalHelp: 'Selecciona un archivo .bp exportado anteriormente.',
    importPassphrasePlaceholder: 'Passphrase del archivo',
    importNip44Help: 'Archivo cifrado NIP-44 \u2014 se requiere extensi\u00f3n NIP-07 (Alby/nos2x) para descifrar.',
    importPassphraseMismatch: 'Las passphrases no coinciden',
    importPassphraseShort: 'La passphrase debe tener al menos 8 caracteres',
    importExportError: 'Error',
    importNoTxs: 'El archivo no contiene transacciones activas para importar.',
    importSummaryTpl: 'Se a\u00f1adir\u00e1n {add} tx \u00b7 {dup} duplicadas (ignoradas) \u00b7 {conf} con conflicto UTXO',
    importConflictsTitle: '\u26a0 Conflictos detectados',
    importConflictsNote: 'Fase 1 no permite resolver conflictos UTXO. Salta esas txs en otra exportaci\u00f3n o limpia el pool antes de importar.',
    importNip44Needed: 'Necesitas instalar Alby o nos2x para descifrar este archivo.',
    importDone: '{n} importadas, {s} saltadas',
    exportInProgress: 'Generando archivo...',
    vaultNoNpub: 'Configura tu npub', vaultNoNpubDesc: 'Ve a Ajustes y pega tu npub para activar la b\u00f3veda cifrada',
    vaultNoExt: 'Extensi\u00f3n NIP-07 requerida', vaultNoExtDesc: 'Instala Alby o nos2x para descifrar la b\u00f3veda',
    vaultDecrypting: 'Descifrando...', vaultDecrypted: 'entradas descifradas',
    footerMade: 'Hecho en la madriguera de <a href="https://semillabitcoin.com" target="_blank">Semilla Bitcoin</a>',
    footerInspired: 'Inspirado en la propuesta Broadcast Pool de Craig Raw.',
    hexCopied: 'hex copiado', txidCopied: 'txid copiado',
    copyHex: 'Copiar tx hex', copyTxid: 'Copiar txid',
    mtpLag: 'MTP lag', mtpPassed: 'MTP ya paso esta fecha',
    mtpTip: 'Median Time Past: mediana de los timestamps de los \u00faltimos 11 bloques. El reloj que usa Bitcoin para evaluar nLocktimes en base a tiempo.',
    virtualHeight: 'Altura virtual',
    vhTip: 'Altura virtual que BP est\u00e1 reportando a las wallets. Las wallets firmar\u00e1n txs con nLockTime cerca de este valor.',
    mtpWill: 'MTP la alcanzara en',
  },
  en: {
    title: 'Broadcast Pool',
    subtitle: 'Electrum proxy with scheduled Bitcoin transaction broadcast',
    net: 'Network', height: 'Height', mtp: 'MTP', retained: 'Retained',
    scheduled: 'Scheduled', connections: 'Connections', upstream: 'Upstream',
    connectionsTip: 'Wallets currently connected to Broadcast Pool',
    change: 'Change', host: 'Host', port: 'Port', connect: 'Connect',
    cancel: 'Cancel', reconnecting: 'Reconnecting...',
    setBehavior: '2. Broadcast Pool behavior',
    setBehaviorScopeNote: 'These rules only apply to txs intercepted via the Electrum proxy. Txs added manually (Enter TX ✍️) always land as Pending.',
    importTx: 'Enter TX ✍️',
    poolActionsLabel: 'Pool:',
    poolImportHeader: 'Import',
    poolExportHeader: 'Export',
    presentPastWarn: '⚠ This tx has a nLockTime that already passed. Broadcasting it leaves a detectable on-chain fingerprint (anti-fee-sniping). Continue?',
    lockIconPastTip: 'nLockTime already passed — tx can be broadcast but leaves a detectable on-chain fingerprint',
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
    st_confirmed: 'confirmed', st_failed: 'failed', st_replaced: 'replaced', st_abandoned: 'abandoned', st_expired: 'expired',
    st_rotating: ['Broadcasted', 'waiting', 'confirmation'],
    emit: 'Broadcast now', delete: 'Delete', retry: 'Retry',
    emitConfirm: 'Broadcast this transaction now?',
    deleteConfirm: 'Delete this transaction? UTXOs will be freed.',
    pasteAlert: 'Paste the transaction hex',
    datePicker: 'Target date', calcBlock: 'Calculate block', close: 'Close',
    dateFuture: 'Date must be in the future',
    blocks: 'blocks', bl: 'bl',
    tabPool: 'Pool', tabSettings: 'Settings', tabVault: 'Vault', tabHowto: 'How it works',
    setUpstream: '1. Connect Broadcast Pool to an Electrum server',
    setUpstreamDesc: 'BP relays txs through this server. It also queries block height and MTP to evaluate locktimes.',
    setVault: '3. Encrypted vault (Nostr)',
    setPrefs: '4. Other preferences', setLang: 'Language', setUnit: 'Unit', setPort: 'Port',
    setNpubHelp: 'BP purges confirmed txs after 1 block. Set an npub to archive them encrypted — only decryptable with a NIP-07 extension (Alby, nos2x).',
    setNpubWarn: 'Tip: use a burner npub — don\'t link your main nym to your Bitcoin tx activity.',
    testConn: 'Test connection',
    save: 'Save', saved: 'Saved',
    connecting: 'Connecting...', connected: 'Connected',
    connectBtn: 'Connect', useServer: 'Use this server',
    currentUpstream: 'Connected to:', noServers: 'No Electrum servers detected on local network',
    searchingServers: 'Discovering local Electrum servers...',
    localServers: 'Local Electrum servers found:',
    hostPortRequired: 'Enter host and port',
    checking: 'Checking...', disconnected: 'Disconnected',
    npubSaved: 'npub saved', npubCleared: 'npub cleared',
    saveNpub: 'Save',
    removeNpub: 'Remove',
    removeNpubConfirm: '⚠ You are about to delete the configured npub and its encrypted VAULT. Archived txs will be permanently deleted with no recovery. Continue?',
    copied: 'copied',
    subAutoFuture: '2.1 Auto-schedule txs with future nLockTime',
    subAutoFutureDesc: 'BP detects a future nLockTime (block height ≥ tip+1, or a timestamp not yet reached by MTP) and schedules the tx to be broadcast when the target block or MTP arrives.<br><em>On by default.</em>',
    subAutoFutureToggle: 'Enable auto-scheduling for future nLockTime',
    subAutoPresentPast: '2.2 Auto-broadcast txs with present/past nLockTime',
    subAutoPresentPastDesc: 'When a tx has nLockTime ≠ 0 and the condition is already met (height ≤ current tip, or MTP already past the timestamp), BP forwards it to the upstream immediately without manual click. This matches the anti-fee-sniping pattern of Sparrow/Core/Electrum where locktime ≈ tip. Enabling this mimics the normal behavior of an Electrum Server for txs with nLockTime ≠ 0.<br><em>Off by default.</em>',
    subAutoPresentPastToggle: 'Enable auto-broadcast for present/past nLockTime',
    subAutoZero: '2.3 Auto-broadcast txs with nLockTime = 0',
    subAutoZeroDesc: 'When a tx arrives with <code class="kbd-mono">nLockTime = 0</code> (no time-lock), BP forwards it immediately. If you leave it off, it lands as Pending so you can fire it manually or pair it with a price trigger.<br><em>Off by default.</em>',
    subAutoZeroToggle: 'Enable auto-broadcast for nLockTime = 0',
    subPrice: '2.4 Price-triggered broadcast',
    subLiana: '2.5 Virtual block height',
    lianaDesc: 'Some wallets (e.g. Liana) set nLockTime to the current tip without allowing changes. BP can report a virtual height so they sign with a future nLockTime. Set the offset and enable before creating each cycling tx.<br><em>Off by default.</em>',
    lianaOffset: 'Offset',
    lianaBump: 'Blocks bumped per signed tx',
    lianaBumpLabel: 'blocks the virtual height advances per tx received at it',
    lianaDisableAt: 'Auto-disable',
    lianaDisableAtTemplate: 'at block {n} ({k} blocks left)',
    lianaDisableAtPassed: 'pending — will disable on next block',
    lianaEnabled: 'Enable virtual height (auto-disables after 12 real blocks)',
    lianaEnabledActive: 'Enable virtual height (auto-disables at block {n})',
    priceDesc: 'Broadcasts txs when BTC price crosses a set threshold. Use this to send collateral before a loan gets liquidated.<br><em>Off by default.</em>',
    priceEnabled: 'Enable price-based broadcast',
    priceSource: 'Source', priceNone: 'Select...', priceCustom: 'Local oracle',
    priceSchedule: 'Broadcast if BTC', priceBelow: 'drops below', priceAbove: 'rises above',
    priceExpiry: 'Expires', priceExpired: 'expired',
    poolExport: 'Export pool', poolImport: 'Import pool',
    exportModalTitle: 'Export pool',
    exportModalHelp: 'Choose how to encrypt the file. The export only includes active transactions (pending + scheduled).',
    exportMethodPassphrase: 'Passphrase', exportMethodNip44: 'NIP-44 (your npub)',
    exportMethodNone: 'Unencrypted (plaintext)',
    exportNoneWarn: '⚠ The file will contain your signed transactions in clear text. Anyone with access can see and rebroadcast them.',
    exportNoneAck: 'I understand and want to export unencrypted',
    exportNoneAckRequired: 'Check the acknowledgement box',
    exportPassphrasePlaceholder: 'Passphrase (min 8)',
    exportPassphraseConfirmPlaceholder: 'Confirm passphrase',
    exportPassphraseWarn: '⚠ If you lose the passphrase, the file is unrecoverable.',
    exportNip44Help: 'Will be encrypted with the npub set in BP. To decrypt on import you\'ll need a NIP-07 extension (Alby, nos2x).',
    exportNip44NoNpub: 'No npub configured. Set one in the Vault section.',
    btnCancel: 'Cancel', btnDownload: 'Download', btnAnalyze: 'Analyze', btnImport: 'Import',
    importModalTitle: 'Import pool',
    importModalHelp: 'Pick a .bp file you exported before.',
    importPassphrasePlaceholder: 'File passphrase',
    importNip44Help: 'NIP-44 encrypted file — you need a NIP-07 extension (Alby/nos2x) to decrypt.',
    importPassphraseMismatch: 'Passphrases do not match',
    importPassphraseShort: 'Passphrase must be at least 8 characters',
    importExportError: 'Error',
    importNoTxs: 'The file contains no active transactions to import.',
    importSummaryTpl: '{add} txs will be added · {dup} duplicates (ignored) · {conf} with UTXO conflict',
    importConflictsTitle: '⚠ Conflicts detected',
    importConflictsNote: 'Phase 1 cannot resolve UTXO conflicts. Skip those txs in another export or clean the pool before importing.',
    importNip44Needed: 'You need to install Alby or nos2x to decrypt this file.',
    importDone: '{n} imported, {s} skipped',
    exportInProgress: 'Generating file...',
    vaultNoNpub: 'Set up your npub', vaultNoNpubDesc: 'Go to Settings and paste your npub to enable the encrypted vault',
    vaultNoExt: 'NIP-07 extension required', vaultNoExtDesc: 'Install Alby or nos2x to decrypt the vault',
    vaultDecrypting: 'Decrypting...', vaultDecrypted: 'entries decrypted',
    footerInspired: 'Inspired by Craig Raw\'s Broadcast Pool proposal.',
    footerMade: 'Made in <a href="https://semillabitcoin.com" target="_blank">Semilla Bitcoin</a>\'s rabbit hole',
    hexCopied: 'hex copied', txidCopied: 'txid copied',
    copyHex: 'Copy tx hex', copyTxid: 'Copy txid',
    mtpLag: 'MTP lag', mtpPassed: 'MTP already passed this date',
    mtpTip: 'Median Time Past: median of the last 11 block timestamps. The clock Bitcoin uses to evaluate time-based nLocktimes.',
    virtualHeight: 'Virtual height',
    vhTip: 'Virtual height BP is reporting to wallets. Wallets will sign txs with nLockTime close to this value.',
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
  document.getElementById('tab-btn-howto').textContent = t('tabHowto');
  if (typeof renderHowto === 'function') renderHowto();

  document.getElementById('lbl-net').textContent = t('net');
  document.getElementById('lbl-height').textContent = t('height');
  document.getElementById('lbl-mtp').innerHTML = t('mtp') + ' <span class="help-tip" onclick="toggleTooltip(event,\'mtp-detail\')">?<span class="lock-detail" id="mtp-detail">' + t('mtpTip') + '</span></span>';
  document.getElementById('lbl-virtual-height').innerHTML = t('virtualHeight') + ' <span class="help-tip" onclick="toggleTooltip(event,\'vh-detail\')">?<span class="lock-detail" id="vh-detail">' + t('vhTip') + '</span></span>';
  document.getElementById('lbl-retained').textContent = t('retained');
  document.getElementById('lbl-scheduled').textContent = t('scheduled');
  document.getElementById('lbl-connections').textContent = t('connections');
  document.getElementById('lbl-connections').title = t('connectionsTip');
  document.getElementById('btn-import').innerHTML = t('importTx');
  document.getElementById('lbl-pool-actions').textContent = t('poolActionsLabel');
  document.getElementById('btn-pool-import-header').textContent = t('poolImportHeader');
  document.getElementById('btn-pool-export-header').textContent = t('poolExportHeader');

  // Settings tab
  document.getElementById('set-title-upstream').textContent = t('setUpstream');
  document.getElementById('set-upstream-desc').textContent = t('setUpstreamDesc');
  document.getElementById('set-title-vault').textContent = t('setVault');
  document.getElementById('set-title-prefs').textContent = t('setPrefs');
  if (typeof applyExportImportI18n === 'function') applyExportImportI18n();
  document.getElementById('set-npub-help').textContent = t('setNpubHelp');
  document.getElementById('set-npub-warn').textContent = t('setNpubWarn');
  document.getElementById('btn-test-conn').textContent = t('testConn');
  document.getElementById('set-lbl-port').textContent = t('setPort');
  document.getElementById('set-lbl-lang').textContent = t('setLang');
  document.getElementById('set-lbl-unit').textContent = t('setUnit');
  document.getElementById('set-title-behavior').textContent = t('setBehavior');
  document.getElementById('set-behavior-scope-note').textContent = t('setBehaviorScopeNote');
  document.getElementById('set-sub-auto-future').textContent = t('subAutoFuture');
  document.getElementById('set-auto-future-desc').innerHTML = t('subAutoFutureDesc');
  document.getElementById('set-lbl-auto-future').textContent = t('subAutoFutureToggle');
  document.getElementById('set-sub-auto-present-past').textContent = t('subAutoPresentPast');
  document.getElementById('set-auto-present-past-desc').innerHTML = t('subAutoPresentPastDesc');
  document.getElementById('set-lbl-auto-present-past').textContent = t('subAutoPresentPastToggle');
  document.getElementById('set-sub-auto-zero').textContent = t('subAutoZero');
  document.getElementById('set-auto-zero-desc').innerHTML = t('subAutoZeroDesc');
  document.getElementById('set-lbl-auto-zero').textContent = t('subAutoZeroToggle');
  document.getElementById('set-sub-liana').textContent = t('subLiana');
  document.getElementById('set-liana-desc').innerHTML = t('lianaDesc');
  document.getElementById('set-lbl-liana-offset').textContent = t('lianaOffset');
  document.getElementById('set-lbl-liana-bump').textContent = t('lianaBump');
  document.getElementById('set-liana-bump-label').textContent = t('lianaBumpLabel');
  document.getElementById('set-lbl-liana-disable-at').textContent = t('lianaDisableAt');
  document.getElementById('set-lbl-liana-enabled').textContent = t('lianaEnabled');
  document.getElementById('set-sub-price').textContent = t('subPrice');
  document.getElementById('set-price-desc').innerHTML = t('priceDesc');
  document.getElementById('set-lbl-price-enabled').textContent = t('priceEnabled');
  document.getElementById('price-manual-summary').textContent = lang === 'es' ? 'Configurar URL manualmente' : 'Configure URL manually';
  document.getElementById('manual-conn-summary').textContent = lang === 'es' ? 'Configurar manualmente' : 'Configure manually';
  // Banner del dashboard: el texto lo decide loadConnectInfo() según si hay
  // upstream Electrum conectado (depende del status), así que aquí solo
  // re-renderizamos cuando ya tenemos status fresco.
  if (currentStatus && typeof loadConnectInfo === 'function') loadConnectInfo(currentStatus);
  const saveNpubBtn = document.getElementById('btn-save-npub');
  if (saveNpubBtn && saveNpubBtn.style.display !== 'none') saveNpubBtn.textContent = t('saveNpub');


  // Vault tab
  document.getElementById('vault-no-npub-title').textContent = t('vaultNoNpub');
  document.getElementById('vault-no-npub-desc').textContent = t('vaultNoNpubDesc');
  document.getElementById('vault-no-ext-title').textContent = t('vaultNoExt');
  document.getElementById('vault-no-ext-desc').textContent = t('vaultNoExtDesc');


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
  const hasPricePicker = document.querySelector('[id^="pricepicker-"]');
  const isEditing = hasDatePicker || hasPricePicker || (active && (active.classList.contains('target-input') || active.tagName === 'TEXTAREA'));

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

  if (s.current_mtp) {
    const mtpDate = new Date(s.current_mtp * 1000);
    const lagMin = Math.round((Date.now() - mtpDate.getTime()) / 60000);
    document.getElementById('s-mtp').textContent = mtpDate.toLocaleDateString(undefined, {day:'numeric',month:'short'}) + ' ' + mtpDate.toLocaleTimeString(undefined, {hour:'2-digit',minute:'2-digit'});
    const mtpTip = lang === 'es'
      ? `Median Time Past: mediana de los timestamps de los ultimos 11 bloques.\nEs el reloj de Bitcoin para timelocks.\nLag actual: ${lagMin} min respecto al reloj del sistema.\nUnix: ${s.current_mtp}`
      : `Median Time Past: median of last 11 block timestamps.\nBitcoin's clock for timelocks.\nCurrent lag: ${lagMin} min vs system clock.\nUnix: ${s.current_mtp}`;
  } else {
    document.getElementById('s-mtp').textContent = '--';
  }

  // Virtual height display (replaces MTP when faking is active)
  const mtpEl = document.getElementById('status-mtp');
  const vhEl = document.getElementById('status-virtual-height');
  if (s.liana_height_offset && s.liana_height_offset > 0 && s.current_height) {
    mtpEl.style.display = 'none';
    vhEl.style.display = '';
    document.getElementById('s-virtual-height').textContent =
      (s.current_height + s.liana_height_offset).toLocaleString();
  } else {
    mtpEl.style.display = '';
    vhEl.style.display = 'none';
  }

  // Live countdown on the Liana auto-disable line (Settings panel)
  if (document.getElementById('set-liana-disable-at-row')) {
    updateLianaDisableAtDisplay(s.liana_disable_at_height, s.current_height);
  }
  updateLianaEnabledLabel(s.liana_disable_at_height);

  // Price display (next to tabs)
  const priceEl = document.getElementById('price-display');
  if (s.current_price && s.price_source) {
    priceEl.style.display = '';
    priceEl.textContent = '$' + Math.round(s.current_price).toLocaleString();
  } else {
    priceEl.style.display = 'none';
  }
}

// --- Settings (removed old inline panel functions) ---

// --- Table ---

function renderTable(txs, height) {
  const table = document.getElementById('tx-table');
  const empty = document.getElementById('empty-state');
  const tbody = document.getElementById('tx-body');
  const confirmedSection = document.getElementById('confirmed-section');
  const confirmedBody = document.getElementById('confirmed-body');

  const historyStatuses = new Set(['confirmed', 'replaced', 'abandoned', 'expired']);
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

  const isMtpScheduled = tx.status === 'scheduled' && !tx.target_block && !tx.target_price
    && tx.locktime && tx.locktime.type === 'timestamp';
  const isBlockScheduled = tx.status === 'scheduled' && tx.target_block;
  const isPriceScheduled = tx.status === 'scheduled' && tx.target_price;
  const isPending = tx.status === 'pending';

  const priceActive = currentStatus.price_source;
  const priceBtnHtml = priceActive
    ? `<button class="target-cal target-price-btn" onclick="showPricePicker('${tx.txid_full}')" title="$" style="right:24px;color:var(--mainnet)">$</button>`
    : '';

  let targetCell;
  if (isPriceScheduled) {
    // Price scheduled: show price threshold + expiry + pencil (if not expired)
    const dir = tx.price_direction === 'above' ? '↑' : '↓';
    const expired = isExpiredByDate(tx);
    let expiryTag = '';
    if (tx.expires_at) {
      const expDate = new Date(tx.expires_at);
      const remainingMin = Math.round((expDate - Date.now()) / 60000);
      if (remainingMin <= 0) {
        expiryTag = `<span class="target-rem" style="color:var(--red)">(${t('priceExpired')})</span>`;
      } else if (remainingMin < 60) {
        expiryTag = `<span class="target-rem">(${remainingMin}min)</span>`;
      } else if (remainingMin < 1440) {
        expiryTag = `<span class="target-rem">(${Math.round(remainingMin/60)}h)</span>`;
      } else {
        expiryTag = `<span class="target-rem">(${Math.round(remainingMin/1440)}d)</span>`;
      }
    }
    const editBtn = expired ? '' : `<span class="target-edit" onclick="unschedule('${tx.txid_full}')" title="${lang==='es'?'Modificar':'Edit'}">&#9998;</span>`;
    targetCell = `<div class="target-cell">
      <span class="mono">${dir} $${Math.round(tx.target_price).toLocaleString()}</span>
      ${expiryTag}
      ${editBtn}
    </div>`;
  } else if (isMtpScheduled) {
    // MTP scheduled: show date + pencil to edit
    targetCell = `<div class="target-cell">
      <span style="font-size:12px">MTP: ${tx.locktime.date}</span>
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
    // Pending: input + OK + calendar + $ (if price enabled)
    targetCell = `<div class="target-cell">
      <input class="target-input" type="text" inputmode="numeric" pattern="[0-9]*"
        id="blk-${tx.txid_full}" value="${val}" placeholder="--"
        oninput="onTargetInput('${tx.txid_full}')"
        onkeydown="if(event.key==='Enter')schedule('${tx.txid_full}')">
      <button class="target-ok" id="ok-${tx.txid_full}" onclick="schedule('${tx.txid_full}')">OK</button>
      ${priceBtnHtml}
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
    <td class="cell-status">${badgeHTML(tx.status, tx.txid_full)}</td>
    <td class="cell-status-icon">${locktimeLock(tx)}</td>
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

function toggleTooltip(event, id) {
  event.stopPropagation();
  const existing = document.getElementById('bp-tooltip');
  if (existing && existing.dataset.source === id) {
    existing.remove();
    return;
  }
  if (existing) existing.remove();

  const source = document.getElementById(id);
  if (!source) return;

  const rect = event.currentTarget.getBoundingClientRect();
  const tip = document.createElement('div');
  tip.id = 'bp-tooltip';
  tip.className = 'bp-tooltip';
  tip.dataset.source = id;
  tip.textContent = source.textContent;
  document.body.appendChild(tip);

  const tipW = tip.offsetWidth;
  let left = rect.left + rect.width / 2 - tipW / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipW - 8));
  tip.style.left = left + 'px';
  tip.style.top = (rect.bottom + 6) + 'px';
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.lock-icon') && !e.target.closest('.help-tip') && !e.target.closest('.bp-tooltip')) {
    const tip = document.getElementById('bp-tooltip');
    if (tip) tip.remove();
  }
});

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
    expired: t('st_expired'),
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
  // Branch on locktime_category (set by backend); falls back to old behavior if absent.
  const cat = tx.locktime_category;
  if (!cat || cat === 'zero') return '';
  if (!tx.locktime) return '';
  const lt = tx.locktime;
  const id = 'lock-' + tx.txid_full;
  const isPending = tx.status === 'pending';

  // Suppress the anti-fee-sniping warning when the user has already opted into
  // the fingerprint trade-off via the auto-broadcast toggle, OR when the tx is
  // no longer in pending state (the broadcast decision has already been taken).
  if (cat === 'present_past') {
    if (!isPending) return '';
    if (currentData && currentData.auto_broadcast_present_past_locktime) return '';
  }

  if (cat === 'future') {
    const autoMsg = tx.status === 'scheduled'
      ? (lang === 'es' ? ' — auto programada por nLockTime' : ' — auto-scheduled by nLockTime')
      : '';
    const clickMsg = isPending
      ? (lang === 'es' ? '\nClick para programar a este nLockTime' : '\nClick to schedule at this nLockTime')
      : '';
    const detail = lt.type === 'timestamp'
      ? `nLockTime MTP: ${lt.date}${autoMsg}${clickMsg}`
      : `nLockTime ${lang === 'es' ? 'bloque' : 'block'}: ${lt.value.toLocaleString()}${autoMsg}${clickMsg}`;
    const handler = isPending
      ? `clickLockIcon('${tx.txid_full}', '${id}', event)`
      : `toggleTooltip(event,'${id}')`;
    const cursor = isPending ? 'pointer' : 'help';
    return `<span class="lock-icon" style="cursor:${cursor}" onclick="${handler}">&#128274;<span class="lock-detail" id="${id}">${detail}</span></span>`;
  }

  // present_past: tx leaves an on-chain fingerprint if broadcast as-is.
  const ltStr = lt.type === 'timestamp'
    ? lt.date
    : (lang === 'es' ? 'bloque ' : 'block ') + lt.value.toLocaleString();
  const detail = `${t('lockIconPastTip')}\nnLockTime: ${ltStr}`;
  return `<span class="lock-icon lock-warn" style="cursor:help;color:var(--red,#e06060);opacity:1" onclick="toggleTooltip(event,'${id}')">&#9888;<span class="lock-detail" id="${id}">${detail}</span></span>`;
}

async function confirmPresentPastSchedule(tx) {
  // Native confirm() for now; a custom modal can replace this in Bloque E.
  return window.confirm(t('presentPastWarn'));
}

async function clickLockIcon(txid, tooltipId, event) {
  // First show tooltip so the user has visual feedback while the request flies.
  toggleTooltip(event, tooltipId);
  try {
    const resp = await fetch(`/api/txs/${txid}/auto-schedule-locktime`, { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) {
      console.warn('auto-schedule-locktime failed:', data.error);
      return;
    }
    refresh();
  } catch (e) {
    console.error('auto-schedule-locktime error:', e);
  }
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

function isExpiredByDate(tx) {
  if (!tx.expires_at) return false;
  return new Date(tx.expires_at) <= Date.now();
}

function buildActions(tx) {
  const btns = [];
  if ((tx.status === 'pending' || tx.status === 'scheduled') && !isExpiredByDate(tx)) {
    btns.push(`<span class="action-icon send" onclick="broadcastNow('${tx.txid_full}')" title="${t('emit')}"><svg class="plane-icon" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></span>`);
    btns.push(`<span class="action-icon delete" onclick="deleteTx('${tx.txid_full}')" title="${t('delete')}"><svg class="x-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></span>`);
  } else if (isExpiredByDate(tx) && tx.status === 'scheduled') {
    // Only allow delete for visually expired txs
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

  // Double-confirm if tx has present/past locktime (fingerprint risk on chain)
  const tx = currentData && currentData.txs.find(t => t.txid_full === txid);
  if (tx && tx.locktime_category === 'present_past') {
    if (!await confirmPresentPastSchedule(tx)) return;
  }

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
  const tx = currentData && currentData.txs.find(t => t.txid_full === txid);
  if (tx && tx.locktime_category === 'present_past') {
    if (!await confirmPresentPastSchedule(tx)) return;
  }
  if (!confirm(t('emitConfirm'))) return;
  const result = await fetchJSON(`/api/txs/${txid}/broadcast-now`, { method: 'POST' });
  if (result.error) alert('Error: ' + result.error);
  refresh();
}

async function deleteTx(txid) {
  if (!confirm(t('deleteConfirm'))) return;
  await fetchJSON(`/api/txs/${txid}`, { method: 'DELETE' });
  // Force immediate re-render (bypass isEditing check)
  const [txData, statusData] = await Promise.all([fetchJSON('/api/txs'), fetchJSON('/api/status')]);
  currentData = txData;
  currentStatus = statusData;
  updateStatus(statusData);
  renderTable(txData.txs, txData.current_height);
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

// --- Scan dependencies ---

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
  // Close price picker if open
  const pricePicker = document.getElementById('pricepicker-' + txid);
  if (pricePicker) pricePicker.remove();

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
  picker.innerHTML = `<td colspan="10" style="background:var(--bg-card);padding:12px;border-bottom:1px solid var(--border)">
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
  const tx = currentData && currentData.txs.find(t => t.txid_full === txid);
  if (tx && tx.locktime_category === 'present_past') {
    if (!await confirmPresentPastSchedule(tx)) return;
  }
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

  // Show current upstream connection (friendly label updated after discover)
  const curEl = document.getElementById('current-upstream');
  if (s.upstream_host) {
    curEl.textContent = `${t('currentUpstream')} ${upstreamLabel(s.upstream_host, s.upstream_port, s.upstream_ssl)}`;
  } else {
    curEl.textContent = '';
  }

  // Pre-fill manual form
  document.getElementById('set-host').value = s.upstream_host || '';
  document.getElementById('set-port').value = s.upstream_port || '';
  document.getElementById('set-ssl').checked = s.upstream_ssl || false;

  // npub
  document.getElementById('set-npub').value = s.npub || '';
  applyNpubFieldState(s.npub);

  // Preferences
  document.getElementById('set-lang').value = lang;
  document.getElementById('set-unit').value = unit;
  // Checkbox semantics are inverted: checked = user opted OUT (feature still ON by default)
  // New positive-polarity checkboxes (default ON for future, OFF for present/past + zero).
  document.getElementById('set-auto-future').checked = s.auto_schedule_locktime !== false;
  document.getElementById('set-auto-present-past').checked = !!s.auto_broadcast_present_past_locktime;
  document.getElementById('set-auto-zero').checked = !!s.auto_broadcast_zero_locktime;
  const lianaOffset = s.liana_height_offset || 0;
  const lianaBump = s.liana_increment_blocks_per_tx || 1000;
  const lianaDisableAt = s.liana_disable_at_height || 0;
  const lianaEnabled = lianaOffset > 0;
  document.getElementById('set-liana-enabled').checked = lianaEnabled;
  document.getElementById('set-liana-offset').value = lianaOffset;
  document.getElementById('set-liana-bump').value = lianaBump;
  updateLianaDisableAtDisplay(lianaDisableAt, currentStatus && currentStatus.current_height);
  updateLianaEnabledLabel(lianaDisableAt);
  toggleLianaFake(lianaEnabled);
  updateLianaOffsetLabel(lianaOffset);

  // Price
  const priceEnabled = !!s.price_source;
  document.getElementById('set-price-enabled').checked = priceEnabled;
  document.getElementById('price-source-config').style.display = priceEnabled ? 'block' : 'none';
  updatePriceCurrentLabel(s.price_source);
  if (priceEnabled) discoverPriceOracle();

  // Connection info (uses status endpoint for proxy_port + hidden_service)
  loadConnectInfo(currentStatus);

  // Discover Umbrel servers
  discoverUpstreams();
}

function applyNpubFieldState(npub) {
  const npubInput = document.getElementById('set-npub');
  const saveBtn = document.getElementById('btn-save-npub');
  const changeBtn = document.getElementById('btn-npub-change');
  const removeBtn = document.getElementById('btn-npub-remove');
  const statusEl = document.getElementById('npub-status');

  if (npub) {
    npubInput.readOnly = true;
    npubInput.style.opacity = '0.6';
    saveBtn.style.display = 'none';
    changeBtn.style.display = 'inline-block';
    changeBtn.textContent = lang === 'es' ? 'Cambiar' : 'Change';
    if (removeBtn) {
      removeBtn.style.display = 'inline-block';
      removeBtn.textContent = t('removeNpub');
    }
    statusEl.textContent = '';
  } else {
    npubInput.readOnly = false;
    npubInput.style.opacity = '1';
    saveBtn.style.display = 'inline-block';
    saveBtn.textContent = t('saveNpub');
    changeBtn.style.display = 'none';
    if (removeBtn) removeBtn.style.display = 'none';
    statusEl.textContent = '';
  }

  // Show save btn only when there's text to save (and field is editable)
  npubInput.oninput = () => {
    if (!npubInput.readOnly) {
      saveBtn.style.display = npubInput.value.trim() ? 'inline-block' : 'inline-block';
      statusEl.textContent = '';
    }
  };
}

async function testUpstreamConnection() {
  const host = document.getElementById('set-host').value.trim();
  const port = parseInt(document.getElementById('set-port').value);
  const useSsl = document.getElementById('set-ssl').checked;
  const el = document.getElementById('upstream-status');
  const connectBtn = document.getElementById('btn-connect-manual');

  connectBtn.style.display = 'none';

  if (!host || !port) {
    el.textContent = t('hostPortRequired');
    el.style.color = 'var(--red)';
    return;
  }

  el.textContent = t('checking');
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
      el.textContent = t('connected') + netName;
      el.style.color = 'var(--green)';
      // Show connect button
      connectBtn.style.display = 'inline-block';
      connectBtn.textContent = t('connectBtn');
    } else {
      el.textContent = 'Error: ' + result.error;
      el.style.color = 'var(--red)';
    }
  } catch {
    el.textContent = t('disconnected');
    el.style.color = 'var(--red)';
  }
}

async function discoverUpstreams() {
  const container = document.getElementById('discovered-servers');
  container.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${t('searchingServers')}</span>`;

  try {
    const data = await fetchJSON('/api/discover-upstreams');
    const online = data.servers.filter(s => s.online);
    discoveredServers = online;

    if (online.length === 0) {
      container.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${t('noServers')}</span>`;
      return;
    }

    const cards = online.map(s => {
      const net = s.network && s.network !== 'unknown'
        ? s.network.charAt(0).toUpperCase() + s.network.slice(1) : '';
      const netColor = s.network === 'mainnet' ? 'var(--mainnet)' : s.network === 'signet' ? 'var(--signet)' : s.network === 'testnet' ? 'var(--testnet)' : 'var(--text)';
      return `<button class="server-card" onclick="connectToUpstream('${s.host}',${s.port},${s.ssl})" title="${s.host}:${s.port}">
        <span class="server-dot">\u{1F7E2}</span>
        <span class="server-name">${s.name}</span>
        <span class="server-net" style="color:${netColor}">${net}</span>
      </button>`;
    }).join('');

    container.innerHTML = `<div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">${t('localServers')}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${cards}</div>`;

    // Update current-upstream label now that we know server names
    updateUpstreamLabel();
  } catch {
    container.innerHTML = '';
  }
}

function upstreamLabel(host, port, ssl) {
  const match = discoveredServers.find(s => s.host === host && s.port === port);
  if (match) {
    const net = match.network && match.network !== 'unknown'
      ? ' ' + match.network.charAt(0).toUpperCase() + match.network.slice(1) : '';
    return `${match.name}${net} (local)`;
  }
  // External server — show address + network from status
  const net = currentStatus.network;
  const netStr = net && net !== 'unknown'
    ? ' — ' + net.charAt(0).toUpperCase() + net.slice(1) : '';
  return `${host}:${port}${netStr}`;
}

function updateUpstreamLabel() {
  const curEl = document.getElementById('current-upstream');
  if (!curEl) return;
  const host = currentStatus.upstream_host;
  const port = currentStatus.upstream_port;
  const ssl = currentStatus.upstream_ssl;
  if (host) {
    curEl.textContent = `${t('currentUpstream')} ${upstreamLabel(host, port, ssl)}`;
  }
}

function unlockNpubField() {
  const msg = lang === 'es'
    ? 'Si cambias la npub, se borrará la bóveda de transacciones ya cifradas. Las nuevas transacciones se cifrarán con la nueva npub.\n\n¿Deseas continuar?'
    : 'If you change the npub, the existing encrypted vault will be deleted. New transactions will be encrypted with the new npub.\n\nDo you want to continue?';

  if (!confirm(msg)) return;

  const npubInput = document.getElementById('set-npub');
  npubInput.readOnly = false;
  npubInput.style.opacity = '1';
  npubInput.value = '';
  npubInput.focus();
  npubInput._vaultCleared = true;
  document.getElementById('btn-npub-change').style.display = 'none';
  document.getElementById('btn-save-npub').style.display = 'inline-block';
  document.getElementById('btn-save-npub').textContent = t('saveNpub');
  document.getElementById('npub-status').textContent = '';
}

// --- Wallet connection info ---

function loadConnectInfo(status) {
  const label = document.getElementById('connect-banner-label');
  const code = document.getElementById('connect-lan');
  const copyBtn = document.querySelector('.connect-banner .copy-btn');

  // Until BP is connected to an Electrum upstream, scheduler can't run and
  // serving the proxy address would mislead the user. Show a prompt instead.
  const upstreamConnected = !!(status && status.network);

  if (!upstreamConnected) {
    label.textContent = lang === 'es'
      ? 'Conecta Broadcast Pool a un servidor Electrum para continuar'
      : 'Connect Broadcast Pool to an Electrum server to continue';
    code.style.display = 'none';
    if (copyBtn) copyBtn.style.display = 'none';
    return;
  }

  const proxyPort = status.proxy_port || 50005;
  const hostname = location.hostname || 'tu-nodo.local';
  const lanAddr = hostname + ':' + proxyPort;
  label.textContent = lang === 'es' ? 'Conecta tu wallet a:' : 'Connect your wallet to:';
  code.textContent = lanAddr;
  code.style.display = '';
  if (copyBtn) copyBtn.style.display = '';
}

function copyConnectValue(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.textContent;

  try {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text);
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
    const orig = el.textContent;
    el.textContent = t('copied');
    setTimeout(() => { el.textContent = orig; }, 800);
  } catch (e) {
    console.warn('Copy failed:', e);
  }
}

// Connect to a discovered upstream server (click on card)
async function connectToUpstream(host, port, ssl) {
  const curEl = document.getElementById('current-upstream');
  curEl.textContent = t('connecting');
  curEl.style.color = 'var(--text-muted)';

  const result = await fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upstream_host: host, upstream_port: port, upstream_ssl: ssl }),
  });

  if (result.error) {
    curEl.textContent = 'Error: ' + result.error;
    curEl.style.color = 'var(--red)';
    return;
  }

  curEl.textContent = `${t('currentUpstream')} ${upstreamLabel(host, port, ssl)}`;
  curEl.style.color = 'var(--green)';
  setTimeout(() => { curEl.style.color = 'var(--text-muted)'; }, 2000);

  // Update manual form to match
  document.getElementById('set-host').value = host;
  document.getElementById('set-port').value = port;
  document.getElementById('set-ssl').checked = ssl;
  document.getElementById('upstream-status').textContent = '';
  document.getElementById('btn-connect-manual').style.display = 'none';
}

// Connect from the manual connection form
async function connectManual() {
  const host = document.getElementById('set-host').value.trim();
  const port = parseInt(document.getElementById('set-port').value);
  const ssl = document.getElementById('set-ssl').checked;
  const el = document.getElementById('upstream-status');

  el.textContent = t('connecting');
  el.style.color = 'var(--text-muted)';

  const result = await fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upstream_host: host, upstream_port: port, upstream_ssl: ssl }),
  });

  if (result.error) {
    el.textContent = 'Error: ' + result.error;
    el.style.color = 'var(--red)';
    return;
  }

  el.textContent = t('connected') + ' — ' + host + ':' + port;
  el.style.color = 'var(--green)';
  document.getElementById('btn-connect-manual').style.display = 'none';

  // Update current upstream display
  const curEl = document.getElementById('current-upstream');
  curEl.textContent = `${t('currentUpstream')} ${upstreamLabel(host, port, ssl)}`;

  // Keep details open so the user sees the success
}

// Save npub independently
async function saveNpub() {
  const npubInput = document.getElementById('set-npub');
  const statusEl = document.getElementById('npub-status');
  const npub = npubInput.value.trim();
  const clearVault = npubInput._vaultCleared || false;

  const result = await fetchJSON('/api/npub', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ npub, clear_vault: clearVault }),
  });

  if (result.error) {
    statusEl.textContent = 'Error: ' + result.error;
    statusEl.style.color = 'var(--red)';
    return;
  }

  npubInput._vaultCleared = false;
  currentNpub = npub;
  updateVaultTabVisibility();
  applyNpubFieldState(npub);

  statusEl.textContent = npub ? t('npubSaved') : t('npubCleared');
  statusEl.style.color = 'var(--green)';
  setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

async function removeNpub() {
  if (!confirm(t('removeNpubConfirm'))) return;

  const statusEl = document.getElementById('npub-status');
  const result = await fetchJSON('/api/npub', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ npub: '', clear_vault: true }),
  });

  if (result.error) {
    statusEl.textContent = 'Error: ' + result.error;
    statusEl.style.color = 'var(--red)';
    return;
  }

  // Reset the input and switch the Vault tab back to hidden
  document.getElementById('set-npub').value = '';
  currentNpub = '';
  updateVaultTabVisibility();
  applyNpubFieldState('');
  // If the user was viewing the Vault tab, send them back to Pool
  if (activeTab === 'vault') switchTab('pool');

  statusEl.textContent = t('npubCleared');
  statusEl.style.color = 'var(--green)';
  setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

// Inline preference saves (no global Save button)
function savePrefLang(val) {
  if (val !== lang) {
    lang = val;
    localStorage.setItem('bp-lang', lang);
    applyLang();
    renderTable(currentData.txs, currentData.current_height);
  }
}

function savePrefUnit(val) {
  if (val !== unit) {
    unit = val;
    localStorage.setItem('bp-unit', unit);
    const ub = document.getElementById('unit-btn'); if (ub) ub.textContent = unit === 'btc' ? 'BTC' : 'sats';
    renderTable(currentData.txs, currentData.current_height);
  }
}

// Positive-polarity toggles. Checked = feature ON.
function savePrefAutoFuture(checked) {
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_schedule_locktime: !!checked }),
  });
}

function savePrefAutoPresentPast(checked) {
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_broadcast_present_past_locktime: !!checked }),
  });
}

function savePrefAutoZero(checked) {
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_broadcast_zero_locktime: !!checked }),
  });
}

function updateLianaOffsetLabel(val) {
  const blocks = parseInt(val) || 0;
  const days = Math.round(blocks * 10 / 1440 * 10) / 10;  // 10 min/block
  const eq = document.getElementById('set-liana-offset-eq');
  if (eq) {
    if (blocks === 0) eq.textContent = lang === 'es' ? 'desactivado' : 'disabled';
    else if (days < 30) eq.textContent = `~${days} ${lang === 'es' ? 'días' : 'days'}`;
    else if (days < 365) eq.textContent = `~${Math.round(days/30*10)/10} ${lang === 'es' ? 'meses' : 'months'}`;
    else eq.textContent = `~${Math.round(days/365*10)/10} ${lang === 'es' ? 'años' : 'years'}`;
  }
}

function saveLianaOffset(val) {
  const offset = parseInt(val) || 0;
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ liana_height_offset: offset }),
  });
}

function saveLianaBump(val) {
  let bump = parseInt(val) || 1000;
  bump = Math.max(1, Math.min(bump, 10000));
  document.getElementById('set-liana-bump').value = bump;
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ liana_increment_blocks_per_tx: bump }),
  });
}

function updateLianaEnabledLabel(disableAt) {
  const el = document.getElementById('set-lbl-liana-enabled');
  if (!el) return;
  if (disableAt && disableAt > 0) {
    el.textContent = t('lianaEnabledActive').replace('{n}', disableAt.toLocaleString());
  } else {
    el.textContent = t('lianaEnabled');
  }
}

function updateLianaDisableAtDisplay(disableAt, currentHeight) {
  const row = document.getElementById('set-liana-disable-at-row');
  const label = document.getElementById('set-liana-disable-at-label');
  if (!disableAt || disableAt <= 0) {
    row.style.display = 'none';
    return;
  }
  row.style.display = '';
  const ch = currentHeight || 0;
  const remaining = disableAt - ch;
  if (remaining <= 0) {
    label.textContent = t('lianaDisableAtPassed');
  } else {
    label.textContent = t('lianaDisableAtTemplate')
      .replace('{n}', disableAt.toLocaleString())
      .replace('{k}', remaining);
  }
}

function toggleLianaFake(enabled) {
  const config = document.getElementById('liana-fake-config');
  const offsetInput = document.getElementById('set-liana-offset');
  const bumpInput = document.getElementById('set-liana-bump');
  config.classList.toggle('is-disabled', !enabled);
  if (enabled) {
    offsetInput.disabled = false;
    bumpInput.disabled = false;
  } else {
    offsetInput.disabled = true;
    bumpInput.disabled = true;
    // Reset to 0 when disabled; backend will clear disable_at automatically
    offsetInput.value = 0;
    updateLianaDisableAtDisplay(0, 0);
    updateLianaOffsetLabel(0);
    saveLianaOffset(0);
  }
}

function togglePriceSource(enabled) {
  document.getElementById('price-source-config').style.display = enabled ? 'block' : 'none';
  if (!enabled) {
    connectPriceSource('');
  } else {
    discoverPriceOracle();
  }
}

function connectPriceSource(source) {
  fetchJSON('/api/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price_source: source }),
  });
  updatePriceCurrentLabel(source);
}

function updatePriceCurrentLabel(source) {
  const el = document.getElementById('price-current-source');
  if (!source) {
    el.textContent = '';
  } else if (source === 'coingecko') {
    el.textContent = `${t('currentUpstream')} CoinGecko API`;
  } else {
    // Try to match a discovered oracle for friendly name (port 7777 from v2,
    // 3200 on older installs).
    const name = (source.includes(':7777') || source.includes(':3200'))
      ? 'El Or\u00e1culo (local)' : source;
    el.textContent = `${t('currentUpstream')} ${name}`;
  }
}

async function discoverPriceOracle() {
  const container = document.getElementById('price-discovered');
  container.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${t('searchingServers').replace('Electrum', 'precio')}</span>`;

  try {
    const data = await fetchJSON('/api/discover-price-oracle');
    const oracles = data.oracles || [];

    // Local oracles first, then CoinGecko
    let cards = '';
    for (const o of oracles) {
      const priceStr = o.price_usd ? '$' + Math.round(o.price_usd).toLocaleString() : '';
      cards += `<button class="server-card" onclick="connectPriceSource('${o.url}')" title="${o.url}">
        <span class="server-dot">\u{1F7E2}</span>
        <span class="server-name">${o.name}</span>
        <span class="server-net" style="color:var(--mainnet)">${priceStr}</span>
        <span class="server-net" style="color:var(--text-muted)">local</span>
      </button>`;
    }
    cards += `<button class="server-card" onclick="connectPriceSource('coingecko')">
      <span class="server-dot">\u{1F7E2}</span>
      <span class="server-name">CoinGecko API</span>
      <span class="server-net" style="color:var(--text-muted)">externa</span>
    </button>`;

    container.innerHTML = `<div style="display:flex;gap:8px;flex-wrap:wrap">${cards}</div>`;
  } catch {
    container.innerHTML = '';
  }
}

function connectPriceUrl() {
  const url = document.getElementById('set-price-url').value.trim();
  if (!url) return;
  connectPriceSource(url);
}

function showPricePicker(txid) {
  const existing = document.getElementById('pricepicker-' + txid);
  if (existing) { existing.remove(); return; }
  // Close date picker if open
  const datePicker = document.getElementById('datepicker-' + txid);
  if (datePicker) datePicker.remove();

  const row = document.getElementById('blk-' + txid).closest('tr');
  const picker = document.createElement('tr');
  picker.id = 'pricepicker-' + txid;
  // Default expiry: 7 days from now
  const defaultExpiry = new Date(Date.now() + 7 * 86400000);
  const expiryStr = defaultExpiry.toISOString().slice(0, 16);

  picker.innerHTML = `<td colspan="10" style="background:var(--bg-card);padding:12px;border-bottom:1px solid var(--border)">
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
      <label style="font-size:13px;color:var(--text-muted)">${t('priceSchedule')}</label>
      <select id="price-dir-${txid}" class="inline-edit" style="width:auto;padding:4px 8px">
        <option value="below">${t('priceBelow')}</option>
        <option value="above">${t('priceAbove')}</option>
      </select>
      <span style="color:var(--text-muted);font-weight:600">$</span>
      <input type="number" id="price-val-${txid}" class="inline-edit" style="width:120px" placeholder="50000">
      <span style="border-left:1px solid var(--border);height:20px"></span>
      <label style="font-size:13px;color:var(--text-muted)">${t('priceExpiry')}:</label>
      <input type="datetime-local" id="price-exp-${txid}" class="inline-edit" style="width:200px" value="${expiryStr}">
      <button class="small" onclick="scheduleByPrice('${txid}')">OK</button>
      <button class="small secondary" onclick="document.getElementById('pricepicker-${txid}').remove()">${t('close')}</button>
    </div>
  </td>`;
  row.after(picker);
}

async function scheduleByPrice(txid) {
  const tx = currentData && currentData.txs.find(t => t.txid_full === txid);
  if (tx && tx.locktime_category === 'present_past') {
    if (!await confirmPresentPastSchedule(tx)) return;
  }
  const price = parseFloat(document.getElementById('price-val-' + txid).value);
  const dir = document.getElementById('price-dir-' + txid).value;
  const expiryInput = document.getElementById('price-exp-' + txid).value;
  if (!price || price <= 0) return;

  const body = { target_price: price, direction: dir };
  if (expiryInput) body.expires_at = expiryInput;

  const result = await fetchJSON('/api/txs/' + txid + '/schedule-price', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (result.error) {
    alert('Error: ' + result.error);
    return;
  }

  const picker = document.getElementById('pricepicker-' + txid);
  if (picker) picker.remove();
  refresh();
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

// --- Pool export / import (Phase 1) ---

let _importParsedFile = null;
let _importDecryptedPayload = null;

function openExportModal() {
  document.getElementById('pool-modal-overlay').classList.add('is-open');
  document.getElementById('pool-modal-export').style.display = '';
  document.getElementById('pool-modal-import').style.display = 'none';
  document.getElementById('export-modal-error').classList.remove('is-visible');
  document.getElementById('export-passphrase').value = '';
  document.getElementById('export-passphrase-confirm').value = '';
  document.getElementById('export-none-ack').checked = false;
  document.querySelector('input[name="export-method"][value="passphrase"]').checked = true;
  updateExportMethod();
  applyExportImportI18n();
  // Populate the npub display for NIP-44 method
  const npub = currentStatus && currentStatus.npub || (document.getElementById('set-npub') ? document.getElementById('set-npub').value : '');
  document.getElementById('export-nip44-npub').textContent = npub || '';
}

function openImportModal() {
  document.getElementById('pool-modal-overlay').classList.add('is-open');
  document.getElementById('pool-modal-export').style.display = 'none';
  document.getElementById('pool-modal-import').style.display = '';
  document.getElementById('import-modal-error').classList.remove('is-visible');
  document.getElementById('import-step-pick').style.display = '';
  document.getElementById('import-step-review').style.display = 'none';
  document.getElementById('import-file').value = '';
  document.getElementById('import-passphrase').value = '';
  document.getElementById('import-passphrase-row').style.display = 'none';
  document.getElementById('import-nip44-row').style.display = 'none';
  document.getElementById('import-plan-submit').disabled = true;
  _importParsedFile = null;
  _importDecryptedPayload = null;
  applyExportImportI18n();
}

function closePoolModal(e) {
  if (e && e.target && e.target.id !== 'pool-modal-overlay') return;
  // Wipe passphrase fields BEFORE hiding the modal — Chrome only offers to save
  // credentials when a password field has a value at the moment its container
  // disappears. Emptying first silences the prompt.
  ['export-passphrase', 'export-passphrase-confirm', 'import-passphrase'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('pool-modal-overlay').classList.remove('is-open');
}

function applyExportImportI18n() {
  const setText = (id, key) => { const el = document.getElementById(id); if (el) el.textContent = t(key); };
  setText('export-modal-title', 'exportModalTitle');
  setText('export-modal-help', 'exportModalHelp');
  setText('export-method-passphrase', 'exportMethodPassphrase');
  setText('export-method-nip44', 'exportMethodNip44');
  setText('export-method-none', 'exportMethodNone');
  setText('export-passphrase-warn', 'exportPassphraseWarn');
  setText('export-none-warn', 'exportNoneWarn');
  setText('export-none-ack-label', 'exportNoneAck');
  setText('export-nip44-help', 'exportNip44Help');
  setText('export-modal-cancel', 'btnCancel');
  setText('export-modal-submit', 'btnDownload');
  document.getElementById('export-passphrase').placeholder = t('exportPassphrasePlaceholder');
  document.getElementById('export-passphrase-confirm').placeholder = t('exportPassphraseConfirmPlaceholder');
  setText('import-modal-title', 'importModalTitle');
  setText('import-modal-help', 'importModalHelp');
  setText('import-nip44-help', 'importNip44Help');
  setText('import-modal-cancel', 'btnCancel');
  setText('import-plan-submit', 'btnAnalyze');
  setText('import-review-cancel', 'btnCancel');
  setText('import-apply-submit', 'btnImport');
  setText('import-conflicts-title', 'importConflictsTitle');
  setText('import-conflicts-note', 'importConflictsNote');
  document.getElementById('import-passphrase').placeholder = t('importPassphrasePlaceholder');
}

function updateExportMethod() {
  const method = document.querySelector('input[name="export-method"]:checked').value;
  document.getElementById('export-passphrase-fields').style.display = method === 'passphrase' ? '' : 'none';
  document.getElementById('export-nip44-fields').style.display = method === 'nip44' ? '' : 'none';
  document.getElementById('export-none-fields').style.display = method === 'none' ? '' : 'none';
  // Reset the ack checkbox when switching away from "none"
  if (method !== 'none') document.getElementById('export-none-ack').checked = false;
}

function _showExportError(msg) {
  const el = document.getElementById('export-modal-error');
  el.textContent = msg;
  el.classList.add('is-visible');
}

async function doExport() {
  const method = document.querySelector('input[name="export-method"]:checked').value;
  document.getElementById('export-modal-error').classList.remove('is-visible');
  const submitBtn = document.getElementById('export-modal-submit');
  submitBtn.disabled = true;
  const originalText = submitBtn.textContent;
  submitBtn.textContent = t('exportInProgress');

  let body = { method };
  if (method === 'passphrase') {
    const p1 = document.getElementById('export-passphrase').value;
    const p2 = document.getElementById('export-passphrase-confirm').value;
    if (p1.length < 8) {
      _showExportError(t('importPassphraseShort'));
      submitBtn.disabled = false; submitBtn.textContent = originalText; return;
    }
    if (p1 !== p2) {
      _showExportError(t('importPassphraseMismatch'));
      submitBtn.disabled = false; submitBtn.textContent = originalText; return;
    }
    body.passphrase = p1;
    // Clear DOM inputs immediately so the password manager doesn't snapshot them
    document.getElementById('export-passphrase').value = '';
    document.getElementById('export-passphrase-confirm').value = '';
  } else if (method === 'none') {
    if (!document.getElementById('export-none-ack').checked) {
      _showExportError(t('exportNoneAckRequired'));
      submitBtn.disabled = false; submitBtn.textContent = originalText; return;
    }
  }

  try {
    const resp = await fetch('/api/pool/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ error: 'export failed' }));
      _showExportError(data.error || ('HTTP ' + resp.status));
      return;
    }
    const blob = await resp.blob();
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'broadcast-pool-export.bp';
    const txCount = resp.headers.get('X-Tx-Count') || '?';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    closePoolModal();
  } catch (e) {
    _showExportError(String(e));
  } finally {
    submitBtn.disabled = false; submitBtn.textContent = originalText;
  }
}

async function onImportFileChosen(input) {
  document.getElementById('import-modal-error').classList.remove('is-visible');
  document.getElementById('import-plan-submit').disabled = true;
  const file = input.files && input.files[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (parsed.version !== 1 || !parsed.encryption || !parsed.ciphertext) {
      throw new Error('not a valid BP export file');
    }
    _importParsedFile = parsed;
    if (parsed.encryption === 'passphrase') {
      document.getElementById('import-passphrase-row').style.display = '';
      document.getElementById('import-nip44-row').style.display = 'none';
    } else if (parsed.encryption === 'nip44') {
      document.getElementById('import-passphrase-row').style.display = 'none';
      document.getElementById('import-nip44-row').style.display = '';
      if (!window.nostr || !window.nostr.nip44) {
        _showImportError(t('importNip44Needed'));
        return;
      }
    } else {
      throw new Error('unsupported encryption: ' + parsed.encryption);
    }
    document.getElementById('import-plan-submit').disabled = false;
  } catch (e) {
    _showImportError(t('importExportError') + ': ' + e.message);
  }
}

function _showImportError(msg) {
  const el = document.getElementById('import-modal-error');
  el.textContent = msg;
  el.classList.add('is-visible');
}

async function doImportPlan() {
  document.getElementById('import-modal-error').classList.remove('is-visible');
  if (!_importParsedFile) return;
  const submitBtn = document.getElementById('import-plan-submit');
  submitBtn.disabled = true;

  try {
    let body;
    if (_importParsedFile.encryption === 'nip44') {
      const ephem = (_importParsedFile.encryption_meta || {}).ephem_pubkey;
      const plaintext = await window.nostr.nip44.decrypt(ephem, _importParsedFile.ciphertext);
      _importDecryptedPayload = JSON.parse(plaintext);
      body = { decrypted_payload: _importDecryptedPayload };
    } else {
      const pass = document.getElementById('import-passphrase').value;
      if (!pass) { _showImportError(t('importPassphraseShort')); submitBtn.disabled = false; return; }
      body = { file: _importParsedFile, passphrase: pass };
      // Clear the DOM input right away to prevent the password manager snapshot
      document.getElementById('import-passphrase').value = '';
    }

    const resp = await fetch('/api/pool/import-plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      _showImportError(data.error || ('HTTP ' + resp.status));
      submitBtn.disabled = false;
      return;
    }
    _renderImportSummary(data, body);
  } catch (e) {
    _showImportError(String(e));
    submitBtn.disabled = false;
  }
}

function _renderImportSummary(plan, planBody) {
  document.getElementById('import-step-pick').style.display = 'none';
  document.getElementById('import-step-review').style.display = '';

  const addN = (plan.to_add || []).length;
  const dupN = (plan.duplicates || []).length;
  const confN = (plan.conflicts || []).length;

  document.getElementById('import-summary').textContent = t('importSummaryTpl')
    .replace('{add}', addN).replace('{dup}', dupN).replace('{conf}', confN);

  const conflictsBlock = document.getElementById('import-conflicts-block');
  const conflictsList = document.getElementById('import-conflicts-list');
  if (confN > 0) {
    conflictsBlock.style.display = '';
    conflictsList.innerHTML = plan.conflicts.map(c =>
      `→ ${c.imported_txid.slice(0,16)}... ↔ ${c.existing_txids.map(t => t.slice(0,12)+'...').join(', ')}`
    ).join('<br>');
    document.getElementById('import-apply-submit').disabled = (addN === 0);
  } else {
    conflictsBlock.style.display = 'none';
    document.getElementById('import-apply-submit').disabled = (addN === 0);
  }
  // Stash the body so apply can reuse it (no need to re-decrypt)
  document.getElementById('import-apply-submit').dataset.planBody = JSON.stringify(planBody);
}

async function doImportApply() {
  document.getElementById('import-modal-error').classList.remove('is-visible');
  const submitBtn = document.getElementById('import-apply-submit');
  submitBtn.disabled = true;
  try {
    const planBody = JSON.parse(submitBtn.dataset.planBody || '{}');
    // Phase 1: skip every conflicting tx automatically (no wizard yet)
    planBody.resolutions = {};
    // We don't know which were conflicts here without re-running plan; the server
    // will refuse and tell us if any blocking conflict remains. The simpler path:
    // ask for "skip-all-conflicts" by re-running plan on the server and marking them.
    // To keep it minimal, just call apply and let the server enforce.
    const resp = await fetch('/api/pool/import-apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(planBody),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (data.error === 'utxo_conflicts') {
        // Re-call with skip resolutions for every conflict
        const skipRes = {};
        for (const c of (data.conflicts || [])) skipRes[c.imported_txid] = 'skip';
        planBody.resolutions = skipRes;
        const resp2 = await fetch('/api/pool/import-apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(planBody),
        });
        const data2 = await resp2.json();
        if (!resp2.ok) { _showImportError(data2.error || 'apply failed'); submitBtn.disabled = false; return; }
        _finishImport(data2);
        return;
      }
      _showImportError(data.error || ('HTTP ' + resp.status));
      submitBtn.disabled = false;
      return;
    }
    _finishImport(data);
  } catch (e) {
    _showImportError(String(e));
    submitBtn.disabled = false;
  }
}

function _finishImport(result) {
  closePoolModal();
  refresh();
}

// --- How it works tab ---
// Static educational content. Re-rendered when the language toggles.
function renderHowto() {
  const root = document.getElementById('tab-howto');
  if (!root) return;
  // Resolve the wallet connect address dynamically (same value as the dashboard banner)
  const proxyPort = (currentStatus && currentStatus.proxy_port) || 50005;
  const connectAddr = (location.hostname || 'tu-nodo.local') + ':' + proxyPort;
  root.innerHTML = (lang === 'es') ? howtoHtmlES(connectAddr) : howtoHtmlEN(connectAddr);
}

function howtoHtmlES(connectAddr) {
  return `
  <div class="settings-section">
    <h2 class="settings-title">1. Qué es Broadcast Pool</h2>
    <p class="settings-help">Broadcast Pool (BP) es un proxy Electrum local. Se interpone entre tu wallet y tu servidor Electrum: cuando la wallet ordena broadcastear una tx, BP la <strong>retiene</strong> y la agenda para retransmitirla más tarde según el criterio que configures (bloque, MTP o precio de BTC).</p>
    <p class="settings-help">Tu wallet se conecta a BP exactamente como se conectaría a cualquier servidor Electrum. BP se conecta por su lado al servidor real. Para la wallet, BP es transparente y actúa como un servidor Electrum, salvo en el broadcast (que lo retiene).</p>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">2. Casos de uso</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Migración de wallet con privacidad</strong>
      <p class="settings-help">Firma N transacciones hoy, cada una con un <code class="kbd-mono">nLockTime</code> futuro distinto (aleatorio entre bloques futuros). BP las retransmite en bloques separados: ningún observador on-chain puede vincularlas por coincidir en el mismo bloque, y la wallet firmante no deja huella de timing.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Ciclados de Liana</strong>
      <p class="settings-help">Liana requiere ciclar monedas periódicamente para <strong>evitar que la clave de recuperación quede activa</strong> antes de lo previsto. El contador del timelock relativo (CSV) empieza al recibir cada UTXO; si no se ciclan a tiempo, la recovery key puede gastar los fondos sin la firma de la clave primaria. Firma hoy las txs de ciclado con <code class="kbd-mono">nLockTime</code> varios meses en el futuro. BP las retransmite a su tiempo, sin que debas estar presente ni tener la wallet disponible.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Colateral de préstamo Bitcoin</strong>
      <p class="settings-help">Pre-firma una tx de envío de colateral con <code class="kbd-mono">locktime 0</code> y configura un umbral de precio en BP. Si BTC cae por debajo del umbral, BP retransmite la tx automáticamente, sin intervención manual. Útil para evitar liquidaciones en protocolos de préstamo.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">3. Cómo conectarlo</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Paso 1 — Apunta BP a tu servidor Electrum</strong>
      <p class="settings-help">En <strong>Ajustes → Sección 1</strong>, introduce el host y puerto de tu servidor Electrum (p.ej. tu nodo Umbrel, Sparrow Server, Fulcrum). BP usará ese servidor para consultar la cadena y retransmitir transacciones.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Paso 2 — Apunta tu wallet a BP</strong>
      <p class="settings-help">Configura tu wallet para conectarse a BP en lugar de a tu servidor Electrum directamente. BP escucha en el puerto mostrado en la barra superior:</p>
      <p class="settings-help"><code class="kbd-mono">${connectAddr}</code></p>
      <p class="settings-help">Usa SSL desactivado (conexión TCP directa). Compatible con Sparrow, Liana y cualquier wallet que soporte servidores Electrum personalizados.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Paso 3 — Envía una transacción</strong>
      <p class="settings-help">Cuando la wallet broadcastee una tx, aparecerá en el Pool con estado <em>pendiente</em> o <em>programada</em>. A partir de ahí BP gestiona el timing.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">4. Cómo BP clasifica el nLockTime</h2>
    <p class="settings-help">BP lee el <code class="kbd-mono">nLockTime</code> de cada tx al recibirla y la clasifica en una de tres categorías. El comportamiento es distinto en cada caso.</p>
    <table>
      <thead>
        <tr><th>Categoría</th><th>Condición</th><th>Qué hace BP</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Futuro</strong></td>
          <td><code class="kbd-mono">locktime &gt; tip+1</code> o <code class="kbd-mono">mtp &lt; locktime</code></td>
          <td>Agenda automáticamente. Retransmite cuando el bloque o MTP alcanzan el locktime. No requiere intervención. Estado: <em>programada</em>.</td>
        </tr>
        <tr>
          <td><strong>Presente/Pasado ⚠</strong></td>
          <td><code class="kbd-mono">0 &lt; locktime ≤ tip+1</code></td>
          <td>Retiene con advertencia. Incluye el caso anti-fee-sniping (locktime ≈ altura actual). BP pide confirmación explícita antes de programar.</td>
        </tr>
        <tr>
          <td><strong>Cero</strong></td>
          <td><code class="kbd-mono">locktime == 0</code></td>
          <td>Sin limitación temporal. La tx queda en estado <em>pendiente</em> hasta que la emites manualmente o hasta que se dispara un trigger de precio configurado.</td>
        </tr>
      </tbody>
    </table>
    <p class="alert-soft"><strong>Anti-fee-sniping fingerprint:</strong> Sparrow, Electrum y wallets similares fijan el nLockTime a la altura actual del bloque como defensa contra fee-sniping. Bitcoin Core añade una capa extra: en ~10% de las txs resta un valor aleatorio entre 0 y 99 bloques al nLockTime, para que las txs con retardo de broadcast (CoinJoins de alta latencia, hardware wallets offline) no queden claramente diferenciadas. Si una tx se emite 100+ bloques tras su firma, el delta locktime→confirmación revela <em>el momento aproximado en que fue firmada</em> — combinable con otras huellas para inferir la herramienta usada. Si programas este tipo de txs con retardo intencional, asumes ese riesgo de privacidad.</p>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">5. Cuándo retransmite BP</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Por bloque</strong>
      <p class="settings-help">BP monitoriza la altura de bloque del servidor upstream. Cuando <code class="kbd-mono">current_height ≥ locktime</code>, retransmite la tx. Comprobación en cada nuevo bloque.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Por MTP (Median Time Past)</strong>
      <p class="settings-help">Para locktimes expresados como timestamp Unix, Bitcoin usa el MTP: la mediana de los timestamps de los últimos 11 bloques. BP retransmite cuando <code class="kbd-mono">mtp &gt; locktime_timestamp</code> (la tx pasa a ser final en consenso exactamente en ese punto). El MTP suele ir <strong>~1 hora</strong> por detrás del reloj real bajo condiciones normales de minado — esta diferencia se muestra en la barra de estado como <em>MTP lag</em>.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Por precio de BTC</strong>
      <p class="settings-help">Configura una fuente de precio (CoinGecko o un oráculo local) y un umbral en Ajustes → BP consulta el precio periódicamente. Al cruzar el umbral, retransmite todas las txs que tengan ese trigger activo. Útil para txs con <code class="kbd-mono">locktime 0</code> que no tienen constraint de bloque.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">6. Funciones avanzadas</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Altura de bloque virtual (Liana)</strong>
      <p class="settings-help">Liana fija el <code class="kbd-mono">nLockTime</code> a la altura del tip actual que ve en su servidor Electrum. No permite configurarlo manualmente. Pero si BP le reporta una altura virtual más alta (falsa), Liana firmará con un <code class="kbd-mono">nLockTime</code> futuro, bingo!</p>
      <p class="settings-help">El mecanismo funciona por evento: cada tx que Liana firma al tip virtual (la altura de bloque falsa) incrementa el offset en N bloques (<em>bump</em>). Esto permite acumular varias txs de ciclado con locktimes progresivamente más lejanos en una sola sesión, sin necesidad de recalcular manualmente.</p>
      <p class="settings-help"><strong>Cap de seguridad:</strong> la función se desactiva automáticamente a los 12 bloques reales desde que se activó. Pasado ese punto, la diferencia acumulada entre altura real y virtual podría confundir otras operaciones de la wallet. Volver a activar para la siguiente sesión de firma.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Retransmisión por precio</strong>
      <p class="settings-help">BP puede disparar el broadcast en función del precio de BTC. Configura una fuente de precio (CoinGecko o un oráculo local en tu nodo) y, por cada tx, un umbral con dirección — <em>por debajo de</em> o <em>por encima de</em> X. Cuando el precio cruza ese umbral, BP la retransmite inmediatamente.</p>
      <p class="settings-help">El polling al oráculo es cada 30 segundos. BP rechaza saltos de precio &gt;15% entre poll y poll como protección contra valores aberrantes (oráculo defectuoso). Si tu nodo expone un oráculo local, BP lo prefiere sobre CoinGecko — auto-descubre IPs internas comunes (Umbrel, Start9).</p>
      <p class="settings-help">Cada tx con trigger de precio puede tener una <strong>fecha de expiración</strong> opcional. Si el umbral no se cruza antes de esa fecha, la tx pasa a estado <em>expirada</em> y deja de monitorizarse. Sin expiración, queda armada indefinidamente.</p>
      <p class="settings-help"><strong>Combinación con locktime 0:</strong> el caso canónico es pre-firmar una tx de envío de colateral con <code class="kbd-mono">locktime 0</code> + umbral "por debajo de $X". La tx queda lista para dispararse si el precio cae, sin requerir tu presencia. Si en lugar de locktime 0 usas un locktime futuro, el broadcast espera al primero que se cumpla.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Bóveda cifrada (Nostr)</strong>
      <p class="settings-help">BP purga las txs confirmadas tras 1 bloque para mantener el pool ligero. Si configuras un npub en Ajustes → Sección 3, BP archiva cada tx confirmada cifrada con NIP-44 v2. El cifrado usa ECDH entre una clave efímera del lado servidor y tu clave pública (npub): solo quien posea la clave privada correspondiente puede descifrar.</p>
      <p class="settings-help">Los datos se guardan localmente en la base de datos de BP, no en relays Nostr. El descifrado ocurre en el browser vía extensión NIP-07 (Alby, nos2x): BP nunca ve tu clave privada. Usa un npub dedicado — no tu identidad Nostr principal — para no vincular tu actividad de txs a tu nym.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Export / Import del pool</strong>
      <p class="settings-help">Las txs pendientes y programadas viven en la base de datos local de BP. Si pierdes esa DB (reinstalación, migración de nodo), las txs sin broadcastear se pierden — los UTXOs quedan congelados hasta que alguien las retransmita o expire el locktime.</p>
      <p class="settings-help">Exporta el pool regularmente como backup. El archivo <code class="kbd-mono">.bp</code> puede cifrarse con passphrase o con tu npub (NIP-44). Al importar, BP detecta duplicados y conflictos de UTXO y los omite sin sobreescribir el estado existente.</p>
    </div>
  </div>
  `;
}

function howtoHtmlEN(connectAddr) {
  return `
  <div class="settings-section">
    <h2 class="settings-title">1. What is Broadcast Pool</h2>
    <p class="settings-help">Broadcast Pool (BP) is a local Electrum proxy. It sits between your wallet and your Electrum server: when the wallet orders a broadcast, BP <strong>holds</strong> the transaction and schedules it for later relay based on the criteria you configure (block height, MTP or BTC price).</p>
    <p class="settings-help">Your wallet connects to BP exactly as it would to any Electrum server. BP connects to the real server on its end. From the wallet's perspective, BP is transparent and acts as an Electrum server, except for broadcasts (which it holds).</p>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">2. Use cases</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Privacy-preserving wallet migration</strong>
      <p class="settings-help">Sign N transactions today, each with a distinct future <code class="kbd-mono">nLockTime</code> (randomized across future blocks). BP broadcasts them in separate blocks: no on-chain observer can link them by timing, and the signing wallet leaves no timing fingerprint.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Liana cycling transactions</strong>
      <p class="settings-help">Liana requires periodic coin cycling to <strong>prevent the recovery key from becoming active</strong> prematurely. The relative timelock (CSV) clock starts when each UTXO is received; if coins aren't cycled in time, the recovery key can spend the funds without the primary key's signature. Sign today's cycling txs with <code class="kbd-mono">nLockTime</code> months in the future. BP broadcasts them on schedule without requiring you to be present or have the wallet available.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Bitcoin loan collateral</strong>
      <p class="settings-help">Pre-sign a collateral tx with <code class="kbd-mono">locktime 0</code> and configure a price threshold in BP. If BTC drops below the threshold, BP broadcasts the tx automatically — no manual intervention needed. Useful for avoiding liquidations in lending protocols.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">3. How to connect</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Step 1 — Point BP to your Electrum server</strong>
      <p class="settings-help">In <strong>Settings → Section 1</strong>, enter the host and port of your Electrum server (e.g. your Umbrel node, Sparrow Server, Fulcrum). BP will use that server to query the chain and relay transactions.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Step 2 — Point your wallet to BP</strong>
      <p class="settings-help">Configure your wallet to connect to BP instead of directly to your Electrum server. BP listens on the port shown in the top bar:</p>
      <p class="settings-help"><code class="kbd-mono">${connectAddr}</code></p>
      <p class="settings-help">Use unencrypted TCP (no SSL). Compatible with Sparrow, Liana, and any wallet that supports custom Electrum servers.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Step 3 — Send a transaction</strong>
      <p class="settings-help">When the wallet broadcasts a tx, it will appear in the Pool with status <em>pending</em> or <em>scheduled</em>. From there, BP handles the timing.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">4. How BP classifies nLockTime</h2>
    <p class="settings-help">BP reads the <code class="kbd-mono">nLockTime</code> of each incoming tx and places it in one of three categories. Behavior differs per category.</p>
    <table>
      <thead>
        <tr><th>Category</th><th>Condition</th><th>What BP does</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Future</strong></td>
          <td><code class="kbd-mono">locktime &gt; tip+1</code> or <code class="kbd-mono">mtp &lt; locktime</code></td>
          <td>Auto-schedules. Broadcasts when block height or MTP reaches the locktime. No action needed. Status: <em>scheduled</em>.</td>
        </tr>
        <tr>
          <td><strong>Present/Past ⚠</strong></td>
          <td><code class="kbd-mono">0 &lt; locktime ≤ tip+1</code></td>
          <td>Holds with a warning. Includes the anti-fee-sniping case (locktime ≈ current height). BP requires explicit confirmation before scheduling.</td>
        </tr>
        <tr>
          <td><strong>Zero</strong></td>
          <td><code class="kbd-mono">locktime == 0</code></td>
          <td>No time constraint. The tx stays <em>pending</em> until you broadcast it manually or a configured price trigger fires.</td>
        </tr>
      </tbody>
    </table>
    <p class="alert-soft"><strong>Anti-fee-sniping fingerprint:</strong> Sparrow, Electrum and similar wallets set nLockTime to the current block height as a fee-sniping defense. Bitcoin Core adds an extra privacy layer: in ~10% of transactions it subtracts a random value between 0 and 99 from the nLockTime, so that delayed broadcasts (high-latency CoinJoins, offline hardware wallets) blend in. If a tx is broadcast 100+ blocks after signing, the locktime→confirmation delta reveals <em>the approximate signing time</em> — combinable with other transaction fingerprints to suggest which tool was used. Scheduling these txs with an intentional delay means accepting that privacy trade-off.</p>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">5. When BP broadcasts</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">By block height</strong>
      <p class="settings-help">BP monitors the upstream server's block height. When <code class="kbd-mono">current_height ≥ locktime</code>, the tx is broadcast. Checked on every new block.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">By MTP (Median Time Past)</strong>
      <p class="settings-help">For timestamp-based locktimes, Bitcoin evaluates against the MTP: the median of the last 11 block timestamps. BP broadcasts when <code class="kbd-mono">mtp &gt; locktime_timestamp</code> (the tx becomes final under consensus at that exact point). MTP typically lags real clock time by <strong>~1 hour</strong> under normal mining conditions — this delta is shown in the status bar as <em>MTP lag</em>.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">By BTC price</strong>
      <p class="settings-help">Configure a price source (CoinGecko or a local oracle) and a threshold in Settings → BP queries the price periodically. When the threshold is crossed, it broadcasts all txs with that trigger active. Most useful for txs with <code class="kbd-mono">locktime 0</code> that have no block constraint.</p>
    </div>
  </div>

  <div class="settings-section">
    <h2 class="settings-title">6. Advanced features</h2>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Virtual block height (Liana)</strong>
      <p class="settings-help">Liana sets <code class="kbd-mono">nLockTime</code> to the current tip it sees from its Electrum server. It provides no way to override this. But if BP reports a higher (fake) virtual height, Liana will sign with a future <code class="kbd-mono">nLockTime</code> — bingo.</p>
      <p class="settings-help">The mechanism is event-driven: each tx Liana signs at the virtual tip (the fake block height) bumps the offset by N blocks. This lets you accumulate several cycling txs with progressively later locktimes in a single session, without manual recalculation.</p>
      <p class="settings-help"><strong>Safety cap:</strong> the feature auto-disables after 12 real blocks from activation. Beyond that, the accumulated gap between real and virtual height could confuse other wallet operations. Re-enable for the next signing session.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Price-triggered broadcast</strong>
      <p class="settings-help">BP can fire a broadcast based on the BTC price. Set up a price source (CoinGecko or a local oracle on your node) and, per tx, a threshold with direction — <em>below</em> or <em>above</em> X. When the price crosses that threshold, BP broadcasts the tx immediately.</p>
      <p class="settings-help">The oracle is polled every 30 seconds. BP rejects price jumps &gt;15% between polls as a sanity check against bogus oracle values. If your node exposes a local price oracle, BP prefers it over CoinGecko — common internal IPs (Umbrel, Start9) are auto-discovered.</p>
      <p class="settings-help">Each price-triggered tx can have an optional <strong>expiry date</strong>. If the threshold isn't crossed before that date, the tx becomes <em>expired</em> and is no longer monitored. Without an expiry, it stays armed indefinitely.</p>
      <p class="settings-help"><strong>Pairing with locktime 0:</strong> the canonical use case is pre-signing a collateral tx with <code class="kbd-mono">locktime 0</code> + a "below $X" threshold. The tx is ready to fire if price drops, no presence required. If you use a future locktime instead of 0, the broadcast waits for whichever condition is met first.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Encrypted vault (Nostr)</strong>
      <p class="settings-help">BP purges confirmed txs after 1 block to keep the pool lean. If you set an npub in Settings → Section 3, BP archives each confirmed tx encrypted with NIP-44 v2. Encryption uses ECDH between a server-side ephemeral key and your public key (npub): only the holder of the corresponding private key can decrypt.</p>
      <p class="settings-help">Data is stored in BP's local database, not on Nostr relays. Decryption happens in the browser via NIP-07 extension (Alby, nos2x): BP never sees your private key. Use a dedicated npub — not your main Nostr identity — to avoid linking tx activity to your nym.</p>
    </div>
    <div class="settings-subsection">
      <strong class="settings-subsection-title">Pool export / import</strong>
      <p class="settings-help">Pending and scheduled txs live in BP's local database. If that DB is lost (reinstall, node migration), unbroadcast txs are gone — UTXOs stay frozen until someone relays them or the locktime expires.</p>
      <p class="settings-help">Export the pool regularly as a backup. The <code class="kbd-mono">.bp</code> file can be encrypted with a passphrase or your npub (NIP-44). On import, BP detects duplicates and UTXO conflicts and skips them without overwriting existing state.</p>
    </div>
  </div>
  `;
}
