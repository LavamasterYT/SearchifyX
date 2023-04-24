if __name__ != '__mp_main__':
    import grequests  # gevent patching causes issues with mailtm
    import orjson
    from bs4 import BeautifulSoup
    from requests_html import HTMLSession
    from fake_headers import Headers
    import re
    import os
    import sys
    import time
    from random import choice
    from urllib.parse import urlencode
    from threading import Thread
    import sqlite3
    from jellyfish import jaro_distance as similar
    from itertools import chain
import logging

# set logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S'))
logger.propagate = False
logger.addHandler(ch)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)


headers = {
    "Sec-Ch-Ua": "\"(Not(A:Brand\";v=\"8\", \"Chromium\";v=\"99\"",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.74 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close"
}

google_domains = (
    'com', 'ad', 'ae', 'com.af', 'com.ag', 'com.ai', 'al', 'am',
    'co.ao', 'com.ar', 'as', 'at', 'com.au', 'az', 'ba', 'com.bd',
    'be', 'bf', 'bg', 'com.bh', 'bi', 'bj', 'com.bn', 'com.bo',
    'com.br', 'bs', 'bt', 'co.bw', 'by', 'com.bz', 'ca', 'cd', 'cf',
    'cg', 'ch', 'ci', 'co.ck', 'cl', 'cm', 'cn', 'com.co', 'co.cr',
    'com.cu', 'cv', 'com.cy', 'cz', 'de', 'dj', 'dk', 'dm', 'com.do',
    'dz', 'com.ec', 'ee', 'com.eg', 'es', 'com.et', 'fi', 'com.fj',
    'fm', 'fr', 'ga', 'ge', 'gg', 'com.gh', 'com.gi', 'gl', 'gm',
    'gr', 'com.gt', 'gy', 'com.hk', 'hn', 'hr', 'ht', 'hu', 'co.id',
    'ie', 'co.il', 'im', 'co.in', 'iq', 'is', 'it', 'je', 'com.jm',
    'jo', 'co.jp', 'co.ke', 'com.kh', 'ki', 'kg', 'co.kr', 'com.kw',
    'kz', 'la', 'com.lb', 'li', 'lk', 'co.ls', 'lt', 'lu', 'lv',
    'com.ly', 'co.ma', 'md', 'me', 'mg', 'mk', 'ml', 'com.mm', 'mn',
    'ms', 'com.mt', 'mu', 'mv', 'mw', 'com.mx', 'com.my', 'co.mz',
    'com.na', 'com.ng', 'com.ni', 'ne', 'nl', 'no', 'com.np', 'nr',
    'nu', 'co.nz', 'com.om', 'com.pa', 'com.pe', 'com.pg', 'com.ph',
    'com.pk', 'pl', 'pn', 'com.pr', 'ps', 'pt', 'com.py', 'com.qa',
    'ro', 'ru', 'rw', 'com.sa', 'com.sb', 'sc', 'se', 'com.sg', 'sh',
    'si', 'sk', 'com.sl', 'sn', 'so', 'sm', 'sr', 'st', 'com.sv',
    'td', 'tg', 'co.th', 'com.tj', 'tl', 'tm', 'tn', 'to', 'com.tr', 
    'tt', 'com.tw', 'co.tz', 'com.ua', 'co.ug', 'co.uk', 'com.uy',
    'co.uz', 'com.vc', 'co.ve', 'vg', 'co.vi', 'com.vn', 'vu', 'ws',
    'rs', 'co.za', 'co.zm', 'co.zw', 'cat'
)

get_text  = lambda x: BeautifulSoup(x, features='lxml').get_text().strip()
sluggify  = lambda a: ' '.join(a.lower().split())
remove_duplicates = lambda a: list(set(a))

def _make_headers():
    return {**headers, **Headers(headers=True, browser='chrome', os='windows').generate()}


_web_engines = {
    'google': {
        'domain': 'https://www.google.com/',
        'query': 'q',
        'args': {'aqs': 'chrome..69i57.888j0j1', 'sourceid': 'chrome', 'ie': 'UTF-8'},
        'limit': 2038,
        'start_sess': False,
    },
    'bing': {
        'domain': 'https://www.bing.com/',
        'query': 'q',
        'args': {'lq': '0', 'ghsh': '0', 'ghacc': '0', 'ghpl': ''},
        'limit': 990,
        'start_sess': True,
    },
    'startpage': {
        'domain': 'https://www.startpage.com/',
        'limit': 2038,
        'start_sess': True,
    },
    'duckduckgo': {
        'domain': 'https://ddg-api.herokuapp.com/',
        'query': 'query',
        'args': {'limit': '10'},
        'limit': 490,
        'start_sess': False,
    }
}

class SearchEngine:
    def __init__(self, engine_name):
        self.sess = HTMLSession()
        self.engine_name = engine_name
        self.sess.headers.update({**headers, "Sec-Fetch-Site": "same-origin", 'Referer': _web_engines[self.engine_name]['domain']})
        logger.info('Starting instance...')
        self.t = Thread(target=self._init_search)
        self.t.daemon = True
        self.t.start()
        
    def _init_search(self):
        if not _web_engines[self.engine_name]['start_sess']:
            return
        r = self.sess.get(_web_engines[self.engine_name]['domain'])
        if self.engine_name == 'startpage':
            self._startpage_data = self.get_startpage_items(r)
    
    def startpage_get_page(self, query, sites):
        resps = grequests.map([
            grequests.post('https://www.startpage.com/sp/search',
                data={
                    **self._startpage_data,
                    'query': f"{query[:_web_engines[self.engine_name]['limit']-len(site)]} site:{site}.com"
                },
                session=self.sess
            )
            for site in sites
        ])
        self.t = Thread(target=self.get_startpage_items, args=(resps[-1],))
        self.t.daemon = True
        self.t.start()
        return dict(zip(sites, resps))
        
    def find_items(self, soup, args):
        return {i: soup.find('input', {'type': 'hidden', 'name': i})['value'] for i in args}
    
    def get_startpage_items(self, r):
        soup = BeautifulSoup(r.text, 'lxml')
        return {'query': None, 'cat': 'web', **self.find_items(soup, ['lui', 'language', 'sc', 'abp'])}
    
    def get_page(self, query, sites):
        self.t.join()
        # escape query sequence
        query = re.escape(query)
        if self.engine_name == 'startpage':
            return self.startpage_get_page(query, sites)
        elif self.engine_name == 'google':
            self.sess.headers['Referer'] = _web_engines[self.engine_name]['domain'] = f'https://www.google.{choice(google_domains)}/'
        return dict(zip(
            sites,
            grequests.map([
                grequests.get(
                    (web_engine := _web_engines[self.engine_name])['domain'] + 'search?'
                    + urlencode({
                        web_engine['query']: f"{query[:_web_engines[self.engine_name]['limit']-len(site)]} site:{site}.com",
                        **web_engine['args']
                    }),
                    session=self.sess
                )
                for site in sites
            ], size=len(sites))
        ))

class SearchWeb:
    """
    search web for query
    """
    def __init__(self, query, sites, engine):
        self.query = query
        self.links = None
        self.sites = sites
        self.engine = engine
        self._regex_objs = {
            'quizlet': re.compile('https?://quizlet.com/\d+/[a-z\d\\-]+/'),
            'quizizz': re.compile('https?://quizizz.com/admin/quiz/[a-f0-9]+/[a-z\\-]+'),
        }

    def search(self):
        """
        search web for query
        """
        resps = self.engine.get_page(self.query, self.sites)
        if None in resps.values():
            raise Exception('Error searching web')
        self.links = {
            site: remove_duplicates(re.findall(self._regex_objs[site], resps[site].text))
            for site in self.sites
        }
        

class QuizizzScraper:
    def __init__(self, links, query):
        self.links = links
        self.resps = None
        self.quizizzs = []
        self.query = query
    
    def async_requests(self, links):
        reqs = [grequests.get(u, headers=_make_headers()) for u in links]
        self.resps = grequests.map(reqs, size=len(reqs))

    def parse_links(self):
        links = ['https://quizizz.com/quiz/' + u.split('/')[-2] for u in self.links]
        self.async_requests(links)
        for link, resp in zip(self.links, self.resps):
            try:
                self.quizizzs.append(self.quizizz_parser(link, resp))
            except Exception as e:
                logger.info(f'Quizizz exception: {e} {resp.url}')
        return self.quizizzs


    def quizizz_parser(self, link, resp):
        data = orjson.loads(resp.content)['data']['quiz']['info']
        return [
            {
                'question': questr,
                'answer': get_text(
                    question["structure"]["options"][
                        int(question["structure"]["answer"])
                    ]["text"]
                )
                or question["structure"]["options"][
                    int(question["structure"]["answer"])
                ]["media"][0]["url"]
                if question["type"] == "MCQ"
                else ', '.join(
                    [
                        get_text(
                            question["structure"]["options"][int(answerC)]["text"]
                        )
                        or question["structure"]["options"][int(answerC)]["media"][0]["url"]
                        for answerC in question["structure"]["answer"]
                    ]
                )
                if question["type"] == "MSQ"
                else None,
                'similarity': (similar(questr, self.query), True),
                'url': link,
            }
            for questr, question in [
                (get_text(x["structure"]["query"]["text"]), x)
                for x in data["questions"]
            ]
        ]



class QuizletScraper:
    def __init__(self, links, query):
        self.links = links
        self.resps = None
        self.quizlets = []
        self.query = query
        self._regex_obj = re.compile(r'(\\?)"termIdToTermsMap\\?":({.*?}),\\?"termSort\\?"')

    def async_requests(self, links):
        reqs = [grequests.get(u, headers=_make_headers()) for u in links]
        self.resps = grequests.map(reqs, size=len(reqs))

    def parse_links(self):
        self.async_requests(self.links)
        for link, resp in zip(self.links, self.resps):
            try:
                self.quizlets.append(self.quizlet_parser(link, resp))
            except Exception as e:
                logger.info(f'Quizlet exception: {e} {resp.url}')
        return self.quizlets


    def quizlet_parser(self, link, resp):
        terms_match = re.search(self._regex_obj, resp.text)
        if terms_match[1]:  # needs to be unescaped
            data = orjson.loads(terms_match[2].encode('utf-8').decode('unicode_escape'))
        else:
            data = orjson.loads(terms_match[2])
        return [
            {
                'question': i['word'].strip(),
                'answer': i['definition'].strip(),
                'similarity': max(
                    (similar(i[x], self.query), x == 'word')
                    # (similarity: float, is_term: bool)
                    for x in ['word', 'definition']
                ),
                'url': link,
            }
            for i in data.values()
        ]


class TimeLogger:
    def __init__(self):
        self.elapsed_total = time.time()
        self.ongoing           = {}
        self.finished          = {}
        self.finished_threads  = {}

    def start(self, item):
        self.ongoing[item] = time.time()
    
    def end(self, item=-1, _thread_flag=False):
        if type(item) == int:
            item = list(self.ongoing)[item]
        if _thread_flag:
            self.finished_threads[item] = time.time() - self.ongoing.pop(item)
        else:
            self.finished[item] = time.time() - self.ongoing.pop(item)

    def print_timers(self):
        print('ELAPSED RUN TIMES:')
        longest_len = len(max(list(self.finished), key=lambda x: len(x)))
        for k, v in self.finished.items():
            print(f'> {k.title().ljust(longest_len, " ")} \t= {round(v, 5)}')
        if self.finished_threads:
            print(
                '> Threads'.ljust(longest_len, " ") +
                ' \t= ' +
                (',\n'+longest_len*' ' + '  \t  ').join([
                    ': '.join([name.title(), str(round(time, 5))])
                    for name, time in self.finished_threads.items()
                ])
            )
        print('TOTAL ELAPSED'.ljust(longest_len, " ") + ' \t= ' + str(round(time.time() - self.elapsed_total, 5)))



class Searchify:
    def __init__(self, query, sites, engine=None):
        self.query = query
        self.sites = sites
        self.engine = engine  # optional if using offline mode
        self.timer = TimeLogger()
        self.flashcards = []
        self.unsaved_cards = []
        self.links = []
        self.site_scrapers = {
            'quizlet': QuizletScraper,
            'quizizz': QuizizzScraper,
        }
        # create database for saving flashcards
        self.con = sqlite3.connect(resource_path('flashcards.db'), check_same_thread=False)
        self.cur = self.con.cursor()
        self.cur.execute(
            "CREATE TABLE IF NOT EXISTS flashcards (question TEXT, answer TEXT, url TEXT, "
            "UNIQUE(question, answer, url) ON CONFLICT IGNORE)")
        self.con.commit()
        # add function for character distance
        self.con.create_function("similar", 2, similar)
        self.con.commit()


    def main(self):
        self.get_links()
        threads = []
        for site in self.sites:
            threads.append(Thread(
                target=self._flashcard_thread,
                args=(
                    self.site_scrapers[site],
                    self.links[site],
                    site,
                )
            ))
            threads[-1].daemon = True
            self.timer.start(site)
            threads[-1].start()

        for n, T in enumerate(threads):
            T.join()
            logger.info(f'Thread {n} finished')

        self.sort_flashcards()
        self.stop_time = time.time() - self.timer.elapsed_total
        Thread(target=self.save_flashcards).start()  # save flashcards in background
        

    def _flashcard_thread(self, site_scraper, links, site_name):
        if items := site_scraper(links, self.query).parse_links():
            self.flashcards += [max(f, key=lambda x: x['similarity'][0]) for f in items if f]
            self.unsaved_cards += items
        self.timer.end(site_name, _thread_flag=True)


    def get_links(self):
        self.timer.start('web search')
        search_bing = SearchWeb(self.query, self.sites, self.engine)
        search_bing.search()
        self.timer.end()
        self.links = search_bing.links
        self.match_db()
    
    
    def match_db(self):
        # check if links are already in database
        for site in self.links:
            for url in self.links[site][:]:
                self.cur.execute("SELECT * FROM flashcards WHERE url=?", (url,))
                if not self.cur.fetchone():
                    continue  # skip if not in database
                self.links[site].remove(url)
                # get the top similar flashcard from the database
                self.cur.execute("SELECT * FROM flashcards WHERE url=? ORDER BY similar(question, ?) DESC LIMIT 1", (url, self.query))
                i = self.cur.fetchone()
                similar_score = (similar(i[0], self.query), True)
                self.flashcards.append(dict(zip(('question', 'answer', 'url', 'similarity'), (*i, similar_score))))


    def main_offline(self, amount=20):
        # drop in replacement for main() when offline. timers not supported
        self.cur.execute(f"SELECT * FROM flashcards ORDER BY similar(question, ?) DESC LIMIT {amount}", (self.query,))
        self.flashcards = [
            {
                'question': i[0],
                'answer': i[1],
                'url': i[2],
                'similarity': f"{round(similar(i[0], self.query) * 100, 2)}%"
            }
            for i in self.cur.fetchall()
        ]

    def save_flashcards(self):
        self.cur.executemany(
            "INSERT INTO flashcards VALUES (?, ?, ?)",
            [(i['question'], i['answer'], i['url']) for i in chain.from_iterable(self.unsaved_cards)]
        )
        self.con.commit()
        del self.unsaved_cards


    def sort_flashcards(self):  # sourcery skip: for-index-replacement
        self.flashcards.sort(key=lambda x: x['similarity'], reverse=True)

        for card in range(len(self.flashcards)):
            if not self.flashcards[card]['similarity'][1]: # if cards and terms are swapped
                self.flashcards[card]['question'],  self.flashcards[card]['answer']   = (
                self.flashcards[card]['answer'],    self.flashcards[card]['question']   )

            self.flashcards[card]['similarity'] = str(round(self.flashcards[card]['similarity'][0] * 100, 2)) + '%'



if __name__ == '__main__' and len(sys.argv) > 1:
    # argument parsing
    import argparse
    parser = argparse.ArgumentParser(description='Search the web for flashcards')
    parser.add_argument('--query',  '-q', help='query to search for',  default=None)
    parser.add_argument('--output', '-o', help='output file',          default=None)
    parser.add_argument('--sites',  '-s', help='question sources quizlet,quizizz (comma seperated list)', default='quizlet,quizizz')
    parser.add_argument('--engine', '-e', help='search engine to use', default='duckduckgo', choices=_web_engines.keys())
    parser.add_argument('--chatgpt', '-gpt', help='summarize the results in ChatGPT (expiremental)', action='store_true')
    parser.add_argument('--search-db', '-db', help='search database n amount for flashcards. works offline', type=int, default=None)
    args = parser.parse_args()

    if args.output:
        f = open(args.output, 'w')
        write = f.write
    else:
        write = print

    if not args.query:
        print('No input specified')
        exit()
    
    if args.chatgpt:
        from flashcardgpt import PoeScraper
        chatgpt = PoeScraper()
        s_thread = chatgpt.async_start()

    # main program
    flashcards = [] # create flashcard list

    sites = args.sites.lower().split(',') # get list of sites
    engine_name = args.engine.lower().strip()  # get search engine

    # start search engine
    if args.search_db:
        s = Searchify(query=args.query, sites=sites)
        s.main_offline(args.search_db)
    else:
        engine = SearchEngine(engine_name)
        # run search
        s = Searchify(
            query=args.query,
            sites=sites,
            engine=engine,
        )
        s.main()

    write(orjson.dumps(s.flashcards, option=orjson.OPT_INDENT_2).decode())
    print(f'{len(s.flashcards)} flashcards found')

    not args.search_db and s.timer.print_timers()
    
    # get best answer with chatgpt
    if args.chatgpt and s.flashcards:
        print('\n--------------------\nCHATGPT SUMMARIZATION:')
        s_thread.join()
        for chunk in chatgpt.run(args.query, s.flashcards[:10]):
            print(chunk, end='')
        print('')
        # fix greenlet: WARNING: failed in call to Py_AddPendingCall; expect a memory leak.
        