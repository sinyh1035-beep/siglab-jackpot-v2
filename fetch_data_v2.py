"""
SIGVIEW 잭팟 스캐너 시즌2 v2.0
==========================================
시즌1 v3.7.2 구조 100% 재사용 + 4차함수 c자리 자동 검출만 추가
- 시즌1과 동일: yfinance batch / fdr 시총 / Daum 외인 / KIS 60일 / 5중 곱셈
- 시즌2 추가: 4차함수 f(x)-g(x)=k(x-a)(x-b)(x-c)² c자리 → 6번째 배수
- 출력: jackpot-v2.json (시즌1 jackpot.json과 별도)
"""

import json
import os
import sys
import time
from datetime import datetime
from ftplib import FTP
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf
import requests
import FinanceDataReader as fdr
from scipy.optimize import curve_fit

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 시즌1 kis_client.py / dart_client.py 그대로 재사용
try:
    from kis_client import KISClient
    from dart_client import DARTClient
except ImportError:
    KISClient = None
    DARTClient = None

FTP_HOST = os.environ.get('FTP_HOST', '')
FTP_USER = os.environ.get('FTP_USER', '')
FTP_PASS = os.environ.get('FTP_PASS', '')
FTP_TARGET_DIR = os.environ.get('FTP_TARGET_DIR', '/wp-content/data')

THRESHOLD = 500_000_000_000  # 시총 5천억
OUTPUT_FILE = 'jackpot-v2.json'  # ★ 시즌1과 다른 파일명

# 시즌1 그대로 - 2001~2008 골든 종목
GOLDEN_LIST_2001_2008 = {
    '005880': {'name': '대한해운', 'multi': 93, 'peak': '2007-10'},
    '028670': {'name': '팬오션', 'multi': 2.4, 'peak': '2007-10'},
    '011200': {'name': 'HMM', 'multi': 22, 'peak': '2007-10'},
    '010140': {'name': '삼성중공업', 'multi': 14, 'peak': '2007-07'},
    '042660': {'name': '한화오션', 'multi': 22, 'peak': '2007-10'},
    '005490': {'name': 'POSCO홀딩스', 'multi': 10, 'peak': '2007-10'},
    '004020': {'name': '현대제철', 'multi': 38, 'peak': '2007-10'},
    '001230': {'name': '동국제강', 'multi': 222, 'peak': '2007-10'},
    '010130': {'name': '고려아연', 'multi': 23, 'peak': '2007-07'},
    '010950': {'name': 'S-Oil', 'multi': 10, 'peak': '2007-12'},
    '011170': {'name': '롯데케미칼', 'multi': 32, 'peak': '2007-09'},
    '011780': {'name': '금호석유', 'multi': 42, 'peak': '2007-10'},
    '051910': {'name': 'LG화학', 'multi': 13, 'peak': '2007-11'},
    '000150': {'name': '두산', 'multi': 18, 'peak': '2007-11'},
    '034020': {'name': '두산에너빌리티', 'multi': 55, 'peak': '2007-11'},
    '028050': {'name': '삼성E&A', 'multi': 69, 'peak': '2007-10'},
    '001120': {'name': 'LX인터내셔널', 'multi': 34, 'peak': '2007-07'},
    '010060': {'name': 'OCI', 'multi': 119, 'peak': '2008-05'},
}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)


# ============================================================
# Step 1~7: 시즌1과 동일
# ============================================================
def get_stock_list():
    log("Step 1/9: 시총 5천억+ 종목 리스트...")
    krx = fdr.StockListing('KRX')
    krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
    filtered = krx[krx['Marcap'] >= THRESHOLD].copy()
    filtered = filtered.sort_values('Marcap', ascending=False).reset_index(drop=True)
    log(f"  -> {len(filtered)}개")
    return filtered


def get_kospi_3y_return():
    log("Step 2/9: KOSPI 3년 수익률 (거시 기준값)...")
    try:
        kospi = yf.Ticker("^KS11").history(period='3y', interval='1d').dropna()
        if len(kospi) > 250:
            ret = (kospi['Close'].iloc[-1] - kospi['Close'].iloc[0]) / kospi['Close'].iloc[0] * 100
            log(f"  -> KOSPI 3년 수익률: {ret:+.1f}%")
            return ret
    except Exception as e:
        log(f"  ⚠ KOSPI 데이터 실패: {e}")
    return 200


def fetch_prices(stocks):
    """10년치 일봉 - yfinance batch (50개씩)"""
    log(f"Step 3/9: 가격 10년치 일봉 ({len(stocks)}종목)...")
    all_data = {}
    BATCH = 50
    t0 = time.time()
    for i in range(0, len(stocks), BATCH):
        batch = stocks.iloc[i:i+BATCH]
        codes_yf = [f"{row['Code']}.{'KS' if row['Market']=='KOSPI' else 'KQ'}" for _, row in batch.iterrows()]
        try:
            data = yf.download(codes_yf, period='10y', interval='1d', group_by='ticker',
                              progress=False, threads=True, auto_adjust=True)
        except Exception:
            continue
        for _, row in batch.iterrows():
            yf_code = f"{row['Code']}.{'KS' if row['Market']=='KOSPI' else 'KQ'}"
            try:
                df = data[yf_code] if len(codes_yf) > 1 else data
                df = df.dropna()
                if len(df) > 100:
                    all_data[row['Code']] = {
                        'name': row['Name'],
                        'market': row['Market'],
                        'mcap': int(row['Marcap']),
                        'closes': [int(round(c)) for c in df['Close'].tolist()],
                        'vols': [int(v) for v in df['Volume'].tolist()],
                        'dates': [d.strftime('%Y-%m-%d') for d in df.index],
                    }
            except Exception:
                pass
        time.sleep(0.3)
    log(f"  -> {len(all_data)} ({time.time()-t0:.0f}초)")
    return all_data


def fetch_fundamentals(price_data):
    log(f"Step 4/9: PSR/ROE/영업이익률 ({len(price_data)}종목)...")
    def get_yf_info(code):
        for suffix in ['.KS', '.KQ']:
            try:
                info = yf.Ticker(f"{code}{suffix}").info
                if info.get('priceToSalesTrailing12Months') is not None or info.get('marketCap'):
                    return code, {
                        'psr': info.get('priceToSalesTrailing12Months'),
                        'roe': info.get('returnOnEquity'),
                        'opm': info.get('operatingMargins'),
                    }
            except Exception:
                continue
        return code, {}
    t0 = time.time()
    result = {}
    with ThreadPoolExecutor(max_workers=10) as exe:
        futures = {exe.submit(get_yf_info, c): c for c in price_data.keys()}
        for f in as_completed(futures):
            code, data = f.result()
            result[code] = data
    have = sum(1 for d in result.values() if d.get('psr'))
    log(f"  -> {have}/{len(result)} ({time.time()-t0:.0f}초)")
    return result


def fetch_foreign(price_data):
    log(f"Step 5/9: 외인 지분율 (Daum) ({len(price_data)}종목)...")
    def get_foreign(code):
        try:
            url = f"https://finance.daum.net/api/quotes/A{code}?summary=false"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': f'https://finance.daum.net/quotes/A{code}',
            }
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                return code, {'fr': d.get('foreignRatio')}
        except Exception:
            pass
        return code, {}
    t0 = time.time()
    result = {}
    with ThreadPoolExecutor(max_workers=15) as exe:
        futures = {exe.submit(get_foreign, c): c for c in price_data.keys()}
        for f in as_completed(futures):
            code, data = f.result()
            result[code] = data
    have = sum(1 for d in result.values() if d.get('fr'))
    log(f"  -> {have}/{len(result)} ({time.time()-t0:.0f}초)")
    return result


def fetch_kis_data(price_data):
    log(f"Step 6/9: KIS 외인 매매 시계열 ({len(price_data)}종목)...")
    if not os.environ.get('KIS_APP_KEY') or KISClient is None:
        log("  ⚠ KIS 키 또는 클라이언트 없음 - 건너뜀")
        return {}
    try:
        kis = KISClient()
    except Exception as e:
        log(f"  ⚠ KIS 초기화 실패: {e}")
        return {}
    result = {}
    t0 = time.time()
    def fetch_one(code):
        try:
            return code, kis.get_investor_trend(code, days=60)
        except Exception:
            return code, []
    with ThreadPoolExecutor(max_workers=5) as exe:
        futures = {exe.submit(fetch_one, c): c for c in price_data.keys()}
        for f in as_completed(futures):
            code, data = f.result()
            result[code] = data
    have = sum(1 for d in result.values() if d)
    log(f"  -> {have}/{len(result)} ({time.time()-t0:.0f}초)")
    return result


# ============================================================
# 시즌1 알고리즘 - 그대로 (5중 곱셈)
# ============================================================
def goose_score_v37(closes, vols):
    if len(closes) < 60: return 0, {}
    closes_arr = np.array(closes)
    score = 0
    breakdown = {}
    
    window_len = min(252, len(closes_arr))
    window = closes_arr[-window_len:]
    cv_1y = np.std(window) / np.mean(window)
    if cv_1y < 0.12: comp_s = 30
    elif cv_1y < 0.18: comp_s = 25
    elif cv_1y < 0.25: comp_s = 18
    elif cv_1y < 0.35: comp_s = 10
    else: comp_s = 0
    score += comp_s
    breakdown['cv_1y'] = round(cv_1y, 3)
    
    high_recent = np.max(window)
    from_high = (closes_arr[-1] - high_recent) / high_recent * 100
    if -50 <= from_high <= -25: dd_s = 25
    elif -60 <= from_high < -50: dd_s = 18
    elif -25 < from_high <= -15: dd_s = 18
    elif -70 <= from_high < -60: dd_s = 10
    elif -15 < from_high <= -5: dd_s = 12
    else: dd_s = 5
    score += dd_s
    breakdown['from_1y_high'] = round(from_high, 1)
    
    if len(closes_arr) >= 60:
        ma60 = np.mean(closes_arr[-60:])
        from_ma60 = (closes_arr[-1] - ma60) / ma60 * 100
        if -5 <= from_ma60 <= 15: ma_s = 25
        elif -15 <= from_ma60 < -5: ma_s = 20
        elif 15 < from_ma60 <= 30: ma_s = 15
        elif -25 <= from_ma60 < -15: ma_s = 10
        else: ma_s = 3
        score += ma_s
        breakdown['from_ma60'] = round(from_ma60, 1)
    
    if len(vols) >= 60:
        recent_v = np.mean(vols[-20:])
        prev_v = np.mean(vols[-60:-20])
        vol_ratio = recent_v / prev_v if prev_v > 0 else 1
        if 1.3 <= vol_ratio <= 2.5: vol_s = 20
        elif 1.1 <= vol_ratio < 1.3: vol_s = 12
        elif 2.5 < vol_ratio <= 4: vol_s = 15
        elif vol_ratio > 4: vol_s = 8
        else: vol_s = 3
        score += vol_s
        breakdown['vol_ratio'] = round(vol_ratio, 2)
    
    return score, breakdown


def psr_multiplier(psr):
    if psr is None: return 0.85
    if psr < 0.3: return 1.8
    if psr < 0.5: return 1.6
    if psr < 1.0: return 1.3
    if psr < 1.5: return 1.0
    if psr < 2.5: return 0.85
    return 0.6


def foreign_multiplier(fr_now, kis_60d=None):
    if fr_now is None: abs_mult = 1.0
    elif fr_now >= 35: abs_mult = 1.3
    elif fr_now >= 25: abs_mult = 1.2
    elif fr_now >= 15: abs_mult = 1.1
    elif fr_now >= 5: abs_mult = 1.0
    else: abs_mult = 0.9
    
    trend_mult = 1.0
    if kis_60d and len(kis_60d) >= 20:
        sorted_kis = sorted(kis_60d, key=lambda x: x['date'], reverse=True)[:60]
        recent_20 = sum(d.get('foreign_net', 0) for d in sorted_kis[:20])
        prev_20 = sum(d.get('foreign_net', 0) for d in sorted_kis[20:40]) if len(sorted_kis) >= 40 else 0
        if recent_20 > 0:
            if prev_20 > 0 and recent_20 > prev_20 * 1.5: trend_mult = 1.3
            elif prev_20 > 0: trend_mult = 1.15
            else: trend_mult = 1.2
        elif recent_20 < 0:
            if prev_20 < 0 and recent_20 < prev_20 * 1.5: trend_mult = 0.7
            elif prev_20 < 0: trend_mult = 0.85
            else: trend_mult = 0.9
    return (abs_mult + trend_mult) / 2


def macro_gap_multiplier(stock_3y_return, kospi_3y_return):
    gap = kospi_3y_return - stock_3y_return
    if gap >= 150: return 2.0
    elif gap >= 80: return 1.5
    elif gap >= 30: return 1.2
    elif gap >= -30: return 1.0
    elif gap >= -80: return 0.8
    else: return 0.6


def golden_multiplier(code):
    return 1.2 if code in GOLDEN_LIST_2001_2008 else 1.0


def cubic_stage(prices):
    n = len(prices)
    if n < 30: return None
    xs = np.linspace(0, 1, n)
    try:
        a, b, c, d = np.polyfit(xs, prices, 3)
        slope = 3*a + 2*b + c
        curv = 6*a + 2*b
        disc = b*b - 3*a*c
        l_min, l_max = None, None
        if disc >= 0 and a != 0:
            sq = np.sqrt(disc)
            p1 = (-b-sq)/(3*a); p2 = (-b+sq)/(3*a)
            if a > 0: l_max, l_min = p1, p2
            else: l_min, l_max = p1, p2
        if l_min is not None and -0.1 < l_min < 1:
            dist = 1 - l_min
            if l_max is not None and 1 < l_max < 1.5:
                ratio = dist / (l_max - l_min)
                if ratio < 0.20: st = "1단계"
                elif ratio < 0.50: st = "2단계"
                elif ratio < 0.80: st = "2단계후"
                else: st = "3단계"
            else:
                if dist < 0.20 and curv > 0: st = "1단계"
                elif curv > 0: st = "2단계"
                else: st = "3단계"
        elif slope < 0 and curv > 0: st = "바닥형성"
        elif slope < 0: st = "하락"
        elif slope > 0 and curv > 0: st = "가속"
        else: st = "감속"
        return {'st': st}
    except Exception:
        return None


def resample(closes, dates, freq):
    df = pd.DataFrame({'c': closes}, index=pd.to_datetime(dates))
    rs = df.resample(freq).last().dropna()
    return rs['c'].tolist(), [d.strftime('%Y-%m-%d') for d in rs.index]


def resample_vol(vols, dates, freq):
    df = pd.DataFrame({'v': vols}, index=pd.to_datetime(dates))
    return df.resample(freq).sum().dropna()['v'].tolist()


# ============================================================
# ★★★ 시즌2 핵심 추가 - 4차함수 c자리 검출 ★★★
# f(x) - g(x) = k(x-a)(x-b)(x-c)²
# c = 기러기자리 (이중근, 폭발 직전 매집기)
# ============================================================
def quartic_fn(x, k, a, b, c):
    return k * (x - a) * (x - b) * (x - c) ** 2


def fit_quartic(prices, x_norm):
    """가격 시계열에 4차함수 적합. 최선의 (k,a,b,c,R²) 반환"""
    if len(prices) < 30: return None, -np.inf
    g_base = np.percentile(prices, 20)
    h = prices - g_base
    best, best_r2 = None, -np.inf
    for a0, b0, c0 in [(0.10, 0.40, 0.80), (0.20, 0.50, 0.85),
                        (0.05, 0.35, 0.75), (0.15, 0.45, 0.90)]:
        try:
            scale = max(h.max(), 1)
            k0 = scale / max(abs((1 - a0) * (1 - b0) * (1 - c0) ** 2), 1e-6)
            popt, _ = curve_fit(quartic_fn, x_norm, h, p0=[k0, a0, b0, c0], maxfev=1500)
            k_f, a_f, b_f, c_f = popt
            if not (0 <= a_f < b_f < c_f <= 1) or k_f <= 0:
                continue
            y_fit = quartic_fn(x_norm, *popt)
            ss_res = np.sum((h - y_fit) ** 2)
            ss_tot = np.sum((h - h.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else -np.inf
            if r2 > best_r2:
                best_r2 = r2
                best = (k_f, a_f, b_f, c_f, g_base)
        except Exception:
            continue
    return best, best_r2


def detect_c_in_frame(closes_list, dates_list, r2_min=0.55):
    """단일 프레임에서 c자리 검출. 가장 좋은 c 후보 1개 반환"""
    if len(closes_list) < 60: return None
    prices = np.array(closes_list, dtype=float)
    n = len(prices)
    # 윈도우 크기 후보 (전체의 50%, 70%, 100%)
    win_sizes = [int(n * 0.5), int(n * 0.7), n]
    win_sizes = [w for w in win_sizes if w >= 30]
    
    best = None
    best_r2 = r2_min
    for win in win_sizes:
        prices_w = prices[-win:]
        x_norm = np.linspace(0, 1, win)
        fit_result, r2 = fit_quartic(prices_w, x_norm)
        if fit_result is None or r2 < best_r2:
            continue
        k_f, a_f, b_f, c_f, g_base = fit_result
        # c는 윈도우 후반 (0.65 ~ 0.95)
        if not (0.65 <= c_f <= 0.95):
            continue
        c_idx_in_win = int(c_f * (win - 1))
        c_idx_global = n - win + c_idx_in_win
        if c_idx_global < 0 or c_idx_global >= len(dates_list):
            continue
        c_price = float(prices[c_idx_global])
        latest_price = float(prices[-1])
        best_r2 = r2
        best = {
            'c_date': dates_list[c_idx_global],
            'c_price': int(c_price),
            'r2': round(float(r2), 3),
            'latest_price': int(latest_price),
            'ratio_pct': round((latest_price / c_price - 1) * 100, 1) if c_price > 0 else 0.0,
        }
    return best


def detect_c_aligned(d_closes, d_dates, w_closes, w_dates, m_closes, m_dates):
    """일/주/월 3프레임 c자리 검출 + 시간 일치 검사 → ★별점 반환"""
    d_c = detect_c_in_frame(d_closes, d_dates)
    w_c = detect_c_in_frame(w_closes, w_dates)
    m_c = detect_c_in_frame(m_closes, m_dates)
    
    def months_diff(d1, d2):
        return abs((pd.Timestamp(d1) - pd.Timestamp(d2)).days) / 30
    
    # ★5 - 일주월 다 일치 (각각 c 시점이 비슷)
    if d_c and w_c and m_c:
        dw = months_diff(d_c['c_date'], w_c['c_date'])
        wm = months_diff(w_c['c_date'], m_c['c_date'])
        dm = months_diff(d_c['c_date'], m_c['c_date'])
        if dw <= 6 and wm <= 12 and dm <= 12:
            return {'stars': 5, 'type': '일+주+월', 'd': d_c, 'w': w_c, 'm': m_c,
                    'time_diff_months': round(max(dw, wm, dm), 1)}
    
    # ★4 - 2개 일치
    pairs = []
    if d_c and w_c:
        diff = months_diff(d_c['c_date'], w_c['c_date'])
        if diff <= 6:
            pairs.append({'stars': 4, 'type': '일+주', 'd': d_c, 'w': w_c,
                          'score': d_c['r2'] + w_c['r2'] - diff * 0.02,
                          'time_diff_months': round(diff, 1)})
    if w_c and m_c:
        diff = months_diff(w_c['c_date'], m_c['c_date'])
        if diff <= 12:
            pairs.append({'stars': 4, 'type': '주+월', 'w': w_c, 'm': m_c,
                          'score': w_c['r2'] + m_c['r2'] - diff * 0.02,
                          'time_diff_months': round(diff, 1)})
    if d_c and m_c:
        diff = months_diff(d_c['c_date'], m_c['c_date'])
        if diff <= 12:
            pairs.append({'stars': 4, 'type': '일+월', 'd': d_c, 'm': m_c,
                          'score': d_c['r2'] + m_c['r2'] - diff * 0.02,
                          'time_diff_months': round(diff, 1)})
    if pairs:
        pairs.sort(key=lambda x: -x['score'])
        return pairs[0]
    
    # ★3 - 1개만
    singles = [(d_c, '일', 'd'), (w_c, '주', 'w'), (m_c, '월', 'm')]
    singles = [(c, tn, k) for c, tn, k in singles if c]
    if singles:
        singles.sort(key=lambda x: -x[0]['r2'])
        c, tn, k = singles[0]
        return {'stars': 3, 'type': tn, k: c}
    
    return None


def c_quartic_multiplier(c_alignment):
    """c자리 별점 → 배수. ★5=1.5배, ★4=1.3배, ★3=1.1배, 없음=1.0배"""
    if c_alignment is None: return 1.0
    stars = c_alignment.get('stars', 0)
    # 추가 가산: 현재 가격이 c가격 ±15% 이내 = 매집 자리 = 보너스
    in_c_zone = False
    for k in ['d', 'w', 'm']:
        if k in c_alignment and c_alignment[k]:
            ratio = c_alignment[k].get('ratio_pct', 999)
            if -15 <= ratio <= 15:
                in_c_zone = True
                break
    base = {5: 1.5, 4: 1.3, 3: 1.1}.get(stars, 1.0)
    if in_c_zone:
        base += 0.2  # 매집 자리 보너스
    return round(base, 2)


# ============================================================
# Step 8: 종합 분석 (시즌1 + 4차함수 c자리)
# ============================================================
def analyze(price_data, fundamentals, foreign, kis_data, kospi_3y):
    log(f"Step 8/9: v2.0 종합 분석 (5중 곱셈 + 4차함수 c자리)...")
    t0 = time.time()
    results = {}
    
    for code, info in price_data.items():
        try:
            closes = info['closes']
            vols = info['vols']
            dates = info['dates']
            if len(closes) < 60: continue
            
            # 종목 3년 수익률
            if len(closes) >= 756:
                stock_3y = (closes[-1] - closes[-756]) / closes[-756] * 100
            else:
                stock_3y = (closes[-1] - closes[0]) / closes[0] * 100
            
            # === 일/주/월봉 점수 (시즌1 그대로) ===
            d_goose, _ = goose_score_v37(closes, vols)
            d_stage = cubic_stage(closes[-120:] if len(closes) >= 120 else closes)
            
            w_closes, w_dates = resample(closes, dates, 'W')
            w_vols = resample_vol(vols, dates, 'W')
            w_goose, _ = goose_score_v37(w_closes, w_vols)
            w_stage = cubic_stage(w_closes[-80:] if len(w_closes) >= 80 else w_closes)
            
            m_closes, m_dates = resample(closes, dates, 'ME')
            m_vols = resample_vol(vols, dates, 'ME')
            m_goose, _ = goose_score_v37(m_closes, m_vols)
            m_stage = cubic_stage(m_closes)
            
            if not d_stage: d_stage = {'st': '?'}
            if not w_stage: w_stage = {'st': '?'}
            if not m_stage: m_stage = {'st': '?'}
            
            goose_total = max(d_goose, w_goose, m_goose)
            
            # === 시즌1 5중 배수 ===
            f = fundamentals.get(code, {})
            psr = f.get('psr')
            psr_m = psr_multiplier(psr)
            
            fr = foreign.get(code, {}).get('fr')
            fr_pct = fr * 100 if fr else None
            kis_60d = kis_data.get(code, [])
            fr_m = foreign_multiplier(fr_pct, kis_60d)
            
            macro_m = macro_gap_multiplier(stock_3y, kospi_3y)
            gold_m = golden_multiplier(code)
            
            # ★★★ 시즌2 추가 - 4차함수 c자리 검출 ★★★
            c_alignment = detect_c_aligned(
                closes, dates, w_closes, w_dates, m_closes, m_dates
            )
            c_m = c_quartic_multiplier(c_alignment)
            
            # === 6중 곱셈 (시즌1 5중 × c자리) ===
            jackpot_v2 = round(goose_total * psr_m * fr_m * macro_m * gold_m * c_m)
            
            # 차트 데이터 (시즌1 그대로)
            d_chart = [int(c) for c in (closes[-252:] if len(closes) >= 252 else closes)]
            d_chart_dates = dates[-252:] if len(dates) >= 252 else dates
            w_chart = [int(c) for c in (w_closes[-260:] if len(w_closes) >= 260 else w_closes)]
            w_chart_dates = w_dates[-260:] if len(w_dates) >= 260 else w_dates
            m_chart = [int(c) for c in (m_closes[-120:] if len(m_closes) >= 120 else m_closes)]
            m_chart_dates = m_dates[-120:] if len(m_dates) >= 120 else m_dates
            
            golden = GOLDEN_LIST_2001_2008.get(code)
            
            # c자리 정보 추출
            c_info = None
            if c_alignment:
                c_info = {
                    'stars': c_alignment.get('stars', 0),
                    'type': c_alignment.get('type', ''),
                    'time_diff_months': c_alignment.get('time_diff_months'),
                }
                # 일/주/월 각 c 정보
                for k, label in [('d', 'daily'), ('w', 'weekly'), ('m', 'monthly')]:
                    if k in c_alignment and c_alignment[k]:
                        c_info[label] = c_alignment[k]
            
            results[code] = {
                'n': info['name'],
                'm': info['market'],
                'mc': round(info['mcap']/1e8),
                'p': closes[-1],
                't': goose_total,
                'j': jackpot_v2,  # ★ 시즌2 잭팟 점수 (6중)
                'psr_mult': round(psr_m, 2),
                'accum_mult': round(fr_m, 2),
                'macro_mult': round(macro_m, 2),
                'golden_mult': round(gold_m, 2),
                'c_mult': c_m,  # ★ 4차함수 c자리 배수
                'c_stars': c_alignment.get('stars', 0) if c_alignment else 0,  # ★ 별점
                'c_info': c_info,  # ★ c자리 상세
                'd': {'g': d_goose, 'st': d_stage['st']},
                'w': {'g': w_goose, 'st': w_stage['st']},
                'mo': {'g': m_goose, 'st': m_stage['st']},
                'cd': d_chart, 'cdt': d_chart_dates,
                'cw': w_chart, 'cwt': w_chart_dates,
                'cm': m_chart, 'cmt': m_chart_dates,
                'c': w_chart[-50:] if len(w_chart) >= 50 else w_chart,  # 호환성
                'h': int(max(closes)),
                'l': int(min(closes)),
                'psr': round(psr, 2) if psr else None,
                'roe': round(f.get('roe', 0)*100, 1) if f.get('roe') else None,
                'opm': round(f.get('opm', 0)*100, 1) if f.get('opm') else None,
                'fr': round(fr_pct, 1) if fr_pct else None,
                'stock_3y': round(stock_3y, 1),
                'kospi_3y': round(kospi_3y, 1),
                'macro_gap': round(kospi_3y - stock_3y, 1),
                'golden_2001': golden is not None,
                'golden_multi': golden['multi'] if golden else None,
            }
        except Exception:
            continue
    log(f"  -> {len(results)}/{len(price_data)} ({time.time()-t0:.0f}초)")
    
    # 별점 통계
    five = sum(1 for r in results.values() if r['c_stars'] == 5)
    four = sum(1 for r in results.values() if r['c_stars'] == 4)
    three = sum(1 for r in results.values() if r['c_stars'] == 3)
    log(f"  ★ 4차함수 c자리: ★5={five}, ★4={four}, ★3={three}")
    
    sorted_results = sorted(results.items(), key=lambda x: -x[1]['j'])[:15]
    log("\n  📊 TOP 15 잭팟 v2 점수 (★별점 포함):")
    for code, r in sorted_results:
        grade = "🚀SSS" if r['j'] >= 200 else ("⭐SS" if r['j'] >= 150 else ("S" if r['j'] >= 100 else ("A" if r['j'] >= 70 else "B")))
        stars = '★' * r['c_stars'] if r['c_stars'] > 0 else ''
        golden_mark = " ★골든" if r['golden_2001'] else ""
        log(f"    {r['n']:14} {r['j']:>4}점 ({grade}) {stars}{golden_mark}")
    
    return results


def save_and_upload(results, kospi_3y):
    log(f"Step 9/9: 저장 + Gabia FTP 업로드...")
    output = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(results),
        'version': 'v2.0',
        'season': 2,
        'algo_name': 'SIGVIEW 시즌2 v2.0',
        'algo_desc': '5중 곱셈 + 4차함수 c자리 자동 검출',
        'kospi_3y_return': round(kospi_3y, 1),
        'summary': {
            'five_stars': sum(1 for r in results.values() if r['c_stars'] == 5),
            'four_stars': sum(1 for r in results.values() if r['c_stars'] == 4),
            'three_stars': sum(1 for r in results.values() if r['c_stars'] == 3),
            'sss_grade': sum(1 for r in results.values() if r['j'] >= 200),
            'ss_grade': sum(1 for r in results.values() if 150 <= r['j'] < 200),
            's_grade': sum(1 for r in results.values() if 100 <= r['j'] < 150),
        },
        'data': results,
    }
    data_str = json.dumps(output, ensure_ascii=False, separators=(',', ':'))
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(data_str)
    log(f"  -> {OUTPUT_FILE} ({len(data_str)/1024:.0f}KB)")
    
    if not FTP_HOST:
        log("  ⚠ FTP 없음 - 업로드 건너뜀")
        return
    try:
        with FTP(FTP_HOST, FTP_USER, FTP_PASS) as ftp:
            try:
                ftp.cwd(FTP_TARGET_DIR)
            except Exception:
                parts = FTP_TARGET_DIR.strip('/').split('/')
                ftp.cwd('/')
                for p in parts:
                    try: ftp.cwd(p)
                    except Exception: 
                        ftp.mkd(p); ftp.cwd(p)
            with open(OUTPUT_FILE, 'rb') as f:
                ftp.storbinary(f'STOR {OUTPUT_FILE}', f)
            log(f"  ✓ 업로드 완료: {FTP_TARGET_DIR}/{OUTPUT_FILE}")
    except Exception as e:
        log(f"  ✗ FTP 실패: {e}")
        sys.exit(1)


def main():
    start = time.time()
    log("=" * 60)
    log(f"SIGVIEW 잭팟 스캐너 시즌2 v2.0 - 갱신 시작")
    log("=" * 60)
    
    stocks = get_stock_list()
    kospi_3y = get_kospi_3y_return()
    prices = fetch_prices(stocks)
    fundamentals = fetch_fundamentals(prices)
    foreign = fetch_foreign(prices)
    kis_data = fetch_kis_data(prices)
    results = analyze(prices, fundamentals, foreign, kis_data, kospi_3y)
    save_and_upload(results, kospi_3y)
    
    elapsed = time.time() - start
    log("=" * 60)
    log(f"✓ 완료! {elapsed:.0f}초 ({elapsed/60:.1f}분), {len(results)}종목")
    log(f"  → https://siglab.kr/tools-jackpot-v2/ 확인")
    log("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"✗ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
