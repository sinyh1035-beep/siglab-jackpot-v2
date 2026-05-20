"""
SIGVIEW 잭팟 스캐너 시즌2 v2.0 (GitHub Pages)
==========================================
시즌1 v3.7.2 알고리즘 + 4차함수 c자리 자동 검출
출력: jackpot-v2.json (저장소 루트 - GitHub Actions가 commit/push)
URL: sinyh1035-beep.github.io/siglab-jackpot-v2/jackpot-v2.html
"""
import json, os, sys, time
from datetime import datetime
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

THRESHOLD = 500_000_000_000  # 시총 5천억
OUTPUT_FILE = 'jackpot-v2.json'

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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_stock_list():
    log("Step 1/7: 시총 5천억+ (FinanceDataReader)...")
    krx = fdr.StockListing('KRX')
    krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
    filtered = krx[krx['Marcap'] >= THRESHOLD].copy()
    filtered = filtered.sort_values('Marcap', ascending=False).reset_index(drop=True)
    log(f"  -> {len(filtered)}개")
    return filtered


def get_kospi_3y_return():
    log("Step 2/7: KOSPI 3년 수익률...")
    try:
        kospi = yf.Ticker("^KS11").history(period='3y', interval='1d').dropna()
        if len(kospi) > 250:
            ret = (kospi['Close'].iloc[-1] - kospi['Close'].iloc[0]) / kospi['Close'].iloc[0] * 100
            log(f"  -> {ret:+.1f}%")
            return ret
    except Exception as e:
        log(f"  ⚠ {e}")
    return 200


def fetch_prices(stocks):
    log(f"Step 3/7: yfinance 10년 batch ({len(stocks)}종목)...")
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
    log(f"Step 4/7: yfinance 펀더멘털 ({len(price_data)}종목)...")
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
    log(f"Step 5/7: 외인 지분율 Daum ({len(price_data)}종목)...")
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


# ============================================================
# 시즌1 알고리즘 그대로
# ============================================================
def goose_score_v37(closes, vols):
    if len(closes) < 60: return 0
    closes_arr = np.array(closes)
    score = 0
    window_len = min(252, len(closes_arr))
    window = closes_arr[-window_len:]
    cv_1y = np.std(window) / np.mean(window)
    if cv_1y < 0.12: score += 30
    elif cv_1y < 0.18: score += 25
    elif cv_1y < 0.25: score += 18
    elif cv_1y < 0.35: score += 10
    high_recent = np.max(window)
    from_high = (closes_arr[-1] - high_recent) / high_recent * 100
    if -50 <= from_high <= -25: score += 25
    elif -60 <= from_high < -50: score += 18
    elif -25 < from_high <= -15: score += 18
    elif -70 <= from_high < -60: score += 10
    elif -15 < from_high <= -5: score += 12
    else: score += 5
    if len(closes_arr) >= 60:
        ma60 = np.mean(closes_arr[-60:])
        from_ma60 = (closes_arr[-1] - ma60) / ma60 * 100
        if -5 <= from_ma60 <= 15: score += 25
        elif -15 <= from_ma60 < -5: score += 20
        elif 15 < from_ma60 <= 30: score += 15
        elif -25 <= from_ma60 < -15: score += 10
        else: score += 3
    if len(vols) >= 60:
        recent_v = np.mean(vols[-20:])
        prev_v = np.mean(vols[-60:-20])
        vol_ratio = recent_v / prev_v if prev_v > 0 else 1
        if 1.3 <= vol_ratio <= 2.5: score += 20
        elif 1.1 <= vol_ratio < 1.3: score += 12
        elif 2.5 < vol_ratio <= 4: score += 15
        elif vol_ratio > 4: score += 8
        else: score += 3
    return score


def psr_multiplier(psr):
    if psr is None: return 0.85
    if psr < 0.3: return 1.8
    if psr < 0.5: return 1.6
    if psr < 1.0: return 1.3
    if psr < 1.5: return 1.0
    if psr < 2.5: return 0.85
    return 0.6


def foreign_multiplier(fr_now):
    if fr_now is None: return 1.0
    if fr_now >= 35: return 1.3
    if fr_now >= 25: return 1.2
    if fr_now >= 15: return 1.1
    if fr_now >= 5: return 1.0
    return 0.9


def macro_gap_multiplier(stock_3y, kospi_3y):
    gap = kospi_3y - stock_3y
    if gap >= 150: return 2.0
    if gap >= 80: return 1.5
    if gap >= 30: return 1.2
    if gap >= -30: return 1.0
    if gap >= -80: return 0.8
    return 0.6


def golden_multiplier(code):
    return 1.2 if code in GOLDEN_LIST_2001_2008 else 1.0


def resample(closes, dates, freq):
    df = pd.DataFrame({'c': closes}, index=pd.to_datetime(dates))
    rs = df.resample(freq).last().dropna()
    return rs['c'].tolist(), [d.strftime('%Y-%m-%d') for d in rs.index]


def resample_vol(vols, dates, freq):
    df = pd.DataFrame({'v': vols}, index=pd.to_datetime(dates))
    return df.resample(freq).sum().dropna()['v'].tolist()


# ============================================================
# ★ 시즌2 핵심 - 4차함수 c자리 ★
# ============================================================
def quartic_fn(x, k, a, b, c):
    return k * (x - a) * (x - b) * (x - c) ** 2


def fit_quartic(prices, x_norm):
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
                best = (k_f, a_f, b_f, c_f)
        except Exception:
            continue
    return best, best_r2


def detect_c_in_frame(closes_list, dates_list, r2_min=0.55):
    if len(closes_list) < 60: return None
    prices = np.array(closes_list, dtype=float)
    n = len(prices)
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
        k_f, a_f, b_f, c_f = fit_result
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
            'ratio_pct': round((latest_price / c_price - 1) * 100, 1) if c_price > 0 else 0.0,
        }
    return best


def detect_c_aligned(d_c_in, d_d_in, w_c_in, w_d_in, m_c_in, m_d_in):
    d_c = detect_c_in_frame(d_c_in, d_d_in)
    w_c = detect_c_in_frame(w_c_in, w_d_in)
    m_c = detect_c_in_frame(m_c_in, m_d_in)
    def months_diff(d1, d2):
        return abs((pd.Timestamp(d1) - pd.Timestamp(d2)).days) / 30
    if d_c and w_c and m_c:
        dw = months_diff(d_c['c_date'], w_c['c_date'])
        wm = months_diff(w_c['c_date'], m_c['c_date'])
        dm = months_diff(d_c['c_date'], m_c['c_date'])
        if dw <= 6 and wm <= 12 and dm <= 12:
            return {'stars': 5, 'type': '일+주+월', 'd': d_c, 'w': w_c, 'm': m_c}
    pairs = []
    if d_c and w_c:
        diff = months_diff(d_c['c_date'], w_c['c_date'])
        if diff <= 6: pairs.append({'stars': 4, 'type': '일+주', 'd': d_c, 'w': w_c, 's': d_c['r2'] + w_c['r2']})
    if w_c and m_c:
        diff = months_diff(w_c['c_date'], m_c['c_date'])
        if diff <= 12: pairs.append({'stars': 4, 'type': '주+월', 'w': w_c, 'm': m_c, 's': w_c['r2'] + m_c['r2']})
    if d_c and m_c:
        diff = months_diff(d_c['c_date'], m_c['c_date'])
        if diff <= 12: pairs.append({'stars': 4, 'type': '일+월', 'd': d_c, 'm': m_c, 's': d_c['r2'] + m_c['r2']})
    if pairs:
        pairs.sort(key=lambda x: -x['s'])
        return pairs[0]
    singles = [(c, '일', 'd') for c in [d_c] if c] + [(c, '주', 'w') for c in [w_c] if c] + [(c, '월', 'm') for c in [m_c] if c]
    if singles:
        singles.sort(key=lambda x: -x[0]['r2'])
        c, tn, k = singles[0]
        return {'stars': 3, 'type': tn, k: c}
    return None


def c_quartic_multiplier(c_alignment):
    if c_alignment is None: return 1.0
    stars = c_alignment.get('stars', 0)
    in_c_zone = False
    for k in ['d', 'w', 'm']:
        if k in c_alignment and c_alignment[k]:
            ratio = c_alignment[k].get('ratio_pct', 999)
            if -15 <= ratio <= 15:
                in_c_zone = True
                break
    base = {5: 1.5, 4: 1.3, 3: 1.1}.get(stars, 1.0)
    if in_c_zone:
        base += 0.2
    return round(base, 2)


# ============================================================
# Step 6: 종합 분석 (6중 곱셈)
# ============================================================
def analyze(price_data, fundamentals, foreign, kospi_3y):
    log(f"Step 6/7: 6중 곱셈 + 4차함수 c자리 분석...")
    t0 = time.time()
    results = {}
    for code, info in price_data.items():
        try:
            closes = info['closes']
            vols = info['vols']
            dates = info['dates']
            if len(closes) < 60: continue
            
            if len(closes) >= 756:
                stock_3y = (closes[-1] - closes[-756]) / closes[-756] * 100
            else:
                stock_3y = (closes[-1] - closes[0]) / closes[0] * 100
            
            d_goose = goose_score_v37(closes, vols)
            w_closes, w_dates = resample(closes, dates, 'W')
            w_vols = resample_vol(vols, dates, 'W')
            w_goose = goose_score_v37(w_closes, w_vols)
            m_closes, m_dates = resample(closes, dates, 'ME')
            m_vols = resample_vol(vols, dates, 'ME')
            m_goose = goose_score_v37(m_closes, m_vols)
            
            goose_total = max(d_goose, w_goose, m_goose)
            
            f = fundamentals.get(code, {})
            psr = f.get('psr')
            psr_m = psr_multiplier(psr)
            fr = foreign.get(code, {}).get('fr')
            fr_pct = fr * 100 if fr else None
            fr_m = foreign_multiplier(fr_pct)
            macro_m = macro_gap_multiplier(stock_3y, kospi_3y)
            gold_m = golden_multiplier(code)
            
            c_alignment = detect_c_aligned(closes, dates, w_closes, w_dates, m_closes, m_dates)
            c_m = c_quartic_multiplier(c_alignment)
            
            jackpot_v2 = round(goose_total * psr_m * fr_m * macro_m * gold_m * c_m)
            
            d_chart = [int(c) for c in (closes[-252:] if len(closes) >= 252 else closes)]
            d_chart_dates = dates[-252:] if len(dates) >= 252 else dates
            w_chart = [int(c) for c in (w_closes[-260:] if len(w_closes) >= 260 else w_closes)]
            w_chart_dates = w_dates[-260:] if len(w_dates) >= 260 else w_dates
            m_chart = [int(c) for c in (m_closes[-120:] if len(m_closes) >= 120 else m_closes)]
            m_chart_dates = m_dates[-120:] if len(m_dates) >= 120 else m_dates
            
            golden = GOLDEN_LIST_2001_2008.get(code)
            
            c_info = None
            if c_alignment:
                c_info = {'stars': c_alignment.get('stars', 0), 'type': c_alignment.get('type', '')}
                for k, label in [('d', 'daily'), ('w', 'weekly'), ('m', 'monthly')]:
                    if k in c_alignment and c_alignment[k]:
                        c_info[label] = c_alignment[k]
            
            results[code] = {
                'n': info['name'], 'm': info['market'],
                'mc': round(info['mcap']/1e8), 'p': closes[-1],
                't': goose_total, 'j': jackpot_v2,
                'psr_mult': round(psr_m, 2), 'accum_mult': round(fr_m, 2),
                'macro_mult': round(macro_m, 2), 'golden_mult': round(gold_m, 2),
                'c_mult': c_m,
                'c_stars': c_alignment.get('stars', 0) if c_alignment else 0,
                'c_info': c_info,
                'cd': d_chart, 'cdt': d_chart_dates,
                'cw': w_chart, 'cwt': w_chart_dates,
                'cm': m_chart, 'cmt': m_chart_dates,
                'h': int(max(closes)), 'l': int(min(closes)),
                'psr': round(psr, 2) if psr else None,
                'roe': round(f.get('roe', 0)*100, 1) if f.get('roe') else None,
                'opm': round(f.get('opm', 0)*100, 1) if f.get('opm') else None,
                'fr': round(fr_pct, 1) if fr_pct else None,
                'stock_3y': round(stock_3y, 1), 'kospi_3y': round(kospi_3y, 1),
                'macro_gap': round(kospi_3y - stock_3y, 1),
                'golden_2001': golden is not None,
                'golden_multi': golden['multi'] if golden else None,
            }
        except Exception:
            continue
    log(f"  -> {len(results)}/{len(price_data)} ({time.time()-t0:.0f}초)")
    five = sum(1 for r in results.values() if r['c_stars'] == 5)
    four = sum(1 for r in results.values() if r['c_stars'] == 4)
    three = sum(1 for r in results.values() if r['c_stars'] == 3)
    log(f"  ★ c자리: ★5={five}, ★4={four}, ★3={three}")
    sorted_results = sorted(results.items(), key=lambda x: -x[1]['j'])[:15]
    log("\n  📊 TOP 15 잭팟 v2:")
    for code, r in sorted_results:
        grade = "🚀SSS" if r['j'] >= 200 else ("⭐SS" if r['j'] >= 150 else ("S" if r['j'] >= 100 else ("A" if r['j'] >= 70 else "B")))
        stars = '★' * r['c_stars'] if r['c_stars'] > 0 else ''
        gm = " ★골든" if r['golden_2001'] else ""
        log(f"    {r['n']:14} {r['j']:>4}점 ({grade}) {stars}{gm}")
    return results


def save(results, kospi_3y):
    log(f"Step 7/7: jackpot-v2.json 저장 (저장소 루트)...")
    output = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(results),
        'version': 'v2.0',
        'season': 2,
        'algo_name': 'SIGVIEW 시즌2 v2.0',
        'algo_desc': '시즌1 5중 곱셈 + 4차함수 c자리 자동 검출 = 6중',
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


def main():
    start = time.time()
    log("=" * 60)
    log("SIGVIEW 잭팟 시즌2 v2.0 (GitHub Pages)")
    log("=" * 60)
    stocks = get_stock_list()
    kospi_3y = get_kospi_3y_return()
    prices = fetch_prices(stocks)
    fundamentals = fetch_fundamentals(prices)
    foreign = fetch_foreign(prices)
    results = analyze(prices, fundamentals, foreign, kospi_3y)
    save(results, kospi_3y)
    elapsed = time.time() - start
    log("=" * 60)
    log(f"✓ 완료! {elapsed:.0f}초, {len(results)}종목")
    log("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
