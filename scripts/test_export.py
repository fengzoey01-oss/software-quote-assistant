import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from quote import read
from export_xlsx import export


class ExportTests(unittest.TestCase):
    def test_customer_contains_no_internal_fields_or_formula(self):
        doc = read(Path(__file__).resolve().parents[1]/'examples/demo.json')
        doc['project']['internal_note'] = 'INTERNAL_ONLY_MARKER'
        doc['items'][0]['estimate_basis'] = 'INTERNAL_ONLY_MARKER'
        doc['items'][0]['description'] = '=HYPERLINK("https://example.invalid","example")'
        with tempfile.TemporaryDirectory() as tmp:
            public, internal = export(doc, tmp)
            with ZipFile(public) as z:
                texts = [z.read(n).decode() for n in z.namelist()]
                joined = '\n'.join(texts)
                for value in ['INTERNAL_ONLY_MARKER','factor_a','factor_b','source_refs','<f>','隐藏成本']:
                    self.assertNotIn(value, joined)
                self.assertIn('13200.00',joined)
                for text in texts:
                    ET.fromstring(text)
            with ZipFile(internal) as z:
                self.assertIn('factor_a', z.read('xl/worksheets/sheet2.xml').decode())

    def test_missing_price_remains_blank(self):
        doc = read(Path(__file__).resolve().parents[1]/'examples/demo.json')
        doc['items'][3]['selected'] = True
        with tempfile.TemporaryDirectory() as tmp:
            public, _ = export(doc, tmp)
            with ZipFile(public) as z:
                root = ET.fromstring(z.read('xl/worksheets/sheet3.xml'))
                ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                self.assertEqual(root.find(".//m:c[@r='C2']/m:is/m:t", ns).text, '13200.00')
                for address in ['D2', 'E2', 'F2']:
                    self.assertIsNone(root.find(f".//m:c[@r='{address}']/m:is/m:t", ns).text)
                self.assertIn('待补充',z.read('xl/worksheets/sheet1.xml').decode())


if __name__ == '__main__':
    unittest.main()
