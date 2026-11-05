"""2.8.0: IFS auditXpress (.ifs) - okuma, bire bir geri yazma, puan kurallari, ic alanlar, sekme ve AI."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-ifs-')
os.environ['LOCALAPPDATA'] = TMP
FIXTURE = pathlib.Path(__file__).resolve().parent / 'data' / 'ifs_food8_example.ifs'

import agfo_ifs as I  # noqa: E402


def copy_fixture():
    d = tempfile.mkdtemp(dir=TMP)
    p = os.path.join(d, 'rapor.ifs')
    shutil.copy(FIXTURE, p)
    return p


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.path = copy_fixture()
        self.r = I.IfsReport(self.path)

    def test_round_trip_is_byte_identical(self):
        self.assertEqual(self.r.dumps(), FIXTURE.read_text(encoding='utf-8'))
        self.assertFalse(self.r.changed())
        self.r.save(self.path)
        self.assertEqual(pathlib.Path(self.path).read_bytes(), FIXTURE.read_bytes())

    def test_structure(self):
        self.assertEqual(self.r.module_id, 'food_8')
        self.assertEqual(self.r.standard_name(), 'IFS Food 8')
        self.assertEqual(len(self.r.requirements()), 232)
        cnt = self.r.counts()
        self.assertEqual((cnt['A'], cnt['B'], cnt['C'], cnt['D'], cnt['NA']), (70, 3, 2, 1, 11))
        groups = {g: self.r.question_keys(g) for g, _t, _k in I.GROUPS}
        self.assertEqual(sum(len(v) for v in groups.values()), len(self.r.questions))   # her alan bir bolumde
        self.assertIn('companyName', groups['company'])
        self.assertIn('auditAnnouncedOption', groups['assessment'])

    def test_score_sets_object_correction_and_d_count(self):
        u = next(x.uuid for x in self.r.requirements() if x.score_id == 'A')
        self.r.set_score(u, 'D')
        req = self.r.requirement(u)
        self.assertEqual(req.data['score'], {'value': -20, 'scoreId': 'D', 'label': 'D'})
        self.assertTrue(req.data['isCorrectionRequired'])
        self.assertIn(u, self.r.checklist['correctiveActions'])
        self.assertEqual(self.r.checklist['dCount'], 2)
        self.r.set_score(u, 'A')
        self.assertEqual(req.data['score']['value'], 20)
        self.assertFalse(req.data['isCorrectionRequired'])
        self.assertNotIn(u, self.r.checklist['correctiveActions'])
        self.assertEqual(self.r.checklist['dCount'], 1)
        self.r.set_score(u, '')
        self.assertEqual(req.data['score'], {'value': '', 'scoreId': '', 'label': ''})
        with self.assertRaises(I.IfsError):
            self.r.set_score(u, 'X')

    def test_written_corrective_action_is_kept(self):
        u = next(x.uuid for x in self.r.requirements() if x.score_id == 'D')
        self.r.checklist['correctiveActions'][u]['fields'] = {'correction': {'answer': 'done'}}
        self.r.set_score(u, 'A')
        self.assertIn(u, self.r.checklist['correctiveActions'])         # yazilmis duzeltici faaliyet silinmez

    def test_inner_field_kinds_and_new_rows(self):
        req = next(x for x in self.r.requirements() if 'foodContactPackagingList' in x.fields)
        items = req.fields['foodContactPackagingList']['answer']
        self.assertEqual(I.field_kind('foodContactPackagingList', items), 'group')
        new = I.new_group_item(I.group_template('foodContactPackagingList', items))
        self.assertEqual(list(new['rootQuestions']), ['foodContactPackagingListText'])
        self.assertNotEqual(new['id'], items[0]['id'])
        self.assertEqual(I.field_kind('customerAgreementTypeRelation', ['customerAgreementTypeRecipe']), 'codes')
        self.assertEqual(I.field_kind('widgetCcpPickerByProductScope', [{'type': 'ccp', 'uuid': 'x'}]), 'refs')
        self.assertEqual(I.field_kind('seasonalProduction', 'yes'), 'yesno')
        self.assertEqual(I.field_kind('ccpImplementedList', []), 'group')            # bos liste: bilinen yapi
        self.assertIsNotNone(I.group_template('ccpImplementedList', []))
        self.assertEqual(I.field_kind('unknownWidgetThing', []), 'other')            # bilinmeyen: dokunulmaz

    def test_hash_keep_or_clear(self):
        u = self.r.requirements()[0].uuid
        self.r.set_text(u, 'note', 'Test')
        keep = json.loads(self.r.dumps('keep'))
        clear = json.loads(self.r.dumps('clear'))
        self.assertEqual(keep['hash'], '0' * 40)
        self.assertEqual((clear['hash'], clear['hashVersion2'], clear['hashVersion3']), ('', '', ''))
        self.assertEqual(json.loads(self.r.dumps())['hash'], '0' * 40)      # bosaltma yalniz yazilan dosyada

    def test_save_backs_up_previous_file(self):
        bdir = os.path.join(TMP, 'backups-%d' % id(self))
        self.r.set_text(self.r.requirements()[0].uuid, 'note', 'Yeni not')
        self.r.save(self.path, backup_dir=bdir)
        self.assertEqual(len(os.listdir(bdir)), 1)
        again = I.IfsReport(self.path)
        self.assertEqual(again.requirements()[0].answers['note'], 'Yeni not')

    def test_bad_files(self):
        for raw in ('not json', '{"a": 1}', '{"data": {"modules": {}}}'):
            with self.assertRaises(I.IfsError):
                I.IfsReport(raw=raw)

    def test_dictionary_gives_numbers(self):
        d = I.user_dictionary_dir()
        os.makedirs(d, exist_ok=True)
        u = self.r.requirements()[5].uuid
        pathlib.Path(d, 'food_8-requirements.json').write_text(json.dumps([{'uuid': u, 'no': '1.2.3', 'text': 'Policy'}]),
                                                                encoding='utf-8')
        try:
            r2 = I.IfsReport(self.path)
            self.assertEqual(r2.requirement(u).title(), '1.2.3 Policy')
        finally:
            os.remove(os.path.join(d, 'food_8-requirements.json'))

    def test_labels(self):
        self.assertEqual(I.label_of('foodContactPackagingList'), 'Food Contact Packaging List')
        self.assertTrue(I.label_of('numberOfEmployeesDescription_en').endswith('(EN)'))
        self.assertEqual(I.pair_of('x_en'), 'x')


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class IfsGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.geometry('1300x850')
        self.app.update()
        self.calls = []

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=300):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def fake(self, text='The company has defined the packaging specifications.'):
        def run(backends, fn, *args):
            self.calls.append((fn, args))
            return {'text': text, 'via': 'Test', 'model': 'test'}
        return mock.patch.object(self.m.ai, 'run_with_fallback', run), mock.patch.object(self.app, 'backends', return_value=[])

    def test_open_edit_save(self):
        path = copy_fixture()
        v = self.app.open_path(path)
        self.assertEqual(type(v).__name__, 'IfsReportView')
        self.assertIs(self.app.open_path(path), v)                      # ikinci kez acilmaz
        self.assertIs(self.app.cur_ifs(), v)
        self.pump(n=10)
        self.assertNotIn(str(self.app.side_panel), self.app.paned.panes())   # AI paneli yer kaplamaz
        self.assertEqual(len(v.tree.get_children()), 232)
        # suzme
        v.filter_var.set('D')
        v._fill_tree()
        self.assertEqual(len(v.tree.get_children()), 1)
        v.filter_var.set('Tümü')
        v._fill_tree()
        # madde: puan + aciklama + ic alan satiri
        req = next(x for x in v.report.requirements() if 'foodContactPackagingList' in x.fields)
        v.select_requirement(req.uuid)
        self.pump(n=10)
        v.set_score(req.uuid, 'B')
        self.assertTrue(v.dirty)
        self.assertEqual(v.tree.set(req.uuid, 'score'), 'B')
        box = v.expl_boxes['englishExplanationText']
        box.insert('1.0', 'Packaging specifications are defined.')
        self.pump(n=5)
        self.assertEqual(req.answers['englishExplanationText'], 'Packaging specifications are defined.')
        items = req.fields['foodContactPackagingList']['answer']
        n = len(items)
        items.append(I.new_group_item(I.group_template('foodContactPackagingList', items)))
        # kaydet: dosya guncel, yedek alindi, isaret kalkti
        self.assertTrue(self.app.save())
        self.assertFalse(v.dirty)
        again = I.IfsReport(path)
        r2 = again.requirement(req.uuid)
        self.assertEqual(r2.score_id, 'B')
        self.assertTrue(r2.data['isCorrectionRequired'])
        self.assertEqual(len(r2.fields['foodContactPackagingList']['answer']), n + 1)
        self.assertEqual(json.loads(pathlib.Path(path).read_text(encoding='utf-8'))['hash'], '0' * 40)
        # rapor alanlari sayfalari cizilir
        for g, _t, _k in I.GROUPS:
            v.show(g)
            self.pump(n=3)
        v.show('team')
        v.show('overview')
        self.pump(n=3)
        # kapat
        self.assertTrue(self.app.close_tab_frame(v) is None or v not in self.app.ifs_views)

    def test_ai_explanation_and_en_fields(self):
        path = copy_fixture()
        v = self.app.open_path(path)
        req = next(x for x in v.report.requirements() if x.score_id == 'D')
        req.answers['explanationText'] = 'Kritik limitler ürün bazında tanımlanmamış.'
        v.select_requirement(req.uuid)
        p1, p2 = self.fake('Deviation: the critical limits are not defined for each product.')
        with p1, p2:
            v.ai_explanation(req.uuid)
            self.assertTrue(self.pump(lambda: not self.app.jobs))
        fn, args = self.calls[-1]
        self.assertEqual(fn, 'transform')
        self.assertIn('Kritik limitler', args[0])
        self.assertIn('scored D', args[1]['extra'])
        self.assertEqual(req.answers['englishExplanationText'], 'Deviation: the critical limits are not defined for each product.')
        self.assertIn('Deviation', v.expl_boxes['englishExplanationText'].get('1.0', 'end'))
        # bos EN alanlari: yerel dildeki eslerinden
        q = v.report.questions
        key = next(k for k in v.report.question_keys('site') if I.is_en(k) and I.pair_of(k) in q)
        q[key]['answer'] = ''
        q[I.pair_of(key)]['answer'] = 'Türkçe açıklama'
        p1, p2 = self.fake('English description')
        with p1, p2:
            v.ai_fill_en('site')
            self.assertTrue(self.pump(lambda: not self.app.jobs and q[key]['answer'] == 'English description'))
        self.assertTrue(v.dirty)

    def test_unsaved_close_asks(self):
        v = self.app.open_path(copy_fixture())
        v.set_score(v.report.requirements()[0].uuid, 'C')
        with mock.patch.object(self.m.messagebox, 'askyesnocancel', return_value=None):
            self.assertFalse(self.app.close_ifs_view(v))                # vazgec: acik kalir
        self.assertIn(v, self.app.ifs_views)
        with mock.patch.object(self.m.messagebox, 'askyesnocancel', return_value=False):
            self.assertTrue(self.app.close_ifs_view(v))
        self.assertNotIn(v, self.app.ifs_views)


if __name__ == '__main__':
    unittest.main()
