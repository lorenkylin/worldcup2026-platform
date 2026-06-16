/**
 * 2026 世界杯 H5 前端 SPA
 * 路由：hash 模式；数据：调用本地 /api/* 接口。
 */

const API_BASE = '/api';

// ---------- 工具函数 ----------

function $(sel) { return document.querySelector(sel); }

async function api(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fmtDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const date = d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });
  return { isToday, time, date, full: `${date} ${time}` };
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
}

function statusBadge(status) {
  if (status === 'live') return '<span class="badge-live inline-block px-2 py-0.5 rounded text-xs font-bold text-white">进行中</span>';
  if (status === 'finished') return '<span class="inline-block px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">已结束</span>';
  return '<span class="inline-block px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-400">未开始</span>';
}

function renderMatchScore(m) {
  if (m.status === 'finished' || (m.home_score !== null && m.away_score !== null)) {
    return '<span class="text-2xl font-bold score-big text-white">' + m.home_score + ' : ' + m.away_score + '</span>';
  }
  return '<span class="text-xl font-bold text-slate-500">VS</span>';
}

function matchCard(m) {
  const { time, date, isToday } = fmtDate(m.kickoff_at);
  const home = m.home_team || { name_zh: m.home_team_placeholder || '待定', flag_emoji: '' };
  const away = m.away_team || { name_zh: m.away_team_placeholder || '待定', flag_emoji: '' };
  return `
    <a href="#/match/${m.id}" class="match-card block bg-slate-900 rounded-xl p-4 mb-3 border border-slate-800">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs text-slate-400">${isToday ? '今天' : date} ${time}</span>
        ${statusBadge(m.status)}
      </div>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3 flex-1">
          <span class="team-flag">${home.flag_emoji || '🏳️'}</span>
          <span class="font-medium truncate">${escapeHtml(home.name_zh)}</span>
        </div>
        <div class="px-4">${renderMatchScore(m)}</div>
        <div class="flex items-center gap-3 flex-1 justify-end">
          <span class="font-medium truncate">${escapeHtml(away.name_zh)}</span>
          <span class="team-flag">${away.flag_emoji || '🏳️'}</span>
        </div>
      </div>
      <div class="mt-2 text-xs text-slate-500 truncate">${m.stadium ? escapeHtml(m.stadium.name_en) : ''} · ${m.group_name ? m.group_name + '组' : m.stage}</div>
      ${m._odds ? renderOddsBadge(m._odds) : ''}
    </a>
  `;
}

// M3: 赔率角标（在 matchCard 底部显示 1X2 赔率）
function renderOddsBadge(odds) {
  if (!odds || !odds.home_win || !odds.draw || !odds.away_win) return '';
  return `
    <div class="mt-2 pt-2 border-t border-slate-800 flex items-center gap-3 text-xs">
      <span class="text-slate-500">赔率</span>
      <span class="text-emerald-400 font-mono"><span class="text-slate-500 text-[10px] mr-1">主</span>${odds.home_win.toFixed(2)}</span>
      <span class="text-slate-400 font-mono"><span class="text-slate-500 text-[10px] mr-1">平</span>${odds.draw.toFixed(2)}</span>
      <span class="text-slate-400 font-mono"><span class="text-slate-500 text-[10px] mr-1">客</span>${odds.away_win.toFixed(2)}</span>
    </div>
  `;
}

// M3: 比赛详情赔率卡 + value bet 高亮
function renderOddsDetail(oddsData, homeName, awayName) {
  if (!oddsData || !oddsData.has_odds) {
    return `
      <div class="bg-slate-900 rounded-xl p-4 border border-slate-800 mb-4">
        <h3 class="font-bold text-cyan-400 mb-2">💰 市场赔率</h3>
        <div class="text-sm text-slate-500">该比赛暂无赔率（管理员可在后台录入）</div>
      </div>
    `;
  }
  const consensus = oddsData.consensus;
  const cmpHtml = consensus ? `
    <div class="grid grid-cols-3 gap-2 mt-3 text-center text-xs">
      <div class="bg-slate-950 rounded p-2">
        <div class="text-slate-500">主胜概率</div>
        <div class="text-base font-bold ${consensus.market_prob.home_prob > 0.5 ? 'text-emerald-400' : 'text-white'}">${(consensus.market_prob.home_prob * 100).toFixed(1)}%</div>
        <div class="text-slate-500 text-[10px]">赔率 ${consensus.odds.home_win.toFixed(2)}</div>
      </div>
      <div class="bg-slate-950 rounded p-2">
        <div class="text-slate-500">平局概率</div>
        <div class="text-base font-bold ${consensus.market_prob.draw_prob > 0.3 ? 'text-emerald-400' : 'text-white'}">${(consensus.market_prob.draw_prob * 100).toFixed(1)}%</div>
        <div class="text-slate-500 text-[10px]">赔率 ${consensus.odds.draw.toFixed(2)}</div>
      </div>
      <div class="bg-slate-950 rounded p-2">
        <div class="text-slate-500">客胜概率</div>
        <div class="text-base font-bold ${consensus.market_prob.away_prob > 0.5 ? 'text-emerald-400' : 'text-white'}">${(consensus.market_prob.away_prob * 100).toFixed(1)}%</div>
        <div class="text-slate-500 text-[10px]">赔率 ${consensus.odds.away_win.toFixed(2)}</div>
      </div>
    </div>
    <div class="text-xs text-slate-500 text-right mt-1">博彩公司利润 (vig) ${(consensus.market_prob.total_vig * 100).toFixed(1)}%</div>
  ` : '';

  // 列出各家赔率
  const bookmakersHtml = oddsData.bookmakers.length > 1 ? `
    <div class="mt-3 pt-3 border-t border-slate-800">
      <div class="text-xs text-slate-500 mb-1">各博彩公司</div>
      <div class="space-y-1">
        ${oddsData.bookmakers.map(b => `
          <div class="flex items-center justify-between text-xs">
            <span class="text-slate-400">${escapeHtml(b.bookmaker)}</span>
            <span class="font-mono text-slate-300">
              ${b.odds.home_win ? b.odds.home_win.toFixed(2) : '-'} /
              ${b.odds.draw ? b.odds.draw.toFixed(2) : '-'} /
              ${b.odds.away_win ? b.odds.away_win.toFixed(2) : '-'}
            </span>
          </div>
        `).join('')}
      </div>
    </div>
  ` : '';

  return `
    <div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-4 border border-slate-700 mb-4">
      <h3 class="font-bold text-cyan-400 mb-2">💰 市场赔率 · 多家公司共识</h3>
      ${cmpHtml}
      ${bookmakersHtml}
      <div class="text-[10px] text-slate-500 mt-2">赔率为 decimal 欧式赔率，市场概率已去除博彩公司利润(vig)。仅供分析，不构成投注建议。</div>
    </div>
  `;
}

// ---------- 页面渲染 ----------

// A2: 焦点战索引（模块级，每次点"换一换"递增）
let _homeFocusIdx = 0;

async function renderHome() {
  const [today, groups] = await Promise.all([
    apiWithRetry('/matches/today'),
    apiWithRetry('/groups'),
  ]);
  // A2: 选下一场作为焦点（轮询）
  if (_homeFocusIdx >= today.length) _homeFocusIdx = 0;
  const focus = today[_homeFocusIdx];
  const predictionHtml = focus ? await renderPredictionMini(focus.id) : '';

  $('#app').innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold flex items-center gap-2">
        <span class="w-1 h-5 bg-emerald-400 rounded"></span>今日赛程
      </h2>
      <button onclick="refreshCurrent()" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900">
        <span>🔄</span><span>刷新</span>
      </button>
    </div>
    <section class="mb-6">
      ${today.length ? today.map(m => matchCard(m)).join('') : renderEmpty('📅', '今日无比赛', '赛事还没开始，看看明日赛程吧', '#/schedule', '查看完整赛程')}
    </section>

    ${focus ? `
    <section class="mb-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="w-1 h-5 bg-amber-400 rounded"></span>焦点战预测
          <span class="text-xs text-slate-500 font-normal">（${_homeFocusIdx + 1}/${today.length}）</span>
        </h2>
        ${today.length > 1 ? `<button onclick="nextFocusMatch()" class="text-xs text-slate-400 hover:text-amber-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900">
          <span>🎲</span><span>换一换</span>
        </button>` : ''}
      </div>
      ${predictionHtml}
    </section>` : ''}

    <section class="mb-6">
      <a href="#/simulator" class="block bg-gradient-to-r from-violet-600/20 to-emerald-500/20 hover:from-violet-600/30 hover:to-emerald-500/30 transition rounded-xl p-4 border border-violet-500/30">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-violet-300 mb-1">🎲 出线模拟器 v0</div>
            <div class="text-xs text-slate-300">5000 次蒙特卡洛推演每队晋级概率</div>
          </div>
          <span class="text-2xl">→</span>
        </div>
      </a>
    </section>

    <section>
      <h2 class="text-lg font-bold mb-3 flex items-center gap-2">
        <span class="w-1 h-5 bg-blue-400 rounded"></span>小组积分榜
      </h2>
      ${renderGroupsMini(groups)}
    </section>
  `;
}

async function renderPredictionMini(matchId) {
  try {
    const p = await apiWithRetry('/matches/' + matchId + '/prediction');
    const stars = '★'.repeat(p.stars) + '☆'.repeat(5 - p.stars);
    const h2hBadge = p.h2h_summary
      ? `<div class="text-xs text-amber-300 mt-2">⚔️ ${escapeHtml(p.h2h_summary)}</div>`
      : '';
    const formBadges = (p.home_recent_form || p.away_recent_form)
      ? `<div class="text-xs text-emerald-400 mt-1">📈 ${p.home_recent_form ? '主 ' + escapeHtml(p.home_recent_form) : ''}${p.home_recent_form && p.away_recent_form ? ' / ' : ''}${p.away_recent_form ? '客 ' + escapeHtml(p.away_recent_form) : ''}</div>`
      : '';
    return `
      <a href="#/match/${matchId}" class="block bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-4 border border-slate-700">
        <div class="flex justify-between items-center mb-2">
          <span class="text-amber-400 tracking-widest">${stars}</span>
          <span class="text-xs text-slate-400">推荐比分 ${p.recommended_score}</span>
        </div>
        <div class="flex justify-between text-sm mb-3">
          <span>主胜 <b class="text-white">${p.home_win_prob}%</b></span>
          <span>平 <b class="text-white">${p.draw_prob}%</b></span>
          <span>客胜 <b class="text-white">${p.away_win_prob}%</b></span>
        </div>
        <ul class="text-xs text-slate-400 space-y-1">
          ${p.reasons.slice(0, 3).map(r => '<li>· ' + escapeHtml(r) + '</li>').join('')}
        </ul>
        ${h2hBadge}
        ${formBadges}
      </a>
    `;
  } catch (e) {
    return '';
  }
}

function renderGroupsMini(groups) {
  const keys = Object.keys(groups).sort();
  return keys.map(g => {
    const rows = groups[g].slice(0, 3);
    return `
      <a href="#/groups" class="block bg-slate-900 rounded-xl p-3 mb-3 border border-slate-800">
        <div class="text-sm font-bold text-emerald-400 mb-2">${g}组</div>
        <div class="space-y-2">
          ${rows.map((r, i) => `
            <div class="flex justify-between text-sm">
              <span class="text-slate-300">${i + 1}. ${r.team.flag_emoji || ''} ${escapeHtml(r.team.name_zh)}</span>
              <span class="text-slate-400">${r.played}场 ${r.points}分</span>
            </div>
          `).join('')}
        </div>
      </a>
    `;
  }).join('');
}

// A4 + A5: Schedule 筛选状态
let _scheduleFilter = 'all'; // 'today' | 'tomorrow' | 'week' | 'all'
let _scheduleDate = null;    // 选中的日期（YYYY-MM-DD）

function setScheduleFilter(f) {
  _scheduleFilter = f;
  _scheduleDate = null; // 切换粒度时清掉日期选择
  renderSchedule();
}

function setScheduleDate(d) {
  _scheduleDate = _scheduleDate === d ? null : d; // 再点同一天取消选择
  _scheduleFilter = 'date';
  renderSchedule();
}

async function renderSchedule() {
  const matches = await apiWithRetry('/matches');
  if (!matches.length) {
    $('#app').innerHTML = renderEmpty('📅', '暂无赛程', '赛事未开始或已结束', '#/groups', '查看小组积分');
    return;
  }

  // 计算筛选条件
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const tomorrow = new Date(now.getTime() + 86400000);
  const tomorrowStr = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth()+1).padStart(2,'0')}-${String(tomorrow.getDate()).padStart(2,'0')}`;
  const weekEnd = new Date(now.getTime() + 7 * 86400000);

  let filtered = matches;
  let emptyHint = '';
  if (_scheduleFilter === 'today') {
    filtered = matches.filter(m => m.kickoff_at.startsWith(todayStr));
    emptyHint = '今日无比赛';
  } else if (_scheduleFilter === 'tomorrow') {
    filtered = matches.filter(m => m.kickoff_at.startsWith(tomorrowStr));
    emptyHint = '明日无比赛';
  } else if (_scheduleFilter === 'week') {
    filtered = matches.filter(m => {
      const d = new Date(m.kickoff_at);
      return d >= now && d <= weekEnd;
    });
    emptyHint = '本周暂无未来比赛';
  } else if (_scheduleFilter === 'date' && _scheduleDate) {
    filtered = matches.filter(m => m.kickoff_at.startsWith(_scheduleDate));
    emptyHint = `${_scheduleDate} 无比赛`;
  }

  const byDate = {};
  filtered.forEach(m => {
    const d = fmtDate(m.kickoff_at).date;
    byDate[d] = byDate[d] || [];
    byDate[d].push(m);
  });

  // A5: 日期 chip 列表（从全部 matches 提取日期）
  const allDates = [...new Set(matches.map(m => m.kickoff_at.slice(0, 10)))].sort();

  // A4: 筛选 chip 列表
  const filterChips = [
    { key: 'today', label: '今日', count: matches.filter(m => m.kickoff_at.startsWith(todayStr)).length },
    { key: 'tomorrow', label: '明日', count: matches.filter(m => m.kickoff_at.startsWith(tomorrowStr)).length },
    { key: 'week', label: '本周', count: matches.filter(m => { const d = new Date(m.kickoff_at); return d >= now && d <= weekEnd; }).length },
    { key: 'all', label: '全部', count: matches.length },
  ];

  $('#app').innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-lg font-bold">全部赛程 <span class="text-sm text-slate-500 font-normal">（${filtered.length} 场）</span></h2>
      <button onclick="refreshCurrent()" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900">
        <span>🔄</span><span>刷新</span>
      </button>
    </div>

    <!-- A4: 粒度筛选 -->
    <div class="flex gap-2 mb-3 overflow-x-auto pb-1">
      ${filterChips.map(c => `
        <button onclick="setScheduleFilter('${c.key}')" class="px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition ${_scheduleFilter === c.key ? 'bg-emerald-500 text-slate-950 font-bold' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}">
          ${c.label} <span class="opacity-70">${c.count}</span>
        </button>
      `).join('')}
    </div>

    <!-- A5: 日期 chip 横滚 -->
    <div class="flex gap-2 mb-4 overflow-x-auto pb-2 border-b border-slate-800/50">
      ${allDates.slice(0, 30).map(d => {
        const dObj = new Date(d + 'T00:00:00');
        const wd = ['日','一','二','三','四','五','六'][dObj.getDay()];
        const isActive = _scheduleDate === d;
        const isToday = d === todayStr;
        return `
          <button onclick="setScheduleDate('${d}')" class="flex-shrink-0 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition ${isActive ? 'bg-amber-500 text-slate-950 font-bold' : isToday ? 'bg-slate-700 text-emerald-400 border border-emerald-500/40' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}">
            ${d.slice(5).replace('-', '/')} 周${wd}${isToday ? ' ·今天' : ''}
          </button>
        `;
      }).join('')}
    </div>

    ${filtered.length ? `
      <div class="space-y-5">
        ${Object.keys(byDate).map(date => `
          <div>
            <div class="sticky top-14 z-30 bg-slate-950/95 py-2 text-sm font-bold text-emerald-400 border-b border-slate-800">${date}</div>
            ${byDate[date].map(m => matchCard(m)).join('')}
          </div>
        `).join('')}
      </div>
    ` : renderEmpty('📅', emptyHint, '切换粒度或选别的日期看看', 'javascript:setScheduleFilter("all")', '查看全部赛程')}
  `;
}

async function renderGroups() {
  const groups = await apiWithRetry('/groups');
  const keys = Object.keys(groups).sort();
  if (!keys.length) {
    $('#app').innerHTML = renderEmpty('📊', '暂无积分数据', '小组赛尚未开始', '#/schedule', '查看赛程');
    return;
  }

  $('#app').innerHTML = `
    <h2 class="text-lg font-bold mb-4">小组赛积分榜 <span class="text-sm text-slate-500 font-normal">（${keys.length} 组）</span></h2>
    <div class="space-y-4">
      ${keys.map(g => `
        <div class="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <div class="bg-slate-800 px-4 py-2 text-sm font-bold text-emerald-400">${g}组</div>
          <table class="w-full text-sm">
            <thead class="text-xs text-slate-500 border-b border-slate-800">
              <tr><th class="py-2 pl-4 text-left">球队</th><th class="py-2">赛</th><th class="py-2">胜/平/负</th><th class="py-2">净胜球</th><th class="py-2 pr-4">积分</th></tr>
            </thead>
            <tbody>
              ${groups[g].map(r => `
                <tr class="border-b border-slate-800/50 last:border-0">
                  <td class="py-2 pl-4">
                    <a href="#/team/${r.team.id}" class="flex items-center gap-2">
                      <span>${r.team.flag_emoji || ''}</span>
                      <span class="truncate">${escapeHtml(r.team.name_zh)}</span>
                    </a>
                  </td>
                  <td class="py-2 text-center text-slate-400">${r.played}</td>
                  <td class="py-2 text-center text-slate-400">${r.won}/${r.drawn}/${r.lost}</td>
                  <td class="py-2 text-center text-slate-400">${r.goals_for - r.goals_against}</td>
                  <td class="py-2 pr-4 text-center font-bold text-white">${r.points}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `).join('')}
    </div>
  `;
}

// A6: 球队搜索/排序状态
let _teamsKeyword = '';
let _teamsSort = 'elo'; // 'elo' | 'fifa' | 'az' | 'group'

function setTeamsKeyword(v) {
  _teamsKeyword = (v || '').trim();
  _renderTeamsFiltered();
}

function setTeamsSort(s) {
  _teamsSort = s;
  _renderTeamsFiltered();
}

// 缓存全量球队列表
let _teamsCache = [];

// Elo 数据源切换状态
let _eloSource = 'hicruben'; // 'hicruben' | 'statsbomb'
let _eloModel = 'blend';   // v0.7.0a: 'elo' | 'glicko2' | 'blend' (默认 blend)
let _g2Open = false;       // v0.7.0a: Glicko-2 评分榜默认折叠

function setEloSource(source) {
  if (source !== 'hicruben' && source !== 'statsbomb') return;
  _eloSource = source;
  renderElo();
}

// v0.7.0a ModelBlend 入口: 1v1 预测器切模型 (直接重渲整页,简单稳定)
function setEloModel(model) {
  if (model !== 'elo' && model !== 'glicko2' && model !== 'blend') return;
  _eloModel = model;
  renderElo();
}

// v0.7.0a: 折叠/展开 Glicko-2 48 队评分榜
function toggleG2Section() {
  _g2Open = !_g2Open;
  const sec = document.getElementById('g2-ratings-section');
  const icon = document.getElementById('g2-toggle-icon');
  if (sec) sec.classList.toggle('hidden', !_g2Open);
  if (icon) icon.textContent = _g2Open ? '▼' : '▶';
}

async function renderTeams() {
  const teams = await apiWithRetry('/teams');
  if (!teams.length) {
    $('#app').innerHTML = renderEmpty('⚽', '暂无球队数据', '数据源异常或未导入', '#/', '返回首页');
    return;
  }
  _teamsCache = teams;
  _renderTeamsFiltered();
}

function _renderTeamsFiltered() {
  if (!_teamsCache.length) return;
  let teams = _teamsCache.slice();
  // 关键词过滤
  if (_teamsKeyword) {
    const kw = _teamsKeyword.toLowerCase();
    teams = teams.filter(t =>
      (t.name_zh && t.name_zh.toLowerCase().includes(kw)) ||
      (t.name_en && t.name_en.toLowerCase().includes(kw)) ||
      (t.fifa_code && t.fifa_code.toLowerCase().includes(kw)) ||
      (t.group_name && t.group_name.toLowerCase().includes(kw))
    );
  }
  // 排序
  if (_teamsSort === 'elo') {
    teams.sort((a, b) => (b.elo_rating || 0) - (a.elo_rating || 0));
  } else if (_teamsSort === 'fifa') {
    teams.sort((a, b) => (a.fifa_rank || 999) - (b.fifa_rank || 999));
  } else if (_teamsSort === 'az') {
    teams.sort((a, b) => (a.name_zh || '').localeCompare(b.name_zh || '', 'zh-CN'));
  } else if (_teamsSort === 'group') {
    teams.sort((a, b) => (a.group_name || 'Z').localeCompare(b.group_name || 'Z'));
  }

  const sortOptions = [
    { key: 'elo', label: 'Elo 降序' },
    { key: 'fifa', label: 'FIFA 升序' },
    { key: 'az', label: '名称 A-Z' },
    { key: 'group', label: '按组' },
  ];

  $('#app').innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-lg font-bold">48 支球队 <span class="text-sm text-slate-500 font-normal">（${teams.length} 队）</span></h2>
      <button onclick="refreshCurrent()" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900">
        <span>🔄</span><span>刷新</span>
      </button>
    </div>

    <!-- A6: 搜索 + 排序 -->
    <div class="flex gap-2 mb-3">
      <input id="teams-search" type="text" placeholder="🔍 搜球队名 / FIFA code / 组别"
        value="${escapeHtml(_teamsKeyword)}"
        oninput="setTeamsKeyword(this.value)"
        class="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500" />
      <select onchange="setTeamsSort(this.value)"
        class="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500 cursor-pointer">
        ${sortOptions.map(s => `<option value="${s.key}" ${_teamsSort === s.key ? 'selected' : ''}>${s.label}</option>`).join('')}
      </select>
    </div>

    ${teams.length ? `
      <div class="grid grid-cols-2 gap-3">
        ${teams.map(t => `
          <a href="#/team/${t.id}" class="bg-slate-900 rounded-xl p-3 border border-slate-800 flex items-center gap-3 hover:border-slate-700 transition">
            <span class="text-2xl">${t.flag_emoji || '🏳️'}</span>
            <div class="flex-1 min-w-0">
              <div class="font-medium truncate">${escapeHtml(t.name_zh)}</div>
              <div class="text-xs text-slate-500 truncate">${t.group_name}组 · ${t.fifa_code} · Elo ${t.elo_rating}</div>
            </div>
          </a>
        `).join('')}
      </div>
    ` : renderEmpty('🔍', '没找到匹配球队', '试试换个关键词', 'javascript:setTeamsKeyword("")', '清空搜索')}
  `;
}

function renderFactorsBreakdown(factors, home, away) {
  // F2: 可解释性面板 - 拆分 Elo/Form/H2H 三个因子的贡献
  if (!factors) return '';

  const elo = factors.elo || {};
  const form = factors.form || {};
  const h2h = factors.h2h || {};
  const lambda = factors.lambda || {};

  // Elo 差条
  const eloDiff = elo.diff || 0;
  const eloBar = Math.min(100, Math.max(0, 50 + eloDiff / 4));
  const eloColor = eloDiff > 30 ? 'bg-emerald-500' : eloDiff < -30 ? 'bg-rose-500' : 'bg-amber-500';

  // Form 差条
  const formDiff = form.diff;
  const formBar = formDiff != null ? Math.min(100, Math.max(0, 50 + formDiff * 4)) : 50;
  const formColor = formDiff == null ? 'bg-slate-600' : formDiff > 0 ? 'bg-emerald-500' : 'bg-rose-500';

  // H2H 胜负条
  const h2hTotal = (h2h.sample || 0);
  const h2hHomePct = h2hTotal > 0 ? (h2h.home_wins / h2hTotal * 100) : 0;
  const h2hAwayPct = h2hTotal > 0 ? (h2h.away_wins / h2hTotal * 100) : 0;
  const h2hDrawPct = h2hTotal > 0 ? (h2h.draws / h2hTotal * 100) : 0;
  const h2hSourceLabel = h2h.source === 'current' ? '本届' : h2h.source === 'history' ? '历史' : '无数据';

  return `
    <details class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl border border-slate-700 mb-4 overflow-hidden group" open>
      <summary class="cursor-pointer p-3 flex items-center justify-between hover:bg-slate-800/50 transition">
        <div class="flex items-center gap-2">
          <span class="text-base">⚙️</span>
          <span class="text-sm font-medium text-slate-200">为什么这么预测？</span>
        </div>
        <span class="text-slate-500 text-xs group-open:rotate-180 transition-transform">▼</span>
      </summary>

      <div class="px-4 pb-4 space-y-4 border-t border-slate-800 pt-3">
        <!-- B1: Elo 实力差距 -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs text-slate-400">🏆 Elo 实力（B1）</span>
            <span class="text-xs ${eloDiff > 0 ? 'text-emerald-400' : eloDiff < 0 ? 'text-rose-400' : 'text-slate-400'}">
              ${eloDiff > 0 ? '+' : ''}${eloDiff} 分
            </span>
          </div>
          <div class="text-xs text-slate-500 mb-1.5">
            ${escapeHtml(home.name_zh)} <span class="text-slate-300 font-mono">${elo.home_elo}</span>
            <span class="text-slate-600 mx-1">vs</span>
            ${escapeHtml(away.name_zh)} <span class="text-slate-300 font-mono">${elo.away_elo}</span>
            <span class="text-slate-600 ml-2">（含主场优势 +${elo.home_advantage || 60}）</span>
          </div>
          <div class="h-2 bg-slate-800 rounded-full overflow-hidden flex">
            <div class="${eloColor} transition-all" style="width: ${eloBar}%"></div>
            <div class="bg-slate-700" style="width: ${100 - eloBar}%"></div>
          </div>
        </div>

        <!-- B2: 近期状态 -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs text-slate-400">📈 近期状态（B2）</span>
            <span class="text-xs ${formDiff == null ? 'text-slate-500' : formDiff > 0 ? 'text-emerald-400' : 'text-rose-400'}">
              ${formDiff == null ? '数据不足' : (formDiff > 0 ? '+' : '') + formDiff + ' 分'}
            </span>
          </div>
          <div class="text-xs text-slate-500 mb-1.5">
            ${escapeHtml(home.name_zh)}：<span class="text-slate-300">${form.home_points ?? '—'}</span> 分
            <span class="text-slate-600 mx-1">vs</span>
            ${escapeHtml(away.name_zh)}：<span class="text-slate-300">${form.away_points ?? '—'}</span> 分
            <span class="text-slate-600 ml-2">（近 5 场，权重 ${(form.weight * 100).toFixed(0)}%）</span>
          </div>
          <div class="h-2 bg-slate-800 rounded-full overflow-hidden flex">
            <div class="${formColor} transition-all" style="width: ${formBar}%"></div>
            <div class="bg-slate-700" style="width: ${100 - formBar}%"></div>
          </div>
        </div>

        <!-- B3: H2H -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs text-slate-400">⚔️ 历史交锋（B3）</span>
            <span class="text-xs text-slate-500">${h2hSourceLabel} · 样本 ${h2hTotal} 场</span>
          </div>
          ${h2hTotal > 0 ? `
            <div class="text-xs text-slate-500 mb-1.5">
              ${escapeHtml(home.name_zh)} <span class="text-emerald-400">${h2h.home_wins}胜</span>
              <span class="text-slate-400">${h2h.draws}平</span>
              <span class="text-rose-400">${h2h.away_wins}负</span>
              ${escapeHtml(away.name_zh)}
            </div>
            <div class="h-2 bg-slate-800 rounded-full overflow-hidden flex">
              <div class="bg-emerald-500" style="width: ${h2hHomePct}%"></div>
              <div class="bg-slate-600" style="width: ${h2hDrawPct}%"></div>
              <div class="bg-rose-500" style="width: ${h2hAwayPct}%"></div>
            </div>
          ` : `
            <div class="text-xs text-slate-500">两队无历史交锋数据</div>
          `}
        </div>

        <!-- 模型参数 -->
        <div class="pt-2 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500">
          <span>模型：Elo-Poisson v1</span>
          <span>λ(H) = ${lambda.home} | λ(A) = ${lambda.away} | base = ${lambda.base}</span>
        </div>
      </div>
    </details>
  `;
}

async function renderTeamDetail(id) {
  let team, matches;
  try {
    [team, matches] = await Promise.all([
      apiWithRetry('/teams/' + id),
      apiWithRetry('/teams/' + id + '/matches'),
    ]);
  } catch (err) {
    $('#app').innerHTML = renderError(err, () => renderTeamDetail(id));
    return;
  }
  $('#app').innerHTML = `
    <!-- A3: 返回按钮 -->
    <div class="mb-3">
      <a href="#/teams" class="text-sm text-slate-400 hover:text-emerald-400 transition flex items-center gap-1">
        <span>←</span><span>返回 48 球队</span>
      </a>
    </div>

    <div class="bg-slate-900 rounded-xl p-6 mb-4 border border-slate-800 text-center">
      <div class="text-5xl mb-2">${team.flag_emoji || '🏳️'}</div>
      <h1 class="text-2xl font-bold">${escapeHtml(team.name_zh)}</h1>
      <div class="text-slate-400 mt-1">${escapeHtml(team.name_en)} · ${team.fifa_code} · ${team.group_name}组</div>
      <div class="mt-3 text-sm text-slate-500">Elo ${team.elo_rating} · FIFA 排名 ${team.fifa_rank || '待定'}</div>
    </div>
    <h2 class="text-lg font-bold mb-3">赛程（${matches.length} 场）</h2>
    ${matches.length ? matches.map(m => matchCard(m)).join('') : renderEmpty('📅', '暂无比赛', '该球队暂未安排比赛', '#/schedule', '查看全部赛程')}
  `;
}

// ============ v0.5.1: 赔率走势图表 ============
// Chart.js instance cache (single chart at a time)
let _oddsTrendChart = null;

async function loadOddsTrend(matchId) {
  // v0.5.1 加载赔率走势(Chart.js 折线图)
  // matchId: 比赛 ID
  // Side effects:
  //   - 在 #odds-trend-chart canvas 渲染 Chart.js line chart
  //   - 三个 tab(主胜/平/客胜)切换 dataset
  try {
    const data = await api(`/matches/${matchId}/odds/history`);
    if (!data || !data.has_history) {
      document.getElementById('odds-trend-empty').classList.remove('hidden');
      document.getElementById('odds-trend-chart-wrapper').classList.add('hidden');
      return;
    }
    document.getElementById('odds-trend-empty').classList.add('hidden');
    document.getElementById('odds-trend-chart-wrapper').classList.remove('hidden');

    // 配色:每个 bookmaker 一种颜色
    const palette = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4'];
    const bookmakers = data.bookmakers;
    const labels = [];  // X 轴:所有时间戳(去重排序)
    const labelSet = new Set();
    for (const bm of bookmakers) {
      for (const pt of (data.series[bm] || [])) {
        if (pt.t) labelSet.add(pt.t);
      }
    }
    labels.push(...Array.from(labelSet).sort());
    const labelFmt = labels.map(t => {
      const d = new Date(t);
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
    });

    // 三种 metric 的 datasets(主胜 / 平 / 客胜)
    const buildDatasets = (metric) => bookmakers.map((bm, idx) => {
      const pts = data.series[bm] || [];
      const byT = {};
      pts.forEach(p => { byT[p.t] = p[metric]; });
      return {
        label: bm,
        data: labels.map(t => byT[t] ?? null),
        borderColor: palette[idx % palette.length],
        backgroundColor: palette[idx % palette.length] + '22',
        tension: 0.25,
        spanGaps: true,
        pointRadius: 3,
        pointHoverRadius: 5,
      };
    });

    // 销毁旧 chart
    if (_oddsTrendChart) _oddsTrendChart.destroy();

    const ctx = document.getElementById('odds-trend-chart').getContext('2d');
    _oddsTrendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labelFmt,
        datasets: buildDatasets('home_win'),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {
          legend: {position: 'bottom', labels: {color: '#cbd5e1', boxWidth: 12}},
          tooltip: {callbacks: {label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) : '-'}`}},
        },
        scales: {
          y: {title: {display: true, text: '赔率(decimal)', color: '#94a3b8'}, ticks: {color: '#94a3b8'}, grid: {color: '#1e293b'}},
          x: {ticks: {color: '#94a3b8', maxRotation: 45, minRotation: 0}, grid: {color: '#1e293b'}},
        },
      },
    });

    // 切换 tab
    document.querySelectorAll('.odds-trend-tab').forEach(tab => {
      tab.onclick = () => {
        document.querySelectorAll('.odds-trend-tab').forEach(t => {
          t.classList.remove('bg-cyan-500', 'text-white');
          t.classList.add('bg-slate-800', 'text-slate-400');
        });
        tab.classList.remove('bg-slate-800', 'text-slate-400');
        tab.classList.add('bg-cyan-500', 'text-white');
        const metric = tab.dataset.metric;
        const metricLabel = {home_win: '主胜', draw: '平', away_win: '客胜'}[metric];
        _oddsTrendChart.data.datasets = buildDatasets(metric);
        _oddsTrendChart.options.scales.y.title.text = `赔率(decimal) · ${metricLabel}`;
        _oddsTrendChart.update();
      };
    });
  } catch (err) {
    console.error('[odds-trend] 加载失败:', err);
    document.getElementById('odds-trend-empty').classList.remove('hidden');
    document.getElementById('odds-trend-empty').textContent = '加载赔率走势失败: ' + (err.message || err);
  }
}

function renderOddsTrendCard() {
  // v0.5.1 返回赔率走势卡片 HTML(主胜/平/客胜 tab + canvas)
  // 占位符,渲染后由 loadOddsTrend(matchId) 填充
  return `
    <div class="bg-slate-900 rounded-xl p-4 border border-slate-800 mb-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-bold text-cyan-400">📈 赔率走势 · 多公司时序</h3>
        <div class="text-xs text-slate-500">v0.5.1</div>
      </div>
      <div id="odds-trend-empty" class="text-sm text-slate-500 hidden">暂无赔率快照(可能尚未录入赔率或 6h 调度器尚未运行)</div>
      <div id="odds-trend-chart-wrapper" class="hidden">
        <div class="flex gap-1 mb-3">
          <button class="odds-trend-tab px-3 py-1 text-xs rounded bg-cyan-500 text-white" data-metric="home_win">主胜</button>
          <button class="odds-trend-tab px-3 py-1 text-xs rounded bg-slate-800 text-slate-400" data-metric="draw">平</button>
          <button class="odds-trend-tab px-3 py-1 text-xs rounded bg-slate-800 text-slate-400" data-metric="away_win">客胜</button>
        </div>
        <div style="position: relative; height: 240px;">
          <canvas id="odds-trend-chart"></canvas>
        </div>
        <div class="text-[10px] text-slate-500 mt-2">数据来源:OddsSnapshot(每 6h 自动打点 + 管理员录入时记录)</div>
      </div>
    </div>
  `;
}

async function renderMatchDetail(id) {
  // A7: 同时拉全部比赛列表算上一场/下一场
  const [m, prediction, weather, allMatches, oddsData] = await Promise.all([
    apiWithRetry('/matches/' + id).catch(err => { throw err; }),
    api('/matches/' + id + '/prediction').catch(() => null),
    api('/matches/' + id + '/weather').catch(() => null),
    api('/matches?limit=200').catch(() => []),
    api('/matches/' + id + '/odds').catch(() => null),
  ]);
  // 算邻居（按 match_number 排序）
  const sorted = (allMatches || []).slice().sort((a, b) => (a.match_number || 0) - (b.match_number || 0));
  const idx = sorted.findIndex(x => String(x.id) === String(id));
  const prev = idx > 0 ? sorted[idx - 1] : null;
  const next = idx >= 0 && idx < sorted.length - 1 ? sorted[idx + 1] : null;
  const positionLabel = idx >= 0 ? `#${idx + 1} / ${sorted.length}` : '';

  const { time, date } = fmtDate(m.kickoff_at);
  const home = m.home_team || { name_zh: m.home_team_placeholder || '待定', flag_emoji: '' };
  const away = m.away_team || { name_zh: m.away_team_placeholder || '待定', flag_emoji: '' };

  const predHtml = prediction ? `
    <div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-4 border border-slate-700 mb-4">
      <div class="flex justify-between items-center mb-3">
        <h3 class="font-bold text-amber-400">AI 预测 v1 · Elo-Poisson</h3>
        <span class="text-xs text-slate-400">推荐比分 ${prediction.recommended_score}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-center mb-3">
        <div class="bg-slate-950 rounded p-2"><div class="text-xs text-slate-500">主胜</div><div class="text-lg font-bold text-white">${prediction.home_win_prob}%</div></div>
        <div class="bg-slate-950 rounded p-2"><div class="text-xs text-slate-500">平</div><div class="text-lg font-bold text-white">${prediction.draw_prob}%</div></div>
        <div class="bg-slate-950 rounded p-2"><div class="text-xs text-slate-500">客胜</div><div class="text-lg font-bold text-white">${prediction.away_win_prob}%</div></div>
      </div>
      <div class="text-sm text-slate-300 mb-2">星级：${'★'.repeat(prediction.stars)}${'☆'.repeat(5 - prediction.stars)}</div>
      <ul class="text-xs text-slate-400 space-y-1 mb-2">
        ${prediction.reasons.map(r => '<li>· ' + escapeHtml(r) + '</li>').join('')}
      </ul>
      <div class="mt-2 text-xs text-slate-500">${prediction.disclaimer}</div>
    </div>

    ${prediction.home_recent_form || prediction.away_recent_form || prediction.h2h_summary ? `
    <div class="grid grid-cols-2 gap-2 mb-4">
      ${prediction.home_recent_form || prediction.away_recent_form ? `
        <div class="bg-slate-900 rounded-xl p-3 border border-slate-800">
          <div class="text-xs text-slate-500 mb-2">📈 近期状态</div>
          <div class="text-sm">
            <div class="text-slate-300">${escapeHtml(home.name_zh)}：<span class="${prediction.home_recent_form ? 'text-emerald-400 font-bold' : 'text-slate-500'}">${prediction.home_recent_form || '暂无数据'}</span></div>
            <div class="text-slate-300 mt-1">${escapeHtml(away.name_zh)}：<span class="${prediction.away_recent_form ? 'text-emerald-400 font-bold' : 'text-slate-500'}">${prediction.away_recent_form || '暂无数据'}</span></div>
          </div>
        </div>
      ` : '<div></div>'}
      ${prediction.h2h_summary ? `
        <div class="bg-slate-900 rounded-xl p-3 border border-slate-800">
          <div class="flex items-center justify-between mb-2">
            <div class="text-xs text-slate-500">⚔️ 历史交锋</div>
            <a href="#/h2h/${home.fifa_code}/${away.fifa_code}" class="text-xs text-amber-400 hover:text-amber-300 transition">📜 完整历史 →</a>
          </div>
          <div class="text-sm text-amber-300">${escapeHtml(prediction.h2h_summary)}</div>
          ${prediction.h2h_record ? `<div class="text-xs text-slate-500 mt-1">样本 ${prediction.h2h_record.sample} 场</div>` : ''}
        </div>
      ` : '<div></div>'}
    </div>
    ` : ''}

    ${prediction.factors_breakdown ? renderFactorsBreakdown(prediction.factors_breakdown, home, away) : ''}
  ` : '';

  const weatherHtml = weather && weather.available ? `
    <div class="bg-slate-900 rounded-xl p-3 border border-slate-800 mb-4 flex items-center justify-between">
      <div>
        <div class="text-xs text-slate-500 mb-1">🌤️ ${escapeHtml(weather.stadium)} 当日天气</div>
        <div class="text-sm">
          <span class="font-bold text-white">${weather.temperature != null ? weather.temperature.toFixed(1) + '°C' : '-'}</span>
          <span class="text-slate-400 mx-2">·</span>
          <span class="text-slate-300">${weather.label}</span>
          ${weather.precipitation > 0 ? `<span class="text-blue-400 ml-2">降水 ${weather.precipitation}mm</span>` : ''}
        </div>
      </div>
      <div class="text-xs text-slate-500">${weather.windspeed != null ? '💨 ' + weather.windspeed.toFixed(0) + 'km/h' : ''}</div>
    </div>
  ` : '';

  // 赛后 24h 复盘卡片 (B4)
  const reviewHtml = m.status === 'finished' ? renderPostMatchReview(m, prediction) : '';

  $('#app').innerHTML = `
    <!-- A3: 返回按钮 -->
    <div class="flex items-center justify-between mb-4">
      <a href="#/schedule" class="text-sm text-slate-400 hover:text-emerald-400 transition flex items-center gap-1">
        <span>←</span><span>返回赛程</span>
      </a>
      <span class="text-xs text-slate-500">${positionLabel}</span>
    </div>

    <div class="bg-slate-900 rounded-xl p-6 mb-4 border border-slate-800 text-center">
      <div class="text-xs text-slate-500 mb-3">${date} ${time} · ${m.stadium ? escapeHtml(m.stadium.name_en) : ''}</div>
      <div class="flex items-center justify-between">
        <div class="flex-1">
          <div class="text-4xl mb-2">${home.flag_emoji || '🏳️'}</div>
          <div class="font-bold text-lg">${escapeHtml(home.name_zh)}</div>
        </div>
        <div class="px-4">
          ${renderMatchScore(m)}
          <div class="mt-2">${statusBadge(m.status)}</div>
        </div>
        <div class="flex-1">
          <div class="text-4xl mb-2">${away.flag_emoji || '🏳️'}</div>
          <div class="font-bold text-lg">${escapeHtml(away.name_zh)}</div>
        </div>
      </div>
      <div class="mt-4 text-xs text-slate-500">数据来源：${m.data_source} · 更新于 ${new Date(m.last_updated_at).toLocaleString('zh-CN')}</div>
    </div>

    ${predHtml}
    ${weatherHtml}
    ${renderOddsDetail(oddsData, home.name_zh, away.name_zh)}
    ${renderOddsTrendCard()}
    ${reviewHtml}

    <div class="bg-slate-900 rounded-xl p-4 border border-slate-800 mb-4">
      <h3 class="font-bold mb-2">比赛事件</h3>
      ${renderEvents(m.events || [], m)}
    </div>

    <div class="bg-slate-900 rounded-xl p-4 border border-slate-800">
      <h3 class="font-bold mb-2">赛后统计</h3>
      ${renderStats(m.stats || [], m)}
    </div>

    <!-- A7: 上一场 / 下一场 -->
    <div class="mt-6 grid grid-cols-2 gap-3">
      ${prev ? `
        <a href="#/match/${prev.id}" class="bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl p-3 transition flex items-center gap-2 group">
          <span class="text-slate-500 group-hover:text-emerald-400 text-lg">←</span>
          <div class="flex-1 min-w-0">
            <div class="text-xs text-slate-500">上一场 #${prev.match_number}</div>
            <div class="text-sm truncate">${escapeHtml((prev.home_team && prev.home_team.name_zh) || '待定')} vs ${escapeHtml((prev.away_team && prev.away_team.name_zh) || '待定')}</div>
          </div>
        </a>
      ` : '<div></div>'}
      ${next ? `
        <a href="#/match/${next.id}" class="bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl p-3 transition flex items-center gap-2 group">
          <div class="flex-1 min-w-0 text-right">
            <div class="text-xs text-slate-500">下一场 #${next.match_number}</div>
            <div class="text-sm truncate">${escapeHtml((next.home_team && next.home_team.name_zh) || '待定')} vs ${escapeHtml((next.away_team && next.away_team.name_zh) || '待定')}</div>
          </div>
          <span class="text-slate-500 group-hover:text-emerald-400 text-lg">→</span>
        </a>
      ` : '<div></div>'}
    </div>
  `;

  // 赛前 10 分钟请求 PWA 缓存这场比赛的详情
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: 'PRECACHE_MATCH',
      matchId: id,
    });
  }

  // v0.5.1: 加载赔率走势图(异步,Chart.js 渲染)
  loadOddsTrend(id);
}


function renderPostMatchReview(m, prediction) {
  // B4: 赛后 24h 复盘卡片——对比预测 vs 实际
  if (!prediction) return '';
  const actualHome = m.home_score;
  const actualAway = m.away_score;
  if (actualHome == null || actualAway == null) return '';

  const [pHome, pAway] = prediction.recommended_score.split(':').map(Number);
  if (isNaN(pHome) || isNaN(pAway)) return '';

  // 比分命中 = 推荐比分 == 实际比分
  const exactHit = pHome === actualHome && pAway === actualAway;
  // 胜负命中 = 主胜/平/客胜方向命中
  let outcomeHit = 'unknown';
  if (actualHome > actualAway) outcomeHit = 'home';
  else if (actualHome < actualAway) outcomeHit = 'away';
  else outcomeHit = 'draw';
  let predOutcome = 'unknown';
  if (prediction.home_win_prob > prediction.draw_prob && prediction.home_win_prob > prediction.away_win_prob) predOutcome = 'home';
  else if (prediction.away_win_prob > prediction.draw_prob) predOutcome = 'away';
  else predOutcome = 'draw';
  const directionHit = predOutcome === outcomeHit;

  const verdict = exactHit
    ? { color: 'emerald', label: '🎯 比分命中', desc: '推荐比分与实际完全一致' }
    : directionHit
    ? { color: 'amber', label: '✓ 方向命中', desc: '胜负方向正确，比分略有偏差' }
    : { color: 'red', label: '✗ 偏离', desc: '胜负方向判断错误' };

  const actualGoals = actualHome + actualAway;
  const predGoals = pHome + pAway;
  const goalsDiff = actualGoals - predGoals;

  return `
    <div class="bg-gradient-to-br from-${verdict.color}-500/10 to-slate-900 rounded-xl p-4 border border-${verdict.color}-500/30 mb-4">
      <div class="flex justify-between items-center mb-3">
        <h3 class="font-bold text-${verdict.color}-300">📋 赛后复盘</h3>
        <span class="text-xs px-2 py-1 rounded bg-${verdict.color}-500/20 text-${verdict.color}-300">${verdict.label}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-center mb-3 text-sm">
        <div>
          <div class="text-xs text-slate-500">预测比分</div>
          <div class="font-bold text-white">${prediction.recommended_score}</div>
        </div>
        <div>
          <div class="text-xs text-slate-500">实际比分</div>
          <div class="font-bold text-white">${actualHome}:${actualAway}</div>
        </div>
        <div>
          <div class="text-xs text-slate-500">进球差</div>
          <div class="font-bold ${goalsDiff === 0 ? 'text-emerald-400' : goalsDiff > 0 ? 'text-amber-400' : 'text-slate-400'}">${goalsDiff > 0 ? '+' : ''}${goalsDiff}</div>
        </div>
      </div>
      <div class="text-xs text-slate-300 mb-2">${verdict.desc}</div>
      <div class="text-xs text-slate-500 space-y-1">
        <div>· 模型预测主胜 ${prediction.home_win_prob}%，实际${outcomeHit === 'home' ? '主胜' : outcomeHit === 'draw' ? '平局' : '客胜'}</div>
        <div>· 总进球 ${actualGoals} (预测 ${predGoals}) ${goalsDiff > 0 ? '比预测更开放' : goalsDiff < 0 ? '比预测更保守' : '符合预期'}</div>
        <div>· v0 模型仅基于 Elo；B1-B4 升级后将引入近期状态、历史交锋等</div>
      </div>
    </div>
  `;
}

function renderEvents(events, match) {
  if (!events.length) {
    return '<p class="text-sm text-slate-500">暂无事件数据。自动源失效时可通过后台手动录入。</p>';
  }
  return '<ul class="text-sm divide-y divide-slate-800">' + events.map(ev => {
    const team = ev.team_id === match.home_team?.id ? match.home_team : match.away_team;
    const teamFlag = team?.flag_emoji || '🏳️';
    const teamName = team?.name_zh || '未知队';
    const icon = { goal: '⚽', yellow_card: '🟨', red_card: '🟥', substitution: '🔁' }[ev.event_type] || '•';
    const typeLabel = { goal: '进球', yellow_card: '黄牌', red_card: '红牌', substitution: '换人' }[ev.event_type] || ev.event_type;
    return `<li class="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
      <span class="text-amber-400 font-mono w-8 text-right text-sm">${ev.minute}'</span>
      <span class="text-lg">${icon}</span>
      <div class="flex-1 min-w-0">
        <div class="font-medium truncate">${escapeHtml(ev.player_name) || typeLabel}</div>
        <div class="text-xs text-slate-500">${teamFlag} ${escapeHtml(teamName)} · ${typeLabel}${ev.extra_info ? ' · ' + escapeHtml(ev.extra_info) : ''}</div>
      </div>
    </li>`;
  }).join('') + '</ul>';
}

function renderStats(stats, match) {
  if (!stats.length) {
    return '<p class="text-sm text-slate-500">暂无赛后统计数据（自动源未提供，可后台手工补录）。</p>';
  }
  const homeStat = stats.find(s => s.team_id === match.home_team?.id);
  const awayStat = stats.find(s => s.team_id === match.away_team?.id);
  if (!homeStat || !awayStat) {
    return '<p class="text-sm text-slate-500">数据不完整。</p>';
  }
  const rows = [
    ['控球率', homeStat.possession, awayStat.possession, '%'],
    ['射门', homeStat.shots, awayStat.shots, ''],
    ['射正', homeStat.shots_on_target, awayStat.shots_on_target, ''],
    ['角球', homeStat.corners, awayStat.corners, ''],
    ['犯规', homeStat.fouls, awayStat.fouls, ''],
    ['黄牌', homeStat.yellow_cards, awayStat.yellow_cards, ''],
    ['红牌', homeStat.red_cards, awayStat.red_cards, ''],
  ];
  return '<div class="space-y-2">' + rows.map(([label, h, a, unit]) =>
    '<div class="grid grid-cols-3 items-center text-sm">' +
    '<span class="text-right text-slate-300">' + (h ?? '-') + unit + '</span>' +
    '<span class="text-center text-xs text-slate-500">' + label + '</span>' +
    '<span class="text-left text-slate-300">' + (a ?? '-') + unit + '</span>' +
    '</div>'
  ).join('') + '</div>';
}

async function renderSimulator() {
  const data = await apiWithRetry('/simulator/groups');
  if (!data.groups || !data.groups.length) {
    $('#app').innerHTML = renderEmpty('🎲', '暂无模拟数据', '小组赛尚未开打，无法推演', '#/schedule', '查看赛程');
    return;
  }
  $('#app').innerHTML = `
    <h2 class="text-lg font-bold mb-2 flex items-center gap-2">
      <span class="w-1 h-5 bg-violet-400 rounded"></span>出线模拟器 v0
    </h2>
    <p class="text-xs text-slate-400 mb-4">基于当前积分 + 剩余赛程 + Elo-Poisson 模型，运行 ${data.simulations} 次蒙特卡洛模拟。每组前 2 名 + 8 个最佳第 3 名（共 32 队）晋级淘汰赛。</p>
    <div class="space-y-4">
      ${data.groups.map(g => `
        <div class="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <div class="bg-gradient-to-r from-violet-600/30 to-emerald-500/20 px-4 py-2 flex items-center justify-between">
            <span class="text-sm font-bold text-white">${g.group_name} 组</span>
            <span class="text-xs text-slate-300">${g.teams.length} 队</span>
          </div>
          <div class="divide-y divide-slate-800">
            ${g.teams.map((t, i) => `
              <div class="px-4 py-2.5 flex items-center gap-3">
                <span class="text-xs text-slate-500 w-4">${i + 1}</span>
                <span class="text-lg">${t.flag_emoji || '🏳️'}</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium truncate">${escapeHtml(t.team_name)}</div>
                  <div class="text-xs text-slate-500">${t.points}分 · 净胜球 ${t.goal_diff > 0 ? '+' : ''}${t.goal_diff}</div>
                </div>
                <div class="flex items-center gap-1">
                  <div class="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-emerald-400 to-amber-300" style="width: ${t.advance_overall_prob}%"></div>
                  </div>
                  <span class="text-xs font-bold text-emerald-300 w-12 text-right">${t.advance_overall_prob}%</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('')}
    </div>

    <!-- v0.7.1 Monte Carlo Tournament 全模拟 -->
    <div class="mt-8 p-4 bg-gradient-to-br from-amber-900/20 to-rose-900/20 rounded-xl border border-amber-500/30">
      <h3 class="text-base font-bold mb-2 flex items-center gap-2">
        <span class="w-1 h-5 bg-amber-400 rounded"></span>
        <span>🏆 整届模拟 v0.7.1</span>
        <span class="text-xs text-slate-400 font-normal ml-2">Monte Carlo · 整届 10000 次</span>
      </h3>
      <p class="text-xs text-slate-400 mb-3">从组赛到决赛跑完所有 103 场比赛,统计每队 <b>夺冠 / 决赛 / 4 强 / 8 强 / 16 强</b> 概率 + 决赛对阵频次。</p>
      <button id="mc-run-btn" onclick="runMonteCarlo()" class="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-amber-500 to-rose-500 hover:from-amber-400 hover:to-rose-400 text-white text-sm font-bold rounded-lg shadow-lg transition">
        🎲 运行 Monte Carlo (10000 次)
      </button>
      <div id="mc-result" class="mt-4"></div>
    </div>

    <div class="mt-6 p-3 bg-slate-900 rounded-lg text-xs text-slate-500 border border-slate-800">
      <div class="font-bold text-slate-400 mb-1">图例</div>
      <div>· 进度条长度 = 出线概率（直接晋级 + 最佳第 3 名）</div>
      <div>· 模拟方法：剩余比赛按 Elo-Poisson 随机生成比分,统计每队晋级次数</div>
      <div>· 数据有限,模型仅作参考。Elo 初始值来自 FIFA 排名近似（B1 升级后将用 StatsBomb 训练）</div>
    </div>
  `;
}


// v0.7.1 Monte Carlo 全模拟 (整届)
async function runMonteCarlo(simulations = 10000) {
  const btn = document.getElementById('mc-run-btn');
  const out = document.getElementById('mc-result');
  if (!out) return;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 模拟中...'; }
  out.innerHTML = '<div class="text-xs text-slate-400 py-4 text-center"><span class="inline-block animate-spin">⏳</span> 正在运行 ' + simulations + ' 次整届模拟,大约 4-10 秒...</div>';

  try {
    const resp = await fetch('/api/simulator/tournament?simulations=' + simulations + '&model=blend&seed=42');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    renderMonteCarloResult(data);
  } catch (e) {
    out.innerHTML = '<div class="text-xs text-rose-400 py-3">❌ 模拟失败: ' + escapeHtml(String(e)) + '</div>';
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '🎲 运行 Monte Carlo (10000 次)'; }
  }
}

function renderMonteCarloResult(data) {
  const out = document.getElementById('mc-result');
  if (!out) return;
  const champ = data.champion_distribution || {};
  const finalList = data.top_final_matchups || [];
  const champEntries = Object.entries(champ).slice(0, 8);
  const maxProb = champEntries.length ? champEntries[0][1] : 0.01;

  out.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- 冠军榜 -->
      <div class="bg-slate-900 rounded-lg p-3 border border-amber-500/20">
        <h4 class="text-sm font-bold text-amber-300 mb-2 flex items-center gap-2">
          <span>🏆</span><span>夺冠概率 Top 8</span>
        </h4>
        <div class="space-y-1.5">
          ${champEntries.map(([code, p], i) => `
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-500 w-4 text-right">${i + 1}</span>
              <span class="text-sm font-mono w-10">${code}</span>
              <div class="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
                <div class="h-full bg-gradient-to-r from-amber-400 to-rose-400" style="width: ${(p / maxProb * 100).toFixed(1)}%"></div>
              </div>
              <span class="text-xs font-bold text-amber-200 w-12 text-right">${(p * 100).toFixed(1)}%</span>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- 决赛对阵 -->
      <div class="bg-slate-900 rounded-lg p-3 border border-rose-500/20">
        <h4 class="text-sm font-bold text-rose-300 mb-2 flex items-center gap-2">
          <span>🥊</span><span>决赛对阵 Top ${Math.min(5, finalList.length)}</span>
        </h4>
        <div class="space-y-1.5">
          ${finalList.slice(0, 5).map((m, i) => `
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-500 w-4 text-right">${i + 1}</span>
              <span class="text-sm font-mono">${m.home} <span class="text-slate-600">vs</span> ${m.away}</span>
              <span class="text-xs text-slate-500 ml-auto">${(m.prob * 100).toFixed(1)}%</span>
            </div>
          `).join('') || '<div class="text-xs text-slate-500">暂无数据</div>'}
        </div>
      </div>
    </div>

    <!-- 元信息 -->
    <div class="mt-3 text-[10px] text-slate-500 flex items-center gap-3 flex-wrap">
      <span>模型: <b class="text-slate-300">${data.model}</b></span>
      <span>模拟: <b class="text-slate-300">${data.n_sims}</b> 次</span>
      <span>耗时: <b class="text-slate-300">${data.duration_seconds}s</b></span>
      <span>球队: <b class="text-slate-300">${data.n_teams}</b></span>
    </div>
  `;
}


// ============================================================
// 🎛 总览驾驶舱 Cockpit (PC + 横屏优化)
// ============================================================

/** 把 ISO 字符串（球场本地 wall-clock）+ IANA 时区转北京时间字符串 */
function fmtBeijingFromTZ(isoWallClock, tz, withDate) {
  try {
    // 1. 把 wall-clock 字符串解析成"该时区的本地时间"
    //    用 Intl.DateTimeFormat 把 wall-clock 重新格式化成带时区后缀
    const [datePart, timePart] = isoWallClock.split('T');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [h, mi, s = 0] = (timePart || '00:00:00').split(':').map(Number);
    // 2. 用时区反推 UTC 毫秒：构造一个 Date 当作 UTC，然后用时区偏移修正
    const fakeUTC = Date.UTC(y, mo - 1, d, h, mi, s);
    // 取该时区在那一分钟的 offset（分钟数）
    const tzFmt = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
    const parts = Object.fromEntries(tzFmt.formatToParts(new Date(fakeUTC)).map(p => [p.type, p.value]));
    const tzAsUTC = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second)
    );
    const offsetMs = tzAsUTC - fakeUTC; // 该时区当时的 offset (ms)
    const realUTCms = fakeUTC - offsetMs;
    // 3. 转北京时间 (UTC+8)
    const beijingMs = realUTCms + 8 * 3600 * 1000;
    const bj = new Date(beijingMs);
    const pad = n => String(n).padStart(2, '0');
    const m = bj.getUTCMonth() + 1;
    const day = bj.getUTCDate();
    const hh = bj.getUTCHours();
    const mm = bj.getUTCMinutes();
    if (withDate) {
      return `${bj.getUTCFullYear()}-${pad(m)}-${pad(day)} ${pad(hh)}:${pad(mm)}`;
    }
    return `${pad(hh)}:${pad(mm)}`;
  } catch (e) {
    return isoWallClock.slice(11, 16) || '--:--';
  }
}

function beijingNowString() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 距离开赛还有多久（返回中文短串） */
function countdownText(isoWallClock, tz) {
  try {
    const [datePart, timePart] = isoWallClock.split('T');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [h, mi, s = 0] = (timePart || '00:00:00').split(':').map(Number);
    const fakeUTC = Date.UTC(y, mo - 1, d, h, mi, s);
    const tzFmt = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
    const parts = Object.fromEntries(tzFmt.formatToParts(new Date(fakeUTC)).map(p => [p.type, p.value]));
    const tzAsUTC = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second)
    );
    const offsetMs = tzAsUTC - fakeUTC;
    const realUTCms = fakeUTC - offsetMs;
    const now = Date.now();
    const diffMs = realUTCms - now;
    if (diffMs < -2 * 3600 * 1000) return '已结束';
    if (diffMs < 0) return '进行中';
    const days = Math.floor(diffMs / 86400000);
    const hours = Math.floor((diffMs % 86400000) / 3600000);
    const mins = Math.floor((diffMs % 3600000) / 60000);
    if (days > 0) return `${days}天${hours}时后`;
    if (hours > 0) return `${hours}时${mins}分后`;
    return `${mins}分钟后`;
  } catch (e) {
    return '';
  }
}

// ---------- M3 赔率页面 ----------
async function renderOdds() {
  const [data, latest] = await Promise.all([
    apiWithRetry('/odds/compare?limit=30'),
    apiWithRetry('/odds/latest').catch(() => null),
  ]);
  if (!data || !data.items || !data.items.length) {
    $('#app').innerHTML = renderEmpty('💰', '暂无赔率数据', '管理员尚未录入任何比赛赔率', '#/schedule', '查看赛程');
    return;
  }

  // 数据更新提示 (v0.6.0)
  const freshness = latest && latest.minutes_ago != null ? (() => {
    const m = latest.minutes_ago;
    if (m < 1) return '<span class="text-emerald-400">刚刚</span>';
    if (m < 60) return `<span class="text-emerald-400">${Math.round(m)} 分钟前</span>`;
    if (m < 60 * 6) return `<span class="text-amber-400">${(m / 60).toFixed(1)} 小时前</span>`;
    return `<span class="text-rose-400">${(m / 60).toFixed(1)} 小时前</span>`;
  })() : '<span class="text-slate-500">未知</span>';
  const freshnessHtml = `<div class="text-xs text-slate-400 flex items-center gap-1">
    <span class="inline-block w-1.5 h-1.5 rounded-full ${latest && latest.minutes_ago != null && latest.minutes_ago < 360 ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}"></span>
    数据更新于 ${freshness}${latest ? ` · 共 ${latest.snapshot_count} 个快照` : ''}
  </div>`;

  // 顶部 value bet 提醒卡片
  const valueBets = data.items.filter(it => it.best_value && it.best_value_rate >= 0.05);
  const valueBetsHtml = valueBets.length > 0 ? `
    <div class="bg-gradient-to-br from-amber-900/30 to-slate-900 rounded-xl p-4 border border-amber-700/50 mb-4">
      <div class="flex items-center gap-2 mb-3">
        <span class="text-2xl">💎</span>
        <h3 class="font-bold text-amber-400">价值投注 TOP ${valueBets.length}</h3>
      </div>
      <div class="text-xs text-slate-400 mb-2">Elo 模型 vs 市场隐含概率,差异 ≥ 5%</div>
      <div class="space-y-2">
        ${valueBets.slice(0, 5).map(it => `
          <a href="#/match/${it.match_id}" class="block bg-slate-900 rounded-lg p-3 hover:bg-slate-800 transition">
            <div class="flex items-center justify-between mb-1">
              <span class="text-sm font-medium">${escapeHtml(it.home_team.name_zh)} <span class="text-slate-500">vs</span> ${escapeHtml(it.away_team.name_zh)}</span>
              <span class="text-emerald-400 font-mono text-sm">+${(it.best_value_rate * 100).toFixed(1)}%</span>
            </div>
            <div class="text-xs text-slate-400">
              模型看 <span class="text-amber-400">${it.best_value === 'home' ? '主胜' : it.best_value === 'draw' ? '平局' : '客胜'}</span>
              ${(it.elo[it.best_value + '_prob'] * 100).toFixed(1)}%
              · 市场 ${(it.market[it.best_value + '_prob'] * 100).toFixed(1)}%
            </div>
          </a>
        `).join('')}
      </div>
    </div>
  ` : '';

  const itemsHtml = data.items.map(it => {
    const vbHome = it.value_bet.home;
    const vbDraw = it.value_bet.draw;
    const vbAway = it.value_bet.away;
    const fmtVb = (v) => {
      if (v >= 0.05) return `<span class="text-emerald-400 font-mono">+${(v * 100).toFixed(1)}%</span>`;
      if (v >= 0) return `<span class="text-slate-400 font-mono">+${(v * 100).toFixed(1)}%</span>`;
      return `<span class="text-rose-400 font-mono">${(v * 100).toFixed(1)}%</span>`;
    };
    return `
      <a href="#/match/${it.match_id}" class="block bg-slate-900 rounded-xl p-4 mb-3 border border-slate-800 hover:border-cyan-700 transition">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs text-slate-500">${escapeHtml(it.stage)}${it.group_name ? ' · ' + it.group_name + '组' : ''}</span>
          ${it.best_value && it.best_value_rate >= 0.05 ? '<span class="text-xs bg-amber-900/50 text-amber-300 px-2 py-0.5 rounded">💎 VALUE BET</span>' : ''}
        </div>
        <div class="flex items-center justify-between mb-2">
          <span class="font-medium text-sm">${escapeHtml(it.home_team.name_zh)}</span>
          <span class="text-xs text-slate-500">VS</span>
          <span class="font-medium text-sm">${escapeHtml(it.away_team.name_zh)}</span>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center text-xs">
          <div class="bg-slate-950 rounded p-2">
            <div class="text-slate-500">主胜</div>
            <div class="text-slate-300">${(it.market.home_prob * 100).toFixed(0)}%</div>
            <div class="text-cyan-400">${fmtVb(vbHome)}</div>
          </div>
          <div class="bg-slate-950 rounded p-2">
            <div class="text-slate-500">平</div>
            <div class="text-slate-300">${(it.market.draw_prob * 100).toFixed(0)}%</div>
            <div class="text-cyan-400">${fmtVb(vbDraw)}</div>
          </div>
          <div class="bg-slate-950 rounded p-2">
            <div class="text-slate-500">客胜</div>
            <div class="text-slate-300">${(it.market.away_prob * 100).toFixed(0)}%</div>
            <div class="text-cyan-400">${fmtVb(vbAway)}</div>
          </div>
        </div>
        <div class="mt-2 text-[10px] text-slate-500 text-center">蓝=Elo vs 市场偏离值（蓝正=模型低估此结果=价值）</div>
      </a>
    `;
  }).join('');

  $('#app').innerHTML = `
    <h2 class="text-lg font-bold mb-2 flex items-center gap-2">
      <span class="text-xl">💰</span><span>赔率分析</span>
      <span class="text-xs text-slate-500 font-normal ml-auto">${data.count} 场</span>
    </h2>
    <div class="mb-4">${freshnessHtml}</div>
    <div class="text-xs text-slate-400 mb-4">市场预期 vs Elo 模型对比，识别市场定价偏离</div>
    ${valueBetsHtml}
    ${itemsHtml}
    <div class="text-[10px] text-slate-500 mt-2 text-center">赔率为各家共识平均，仅供分析参考，不构成投注建议。</div>
  `;
}

async function renderCockpit() {
  // 切换为宽布局
  const app = $('#app');
  app.classList.remove('max-w-2xl');
  app.classList.add('max-w-none', 'px-4');

  let today, allMatches, groups, teams, accuracy;
  try {
    [today, allMatches, groups, teams, accuracy] = await Promise.all([
      apiWithRetry('/matches/today'),
      apiWithRetry('/matches?limit=200'),
      apiWithRetry('/groups'),
      apiWithRetry('/teams'),
      apiWithRetry('/elo/accuracy-stats?days=180').catch(() => null),
    ]);
  } catch (err) {
    app.classList.add('max-w-2xl');
    app.classList.remove('max-w-none');
    $('#app').innerHTML = renderError(err, renderCockpit);
    return;
  }

  if (!allMatches.length) {
    app.classList.add('max-w-2xl');
    app.classList.remove('max-w-none');
    $('#app').innerHTML = renderEmpty('📊', '暂无比赛数据', '数据源异常或赛事未开始', '#/schedule', '查看赛程');
    return;
  }

  const finished = allMatches.filter(m => m.status === 'finished');
  const scheduled = allMatches.filter(m => m.status === 'scheduled');
  const nowMs = Date.now();
  // 24h 内开赛：用 beijing 转换后比较
  const in24h = scheduled.filter(m => {
    const tz = m.stadium && m.stadium.timezone ? m.stadium.timezone : 'UTC';
    const [datePart, timePart] = m.kickoff_at.split('T');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [h, mi, s = 0] = (timePart || '00:00:00').split(':').map(Number);
    const fakeUTC = Date.UTC(y, mo - 1, d, h, mi, s);
    const tzFmt = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
    const parts = Object.fromEntries(tzFmt.formatToParts(new Date(fakeUTC)).map(p => [p.type, p.value]));
    const tzAsUTC = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second)
    );
    const offsetMs = tzAsUTC - fakeUTC;
    const realUTCms = fakeUTC - offsetMs;
    return (realUTCms - nowMs) >= 0 && (realUTCms - nowMs) < 24 * 3600 * 1000;
  });

  // 进球统计
  const totalGoals = finished.reduce((s, m) => s + (m.home_score || 0) + (m.away_score || 0), 0);
  const avgGoals = finished.length ? (totalGoals / finished.length).toFixed(2) : '0.00';

  // 冠军热门：Elo 最高的队
  const topTeam = teams.slice().sort((a, b) => (b.elo_rating || 0) - (a.elo_rating || 0))[0];

  // Top 16 Elo
  const top16 = teams.slice().sort((a, b) => (b.elo_rating || 0) - (a.elo_rating || 0)).slice(0, 16);
  const maxElo = top16[0] ? top16[0].elo_rating : 2000;
  const minElo = top16[top16.length - 1] ? top16[top16.length - 1].elo_rating : 1800;

  // 12 小组，按字母排
  const groupKeys = Object.keys(groups).sort();

  // 24h 时间线（按北京时间的"小时"分桶：未来 24 小时每场比赛落入哪个小时槽）
  // 用当前北京时间为基准
  const nowBj = new Date(new Date().getTime() + 8 * 3600 * 1000); // 粗略北京
  // 更准：直接用 Date.now()，然后把 scheduled 都转成 UTC ms，桶到"距今 X 小时"
  const hourBuckets = Array.from({ length: 24 }, () => []);
  scheduled.forEach(m => {
    const tz = m.stadium && m.stadium.timezone ? m.stadium.timezone : 'UTC';
    const [datePart, timePart] = m.kickoff_at.split('T');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [h, mi, s = 0] = (timePart || '00:00:00').split(':').map(Number);
    const fakeUTC = Date.UTC(y, mo - 1, d, h, mi, s);
    const tzFmt = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
    const parts = Object.fromEntries(tzFmt.formatToParts(new Date(fakeUTC)).map(p => [p.type, p.value]));
    const tzAsUTC = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second)
    );
    const offsetMs = tzAsUTC - fakeUTC;
    const realUTCms = fakeUTC - offsetMs;
    const diffH = (realUTCms - nowMs) / 3600000;
    if (diffH >= 0 && diffH < 24) {
      const bucket = Math.floor(diffH);
      if (hourBuckets[bucket]) hourBuckets[bucket].push(m);
    }
  });

  // 16 球场聚合
  const stadiumMap = {};
  allMatches.forEach(m => {
    if (!m.stadium) return;
    const k = m.stadium.name_en;
    if (!stadiumMap[k]) {
      stadiumMap[k] = { info: m.stadium, total: 0, finished: 0, todayCount: 0 };
    }
    stadiumMap[k].total++;
    if (m.status === 'finished') stadiumMap[k].finished++;
  });
  today.forEach(m => {
    if (m.stadium && stadiumMap[m.stadium.name_en]) {
      stadiumMap[m.stadium.name_en].todayCount++;
    }
  });
  const stadiums = Object.values(stadiumMap).sort((a, b) => b.total - a.total);

  // ============= 渲染 =============
  $('#app').innerHTML = `
    <!-- 顶栏 -->
    <div class="cockpit-header flex items-center justify-between mb-4 px-1">
      <div class="flex items-center gap-3">
        <span class="text-2xl">🎛</span>
        <div>
          <div class="text-xl font-bold text-emerald-400">赛事总览驾驶舱</div>
          <div class="text-xs text-slate-500">PC / 平板横屏 优化版</div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button onclick="refreshCurrent()" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900 border border-slate-800">
          <span>🔄</span><span>刷新</span>
        </button>
        <div class="text-right">
          <div class="text-xs text-slate-500">北京时间</div>
          <div class="text-lg font-bold text-slate-200" id="bj-clock">${beijingNowString()}</div>
        </div>
      </div>
    </div>

    <!-- KPI 卡片 -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
      ${kpiCard('✅', '已完赛', finished.length, '场', 'emerald')}
      ${kpiCard('📅', '今日', today.length, '场', 'amber')}
      ${kpiCard('⏰', '24h 内', in24h.length, '场', 'blue')}
      ${kpiCard('⚽', '场均进球', avgGoals, '', 'rose')}
      ${kpiCard('🏆', '热门第 1', topTeam ? topTeam.flag_emoji + ' ' + topTeam.name_zh : '-', '', 'violet', topTeam ? 'Elo ' + topTeam.elo_rating : '')}
      ${kpiCard('🎯', '模型胜率', accuracy && accuracy.n_settled > 0 ? (accuracy.accuracy * 100).toFixed(1) + '%' : '—', accuracy ? `n=${accuracy.n_settled}` : '暂无', 'cyan', accuracy && accuracy.by_model ? `🏅 ${bestModelLabel(accuracy.by_model)}` : '—')}
    </div>

    <!-- 模型准确率 mini-card: 3 模型横评 -->
    ${accuracy && accuracy.n_settled > 0 ? `
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">🎯 3 模型横评（最近 ${accuracy.n_settled} 场已结算）</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${accuracyMiniCard('🧠 全部模型汇总', accuracy, '')}
        ${accuracyMiniCard('⚡ Glicko-2 v3', accuracy.by_model['v3_glicko2'], 'cyan')}
        ${accuracyMiniCard('📊 Elo M1 v1', accuracy.by_model['v1_elo'], 'violet')}
      </div>
      <div class="mt-2 text-xs text-slate-500">
        ▎ 准确率 ≥ 60% 绿 / 55-60% 橙 / &lt;55% 红 · 详情见 <a href="#/accuracy" class="text-blue-600 hover:underline">#/accuracy</a>
      </div>
    </section>
    ` : `
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">🎯 3 模型横评</h2>
      <div class="text-slate-500 text-sm py-4 text-center">
        ⏳ 暂无已结算预测 · 预测日志正在积累中,预计 15 分钟内首批结算入库
      </div>
    </section>
    `}

    <!-- 焦点战 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">⚽ 今日焦点战</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        ${(today.length ? today : allMatches.slice(0, 6)).slice(0, 6).map(m => focusCard(m)).join('')}
        ${!today.length ? '<div class="text-slate-500 text-sm col-span-full text-center py-6">今日无比赛，展示最近 6 场</div>' : ''}
      </div>
    </section>

    <!-- 12 小组热力图 + Elo Top 16 -->
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
      <section class="cockpit-section xl:col-span-2">
        <h2 class="cockpit-section-title">📊 12 小组积分热力图</h2>
        <div class="text-xs text-slate-500 mb-2">▎ 第 1-2 名 绿 / 第 3 名 蓝 / 第 4 名 红</div>
        <div class="overflow-x-auto pb-2">
          <div class="grid grid-cols-12 gap-1 min-w-[1100px]">
            ${groupKeys.map(g => groupHeatCell(g, groups[g])).join('')}
          </div>
        </div>
      </section>
      <section class="cockpit-section">
        <h2 class="cockpit-section-title">🏆 Elo 战力 Top 16</h2>
        <div class="cockpit-top16 pr-1">
          ${top16.map((t, i) => eloRow(i + 1, t, maxElo, minElo)).join('')}
        </div>
      </section>
    </div>

    <!-- 24h 时间线 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">📅 未来 24 小时开赛时间线（北京时间）</h2>
      <div class="text-xs text-slate-500 mb-2">▎ 每格 = 1 小时，色深 = 该小时比赛数</div>
      <div class="cockpit-timeline">
        ${hourBuckets.map((bucket, h) => hourCell(h, bucket)).join('')}
      </div>
    </section>

    <!-- 16 球场 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">🏟 16 个球场赛事分布</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        ${stadiums.map(s => stadiumCard(s)).join('')}
      </div>
    </section>

    <!-- 数据状态 -->
    <div class="text-center text-xs text-slate-600 py-2">
      数据源：${escapeHtml(allMatches[0] ? (allMatches[0].data_source || 'worldcupstats.football') : '未知')} ·
      共 ${allMatches.length} 场赛事 · 完赛率 ${allMatches.length ? ((finished.length / allMatches.length) * 100).toFixed(1) : '0'}%
    </div>
  `;

  // 启动北京时间钟
  if (window.__cockpitClock) clearInterval(window.__cockpitClock);
  const tick = () => {
    const el = document.getElementById('bj-clock');
    if (el) el.textContent = beijingNowString();
  };
  window.__cockpitClock = setInterval(tick, 30000);
}

// ============================================================
// 📈 M1.5 Elo 实力榜 + 1v1 对比器（M1 增强前端）
// ============================================================

/** 算"实力分"（0-100，越高越强），用于进度条 + 排名 */
function strengthScore(elo, topElo) {
  if (!topElo || topElo < 1400) return 0;
  // 锚定 1400 作为"最低"参考，Top 1 = 100
  return Math.max(0, Math.min(100, ((elo - 1400) / (topElo - 1400)) * 100));
}

async function renderElo() {
  // Elo 页也用宽布局
  const app = $('#app');
  app.classList.remove('max-w-2xl');
  app.classList.add('max-w-none', 'px-4');

  const source = _eloSource;
  let ratings, teams, backtest, g2Ratings;
  try {
    [ratings, teams, backtest, g2Ratings] = await Promise.all([
      apiWithRetry('/elo/ratings?source=' + source),
      apiWithRetry('/teams?limit=48'),
      source === 'hicruben' ? apiWithRetry('/elo/backtest') : Promise.resolve({}),
      apiWithRetry('/elo/glicko2-ratings?limit=48').catch(() => []),
    ]);
  } catch (err) {
    app.classList.add('max-w-2xl');
    app.classList.remove('max-w-none');
    $('#app').innerHTML = renderError(err, renderElo);
    return;
  }

  // client-side join: fifa_code → 球队详情 (Elo M1 ratings 用)
  const teamMap = {};
  teams.forEach(t => { teamMap[t.fifa_code] = t; });
  // Glicko-2 ratings 用 name_en 拼接 (API 返回 team_name = English country name, 如 "Spain")
  const teamMapByName = {};
  teams.forEach(t => { teamMapByName[t.name_en] = t; });

  // 合并
  const rows = ratings.map((r, i) => {
    const t = teamMap[r.fifa_code] || {};
    return {
      rank: i + 1,
      fifa_code: r.fifa_code,
      elo: r.elo,
      name_zh: t.name_zh || r.fifa_code,
      flag_emoji: t.flag_emoji || '🏳️',
      group_name: t.group_name || '-',
      recent_form_points: t.recent_form_points,
      recent_goal_diff: t.recent_goal_diff,
    };
  });

  const topElo = rows[0] ? rows[0].elo : 2010;
  const bottomElo = rows[rows.length - 1] ? rows[rows.length - 1].elo : 1400;
  const spread = topElo - bottomElo;

  // M1 = 球队分组：按 group 排序
  const groupedByGroup = {};
  rows.forEach(r => {
    const g = r.group_name || '?';
    if (!groupedByGroup[g]) groupedByGroup[g] = [];
    groupedByGroup[g].push(r);
  });

  // 1v1 初始值:Top 1 vs 末尾队
  let initHome = rows[0] ? rows[0].fifa_code : 'BRA';
  let initAway = rows[rows.length - 1] ? rows[rows.length - 1].fifa_code : 'GUA';
  // v0.7.0a: Glicko-2 lookup 字典(G2_NAME_TO_CODE)只覆盖约 48 强队
  // 强制选 g2Ratings top10 中的强队, 保证 Blend/Glicko-2 tab 默认加载不 404
  if (g2Ratings && g2Ratings.length >= 10) {
    const safeAway = teamMapByName[g2Ratings[9].team_name];
    if (safeAway) initAway = safeAway.fifa_code;
  }

  // 渲染
  $('#app').innerHTML = `
    <!-- 顶栏 -->
    <div class="cockpit-header flex items-center justify-between mb-4 px-1">
      <div class="flex items-center gap-3">
        <span class="text-2xl">📈</span>
        <div>
          <div class="text-xl font-bold text-emerald-400">Elo 实力榜</div>
          <div class="text-xs text-slate-500">
            ${source === 'statsbomb'
              ? '基于 StatsBomb Open Data · 世界杯/欧洲杯/美洲杯/非洲杯 · 缺失球队 fallback 到 Hicruben'
              : `基于 Hicruben 913 场 walk-forward 回测 · 截至 ${backtest.date_range ? backtest.date_range[1] : '--'}`}
          </div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex items-center bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <button onclick="setEloSource('hicruben')" class="text-xs px-3 py-1.5 transition ${source === 'hicruben' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-emerald-400'}">Hicruben</button>
          <button onclick="setEloSource('statsbomb')" class="text-xs px-3 py-1.5 transition ${source === 'statsbomb' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-emerald-400'}">StatsBomb</button>
        </div>
        <button onclick="exportEloToCSV()" title="导出 48 队 Elo 评级 CSV" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900 border border-slate-800">
          <span>📥</span><span>导出 CSV</span>
        </button>
        <button onclick="refreshCurrent()" class="text-xs text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-900 border border-slate-800">
          <span>🔄</span><span>刷新</span>
        </button>
      </div>
    </div>

    <!-- KPI 卡片：48 队 / Top 1 / 强弱差 / 准确率 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
        <div class="text-xs text-slate-500 mb-1">参赛队</div>
        <div class="text-2xl font-bold text-slate-200">${rows.length}</div>
        <div class="text-xs text-slate-500 mt-1">全部 48 队</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
        <div class="text-xs text-slate-500 mb-1">Top 1 · ${rows[0] ? escapeHtml(rows[0].flag_emoji + ' ' + rows[0].name_zh) : '-'}</div>
        <div class="text-2xl font-bold text-emerald-400">${rows[0] ? rows[0].elo : '-'}</div>
        <div class="text-xs text-slate-500 mt-1">Elo 评分</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
        <div class="text-xs text-slate-500 mb-1">强弱差</div>
        <div class="text-2xl font-bold text-amber-400">${spread}</div>
        <div class="text-xs text-slate-500 mt-1">${rows[0] ? escapeHtml(rows[0].name_zh) : '-'} - ${rows[rows.length - 1] ? escapeHtml(rows[rows.length - 1].name_zh) : '-'}</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
        <div class="text-xs text-slate-500 mb-1">回测准确率</div>
        <div class="text-2xl font-bold text-violet-400">${backtest.metrics ? backtest.metrics.accuracy_pct : '-'}%</div>
        <div class="text-xs text-slate-500 mt-1">${backtest.evaluated || '-'} 场 walk-forward</div>
      </div>
    </div>

    <!-- 1v1 对比器 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">⚔️ 1v1 实力对比</h2>
      <div class="bg-slate-900 rounded-xl p-4 border border-slate-800">
        <!-- v0.7.0a 模型切换 tab -->
        <div class="flex items-center gap-2 mb-3 flex-wrap">
          <span class="text-xs text-slate-500">模型:</span>
          <div class="flex items-center bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
            <button onclick="setEloModel('elo')" class="text-xs px-3 py-1.5 transition ${_eloModel === 'elo' ? 'bg-violet-600 text-white' : 'text-slate-400 hover:text-violet-400'}">📊 Elo M1 v1</button>
            <button onclick="setEloModel('glicko2')" class="text-xs px-3 py-1.5 transition ${_eloModel === 'glicko2' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-cyan-400'}">⚡ Glicko-2 v3</button>
            <button onclick="setEloModel('blend')" class="text-xs px-3 py-1.5 transition ${_eloModel === 'blend' ? 'bg-gradient-to-r from-violet-600 to-cyan-600 text-white' : 'text-slate-400 hover:text-violet-400'}">🧠 Blend ⭐ (默认)</button>
          </div>
          <span class="text-[10px] text-slate-500 hidden md:inline">
            ${_eloModel === 'elo' ? '· Hicruben Elo (v1)' : _eloModel === 'glicko2' ? '· 913 场 walk-forward · 准确率 62.7%' : '· Elo + Glicko-2 等权 (w_elo=0.5)'}
          </span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-7 gap-3 items-center">
          <div class="md:col-span-3">
            <label class="text-xs text-slate-500 mb-1 block">主队</label>
            <select id="elo-home" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none">
              ${rows.map(r => `<option value="${r.fifa_code}" ${r.fifa_code === initHome ? 'selected' : ''}>${r.flag_emoji} ${escapeHtml(r.name_zh)} (${r.elo})</option>`).join('')}
            </select>
          </div>
          <div class="md:col-span-1 text-center text-2xl text-slate-500 font-bold">VS</div>
          <div class="md:col-span-3">
            <label class="text-xs text-slate-500 mb-1 block">客队</label>
            <select id="elo-away" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none">
              ${rows.map(r => `<option value="${r.fifa_code}" ${r.fifa_code === initAway ? 'selected' : ''}>${r.flag_emoji} ${escapeHtml(r.name_zh)} (${r.elo})</option>`).join('')}
            </select>
          </div>
        </div>
        <div id="elo-predict-result" class="mt-4">${await _renderEloPredict(initHome, initAway)}</div>
      </div>
    </section>

    <!-- 48 队全榜（按 Elo 降序） -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">🏆 48 队 Elo 全榜</h2>
      <div class="text-xs text-slate-500 mb-2">▎ 实力分 = 相对 Top 1 的差距归一化（0-100）</div>
      <div class="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
        ${rows.map(r => _eloFullRow(r, topElo)).join('')}
      </div>
    </section>

    ${source === 'statsbomb' ? `
    <!-- StatsBomb 说明卡片 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">ℹ️ StatsBomb 数据说明</h2>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-400 space-y-2">
        <div>📡 数据源：<b class="text-slate-200">StatsBomb Open Data</b>（世界杯 2018/2022、欧洲杯 2020/2024、美洲杯 2024、非洲杯 2023）</div>
        <div>⚙️ 训练：K=60 · 中立场 home_bonus=0 · 按比赛日期排序更新</div>
        <div>📝 许可：公开使用需标注 StatsBomb 并使用其 logo</div>
        <div>⚠️ 注意：StatsBomb Open Data 缺少 2023-2026 友谊赛/预选赛，部分 2026 参赛队（伊拉克、乌兹别克斯坦等）无数据，已 fallback 到 Hicruben</div>
      </div>
    </section>
    ` : `
    <!-- 回测指标卡片 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">📊 4 年 walk-forward 回测指标</h2>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
        ${_backtestCard('准确率', (backtest.metrics ? backtest.metrics.accuracy_pct : '-') + '%', '命中 1X2', 'emerald')}
        ${_backtestCard('RPS', backtest.metrics ? backtest.metrics.rps : '-', '越低越好 (0 完美)', 'blue')}
        ${_backtestCard('Log-loss', backtest.metrics ? backtest.metrics.log_loss : '-', '越低越好', 'amber')}
        ${_backtestCard('Brier', backtest.metrics ? backtest.metrics.brier : '-', '越低越好', 'rose')}
        ${_backtestCard('ECE', (backtest.metrics ? backtest.metrics.ece_pct : '-') + '%', '校准误差', 'violet')}
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-400 space-y-1">
        <div>📅 数据范围：<b class="text-slate-200">${backtest.date_range ? backtest.date_range[0] : '-'} ~ ${backtest.date_range ? backtest.date_range[1] : '-'}</b></div>
        <div>🧪 评估：<b class="text-slate-200">${backtest.evaluated || '-'}</b> 场（burn-in ${backtest.burn_in || '-'} 场后）</div>
        <div>⚙️ 参数：K=${backtest.parameters ? backtest.parameters.k_factor : '-'} · 主队加成=${backtest.parameters ? backtest.parameters.home_bonus : '-'} · ρ=${backtest.parameters ? backtest.parameters.dc_rho : '-'}</div>
        <div>📡 数据源：<b class="text-slate-200">Hicruben/world-cup-2026-prediction-model</b>（已校准到 2026-06-11）</div>
        <div class="text-slate-500 italic">${backtest.note || ''}</div>
      </div>
    </section>
    `}

    <!-- v0.7.0a: Glicko-2 48 队评分榜 (默认折叠) -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title cursor-pointer select-none" onclick="toggleG2Section()">
        ⚡ Glicko-2 评分榜 (48 队) <span id="g2-toggle-icon" class="text-slate-500 text-xs">${_g2Open ? '▼' : '▶'}</span>
        <span class="text-[10px] text-slate-500 font-normal ml-2">· 比 Elo M1 准确率高 4-5 pp</span>
      </h2>
      <div id="g2-ratings-section" class="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden ${_g2Open ? '' : 'hidden'}">
        <div class="text-[10px] text-slate-500 px-3 py-2 border-b border-slate-800 flex items-center justify-between">
          <span>▎ 按 Glicko-2 评分降序 · 913 场 walk-forward · 截至 2026-06-11</span>
          <span class="text-cyan-400 font-mono">训练指标: 62.7% / RPS 0.17</span>
        </div>
        ${(g2Ratings && g2Ratings.length) ? g2Ratings.slice(0, 48).map((r, i) => {
          // v0.7.0a: Glicko-2 API 返回 team_name=English country name, 用 name_en join
          const t = teamMapByName[r.team_name] || {};
          const topRating = g2Ratings[0] ? g2Ratings[0].rating : r.rating;
          const score = Math.max(0, Math.min(100, ((r.rating - 1300) / (topRating - 1300)) * 100));
          return `
            <div class="elo-full-row flex items-center gap-3 px-3 py-2 border-b border-slate-800/50 hover:bg-slate-800/30 transition">
              <span class="text-slate-500 font-mono w-6 text-right text-xs">${i + 1}</span>
              <span class="team-flag text-xl">${t.flag_emoji || '🏳️'}</span>
              <a href="#/team/${r.team_name}" class="font-medium text-sm flex-1 min-w-0 truncate hover:text-emerald-400 transition">
                ${escapeHtml(t.name_zh || r.team_name)}
              </a>
              <span class="text-[10px] text-cyan-400 w-12 text-right" title="Rating Deviation 不确定度">±${r.rd.toFixed(0)}</span>
              <div class="flex-1 max-w-[140px]">
                <div class="h-2 bg-slate-800 rounded overflow-hidden">
                  <div class="h-full bg-gradient-to-r from-cyan-500 to-emerald-400" style="width:${score.toFixed(0)}%"></div>
                </div>
              </div>
              <span class="text-cyan-400 font-bold font-mono w-12 text-right">${r.rating.toFixed(0)}</span>
            </div>
          `;
        }).join('') : '<div class="px-3 py-4 text-center text-slate-500 text-sm">Glicko-2 评分加载中...</div>'}
      </div>
    </section>

    <!-- 数据状态 -->
    <div class="text-center text-xs py-2 ${source === 'statsbomb' ? 'text-amber-500/80' : 'text-slate-600'}">
      ${source === 'statsbomb'
        ? `StatsBomb 评分来源 · StatsBomb Open Data · 共 ${rows.length} 队 · 缺失球队 fallback 到 Hicruben`
        : `Elo 评分来源 · Hicruben Elo-calibrated dataset · 共 ${rows.length} 队`}
    </div>
  `;

  // 绑定 1v1 select 变化
  setTimeout(() => {
    const homeSel = document.getElementById('elo-home');
    const awaySel = document.getElementById('elo-away');
    if (!homeSel || !awaySel) return;
    const update = async () => {
      const result = document.getElementById('elo-predict-result');
      if (!result) return;
      result.innerHTML = '<div class="text-slate-500 text-sm text-center py-4">预测中...</div>';
      result.innerHTML = await _renderEloPredict(homeSel.value, awaySel.value);
    };
    homeSel.addEventListener('change', update);
    awaySel.addEventListener('change', update);
  }, 50);
}

async function exportEloToCSV() {
  // 找到按钮做自我反馈（无 toast 基础设施时用）
  const btn = document.querySelector('button[onclick="exportEloToCSV()"]');
  const setBtn = (icon, text, cls) => {
    if (!btn) return;
    btn.innerHTML = `<span>${icon}</span><span>${text}</span>`;
    btn.className = btn.className.replace(/text-\w+-\d+|border-slate-\d+/g, '').trim() + ` ${cls}`;
  };
  setBtn('⏳', '导出中...', 'text-amber-400 border-amber-700');
  let ratings, teams;
  const source = _eloSource;
  try {
    [ratings, teams] = await Promise.all([
      apiWithRetry('/elo/ratings?source=' + source),
      apiWithRetry('/teams?limit=48'),
    ]);
  } catch (err) {
    setBtn('❌', '导出失败', 'text-rose-400 border-rose-700');
    console.error('[exportEloToCSV]', err);
    setTimeout(() => setBtn('📥', '导出 CSV', 'text-slate-400 border-slate-800'), 2000);
    return;
  }
  // client-side join（同 renderElo）
  const teamMap = {};
  teams.forEach(t => { teamMap[t.fifa_code] = t; });
  // 过滤：只导出 2026 世界杯参赛队（48 队），丢弃 Hicruben Elo 里的非参赛队
  // 原因：按钮 title 写 "48 队 Elo 评级 CSV"，保持一致
  const allRows = ratings.map((r, i) => {
    const t = teamMap[r.fifa_code] || {};
    return {
      rank: i + 1,
      fifa_code: r.fifa_code,
      elo: r.elo,
      name_zh: t.name_zh || r.fifa_code,
      name_en: t.name_en || '',
      flag_emoji: t.flag_emoji || '',
      group_name: t.group_name || '',
      recent_form_points: t.recent_form_points != null ? t.recent_form_points : '',
      recent_goal_diff: t.recent_goal_diff != null ? t.recent_goal_diff : '',
      _has_team: !!t.name_zh,
    };
  });
  const rows = allRows.filter(r => r._has_team).map((r, idx) => ({ ...r, rank: idx + 1 }));
  const topElo = rows[0] ? rows[0].elo : 2010;
  // 实力分（同 _eloFullRow 一致：锚定 1400 参考线）
  rows.forEach(r => {
    r.strength_score = ((r.elo - 1400) / (topElo - 1400) * 100).toFixed(1);
  });
  // CSV 表头（中文，让 Excel 中文版友好）
  const headers = ['排名', 'FIFA代码', '中文名', '英文名', '小组', '国旗', 'Elo评分', '实力分(0-100)', '近5场得分', '近5场净胜'];
  const csvRows = [headers];
  rows.forEach(r => {
    csvRows.push([
      r.rank,
      r.fifa_code,
      r.name_zh,
      r.name_en,
      r.group_name,
      r.flag_emoji,
      r.elo,
      r.strength_score,
      r.recent_form_points,
      r.recent_goal_diff,
    ]);
  });
  // RFC 4180 转义
  const csvContent = csvRows.map(row =>
    row.map(cell => csvEscape(cell)).join(',')
  ).join('\r\n');
  // 加 UTF-8 BOM（Excel 中文版正确识别 UTF-8）
  const BOM = '\uFEFF';
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  const today = new Date().toISOString().slice(0, 10);
  const filename = `wc2026_elo_ratings_${today}.csv`;
  // 触发浏览器下载
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 100);
  setBtn('✅', `已导出 ${rows.length} 队`, 'text-emerald-400 border-emerald-700');
  console.log(`[exportEloToCSV] ${rows.length} 队 → ${filename}`);
  setTimeout(() => setBtn('📥', '导出 CSV', 'text-slate-400 border-slate-800'), 2000);
}

function csvEscape(value) {
  // RFC 4180: 含逗号/双引号/换行的字段加双引号；内部双引号转义为两个双引号
  const s = String(value == null ? '' : value);
  if (/[",\r\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

async function _renderEloPredict(homeCode, awayCode) {
  // v0.7.0a: 根据 _eloModel 路由到不同预测器
  if (!homeCode || !awayCode || homeCode === awayCode) {
    return '<div class="text-amber-400 text-sm text-center py-4">请选择两支不同的球队</div>';
  }
  const model = window._eloModel || _eloModel || 'blend';
  if (model === 'elo') return _renderEloM1Predict(homeCode, awayCode);
  if (model === 'glicko2') return _renderGlicko2Predict(homeCode, awayCode);
  return _renderBlendPredict(homeCode, awayCode);
}

// Elo M1 (v1) 单模型预测
async function _renderEloM1Predict(homeCode, awayCode) {
  try {
    const p = await apiWithRetry('/elo/predict/' + homeCode + '/' + awayCode + '?source=' + _eloSource);
    const hWin = (p.probabilities.home_win * 100).toFixed(1);
    const draw = (p.probabilities.draw * 100).toFixed(1);
    const aWin = (p.probabilities.away_win * 100).toFixed(1);
    const maxProb = Math.max(p.probabilities.home_win, p.probabilities.draw, p.probabilities.away_win);
    const winnerText = maxProb === p.probabilities.home_win ? '主胜倾向' : maxProb === p.probabilities.away_win ? '客胜倾向' : '平局倾向';
    const winnerColor = maxProb === p.probabilities.home_win ? 'text-emerald-400' : maxProb === p.probabilities.away_win ? 'text-rose-400' : 'text-amber-400';
    return `
      <div class="space-y-3">
        <div>
          <div class="flex justify-between text-sm mb-2">
            <span>主胜 <b class="text-emerald-400">${hWin}%</b></span>
            <span>平 <b class="text-amber-400">${draw}%</b></span>
            <span>客胜 <b class="text-rose-400">${aWin}%</b></span>
          </div>
          <div class="flex h-3 rounded-full overflow-hidden bg-slate-800">
            <div class="bg-emerald-500" style="width:${hWin}%"></div>
            <div class="bg-amber-500" style="width:${draw}%"></div>
            <div class="bg-rose-500" style="width:${aWin}%"></div>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-2 text-center">
          <div class="bg-slate-800/50 rounded p-2">
            <div class="text-xs text-slate-500">主队预期进球</div>
            <div class="text-lg font-bold text-emerald-400">${p.expected_goals.home.toFixed(2)}</div>
          </div>
          <div class="bg-slate-800/50 rounded p-2">
            <div class="text-xs text-slate-500">客队预期进球</div>
            <div class="text-lg font-bold text-rose-400">${p.expected_goals.away.toFixed(2)}</div>
          </div>
        </div>
        <div class="text-center">
          <span class="text-xs text-slate-500">结论：</span>
          <span class="${winnerColor} font-bold">${winnerText}</span>
          <span class="text-xs text-slate-500 ml-2">（最高概率 ${(maxProb * 100).toFixed(1)}%）</span>
        </div>
        <div class="text-center text-[10px] text-slate-600">📊 Elo M1 v1 · 数据源: ${escapeHtml(p.data_source || _eloSource)}</div>
      </div>
    `;
  } catch (e) {
    return '<div class="text-rose-400 text-sm text-center py-4">Elo 预测失败：' + escapeHtml(e.message || '') + '</div>';
  }
}

// Glicko-2 (v3) 单模型预测
async function _renderGlicko2Predict(homeCode, awayCode) {
  try {
    const p = await apiWithRetry('/elo/predict-glicko2/' + homeCode + '/' + awayCode);
    const hWin = (p.probabilities.home_win * 100).toFixed(1);
    const draw = (p.probabilities.draw * 100).toFixed(1);
    const aWin = (p.probabilities.away_win * 100).toFixed(1);
    const maxProb = Math.max(p.probabilities.home_win, p.probabilities.draw, p.probabilities.away_win);
    const winnerText = maxProb === p.probabilities.home_win ? '主胜倾向' : maxProb === p.probabilities.away_win ? '客胜倾向' : '平局倾向';
    const winnerColor = maxProb === p.probabilities.home_win ? 'text-emerald-400' : maxProb === p.probabilities.away_win ? 'text-rose-400' : 'text-amber-400';
    return `
      <div class="space-y-3">
        <div>
          <div class="flex justify-between text-sm mb-2">
            <span>主胜 <b class="text-emerald-400">${hWin}%</b></span>
            <span>平 <b class="text-amber-400">${draw}%</b></span>
            <span>客胜 <b class="text-rose-400">${aWin}%</b></span>
          </div>
          <div class="flex h-3 rounded-full overflow-hidden bg-slate-800">
            <div class="bg-emerald-500" style="width:${hWin}%"></div>
            <div class="bg-amber-500" style="width:${draw}%"></div>
            <div class="bg-rose-500" style="width:${aWin}%"></div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="bg-slate-800/50 rounded p-2">
            <div class="text-xs text-slate-500">主队 Glicko-2</div>
            <div class="text-sm font-bold text-cyan-400">${p.home.rating.toFixed(0)}</div>
            <div class="text-[10px] text-slate-500">±${p.home.rd.toFixed(1)}</div>
          </div>
          <div class="bg-slate-800/50 rounded p-2">
            <div class="text-xs text-slate-500">期望进球</div>
            <div class="text-sm font-bold text-slate-300">${(p.expected_score * 2.6).toFixed(2)} - ${((1 - p.expected_score) * 2.6).toFixed(2)}</div>
          </div>
          <div class="bg-slate-800/50 rounded p-2">
            <div class="text-xs text-slate-500">客队 Glicko-2</div>
            <div class="text-sm font-bold text-rose-400">${p.away.rating.toFixed(0)}</div>
            <div class="text-[10px] text-slate-500">±${p.away.rd.toFixed(1)}</div>
          </div>
        </div>
        <div class="text-center">
          <span class="text-xs text-slate-500">结论：</span>
          <span class="${winnerColor} font-bold">${winnerText}</span>
          <span class="text-xs text-slate-500 ml-2">（最高概率 ${(maxProb * 100).toFixed(1)}%）</span>
        </div>
        <div class="text-center text-[10px] text-slate-600">⚡ Glicko-2 v3 · 913 场 walk-forward · 准确率 62.7%</div>
      </div>
    `;
  } catch (e) {
    // v0.7.0a: 404 fallback (球队不在 Glicko-2 字典) → 降级显示 Elo M1
    if (e.message && e.message.includes('404')) {
      const fallback = await _renderEloM1Predict(homeCode, awayCode);
      return fallback + '<div class="text-center text-amber-400 text-[10px] mt-1">⚠️ 该队不在 Glicko-2 字典, 已降级到 Elo M1</div>';
    }
    return '<div class="text-rose-400 text-sm text-center py-4">Glicko-2 预测失败：' + escapeHtml(e.message || '') + '</div>';
  }
}

// v0.7.0a ModelBlend: Elo + Glicko-2 加权平均(默认 w_elo=0.5)
async function _renderBlendPredict(homeCode, awayCode) {
  try {
    const b = await apiWithRetry('/elo/predict-blend/' + homeCode + '/' + awayCode + '?w_elo=0.5&w_glicko2=0.5');
    const probs = b.blended.probabilities;
    const hWin = (probs.home_win * 100).toFixed(1);
    const draw = (probs.draw * 100).toFixed(1);
    const aWin = (probs.away_win * 100).toFixed(1);
    const eloProbs = b.elo.probabilities;
    const g2Probs = b.glicko2.probabilities;
    const maxProb = Math.max(probs.home_win, probs.draw, probs.away_win);
    const winnerText = maxProb === probs.home_win ? '主胜倾向' : maxProb === probs.away_win ? '客胜倾向' : '平局倾向';
    const winnerColor = maxProb === probs.home_win ? 'text-emerald-400' : maxProb === probs.away_win ? 'text-rose-400' : 'text-amber-400';
    // 3 模型并排: Elo / Glicko-2 / Blend
    const compRow = (label, color, p) => `
      <div class="bg-slate-800/40 rounded p-2">
        <div class="text-[10px] text-slate-500">${label}</div>
        <div class="text-[11px] font-mono ${color}">${(p.home_win * 100).toFixed(1)} / ${(p.draw * 100).toFixed(1)} / ${(p.away_win * 100).toFixed(1)}</div>
      </div>
    `;
    return `
      <div class="space-y-3">
        <div>
          <div class="flex justify-between text-sm mb-2">
            <span>主胜 <b class="text-emerald-400">${hWin}%</b></span>
            <span>平 <b class="text-amber-400">${draw}%</b></span>
            <span>客胜 <b class="text-rose-400">${aWin}%</b></span>
          </div>
          <div class="flex h-3 rounded-full overflow-hidden bg-slate-800">
            <div class="bg-emerald-500" style="width:${hWin}%"></div>
            <div class="bg-amber-500" style="width:${draw}%"></div>
            <div class="bg-rose-500" style="width:${aWin}%"></div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center">
          ${compRow('📊 Elo M1', 'text-violet-400', eloProbs)}
          ${compRow('⚡ Glicko-2', 'text-cyan-400', g2Probs)}
          ${compRow('🧠 Blend ⭐', 'text-gradient bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent', probs)}
        </div>
        <div class="text-center">
          <span class="text-xs text-slate-500">结论：</span>
          <span class="${winnerColor} font-bold">${winnerText}</span>
          <span class="text-xs text-slate-500 ml-2">（Blend 最高概率 ${(maxProb * 100).toFixed(1)}%）</span>
        </div>
        <div class="text-center text-[10px] text-slate-600">🧠 ModelBlend · Elo + Glicko-2 等权 w=0.5/0.5 · 三方融合见 v0.7.3</div>
      </div>
    `;
  } catch (e) {
    // v0.7.0a: 404 fallback (球队不在 Glicko-2 字典) → 降级显示 Elo M1
    if (e.message && e.message.includes('404')) {
      const fallback = await _renderEloM1Predict(homeCode, awayCode);
      return fallback + '<div class="text-center text-amber-400 text-[10px] mt-1">⚠️ 该队不在 Glicko-2 字典, 已降级到 Elo M1</div>';
    }
    return '<div class="text-rose-400 text-sm text-center py-4">Blend 预测失败：' + escapeHtml(e.message || '') + '</div>';
  }
}

function _eloFullRow(r, topElo) {
  const score = strengthScore(r.elo, topElo);
  const form = r.recent_form_points;
  const formText = form === null || form === undefined ? '新' : `${form}/15`;
  const formColor = form === null || form === undefined ? 'text-slate-500'
    : form >= 10 ? 'text-emerald-400'
    : form >= 5 ? 'text-amber-400'
    : 'text-rose-400';
  const groupBadge = r.group_name !== '-' ? `<span class="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400 ml-1">${r.group_name}</span>` : '';
  return `
    <div class="elo-full-row flex items-center gap-3 px-3 py-2 border-b border-slate-800/50 hover:bg-slate-800/30 transition">
      <span class="text-slate-500 font-mono w-6 text-right text-xs">${r.rank}</span>
      <span class="team-flag text-xl">${r.flag_emoji}</span>
      <a href="#/team/${r.fifa_code}" class="font-medium text-sm flex-1 min-w-0 truncate hover:text-emerald-400 transition">
        ${escapeHtml(r.name_zh)}${groupBadge}
      </a>
      <span class="text-xs ${formColor} w-10 text-right" title="近 5 场得分">${formText}</span>
      <div class="flex-1 max-w-[140px]">
        <div class="h-2 bg-slate-800 rounded overflow-hidden">
          <div class="h-full bg-gradient-to-r from-emerald-500 to-amber-400" style="width:${score.toFixed(0)}%"></div>
        </div>
      </div>
      <span class="text-emerald-400 font-bold font-mono w-12 text-right">${r.elo}</span>
    </div>
  `;
}

function _backtestCard(label, value, sub, color) {
  const colorMap = {
    emerald: 'text-emerald-400 border-emerald-500/30',
    blue: 'text-blue-400 border-blue-500/30',
    amber: 'text-amber-400 border-amber-500/30',
    rose: 'text-rose-400 border-rose-500/30',
    violet: 'text-violet-400 border-violet-500/30',
  };
  return `
    <div class="bg-slate-900 border ${colorMap[color]} rounded-xl p-3">
      <div class="text-xs text-slate-500 mb-1">${label}</div>
      <div class="text-xl font-bold ${colorMap[color].split(' ')[0]}">${value}</div>
      <div class="text-xs text-slate-500 mt-1">${sub}</div>
    </div>
  `;
}

// 离开 cockpit 时还原 max-w-2xl
function restoreAppWidth() {
  const app = $('#app');
  if (!app) return;
  app.classList.remove('max-w-none');
  app.classList.add('max-w-2xl');
}

function kpiCard(icon, label, value, unit, color, sub) {
  const colorMap = {
    emerald: 'from-emerald-500/20 to-emerald-600/10 text-emerald-400 border-emerald-500/30',
    amber: 'from-amber-500/20 to-amber-600/10 text-amber-400 border-amber-500/30',
    blue: 'from-blue-500/20 to-blue-600/10 text-blue-400 border-blue-500/30',
    rose: 'from-rose-500/20 to-rose-600/10 text-rose-400 border-rose-500/30',
    violet: 'from-violet-500/20 to-violet-600/10 text-violet-400 border-violet-500/30',
    cyan: 'from-cyan-500/20 to-cyan-600/10 text-cyan-400 border-cyan-500/30',
  };
  return `
    <div class="cockpit-kpi bg-gradient-to-br ${colorMap[color]} border rounded-xl p-3">
      <div class="flex items-center justify-between mb-1">
        <span class="text-2xl">${icon}</span>
        <span class="text-xs text-slate-400">${label}</span>
      </div>
      <div class="flex items-baseline gap-1">
        <span class="text-2xl font-bold">${value}</span>
        <span class="text-sm text-slate-400">${unit}</span>
      </div>
      ${sub ? `<div class="text-xs text-slate-500 mt-1">${sub}</div>` : ''}
    </div>
  `;
}

// v0.6.0: 模型准确率 mini-card (Cockpit 用)
function accuracyMiniCard(label, m, color) {
  if (!m) {
    return `<div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 text-center text-slate-500 text-xs">
      <div class="mb-1">${label}</div>
      <div>暂无数据</div>
    </div>`;
  }
  const acc = m.accuracy == null ? null : (m.accuracy * 100).toFixed(1) + '%';
  const colorCls = acc == null ? 'text-slate-500'
    : parseFloat(acc) >= 60 ? 'text-emerald-400'
    : parseFloat(acc) >= 55 ? 'text-amber-400'
    : 'text-rose-400';
  const accent = color === 'cyan' ? 'border-cyan-500/30'
    : color === 'violet' ? 'border-violet-500/30'
    : 'border-slate-700';
  return `
    <div class="bg-slate-900/50 border ${accent} rounded-xl p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-slate-300 font-semibold">${label}</span>
        <span class="text-xs text-slate-500">n=${m.n}</span>
      </div>
      <div class="flex items-baseline gap-2 mb-3">
        <span class="text-3xl font-bold ${colorCls}">${acc ?? '—'}</span>
        <span class="text-xs text-slate-500">准确率</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div class="text-slate-500">RPS</div>
          <div class="font-mono ${m.rps == null ? 'text-slate-600' : 'text-slate-200'}">${m.rps == null ? '—' : m.rps.toFixed(4)}</div>
        </div>
        <div>
          <div class="text-slate-500">Brier</div>
          <div class="font-mono ${m.brier == null ? 'text-slate-600' : 'text-slate-200'}">${m.brier == null ? '—' : m.brier.toFixed(4)}</div>
        </div>
        <div>
          <div class="text-slate-500">LogLoss</div>
          <div class="font-mono ${m.log_loss == null ? 'text-slate-600' : 'text-slate-200'}">${m.log_loss == null ? '—' : m.log_loss.toFixed(4)}</div>
        </div>
      </div>
    </div>
  `;
}

// v0.6.0: 找出胜率最高的模型
function bestModelLabel(byModel) {
  if (!byModel) return '—';
  let bestKey = null, bestAcc = -1;
  Object.entries(byModel).forEach(([k, v]) => {
    if (v.accuracy != null && v.accuracy > bestAcc) {
      bestAcc = v.accuracy;
      bestKey = k;
    }
  });
  if (!bestKey) return '—';
  const labelMap = {
    v1_elo: 'Elo M1',
    v2_enhanced: 'Elo v2',
    v3_glicko2: 'Glicko-2',
  };
  return `${labelMap[bestKey] || bestKey} ${(bestAcc * 100).toFixed(0)}%`;
}

function focusCard(m) {
  const tz = m.stadium && m.stadium.timezone ? m.stadium.timezone : 'UTC';
  const bj = fmtBeijingFromTZ(m.kickoff_at, tz, true);
  const cd = countdownText(m.kickoff_at, tz);
  const home = m.home_team || { name_zh: m.home_team_placeholder || '待定', flag_emoji: '🏳️' };
  const away = m.away_team || { name_zh: m.away_team_placeholder || '待定', flag_emoji: '🏳️' };
  const score = (m.status === 'finished' || (m.home_score !== null && m.away_score !== null))
    ? `${m.home_score} : ${m.away_score}` : 'VS';
  const scoreColor = m.status === 'finished' ? 'text-white' : 'text-slate-500';
  return `
    <a href="#/match/${m.id}" class="block bg-slate-900 hover:bg-slate-800 rounded-xl p-3 border border-slate-800 transition">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs text-slate-500">${bj} 北京</span>
        <span class="text-xs ${m.status === 'finished' ? 'text-slate-400' : 'text-emerald-400'}">${cd || statusBadgeText(m.status)}</span>
      </div>
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <span class="team-flag text-xl">${home.flag_emoji || '🏳️'}</span>
          <span class="font-medium text-sm truncate">${escapeHtml(home.name_zh)}</span>
        </div>
        <div class="text-xl font-bold ${scoreColor} score-big px-2">${score}</div>
        <div class="flex items-center gap-2 flex-1 min-w-0 justify-end">
          <span class="font-medium text-sm truncate">${escapeHtml(away.name_zh)}</span>
          <span class="team-flag text-xl">${away.flag_emoji || '🏳️'}</span>
        </div>
      </div>
      <div class="mt-2 text-xs text-slate-500 truncate">${m.group_name ? m.group_name + '组 · ' : ''}${m.stadium ? escapeHtml(m.stadium.name_en) : ''}</div>
    </a>
  `;
}

function statusBadgeText(s) {
  if (s === 'live') return '进行中';
  if (s === 'finished') return '已结束';
  return '未开始';
}

function groupHeatCell(g, rows) {
  // rows 已按名次排好（API 排序）
  const sorted = rows.slice(0, 4);
  return `
    <div class="bg-slate-900 rounded border border-slate-800 overflow-hidden">
      <div class="text-center text-xs font-bold text-emerald-400 bg-slate-800/50 py-0.5">${g}</div>
      ${sorted.map((r, idx) => {
        const pos = idx + 1;
        const colorMap = {
          1: 'bg-emerald-500/20 text-emerald-300',
          2: 'bg-emerald-500/10 text-emerald-400/80',
          3: 'bg-blue-500/15 text-blue-300',
          4: 'bg-rose-500/15 text-rose-300/70',
        };
        return `
          <div class="${colorMap[pos]} px-1 py-0.5 text-[10px] flex justify-between items-center border-t border-slate-800/50">
            <span class="truncate flex-1">${r.team.flag_emoji || ''} ${escapeHtml(r.team.name_zh)}</span>
            <span class="font-bold ml-1">${r.points}</span>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function eloRow(rank, t, maxElo, minElo) {
  const elo = t.elo_rating || 1800;
  const widthPct = Math.max(20, ((elo - (minElo - 50)) / (maxElo - (minElo - 50))) * 100);
  const form = t.recent_form_points;
  const formText = form === null || form === undefined ? '新' : `近 ${form}/15`;
  return `
    <a href="#/team/${t.id}" class="block bg-slate-900 hover:bg-slate-800 rounded p-1.5 border border-slate-800 transition">
      <div class="flex items-center justify-between text-xs mb-0.5">
        <span class="flex items-center gap-1.5 min-w-0">
          <span class="text-slate-500 font-mono w-5 text-right">${rank}</span>
          <span class="team-flag text-base">${t.flag_emoji || '🏳️'}</span>
          <span class="font-medium truncate">${escapeHtml(t.name_zh)}</span>
        </span>
        <span class="text-emerald-400 font-bold font-mono">${elo}</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden">
          <div class="h-full bg-gradient-to-r from-emerald-500 to-amber-400" style="width:${widthPct.toFixed(0)}%"></div>
        </div>
        <span class="text-[10px] text-slate-500 w-12 text-right">${formText}</span>
      </div>
    </a>
  `;
}

function hourCell(h, bucket) {
  const n = bucket.length;
  const intensity = n === 0 ? 'bg-slate-900' : n === 1 ? 'bg-emerald-500/30' : n === 2 ? 'bg-emerald-500/50' : 'bg-emerald-500/80';
  const heightClass = n === 0 ? 'h-10' : n === 1 ? 'h-12' : n === 2 ? 'h-14' : 'h-16';
  const list = bucket.slice(0, 3).map(m => {
    const home = (m.home_team || { name_zh: m.home_team_placeholder || '?' }).name_zh;
    const away = (m.away_team || { name_zh: m.away_team_placeholder || '?' }).name_zh;
    return `<div class="truncate text-[10px] text-slate-200">${home} vs ${away}</div>`;
  }).join('');
  const more = n > 3 ? `<div class="text-[10px] text-slate-400">+${n - 3} 场</div>` : '';
  return `
    <div class="${intensity} ${heightClass} rounded border border-slate-800/50 p-1 flex flex-col justify-end" title="+${h}h: ${n} 场">
      <div class="text-[10px] text-slate-500 font-mono">+${h}h</div>
      ${list}${more}
    </div>
  `;
}

function stadiumCard(s) {
  const todayBadge = s.todayCount > 0
    ? `<span class="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">今日 ${s.todayCount} 场</span>`
    : `<span class="text-[10px] text-slate-600">今日无</span>`;
  return `
    <div class="bg-slate-900 rounded-lg p-2 border border-slate-800">
      <div class="flex items-start justify-between mb-1">
        <div class="font-bold text-xs text-slate-200 truncate">${escapeHtml(s.info.name_en)}</div>
        ${todayBadge}
      </div>
      <div class="text-[10px] text-slate-500 truncate">${escapeHtml(s.info.city)}, ${escapeHtml(s.info.country)}</div>
      <div class="flex items-center gap-2 mt-1.5 text-[10px]">
        <span class="text-slate-400">已踢 <b class="text-white">${s.finished}</b></span>
        <span class="text-slate-400">总 <b class="text-white">${s.total}</b></span>
        <div class="flex-1 h-1 bg-slate-800 rounded overflow-hidden">
          <div class="h-full bg-emerald-500" style="width:${s.total ? (s.finished / s.total * 100).toFixed(0) : 0}%"></div>
        </div>
      </div>
    </div>
  `;
}


// ---------- 路由 ----------


// ============================================================
// 🔧 P0 通用组件: 404 / 骨架屏 / 错误重试 / 空状态
// ============================================================

/**
 * A9: 显示加载骨架屏
 * @param {'home'|'schedule'|'teams'|'match-detail'|'team-detail'|'groups'|'simulator'|'cockpit'|'generic'} type
 */
function showSkeleton(type) {
  const map = {
    'home': `<div class="space-y-3">
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
    </div>`,
    'schedule': `<div class="space-y-2">
      ${[1,2,3,4,5].map(() => '<div class="skeleton-shimmer skeleton-row"></div>').join('')}
    </div>`,
    'teams': `<div class="grid grid-cols-2 gap-3">
      ${[1,2,3,4,5,6,7,8].map(() => '<div class="skeleton-shimmer" style="height:64px;border-radius:12px"></div>').join('')}
    </div>`,
    'match-detail': `<div class="skeleton-shimmer skeleton-detail" style="margin-bottom:16px"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>`,
    'team-detail': `<div class="skeleton-shimmer" style="height:140px;border-radius:12px;margin-bottom:16px"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>`,
    'h2h-detail': `<div class="skeleton-shimmer" style="height:200px;border-radius:12px;margin-bottom:16px"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>
      <div class="skeleton-shimmer skeleton-card"></div>`,
    'h2h': `<div class="skeleton-shimmer" style="height:80px;border-radius:12px;margin-bottom:16px"></div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        ${[1,2,3,4,5,6].map(() => '<div class="skeleton-shimmer" style="height:80px;border-radius:12px"></div>').join('')}
      </div>`,
    'groups': `<div class="space-y-3">
      ${[1,2,3].map(() => '<div class="skeleton-shimmer" style="height:200px;border-radius:12px"></div>').join('')}
    </div>`,
    'simulator': `<div class="space-y-3">
      ${[1,2,3].map(() => '<div class="skeleton-shimmer" style="height:240px;border-radius:12px"></div>').join('')}
    </div>`,
    'cockpit': `<div class="space-y-3">
      <div class="skeleton-shimmer" style="height:80px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:160px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:280px;border-radius:12px"></div>
    </div>`,
    'elo': `<div class="space-y-3">
      <div class="skeleton-shimmer" style="height:80px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:160px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:280px;border-radius:12px"></div>
    </div>`,
    'bracket': `<div class="space-y-3">
      <div class="skeleton-shimmer" style="height:60px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:200px;border-radius:12px"></div>
      <div class="skeleton-shimmer" style="height:280px;border-radius:12px"></div>
    </div>`,
    'generic': `<div class="text-center py-12 text-slate-500">加载中...</div>`,
  };
  $('#app').innerHTML = map[type] || map['generic'];
}

/**
 * A10: 渲染错误页（含重试按钮）
 * @param {Error|string} err
 * @param {Function} retryFn - 点击"重试"时调用，可为 null
 */
function renderError(err, retryFn) {
  const msg = (err && err.message) ? err.message : (typeof err === 'string' ? err : '未知错误');
  const retryAttr = retryFn ? `onclick="(${retryFn.toString()})()"` : '';
  return `
    <div class="state-card state-card-error text-center">
      <div class="text-5xl mb-3">😵</div>
      <h3 class="text-lg font-bold text-red-300 mb-2">加载失败</h3>
      <div class="text-sm text-slate-400 mb-5 break-all">${escapeHtml(msg)}</div>
      <div class="flex gap-3 justify-center flex-wrap">
        ${retryFn ? `<button ${retryAttr} class="btn-warning">🔄 重试</button>` : ''}
        <a href="#/" class="btn-secondary">返回首页</a>
      </div>
    </div>
  `;
}

/**
 * A8: 渲染 404 页面
 */
function renderNotFound() {
  const links = [
    { hash: '#/', icon: '🏠', label: '首页' },
    { hash: '#/cockpit', icon: '🎛', label: '总览驾驶舱' },
    { hash: '#/bracket', icon: '🏆', label: '晋级路线' },
    { hash: '#/schedule', icon: '📅', label: '赛程' },
    { hash: '#/groups', icon: '📊', label: '积分' },
    { hash: '#/simulator', icon: '🎲', label: '出线模拟' },
    { hash: '#/teams', icon: '⚽', label: '48 球队' },
  ];
  return `
    <div class="state-card text-center mt-4">
      <div class="text-6xl mb-4">🧭</div>
      <h2 class="text-xl font-bold text-slate-200 mb-2">找不到这个页面</h2>
      <p class="text-sm text-slate-500 mb-6">链接可能已过期或地址输错，要不换个地方看看？</p>
      <div class="notfound-grid">
        ${links.map(l => `
          <a href="${l.hash}" class="notfound-link">
            <span class="text-xl">${l.icon}</span>
            <span class="text-sm text-slate-300">${l.label}</span>
          </a>
        `).join('')}
      </div>
    </div>
  `;
}

/**
 * A8: 渲染空状态
 */
function renderEmpty(emoji, title, hint, ctaHash, ctaLabel) {
  return `
    <div class="state-card state-card-empty text-center">
      <div class="text-5xl mb-3">${emoji}</div>
      <div class="text-base text-slate-300 mb-1">${escapeHtml(title)}</div>
      ${hint ? `<div class="text-xs text-slate-500 mb-4">${escapeHtml(hint)}</div>` : '<div class="mb-4"></div>'}
      ${ctaHash && ctaLabel ? `<a href="${ctaHash}" class="btn-primary text-sm">${escapeHtml(ctaLabel)}</a>` : ''}
    </div>
  `;
}

/**
 * A10: 带重试的 API 调用
 * 失败时抛出 Error 对象附带 status 信息，由 renderError 统一处理
 */
async function apiWithRetry(path, options = {}) {
  const { retries = 1, retryDelay = 600 } = options;
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    try {
      return await api(path);
    } catch (err) {
      lastErr = err;
      if (i < retries) {
        await new Promise(r => setTimeout(r, retryDelay));
      }
    }
  }
  throw lastErr;
}

/** A1: 刷新当前页（在不改变 hash 的情况下重新调当前 render 函数） */
function refreshCurrent() {
  const hash = location.hash.slice(1) || '/';
  if (hash.startsWith('/match/')) {
    return renderMatchDetail(hash.split('/')[2]);
  }
  if (hash.startsWith('/team/')) {
    return renderTeamDetail(hash.split('/')[2]);
  }
  if (hash.startsWith('/h2h/')) {
    const parts = hash.split('/');
    return renderH2HDetail(parts[2], parts[3]);
  }
  if (routes[hash]) {
    return routes[hash]();
  }
}

/** A2: 切换下一场焦点战 */
function nextFocusMatch() {
  _homeFocusIdx = (_homeFocusIdx + 1);
  // 注意：不 modulo，让 renderHome 内部处理边界
  renderHome();
}

/** A11: 切换抽屉 */
function toggleDrawer() {
  const drawer = document.getElementById('drawer');
  const overlay = document.getElementById('drawer-overlay');
  if (!drawer || !overlay) return;
  const isOpen = drawer.classList.contains('open');
  if (isOpen) {
    drawer.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  } else {
    drawer.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    // 更新抽屉底部时间
    const el = document.getElementById('drawer-update-time');
    if (el) el.textContent = beijingNowString();
  }
}

/** A11: 关于本站弹窗 */
function showAbout() {
  toggleDrawer();
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal-card">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold text-emerald-400 flex items-center gap-2"><span>ℹ️</span>关于本站</h3>
        <button onclick="this.closest('.modal-backdrop').remove()" class="text-slate-400 hover:text-white text-xl">✕</button>
      </div>
      <div class="space-y-3 text-sm text-slate-300">
        <p><b class="text-white">2026 美加墨世界杯赛事分析</b> · 个人轻量 H5 工具</p>
        <p>核心功能：</p>
        <ul class="list-disc list-inside text-slate-400 space-y-1 text-xs">
          <li>完整赛程 · 48 队 · 12 组 · 16 球场</li>
          <li>Elo-Poisson 胜负预测（含 Elo / 状态 / 历史交锋 三因子）</li>
          <li>出线模拟器：5000 次蒙特卡洛推演</li>
          <li>北京时间转换 · 实时天气 · 球场分布</li>
        </ul>
        <p class="text-xs text-slate-500 mt-4">所有比赛时间已转换为北京时间。数据自动源 + 人工校对。</p>
      </div>
    </div>
  `;
  backdrop.onclick = (e) => { if (e.target === backdrop) backdrop.remove(); };
  document.body.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add('open'));
}

/** A11: 数据来源弹窗 */
function showDataSource() {
  toggleDrawer();
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal-card">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold text-emerald-400 flex items-center gap-2"><span>📡</span>数据来源</h3>
        <button onclick="this.closest('.modal-backdrop').remove()" class="text-slate-400 hover:text-white text-xl">✕</button>
      </div>
      <div class="space-y-3 text-sm text-slate-300">
        <div>
          <div class="font-bold text-white mb-1">赛程 / 球队</div>
          <div class="text-xs text-slate-400">worldcupstats.football + FIFA 官网</div>
        </div>
        <div>
          <div class="font-bold text-white mb-1">Elo 评分</div>
          <div class="text-xs text-slate-400">基于 FIFA 排名近似 + 修正系数</div>
        </div>
        <div>
          <div class="font-bold text-white mb-1">天气</div>
          <div class="text-xs text-slate-400">Open-Meteo（球场本地时区）</div>
        </div>
        <div>
          <div class="font-bold text-white mb-1">比赛事件 / 统计</div>
          <div class="text-xs text-slate-400">人工录入 / 后台管理</div>
        </div>
        <p class="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-800">
          数据仅供参考，不构成投注建议。<br/>
          时区：所有显示时间已转换为北京时间 (UTC+8)
        </p>
      </div>
    </div>
  `;
  backdrop.onclick = (e) => { if (e.target === backdrop) backdrop.remove(); };
  document.body.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add('open'));
}

// ESC 关闭抽屉
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const drawer = document.getElementById('drawer');
    if (drawer && drawer.classList.contains('open')) toggleDrawer();
  }
});

// ============================================
// 🏆 B1 路线图（晋级路线图，2026 美加墨世界杯 48 队）
// ============================================

/** B1: 渲染完整晋级路线图（小组赛 + 32 强 → 冠军） */
async function renderBracket() {
  // 1. 宽屏布局（Cockpit 同款）
  const app = $('#app');
  if (app) {
    app.classList.remove('max-w-2xl');
    app.classList.add('max-w-none');
  }

  // 2. 并发拉数据
  // v0.3.0: 淘汰赛真实数据来自 /api/bracket，小组赛仍来自 /api/groups
  const [bracket, teams, groups, matches] = await Promise.all([
    apiWithRetry('/bracket'),
    apiWithRetry('/teams'),
    apiWithRetry('/groups'),
    apiWithRetry('/matches'),
  ]);

  // 3. 小组赛信息
  const groupMatches = matches.filter(m => m.stage === '小组赛' && m.group_name);
  const rounds = bracket && bracket.rounds ? bracket.rounds : {};

  // 4. 进度统计
  const finished = matches.filter(m => m.status === 'finished').length;
  const live = matches.filter(m => m.status === 'live').length;
  const groupStageFinished = bracket && bracket.group_stage_finished;

  // 5. 渲染
  $('#app').innerHTML = `
    <div class="bracket-page">
      <!-- 顶部：标题 + 控件 -->
      <header class="bracket-header">
        <div>
          <h1 class="bracket-title">
            <span class="text-3xl">🏆</span>
            <span>2026 世界杯晋级路线图</span>
          </h1>
          <p class="bracket-subtitle">
            ${matches.length} 场赛事 · ${teams.length} 支球队 · ${Object.keys(groups).length} 小组
            ${live > 0 ? ` · <span class="text-rose-400">● ${live} 场进行中</span>` : ''}
            ${finished > 0 ? ` · <span class="text-emerald-400">✓ ${finished} 场已完赛</span>` : ''}
            ${groupStageFinished ? ' · <span class="text-emerald-400">32 强已出炉</span>' : ' · <span class="text-amber-400">32 强推演中</span>'}
          </p>
        </div>
        <div class="flex gap-2">
          <button onclick="toggleGroupsCollapse()" class="bracket-tool-btn" id="groups-collapse-btn">
            <span>▾</span><span>小组赛</span>
          </button>
          <button onclick="refreshCurrent()" class="bracket-tool-btn">
            <span>🔄</span><span>刷新</span>
          </button>
        </div>
      </header>

      <!-- 阶段一：12 小组赛（可折叠） -->
      <section id="bracket-groups-section" class="bracket-section">
        <h2 class="bracket-section-title">
          <span class="bracket-stage-dot bg-emerald-500"></span>
          阶段一 · 12 小组赛（${groupMatches.length} 场）
        </h2>
        <p class="bracket-section-hint">▎ 小组赛前 2 名 + 8 个成绩最好的第 3 名晋级 32 强</p>
        <div class="bracket-groups-grid">
          ${Object.keys(groups).sort().map(g => renderBracketGroupCard(g, groups[g])).join('')}
        </div>
      </section>

      <!-- 阶段二：路线图 R32 → 冠军 -->
      <section class="bracket-section">
        <h2 class="bracket-section-title">
          <span class="bracket-stage-dot bg-amber-500"></span>
          阶段二 · 淘汰赛路线图
        </h2>
        <p class="bracket-section-hint">
          ▎ 32 强 → 16 强 → 8 强 → 半决赛 → 决赛 → 冠军
          ${groupStageFinished ? '' : ' · 当前为基于积分榜的推演对阵'}
        </p>

        <div class="bracket-flow">
          ${renderBracketColumnReal('R32 · 32 强', rounds.r32, 16, '等待小组赛结束（6/26 出 32 强）')}
          <div class="bracket-arrow">→</div>
          ${renderBracketColumnReal('R16 · 16 强', rounds.r16, 8, '等待 32 强结果')}
          <div class="bracket-arrow">→</div>
          ${renderBracketColumnReal('QF · 8 强', rounds.qf, 4, '等待 16 强结果')}
          <div class="bracket-arrow">→</div>
          ${renderBracketColumnReal('SF · 半决赛', rounds.sf, 2, '等待 8 强结果')}
          <div class="bracket-arrow">→</div>
          ${renderBracketColumnReal('F · 决赛', rounds.final ? [rounds.final] : [], 1, '等待半决赛结果')}
        </div>

        <!-- 季军赛 + 冠军（独立行） -->
        <div class="bracket-extras">
          ${rounds.third_place ? renderBracketNodeReal(rounds.third_place, '3rd · 季军赛') :
            renderBracketPlaceholder('3rd · 季军赛', '半决赛结束后')}
          <div class="bracket-trophy-card">
            <div class="trophy-icon">🏆</div>
            <div class="trophy-label">CHAMPIONS</div>
            <div class="trophy-hint">决赛胜方</div>
          </div>
        </div>
      </section>

      <!-- 底部说明 -->
      <footer class="bracket-footer">
        <p>💡 提示：点击任意节点跳转比赛详情 · 数据每 5 分钟自动同步</p>
        <p class="bracket-footer-meta">数据源：${escapeHtml(matches[0]?.data_source || 'worldcupstats.football')} · 最后更新 ${beijingNowString()}</p>
      </footer>
    </div>
  `;
}

/** B1: 渲染单个小组卡（4 队 + 排名色阶） */
function renderBracketGroupCard(groupName, rows) {
  if (!rows || !rows.length) {
    return `<div class="bracket-group-card state-card-empty">
      <div class="bracket-group-name">${groupName}组</div>
      <div class="text-xs text-slate-500">无数据</div>
    </div>`;
  }
  const sorted = rows.slice(0, 4);
  return `
    <a href="#/groups" class="bracket-group-card">
      <div class="bracket-group-name">${groupName}组</div>
      <div class="bracket-group-teams">
        ${sorted.map((r, i) => {
          const pos = i + 1;
          const colorMap = {
            1: { bg: 'bg-emerald-500/25', text: 'text-emerald-300', border: 'border-l-emerald-400' },
            2: { bg: 'bg-emerald-500/10', text: 'text-emerald-400/80', border: 'border-l-emerald-500/60' },
            3: { bg: 'bg-blue-500/15', text: 'text-blue-300', border: 'border-l-blue-400' },
            4: { bg: 'bg-rose-500/10', text: 'text-rose-300/70', border: 'border-l-rose-500/60' },
          };
          const c = colorMap[pos];
          return `
            <div class="bracket-group-team ${c.bg} ${c.border}">
              <span class="bracket-group-team-rank ${c.text}">${pos}</span>
              <span class="team-flag text-sm">${r.team.flag_emoji || '🏳️'}</span>
              <span class="bracket-group-team-name ${c.text}">${escapeHtml(r.team.name_zh)}</span>
              <span class="bracket-group-team-pts ${c.text}">${r.points}</span>
            </div>
          `;
        }).join('')}
      </div>
    </a>
  `;
}

/** B1: 渲染一列节点（R32 16 个 / R16 8 个 / QF 4 个 / SF 2 个 / F 1 个）
 *  整列无真实球队数据时 → 用汇总卡片代替 16 个 TBD 节点（视觉更优雅） */
function renderBracketColumn(label, matches, expectedCount, placeholderHint) {
  const safeMatches = matches || [];
  // 检测：本列是否有"真实球队"的比赛
  const realMatches = safeMatches.filter(m =>
    m && (m.home_team?.name_zh || m.away_team?.name_zh)
  );

  // 整列无真实数据 → 汇总卡片（如 R32 已知时空 / R16+ 完全未排定）
  if (realMatches.length === 0) {
    return renderBracketColumnSummary(label, safeMatches, expectedCount, placeholderHint);
  }

  // 有真实数据 → 逐个渲染节点，空槽用 placeholder 补齐
  const slots = [];
  let realIdx = 0;
  for (let i = 0; i < expectedCount; i++) {
    const m = realMatches[realIdx];
    if (m) {
      slots.push(renderBracketNode(m, `${label.split(' ')[0]} #${i + 1}`));
      realIdx++;
    } else {
      slots.push(renderBracketPlaceholder(`${label.split(' ')[0]} #${i + 1}`, placeholderHint));
    }
  }
  return `
    <div class="bracket-col">
      <div class="bracket-col-header">${label}</div>
      <div class="bracket-col-nodes bracket-col-count-${expectedCount}">
        ${slots.join('')}
      </div>
    </div>
  `;
}

/** B1: 渲染整列汇总卡片（R32 已知时空 / R16+ 完全未排定） */
function renderBracketColumnSummary(label, matches, expectedCount, placeholderHint) {
  const count = matches.length || expectedCount;
  // 用 expectedCount 数字映射阶段 emoji（更稳健，不依赖 label 文本格式）
  const stageEmojis = {
    16: '⏳',  // 32 强（16 场对决）
     8: '🕒',  // 16 强（8 场）
     4: '🎯',  // 8 强 / 四分之一决赛（4 场）
     2: '🔥',  // 半决赛（2 场）
     1: '🏆',  // 决赛（1 场）
  };
  const emoji = stageEmojis[expectedCount] || '⏳';

  // 计算时间范围（从已有 match.kickoff_at）
  const times = matches
    .map(m => m && m.kickoff_at)
    .filter(Boolean)
    .map(s => new Date(s))
    .filter(d => !isNaN(d.getTime()))
    .sort((a, b) => a - b);
  let rangeText = '';
  if (times.length >= 2) {
    const fmt = d => `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    rangeText = `${fmt(times[0])} ~ ${fmt(times[times.length - 1])}`;
  } else if (times.length === 1) {
    rangeText = `${String(times[0].getMonth() + 1).padStart(2, '0')}-${String(times[0].getDate()).padStart(2, '0')}`;
  }

  // 提取场地（去重，最多 3 个）
  const stadiums = Array.from(new Set(
    matches.map(m => m && m.stadium && m.stadium.name_zh).filter(Boolean)
  )).slice(0, 3);

  // 文案根据数据丰富度
  let titleText, metaText;
  if (times.length > 0) {
    // 已知时空（R32 起所有阶段都已公布时间）
    titleText = `${count} 场已排定`;
    // 用 expectedCount 推断等待谁的结果
    const waitHints = {
      16: '等待小组赛结束（6/26 出 32 强）',
       8: '等待 32 强结果',
       4: '等待 16 强结果',
       2: '等待 8 强结果',
       1: '等待半决赛结果',
    };
    metaText = waitHints[expectedCount] || '对阵待定';
  } else {
    // 完全未排定（兜底，正常不应进入此分支）
    titleText = `${count} 场待开赛`;
    metaText = '十六强赛起 6 月 28 日陆续开打';
  }

  return `
    <div class="bracket-col">
      <div class="bracket-col-header">${label}</div>
      <div class="bracket-col-summary">
        <div class="bracket-col-summary-card">
          <div class="summary-emoji">${emoji}</div>
          <div class="summary-title">${titleText}</div>
          ${rangeText ? `<div class="summary-range">📅 ${rangeText}</div>` : ''}
          <div class="summary-meta">${metaText}</div>
          ${stadiums.length > 0 ? `
            <div class="summary-stadium">
              <span>🏟</span>
              <span>${stadiums.join(' · ')}</span>
            </div>` : ''}
        </div>
      </div>
    </div>
  `;
}

/** B1: 渲染单个比赛节点 */
function renderBracketNode(m, positionLabel) {
  // 区分两种"未确定"状态：
  // 1. R32 已排定比赛（有时间+场地，无球队）→ 走"已知时空"风格
  // 2. R16+ 完全无数据 → 走 placeholder
  const isScheduledUnknown = !m.home_team && !m.away_team && m.kickoff_at;

  const home = m.home_team || { name_zh: 'TBD', flag_emoji: '🏳️' };
  const away = m.away_team || { name_zh: 'TBD', flag_emoji: '🏳️' };
  const isFinished = m.status === 'finished' || (m.home_score !== null && m.away_score !== null);
  const isLive = m.status === 'live';
  const homeWin = isFinished && m.home_score > m.away_score;
  const awayWin = isFinished && m.away_score > m.home_score;

  let timeText = '';
  if (m.kickoff_at) {
    try {
      const tz = (m.stadium && m.stadium.timezone) || 'UTC';
      timeText = fmtBeijingFromTZ(m.kickoff_at, tz, true);
    } catch (e) {
      timeText = new Date(m.kickoff_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
    }
  }

  // 状态色边框
  let statusBorder = 'border-slate-800';
  let statusBg = 'bg-slate-900';
  let statusBadge = '';
  if (isLive) {
    statusBorder = 'border-rose-500 bracket-pulse';
    statusBadge = '<span class="bracket-status-badge bg-rose-500 text-white">● LIVE</span>';
  } else if (isFinished) {
    statusBorder = 'border-slate-700';
  } else if (isScheduledUnknown) {
    // R32 已排定但 TBD：虚线边 + 琥珀色调，提示"时空已定"
    statusBorder = 'border-amber-700/60 border-dashed';
    statusBg = 'bg-slate-900/60';
  } else {
    statusBorder = 'border-slate-800 border-dashed';
  }

  // 节点底部：R32/R16/QF/SF/F 已排定比赛显示"📍 场地 · 城市" 真实信息
  let nodeFoot = '';
  if (isScheduledUnknown) {
    const stName = m.stadium?.name_zh;
    const stCity = m.stadium?.city_zh;
    if (stName && stCity) {
      nodeFoot = `<div class="bracket-node-foot-scheduled">📍 ${escapeHtml(stName)} · ${escapeHtml(stCity)}</div>`;
    } else if (stName) {
      nodeFoot = `<div class="bracket-node-foot-scheduled">📍 ${escapeHtml(stName)}</div>`;
    }
  }

  const linkHref = isScheduledUnknown ? '#/bracket' : `#/match/${m.id}`;

  return `
    <a href="${linkHref}" class="bracket-node ${statusBorder} ${statusBg}" title="${escapeHtml(positionLabel)} · ${escapeHtml(home.name_zh)} vs ${escapeHtml(away.name_zh)}">
      <div class="bracket-node-head">
        <span class="bracket-node-pos">${escapeHtml(positionLabel)}</span>
        ${statusBadge || `<span class="bracket-node-time">${escapeHtml(timeText)}</span>`}
      </div>
      <div class="bracket-node-body">
        <div class="bracket-node-team ${homeWin ? 'bracket-node-winner' : ''} ${isFinished && !homeWin ? 'bracket-node-loser' : ''}">
          <span class="team-flag text-base">${home.flag_emoji || '🏳️'}</span>
          <span class="bracket-node-team-name">${escapeHtml(home.name_zh)}</span>
          <span class="bracket-node-score">${isFinished ? m.home_score : ''}</span>
        </div>
        <div class="bracket-node-team ${awayWin ? 'bracket-node-winner' : ''} ${isFinished && !awayWin ? 'bracket-node-loser' : ''}">
          <span class="team-flag text-base">${away.flag_emoji || '🏳️'}</span>
          <span class="bracket-node-team-name">${escapeHtml(away.name_zh)}</span>
          <span class="bracket-node-score">${isFinished ? m.away_score : ''}</span>
        </div>
      </div>
      ${nodeFoot}
    </a>
  `;
}

/** v0.3.0: 渲染基于 /api/bracket 真实数据的整列 */
function renderBracketColumnReal(label, matches, expectedCount, placeholderHint) {
  const safeMatches = matches || [];
  // 检测：本列是否有"真实球队"的比赛（bracket API 中 team 非空）
  const realMatches = safeMatches.filter(m =>
    m && (m.home?.team?.name_zh || m.away?.team?.name_zh)
  );

  // 整列无真实数据 → 汇总卡片
  if (realMatches.length === 0) {
    return renderBracketColumnSummary(label, safeMatches, expectedCount, placeholderHint);
  }

  // 有真实数据 → 逐个渲染节点，空槽用 placeholder 补齐
  const slots = [];
  for (let i = 0; i < expectedCount; i++) {
    const m = safeMatches[i];
    if (m) {
      slots.push(renderBracketNodeReal(m, `${label.split(' ')[0]} #${i + 1}`));
    } else {
      slots.push(renderBracketPlaceholder(`${label.split(' ')[0]} #${i + 1}`, placeholderHint));
    }
  }
  return `
    <div class="bracket-col">
      <div class="bracket-col-header">${label}</div>
      <div class="bracket-col-nodes bracket-col-count-${expectedCount}">
        ${slots.join('')}
      </div>
    </div>
  `;
}

/** v0.3.0: 渲染基于 /api/bracket 真实数据的单个节点 */
function renderBracketNodeReal(m, positionLabel) {
  const home = m.home?.team || { name_zh: m.home?.placeholder || 'TBD', flag_emoji: '🏳️' };
  const away = m.away?.team || { name_zh: m.away?.placeholder || 'TBD', flag_emoji: '🏳️' };
  const homeSource = m.home?.source || '';
  const awaySource = m.away?.source || '';
  const isDetermined = m.home?.team && m.away?.team;
  const isFinished = m.status === 'finished' || (m.home_score !== null && m.away_score !== null);
  const homeWin = isFinished && m.home_score > m.away_score;
  const awayWin = isFinished && m.away_score > m.home_score;

  let timeText = '';
  if (m.kickoff_at) {
    try {
      timeText = new Date(m.kickoff_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
    } catch (e) {
      timeText = '';
    }
  }

  // 状态色边框
  let statusBorder = 'border-slate-800';
  let statusBg = 'bg-slate-900';
  if (isFinished) {
    statusBorder = 'border-slate-700';
  } else if (!isDetermined) {
    statusBorder = 'border-amber-700/60 border-dashed';
    statusBg = 'bg-slate-900/60';
  }

  // Elo 预测概率条（仅双方球队都确定时显示）
  let probBar = '';
  const p = m.prediction;
  if (isDetermined && p && (p.home_win > 0 || p.draw > 0 || p.away_win > 0)) {
    const homePct = Math.round(p.home_win * 100);
    const drawPct = Math.round(p.draw * 100);
    const awayPct = 100 - homePct - drawPct;
    probBar = `
      <div class="bracket-prob-bar">
        <div class="bracket-prob-seg bracket-prob-home" style="width:${homePct}%"></div>
        <div class="bracket-prob-seg bracket-prob-draw" style="width:${drawPct}%"></div>
        <div class="bracket-prob-seg bracket-prob-away" style="width:${awayPct}%"></div>
      </div>
      <div class="bracket-prob-labels">
        <span class="bracket-prob-home-text">${homePct}%</span>
        <span class="bracket-prob-draw-text">平 ${drawPct}%</span>
        <span class="bracket-prob-away-text">${awayPct}%</span>
      </div>
    `;
  }

  const linkHref = isDetermined && m.match_number ? `#/match/${m.match_number}` : '#/bracket';

  return `
    <a href="${linkHref}" class="bracket-node ${statusBorder} ${statusBg}" title="${escapeHtml(positionLabel)} · ${escapeHtml(home.name_zh)} vs ${escapeHtml(away.name_zh)}">
      <div class="bracket-node-head">
        <span class="bracket-node-pos">${escapeHtml(positionLabel)}</span>
        <span class="bracket-node-source">${escapeHtml(homeSource)} vs ${escapeHtml(awaySource)}</span>
      </div>
      <div class="bracket-node-body">
        <div class="bracket-node-team ${homeWin ? 'bracket-node-winner' : ''} ${isFinished && !homeWin ? 'bracket-node-loser' : ''}">
          <span class="team-flag text-base">${home.flag_emoji || '🏳️'}</span>
          <span class="bracket-node-team-name">${escapeHtml(home.name_zh)}</span>
          <span class="bracket-node-score">${isFinished ? m.home_score : ''}</span>
        </div>
        <div class="bracket-node-team ${awayWin ? 'bracket-node-winner' : ''} ${isFinished && !awayWin ? 'bracket-node-loser' : ''}">
          <span class="team-flag text-base">${away.flag_emoji || '🏳️'}</span>
          <span class="bracket-node-team-name">${escapeHtml(away.name_zh)}</span>
          <span class="bracket-node-score">${isFinished ? m.away_score : ''}</span>
        </div>
      </div>
      ${probBar}
      ${timeText ? `<div class="bracket-node-foot-scheduled">📅 ${escapeHtml(timeText)}</div>` : ''}
    </a>
  `;
}

/**
 * P1.3 主页: 历史交锋（选队 + 对手列表）.
 *
 * 入口:
 *  - 抽屉菜单 "⚔️ 历史交锋"（#69/73 已规划，P1.3 阶段实现）
 *  - 选队 select → 调 /api/teams/{code}/h2h-opponents 拿对手列表
 *  - 对手卡片点击 → 跳转 #/h2h/{code}/{opp_code} 详情页（renderH2HDetail）
 *
 * URL: #/h2h
 * 数据: GET /api/teams?limit=48（48 队下拉）+ GET /api/teams/{code}/h2h-opponents
 */
async function renderH2H() {
  const app = $('#app');
  app.classList.remove('max-w-2xl');
  app.classList.add('max-w-none', 'px-4');

  let teams;
  try {
    teams = await apiWithRetry('/teams?limit=48');
  } catch (err) {
    app.classList.add('max-w-2xl');
    app.classList.remove('max-w-none');
    $('#app').innerHTML = renderError(err, renderH2H);
    return;
  }

  // 默认选 BRA（如果存在），否则选第一队
  const defaultCode = teams.find(t => t.fifa_code === 'BRA')
    ? 'BRA'
    : (teams[0] ? teams[0].fifa_code : 'BRA');

  app.innerHTML = `
    <!-- 顶栏 -->
    <div class="cockpit-header flex items-center justify-between mb-4 px-1">
      <div class="flex items-center gap-3">
        <span class="text-2xl">⚔️</span>
        <div>
          <div class="text-xl font-bold text-emerald-400">历史交锋</div>
          <div class="text-xs text-slate-500">39 队 · 109 对历史对决 · 2018+2022 世界杯种子 + 2026 已完赛</div>
        </div>
      </div>
    </div>

    <!-- 选队 select -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">🎯 选择球队</h2>
      <div class="bg-slate-900 rounded-xl p-3 border border-slate-800">
        <label class="text-xs text-slate-500 mb-1 block">查看该队与所有对手的历史交锋</label>
        <select id="h2h-team-select" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none">
          ${teams.map(t => `<option value="${t.fifa_code}" ${t.fifa_code === defaultCode ? 'selected' : ''}>${t.flag_emoji || '🏳️'} ${escapeHtml(t.name_zh)} (${t.fifa_code} · ${t.group_name || '-'})</option>`).join('')}
        </select>
      </div>
    </section>

    <!-- 对手列表 -->
    <section class="cockpit-section mb-4">
      <h2 class="cockpit-section-title">📜 对手列表</h2>
      <div id="h2h-opponents-list">
        <div class="text-slate-500 text-sm text-center py-4">加载对手列表...</div>
      </div>
    </section>

    <!-- 数据状态 -->
    <div class="text-center text-xs text-slate-600 py-2">
      数据源 · 2018+2022 世界杯种子（${'(111)'} 场）+ 2026 已完赛（${'(4)'} 场）· 共 <span id="h2h-total">--</span> 对不同对决
    </div>
  `;

  // 渲染对手列表（默认球队）
  await _renderH2HList(defaultCode);

  // 绑定 select 变化
  setTimeout(() => {
    const sel = document.getElementById('h2h-team-select');
    if (!sel) return;
    sel.addEventListener('change', () => _renderH2HList(sel.value));
  }, 50);
}

/**
 * P1.3 内部: 渲染指定球队的对手列表.
 */
async function _renderH2HList(teamCode) {
  const listEl = document.getElementById('h2h-opponents-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="text-slate-500 text-sm text-center py-4">加载对手列表...</div>';

  let data;
  try {
    data = await apiWithRetry('/teams/' + encodeURIComponent(teamCode) + '/h2h-opponents');
  } catch (err) {
    listEl.innerHTML = renderError(err, () => _renderH2HList(teamCode));
    return;
  }

  if (!data.opponents || data.opponents.length === 0) {
    listEl.innerHTML = '<div class="bg-slate-900 rounded-xl p-8 text-center border border-slate-800"><div class="text-4xl mb-2">🤷</div><div class="text-slate-400">该队暂无历史交锋对手</div><div class="text-xs text-slate-600 mt-1">（2018+2022 世界杯 + 2026 已完赛范围内）</div></div>';
    // 更新 total
    const totalEl = document.getElementById('h2h-total');
    if (totalEl) totalEl.textContent = '0';
    return;
  }

  // 更新 total
  const totalEl = document.getElementById('h2h-total');
  if (totalEl) totalEl.textContent = data.opponents_count;

  listEl.innerHTML = `
    <div class="text-xs text-slate-500 mb-2">▎ 共 ${data.opponents_count} 个对手（按对决数倒序）</div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      ${data.opponents.map(o => `
        <a href="#/h2h/${teamCode}/${o.fifa_code}" class="block bg-slate-900 border border-slate-800 rounded-xl p-3 hover:border-emerald-700 hover:bg-slate-800 transition">
          <div class="flex items-center justify-between mb-1">
            <div class="flex items-center gap-2 min-w-0 flex-1">
              <span class="text-2xl shrink-0">${o.flag_emoji || '🏳️'}</span>
              <div class="min-w-0">
                <div class="text-sm font-bold text-slate-200 truncate">${escapeHtml(o.name_zh)}</div>
                <div class="text-xs text-slate-500 truncate">${o.fifa_code}${o.name_en ? ' · ' + escapeHtml(o.name_en) : ''}</div>
              </div>
            </div>
            <div class="text-right shrink-0 ml-2">
              <div class="text-2xl font-bold text-emerald-400">${o.matches_count}</div>
              <div class="text-[10px] text-slate-500">对决</div>
            </div>
          </div>
          <div class="text-xs text-slate-400 mt-1 text-right">点击查看完整历史 →</div>
        </a>
      `).join('')}
    </div>
  `;
}

/**
 * P1.3 详情页: 历史交锋详情页 — 显示两队所有直接对决的完整列表 + 胜负条
 *
 * 入口:
 *  - P1.3 主页对手卡片点击
 *  - match detail 页 H2H 卡片右上 "📜 完整历史 →" 链接
 *
 * URL: #/h2h/{code1}/{code2}
 * 数据: GET /api/h2h/{code1}/{code2}
 */
async function renderH2HDetail(code1, code2) {
  // 顶部加 padding（与 Cockpit 一致）
  const app = $('#app');
  app.classList.remove('max-w-2xl');
  app.classList.add('max-w-none', 'px-4');

  let data;
  try {
    data = await apiWithRetry('/h2h/' + encodeURIComponent(code1) + '/' + encodeURIComponent(code2));
  } catch (err) {
    app.innerHTML = renderError(err, () => renderH2HDetail(code1, code2));
    return;
  }

  const { code1_team, code2_team, summary, matches } = data;
  const t1 = code1_team, t2 = code2_team;

  // 胜负条（基于 code1 视角）
  const total = Math.max(1, summary.total);
  const w1Pct = (summary.code1_wins / total * 100).toFixed(1);
  const dPct = (summary.draws / total * 100).toFixed(1);
  const w2Pct = (summary.code2_wins / total * 100).toFixed(1);

  // 来源标签
  const sourceParts = [];
  if (summary.current_2026 > 0) sourceParts.push(`本届 ${summary.current_2026} 场`);
  if (summary.history > 0) sourceParts.push(`2018+2022 世界杯 ${summary.history} 场`);
  const sourceLabel = sourceParts.length ? sourceParts.join(' · ') : '暂无数据';

  // 场次列表（按日期倒序，已经 server 排序好）
  const matchesHtml = matches.length === 0
    ? `<div class="bg-slate-900 rounded-xl p-8 text-center border border-slate-800">
         <div class="text-4xl mb-2">🤝</div>
         <div class="text-slate-400">两队暂无历史交锋数据</div>
         <div class="text-xs text-slate-600 mt-1">（2018+2022 世界杯 + 2026 已完赛）</div>
       </div>`
    : matches.map(m => {
        // 比分：从 code1 视角展示
        const c1ScoreColor = m.code1_won ? 'text-emerald-400' : m.draw ? 'text-slate-300' : 'text-rose-400';
        const c2ScoreColor = m.code2_won ? 'text-emerald-400' : m.draw ? 'text-slate-300' : 'text-rose-400';
        const homeTag = m.is_code1_home
          ? `<span class="text-xs text-amber-300 ml-1">(主)</span>`
          : `<span class="text-xs text-slate-500 ml-1">(客)</span>`;
        const sourceTag = m.source === 'current_2026'
          ? `<span class="text-xs px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-300">本届</span>`
          : `<span class="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">历史</span>`;
        return `
          <div class="bg-slate-900 rounded-xl p-3 border border-slate-800 flex items-center gap-3">
            <div class="text-center min-w-[60px]">
              <div class="text-xs text-slate-500">${m.match_date.slice(0, 10)}</div>
              <div class="text-[10px] text-slate-600">${m.match_date.slice(11, 16) || ''}</div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs text-slate-500">${escapeHtml(m.competition || '')}</span>
                <span class="text-xs text-slate-600">·</span>
                <span class="text-xs text-slate-400">${escapeHtml(m.stage || '')}</span>
              </div>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-sm font-bold ${c1ScoreColor}">${m.code1_score}</span>
                <span class="text-slate-500">-</span>
                <span class="text-sm font-bold ${c2ScoreColor}">${m.code2_score}</span>
                <span class="text-xs text-slate-500">${escapeHtml(t1.flag_emoji)} ${escapeHtml(t1.name_zh)}</span>
                <span class="text-xs text-slate-600">vs</span>
                <span class="text-xs text-slate-500">${escapeHtml(t2.flag_emoji)} ${escapeHtml(t2.name_zh)}${homeTag}</span>
              </div>
            </div>
            <div class="text-right">
              ${sourceTag}
              <div class="text-[10px] text-slate-600 mt-1">${m.code1_won ? '①胜' : m.draw ? '平' : '①负'}</div>
            </div>
          </div>
        `;
      }).join('');

  app.innerHTML = `
    <!-- P1.3: 返回按钮 -->
    <div class="mb-3">
      <a href="javascript:history.back()" class="text-sm text-slate-400 hover:text-emerald-400 transition flex items-center gap-1">
        <span>←</span><span>返回</span>
      </a>
    </div>

    <!-- P1.3: 头部两队对比 -->
    <div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-5 border border-slate-700 mb-4">
      <div class="text-center mb-3">
        <div class="text-xs text-slate-500 mb-1">⚔️ 历史交锋详情</div>
        <h1 class="text-2xl font-bold text-white">
          <span>${escapeHtml(t1.flag_emoji || '🏳️')} ${escapeHtml(t1.name_zh)}</span>
          <span class="text-slate-500 mx-2">VS</span>
          <span>${escapeHtml(t2.flag_emoji || '🏳️')} ${escapeHtml(t2.name_zh)}</span>
        </h1>
        <div class="text-xs text-slate-500 mt-1">
          ${escapeHtml(t1.name_en)} (${t1.fifa_code}) vs ${escapeHtml(t2.name_en)} (${t2.fifa_code})
        </div>
      </div>

      <!-- 胜负条（基于 code1 视角） -->
      ${summary.total > 0 ? `
        <div class="mt-4">
          <div class="flex items-center justify-between text-xs mb-1.5">
            <span class="text-emerald-400 font-bold">${escapeHtml(t1.name_zh)} ${summary.code1_wins} 胜</span>
            <span class="text-slate-400">${summary.draws} 平</span>
            <span class="text-rose-400 font-bold">${summary.code2_wins} 胜 ${escapeHtml(t2.name_zh)}</span>
          </div>
          <div class="h-3 bg-slate-800 rounded-full overflow-hidden flex">
            <div class="bg-emerald-500 transition-all" style="width: ${w1Pct}%"></div>
            <div class="bg-slate-600 transition-all" style="width: ${dPct}%"></div>
            <div class="bg-rose-500 transition-all" style="width: ${w2Pct}%"></div>
          </div>
          <div class="text-center text-xs text-slate-500 mt-2">
            共 ${summary.total} 场（${sourceLabel}）
          </div>
        </div>
      ` : `
        <div class="text-center text-sm text-slate-500 mt-4">两队暂无历史交锋</div>
      `}
    </div>

    <!-- P1.3: 场次列表 -->
    <h2 class="text-lg font-bold mb-3">📜 完整交锋记录（${summary.total} 场）</h2>
    <div class="space-y-2">
      ${matchesHtml}
    </div>

    <div class="mt-4 text-center text-xs text-slate-600">
      数据基础：2018 + 2022 世界杯 + 2026 完赛场次
    </div>
  `;
}

/** B1: 渲染占位节点（"等待前序结果"） */
function renderBracketPlaceholder(positionLabel, hint) {
  return `
    <div class="bracket-node bracket-node-placeholder" title="${escapeHtml(positionLabel)} · ${escapeHtml(hint)}">
      <div class="bracket-node-head">
        <span class="bracket-node-pos">${escapeHtml(positionLabel)}</span>
        <span class="bracket-node-time text-slate-600">⏳</span>
      </div>
      <div class="bracket-node-body">
        <div class="bracket-node-team-placeholder">
          <span class="bracket-node-team-name text-slate-600 italic">TBD</span>
        </div>
        <div class="bracket-node-team-placeholder">
          <span class="bracket-node-team-name text-slate-600 italic">TBD</span>
        </div>
      </div>
      <div class="bracket-node-foot">${escapeHtml(hint)}</div>
    </div>
  `;
}

/** B1: 折叠/展开 12 小组赛面板 */
let _bracketGroupsCollapsed = false;
function toggleGroupsCollapse() {
  _bracketGroupsCollapsed = !_bracketGroupsCollapsed;
  const sec = document.getElementById('bracket-groups-section');
  const btn = document.getElementById('groups-collapse-btn');
  if (!sec || !btn) return;
  if (_bracketGroupsCollapsed) {
    sec.classList.add('bracket-collapsed');
    btn.querySelector('span:first-child').textContent = '▸';
  } else {
    sec.classList.remove('bracket-collapsed');
    btn.querySelector('span:first-child').textContent = '▾';
  }
}

const routes = {
  '/': renderHome,
  '/cockpit': renderCockpit,
  '/dashboard': renderCockpit,  // v0.6.0: 新别名, 同 cockpit
  '/bracket': renderBracket,
  '/schedule': renderSchedule,
  '/groups': renderGroups,
  '/teams': renderTeams,
  '/elo': renderElo,
  '/h2h': renderH2H,
  '/simulator': renderSimulator,
  '/odds': renderOdds,
  '/accuracy': renderAccuracy,  // v0.6.0: 准确率 dashboard
  '/health': renderHealth,  // v0.6.0: 数据源健康
};

/** 把当前 hash 映射到对应的骨架屏类型 */
function skeletonTypeForHash(hash) {
  if (hash.startsWith('/match/')) return 'match-detail';
  if (hash.startsWith('/team/')) return 'team-detail';
  if (hash.startsWith('/h2h/')) return 'h2h-detail';
  return {
    '/': 'home',
    '/cockpit': 'cockpit',
    '/bracket': 'bracket',
    '/schedule': 'schedule',
    '/groups': 'groups',
    '/teams': 'teams',
    '/elo': 'elo',
    '/h2h': 'h2h',
    '/simulator': 'simulator',
    '/odds': 'generic',
  }[hash] || 'generic';
}

async function router() {
  const hash = location.hash.slice(1) || '/';
  // 还原默认宽度（cockpit 会自己重设）
  if (hash !== '/cockpit') restoreAppWidth();
  // A9: 先显示骨架屏
  showSkeleton(skeletonTypeForHash(hash));
  try {
    if (hash.startsWith('/match/')) {
      await renderMatchDetail(hash.split('/')[2]);
    } else if (hash.startsWith('/team/')) {
      await renderTeamDetail(hash.split('/')[2]);
    } else if (hash.startsWith('/h2h/')) {
      // P1.3: /h2h/{code1}/{code2}
      const parts = hash.split('/');
      // [' , 'h2h', code1, code2]
      await renderH2HDetail(parts[2], parts[3]);
    } else if (routes[hash]) {
      await routes[hash]();
    } else {
      // A8: 404 页
      $('#app').innerHTML = renderNotFound();
    }
  } catch (err) {
    // A10: 错误页（含重试）
    $('#app').innerHTML = renderError(err, router);
    console.error('[router]', hash, err);
  }
}

window.addEventListener('hashchange', router);
window.addEventListener('DOMContentLoaded', router);

// ============================================================
// v0.6.0 新增 - 准确率 dashboard
// ============================================================

async function renderAccuracy() {
  // 顶部 KPI
  const [all, glicko2, v1elo] = await Promise.all([
    apiWithRetry('/elo/accuracy-stats'),
    apiWithRetry('/elo/accuracy-stats?model_version=v3_glicko2'),
    apiWithRetry('/elo/accuracy-stats?model_version=v1_elo'),
  ]);
  const [bias, g2Metrics] = await Promise.all([
    apiWithRetry('/elo/top-bias?model_version=v3_glicko2&n=5'),
    apiWithRetry('/elo/glicko2-metrics'),
  ]);

  const overallColor = (acc) => acc == null ? '#999' : acc >= 0.60 ? '#16a34a' : acc >= 0.55 ? '#d97706' : '#dc2626';
  const modelCard = (label, m, color) => `
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
      <div class="text-xs text-slate-500 mb-1">${label}</div>
      <div class="text-3xl font-bold" style="color:${overallColor(m.accuracy)}">${m.accuracy == null ? '—' : (m.accuracy * 100).toFixed(1) + '%'}</div>
      <div class="text-xs text-slate-500 mt-2">n_settled=${m.n_settled} / n_total=${m.n_total}</div>
      <div class="grid grid-cols-3 gap-2 mt-3 text-xs">
        <div><div class="text-slate-400">RPS</div><div class="font-semibold">${m.rps == null ? '—' : m.rps.toFixed(4)}</div></div>
        <div><div class="text-slate-400">Brier</div><div class="font-semibold">${m.brier == null ? '—' : m.brier.toFixed(4)}</div></div>
        <div><div class="text-slate-400">LogLoss</div><div class="font-semibold">${m.log_loss == null ? '—' : m.log_loss.toFixed(4)}</div></div>
      </div>
    </div>
  `;

  const compareRow = (label, m, _order) => {
    if (!m || m.n_settled == null) {
      return `<tr class="border-t border-slate-100 text-slate-400">
        <td class="py-2">${label}</td>
        <td class="text-right">—</td><td class="text-right">—</td><td class="text-right">—</td><td class="text-right">—</td><td class="text-right">—</td>
        <td class="text-center"><span class="text-xs px-2 py-0.5 bg-slate-100 rounded">无数据</span></td>
      </tr>`;
    }
    const acc = m.accuracy;
    const rating = acc == null ? '无数据'
      : acc >= 0.60 ? { txt: '优', cls: 'bg-emerald-100 text-emerald-700' }
      : acc >= 0.55 ? { txt: '良', cls: 'bg-amber-100 text-amber-700' }
      : { txt: '待优化', cls: 'bg-rose-100 text-rose-700' };
    const accColor = acc == null ? 'text-slate-400'
      : acc >= 0.60 ? 'text-emerald-700 font-bold'
      : acc >= 0.55 ? 'text-amber-700 font-bold'
      : 'text-rose-700 font-bold';
    return `<tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="py-2 font-medium">${label}</td>
      <td class="text-right font-mono">${m.n_settled}</td>
      <td class="text-right font-mono ${accColor}">${acc == null ? '—' : (acc * 100).toFixed(1) + '%'}</td>
      <td class="text-right font-mono text-slate-600">${m.rps == null ? '—' : m.rps.toFixed(4)}</td>
      <td class="text-right font-mono text-slate-600">${m.brier == null ? '—' : m.brier.toFixed(4)}</td>
      <td class="text-right font-mono text-slate-600">${m.log_loss == null ? '—' : m.log_loss.toFixed(4)}</td>
      <td class="text-center"><span class="text-xs px-2 py-0.5 rounded ${rating.cls || 'bg-slate-100 text-slate-500'}">${rating.txt}</span></td>
    </tr>`;
  };

  const byOutcomeRows = (byOut) => {
    const order = ['home', 'draw', 'away'];
    const label = {home: '🏠 主胜', draw: '🤝 平局', away: '✈️ 客胜'};
    return order.map(o => {
      const x = byOut[o];
      return `<tr class="border-t border-slate-100"><td class="py-2">${label[o]}</td><td>${x ? x.n : 0}</td><td>${x ? (x.accuracy * 100).toFixed(1) + '%' : '—'}</td></tr>`;
    }).join('');
  };

  const byModelRows = (byModel) => Object.entries(byModel).map(([k, v]) => `
    <tr class="border-t border-slate-100">
      <td class="py-2 font-mono text-xs">${k}</td>
      <td>${v.n}</td>
      <td>${(v.accuracy * 100).toFixed(1)}%</td>
      <td>${v.brier.toFixed(4)}</td>
      <td>${v.log_loss.toFixed(4)}</td>
    </tr>
  `).join('');

  const biasRows = (bias || []).map(b => {
    const surprisePct = (b.surprise_score * 100).toFixed(0);
    return `<tr class="border-t border-slate-100">
      <td class="py-2">#${b.match_id}</td>
      <td><span class="font-mono">${b.predicted_outcome}</span></td>
      <td><span class="font-mono">${b.actual_outcome}</span></td>
      <td>${(b.confidence * 100).toFixed(1)}%</td>
      <td>${(b.actual_p * 100).toFixed(1)}%</td>
      <td><span class="text-red-600 font-semibold">${surprisePct}%</span></td>
    </tr>`;
  }).join('');

  $('#app').innerHTML = `
    <div class="max-w-6xl mx-auto p-4">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-slate-800">📊 预测准确率 Dashboard</h1>
        <a href="#/cockpit" class="text-sm text-blue-600 hover:underline">← 返回驾驶舱</a>
      </div>

      <!-- KPI 行: 3 个模型对比 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        ${modelCard('🧠 全部模型汇总', all, '')}
        ${modelCard('⚡ Glicko-2 (v3, 默认)', glicko2, '')}
        ${modelCard('📊 Elo M1 (v1, 基准)', v1elo, '')}
      </div>

      <!-- 3 模型横评对比表 -->
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4 mb-6">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">📈 3 模型横评对比表</h2>
        <table class="w-full text-sm">
          <thead class="text-xs text-slate-500 border-b-2 border-slate-200">
            <tr>
              <th class="text-left py-2">模型</th>
              <th class="text-right">n_settled</th>
              <th class="text-right">准确率</th>
              <th class="text-right">RPS ↓</th>
              <th class="text-right">Brier ↓</th>
              <th class="text-right">LogLoss ↓</th>
              <th class="text-center">评级</th>
            </tr>
          </thead>
          <tbody>
            ${compareRow('⚡ Glicko-2 (v3, 默认)', glicko2, glicko2.accuracy == null ? 0 : 1)}
            ${compareRow('📊 Elo M1 (v1, 基准)', v1elo, v1elo.accuracy == null ? 0 : 1)}
            ${compareRow('🧠 全部模型汇总 (混合)', all, all.accuracy == null ? 0 : 1)}
          </tbody>
        </table>
        <div class="text-xs text-slate-500 mt-2">
          ▎ ↓ = 越低越好 · 评级: ≥60% 优 / 55-60% 良 / &lt;55% 待优化 · 数据基于 prediction_log 实盘结算
        </div>
      </div>

      <!-- 按 actual_outcome 分组 -->
      ${all.n_settled > 0 ? `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-800 mb-3">按实际结果分组 (全部模型)</h2>
            <table class="w-full text-sm">
              <thead class="text-xs text-slate-500 border-b border-slate-200">
                <tr><th class="text-left py-2">结果</th><th>n</th><th>准确率</th></tr>
              </thead>
              <tbody>${byOutcomeRows(all.by_outcome)}</tbody>
            </table>
          </div>
          <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-800 mb-3">按模型分组 (已结算)</h2>
            <table class="w-full text-sm">
              <thead class="text-xs text-slate-500 border-b border-slate-200">
                <tr><th class="text-left py-2">模型</th><th>n</th><th>Acc</th><th>Brier</th><th>LogLoss</th></tr>
              </thead>
              <tbody>${byModelRows(all.by_model)}</tbody>
            </table>
          </div>
        </div>
      ` : `
        <div class="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center mb-6">
          <div class="text-3xl mb-2">⏳</div>
          <div class="text-slate-700 font-semibold mb-1">暂无已结算预测</div>
          <div class="text-sm text-slate-600">预测日志正在积累中. 已完赛的 MEX 2-0 RSA 比赛将在 15 分钟内被调度器结算.</div>
        </div>
      `}

      <!-- Glicko-2 walk-forward 历史基线 -->
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4 mb-6">
        <h2 class="text-lg font-semibold text-slate-800 mb-2">🎯 Glicko-2 训练基线 (913 场 walk-forward)</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div class="bg-slate-50 p-3 rounded-lg">
            <div class="text-xs text-slate-500">准确率</div>
            <div class="text-2xl font-bold text-slate-800">${(g2Metrics.metrics.accuracy * 100).toFixed(1)}%</div>
          </div>
          <div class="bg-slate-50 p-3 rounded-lg">
            <div class="text-xs text-slate-500">RPS</div>
            <div class="text-2xl font-bold text-slate-800">${g2Metrics.metrics.rps.toFixed(4)}</div>
          </div>
          <div class="bg-slate-50 p-3 rounded-lg">
            <div class="text-xs text-slate-500">Brier</div>
            <div class="text-2xl font-bold text-slate-800">${g2Metrics.metrics.brier.toFixed(4)}</div>
          </div>
          <div class="bg-slate-50 p-3 rounded-lg">
            <div class="text-xs text-slate-500">LogLoss</div>
            <div class="text-2xl font-bold text-slate-800">${g2Metrics.metrics.log_loss.toFixed(4)}</div>
          </div>
        </div>
        <div class="text-xs text-slate-500 mt-3">训练数据: Hicruben 913 场国际赛 (2023-11 ~ 2026-06). 较 Elo M1 准确率提升 <span class="text-green-600 font-bold">+${((g2Metrics.metrics.accuracy - 0.5663) * 100).toFixed(1)} pp</span>.</div>
      </div>

      <!-- 偏差分析 -->
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">🚨 Glicko-2 Top 5 偏差场次</h2>
        ${bias && bias.length > 0 ? `
          <table class="w-full text-sm">
            <thead class="text-xs text-slate-500 border-b border-slate-200">
              <tr><th class="text-left py-2">Match</th><th>预测</th><th>实际</th><th>Confidence</th><th>实际P</th><th>Surprise</th></tr>
            </thead>
            <tbody>${biasRows}</tbody>
          </table>
          <div class="text-xs text-slate-500 mt-2">Surprise = 模型 confidence − 实际结果概率. 越大表示越离谱.</div>
        ` : `<div class="text-sm text-slate-500">暂无错误预测 (或全部预测都对了 🎉)</div>`}
      </div>

      <!-- 数据源健康 -->
      <div class="mt-6 bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">🔌 数据源健康</h2>
        <a href="#/health" class="text-sm text-blue-600 hover:underline" onclick="location.hash='#/'; setTimeout(() => location.hash='#/health', 100)">查看 4 源实时状态 →</a>
        <div class="text-xs text-slate-500 mt-2">worldcup26.ir 主源 + football-data.org 增强 + StatsBomb 对比 + worldcupstats.football 备份</div>
      </div>
    </div>
  `;
}

async function renderHealth() {
  // v0.6.0: 数据源健康 dashboard
  let data;
  try {
    data = await apiWithRetry('/api/health/sources');
  } catch (e) {
    $('#app').innerHTML = `<div class="p-8 text-center text-red-600">数据源健康检查失败: ${e.message}</div>`;
    return;
  }
  const statusColor = (s) => s === 'ok' ? 'text-green-600 bg-green-50' : s === 'degraded' ? 'text-amber-600 bg-amber-50' : s === 'timeout' ? 'text-orange-600 bg-orange-50' : 'text-red-600 bg-red-50';
  const statusBadge = (s) => `<span class="px-2 py-0.5 rounded-full text-xs font-bold ${statusColor(s)}">${s.toUpperCase()}</span>`;
  const overallBadge = (o) => {
    const map = {
      all_ok: ['bg-green-100 text-green-800', '✅ 全部正常'],
      minor_issue: ['bg-amber-100 text-amber-800', '⚠️ 小问题'],
      degraded: ['bg-orange-100 text-orange-800', '🟠 降级'],
      critical: ['bg-red-100 text-red-800', '🔴 严重'],
    };
    const [cls, text] = map[o] || ['', o];
    return `<span class="px-3 py-1 rounded-full text-sm font-bold ${cls}">${text}</span>`;
  };
  const sourceCards = (data.sources || []).map(s => `
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4">
      <div class="flex items-start justify-between mb-2">
        <div>
          <div class="font-semibold text-slate-800 text-sm">${s.name}</div>
          <div class="text-xs text-slate-500 mt-1">${s.description || ''}</div>
        </div>
        ${statusBadge(s.status)}
      </div>
      <div class="grid grid-cols-3 gap-2 text-xs text-slate-600 mt-3">
        <div><span class="text-slate-400">延迟</span><br><span class="font-mono">${s.latency_ms}ms</span></div>
        <div><span class="text-slate-400">状态码</span><br><span class="font-mono">${s.status_code || '—'}</span></div>
        <div><span class="text-slate-400">类型</span><br><span class="font-mono">${s.type}</span></div>
      </div>
      ${s.requires_token ? '<div class="text-xs text-amber-600 mt-2">🔑 需要 API token</div>' : ''}
      ${s.error ? `<div class="text-xs text-red-600 mt-2 font-mono">${s.error}</div>` : ''}
    </div>
  `).join('');

  $('#app').innerHTML = `
    <div class="max-w-5xl mx-auto p-4">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-slate-800">🔌 数据源健康</h1>
        <a href="#/" class="text-sm text-blue-600 hover:underline">← 返回首页</a>
      </div>
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-4 mb-4 flex items-center justify-between">
        <div>
          <div class="text-sm text-slate-500">总体状态</div>
          <div class="text-2xl font-bold mt-1">${overallBadge(data.overall)}</div>
        </div>
        <div class="text-right text-sm text-slate-600">
          <div>OK: <span class="font-bold text-green-600">${data.summary.ok}</span> / ${data.summary.total}</div>
          <div>Degraded: <span class="text-amber-600">${data.summary.degraded}</span></div>
          <div>Down: <span class="text-red-600">${data.summary.down}</span></div>
          ${data.avg_latency_ms ? `<div class="mt-1 text-xs text-slate-400">avg ${data.avg_latency_ms}ms</div>` : ''}
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">${sourceCards}</div>
      <div class="text-xs text-slate-400 mt-4">检测时间: ${data.checked_at}</div>
    </div>
  `;
}
