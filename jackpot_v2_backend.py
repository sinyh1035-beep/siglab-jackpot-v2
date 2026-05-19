"""
jackpot_v2_backend.py
==========================================
SIGVIEW 잭팟 도구 시즌2 v2.1
- pykrx 자동 종목 빌더 (시총 1조+ cyclical)
- 약 80개 종목 자동 발굴 (41개 시드 + 자동 추가)
- 매일 시총 변화 자동 반영
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

NAVER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'https://m.stock.naver.com/',
}

FOREIGN_HISTORY_FILE = 'foreign-history.json'

# ============================================================
# 시드 종목 (항상 포함 - 보험)
# ============================================================
SEED_STOCKS = {
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

# 중국 수혜 종목 (직접)
CHINA_DIRECT = {
    '005490', '004020', '010130', '103140',
    '011170', '009830', '011780', '096770', '010950',
    '009540', '010140', '042660',
    '011200', '028670',
    '267250', '329180', '034020',
    '003490',
}

# Cyclical 키워드 (종목명 기반 분류)
CYCLICAL_KEYWORDS = [
    # 반도체
    '반도체', '하이닉스', '디스플레이', '실리콘', '에스앤에스텍', 'DB하이텍',
    # 2차전지/소재
    '에코프로', '엘앤에프', '코스모신소재', '포스코퓨처엠',
    # 자동차
    '현대차', '기아', '모비스', '만도', '한국타이어', '넥센타이어', '한라', 'HL',
    # 조선
    '조선', '중공업', '오션', '미포', 'HD한국',
    # 철강/비철
    '제철', '철강', '세아', '동국', '고려아연', '풍산', 'POSCO', '포스코',
    # 화학/정유
    '케미칼', '화학', '석유', '에너지', 'OCI', 'SK이노베이션', 'S-Oil', '에쓰오일',
    # 건설/건자재
    '건설', '시멘트', '쌍용씨앤이', 'HDC', '대우건설', '대림', 'DL',
    # 운송
    'HMM', '팬오션', '대한항공', '아시아나', '진에어', '제주항공', '한진',
    # 방산/항공
    '에어로스페이스', '한화시스템', 'LIG넥스원', '한국항공우주', '풍산',
    # 원자력/유틸리티
    '한전', '두산에너빌리티', '씨에스윈드', '두산',
    # 종합상사
    'LX인터내셔널', 'GS글로벌', '삼성물산', '포스코인터내셔널',
    # 기계
    '두산밥캣', '한온시스템', '현대건설기계',
]

# Cyclical 직접 매핑 (종목명 → 카테고리 + 중국 여부)
CYCLICAL_DIRECT_MAP = {
    # 종목코드: (카테고리, 중국 수혜 여부)
    # 추가 cyclical 후보들 (시총 1조+ 추정)
    '010620': ('조선', True),     # 현대미포조선
    '010060': ('화학', False),    # OCI홀딩스
    '001230': ('철강', True),     # 동국홀딩스
    '008060': ('전자', False),    # 대덕전자
    '012630': ('건설', False),    # HDC
    '001120': ('상사', True),     # LX인터내셔널
    '011790': ('화학', False),    # SKC
    '003030': ('철강', True),     # 세아제강지주
    '003410': ('시멘트', False),  # 쌍용씨앤이
    '001250': ('상사', True),     # GS글로벌
    '002990': ('건설', False),    # 금호건설
    '005010': ('철강', True),     # 휴스틸
    '028050': ('건설', False),    # 삼성E&A
    '000150': ('자동차', False),  # 두산
    '241560': ('기계', False),    # 두산밥캣
    '267260': ('기계', False),    # HD현대일렉트릭
    '329180': ('조선', True),     # HD현대중공업
    '042700': ('반도체', False),  # 한미반도체
    '161390': ('자동차', False),  # 한국타이어
    '000240': ('자동차', False),  # 한라
    '004990': ('상사', False),    # 롯데지주
    '120110': ('화학', False),    # 코오롱인더
    '000880': ('상사', False),    # 한화
    '012450': ('방산', False),    # 한화에어로스페이스
    '014820': ('자동차', False),  # 동원시스템즈
    '298050': ('화학', False),    # 효성첨단소재
    '298040': ('화학', False),    # 효성중공업
    '004800': ('상사', False),    # 효성
    '298000': ('화학', False),    # 효성화학
    '002380': ('철강', True),     # KCC
    '001530': ('철강', True),     # DI동일
    '083420': ('철강', True),     # 그린플러스
    '006650': ('화학', False),    # 대한유화
    '120030': ('화학', False),    # 조선내화
    '000390': ('자동차', False),  # 삼화페인트
    '004990': ('상사', False),    # 롯데지주
    '009830': ('화학', False),    # 한화솔루션 (중복)
    '002030': ('철강', True),     # 아세아
    '000370': ('자동차', False),  # 한화손해보험 (사실 금융이라 제외)
    '011210': ('화학', False),    # 현대위아
    '241560': ('기계', False),    # 두산밥캣
    '042660': ('조선', True),     # 한화오션
}


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
# ★ v2.1 핵심 - 자동 종목 빌더
# ============================================================
def is_cyclical_name(name):
    """종목명으로 cyclical 여부 추정"""
    if not name:
        return False
    for kw in CYCLICAL_KEYWORDS:
        if kw in name:
            return True
    return False


def build_universe(min_cap_eok=10000):
    """
    pykrx로 시총 N억 이상 cyclical 종목 자동 빌드
    - SEED_STOCKS (41개) 항상 포함
    - 시총 1조+ 중 cyclical 키워드 매칭 종목 추가
    
    min_cap_eok: 최소 시총 (억원). 10000 = 1조
    """
    universe = dict(SEED_STOCKS)  # 시드 복사
    china_set = set(CHINA_DIRECT)
    
    print(f'  종목 풀 빌드 시작 (시드 {len(universe)}개)')
    
    # 어제 날짜로 시총 조회 (오늘 장 안 끝났을 수 있음)
    yesterday = TODAY - timedelta(days=1)
    # 주말이면 금요일로
    while yesterday.weekday() >= 5:
        yesterday -= timedelta(days=1)
    cap_date = yesterday.strftime('%Y%m%d')
    
    added = 0
    skipped = 0
    
    for market in ['KOSPI', 'KOSDAQ']:
        try:
            cap_df = stock.get_market_cap_by_ticker(cap_date, market=market)
            if cap_df is None or len(cap_df) == 0:
                print(f'    {market}: 시총 데이터 없음')
                continue
            
            # 시총 1조+ 필터 (시총 컬럼명: '시가총액')
            cap_col = '시가총액' if '시가총액' in cap_df.columns else cap_df.columns[0]
            min_cap = min_cap_eok * 1e8  # 억 → 원
            big_caps = cap_df[cap_df[cap_col] >= min_cap]
            
            print(f'    {market} 시총 {min_cap_eok/10000:.0f}조+: {len(big_caps)}개')
            
            for code in big_caps.index:
                if code in universe:
                    continue
                
                try:
                    name = stock.get_market_ticker_name(code)
                    if not name:
                        continue
                    
                    # cyclical 판정: 키워드 매칭 OR 직접 매핑
                    is_cyc = False
                    if code in CYCLICAL_DIRECT_MAP:
                        is_cyc = True
                        _, is_china = CYCLICAL_DIRECT_MAP[code]
                        if is_china:
                            china_set.add(code)
                    elif is_cyclical_name(name):
                        is_cyc = True
                    
                    if is_cyc:
                        universe[code] = name
                        added += 1
                    else:
                        skipped += 1
                except Exception as e:
                    continue
        except Exception as e:
            print(f'    {market} 조회 실패: {e}')
            continue
    
    print(f'  ✓ 자동 발굴: {added}개 추가, {skipped}개 비-cyclical 제외')
    print(f'  ✓ 최종 종목 풀: {len(universe)}개')
    return universe, china_set


# ============================================================
# NAVER 외인
# ============================================================
def fetch_naver_foreign(code, retry=2):
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
                    date_str = f'{bizdate[:4]}-{bizdate[4:6]}-{bizdate[6:8]}'
                    ratio_str = str(d.get('foreignerHoldRatio', '')).replace('%', '').replace(',', '').strip()
                    try:
                        ratio = float(ratio_str) if ratio_str else None
                    except ValueError:
                        ratio = None
                    results.append({'date': date_str, 'foreign_ratio': ratio})
                return results
        except Exception:
            if attempt < retry - 1:
                time.sleep(0.5)
                continue
    return None


def load_foreign_history():
    if not os.path.exists(FOREIGN_HISTORY_FILE):
        return {}
    try:
        with open(FOREIGN_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_foreign_history(history):
    with open(FOREIGN_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_foreign_history(history, code, new_data):
    if code not in history:
        history[code] = {}
    existing_dates = set(history[code].keys())
    added = 0
    for entry in new_data:
        date = entry['date']
        if date not in existing_dates:
            history[code][date] = {'fr': entry.get('foreign_ratio')}
            added += 1
    return added


def analyze_foreign_from_history(history, code):
    if code not in history or not history[code]:
        return {'trend': 'no_data', 'latest_ratio': None, 'change_30d': None, 'data_points': 0}
    series = []
    for date, vals in history[code].items():
        fr = vals.get('fr')
        if fr is not None:
            series.append((date, fr))
    series.sort(key=lambda x: x[0])
    if not series:
        return {'trend': 'no_data', 'latest_ratio': None, 'change_30d': None, 'data_points': 0}
    latest_ratio = series[-1][1]
    n = len(series)
    change_30d = None
    if n >= 2:
        cutoff_30 = (TODAY - timedelta(days=30)).strftime('%Y-%m-%d')
        old_30 = [s for s in series if s[0] <= cutoff_30]
        if old_30:
            change_30d = round(latest_ratio - old_30[-1][1], 2)
    slope_per_month = 0.0
    if n >= 5:
        try:
            x = np.arange(n, dtype=float)
            y = np.array([s[1] for s in series])
            slope, _, _, _, _ = linregress(x, y)
            slope_per_month = float(slope * 20)
        except Exception:
            slope_per_month = 0.0
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
        'trend': trend, 'latest_ratio': round(latest_ratio, 2),
        'change_30d': change_30d, 'data_points': n,
    }


# ============================================================
# 4차함수 c자리
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
                                'daily': d, 'weekly': w, 'monthly': m, 'score': float(score)}
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
    return {'count': crossings, 'price_range_pct': round(price_range_pct, 1), 'is_stealth': is_stealth}


def determine_phase(ratio_pct, ma20_stealth, foreign_trend):
    if (-15 <= ratio_pct <= 15) and ma20_stealth and foreign_trend in ('accumulating', 'slight_up'):
        return 'stealth_accumulation'
    if (-15 <= ratio_pct <= 15) and foreign_trend in ('accumulating', 'slight_up'):
        return 'quiet_accumulation'
    if (-15 <= ratio_pct <= 15) and ma20_stealth and foreign_trend in ('gathering_data', 'no_data'):
        return 'likely_accumulation'
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


def determine_verdict(stars, phase):
    if phase == 'stealth_accumulation': return '🎯 외인 매집 확정'
    if phase == 'quiet_accumulation': return '🐢 외인 조용한 매집'
    if phase == 'likely_accumulation': return '🔍 매집 추정'
    if phase == 'early_breakout': return '🌱 막 깨고 나옴'
    if phase == 'in_progress': return '⚪ 진행 중'
    if phase == 'already_run': return '🔥 이미 폭발'
    if phase == 'risky': return '⚠️ 외인 매도중'
    if phase == 'failed': return '❌ 약함'
    return f'★{stars}'


def calc_score(stars, phase, ma20_data, foreign_data, is_china):
    score = stars * 10
    phase_score = {
        'stealth_accumulation': 35, 'quiet_accumulation': 25,
        'likely_accumulation': 15, 'early_breakout': 15,
        'in_progress': 5, 'already_run': -5,
        'risky': -15, 'failed': -20, 'neutral': 0,
    }
    score += phase_score.get(phase, 0)
    ft = foreign_data['trend']
    if ft == 'accumulating': score += 20
    elif ft == 'slight_up': score += 10
    elif ft == 'distributing': score -= 15
    elif ft == 'slight_down': score -= 5
    if ma20_data['is_stealth']: score += 10
    if is_china: score += 5
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


def extract_chart_data(df, max_points=300):
    if df is None or len(df) == 0:
        return None
    ma20 = df['종가'].rolling(20).mean()
    if len(df) > max_points:
        step = len(df) // max_points
        df_ds = df.iloc[::step]
        ma20_ds = ma20.iloc[::step]
    else:
        df_ds = df
        ma20_ds = ma20
    return {
        'dates': [d.strftime('%Y-%m-%d') for d in df_ds.index],
        'closes': [round(float(c), 1) for c in df_ds['종가'].values],
        'ma20': [round(float(v), 1) if not pd.isna(v) else None for v in ma20_ds.values],
    }


def analyze_stock(code, name, foreign_history, china_set):
    df_d_5y = get_daily(code, 5)
    if df_d_5y is None or len(df_d_5y) < 250:
        return None

    df_d_long = get_daily(code, 20)
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
    
    phase = determine_phase(avg_ratio, ma20_data['is_stealth'], foreign_data['trend'])
    verdict = determine_verdict(alignment['stars'], phase)
    is_china = code in china_set
    accum_score = calc_score(alignment['stars'], phase, ma20_data, foreign_data, is_china)

    chart_data = {
        'daily': extract_chart_data(df_d_5y, max_points=300),
        'weekly': extract_chart_data(df_w, max_points=300),
        'monthly': extract_chart_data(df_m, max_points=300),
    }
    
    data_info = {
        'daily_years': round(len(df_d_5y) / 252, 1),
        'weekly_years': round(len(df_w) / 52, 1),
        'monthly_years': round(len(df_m) / 12, 1),
    }

    return {
        'code': code, 'name': name,
        'stars': int(alignment['stars']),
        'phase': phase, 'verdict': verdict,
        'accumulation_score': accum_score,
        'is_china_play': bool(is_china),
        'avg_ratio_pct': round(avg_ratio, 1),
        'signals': {
            'foreign_trend': foreign_data['trend'],
            'foreign_latest_ratio': foreign_data['latest_ratio'],
            'foreign_change_30d': foreign_data['change_30d'],
            'foreign_data_points': foreign_data['data_points'],
            'ma20_crossings': ma20_data['count'],
            'ma20_stealth': bool(ma20_data['is_stealth']),
        },
        'chart': chart_data,
        'data_info': data_info,
    }


def main():
    print(f'[SIGVIEW 잭팟 시즌2 v2.1] {TODAY.strftime("%Y-%m-%d %H:%M:%S")} KST')
    print(f'자동 종목 빌더 + NAVER 외인 + 4차함수 c자리')
    print()
    
    # ★ Step 0: 자동 종목 빌드
    print('[Step 0] 종목 풀 자동 빌드')
    print('-' * 60)
    universe, china_set = build_universe(min_cap_eok=10000)  # 1조+
    print()
    
    # Step 1: 외인 히스토리 로드
    foreign_history = load_foreign_history()
    print(f'외인 히스토리: {len(foreign_history)}개 종목 기록')
    
    print('\n[Step 1] NAVER 외인 데이터 수집')
    print('-' * 60)
    fetch_success = 0
    total_new_records = 0
    for code, name in universe.items():
        new_data = fetch_naver_foreign(code)
        if new_data:
            added = update_foreign_history(foreign_history, code, new_data)
            total_new_records += added
            fetch_success += 1
        time.sleep(0.3)  # rate limit 강화 (80개라)
    save_foreign_history(foreign_history)
    print(f'성공: {fetch_success}/{len(universe)}, 신규 누적: {total_new_records}건')
    
    print('\n[Step 2] 종목 분석')
    print('-' * 60)
    results = []
    matched_count = 0
    for i, (code, name) in enumerate(universe.items(), 1):
        try:
            r = analyze_stock(code, name, foreign_history, china_set)
            if r:
                results.append(r)
                matched_count += 1
                china_tag = ' 🇨🇳' if r['is_china_play'] else ''
                if i % 10 == 0 or i <= 5 or r['accumulation_score'] >= 50:
                    print(f'  [{i}/{len(universe)}] {name}{china_tag} ★{r["stars"]} '
                          f'점수{r["accumulation_score"]} {r["verdict"]}')
        except Exception as e:
            print(f'  [{i}/{len(universe)}] {name} - 에러: {str(e)[:80]}')

    results.sort(key=lambda x: -x['accumulation_score'])
    for i, r in enumerate(results, 1):
        r['rank'] = i

    output = {
        'version': '2.0', 'season': 2, 'algo_version': '2.1',
        'generated_at': TODAY.isoformat(),
        'n_scanned': len(universe), 'n_matched': len(results),
        'foreign_data': {
            'source': 'NAVER mobile API',
            'total_codes_tracked': len(foreign_history),
            'fetch_success_today': fetch_success,
            'new_records_today': total_new_records,
        },
        'algorithm': {
            'name': 'SIGVIEW 시즌2 v2.1',
            'description': '자동 종목 빌더 (시총 1조+ cyclical) + 4차함수 + 외인 매집',
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
        'disclaimer': '4차함수 패턴 매칭 + NAVER 외인 보유율 분석. 투자 권유 X.',
    }

    output = to_native(output)
    with open('jackpot-v2.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n완료: {len(results)}개 매칭 / {len(universe)}개 스캔')


if __name__ == '__main__':
    main()
