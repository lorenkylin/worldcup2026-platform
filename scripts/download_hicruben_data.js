// M1.1 下载 Hicruben Elo 数据集
const https = require('https');
const fs = require('fs');
const path = require('path');

const REPO = 'Hicruben/world-cup-2026-prediction-model';
const FILES = [
  { name: 'data/elo-calibrated.json', desc: '60 队 Elo 评分' },
  { name: 'data/wc2026-results.json', desc: '6/11-6/12 真实比赛' },
  { name: 'data/model-backtest.json', desc: '回测结果' },
  { name: 'elo.mjs', desc: 'Elo + Dixon-Coles + Monte Carlo 公式' },
  { name: 'predict.mjs', desc: '预测脚本' },
  { name: 'backtest.mjs', desc: '回测脚本' },
];

const SEED_DIR = path.join(__dirname, '..', 'data', 'seed', 'hicruben');
if (!fs.existsSync(SEED_DIR)) fs.mkdirSync(SEED_DIR, { recursive: true });

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'WorkBuddy' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetchJson(res.headers.location).then(resolve, reject);
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('Not JSON: ' + data.slice(0, 200))); }
      });
      res.on('error', reject);
    });
  });
}

async function main() {
  const log = [];
  for (const f of FILES) {
    const url = `https://api.github.com/repos/${REPO}/contents/data/${f.name}`;
    process.stdout.write(`Downloading ${f.name} ... `);
    try {
      const meta = await fetchJson(url);
      const out = path.join(SEED_DIR, f.name);
      if (meta.content) {
        // GitHub contents API: base64 编码
        const content = Buffer.from(meta.content, 'base64').toString('utf-8');
        fs.writeFileSync(out, content);
        log.push(`✅ ${f.name.padEnd(25)} ${content.length.toString().padStart(8)}B  (${f.desc})`);
        console.log(`${content.length}B`);
      } else if (meta.download_url) {
        // 用 raw URL 拉（fallback）
        const raw = await fetch(meta.download_url).then(r => r.text());
        fs.writeFileSync(out, raw);
        log.push(`✅ ${f.name.padEnd(25)} ${raw.length.toString().padStart(8)}B  (${f.desc})`);
        console.log(`${raw.length}B (raw)`);
      } else {
        log.push(`⚠️ ${f.name}: no content/download_url`);
        console.log('no content');
      }
    } catch (e) {
      log.push(`❌ ${f.name}: ${e.message}`);
      console.log(`FAIL: ${e.message}`);
    }
  }
  // results.json 单独处理（在根目录）
  console.log('\nDownloading results.json (910 场) ...');
  try {
    const url = `https://api.github.com/repos/${REPO}/contents/data/results.json`;
    const meta = await fetchJson(url);
    if (meta.content) {
      const content = Buffer.from(meta.content, 'base64').toString('utf-8');
      fs.writeFileSync(path.join(SEED_DIR, 'results.json'), content);
      log.push(`✅ results.json${' '.repeat(13)} ${content.length.toString().padStart(8)}B  (913 场国际赛)`);
      console.log(`${content.length}B`);
    } else {
      log.push(`⚠️ results.json: no content (probably > 1MB truncated by API)`);
      console.log('no content - file too big for contents API');
    }
  } catch (e) {
    log.push(`❌ results.json: ${e.message}`);
    console.log(`FAIL: ${e.message}`);
  }

  console.log('\n========== M1.1 下载报告 ==========');
  log.forEach(l => console.log(l));

  // 验证 elo-calibrated.json
  const eloPath = path.join(SEED_DIR, 'elo-calibrated.json');
  if (fs.existsSync(eloPath)) {
    const elo = JSON.parse(fs.readFileSync(eloPath, 'utf-8'));
    console.log(`\n📊 Elo 评分覆盖: ${Object.keys(elo.ratings).length} 队`);
    const top5 = Object.entries(elo.ratings).sort((a, b) => b[1] - a[1]).slice(0, 5);
    console.log('   Top 5:', top5.map(([k, v]) => `${k}(${v})`).join(', '));
    const bottom3 = Object.entries(elo.ratings).sort((a, b) => a[1] - b[1]).slice(0, 3);
    console.log('   Bottom 3:', bottom3.map(([k, v]) => `${k}(${v})`).join(', '));
  }
}

main().catch(e => { console.error(e); process.exit(1); });
