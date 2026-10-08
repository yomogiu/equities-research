"""Entirely fictitious publisher structure; no private research fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
from research import transcript_currentness as scope, source_parse, library
from research.contracts import digest
from research.freshness import assess_document, DEFAULT_POLICY
from datetime import datetime, timezone

URL = 'https://stockanalysis.com/stocks/fake/transcripts/123-q2-2026/'
BLOCK = '<div class="border-t first:border-t-0"><div>Fictional Speaker</div><span class="transcript-sentence">Fictional dialogue. This fictional earnings discussion contains complete synthetic text for verification.</span></div>'
def html(quote='100 At close:', block=BLOCK):
    return ('<html><head><title>Fictional Q2 2026</title></head><body><div class="mb-5 flex flex-row items-end">'+quote+'</div><h1>Earnings Call: Q2 2026</h1>'+block+'<footer>Fictional attribution</footer></body></html>').encode()

class CurrentnessTest(unittest.TestCase):
    def test_market_only(self):
        proof = scope.compare(html(),html('99 Pre-market:'),URL)
        self.assertFalse(proof['whole_page_bytes_equal'])
        self.assertFalse(proof['whole_page_text_equal'])
        self.assertEqual(len(proof['signature']['block_sha256']),1)

    def test_tampered_call_metadata_or_other_content(self):
        for changed in [html().replace(b'dialogue',b'altered'),html().replace(b'Speaker',b'Impostor'),
                        html().replace(b'Q2',b'Q3'),html().replace(b'attribution',b'wrong attribution'),
                        html(block=BLOCK+BLOCK),html(block=''),html(block=BLOCK.replace('</div>','',1)),
                        html(block='<span class="transcript-sentence">Unbound</span>'+BLOCK)]:
            with self.subTest(changed=changed),self.assertRaises(ValueError):scope.compare(html(),changed,URL)

    def test_app_counts_only_and_legacy_strictness(self):
        footer = ('<footer>Install The App<a href="https://apps.apple.com/us/app/stock-analysis-app/id6751272467">'
                  '<span>4.9</span><span class="text-gray-400">6.9K</span></a>'
                  '<a href="https://play.google.com/store/apps/details?id=com.stockanalysis.app">'
                  '<span>4.9</span><span class="text-gray-400">7.5K</span></a></footer>').encode()
        before = html().replace(b'<footer>Fictional attribution</footer>', footer)
        after = before.replace(b'6.9K', b'7.0K').replace(b'7.5K', b'7.7K')
        scope.compare(before, after, URL)
        with self.assertRaises(ValueError):
            scope.compare(before, after, URL, allow_app_counters=False)
        for changed in [after.replace(b'4.9',b'4.8'), after.replace(b'dialogue',b'changed'),
                        after.replace(b'Install The App',b'New business claim'),
                        after.replace(b'id6751272467',b'id0000000000'),
                        after.replace(b'7.7K',b'profit rose')]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                scope.compare(before, changed, URL)
        with self.assertRaises(ValueError):
            scope.compare(before.replace(b'<footer>',b'<section>').replace(b'</footer>',b'</section>'),
                          after.replace(b'<footer>',b'<section>').replace(b'</footer>',b'</section>'), URL)

    def fixture(self,root):
        old,new=html(),html('99 Pre-market:');text=source_parse.page(old,URL).text.encode()
        for name,body in [('old.html',old),('old.txt',text),('sources/test/objects/new.html',new)]:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        q={'document_id':digest(['issuer:fake',scope.sha(text)]),'text_sha256':scope.sha(text),'period':'FY2026-Q2',
           'kind':'transcript','completeness':'full','source_accepted':True,'language':'en','english_coverage':'full','publisher_type':'third_party','source_spans':[{'start':0,'end':9,'text':text.decode()[:9]}]}
        qid=digest(q);library.save(root/'library/qualifications'/ (qid+'.json'),q)
        cache={'sha256':scope.sha(new),'checked_at':'2026-10-05T12:00:00+00:00','final_url':URL,'content_type':'text/html','body_path':'objects/new.html'}
        library.save(root/'sources/test/http-cache.json',{URL:cache})
        doc={'source_url':URL,'raw_path':'old.html','raw_sha256':scope.sha(old),'text_path':'old.txt','text_sha256':scope.sha(text),'qualification_id':qid}
        observed={'raw_path':'sources/test/objects/new.html','observed_sha256':scope.sha(new),'checked_at':cache['checked_at']}
        ref=scope.create(root,{'issuer_id':'issuer:fake','period':'FY2026-Q2'},doc,observed,'sources/test/http-cache.json')
        doc.update(scoped_currentness=ref,source_check_status=scope.STATUS,scoped_checked_at=cache['checked_at'])
        return ref,doc

    def test_historical_replay_preserves_recorded_proof_but_not_currentness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ref,doc=self.fixture(root)
            library.save(root/'sources/later/http-cache.json',{URL:{'checked_at':'2026-10-06T12:00:00+00:00','sha256':'a'*64}})
            with self.assertRaisesRegex(ValueError,'Latest source observation'):
                scope.replay(root,ref,doc)
            scope.replay(root,ref,doc,historical=True)
            (root/'sources/test/objects/new.html').write_bytes(b'changed substantive call')
            with self.assertRaises(ValueError):
                scope.replay(root,ref,doc,historical=True)

    def test_historical_replay_still_requires_exact_fetch_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ref,doc=self.fixture(root)
            (root/'sources/test/http-cache.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'HTTP observation changed'):
                scope.replay(root,ref,doc,historical=True)

    def test_replay_and_request_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ref,doc=self.fixture(root)
            scope.replay(root,ref,doc)
            self.assertEqual(len(scope.bindings(root,doc)),4)
            fresh=assess_document(doc,DEFAULT_POLICY,datetime(2026,10,5,13,tzinfo=timezone.utc))
            self.assertEqual(fresh['basis'],'scoped_transcript_checked_at')
            self.assertEqual(fresh['status'],'fresh')
            doc['scoped_checked_at']='2026-10-05T13:00:00+00:00'
            with self.assertRaises(ValueError):scope.replay(root,ref,doc)

    def test_catalog_packet_replay_and_persistent_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ref,doc=self.fixture(root)
            did=digest(['issuer:fake',doc['text_sha256']])
            source={k:doc[k] for k in ('source_url','raw_path','raw_sha256','text_path','text_sha256')}
            source.update(retrieved_at='2026-10-01T00:00:00+00:00',checked_at=None,source_check_status='content_changed')
            cat={'issuers':{'issuer:fake':{'monitoring_eligible':True}},'documents':{did:{'document_id':did,
                 'issuer_id':'issuer:fake','text_sha256':doc['text_sha256'],'titles':['Fictional call'],'sources':[source]}}}
            cat['catalog_id']=digest(cat)
            library.save(root/'library/catalog.json',cat)
            library.save(root/'config.json',{'packet_freshness':DEFAULT_POLICY})
            scope.restore_available(root,{'issuer:fake'})
            packet=library.make_packet(root,'issuer:fake','FY2026-Q2',[doc['qualification_id']])
            actual=packet['documents'][0]
            self.assertEqual(actual['raw_sha256'],doc['raw_sha256'])
            self.assertEqual(actual['text_sha256'],doc['text_sha256'])
            self.assertIsNone(actual['checked_at'])
            self.assertEqual(actual['scoped_currentness'],ref)
            library.materialize(root,packet)
            # Collection rebuild restores ordinary changed-content variants;
            # replay reconstructs the exact same immutable scoped snapshot.
            library.save(root/'library/catalog.json',cat)
            scope.restore_available(root,{'issuer:fake'})
            self.assertEqual(library.catalog(root)['catalog_id'],packet['catalog_id'])
            # Latest contrary observation prevents an old proof clearing a hold.
            library.save(root/'sources/later/http-cache.json',{URL:{'checked_at':'2026-10-05T13:00:00+00:00','sha256':'f'*64}})
            library.save(root/'library/catalog.json',cat)
            self.assertEqual(scope.restore_available(root,{'issuer:fake'}),[])
            with self.assertRaises(ValueError):scope.apply(root,[ref])
            with self.assertRaises(ValueError):library.materialize(root,packet)
            (root/ref['path']).write_text('{}')
            with self.assertRaises(ValueError):library.materialize(root,packet)

    def test_forged_receipt_and_fetch(self):
        for target in ['receipt','raw','cache','qualification']:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();ref,doc=self.fixture(root)
                path={'receipt':root/ref['path'],'raw':root/'sources/test/objects/new.html','cache':root/'sources/test/http-cache.json',
                      'qualification':root/'library/qualifications'/(doc['qualification_id']+'.json')}[target]
                path.write_bytes(path.read_bytes()+b' ')
                if target=='qualification':
                    # JSON whitespace does not alter qualification semantic digest.
                    q=json.loads(path.read_text());q['completeness']='partial';library.save(path,q)
                with self.assertRaises(ValueError):scope.replay(root,ref,doc)

if __name__=='__main__':unittest.main()
