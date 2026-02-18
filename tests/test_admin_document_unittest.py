import time
import unittest

import deva.admin as admin


class TestAdminDocumentHelpers(unittest.TestCase):
    def test_extract_doc_examples(self):
        doc = """
        demo
        >>> a = 1
        >>> a + 2
        text
        >>> print('x')
        ... print('y')
        """
        ex = admin._extract_doc_examples(doc)
        self.assertGreaterEqual(len(ex), 2)
        self.assertIn('a = 1', ex[0])
        self.assertIn("print('x')", ex[1])

    def test_mask_attr_value(self):
        self.assertEqual(admin._mask_attr_value('api_key', 'abc'), '[MASKED]')
        self.assertEqual(admin._mask_attr_value('normal', 'contains token text'), '[MASKED]')
        self.assertEqual(admin._mask_attr_value('normal', 12345), '12345')

    def test_module_whitelist(self):
        self.assertTrue(admin._document_module_allowed('core'))
        self.assertFalse(admin._document_module_allowed('non_existing_module'))

    def test_callable_smoke_eligibility(self):
        def ok():
            return 1

        def needs_arg(x):
            return x

        class C:
            pass

        eligible, _ = admin._callable_smoke_eligibility(ok)
        self.assertTrue(eligible)

        eligible, reason = admin._callable_smoke_eligibility(needs_arg)
        self.assertFalse(eligible)
        self.assertIn('需要参数', reason)

        eligible, reason = admin._callable_smoke_eligibility(C)
        self.assertFalse(eligible)
        self.assertIn('类不自动执行', reason)

    def test_scan_document_modules_uses_cache(self):
        sentinel = [{'module_name': 'x', 'objects': [], 'error': None}]
        admin._DOCUMENT_CACHE['data'] = sentinel
        admin._DOCUMENT_CACHE['ts'] = time.time()
        data = admin._scan_document_modules(use_cache=True)
        self.assertIs(data, sentinel)


if __name__ == '__main__':
    unittest.main()
