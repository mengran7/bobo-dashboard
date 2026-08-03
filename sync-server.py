import json, os, urllib.request, xml.etree.ElementTree as ET
from http.server import HTTPServer, SimpleHTTPRequestHandler

DIR = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(DIR, 'state.json')
STOCK_CACHE = os.path.join(DIR, 'stock-cache.json')

STOCK_SYMBOLS = ["D05.SI","O39.SI","U11.SI","^STI","AAPL","TSLA","SPCX","NVDA","GOOGL","NFLX","GC=F","USDSGD=X"]
NEWS_CACHE = os.path.join(DIR, 'news-cache.json')
NEWS_SOURCES = [
    {"name": "新浪财经", "url": "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=10&page=1", "category": "财经", "type": "sina"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "category": "财经"},
    {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "category": "财经"},
    {"name": "36氪", "url": "https://www.36kr.com/feed", "category": "科技"},
    {"name": "HN 热门", "url": "https://hnrss.org/frontpage?format=xml", "category": "科技"},
]

FORTUNE_CACHE = os.path.join(DIR, 'fortune-cache.json')

def _mingyu_post(path, payload):
    req = urllib.request.Request(
        f'https://aov.cc/api/v1{path}',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))

class Handler(SimpleHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self._cors()
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/dashboard.html')
            self.end_headers()
            return
        if self.path == '/api/state':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if os.path.exists(STATE):
                with open(STATE, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            else:
                self.wfile.write(b'{}')
            return
        if self.path == '/api/stocks':
            try:
                if os.path.exists(STOCK_CACHE):
                    with open(STOCK_CACHE, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                else:
                    cache = {}
                now = __import__('time').time()
                if cache.get('time', 0) < now - 30 * 60:
                    prices = {}
                    for sym in STOCK_SYMBOLS:
                        try:
                            req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d", headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=8) as resp:
                                data = json.loads(resp.read().decode('utf-8'))
                            r = data['chart']['result'][0]
                            meta = r['meta']
                            quote = r['indicators']['quote'][0] if r.get('indicators') and r['indicators'].get('quote') else {}
                            closes = [c for c in quote.get('close', []) if c is not None]
                            prev = meta.get('chartPreviousClose') or (closes[-2] if len(closes) > 1 else None)
                            price = meta.get('regularMarketPrice') or (closes[-1] if closes else None)
                            change = (price - prev) if price and prev else None
                            pct = (change / prev * 100) if change and prev and prev != 0 else None
                            prices[sym] = {'price': price, 'change': change, 'changePct': pct}
                        except Exception:
                            prices[sym] = None
                    cache = {'prices': prices, 'time': now}
                    with open(STOCK_CACHE, 'w', encoding='utf-8') as f:
                        json.dump(cache, f)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(cache).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
            return
        if self.path == '/api/news':
            try:
                now = __import__('time').time()
                cache = {'articles': [], 'time': 0}
                if os.path.exists(NEWS_CACHE):
                    with open(NEWS_CACHE, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                if cache.get('time', 0) < now - 15 * 60:
                    articles = []
                    for src in NEWS_SOURCES:
                        try:
                            req = urllib.request.Request(src['url'], headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=8) as resp:
                                data = resp.read().decode('utf-8', errors='ignore')
                            if src.get('type') == 'sina':
                                js = json.loads(data)
                                items = js.get('result', {}).get('data', [])[:5]
                                for item in items:
                                    t = item.get('title', '').strip()[:120]
                                    if not t:
                                        continue
                                    articles.append({
                                        'source': src['name'],
                                        'category': src['category'],
                                        'title': t,
                                        'url': item.get('url', item.get('wapurl', '')),
                                        'time': item.get('ctime', ''),
                                        'desc': item.get('intro', item.get('summary', ''))[:150]
                                    })
                            else:
                                root = ET.fromstring(data)
                                items = root.findall('.//item')[:5]
                                for item in items:
                                    title = item.find('title')
                                    link = item.find('link')
                                    pubDate = item.find('pubDate')
                                    desc = item.find('description')
                                    t = title.text if title is not None else ""
                                    if not t:
                                        continue
                                    articles.append({
                                        'source': src['name'],
                                        'category': src['category'],
                                        'title': t.strip()[:120],
                                        'url': link.text if link is not None else "",
                                        'time': pubDate.text if pubDate is not None else "",
                                        'desc': (desc.text or "")[:150]
                                    })
                        except Exception:
                            pass
                    cache = {'articles': articles[:20], 'time': now}
                    with open(NEWS_CACHE, 'w', encoding='utf-8') as f:
                        json.dump(cache, f)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(cache).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/state':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            with open(STATE, 'w', encoding='utf-8') as f:
                f.write(body.decode('utf-8'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/state':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            with open(STATE, 'w', encoding='utf-8') as f:
                f.write(body.decode('utf-8'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            return
        if self.path == '/api/fortune':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                payload = json.loads(body.decode('utf-8')) if body else {}
                birth = payload.get('birth', {})
                today = __import__('datetime').datetime.now()
                today_str = f"{today.year}-{today.month}-{today.day}"

                bazi_resp = _mingyu_post('/bazi/calculate', {
                    'year': birth.get('year', 1990),
                    'month': birth.get('month', 1),
                    'day': birth.get('day', 1),
                    'gender': birth.get('gender', 'female'),
                    'birthHour': birth.get('hour', 12),
                    'birthMinute': birth.get('minute', 0),
                    'dateType': 'solar',
                    'useTrueSolarTime': True,
                    'birthLatitude': birth.get('latitude', 31.2),
                    'birthLongitude': birth.get('longitude', 121.5),
                    'timeZoneId': birth.get('timeZoneId', 'Asia/Shanghai')
                })

                wuxing_resp = _mingyu_post('/foundation/wuxing', {
                    'year': birth.get('year', 1990),
                    'month': birth.get('month', 1),
                    'day': birth.get('day', 1),
                    'gender': birth.get('gender', 'female'),
                    'birthHour': birth.get('hour', 12),
                    'birthMinute': birth.get('minute', 0),
                    'dateType': 'solar',
                    'birthLatitude': birth.get('latitude', 31.2),
                    'birthLongitude': birth.get('longitude', 121.5),
                    'timeZoneId': birth.get('timeZoneId', 'Asia/Shanghai')
                })

                almanac_resp = _mingyu_post('/divination/almanac', {
                    'startDate': today_str,
                    'endDate': today_str,
                    'participants': [{
                        'year': birth.get('year', 1990),
                        'month': birth.get('month', 1),
                        'day': birth.get('day', 1),
                        'gender': birth.get('gender', 'female'),
                        'birthHour': birth.get('hour', 12),
                        'birthMinute': birth.get('minute', 0),
                        'dateType': 'solar'
                    }],
                    'eventType': 'custom'
                })

                dm = bazi_resp.get('data', {}).get('dayMaster', {})
                wuxing = wuxing_resp.get('data', {})
                almanac = almanac_resp.get('data', {})

                fortune = {
                    'dayMaster': f"{dm.get('yinYang', '')}{dm.get('element', '')}日主",
                    'wuxing': wuxing.get('wuxingDistribution', []),
                    'todayAlmanac': almanac.get('almanacDays', [{}])[0] if almanac.get('almanacDays') else {},
                    'date': today_str
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(fortune, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
            return
        return super().do_POST()

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    os.chdir(DIR)
    if not os.path.exists(STATE):
        with open(STATE, 'w', encoding='utf-8') as f:
            f.write('{}')
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print('sync server running at http://0.0.0.0:' + str(port))
    server.serve_forever()
