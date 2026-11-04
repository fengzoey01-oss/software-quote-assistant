import copy
import json
import unittest
from pathlib import Path
from quote import calculate, customer_view, digest, diff, InputError, read

PKG=Path(__file__).resolve().parents[1]


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.doc=read(PKG/'examples/demo.json')

    def calc(self):
        return calculate(self.doc)

    def codes(self):
        return {x['code'] for x in self.calc()['issues'] if x['blocking']}

    def test_service_price(self):
        self.assertEqual(self.calc()['items'][0]['amount'],'5400.00')

    def test_cost_plus(self):
        self.assertEqual(self.calc()['items'][1]['amount'],'7800.00')

    def test_inclusive_tax(self):
        t=self.calc()['totals'][0]
        self.assertEqual((t['gross'],t['net'],t['tax']),('13200.00','12452.83','747.17'))

    def test_exclusive_tax(self):
        self.doc['project']['price_basis']='exclusive'
        self.assertEqual(self.calc()['totals'][0]['gross'],'13992.00')

    def test_unknown_exclusive_tax(self):
        self.doc['project'].update(price_basis='exclusive',tax_rate=None)
        self.assertIn('TAX_MISSING',self.codes())
        self.assertIsNone(self.calc()['totals'][0]['gross'])

    def test_no_double_markup(self):
        self.doc['items'][0]['pricing']['markup']='0.2'
        self.assertIn('PRICE_INPUT',self.codes())

    def test_unselected_missing_price(self):
        self.assertEqual(self.calc()['status'],'可审阅草稿')

    def test_selected_missing_price(self):
        self.doc['items'][3]['selected']=True
        self.assertIsNone(self.calc()['totals'][0]['gross'])

    def test_zero_is_not_blank(self):
        self.doc['items'][0]['pricing']['rate']='0'
        self.doc['items'][0]['zero_reason']='用户明确免收此项'
        self.assertEqual(self.calc()['items'][0]['amount'],'0.00')
        self.assertEqual(self.calc()['totals'][0]['gross'],'7800.00')

    def test_zero_without_reason(self):
        self.doc['items'][0]['pricing']['rate']='0'
        self.assertIn('ZERO_REASON',self.codes())

    def test_included_missing_owner(self):
        self.doc['items'][2]['included_in']=['MISSING']
        self.assertIn('OWNER_UNKNOWN',self.codes())

    def test_included_cycle(self):
        self.doc['items'][0].update(method='included',pricing={},included_in=['D3'])
        self.assertIn('INCLUSION_CYCLE',self.codes())

    def test_owner_not_selected(self):
        self.doc['items'][0].update(scope='optional',selected=False)
        self.assertIn('OWNER_NOT_SELECTED',self.codes())

    def test_exclusive(self):
        self.doc['relations']=[dict(id='E',kind='exclusive',items=['D1','D2'])]
        self.assertIn('EXCLUSIVE',self.codes())

    def test_dependency(self):
        self.doc['relations']=[dict(id='R',kind='requires_any',items=['D1'],any_of=[{'item':'D4'},{'condition':'supplied'}])]
        self.assertIn('DEPENDENCY',self.codes())
        self.doc['conditions']['supplied']=True
        self.assertNotIn('DEPENDENCY',self.codes())

    def test_overlap_confirmed(self):
        self.doc['relations']=[dict(id='O',kind='overlap_credit',items=['D1','D2'],condition='same',amount='1000')]
        self.doc['conditions']['same']=True
        self.assertEqual(self.calc()['totals'][0]['gross'],'12200.00')
        self.doc['conditions']['same']=False
        self.assertEqual(self.calc()['totals'][0]['gross'],'13200.00')

    def test_overlap_unknown(self):
        self.doc['relations']=[dict(id='O',kind='overlap_credit',items=['D1','D2'],condition='same',amount='1000')]
        self.assertIn('OVERLAP_UNCONFIRMED',self.codes())

    def test_credit_excess(self):
        self.doc['relations']=[dict(id='O',kind='overlap_credit',items=['D1','D2'],condition='same',amount='6000')]
        self.doc['conditions']['same']=True
        self.assertIn('CREDIT_EXCESS',self.codes())

    def test_override_zero(self):
        self.doc['overrides']=[dict(bucket='软件',frequency='once',amount='0',reason='测试免费执行价')]
        self.assertEqual(self.calc()['totals'][0]['gross'],'0.00')

    def test_override_missing_reason(self):
        self.doc['overrides']=[dict(bucket='软件',frequency='once',amount='10000')]
        self.assertIn('OVERRIDE_REASON',self.codes())

    def test_rounding(self):
        self.doc['items'][0]['pricing'].update(days='1',rate='2.345')
        self.assertEqual(self.calc()['items'][0]['amount'],'2.35')

    def test_review_invalidated(self):
        self.doc['reviews']=[dict(stage='scope',input_hash=digest(self.doc),reviewer='测试负责人',date='2026-10-22')]
        self.assertEqual(self.calc()['reviews']['scope'],'有效')
        self.doc['items'][0]['pricing']['days']='4'
        self.assertEqual(self.calc()['reviews']['scope'],'待复核')

    def test_period_separation(self):
        self.doc['items'][1].update(bucket='服务器',frequency='year')
        self.assertEqual(len(self.calc()['totals']),2)
        self.assertNotIn('grand_total',self.calc())

    def test_duplicate_id(self):
        self.doc['items'][1]['id']='D1'
        with self.assertRaises(InputError): self.calc()

    def test_invalid_numeric(self):
        for v in ('NaN','Infinity','-1',True):
            self.doc['items'][0]['pricing']['rate']=v
            self.assertIn('PRICE_INPUT',self.codes())

    def test_customer_whitelist(self):
        r=self.calc(); r['items'][0]['secret_cost']='SECRET'; r['project']['internal_note']='SECRET'
        text=json.dumps(customer_view(r),ensure_ascii=False)
        for needle in ('SECRET','factor_a','factor_b','source_refs','rate_kind','"cost"'):
            self.assertNotIn(needle,text)

    def test_requirement_coverage(self):
        self.doc['requirements']=[dict(id='NEED',item_ids=[],required=True)]
        self.assertIn('REQUIREMENT_UNMAPPED',self.codes())

    def test_diff(self):
        before=copy.deepcopy(self.doc); self.doc['items'][0]['pricing']['days']='4'
        self.assertTrue(diff(before,self.doc)['review_invalidated'])




    def test_blocking_question(self):
        self.doc['open_questions']=[dict(question='接口数量待定',blocks_price=True)]
        self.assertEqual(self.calc()['status'],'待补充')
        self.assertIsNone(self.calc()['totals'][0]['gross'])

    def test_module_price(self):
        self.doc['items'][0].update(method='module_price',pricing=dict(quantity='2',unit_price='3000',rate_kind='module_price'))
        self.assertEqual(self.calc()['items'][0]['amount'],'6000.00')

    def test_included_cannot_charge_again(self):
        self.doc['items'][0]['included_in']=['D2']
        with self.assertRaises(InputError): self.calc()

    def test_source_id_unique(self):
        self.doc['sources'].append(copy.deepcopy(self.doc['sources'][0]))
        with self.assertRaises(InputError): self.calc()


if __name__=='__main__':
    unittest.main(verbosity=2)
