"""Fictional source/receipt fixtures only; no workers or external access."""
import copy
import hashlib
import json
import unittest

from research.source_parse import page
from research.transcript_evidence import index_publisher_transcript
from research.reviewed_transcript_index import apply_reviewed_sidecar


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def block(name, label, speech):
    return (f'<div class="border-t first:border-t-0"><div>{name}</div>'
            f'<div class="italic">{label}</div><p><span class="transcript-sentence">{speech}</span></p></div>')


def fixture(submitted=False):
    rows = [('Anonymous opening', '', 'Safe harbor.'),
            ('Pat Host', 'Director, External IR', 'We now turn to questions.'),
            ('Unknown participant', '', 'Why did fictional output rise?'),
            ('Ari Executive', 'CEO, Fictional Widgets', 'Fictional output rose by €2 from one new line.'),
            ('Operator', '', 'The call has ended.')]
    if submitted:
        rows[2] = ('Pat Host', 'Director, External IR', 'A submitted question: why did fictional output rise?')
    raw = ('<nav>Summary menu</nav>' + ''.join(block(*x) for x in rows) + '<footer>Related stories</footer>').encode()
    text = page(raw, '').text
    source = {'document_id': 'fake-document', 'issuer_id': 'fake-issuer', 'issuer_names': ['Fictional Widgets'],
              'raw_sha256': sha(raw), 'text_sha256': sha(text)}
    base = index_publisher_transcript(text, source, raw)
    turns = base['turns']
    def span(t):
        return {k: t[k] for k in ('start', 'end')} | {'text_sha256': sha(text[t['start']:t['end']])}
    ev = [{'id': 'e'+str(i), **span(t), 'quote': text[t['start']:t['end']]} for i,t in enumerate(turns)]
    speakers = [{'source_speaker': 'Pat Host', 'proposed_role': 'unknown',
                 'participant_function': 'submitted_question_moderator' if submitted else 'external_investor_relations_host',
                 'turns': [span(t) for t in turns if t['speaker']=='Pat Host'], 'evidence_ids':['e1'] }]
    if not submitted:
        speakers.append({'source_speaker':'Unknown participant','proposed_role':'unknown',
                         'participant_function':'investor_questioner','turns':[span(turns[2])], 'evidence_ids':['e2']})
    proposal = {'symbol':'FAKE','issuer_id':source['issuer_id'],'document_id':source['document_id'],
                'source':source.copy(), 'speaker_proposals':speakers,'evidence':ev,
                'qa_proposal':{'proposed_qa_section_start':turns[1]['start'], 'qa_end':turns[-1]['end'],
                               'first_substantive_question_turn_start':turns[2]['start'], 'evidence_ids':['e1','e2']},
                'dialogue_function_proposals':[], 'holds':['Fictional independent source check remains separate.']}
    if submitted:
        proposal['dialogue_function_proposals']=[dict(span(turns[2]),source_speaker='Pat Host',dialogue_function='submitted_question',evidence_id='e2')]
    review={'reviewer_session':'fake-reviewer', 'conditions':['No identity promotion.'], 'decisions':[
        {'symbol':'FAKE','document_id':source['document_id'], 'raw_sha256':source['raw_sha256'],
         'text_sha256':source['text_sha256'],'verdict':'pass_with_holds','proposal_sha256':sha(encoded(proposal)),
         'qa_decision':'pass', 'dialogue_function_decision':'pass', 'retained_holds':['Coverage review required.'],
         'speaker_decisions':[{'source_speaker':s['source_speaker'],'proposed_role':s['proposed_role'],
                               'participant_function':s['participant_function'],'verdict':'pass'} for s in speakers]}]}
    authorization={k:source[k] for k in ('document_id','issuer_id','raw_sha256','text_sha256')}
    authorization.update(proposal_sha256=sha(encoded(proposal)),review_sha256=sha(encoded(review)),
                         author_id='fake-author',reviewer_id='fake-reviewer',proposal_path='private/proposal.json',review_path='private/review.json')
    return text,raw,source,proposal,review,authorization


def apply(f):
    text,raw,source,p,r,a=f
    return apply_reviewed_sidecar(text,raw,source,encoded(p),encoded(r),a)


def rebind(f):
    p,r,a=f[3:]
    a['proposal_sha256']=sha(encoded(p))
    rows=r.get('decisions',r.get('companies'))
    rows[0]['proposal_sha256' if 'decisions' in r else 'artifact_sha256']=a['proposal_sha256']
    a['review_sha256']=sha(encoded(r))


class ReviewedTranscriptTests(unittest.TestCase):
    def test_unknown_questioner_preserved_and_original_offsets_exact(self):
        f=fixture(); before=copy.deepcopy(f); index=apply(f)
        self.assertEqual(f,before)
        question=index['exchanges'][0]
        self.assertEqual(question['questioner_occupation'],'unknown')
        self.assertNotIn('analyst',question)
        self.assertTrue(question['answer_turn_ids'])
        self.assertEqual(index['coverage']['mapping_blockers'],[])
        self.assertTrue(index['needs_review'])
        self.assertEqual(index['boundary_review'],'partially_reviewed')
        self.assertEqual(index['reviewed_sidecar']['coverage_review'],'required')
        self.assertEqual(index['reviewed_sidecar']['proposal']['sha256'],f[5]['proposal_sha256'])
        self.assertEqual(len(index['reviewed_sidecar']['retained_holds']),2)
        self.assertLess(index['turns'][0]['start'],index['sections'][1]['start'])
        for t in index['turns']:
            self.assertEqual(t['text_sha256'],sha(f[0][t['start']:t['end']]))
        self.assertNotIn('Summary menu',f[0][index['call_span']['start']:index['call_span']['end']])
        self.assertEqual(index['turns'][0]['role'],'unknown')

    def test_submitted_question_does_not_promote_ir_host(self):
        index=apply(fixture(True));e=index['exchanges'][0]
        self.assertEqual(e['questioner'],'Pat Host');self.assertEqual(e['questioner_occupation'],'unknown')
        self.assertTrue(e['answer_turn_ids'])
        self.assertEqual(index['coverage']['mapping_blockers'],[])

    def test_unknown_answer_turn_remains_unresolved(self):
        f=fixture();f[2]['issuer_names']=[]
        index=apply(f)
        self.assertIn('unresolved_qa_dialogue',index['coverage']['mapping_blockers'])
        self.assertIn('no_answered_exchange',index['coverage']['mapping_blockers'])
        self.assertEqual(index['turns'][3]['role'],'unknown')

    def test_reviewed_response_candidate_preserves_unknown_occupation(self):
        f=fixture();f[2]['issuer_names']=[];e=f[3]['evidence'][3]
        f[3]['dialogue_function_proposals']=[dict(start=e['start'],end=e['end'],source_speaker='Ari Executive',dialogue_function='issuer_response_candidate',evidence_id='e3')]
        rebind(f);index=apply(f);turn=index['turns'][3]
        self.assertEqual(turn['role'],'unknown')
        self.assertEqual(turn['indexed_dialogue_function'],'issuer_response_candidate')
        self.assertIn(turn['id'],index['exchanges'][0]['answer_turn_ids'])
        self.assertTrue(index['needs_review'])
        self.assertEqual(index['reviewed_sidecar']['coverage_review'],'required')

    def test_reviewed_handoff_is_not_an_answer(self):
        f=fixture();e=f[3]['evidence'][3]
        f[3]['dialogue_function_proposals']=[dict(start=e['start'],end=e['end'],source_speaker='Ari Executive',dialogue_function='issuer_handoff',evidence_id='e3')]
        rebind(f);index=apply(f);turn=index['turns'][3]
        self.assertEqual(turn['role'],'management')
        self.assertNotIn(turn['id'],index['exchanges'][0]['answer_turn_ids'])
        self.assertIn('no_answered_exchange',index['coverage']['mapping_blockers'])

    def test_explicit_answer_requires_issuer_attribution(self):
        f=fixture();f[2]['issuer_names']=[];e=f[3]['evidence'][3]
        f[3]['dialogue_function_proposals']=[dict(start=e['start'],end=e['end'],source_speaker='Ari Executive',dialogue_function='issuer_answer',evidence_id='e3')]
        rebind(f)
        with self.assertRaisesRegex(ValueError,'issuer attribution'):apply(f)

    def test_raw_text_authorization_and_artifact_tampering_rejected(self):
        for part,key in [(2,'raw_sha256'),(2,'text_sha256'),(5,'document_id'),(5,'issuer_id'),(5,'proposal_sha256'),(5,'review_sha256')]:
            with self.subTest(part=part,key=key):
                f=fixture();f[part][key]='wrong'
                with self.assertRaises(ValueError):apply(f)

    def test_stale_turn_hash_and_evidence_quote_rejected_even_if_review_bound(self):
        for mode in ('turn','quote','label','offset'):
            with self.subTest(mode=mode):
                f=fixture()
                if mode=='turn':f[3]['speaker_proposals'][1]['turns'][0]['text_sha256']='wrong'
                if mode=='quote':f[3]['evidence'][0]['quote']='Invented.'
                if mode=='label':f[3]['speaker_proposals'][1]['source_speaker']='Invented analyst'
                if mode=='offset':f[3]['speaker_proposals'][1]['turns'][0]['start']+=1
                rebind(f)
                with self.assertRaises(ValueError):apply(f)

    def test_independent_approved_exact_receipt_required(self):
        for mode in ('self','failed','stale','duplicate','speaker','qa'):
            with self.subTest(mode=mode):
                f=fixture()
                if mode=='self':f[5]['author_id']='fake-reviewer'
                if mode=='failed':f[4]['decisions'][0]['verdict']='changes_required'
                if mode=='duplicate':f[4]['decisions'].append(copy.deepcopy(f[4]['decisions'][0]))
                if mode=='speaker':f[4]['decisions'][0]['speaker_decisions'][1]['proposed_role']='analyst'
                if mode=='qa':f[4]['decisions'][0]['qa_decision']='changes_required'
                rebind(f)
                if mode=='stale':f[4]['decisions'][0]['proposal_sha256']='wrong';f[5]['review_sha256']=sha(encoded(f[4]))
                with self.assertRaises(ValueError):apply(f)

    def test_native_missing_empty_or_surplus_speaker_decisions_rejected(self):
        for mode in ('missing','empty','surplus'):
            f=fixture();row=f[4]['decisions'][0]
            if mode=='missing':del row['speaker_decisions']
            elif mode=='empty':row['speaker_decisions']=[]
            else:row['speaker_decisions'].append({'source_speaker':'Invented','proposed_role':'analyst','verdict':'pass'})
            rebind(f)
            with self.assertRaisesRegex(ValueError,'Exact speaker review'):apply(f)

    def test_duplicate_turn_and_function_rejected(self):
        for mode in ('turn','function'):
            f=fixture(True)
            if mode=='turn':f[3]['speaker_proposals'][0]['turns'].append(copy.deepcopy(f[3]['speaker_proposals'][0]['turns'][0]))
            else:f[3]['dialogue_function_proposals']*=2
            rebind(f)
            with self.assertRaises(ValueError):apply(f)

    def test_whole_turn_qa_bounds_required(self):
        f=fixture();f[3]['qa_proposal']['proposed_qa_section_start']+=1;rebind(f)
        with self.assertRaisesRegex(ValueError,'whole turns'):apply(f)

    def test_a_revised_format_and_function_do_not_promote_occupation(self):
        f=fixture();p=f[3];question=p['speaker_proposals'].pop()
        p.update(author_session='fake-author',raw_sha256=f[2]['raw_sha256'],text_sha256=f[2]['text_sha256'])
        del p['source']
        p['dialogue_function_proposals']=[dict(source_speaker=question['source_speaker'],participant_function='investor_questioner',occupational_role='unknown',turns=question['turns'],evidence=[p['evidence'][2]])]
        q=p['qa_proposal'];p['qa_proposal']={'transition_start':q['proposed_qa_section_start'],'first_substantive_question_turn_start':q['first_substantive_question_turn_start'],'evidence':[p['evidence'][1],p['evidence'][2]]}
        f[4].clear();f[4].update(reviewer='fake-reviewer',author='fake-author',status='pass_sidecar_only',companies=[{'symbol':'FAKE','status':'pass','artifact_sha256':''}]);rebind(f)
        index=apply(f)
        self.assertEqual(index['exchanges'][0]['questioner_occupation'],'unknown')
        self.assertEqual(index['coverage']['mapping_blockers'],[])
        p['dialogue_function_proposals'][0]['occupational_role']='analyst';rebind(f)
        with self.assertRaisesRegex(ValueError,'promote occupation'):apply(f)

    def test_original_a_shape_derives_missing_turn_hash_without_changing_offsets(self):
        f=fixture();p=f[3]
        p.update(author_session='fake-author',raw_sha256=f[2]['raw_sha256'],text_sha256=f[2]['text_sha256'])
        del p['source']
        for item in p['speaker_proposals']:
            item['evidence']=[p['evidence'][1 if item['source_speaker']=='Pat Host' else 2]]
            del item['evidence_ids']
            for t in item['turns']:
                del t['text_sha256']
                t['speaker']=item['source_speaker']
        rebind(f);result=apply(f)
        self.assertEqual(result['coverage']['mapping_blockers'],[])
        self.assertTrue(all(t['text_sha256'] for t in result['turns']))

    def test_submitted_topic_answer_is_kept_before_individual_question(self):
        f=fixture(True);p=f[3];first=p['evidence'][2]
        p['dialogue_function_proposals'][0]['dialogue_function']='submitted_question_topic_transition'
        answer=p['evidence'][3]
        p['dialogue_function_proposals'].append(dict(start=answer['start'],end=answer['end'],source_speaker='Ari Executive',dialogue_function='answer_to_submitted_topic',evidence_id='e3'))
        rebind(f);i=apply(f)
        self.assertEqual(i['exchanges'][0]['question_kind'],'submitted_topic')
        self.assertTrue(i['exchanges'][0]['answer_turn_ids'])
        self.assertEqual(i['turns'][3]['dialogue_function'],'answer_to_submitted_topic')

    def test_missing_supporting_evidence_rejected(self):
        f=fixture();f[3]['speaker_proposals'][0]['evidence_ids']=[];rebind(f)
        with self.assertRaisesRegex(ValueError,'Source evidence'):apply(f)

    def test_issuer_ir_can_read_question_without_becoming_analyst(self):
        f=fixture(True);p=f[3]
        p['speaker_proposals'][0]['proposed_role']='management'
        p['speaker_proposals'][0]['participant_function']='issuer_representative'
        f[4]['decisions'][0]['speaker_decisions'][0].update(proposed_role='management',participant_function='issuer_representative')
        rebind(f);i=apply(f)
        self.assertEqual(i['exchanges'][0]['questioner_occupation'],'management')
        self.assertEqual(i['turns'][2]['dialogue_function'],'submitted_question')


if __name__=='__main__':unittest.main()
