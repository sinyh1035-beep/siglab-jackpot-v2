"""
jackpot_v2_backend.py
==========================================
SIGVIEW 잭팟 도구 시즌2 - 백엔드 자동 스캔
- pykrx로 KOSPI/KOSDAQ cyclical 종목 일/주/월봉 다운로드
- MFAS v2 알고리즘 (4차함수 c자리 다중 프레임 시간 일치)
- jackpot-v2.json 출력
- GitHub Actions에서 매일 자정 (KST) 자동 실행

알고리즘:
  f(x) - g(x) = k(x - a)(x - b)(x - c)^2
  - a, b: 단순근 (zero crossings)
  - c: 이중근 (접점, 기러기 자리)
  - 일/주/월 3프레임에서 동시 c자리 일치 = 강신호
"""
import json
import warnings
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from pykrx import stock

warnings.filterwarnings('ignore')

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST)
END_DATE = TODAY.strftime('%Y%m%d')

# ============================================================
# 종목 풀 - 경기민감주 (시총 5천억+, 추후 확장)
# ============================================================
CYCLICAL = {
    # 반도체
    '005930': '삼성전자', '000660': 'SK하이닉스', '042700': '한미반도체',
    '058470': '리노공업', '039030': '이오테크닉스',
    # 2차전지
    '373220': 'LG에너지솔루션', '006400': '삼성SDI', '051910': 'LG화학',
    '003670': '포스코퓨처엠', '247540': '에코프로비엠', '086520': '에코프로',
    # 자동차
    '005380': '현대차', '000270': '기아', '012330': '현대모비스',
    # 조선
    '009540': 'HD한국조선해양', '010140': '삼성중공업', '042660': '한화오션',
    # 철강/비철
    '005490': 'POSCO홀딩스', '004020': '현대제철', '010130': '고려아연',
    '103140': '풍산',
    # 화학/정유
    '011170': '롯데케미칼', '009830': '한화솔루션', '011780': '금호석유',
    '096770': 'SK이노베이션', '010950': 'S-Oil',
    # 건설
    '000720': '현대건설', '006360': 'GS건설', '047040': '대우건설',
    # 해운/항공
    '011200': 'HMM', '028670': '팬오션', '003490': '대한항공',
    # 방산
    '012450': '한화에어로스페이스', '047810': '한국항공우주', '079550': 'LIG넥스원',
    # 풍력/원자력
    '112610': '씨에스윈드', '052690': '한전기술', '051600': '한전KPS',
    # 중공업
    '034020': '두산에너빌리티',
    '267250': 'HD현대', '329180': 'HD현대중공업',
}


# ============================================================
# 4차함수 모델
# ============================================================
def quartic(x, k, a, b, c):
    return k * (x - a) * (x - b) * (x - c) ** 2


def fit_quartic(prices, x_norm):
    g_base = np.percentile(prices, 20)
    h = prices - g_base
    best, best_r2 = None, -np.inf
    for a0, b0, c0 in [(0.10, 0.40, 0.80), (0.20, 0.50, 0.85),
                        (0.05, 0.35, 0.75), (0.15, 0.45, 0.90)]:
        try:
            scale = max(h.max(), 1)
            k0 = scale / max(abs((1 - a0) * (1 - b0) * (1 - c0) ** 2), 1e-6)
            popt, _ = curve_fit(quartic, x_norm, h, p0=[k0, a0, b0, c0], maxfev=1500)
            k_f, a_f, b_f, c_f = popt
            if not (0 <= a_f < b_f < c_f <= 1) or k_f <= 0:
                continue
            y_fit = quartic(x_norm, *popt)
            ss_res = np.sum((h - y_fit) ** 2)
            ss_tot = np.sum((h - h.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else -np.inf
            if r2 > best_r2:
                best_r2 = r2
                best = (k_f, a_f, b_f, c_f, g_base)
        except Exception:
            continue
    return best, best_r2


def collect_c_candidates(df, win_sizes, step, recent_cutoff, r2_min=0.60):
    cands = []
    for win_size in win_sizes:
        if len(df) < win_size:
            continue
        for start_i in range(0, len(df) - win_size + 1, step):
            window = df.iloc[start_i:start_i + win_size]
            prices = window['종가'].values.astype(float)
            x_norm = np.linspace(0, 1, win_size)
            fit_result, r2 = fit_quartic(prices, x_norm)
            if fit_result is None or r2 < r2_min:
                continue
            k_f, a_f, b_f, c_f, g_base = fit_result
            if not (0.65 <= c_f <= 0.95):
                continue
            c_idx = start_i + int(c_f * (win_size - 1))
            c_date = df.index[c_idx]
            if c_date < recent_cutoff:
                continue
            c_price = float(df['종가'].iloc[c_idx])
            latest_price = float(df['종가'].iloc[-1])
            cands.append({
                'c_date': c_date.strftime('%Y-%m-%d'),
                'c_price': c_price,
                'r2': round(float(r2), 3),
                'c_pos': round(float(c_f), 3),
                'win_size': win_size,
                'latest_price': latest_price,
                'ratio_pct': round((latest_price / c_price - 1) * 100, 1) if c_price > 0 else 0,
            })
    return cands


def find_aligned_c(daily, weekly, monthly,
                    max_dw_m=6, max_wm_m=12, max_dwm_m=12):
    """3프레임 시간 일치 c자리 찾기"""
    best = None
    best_score = -np.inf

    def date_diff_months(d1, d2):
        a = pd.Timestamp(d1)
        b = pd.Timestamp(d2)
        return abs((a - b).days) / 30

    # ★★★★★ (3프레임)
    for d in daily:
        for w in weekly:
            for m in monthly:
                dw = date_diff_months(d['c_date'], w['c_date'])
                wm = date_diff_months(w['c_date'], m['c_date'])
                dm = date_diff_months(d['c_date'], m['c_date'])
                if dw <= max_dw_m and wm <= max_wm_m and dm <= max_dwm_m:
                    score = (d['r2'] + w['r2'] + m['r2']) - (dw + wm + dm) * 0.02
                    if score > best_score:
                        best_score = score
                        best = {'stars': 5, 'type': '일+주+월',
                                'time_diff_months': round(max(dw, wm, dm), 1),
                                'daily': d, 'weekly': w, 'monthly': m, 'score': score}
    if best:
        return best

    # ★★★★ (2프레임)
    pairs = [
        ('일+주', daily, weekly, max_dw_m, 'daily', 'weekly'),
        ('주+월', weekly, monthly, max_wm_m, 'weekly', 'monthly'),
        ('일+월', daily, monthly, max_dwm_m, 'daily', 'monthly'),
    ]
    for type_name, frame_a, frame_b, max_m, key_a, key_b in pairs:
        for a in frame_a:
            for b in frame_b:
                diff = date_diff_months(a['c_date'], b['c_date'])
                if diff <= max_m:
                    score = a['r2'] + b['r2'] - diff * 0.02
                    if score > best_score:
                        best_score = score
                        best = {'stars': 4, 'type': type_name,
                                'time_diff_months': round(diff, 1),
                                key_a: a, key_b: b, 'score': score}
    if best:
        return best

    # ★★★ (1프레임)
    all_singles = []
    for d in daily:
        all_singles.append(('일', 'daily', d))
    for w in weekly:
        all_singles.append(('주', 'weekly', w))
    for m in monthly:
        all_singles.append(('월', 'monthly', m))
    if all_singles:
        all_singles.sort(key=lambda x: -x[2]['r2'])
        type_name, key, d = all_singles[0]
        return {'stars': 3, 'type': type_name, key: d, 'score': d['r2']}
    return None


def determine_phase(alignment):
    """phase 결정: exploded / early_rise / accumulating"""
    ratios = []
    for k in ['daily', 'weekly', 'monthly']:
        if k in alignment and alignment[k]:
            ratios.append(alignment[k]['ratio_pct'])
    if not ratios:
        return 'unknown'
    avg = np.mean(ratios)
    if avg > 100:
        return 'exploded'
    elif avg > 20:
        return 'early_rise'
    else:
        return 'accumulating'


def determine_verdict(stars, phase):
    if stars >= 4 and phase in ('accumulating', 'early_rise'):
        return '현재 진입 후보'
    if stars >= 4 and phase == 'exploded':
        return '검증 케이스'
    if stars == 3 and phase == 'early_rise':
        return '신규 따끈한 신호'
    return f'★{stars} 단독'


# ============================================================
# 한 종목 분석
# ============================================================
def analyze_stock(code, name):
    # 일봉 — 5년
    start_d = (TODAY - timedelta(days=5 * 365)).strftime('%Y%m%d')
    df_d = stock.get_market_ohlcv(start_d, END_DATE, code)
    if df_d is None or len(df_d) < 250:
        return None

    # 주봉 — 8년
    start_w = (TODAY - timedelta(days=8 * 365)).strftime('%Y%m%d')
    df_w = stock.get_market_ohlcv(start_w, END_DATE, code, freq='w')
    
    # 월봉 — 20년
    start_m = (TODAY - timedelta(days=20 * 365)).strftime('%Y%m%d')
    df_m = stock.get_market_ohlcv(start_m, END_DATE, code, freq='m')

    if df_w is None or df_m is None or len(df_w) < 100 or len(df_m) < 60:
        return None

    cutoff_d = pd.Timestamp((TODAY - timedelta(days=3 * 365)).date())
    cutoff_w = pd.Timestamp((TODAY - timedelta(days=4 * 365)).date())
    cutoff_m = pd.Timestamp((TODAY - timedelta(days=6 * 365)).date())

    daily_c = collect_c_candidates(df_d, [800, 1200], 100, cutoff_d, r2_min=0.60)
    weekly_c = collect_c_candidates(df_w, [200, 300], 15, cutoff_w, r2_min=0.60)
    monthly_c = collect_c_candidates(df_m, [84, 120], 12, cutoff_m, r2_min=0.60)

    if not (daily_c or weekly_c or monthly_c):
        return None

    alignment = find_aligned_c(daily_c, weekly_c, monthly_c)
    if alignment is None:
        return None

    phase = determine_phase(alignment)
    verdict = determine_verdict(alignment['stars'], phase)

    return {
        'code': code,
        'name': name,
        'stars': alignment['stars'],
        'type': alignment['type'],
        'time_diff_months': alignment.get('time_diff_months'),
        'phase': phase,
        'verdict': verdict,
        'frames': {
            'daily': alignment.get('daily'),
            'weekly': alignment.get('weekly'),
            'monthly': alignment.get('monthly'),
        },
        '_score': alignment['score'],
    }


# ============================================================
# 메인
# ============================================================
def main():
    print(f'[SIGVIEW 잭팟 시즌2] {TODAY.strftime("%Y-%m-%d %H:%M:%S")} KST 스캔 시작')
    print(f'경기민감주 풀: {len(CYCLICAL)}개')

    results = []
    for i, (code, name) in enumerate(CYCLICAL.items(), 1):
        try:
            r = analyze_stock(code, name)
            if r:
                results.append(r)
                print(f'  [{i}/{len(CYCLICAL)}] {name} ★{r["stars"]} ({r["type"]}) {r["verdict"]}')
            else:
                print(f'  [{i}/{len(CYCLICAL)}] {name} - 매칭 없음')
        except Exception as e:
            print(f'  [{i}/{len(CYCLICAL)}] {name} - 에러: {e}')

    # 정렬: stars 내림차순, score 내림차순
    results.sort(key=lambda x: (-x['stars'], -x['_score']))
    for i, r in enumerate(results, 1):
        r['rank'] = i
        r.pop('_score', None)

    # JSON 출력
    output = {
        'version': '2.0',
        'season': 2,
        'generated_at': TODAY.isoformat(),
        'scan_universe': 'cyclical_korea',
        'n_scanned': len(CYCLICAL),
        'n_matched': len(results),
        'algorithm': {
            'name': 'MFAS v2',
            'description': 'Multi-Frame Alignment Score - 4차함수 c자리 다중 프레임 시간 일치 검출',
            'frames': ['daily', 'weekly', 'monthly'],
            'r2_min': 0.60,
            'time_constraints_months': {
                'daily_weekly_max': 6,
                'weekly_monthly_max': 12,
                'all_three_max': 12,
            },
            'c_position_range': [0.65, 0.95],
        },
        'summary': {
            'five_stars': sum(1 for r in results if r['stars'] == 5),
            'four_stars': sum(1 for r in results if r['stars'] == 4),
            'three_stars': sum(1 for r in results if r['stars'] == 3),
        },
        'stocks': results,
        'disclaimer': '본 데이터는 4차함수 패턴 매칭 분석 결과이며 투자 권유가 아닙니다. 모든 투자 판단과 책임은 본인에게 있습니다.',
    }

    with open('jackpot-v2.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n완료: {len(results)}개 매칭, jackpot-v2.json 저장됨')
    print(f'  ★★★★★: {output["summary"]["five_stars"]}')
    print(f'  ★★★★:   {output["summary"]["four_stars"]}')
    print(f'  ★★★:    {output["summary"]["three_stars"]}')


if __name__ == '__main__':
    main()
