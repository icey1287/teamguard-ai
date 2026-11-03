import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
from checks import check_sql
from contracts import Decision, ReviewReport, ReviewRequest
from benchmarks import BAD_REVENUE, BENCHMARK_BOOK, GOOD_REVENUE, benchmark_cases
from evaluation import evaluate_case, summarize
from manage import backup
from model_client import ModelClient, ModelSettings, load_settings
from review import review_sql
from storage import Store

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ModelSettings(base_url='https://fixture.invalid/v1', model='fixture', api_key='test-only')
ISSUE = dict(severity='high', category='metric', message='Unpaid orders included', evidence='FROM orders',
             suggestion='Filter eligible orders', rule_id='R001', rule_quote='Recognized revenue')


def mock_client(result=None, status=200, raw=False, finish='stop'):
    result = result if result is not None else {'issues': [ISSUE], 'revised_sql': GOOD_REVENUE}
    def handler(request):
        body = result if raw else {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(result)}}],
                                  'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
        return httpx.Response(status, json=body)
    return ModelClient(SETTINGS, transport=httpx.MockTransport(handler))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.request = ReviewRequest(sql=BAD_REVENUE, rulebook=BENCHMARK_BOOK)

    def test_all_48_structural_expectations(self):
        for case in benchmark_cases():
            with self.subTest(case=case['id']):
                observed = {i.category for i in check_sql(case['sql'], BENCHMARK_BOOK.schema_sql)}
                self.assertEqual(observed, set() if case['group'] in {'clean', 'metric'} else {case['group']})

    def test_valid_evidence_and_revision(self):
        report = review_sql(self.request, mock_client())
        self.assertEqual(report.status, 'needs_review')
        self.assertEqual(report.issues[0].rule_quote, 'Recognized revenue')
        self.assertEqual(report.revised_sql, GOOD_REVENUE)

    def test_unsupported_evidence_fails_closed(self):
        for change in [{'rule_id': 'R999'}, {'rule_quote': '   '}, {'evidence': 'invented'}]:
            with self.subTest(change=change):
                result = {'issues': [{**ISSUE, **change}], 'revised_sql': GOOD_REVENUE}
                self.assertEqual(review_sql(self.request, mock_client(result)).status, 'incomplete')

    def test_malformed_truncated_and_failed_responses(self):
        clients = [mock_client({}, raw=True), mock_client({'choices': [None]}, raw=True),
                   mock_client(status=429), mock_client(finish='length')]
        for client in clients:
            self.assertEqual(review_sql(self.request, client).status, 'incomplete')

    def test_unsafe_revision_withheld(self):
        result = {'issues': [ISSUE], 'revised_sql': 'DROP TABLE orders;'}
        self.assertIsNone(review_sql(self.request, mock_client(result)).revised_sql)

    def test_structural_gate_skips_model(self):
        def forbidden(request):
            raise AssertionError('No model call expected')
        report = review_sql(ReviewRequest(sql='DELETE FROM orders;', rulebook=BENCHMARK_BOOK),
                            ModelClient(SETTINGS, transport=httpx.MockTransport(forbidden)))
        self.assertEqual(report.semantic_status, 'skipped')

    def test_generic_baseline_never_receives_rules(self):
        def inspect(request):
            user = json.loads(request.content)['messages'][1]['content']
            self.assertEqual(set(json.loads(user)), {'sql', 'schema_sql'})
            self.assertNotIn(BENCHMARK_BOOK.rules[0].text, user)
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
                'content': '{"issues":[],"revised_sql":null}'}}]})
        ModelClient(SETTINGS, transport=httpx.MockTransport(inspect)).review(self.request, generic=True)

    def test_missing_configuration_is_not_pass(self):
        self.assertEqual(review_sql(self.request, ModelClient(ModelSettings())).status, 'incomplete')

    def test_local_settings_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.env'
            path.write_text('MODEL_NAME=from-file\n')
            with patch.dict(os.environ, {'TEAMGUARD_MODEL_ENV_FILE': str(path)}, clear=True):
                self.assertEqual(load_settings().model, 'from-file')
                with patch.dict(os.environ, {'MODEL_NAME': 'from-environment'}):
                    self.assertEqual(load_settings().model, 'from-environment')


class StorageAndEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'workspace.sqlite3')
        self.store.save_rulebook(BENCHMARK_BOOK)

    def test_versions_are_atomic_and_reports_are_snapshots(self):
        report = review_sql(ReviewRequest(sql=BAD_REVENUE, rulebook=BENCHMARK_BOOK), mock_client())
        self.store.save_report(report)
        book = BENCHMARK_BOOK.model_copy(update={'version': 2, 'project_name': 'Updated'})
        def save(_):
            try:
                Store(self.store.path).save_rulebook(book)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(save, range(2))), 1)
        self.assertEqual(Store(self.store.path).reports()[0].request.rulebook.version, 1)
        self.store.save_decision(Decision(report_id=report.id, action='reject', reviewer='Test reviewer'))
        self.assertEqual(Store(self.store.path).decisions()[0].action, 'reject')
        with self.assertRaises(ValueError):
            self.store.save_decision(Decision(report_id='missing', action='accept', reviewer='Test reviewer'))

    def test_fresh_workspace_has_no_preloaded_content(self):
        fresh = Store(Path(self.temp.name) / 'fresh.sqlite3')
        self.assertEqual(fresh.projects(), {})
        self.assertEqual(fresh.reports(), [])
        self.assertEqual(fresh.evaluations(), [])
        self.assertEqual(fresh.decisions(), [])

    def test_backup_is_consistent_and_never_overwrites(self):
        output = Path(self.temp.name) / 'backup.sqlite3'
        backup(self.store, output)
        self.assertEqual(Store(output).projects(), self.store.projects())
        with self.assertRaises(ValueError):
            backup(self.store, output)

    def test_scoring_counts_failures_and_wrong_rules(self):
        case = next(c for c in benchmark_cases() if c['group'] == 'metric')
        failed = evaluate_case(case, 'C', ModelClient(ModelSettings()))
        self.assertEqual(summarize([failed])[0]['severe_recall'], 0)
        row = {**failed, 'complete': True, 'predicted': ['metric'], 'issues': [{'category': 'metric', 'rule_id': 'R002'}]}
        score = summarize([row])[0]
        self.assertEqual(score['label_recall'], 1)
        self.assertEqual(score['policy_rule_recall'], 0)
        safety = next(c for c in benchmark_cases() if c['group'] == 'safety')
        score = summarize([evaluate_case(safety, 'C', mock_client())])[0]
        self.assertEqual(score['model_requests'], 0)
        self.assertEqual(score['mean_cost_per_query'], 0)



class InterfaceTests(unittest.TestCase):
    def test_local_user_flow_without_network(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            'TEAMGUARD_DB': str(Path(temp) / 'ui.sqlite3'), 'MODEL_API_KEY': '',
        }):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(Store().projects(), {})
            self.assertEqual(Store().reports(), [])
            app.button[0].click().run()
            self.assertEqual(app.sidebar.radio[0].value, 'Project & rules')
            app.text_input[0].set_value('Sales team')
            app.text_area[0].set_value('CREATE TABLE sales (id INT, amount DECIMAL(10,2));')
            app.text_area[1].set_value('Sales totals sum amount.')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(Store().projects()), 1)
            app.sidebar.radio[0].set_value('Submit SQL').run()
            app.text_area[0].set_value('SELECT missing FROM sales;')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(Store().reports()), 1)
            app.sidebar.radio[0].set_value('History').run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio[0].value, 'Review report')
            # New browser session sees the same persistent report.
            restarted = AppTest.from_file(str(ROOT / 'app.py')).run()
            restarted.sidebar.radio[0].set_value('Review report').run()
            self.assertFalse(restarted.exception)
            self.assertEqual(len(restarted.selectbox[0].options), 1)

    def test_review_decision_revision_and_rule_version_flow(self):
        from streamlit.testing.v1 import AppTest
        def handler(request):
            sql = json.loads(json.loads(request.content)['messages'][1]['content'])['sql']
            result = {'issues': [ISSUE], 'revised_sql':
                      "SELECT SUM(total_amount) FROM orders WHERE status = 'paid';"}
            if "WHERE status = 'paid'" in sql:
                result = {'issues': [], 'revised_sql': None}
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                                  'message': {'content': json.dumps(result)}}]})
        client = ModelClient(SETTINGS, transport=httpx.MockTransport(handler))
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            'TEAMGUARD_DB': str(Path(temp) / 'ui.sqlite3'), 'MODEL_API_KEY': '',
        }), patch('model_client.ModelClient', return_value=client):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
            app.sidebar.radio[0].set_value('Project & rules').run()
            app.text_input[0].set_value('Revenue team')
            app.text_area[0].set_value('CREATE TABLE orders (total_amount DECIMAL(10,2), status VARCHAR(20));')
            app.text_area[1].set_value('Recognized revenue includes paid orders only.')
            app.button[0].click().run()
            app.sidebar.radio[0].set_value('Submit SQL').run()
            app.text_area[0].set_value('SELECT SUM(total_amount) FROM orders;')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            original = Store().reports()[0]
            self.assertEqual(original.status, 'needs_review')
            app.sidebar.radio[0].set_value('Review report').run()
            next(x for x in app.text_input if x.label == 'Reviewer').set_value('Reviewer A')
            next(x for x in app.text_area if x.label == 'Reason or comment').set_value('Paid filter matches the rule.')
            next(x for x in app.button if x.label == 'Record decision').click().run()
            self.assertEqual(Store().decisions()[0].action, 'accept')
            next(x for x in app.button if x.label == 'Review proposed SQL again').click().run()
            self.assertFalse(app.exception)
            revised = Store().reports()[1]
            self.assertEqual(revised.status, 'passed')
            self.assertEqual(revised.parent_report_id, original.id)
            app.sidebar.radio[0].set_value('Project & rules').run()
            app.selectbox[0].select(original.request.rulebook.project_id).run()
            app.text_area[1].set_value('Recognized revenue includes paid orders only. Exclude zero amounts.')
            app.button[0].click().run()
            self.assertEqual(len(Store().projects()[original.request.rulebook.project_id]), 2)
            self.assertEqual(Store().reports()[0].request.rulebook.version, 1)
            app.sidebar.radio[0].set_value('Evaluation').run()
            self.assertFalse(app.exception)
            self.assertEqual(Store().evaluations(), [])


if __name__ == '__main__':
    unittest.main()
