import os
import tempfile
import time
import unittest
from datetime import datetime

from deva.core.store import DBStream
from deva.core.pipe import passed


class TestDBStream(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _db(self, name='t', **kwargs):
        path = os.path.join(self.tmp.name, name)
        return DBStream(name=name, filename=path, log=passed, **kwargs)

    def test_default_explicit_mode_keeps_bulk_dict_update(self):
        db = self._db('explicit_default')
        db.update({'a': 1, 'b': 2})
        self.assertEqual(db['a'], 1)
        self.assertEqual(db['b'], 2)

    def test_time_mode_rejects_dict_update(self):
        db = self._db('time_reject', key_mode='time', time_dict_policy='reject')
        with self.assertRaises(TypeError):
            db.update({'a': 1})

    def test_time_mode_append_dict_when_policy_append(self):
        db = self._db('time_append', key_mode='time', time_dict_policy='append')
        db.update({'a': 1})
        self.assertEqual(len(db), 1)
        only_value = list(db.values())[0]
        self.assertEqual(only_value, {'a': 1})

    def test_append_and_upsert_apis(self):
        db = self._db('append_upsert', key_mode='time')
        k = db.append({'x': 1})
        db.upsert('cfg', {'v': 2})
        self.assertIn('cfg', db)
        self.assertIsNotNone(float(k))

    def test_slice_skips_non_numeric_keys(self):
        db = self._db('slice_mixed', key_mode='explicit')
        now = time.time()
        k1 = str(now - 30)
        k2 = str(now - 20)
        k3 = str(now - 10)
        db.upsert('ts', 1)
        db.upsert('symbol', 'AAA')
        db.upsert(k1, 'old')
        db.upsert(k2, 'mid')
        db.upsert(k3, 'new')
        start = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now - 25))
        stop = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now - 15))
        keys = list(db[start:stop])
        self.assertEqual(keys, [k2])

    def test_maxsize_evicts_oldest_numeric_keys(self):
        db = self._db('evict_numeric', maxsize=2, key_mode='explicit')
        db.upsert('1.0', 'a')
        db.upsert('2.0', 'b')
        db.upsert('3.0', 'c')
        self.assertNotIn('1.0', db)
        self.assertIn('2.0', db)
        self.assertIn('3.0', db)

    def test_slice_boundary_exclusive(self):
        db = self._db('slice_boundary', key_mode='explicit')
        k1 = '100.0'
        k2 = '200.0'
        k3 = '300.0'
        db.upsert(k1, 'a')
        db.upsert(k2, 'b')
        db.upsert(k3, 'c')
        start = datetime.fromtimestamp(float(k1)).isoformat(sep=' ')
        stop = datetime.fromtimestamp(float(k3)).isoformat(sep=' ')
        keys = list(db[start:stop])
        # exclusive 边界 => 仅中间值
        self.assertEqual(keys, [k2])

    def test_clear_marks_index_dirty_and_removes_all(self):
        db = self._db('clear_test', key_mode='explicit')
        db.upsert('100.0', 'a')
        db.upsert('cfg', {'k': 1})
        db.clear()
        self.assertEqual(len(db), 0)
        self.assertEqual(list(db.values()), [])


if __name__ == '__main__':
    unittest.main()
