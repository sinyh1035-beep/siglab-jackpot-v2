"""
NAVER 외인 API 구조 정찰 v2
- dealTrendInfos 시계열 길이 확인
- 다른 종목들도 작동하는지 확인
- 다른 NAVER API 엔드포인트 시도 (더 긴 시계열 있는지)
"""
import requests
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'https://m.stock.naver.com/',
}

# 4개 종목 테스트
codes = ['005490', '042700', '034020', '000660']
names = ['POSCO홀딩스', '한미반도체', '두산에너빌리티', 'SK하이닉스']

print('=' * 70)
print('NAVER integration API - dealTrendInfos 시계열 길이 확인')
print('=' * 70)

for code, name in zip(codes, names):
    print(f'\n## {name} ({code})')
    print('-' * 60)
    url = f'https://m.stock.naver.com/api/stock/{code}/integration'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            deals = data.get('dealTrendInfos', [])
            print(f'  dealTrendInfos 길이: {len(deals)}개')
            if deals:
                # 첫 행과 마지막 행
                print(f'  첫 행 키: {list(deals[0].keys())[:10]}')
                print(f'  첫 행: bizdate={deals[0].get("bizdate")}, '
                      f'foreignerHoldRatio={deals[0].get("foreignerHoldRatio")}, '
                      f'foreignerPureBuyQuant={deals[0].get("foreignerPureBuyQuant")}')
                if len(deals) > 1:
                    last = deals[-1]
                    print(f'  마지막 행: bizdate={last.get("bizdate")}, '
                          f'foreignerHoldRatio={last.get("foreignerHoldRatio")}, '
                          f'foreignerPureBuyQuant={last.get("foreignerPureBuyQuant")}')
        else:
            print(f'  Status: {r.status_code}')
    except Exception as e:
        print(f'  실패: {str(e)[:100]}')

# 더 긴 시계열 있는 다른 엔드포인트 시도
print('\n\n=' * 35)
print('더 긴 시계열 다른 엔드포인트 시도 (POSCO)')
print('=' * 70)
endpoints_to_try = [
    f'https://m.stock.naver.com/api/stock/005490/dealTrend',
    f'https://m.stock.naver.com/api/stock/005490/dealTrendInfos',
    f'https://m.stock.naver.com/api/stock/005490/dealTrendInfo',
    f'https://m.stock.naver.com/api/stock/005490/foreigner',
    f'https://m.stock.naver.com/api/item/foreigner/005490',
    f'https://api.stock.naver.com/stock/005490/foreigner',
    f'https://api.stock.naver.com/stock/005490/dealTrend',
    # 일별 시세 + 매매동향 형태
    f'https://m.stock.naver.com/api/stock/005490/integration?type=foreigner',
    f'https://m.stock.naver.com/api/stock/005490/finance/foreigner',
    # 더 큰 기간 파라미터 시도
    f'https://m.stock.naver.com/api/stock/005490/integration?period=1y',
    f'https://m.stock.naver.com/api/stock/005490/integration?days=365',
]

for url in endpoints_to_try:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        status_info = f'status={r.status_code}, len={len(r.text)}'
        print(f'\n  {url}')
        print(f'    {status_info}')
        if r.status_code == 200 and len(r.text) > 100:
            try:
                data = r.json()
                if isinstance(data, dict):
                    print(f'    키: {list(data.keys())[:8]}')
                    # dealTrendInfos 같은 시계열 키 찾기
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 5:
                            print(f'    📊 list "{k}" 길이={len(v)}')
                            if v and isinstance(v[0], dict):
                                first = v[0]
                                if any('foreign' in str(kk).lower() for kk in first.keys()):
                                    print(f'      ✅ 외국인 키 있음: {list(first.keys())[:6]}')
            except json.JSONDecodeError:
                print(f'    JSON 아님: {r.text[:200]}')
    except Exception as e:
        print(f'    실패: {str(e)[:100]}')

print('\n정찰 완료')
