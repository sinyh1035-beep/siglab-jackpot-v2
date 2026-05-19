<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SIGVIEW 잭팟 도구 시즌2 v1.3 | 외인 매집 포착 도구</title>
<meta name="description" content="SIGVIEW 잭팟 도구 시즌2 - 4차함수 c자리 + 외국인 매집 추세 + 20일선 횡단 패턴으로 외인과 동일 포지션 매집 종목 발굴.">
<meta name="robots" content="index, follow">
<style>
:root {
  --bg: #ffffff;
  --bg-secondary: #f7f6f1;
  --bg-tertiary: #f1efe8;
  --text-primary: #1a1a1a;
  --text-secondary: #5f5e5a;
  --text-tertiary: #888780;
  --border: rgba(0,0,0,0.08);
  --color-stealth-bg: #FFF6E0;
  --color-stealth-border: #D4A017;
  --color-stealth-text: #5B4400;
  --color-stealth-sub: #8B6914;
  --color-quiet-bg: #FAEEDA;
  --color-quiet-border: #BA7517;
  --color-quiet-text: #633806;
  --color-quiet-sub: #854F0B;
  --color-breakout-bg: #EAF3DE;
  --color-breakout-border: #639922;
  --color-breakout-text: #27500A;
  --color-breakout-sub: #3B6D11;
  --color-progress-bg: #F1EFE8;
  --color-progress-border: #B4B2A9;
  --color-progress-text: #2C2C2A;
  --color-progress-sub: #5F5E5A;
  --color-verified-bg: #E6F1FB;
  --color-verified-border: #378ADD;
  --color-verified-text: #042C53;
  --color-verified-sub: #185FA5;
  --color-risky-bg: #FBE6E6;
  --color-risky-border: #C0392B;
  --color-risky-text: #531A14;
  --color-risky-sub: #A5371F;
  --color-china-bg: #FCE4EC;
  --color-china-text: #B71C1C;
  --radius-md: 8px;
  --radius-lg: 12px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1a1a;
    --bg-secondary: #242422;
    --bg-tertiary: #2c2c2a;
    --text-primary: #f1efe8;
    --text-secondary: #b4b2a9;
    --text-tertiary: #888780;
    --border: rgba(255,255,255,0.08);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif;
  background: var(--bg);
  color: var(--text-primary);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.container { max-width: 760px; margin: 0 auto; padding: 24px 16px 80px; }

.header { margin-bottom: 20px; }
.brand { font-size: 11px; color: var(--text-tertiary); letter-spacing: 1.5px; margin-bottom: 4px; }
h1 { font-size: 24px; font-weight: 600; margin-bottom: 4px; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.philosophy { font-size: 12px; color: var(--text-tertiary); font-style: italic; }
.updated { font-size: 11px; color: var(--text-tertiary); margin-top: 6px; }

.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 20px 0; }
.stat-card { background: var(--bg-secondary); border-radius: var(--radius-md); padding: 12px 8px; text-align: center; }
.stat-label { font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; }
.stat-value { font-size: 20px; font-weight: 600; }
.stat-value.highlight { color: #D4A017; }

.section-title {
  font-size: 17px; font-weight: 600; margin: 28px 0 4px;
  display: flex; align-items: center; gap: 8px;
}
.section-desc { font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }

.stock-card {
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  margin-bottom: 10px;
  border: 1px solid;
  position: relative;
}
.stock-card.stealth { background: var(--color-stealth-bg); border-color: var(--color-stealth-border); }
.stock-card.quiet { background: var(--color-quiet-bg); border-color: var(--color-quiet-border); }
.stock-card.breakout { background: var(--color-breakout-bg); border-color: var(--color-breakout-border); }
.stock-card.progress { background: var(--color-progress-bg); border-color: var(--color-progress-border); }
.stock-card.verified { background: var(--color-verified-bg); border-color: var(--color-verified-border); }
.stock-card.risky { background: var(--color-risky-bg); border-color: var(--color-risky-border); }

.stealth .stock-name { color: var(--color-stealth-text); }
.stealth .stock-sub, .stealth .stock-stars, .stealth .stock-meta { color: var(--color-stealth-sub); }
.quiet .stock-name { color: var(--color-quiet-text); }
.quiet .stock-sub, .quiet .stock-stars, .quiet .stock-meta { color: var(--color-quiet-sub); }
.breakout .stock-name { color: var(--color-breakout-text); }
.breakout .stock-sub, .breakout .stock-stars, .breakout .stock-meta { color: var(--color-breakout-sub); }
.progress .stock-name { color: var(--color-progress-text); }
.progress .stock-sub, .progress .stock-stars, .progress .stock-meta { color: var(--color-progress-sub); }
.verified .stock-name { color: var(--color-verified-text); }
.verified .stock-sub, .verified .stock-stars, .verified .stock-meta { color: var(--color-verified-sub); }
.risky .stock-name { color: var(--color-risky-text); }
.risky .stock-sub, .risky .stock-stars, .risky .stock-meta { color: var(--color-risky-sub); }

.stock-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.stock-name { font-weight: 600; font-size: 15px; }
.stock-name-row { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.china-tag {
  display: inline-block; font-size: 10px; font-weight: 600;
  background: var(--color-china-bg); color: var(--color-china-text);
  padding: 1px 6px; border-radius: 3px;
}
.stock-stars { font-size: 13px; font-weight: 500; white-space: nowrap; }
.stock-sub { font-size: 12px; margin-bottom: 8px; }
.stock-meta { font-size: 11px; line-height: 1.7; opacity: 0.9; }
.score-badge {
  display: inline-block; font-weight: 600; font-size: 13px;
  background: rgba(0,0,0,0.06); padding: 2px 8px; border-radius: 10px;
  margin-left: 4px;
}
@media (prefers-color-scheme: dark) {
  .score-badge { background: rgba(255,255,255,0.08); }
}

.signals-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 12px;
  margin-top: 6px;
  font-size: 11px;
}
.signal-row { display: flex; justify-content: space-between; }
.signal-label { opacity: 0.75; }
.signal-value { font-weight: 500; }

.disclaimer {
  margin-top: 32px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.7;
}
.disclaimer strong { font-weight: 600; color: var(--text-secondary); }

.loading, .error { text-align: center; padding: 40px 20px; color: var(--text-secondary); font-size: 14px; }
.error { color: #c0392b; }

.empty-section { font-size: 12px; color: var(--text-tertiary); padding: 8px 4px; font-style: italic; }

@media (max-width: 480px) {
  .container { padding: 16px 14px 60px; }
  h1 { font-size: 20px; }
  .stats { grid-template-columns: repeat(4, 1fr); gap: 5px; }
  .stat-card { padding: 8px 4px; }
  .stat-value { font-size: 16px; }
  .signals-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="container">

<header class="header">
  <div class="brand">SIGVIEW · JACKPOT v1.3</div>
  <h1>잭팟 도구 시즌2</h1>
  <div class="subtitle">외인 매집 포착 · 4차함수 c자리 + 외국인 보유율 + 20일선 패턴</div>
  <div class="philosophy">"외인과 동일 포지션으로 매집기에 진입한다"</div>
  <div class="updated" id="updated">데이터 불러오는 중...</div>
</header>

<div class="stats" id="stats">
  <div class="stat-card"><div class="stat-label">🎯 외인매집</div><div class="stat-value highlight" id="stat-stealth">-</div></div>
  <div class="stat-card"><div class="stat-label">🐢 조용매집</div><div class="stat-value" id="stat-quiet">-</div></div>
  <div class="stat-card"><div class="stat-label">🌱 막깨고</div><div class="stat-value" id="stat-breakout">-</div></div>
  <div class="stat-card"><div class="stat-label">🇨🇳 중국</div><div class="stat-value" id="stat-china">-</div></div>
</div>

<div id="content">
  <div class="loading">데이터 불러오는 중...</div>
</div>

<div class="disclaimer">
  <strong>외인 매집 포착 도구 · 투자 권유 X</strong><br>
  본 데이터는 4차함수 패턴 매칭 + 외국인 보유율 추세 + 20일선 횡단 + 거래량 비대칭 분석 결과입니다.
  매집기에 외국인과 동일 포지션으로 진입하기 위한 도구이며, 특정 종목 추천이 아닙니다.
  모든 투자 판단과 책임은 본인에게 있습니다.<br><br>
  <span id="algo-info"></span>
</div>

</div>

<script>
const JSON_URL = './jackpot-v2.json';

function phaseToColor(phase) {
  return ({
    'stealth_accumulation': 'stealth',
    'quiet_accumulation': 'quiet',
    'early_breakout': 'breakout',
    'in_progress': 'progress',
    'already_run': 'verified',
    'risky': 'risky',
    'failed': 'risky',
    'neutral': 'progress',
  })[phase] || 'progress';
}

function trendLabel(trend) {
  return ({
    'accumulating': '🟢 매집중',
    'slight_up': '🟢 약매집',
    'flat': '⚪ 평이',
    'slight_down': '🟡 약감소',
    'distributing': '🔴 매도중',
    'unknown': '⚪ 데이터부족',
    'error': '⚪ -',
  })[trend] || '⚪';
}

function formatRatio(pct) {
  if (pct === null || pct === undefined) return '-';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(0)}%`;
}

function renderFrames(stock) {
  const frames = stock.frames || {};
  const labels = { daily: '일봉', weekly: '주봉', monthly: '월봉' };
  const lines = [];
  for (const key of ['daily', 'weekly', 'monthly']) {
    const f = frames[key];
    if (!f) continue;
    lines.push(`<div class="signal-row">
      <span class="signal-label">${labels[key]} c=${f.c_date} R²=${f.r2}</span>
      <span class="signal-value">${formatRatio(f.ratio_pct)}</span>
    </div>`);
  }
  return lines.join('');
}

function renderSignals(stock) {
  const s = stock.signals || {};
  const fiTrend = trendLabel(s.foreign_trend);
  const fiSlope = (s.foreign_slope_per_month !== undefined && s.foreign_slope_per_month !== null)
    ? `${s.foreign_slope_per_month >= 0 ? '+' : ''}${s.foreign_slope_per_month.toFixed(2)}%p/월`
    : '-';
  const fiPct = (s.foreign_latest_pct !== undefined && s.foreign_latest_pct !== null && s.foreign_latest_pct > 0)
    ? `${s.foreign_latest_pct.toFixed(1)}%`
    : '-';
  return `
    <div class="signals-grid">
      <div class="signal-row">
        <span class="signal-label">🌐 외인 추세</span>
        <span class="signal-value">${fiTrend} ${fiSlope}</span>
      </div>
      <div class="signal-row">
        <span class="signal-label">📊 외인 보유</span>
        <span class="signal-value">${fiPct}</span>
      </div>
      <div class="signal-row">
        <span class="signal-label">📈 20일선 횡단</span>
        <span class="signal-value">${s.ma20_crossings || 0}회 ${s.ma20_stealth ? '✓' : ''}</span>
      </div>
      <div class="signal-row">
        <span class="signal-label">📦 거래량 매집</span>
        <span class="signal-value">${(s.volume_down_up_ratio || 0).toFixed(2)} ${s.volume_accumulation ? '✓' : ''}</span>
      </div>
    </div>
  `;
}

function renderCard(stock) {
  const color = phaseToColor(stock.phase);
  const starStr = '★'.repeat(stock.stars);
  const chinaTag = stock.is_china_play ? '<span class="china-tag">🇨🇳 중국</span>' : '';
  const timeDiff = stock.time_diff_months !== undefined && stock.time_diff_months !== null
    ? `시간차 ${stock.time_diff_months}m · `
    : '';
  return `
    <div class="stock-card ${color}">
      <div class="stock-head">
        <div class="stock-name-row">
          <span class="stock-name">${stock.name}</span>
          ${chinaTag}
          <span class="score-badge">${stock.accumulation_score}점</span>
        </div>
        <span class="stock-stars">${starStr}</span>
      </div>
      <div class="stock-sub">${stock.type} · ${timeDiff}${stock.verdict}</div>
      <div class="stock-meta">
        ${renderFrames(stock)}
        ${renderSignals(stock)}
      </div>
    </div>
  `;
}

function renderSection(title, desc, stocks, emptyMsg) {
  let inner;
  if (!stocks || stocks.length === 0) {
    inner = `<div class="empty-section">${emptyMsg || '해당 조건 종목 없음'}</div>`;
  } else {
    inner = stocks.map(renderCard).join('');
  }
  return `
    <h2 class="section-title">${title}</h2>
    <div class="section-desc">${desc}</div>
    ${inner}
  `;
}

async function loadAndRender() {
  try {
    const res = await fetch(JSON_URL + '?t=' + Date.now());
    if (!res.ok) throw new Error('JSON 로드 실패');
    const data = await res.json();

    const dt = new Date(data.generated_at);
    document.getElementById('updated').textContent =
      `업데이트: ${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')} · ${data.n_matched}/${data.n_scanned} 매칭`;

    const summary = data.summary || {};
    document.getElementById('stat-stealth').textContent = summary.stealth_accumulation || 0;
    document.getElementById('stat-quiet').textContent = summary.quiet_accumulation || 0;
    document.getElementById('stat-breakout').textContent = summary.early_breakout || 0;
    document.getElementById('stat-china').textContent = summary.china_plays || 0;

    document.getElementById('algo-info').textContent =
      `알고리즘: ${data.algorithm?.name || 'MFAS v1.3'} · ${data.algorithm?.description || ''}`;

    const stocks = data.stocks || [];
    const stealth = stocks.filter(s => s.phase === 'stealth_accumulation');
    const quiet = stocks.filter(s => s.phase === 'quiet_accumulation');
    const breakout = stocks.filter(s => s.phase === 'early_breakout');
    const progress = stocks.filter(s => s.phase === 'in_progress');
    const verified = stocks.filter(s => s.phase === 'already_run');
    const risky = stocks.filter(s => s.phase === 'risky');

    const content =
      renderSection('🎯 진짜 외인 매집중', 
        '외국인 보유율 상승 + c자리 ±15% + 20일선 횡단 활발. **시즌2 코어 — 최우선 후보.**',
        stealth, '아직 조건을 만족하는 종목이 없습니다. 외인이 본격 매집 시작하면 여기 나타납니다.') +
      renderSection('🐢 조용한 매집중', 
        '외국인 보유율 ↑ + 가격 횡보. 20일선 패턴은 약하지만 진짜 매집 가능성.',
        quiet, '없음') +
      renderSection('🌱 막 깨고 나오는 중', 
        'c자리 통과 후 +10~30% 초기 상승. 매집기 종료, 본격 상승 시작.',
        breakout, '없음') +
      renderSection('🇨🇳 중국 회복 베팅 (총정리)', 
        '철강·화학·조선·해운·중공업 등 중국 경기 회복 직접 수혜 종목.',
        stocks.filter(s => s.is_china_play).slice(0, 10), '없음') +
      renderSection('⚪ 진행 중 (+30~60%)', 
        '상승 진행 중. 추격 부담 있음, 눌림목 대기.',
        progress.slice(0, 5), '없음') +
      renderSection('🔥 이미 폭발 (검증)', 
        '알고리즘 적중 입증용. 진입 X.',
        verified.slice(0, 5), '없음') +
      (risky.length > 0 ? renderSection('⚠️ 외인 매도 중 (회피)', 
        '외국인 보유율 하락. 가짜 신호 가능성, 회피 권장.',
        risky.slice(0, 5), '없음') : '');

    document.getElementById('content').innerHTML = content;
  } catch (e) {
    document.getElementById('content').innerHTML = `<div class="error">데이터 로드 실패: ${e.message}</div>`;
    console.error(e);
  }
}

loadAndRender();
</script>
</body>
</html>
