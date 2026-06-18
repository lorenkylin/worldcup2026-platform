"""
M1.2 步骤1: 把 Hicruben Elo 评分导入 teams 表
- 用 Hicruben 真实 913 场累计 Elo 覆盖占位值
- 60 队 → 48 队映射（缺 12 队 + kebab-case 转换）
- 同步写入 team_elo_ratings 历史表（as_of_date=2026-06-11）
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = r'D:\WorkBuddy\2026FIFA\worldcup2026-platform\data\worldcup2026.db'
ELO_JSON = r'D:\WorkBuddy\2026FIFA\worldcup2026-platform\data\seed\hicruben\elo-calibrated.json'

# Hicruben kebab-case → 本项目 FIFA 3-letter code
HICRUBEN_TO_FIFA = {
    'argentina': 'ARG', 'france': 'FRA', 'spain': 'ESP', 'brazil': 'BRA', 'england': 'ENG',
    'portugal': 'POR', 'netherlands': 'NED', 'germany': 'GER', 'belgium': 'BEL', 'italy': 'ITA',
    'colombia': 'COL', 'uruguay': 'URU', 'croatia': 'CRO', 'morocco': 'MAR', 'switzerland': 'SUI',
    'usa': 'USA', 'mexico': 'MEX', 'japan': 'JPN', 'senegal': 'SEN', 'denmark': 'DEN',
    'ecuador': 'ECU', 'australia': 'AUS', 'south-korea': 'KOR', 'iran': 'IRN', 'poland': 'POL',
    'canada': 'CAN', 'serbia': 'SRB', 'wales': 'WAL', 'ghana': 'GHA', 'tunisia': 'TUN',
    'ivory-coast': 'CIV', 'nigeria': 'NGA', 'saudi-arabia': 'KSA', 'qatar': 'QAT', 'egypt': 'EGY',
    'algeria': 'ALG', 'scotland': 'SCO', 'cameroon': 'CMR', 'paraguay': 'PAR', 'venezuela': 'VEN',
    'chile': 'CHI', 'peru': 'PER', 'czech-republic': 'CZE', 'bosnia-and-herzegovina': 'BIH',
    'south-africa': 'RSA', 'new-zealand': 'NZL', 'panama': 'PAN', 'jamaica': 'JAM',
    'honduras': 'HON', 'jordan': 'JOR', 'haiti': 'HAI', 'el-salvador': 'SLV',
    'trinidad-and-tobago': 'TRI', 'guatemala': 'GUA', 'norway': 'NOR', 'sweden': 'SWE',
    'turkey': 'TUR', 'austria': 'AUT', 'iraq': 'IRQ', 'uzbekistan': 'UZB', 'cape-verde': 'CPV',
    'dr-congo': 'COD', 'curacao': 'CUW',
}

# 反向：FIFA 3-letter → kebab-case（用于反查）
FIFA_TO_HICRUBEN = {v: k for k, v in HICRUBEN_TO_FIFA.items()}

def main():
    elo_data = json.loads(Path(ELO_JSON).read_text(encoding='utf-8'))
    ratings = elo_data['ratings']
    as_of_date = elo_data['generatedAt']  # '2026-06-11T16:47:05.772Z'
    as_of_dt = datetime.fromisoformat(as_of_date.replace('Z', '+00:00'))

    print(f'Hicruben Elo 数据: {len(ratings)} 队 · 截至 {as_of_date}')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. 取所有 48 队
    c.execute('SELECT id, fifa_code, name_zh, elo_rating FROM teams ORDER BY id')
    teams = c.fetchall()

    # 2. 逐队更新
    matched = 0
    unmatched = []
    rank_by_elo = sorted(ratings.items(), key=lambda x: -x[1])  # (kebab, rating)
    rank_map = {k: i+1 for i, (k, _) in enumerate(rank_by_elo)}  # kebab → rank

    updates = []
    history_rows = []
    for team_id, fifa_code, name_zh, old_elo in teams:
        kebab = FIFA_TO_HICRUBEN.get(fifa_code)
        if kebab and kebab in ratings:
            new_elo = ratings[kebab]
            new_rank = rank_map[kebab]
            updates.append((new_elo, new_rank, team_id))
            # 历史表也写一份
            history_rows.append((team_id, as_of_dt, new_elo, new_rank, 'hicruben', as_of_dt))
            matched += 1
            print(f'  {fifa_code:5s} {name_zh:20s}  {old_elo or "-":>4} → {new_elo:>4}  (rank {new_rank:>2})')
        else:
            unmatched.append((fifa_code, name_zh))
            print(f'  ⚠️  {fifa_code:5s} {name_zh:20s}  无 Hicruben 数据')

    print(f'\n匹配 {matched}/48 队')

    # 3. 批量更新 teams.elo_rating + fifa_rank
    c.executemany('UPDATE teams SET elo_rating = ?, fifa_rank = ? WHERE id = ?', updates)
    conn.commit()
    print(f'✅ teams 表更新 {len(updates)} 队')

    # 4. 写入 team_elo_ratings 历史表（v0.14.3 后已清理该死表，保留兼容逻辑）
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_elo_ratings'")
    if c.fetchone():
        c.execute('SELECT COUNT(*) FROM team_elo_ratings')
        history_before = c.fetchone()[0]
        c.executemany('''
            INSERT INTO team_elo_ratings (team_id, as_of_date, rating, rank, source, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', history_rows)
        conn.commit()
        c.execute('SELECT COUNT(*) FROM team_elo_ratings')
        history_after = c.fetchone()[0]
        print(f'✅ team_elo_ratings 写入: {history_before} → {history_after}')
    else:
        print('ℹ️ team_elo_ratings 表已不存在，跳过历史表写入（v0.14.3+ 为预期行为）')

    # 5. 验证
    print('\n=== 48 队 Elo Top 10 ===')
    c.execute('''
        SELECT fifa_code, name_zh, elo_rating, fifa_rank
        FROM teams ORDER BY elo_rating DESC LIMIT 10
    ''')
    for r in c.fetchall():
        print(f'  #{r[3]:>2}  {r[0]:5s}  {r[1]:20s}  Elo={r[2]}')

    print('\n=== 48 队 Elo Bottom 5 ===')
    c.execute('''
        SELECT fifa_code, name_zh, elo_rating, fifa_rank
        FROM teams ORDER BY elo_rating ASC LIMIT 5
    ''')
    for r in c.fetchall():
        print(f'  #{r[3]:>2}  {r[0]:5s}  {r[1]:20s}  Elo={r[2]}')

    if unmatched:
        print(f'\n⚠️ 未匹配: {unmatched}')

    conn.close()

if __name__ == '__main__':
    main()
