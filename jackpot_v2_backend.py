"""
jackpot_v2_backend.py
==========================================
SIGVIEW 잭팟 도구 시즌2 v1.3.1 - BUG FIX
- numpy bool/int/float → Python native 변환 (JSON 직렬화 가능)
- 외국인 함수 디버그 로그 추가 + try/except 더 견고하게
- 차트 데이터 포함 (모달 차트 v1.4용 사전 준비)
"""
import json
import warnings
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import linregress
from pykrx import stock

warnings.filterwarnings('ignore')

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST)
END_DATE = TODAY.strftime('%Y%m%d')

CYCLICAL = {
    '005930': '삼성전자', '000660': 'SK하이닉스', '042700': '한미반도체',
    '058470': '리노공업', '039030': '이오테크닉스',
    '373220': 'LG에너지솔루션', '006400': '삼성SDI', '051910': 'LG화학',
    '003670': '포스코퓨처엠', '247540': '에코프로비엠', '086520': '에코프로',
    '005380': '현대차', '000270': '기아', '012330': '현대모비스',
    '009540': 'HD한국조선해양', '010140': '삼성중공업', '042660': '한화오션',
    '005490': 'POSCO홀딩스', '004020': '현대제철', '010130': '고려아연',
    '103140': '풍산',
    '011170': '롯데케미칼', '009830': '한화솔루션', '011780': '금호석유',
    '096770': 'SK이노베이션', '010950': 'S-Oil',
    '000720': '현대건설', '006360': 'GS건설', '047040': '대우건설',
    '011200': 'HMM', '028670': '팬오션', '003490': '대한항공',
    '012450': '한화에어로스페이스', '047810': '한국항공우주', '079550': 'LIG넥스원',
    '112610': '씨에스윈드', '052690': '한전기술', '051600': '한전KPS',
    '034020': '두산에너빌리티',
    '267250': 'HD현대', '329180': 'HD현대중공업',
}

CHINA_DIRECT = {
    '005490', '004020', '010130', '103140',
    '011170', '009830', '011780', '010060', '096770', '010950',
    '009540', '010140', '042660',
    '011200', '028670',
    '267250', '329180', '034020',
    '003490',
}


# ============================================================
# numpy → Python native 변환 (JSON 직렬화 핵심 수정)
# ============================================================
def to_native(obj):
    """numpy/pandas 타입을 Python native로 재귀 변환"""
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime('%Y-%m-%d')
    if pd.isna(obj) if isinstance(obj, (int, float)) else False:
        return None
    return obj


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


def collect_c_candidates(df, win_sizes, step, recent_cutoff, r2_min=0.55):
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
                'win_size': int(win_size),
                'latest_price': latest_price,
                'ratio_pct': round((latest_price / c_price - 1) * 100, 1) if c_price > 0 else 0.0,
            })
    return cands


def find_aligned_c(daily, weekly, monthly,
                    max_dw_m=6, max_wm_m=12, max_dwm_m=12):
    best = None
    best_score = -np.inf

    def date_diff_months(d1, d2):
        return abs((pd.Timestamp(d1) - pd.Timestamp(d2)).days) / 30

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
                                'time_diff_months': round(float(max(dw, wm, dm)), 1),
                                'daily': d, 'weekly': w, 'monthly': m,
                                'score': float(score)}
    if best:
        return best

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
                                'time_diff_months': round(float(diff), 1),
                                key_a: a, key_b: b, 'score': float(score)}
    if best:
        return best

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
        return {'stars': 3, 'type': type_name, key: d, 'score': float(d['r2'])}
    return None


def analyze_ma20_crossings(df_daily, lookback_days=250):
    if df_daily is None or len(df_daily) < 30:
        return {'count': 0, 'is_stealth': False, 'price_range_pct': 0.0}
    recent = df_daily.tail(lookback_days).copy()
    recent['ma20'] = recent['종가'].rolling(20).mean()
    recent = recent.dropna()
    if len(recent) < 30:
        return {'count': 0, 'is_stealth': False, 'price_range_pct': 0.0}
    above = (recent['종가'] > recent['ma20']).astype(int)
    crossings = int((above.diff().abs() == 1).sum())
    price_range_pct = float((recent['종가'].max() - recent['종가'].min()) / recent['종가'].mean() * 100)
    is_stealth = bool((crossings >= 4) and (price_range_pct <= 35))
    return {
        'count': crossings,
        'price_range_pct': round(price_range_pct, 1),
        'is_stealth': is_stealth,
    }


def analyze_volume_asymmetry(df_daily, lookback_days=250):
    if df_daily is None or len(df_daily) < 30:
        return {'ratio': 0.0, 'is_accumulation': False}
    recent = df_daily.tail(lookback_days).copy()
    recent['change'] = recent['종가'].diff()
    up_days = recent[recent['change'] > 0]
    down_days = recent[recent['change'] < 0]
    if len(up_days) < 5 or len(down_days) < 5:
        return {'ratio': 0.0, 'is_accumulation': False}
    avg_vol_down = float(down_days['거래량'].mean())
    avg_vol_up = float(up_days['거래량'].mean())
    if avg_vol_up == 0:
        return {'ratio': 0.0, 'is_accumulation': False}
    ratio = avg_vol_down / avg_vol_up
    is_accumulation = bool(ratio >= 1.0)
    return {
        'ratio': round(float(ratio), 2),
        'is_accumulation': is_accumulation,
    }


def analyze_foreign_holding(code, days=400):
    """외국인 지분율 추세 (★ v1.3.1 견고화)"""
    result = {'trend': 'unknown', 'slope_per_month': 0.0,
              'latest_pct': 0.0, 'change_pct': 0.0, 'error': None}
    try:
        start = (TODAY - timedelta(days=days)).strftime('%Y%m%d')
        df = stock.get_exhaustion_rates_of_foreign_investment_by_date(start, END_DATE, code)
        if df is None or len(df) < 30:
            result['error'] = 'insufficient_data'
            return result
        
        # 정확한 컬럼명: '지분율' (pykrx 도큐먼트 확인)
        if '지분율' not in df.columns:
            result['error'] = f'no_지분율_col (cols: {list(df.columns)[:3]})'
            return result
        
        df = df.dropna(subset=['지분율'])
        if len(df) < 30:
            result['error'] = 'too_few_after_dropna'
            return result
        
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        latest_pct = float(df['지분율'].iloc[-1])
        oldest_pct = float(df['지분율'].iloc[0])
        change_pct = latest_pct - oldest_pct
        
        x = np.arange(len(df), dtype=float)
        y = df['지분율'].values.astype(float)
        slope, _, _, _, _ = linregress(x, y)
        slope_per_month = float(slope * 20)
        
        if slope_per_month > 0.1:
            trend = 'accumulating'
        elif slope_per_month > 0.03:
            trend = 'slight_up'
        elif slope_per_month < -0.1:
            trend = 'distributing'
        elif slope_per_month < -0.03:
            trend = 'slight_down'
        else:
            trend = 'flat'
        
        result.update({
            'trend': trend,
            'slope_per_month': round(slope_per_month, 3),
            'latest_pct': round(latest_pct, 2),
            'change_pct': round(float(change_pct), 2),
            'error': None,
        })
        return result
    except Exception as e:
        result['error'] = str(e)[:80]
        return result


def determine_phase_v13(ratio_pct, ma20_stealth, vol_accum, fi_trend):
    if (-15 <= ratio_pct <= 15) and ma20_stealth and fi_trend in ('accumulating', 'slight_up'):
        return 'stealth_accumulation'
    if (-15 <= ratio_pct <= 15) and fi_trend in ('accumulating', 'slight_up'):
        return 'quiet_accumulation'
    if 10 < ratio_pct <= 30 and fi_trend in ('accumulating', 'slight_up', 'flat'):
        return 'early_breakout'
    if 30 < ratio_pct <= 60:
        return 'in_progress'
    if ratio_pct > 60:
        return 'already_run'
    if fi_trend == 'distributing':
        return 'risky'
    if ratio_pct < -15:
        return 'failed'
    return 'neutral'


def determine_verdict_v13(stars, phase):
    if phase == 'stealth_accumulation':
        return '🎯 진짜 외인 매집중'
    if phase == 'quiet_accumulation':
        return '🐢 조용한 매집중'
    if phase == 'early_breakout':
        return '🌱 막 깨고 나옴'
    if phase == 'in_progress':
        return '⚪ 진행 중'
    if phase == 'already_run':
        return '🔥 이미 폭발 (검증)'
    if phase == 'risky':
        return '⚠️ 외인 매도 중'
    if phase == 'failed':
        return '❌ 약함'
    return f'★{stars} 단독'


def calc_accumulation_score(stars, phase, ma20_data, vol_data, fi_data, is_china):
    score = stars * 10
    phase_score = {
        'stealth_accumulation': 30, 'quiet_accumulation': 22,
        'early_breakout': 15, 'in_progress': 5, 'already_run': -5,
        'risky': -10, 'failed': -15, 'neutral': 0,
    }
    score += phase_score.get(phase, 0)
    if fi_data['trend'] == 'accumulating':
        score += 15
    elif fi_data['trend'] == 'slight_up':
        score += 7
    elif fi_data['trend'] == 'distributing':
        score -= 10
    if ma20_data['is_stealth']:
        score += 8
    if vol_data['is_accumulation']:
        score += 5
    if is_china:
        score += 5
    return int(max(0, min(100, score)))


def get_daily(code, years):
    start = (TODAY - timedelta(days=years * 365)).strftime('%Y%m%d')
    df = stock.get_market_ohlcv(start, END_DATE, code)
    if df is None or len(df) == 0:
        return None
    df.index = pd.to_datetime(df.index)
    return df


def resample_to_weekly(df_daily):
    if df_daily is None or len(df_daily) == 0:
        return None
    return df_daily.resample('W-FRI').agg({
        '시가': 'first', '고가': 'max', '저가': 'min',
        '종가': 'last', '거래량': 'sum',
    }).dropna()


def resample_to_monthly(df_daily):
    if df_daily is None or len(df_daily) == 0:
        return None
    return df_daily.resample('ME').agg({
        '시가': 'first', '고가': 'max', '저가': 'min',
        '종가': 'last', '거래량': 'sum',
    }).dropna()


def analyze_stock(code, name):
    df_d_5y = get_daily(code, 5)
    if df_d_5y is None or len(df_d_5y) < 250:
        return None

    df_d_long = get_daily(code, 15)
    df_w = resample_to_weekly(df_d_long) if df_d_long is not None else None
    df_m = resample_to_monthly(df_d_long) if df_d_long is not None else None

    if df_w is None or df_m is None or len(df_w) < 100 or len(df_m) < 60:
        return None

    cutoff_d = pd.Timestamp((TODAY - timedelta(days=3 * 365)).date())
    cutoff_w = pd.Timestamp((TODAY - timedelta(days=4 * 365)).date())
    cutoff_m = pd.Timestamp((TODAY - timedelta(days=6 * 365)).date())

    daily_c = collect_c_candidates(df_d_5y, [800, 1200], 100, cutoff_d, r2_min=0.55)
    weekly_c = collect_c_candidates(df_w, [200, 300], 15, cutoff_w, r2_min=0.55)
    monthly_c = collect_c_candidates(df_m, [84, 120], 12, cutoff_m, r2_min=0.55)

    if not (daily_c or weekly_c or monthly_c):
        return None

    alignment = find_aligned_c(daily_c, weekly_c, monthly_c)
    if alignment is None:
        return None

    ma20_data = analyze_ma20_crossings(df_d_5y)
    vol_data = analyze_volume_asymmetry(df_d_5y)
    fi_data = analyze_foreign_holding(code)
    
    ratios = []
    for k in ['daily', 'weekly', 'monthly']:
        if k in alignment and alignment[k]:
            ratios.append(alignment[k]['ratio_pct'])
    avg_ratio = float(np.mean(ratios)) if ratios else 0.0
    
    phase = determine_phase_v13(avg_ratio, ma20_data['is_stealth'],
                                 vol_data['is_accumulation'], fi_data['trend'])
    verdict = determine_verdict_v13(alignment['stars'], phase)
    is_china = code in CHINA_DIRECT
    accum_score = calc_accumulation_score(alignment['stars'], phase,
                                           ma20_data, vol_data, fi_data, is_china)

    return {
        'code': code, 'name': name,
        'stars': int(alignment['stars']),
        'type': alignment['type'],
        'time_diff_months': alignment.get('time_diff_months'),
        'phase': phase, 'verdict': verdict,
        'accumulation_score': accum_score,
        'is_china_play': bool(is_china),
        'avg_ratio_pct': round(avg_ratio, 1),
        'signals': {
            'ma20_crossings': ma20_data['count'],
            'ma20_stealth': bool(ma20_data['is_stealth']),
            'price_range_pct': ma20_data['price_range_pct'],
            'volume_down_up_ratio': vol_data['ratio'],
            'volume_accumulation': bool(vol_data['is_accumulation']),
            'foreign_trend': fi_data['trend'],
            'foreign_slope_per_month': fi_data['slope_per_month'],
            'foreign_latest_pct': fi_data['latest_pct'],
            'foreign_change_pct': fi_data['change_pct'],
            'foreign_error': fi_data.get('error'),
        },
        'frames': {
            'daily': alignment.get('daily'),
            'weekly': alignment.get('weekly'),
            'monthly': alignment.get('monthly'),
        },
    }


def main():
    print(f'[SIGVIEW 잭팟 시즌2 v1.3.1] {TODAY.strftime("%Y-%m-%d %H:%M:%S")} KST')
    print(f'경기민감주 풀: {len(CYCLICAL)}개')

    results = []
    fi_errors = {}
    for i, (code, name) in enumerate(CYCLICAL.items(), 1):
        try:
            r = analyze_stock(code, name)
            if r:
                results.append(r)
                fi = r['signals']
                china_tag = ' 🇨🇳' if r['is_china_play'] else ''
                fi_info = f'{fi["foreign_trend"]} {fi["foreign_change_pct"]:+.1f}%p ({fi["foreign_latest_pct"]:.1f}%)'
                if fi.get('foreign_error'):
                    fi_errors[code] = fi['foreign_error']
                    fi_info = f'ERR: {fi["foreign_error"][:30]}'
                print(f'  [{i}/{len(CYCLICAL)}] {name}{china_tag} ★{r["stars"]} '
                      f'점수{r["accumulation_score"]} {r["verdict"]} (외인:{fi_info})')
            else:
                print(f'  [{i}/{len(CYCLICAL)}] {name} - 매칭 없음')
        except Exception as e:
            print(f'  [{i}/{len(CYCLICAL)}] {name} - 에러: {str(e)[:80]}')
    
    if fi_errors:
        print(f'\n외인 데이터 에러 종목 {len(fi_errors)}개:')
        for code, err in list(fi_errors.items())[:3]:
            print(f'  - {code}: {err}')

    results.sort(key=lambda x: -x['accumulation_score'])
    for i, r in enumerate(results, 1):
        r['rank'] = i

    output = {
        'version': '2.0', 'season': 2, 'algo_version': '1.3.1',
        'generated_at': TODAY.isoformat(),
        'scan_universe': 'cyclical_korea',
        'n_scanned': len(CYCLICAL), 'n_matched': len(results),
        'algorithm': {
            'name': 'MFAS v1.3 + Accumulation Score',
            'description': '4차함수 c자리 + 외인 매집 추세 + 20일선 횡단 + 거래량 비대칭. 형 통찰: 외인과 동일 포지션 잡기.',
            'signals': ['c_alignment', 'foreign_holding_trend',
                        'ma20_crossings', 'volume_asymmetry', 'china_recovery_play'],
            'phases': {
                'stealth_accumulation': '🎯 진짜 외인 매집중 (최우선)',
                'quiet_accumulation': '🐢 조용한 매집중',
                'early_breakout': '🌱 막 깨고 나옴',
                'in_progress': '⚪ 진행 중',
                'already_run': '🔥 이미 폭발 (검증용)',
                'risky': '⚠️ 외인 매도 중',
            },
        },
        'summary': {
            'five_stars': sum(1 for r in results if r['stars'] == 5),
            'four_stars': sum(1 for r in results if r['stars'] == 4),
            'three_stars': sum(1 for r in results if r['stars'] == 3),
            'stealth_accumulation': sum(1 for r in results if r['phase'] == 'stealth_accumulation'),
            'quiet_accumulation': sum(1 for r in results if r['phase'] == 'quiet_accumulation'),
            'early_breakout': sum(1 for r in results if r['phase'] == 'early_breakout'),
            'china_plays': sum(1 for r in results if r['is_china_play']),
        },
        'stocks': results,
        'disclaimer': '본 데이터는 4차함수 패턴 매칭 + 외인 매집 추세 분석 결과이며 투자 권유가 아닙니다. 모든 투자 판단과 책임은 본인에게 있습니다.',
    }

    # ★ numpy 타입 → Python native 전환 (JSON 직렬화 핵심)
    output = to_native(output)

    with open('jackpot-v2.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n완료: {len(results)}개 매칭, jackpot-v2.json 저장됨')
    print(f'  🎯 stealth_accumulation: {output["summary"]["stealth_accumulation"]}')
    print(f'  🐢 quiet_accumulation:   {output["summary"]["quiet_accumulation"]}')
    print(f'  🌱 early_breakout:       {output["summary"]["early_breakout"]}')
    print(f'  🇨🇳 China plays:          {output["summary"]["china_plays"]}')


if __name__ == '__main__':
    main()
