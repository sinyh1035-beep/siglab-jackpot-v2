"""
foreign_data_probe.py
==========================================
외국인 데이터 받을 수 있는 길 정찰
- A: pykrx 외인 함수 (이미 실패함, 확인용)
- B: NAVER 모바일 페이지 스크래핑
- C: NAVER 모바일 API
- D: pykrx 다른 함수 (get_market_net_purchases_of_equities)
- E: KIND (전자공시 시스템) 시도
"""
import sys
import time
import json
import requests
from datetime import datetime, timedelta

TEST_CODE = '005490'  # POSCO홀딩스
TEST_NAME = 'POSCO홀딩스'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}


print('=' * 70)
print(f'외국인 데이터 정찰 - {TEST_NAME} ({TEST_CODE})')
print('=' * 70)

# ============================================================
# A: pykrx 외인 함수
# ============================================================
print('\n[A] pykrx get_exhaustion_rates_of_foreign_investment_by_date')
print('-' * 70)
try:
    from pykrx import stock
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    df = stock.get_exhaustion_rates_of_foreign_investment_by_date(start, end, TEST_CODE)
    if df is not None and len(df) > 0:
        print(f'✅ 성공! {len(df)}행')
        print(df.tail(3))
    else:
        print('❌ 빈 데이터')
except Exception as e:
    print(f'❌ 실패: {str(e)[:200]}')

# ============================================================
# B: NAVER 모바일 페이지 스크래핑
# ============================================================
print('\n[B] NAVER 모바일 페이지 frgn.naver')
print('-' * 70)
try:
    url = f'https://finance.naver.com/item/frgn.naver?code={TEST_CODE}&page=1'
    r = requests.get(url, headers=HEADERS, timeout=10)
    print(f'Status: {r.status_code}, Length: {len(r.text)}')
    if r.status_code == 200:
        r.encoding = 'euc-kr'
        # 테이블 찾기
        if '외국인' in r.text:
            print('✅ "외국인" 키워드 발견 - 페이지 정상')
            # 간단한 파싱 시도
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            tables = soup.find_all('table')
            print(f'테이블 개수: {len(tables)}')
            # 데이터 행이 있는 테이블
            for i, t in enumerate(tables):
                rows = t.find_all('tr')
                if len(rows) >= 5:
                    print(f'\nTable[{i}] - {len(rows)}행:')
                    for row in rows[:4]:
                        cells = [c.get_text(strip=True) for c in row.find_all(['th', 'td'])]
                        if any(cells):
                            print(f'  {cells[:8]}')
                    break
        else:
            print('⚠️ 페이지는 받았지만 "외국인" 키워드 없음')
            print(f'본문 첫 500자: {r.text[:500]}')
    else:
        print(f'❌ 차단 ({r.status_code})')
except Exception as e:
    print(f'❌ 실패: {str(e)[:200]}')

# ============================================================
# C: NAVER 모바일 API
# ============================================================
print('\n[C] m.stock.naver.com API')
print('-' * 70)
for endpoint in ['integration', 'price', 'trend']:
    url = f'https://m.stock.naver.com/api/stock/{TEST_CODE}/{endpoint}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        print(f'  {endpoint}: status={r.status_code}, len={len(r.text)}')
        if r.status_code == 200 and len(r.text) > 100:
            try:
                data = r.json()
                # 외국인 관련 키 찾기
                def find_foreign_keys(obj, path=''):
                    found = []
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if 'foreign' in str(k).lower() or '외국' in str(k):
                                found.append(f'{path}.{k} = {str(v)[:100]}')
                            found.extend(find_foreign_keys(v, f'{path}.{k}'))
                    elif isinstance(obj, list) and obj:
                        found.extend(find_foreign_keys(obj[0], f'{path}[0]'))
                    return found
                
                keys = find_foreign_keys(data)
                if keys:
                    print(f'    ✅ 외국인 키 발견:')
                    for k in keys[:5]:
                        print(f'    {k}')
                    break
                else:
                    print(f'    응답에는 외국인 키 없음')
            except json.JSONDecodeError:
                print(f'    JSON 아님 - 첫 200자: {r.text[:200]}')
    except Exception as e:
        print(f'  {endpoint}: 실패 {str(e)[:100]}')

# ============================================================
# D: pykrx 다른 함수들
# ============================================================
print('\n[D] pykrx 다른 외인 관련 함수')
print('-' * 70)
try:
    from pykrx import stock
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    
    # D1: 외국인/기관 매매 동향
    try:
        df = stock.get_market_trading_value_by_date(start, end, TEST_CODE)
        if df is not None and len(df) > 0:
            print(f'✅ get_market_trading_value_by_date: {len(df)}행')
            print(f'  컬럼: {list(df.columns)}')
            print(df.tail(2))
        else:
            print('❌ 빈 데이터')
    except Exception as e:
        print(f'❌ get_market_trading_value_by_date: {str(e)[:150]}')
    
    print()
    
    # D2: 매매 거래량
    try:
        df = stock.get_market_trading_volume_by_date(start, end, TEST_CODE)
        if df is not None and len(df) > 0:
            print(f'✅ get_market_trading_volume_by_date: {len(df)}행')
            print(f'  컬럼: {list(df.columns)}')
        else:
            print('❌ 빈 데이터')
    except Exception as e:
        print(f'❌ get_market_trading_volume_by_date: {str(e)[:150]}')
    
    print()
    
    # D3: 매매 거래량 by ticker (특정 날짜)
    try:
        df = stock.get_market_net_purchases_of_equities(start, end, 'KOSPI', '외국인')
        if df is not None and len(df) > 0:
            print(f'✅ get_market_net_purchases_of_equities (외국인): {len(df)}행')
            print(f'  컬럼: {list(df.columns)}')
            print(df.head(2))
        else:
            print('❌ 빈 데이터')
    except Exception as e:
        print(f'❌ get_market_net_purchases_of_equities: {str(e)[:150]}')

except Exception as e:
    print(f'❌ pykrx 임포트 실패: {e}')

# ============================================================
# E: 다른 무료 데이터 소스 (DAUM)
# ============================================================
print('\n[E] DAUM 금융')
print('-' * 70)
try:
    url = f'https://finance.daum.net/api/quotes/A{TEST_CODE}'
    headers = {**HEADERS, 'Referer': 'https://finance.daum.net/'}
    r = requests.get(url, headers=headers, timeout=10)
    print(f'  Status: {r.status_code}, Length: {len(r.text)}')
    if r.status_code == 200:
        try:
            data = r.json()
            print('  키:', list(data.keys())[:10])
            if 'foreignRatio' in data:
                print(f'  ✅ 외국인 비율: {data["foreignRatio"]}')
        except:
            print(f'  본문 200자: {r.text[:200]}')
except Exception as e:
    print(f'❌ DAUM 실패: {str(e)[:150]}')

print('\n' + '=' * 70)
print('정찰 완료')
print('=' * 70)
