"""Reproduction checks reject stale evidence and incomplete metric comparisons."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from public_io import sha256
from public_io import check_hashes
from public_io import compare_metrics, compare_ledger_prefix
import pandas as pd


class PublicationReproductionTests(unittest.TestCase):
    def test_short_cash_column_allows_numeric_storage_but_not_economic_changes(self):
        reference=pd.DataFrame({'cash_receivable':[0.,0.], 'nav':[100.,101.]})
        short=pd.DataFrame({'cash_receivable':[0,0], 'nav':[100.,101.]})
        self.assertEqual(compare_ledger_prefix(reference,short)[0]['column'],'cash_receivable')
        short.loc[1,'cash_receivable']=1
        with self.assertRaises(AssertionError):
            compare_ledger_prefix(reference,short)

    def test_storage_normalization_does_not_accept_boolean_cash(self):
        with self.assertRaisesRegex(ValueError,'Non-numeric'):
            compare_ledger_prefix(pd.DataFrame({'cash':[0.,0.]}),pd.DataFrame({'cash':[False,False]}))

    def test_changed_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'evidence.json'
            p.write_text('{"cost":1}',encoding='utf-8')
            bindings={'evidence.json':sha256(p)}
            check_hashes(folder,bindings)
            p.write_text('{"cost":2}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Changed evidence'):
                check_hashes(folder,bindings)

    def test_evidence_path_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'inside';root.mkdir()
            outside=Path(folder)/'outside';outside.write_text('external')
            with self.assertRaisesRegex(ValueError,'escapes'):
                check_hashes(root,{'../outside':sha256(outside)})

    def test_equal_headlines_do_not_hide_changed_cash_accounting(self):
        original=[{'id':'A','volatility':.17,'turnover':.8,'outstanding_receivables':1}]
        changed=[{**original[0],'outstanding_receivables':0}]
        with self.assertRaisesRegex(ValueError,'outstanding_receivables'):
            compare_metrics(changed,original)

    def test_comparison_tolerates_roundoff_but_requires_same_policy_identity(self):
        row={'id':'A','terminal_nav_usd':1_000_000.,'provisional':False}
        compare_metrics([{**row,'terminal_nav_usd':1_000_000.+1e-7}],[row])
        with self.assertRaisesRegex(ValueError,'id'):
            compare_metrics([{**row,'id':'B'}],[row])
