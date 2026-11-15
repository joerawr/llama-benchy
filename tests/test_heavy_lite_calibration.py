import csv,json,math,re,unittest
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'benchmarks/suites/heavy-lite-calibration-20261115'

class LiteReferenceTests(unittest.TestCase):
    def test_apache_excerpts_and_counts(self):
        for version in (1,2,3):
            folder=FIX/f'v{version}'; a=json.loads((folder/'apache.json').read_text());r=a['reference']
            source=(ROOT/a['source']).read_text().splitlines()
            lines=(folder/'apache_lite.log').read_text().splitlines()
            self.assertEqual(lines,[source[i] for i in r['source_line_indices_zero_based']])
            self.assertEqual(len(lines),r['entries'])
            levels=Counter(re.search(r'\] \[(error|notice)\]',x).group(1) for x in lines)
            self.assertEqual(levels['error'],r['error']);self.assertEqual(levels['notice'],r['notice'])
            clients=[re.search(r'\[client ([^\]]+)\]',x).group(1) for x in lines if '[client ' in x]
            self.assertEqual(len(clients),r['client_entries']);self.assertEqual(len(set(clients)),r['unique_client_ips'])
            self.assertEqual(sum(r['client_categories'].values()),len(clients))
            text='\n'.join(lines).lower()
            for evidence in ['awstats','openwebmail','cmd.exe','root.exe','createbean']:
                self.assertIn(evidence,text)
    def test_finance_drawdown_and_daily_extremes_independently(self):
        for version in (1,2,3):
            folder=FIX/f'v{version}';r=json.loads((folder/'finance.json').read_text())['reference']
            rows=list(csv.DictReader((folder/'finance_lite.csv').read_text().splitlines()))
            p=[float(x['AdjustedClose']) for x in rows];dates=[x['Date'] for x in rows]
            changes=[p[i]/p[i-1]-1 for i in range(1,len(p))]
            self.assertEqual(len(p),r['trading_days'])
            self.assertEqual(dates[1+changes.index(max(changes))],r['best_date'])
            self.assertEqual(dates[1+changes.index(min(changes))],r['worst_date'])
            dd,i,j=min((p[j]/p[i]-1,i,j) for j in range(len(p)) for i in range(j+1))
            self.assertAlmostEqual(dd,r['max_drawdown'])
            self.assertEqual((dates[i],dates[j]),(r['max_drawdown_start'],r['max_drawdown_end']))
            mean=sum(changes)/len(changes)
            sd=math.sqrt(sum((x-mean)**2 for x in changes)/(len(changes)-1))
            self.assertAlmostEqual(mean,r['daily_mean']);self.assertAlmostEqual(sd,r['daily_sample_std'])
            self.assertAlmostEqual(sd*math.sqrt(252),r['annualized_vol'])
    def test_frozen_prompt_hashes(self):
        import hashlib
        for version in (1,2,3):
            for task in ('apache','finance'):
                folder=FIX/f'v{version}';a=json.loads((folder/f'{task}.json').read_text())
                self.assertEqual(hashlib.sha256((folder/f'{task}.prompt.txt').read_bytes()).hexdigest(),a['prompt_sha256'])
                self.assertEqual(len({c['id'] for c in a['checks']}),len(a['checks']))
                self.assertEqual(hashlib.sha256((ROOT/a['source']).read_bytes()).hexdigest(),a['source_sha256'])
