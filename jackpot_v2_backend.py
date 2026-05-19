"""
jackpot_v2_backend.py
==========================================
SIGVIEW 잭팟 도구 시즌2 v1.5
- NAVER 모바일 API에서 외인 데이터 받기 (KRX 인증 불필요)
- foreign-history.json에 누적 저장 (자체 외인 DB 구축)
- 외인 보유율 추세 분석 (진짜 형 본질)
- 4차함수 c자리 검출 (기존)
- 보조지표(OBV/AD/CMF) 제거 - 형 본질만
- 차트 데이터 포함 (모달용)
"""
import json
import os
import warnings
import time
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import linregress
from pykrx import stock

warnings.filterwarnings('ignore')

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST)
END_DATE = TODAY.strftime('%Y%m%d')
TODAY_STR = TODAY.strftime('%Y-%m-%d')

NAVER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'https://m.stock.naver.com/',
}

FOREIGN_HISTORY_FILE = 'foreign-history.json'

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
    '011170', '009830', '011780', '096770', '010950',
    '009540', '010140', '042660',
    '011200', '028670',
    '267250', '329180', '034020',
    '003490',
}


# ============================================================
# 유틸: numpy → native (JSON 직렬화)
# ============================================================
def to_native(obj):
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, (np.ndarray,)):
        return [to_native(x) for x in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


# ============================================================
# ★ v1.5 핵심 - NAVER 외인 데이터 + 누적 캐싱
# ============================================================
def fetch_naver_foreign(code, retry=2):
    """NAVER 모바일 API에서 외인/기관 데이터 받기"""
    url = f'https://m.stock.naver.com/api/stock/{code}/integration'
    for attempt in range(retry):
        try:
            r = requests.get(url, headers=NAVER_HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                deals = data.get('dealTrendInfos', [])
                if not deals:
                    return []
                results = []
                for d in deals:
                    bizdate = d.get('bizdate', '')
                    if not bizdate or len(bizdate) != 8:
                        continue
                    # YYYYMMDD → YYYY-MM-DD
                    date_str = f'{bizdate[:4]}-{bizdate[4:6]}-{bizdate[6:8]}'
                    
                    # 보유율 파싱 ("31.42%" → 31.42)
                    ratio_str = str(d.get('foreignerHoldRatio', '')).replace('%', '').replace(',', '').strip()
                    try:
                        ratio = float(ratio_str) if ratio_str else None
                    except ValueError:
                        ratio = None
                    
                    # 순매수 파싱 ("+37,111" → 37111)
                    buy_str = str(d.get('foreignerPureBuyQuant', '')).replace(',', '').replace('+', '').strip()
                    try:
                        buy = int(buy_str) if buy_str and buy_str != '-' else 0
                    except ValueError:
                        buy = 0
                    
                    # 기관 순매수
                    org_str = str(d.get('organPureBuyQuant', '')).replace(',', '').replace('+', '').strip()
                    try:
                        organ = int(org_str) if org_str and org_str != '-' else 0
                    except ValueError:
                        organ = 0
                    
                    results.append({
                        'date': date_str,
                        'foreign_ratio': ratio,
                        'foreign_net_buy': buy,
                        'organ_net_buy': organ,
                    })
                return results
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(0.5)
                continue
            else:
                return None
    return None


def load_foreign_history():
    """기존 누적 외인 히스토리 로드"""
    if not os.path.exists(FOREIGN_HISTORY_FILE):
        return {}
    try:
        with open(FOREIGN_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'history load 실패: {e}')
        return {}


def save_foreign_history(history):
    with open(FOREIGN_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_foreign_history(history, code, new_data):
    """누적 추가 - 기존 날짜 데이터는 덮어쓰지 않음 (역사 보존)"""
    if code not in history:
        history[code] = {}
    existing_dates = set(history[code].keys())
    added = 0
    for entry in new_data:
        date = entry['date']
        if date not in existing_dates:
            history[code][date] = {
                'fr': entry.get('foreign_ratio'),
                'fb': entry.get('foreign_net_buy'),
                'ob': entry.get('organ_net_buy'),
            }
            added += 1
    return added


def analyze_foreign_from_history(history, code):
    """누적된 외인 데이터로 추세 분석"""
    if code not in history or not history[code]:
        return {
            'trend': 'no_data',
            'latest_ratio': None,
            'change_30d': None,
            'change_90d': None,
            'slope_per_month': 0.0,
            'data_points': 0,
        }
    
    series = []
    for date, vals in history[code].items():
        fr = vals.get('fr')
        if fr is not None:
            series.append((date, fr))
    series.sort(key=lambda x: x[0])
    
    if not series:
        return {
            'trend': 'no_data',
            'latest_ratio': None,
            'change_30d': None,
            'change_90d': None,
            'slope_per_month': 0.0,
            'data_points': 0,
        }
    
    latest_ratio = series[-1][1]
    n = len(series)
    
    # 30일 전 비교
    change_30d = None
    if n >= 2:
        cutoff_30 = (TODAY - timedelta(days=30)).strftime('%Y-%m-%d')
        old_30 = [s for s in series if s[0] <= cutoff_30]
        if old_30:
            change_30d = round(latest_ratio - old_30[-1][1], 2)
    
    # 90일 전 비교
    change_90d = None
    if n >= 2:
        cutoff_90 = (TODAY - timedelta(days=90)).strftime('%Y-%m-%d')
        old_90 = [s for s in series if s[0] <= cutoff_90]
        if old_90:
            change_90d = round(latest_ratio - old_90[-1][1], 2)
    
    # 선형 회귀 기울기 (가용한 데이터 전체)
    slope_per_month = 0.0
    if n >= 5:
        try:
            x = np.arange(n, dtype=float)
            y = np.array([s[1] for s in series])
            slope, _, _, _, _ = linregress(x, y)
            # 데이터가 일별 또는 매일 안 모이는 경우 보정 어려움, 일단 그대로
            slope_per_month = float(slope * 20)  # 20거래일 = 약 1개월
        except Exception:
            slope_per_month = 0.0
    
    # 추세 분류 (데이터 충분할 때만)
    if n < 10:
        trend = 'gathering_data'
    elif slope_per_month > 0.1:
        trend = 'accumulating'
    elif slope_per_month > 0.03:
        trend = 'slight_up'
    elif slope_per_month < -0.1:
        trend = 'distributing'
    elif slope_per_month < -0.03:
        trend = 'slight_down'
    else:
        trend = 'flat'
    
    return {
        'trend': trend,
        'latest_ratio': round(latest_ratio, 2),
        'change_30d': change_30d,
        'change_90d': change_90d,
        'slope_per_month': round(slope_per_month, 3),
        'data_points': n,
    }


# ============================================================
# 4차함수 (기존)
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


# ============================================================
# Phase v1.5 - 형 본질만 (외인 추세 + 4차함수 + 20일선)
# ============================================================
def determine_phase_v15(ratio_pct, ma20_stealth, foreign_trend):
    """
    핵심: 외인 보유율이 정말 늘고 있는가 + 가격이 횡보중인가
    """
    # 외인 데이터 충분 + 외인 매집중 + c자리 ±15% + 20일선 횡단
    if (-15 <= ratio_pct <= 15) and ma20_stealth and foreign_trend in ('accumulating', 'slight_up'):
        return 'stealth_accumulation'
    
    # 외인 매집중 + 가격 횡보 (20일선 약함)
    if (-15 <= ratio_pct <= 15) and foreign_trend in ('accumulating', 'slight_up'):
        return 'quiet_accumulation'
    
    # 외인 데이터 부족 + c±15% + 20일선 횡단 (조건부 매집 추정)
    if (-15 <= ratio_pct <= 15) and ma20_stealth and foreign_trend in ('gathering_data', 'no_data'):
        return 'likely_accumulation'  # 데이터 누적되면 확실해질 종목
    
    # 막 깨고 나오는 중
    if 10 < ratio_pct <= 30 and foreign_trend in ('accumulating', 'slight_up', 'flat', 'gathering_data'):
        return 'early_breakout'
    
    if 30 < ratio_pct <= 60:
        return 'in_progress'
    
    if ratio_pct > 60:
        return 'already_run'
    
    if foreign_trend == 'distributing':
        return 'risky'
    
    if ratio_pct < -15:
        return 'failed'
    
    return 'neutral'


def determine_verdict_v15(stars, phase):
    if phase == 'stealth_accumulation':
        return '🎯 외인 매집중 (확정)'
    if phase == 'quiet_accumulation':
        return '🐢 외인 조용한 매집'
    if phase == 'likely_accumulation':
        return '🔍 매집 추정 (데이터 누적중)'
    if phase == 'early_breakout':
        return '🌱 막 깨고 나옴'
    if phase == 'in_progress':
        return '⚪ 진행 중'
    if phase == 'already_run':
        return '🔥 이미 폭발 (검증)'
    if phase == 'risky':
        return '⚠️ 외인 매도중'
    if phase == 'failed':
        return '❌ 약함'
    return f'★{stars} 단독'


def calc_score_v15(stars, phase, ma20_data, foreign_data, is_china):
    score = stars * 10
    phase_score = {
        'stealth_accumulation': 35,
        'quiet_accumulation': 25,
        'likely_accumulation': 15,  # 추정이라 보너스 약하게
        'early_breakout': 15,
        'in_progress': 5,
        'already_run': -5,
        'risky': -15,
        'failed': -20,
        'neutral': 0,
    }
    score += phase_score.get(phase, 0)
    
    # 외인 추세 가중치
    ft = foreign_data['trend']
    if ft == 'accumulating':
        score += 20
    elif ft == 'slight_up':
        score += 10
    elif ft == 'distributing':
        score -= 15
    elif ft == 'slight_down':
        score -= 5
    
    # 20일선 매매 스텔스
    if ma20_data['is_stealth']:
        score += 10
    
    # 중국 수혜
    if is_china:
        score += 5
    
    return int(max(0, min(100, score)))


# ============================================================
# 데이터 수집
# ============================================================
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


def extract_chart_data(df, max_points=300):
    if df is None or len(df) == 0:
        return None
    if len(df) > max_points:
        step = len(df) // max_points
        df = df.iloc[::step]
    return {
        'dates': [d.strftime('%Y-%m-%d') for d in df.index],
        'closes': [round(float(c), 1) for c in df['종가'].values],
    }


def analyze_stock(code, name, foreign_history):
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
    foreign_data = analyze_foreign_from_history(foreign_history, code)
    
    ratios = []
    for k in ['daily', 'weekly', 'monthly']:
        if k in alignment and alignment[k]:
            ratios.append(alignment[k]['ratio_pct'])
    avg_ratio = float(np.mean(ratios)) if ratios else 0.0
    
    phase = determine_phase_v15(avg_ratio, ma20_data['is_stealth'], foreign_data['trend'])
    verdict = determine_verdict_v15(alignment['stars'], phase)
    is_china = code in CHINA_DIRECT
    accum_score = calc_score_v15(alignment['stars'], phase, ma20_data, foreign_data, is_china)

    chart_data = {
        'daily': extract_chart_data(df_d_5y, max_points=300),
        'weekly': extract_chart_data(df_w, max_points=300),
        'monthly': extract_chart_data(df_m, max_points=200),
    }

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
            'foreign_trend': foreign_data['trend'],
            'foreign_latest_ratio': foreign_data['latest_ratio'],
            'foreign_change_30d': foreign_data['change_30d'],
            'foreign_change_90d': foreign_data['change_90d'],
            'foreign_slope_per_month': foreign_data['slope_per_month'],
            'foreign_data_points': foreign_data['data_points'],
            'ma20_crossings': ma20_data['count'],
            'ma20_stealth': bool(ma20_data['is_stealth']),
            'price_range_pct': ma20_data['price_range_pct'],
        },
        'frames': {
            'daily': alignment.get('daily'),
            'weekly': alignment.get('weekly'),
            'monthly': alignment.get('monthly'),
        },
        'chart': chart_data,
    }


# ============================================================
# 메인
# ============================================================
def main():
    print(f'[SIGVIEW 잭팟 시즌2 v1.5] {TODAY.strftime("%Y-%m-%d %H:%M:%S")} KST')
    print(f'경기민감주 풀: {len(CYCLICAL)}개')
    print(f'외인 데이터: NAVER 모바일 API + 누적 캐싱 ({FOREIGN_HISTORY_FILE})')
    print()
    
    # Step 1: 누적 외인 히스토리 로드
    foreign_history = load_foreign_history()
    print(f'외인 히스토리 로드: {len(foreign_history)}개 종목 기록 있음')
    
    # Step 2: NAVER에서 최신 외인 데이터 받기 (모든 종목)
    print('\n[Step 1] NAVER에서 최신 외인 데이터 수집')
    print('-' * 60)
    fetch_success = 0
    total_new_records = 0
    for i, (code, name) in enumerate(CYCLICAL.items(), 1):
        new_data = fetch_naver_foreign(code)
        if new_data:
            added = update_foreign_history(foreign_history, code, new_data)
            total_new_records += added
            fetch_success += 1
            if i <= 3 or added > 0:
                print(f'  [{i}/{len(CYCLICAL)}] {name}: {len(new_data)}일치 받음, {added}일 신규 누적')
        else:
            print(f'  [{i}/{len(CYCLICAL)}] {name}: NAVER 실패')
        time.sleep(0.1)  # rate limit
    
    save_foreign_history(foreign_history)
    print(f'\nNAVER 성공: {fetch_success}/{len(CYCLICAL)}, 신규 누적: {total_new_records}건')
    print(f'외인 히스토리 저장 완료')
    
    # Step 3: 종목 분석
    print('\n[Step 2] 종목 분석 (4차함수 + 외인 추세)')
    print('-' * 60)
    results = []
    for i, (code, name) in enumerate(CYCLICAL.items(), 1):
        try:
            r = analyze_stock(code, name, foreign_history)
            if r:
                results.append(r)
                china_tag = ' 🇨🇳' if r['is_china_play'] else ''
                fs = r['signals']
                fi_info = f'{fs["foreign_trend"]}'
                if fs['foreign_latest_ratio'] is not None:
                    fi_info += f' {fs["foreign_latest_ratio"]:.1f}%'
                if fs['foreign_change_30d'] is not None:
                    fi_info += f' (30d: {fs["foreign_change_30d"]:+.2f}%p)'
                fi_info += f' [n={fs["foreign_data_points"]}]'
                print(f'  [{i}/{len(CYCLICAL)}] {name}{china_tag} ★{r["stars"]} '
                      f'점수{r["accumulation_score"]} {r["verdict"]}')
                print(f'           외인: {fi_info}')
            else:
                print(f'  [{i}/{len(CYCLICAL)}] {name} - 매칭 없음')
        except Exception as e:
            print(f'  [{i}/{len(CYCLICAL)}] {name} - 에러: {str(e)[:100]}')

    results.sort(key=lambda x: -x['accumulation_score'])
    for i, r in enumerate(results, 1):
        r['rank'] = i

    output = {
        'version': '2.0', 'season': 2, 'algo_version': '1.5',
        'generated_at': TODAY.isoformat(),
        'scan_universe': 'cyclical_korea',
        'n_scanned': len(CYCLICAL), 'n_matched': len(results),
        'foreign_data': {
            'source': 'NAVER mobile API (m.stock.naver.com)',
            'storage': FOREIGN_HISTORY_FILE,
            'total_codes_tracked': len(foreign_history),
            'fetch_success_today': fetch_success,
            'new_records_today': total_new_records,
        },
        'algorithm': {
            'name': 'MFAS v1.5',
            'description': '4차함수 c자리 + NAVER 외인 보유율 추세 + 20일선 횡단. 보조지표 없음, 형 본질만.',
            'phases': {
                'stealth_accumulation': '🎯 외인 매집 확정',
                'quiet_accumulation': '🐢 외인 조용한 매집',
                'likely_accumulation': '🔍 매집 추정 (데이터 부족)',
                'early_breakout': '🌱 막 깨고 나옴',
                'already_run': '🔥 이미 폭발 (검증)',
                'risky': '⚠️ 외인 매도중',
            },
        },
        'summary': {
            'five_stars': sum(1 for r in results if r['stars'] == 5),
            'four_stars': sum(1 for r in results if r['stars'] == 4),
            'three_stars': sum(1 for r in results if r['stars'] == 3),
            'stealth_accumulation': sum(1 for r in results if r['phase'] == 'stealth_accumulation'),
            'quiet_accumulation': sum(1 for r in results if r['phase'] == 'quiet_accumulation'),
            'likely_accumulation': sum(1 for r in results if r['phase'] == 'likely_accumulation'),
            'early_breakout': sum(1 for r in results if r['phase'] == 'early_breakout'),
            'china_plays': sum(1 for r in results if r['is_china_play']),
        },
        'stocks': results,
        'disclaimer': '본 데이터는 4차함수 패턴 매칭 + NAVER 외인 보유율 추세 분석 결과이며 투자 권유가 아닙니다. 모든 투자 판단과 책임은 본인에게 있습니다.',
    }

    output = to_native(output)

    with open('jackpot-v2.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n완료: {len(results)}개 매칭')
    print(f'  🎯 외인매집 확정:   {output["summary"]["stealth_accumulation"]}')
    print(f'  🐢 외인 조용매집:   {output["summary"]["quiet_accumulation"]}')
    print(f'  🔍 매집 추정:       {output["summary"]["likely_accumulation"]}')
    print(f'  🌱 막 깨고 나옴:    {output["summary"]["early_breakout"]}')
    print(f'  🇨🇳 중국 플레이:     {output["summary"]["china_plays"]}')


if __name__ == '__main__':
    main()
