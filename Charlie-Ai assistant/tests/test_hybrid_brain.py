import unittest
from unittest.mock import Mock, patch
from engine.hybrid_brain import HybridBrain, task_kind, simple_arithmetic
from engine.pro_chat import ProChatAssistant
from core.llm_client import call_llm


class HybridBrainTests(unittest.TestCase):
    def test_calculator_without_model(self):
        local, cloud = Mock(), Mock()
        brain = HybridBrain('local_only', local=local, cloud=cloud)
        self.assertEqual(brain.generate('s', [{'role':'user','content':'What is 12 times 8?'}]), '12 × 8 = 96')
        local.assert_not_called()
        cloud.assert_not_called()
        self.assertEqual(simple_arithmetic('0.1 + 0.2'), '0.1 + 0.2 = 0.3')
        self.assertIn('undefined', simple_arithmetic('1 / 0'))
        self.assertIn('≈', simple_arithmetic('1 / 3'))
        self.assertIsNone(simple_arithmetic('12 * 8; delete files'))
        self.assertIsNone(simple_arithmetic('Explain why 12 * 8 is wrong'))

    def test_local_only_never_uses_cloud_on_failure(self):
        cloud = Mock()
        brain = HybridBrain('local_only', local=Mock(side_effect=RuntimeError('secret')), cloud=cloud)
        with self.assertRaises(RuntimeError) as error:
            brain.generate('system', [{'role': 'user', 'content': 'debug Python'}])
        cloud.assert_not_called()
        self.assertNotIn('secret', str(error.exception))

    def test_simple_local_complex_cloud_and_followup(self):
        local, cloud = Mock(return_value='local answer'), Mock(return_value='cloud answer')
        brain = HybridBrain(local=local, cloud=cloud)
        self.assertEqual(brain.generate('s', [{'role':'user','content':'hello'}]), 'local answer')
        messages = [{'role':'user','content':'debug Python'}, {'role':'user','content':'continue'}]
        self.assertEqual(brain.generate('s', messages), 'cloud answer')
        self.assertEqual(brain.last_reply.task, 'coding')

    def test_fallback_cooldown_and_recovery(self):
        now = [0]
        local = Mock(side_effect=[RuntimeError('offline'), 'recovered'])
        cloud = Mock(return_value='fallback')
        brain = HybridBrain(local=local, cloud=cloud, clock=lambda: now[0])
        messages = [{'role':'user','content':'hi'}]
        brain.generate('s', messages)
        self.assertTrue(brain.last_reply.fallback)
        brain.generate('s', messages)
        self.assertEqual(local.call_count, 1)
        now[0] = 31
        self.assertEqual(brain.generate('s', messages), 'recovered')

    def test_school_project_routing(self):
        self.assertEqual(task_kind([{'role':'user','content':'class 6 science project'}]), 'learning')
        self.assertEqual(task_kind([{'role':'user','content':'weekly team meeting notes with action items'}]), 'meeting')
        self.assertEqual(task_kind([{'role':'user','content':'draft a formal email to client proposal'}]), 'corporate')
        self.assertEqual(task_kind([{'role':'user','content':'security audit code review for vulnerability'}]), 'audit')
        self.assertEqual(task_kind([{'role':'user','content':'biology of human reproductive system and sexual health'}]), 'wellness')
        self.assertEqual(task_kind([{'role':'user','content':'Hey Charlie open camera and analyze this thing'}]), 'vision_scan')
        self.assertEqual(task_kind([{'role':'user','content':'check firewall rules and run network diagnostic'}]), 'cybersecurity')
        self.assertEqual(task_kind([{'role':'user','content':'calculate income tax and create budgeting spreadsheet'}]), 'finance')
        self.assertEqual(task_kind([{'role':'user','content':'start mock interview simulation with star method'}]), 'interview')
        self.assertEqual(task_kind([{'role':'user','content':'configure home assistant mqtt smart plug automation'}]), 'iot')
        self.assertEqual(task_kind([{'role':'user','content':'optimize postgres database sql query with indexing'}]), 'database')
        self.assertEqual(task_kind([{'role':'user','content':'build docker container and run kubernetes deployment pipeline'}]), 'devops')
        self.assertEqual(task_kind([{'role':'user','content':'train machine learning classification model with pandas'}]), 'ml_data')
        self.assertEqual(task_kind([{'role':'user','content':'design rest api with oauth2 jwt token rate limit'}]), 'api_design')
        self.assertEqual(task_kind([{'role':'user','content':'inspect systemd service and run bash script sysadmin'}]), 'sysadmin')
        self.assertEqual(task_kind([{'role':'user','content':'frontend react component with css grid and core web vitals'}]), 'frontend')
        self.assertEqual(task_kind([{'role':'user','content':'build flutter mobile app for app store submission'}]), 'mobile')
        self.assertEqual(task_kind([{'role':'user','content':'calculate probability distribution and hypothesis test p-value'}]), 'math_stats')
        self.assertEqual(task_kind([{'role':'user','content':'review nda agreement and contract review terms of service'}]), 'legal')
        self.assertEqual(task_kind([{'role':'user','content':'correct desk posture ergonomics and sleep hygiene'}]), 'fitness')
        self.assertEqual(task_kind([{'role':'user','content':'creative writing storytelling with presentation deck speech'}]), 'creative')
        self.assertEqual(task_kind([{'role':'user','content':'sprint planning and agile scrum backlog grooming'}]), 'agile')

    def test_local_endpoint_rejects_remote_before_request(self):
        for url in ('https://example.com', 'http://localhost.example.com', 'http://127.0.0.1@example.com'):
            with self.subTest(url=url), patch('core.llm_client.get_llm_settings', return_value=(url,'model')), \
                 patch('core.llm_client.requests.post') as post:
                with self.assertRaises(RuntimeError):
                    call_llm([], local_only=True)
                post.assert_not_called()

    def test_local_disables_redirects(self):
        response = Mock()
        response.json.return_value = {'message': {'content': 'ok'}}
        with patch('core.llm_client.get_llm_settings', return_value=('http://127.0.0.1:11434','model')), \
             patch('core.llm_client.get_llm_provider', return_value='ollama'), \
             patch('core.llm_client.requests.post', return_value=response) as post:
            self.assertEqual(call_llm([], local_only=True, think=False)['content'], 'ok')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertIs(post.call_args.kwargs['json']['think'], False)

    def test_profile_switch_drops_previous_chat(self):
        captured = []
        chat = ProChatAssistant(lambda s,m: captured.append(m) or 'ok')
        with patch.object(chat, '_active_profile_key', return_value='one'):
            chat.respond('private project one')
        with patch.object(chat, '_active_profile_key', return_value='two'):
            chat.respond('hello')
        self.assertEqual(len(captured[-1]), 1)
        self.assertNotIn('private project', str(captured[-1]))

    def test_profile_switch_during_request_rejects_stale_answer(self):
        chat = ProChatAssistant(lambda *_: 'old profile answer')
        with patch.object(chat, '_active_profile_key', side_effect=['one', 'two']):
            with self.assertRaisesRegex(RuntimeError, 'profile changed'):
                chat.respond('question')
        self.assertEqual(chat.history, [])

    def test_booster_cache_instant_hit(self):
        from engine.brain_booster import get_brain_cache
        cache = get_brain_cache()
        cache.put("what is postgresql indexing", "B-Tree indexes speed up lookups.", "database")

        brain = HybridBrain('hybrid', local=lambda *_: "fresh answer", cloud=lambda *_: "fresh answer")
        res = brain.generate("system", [{"role": "user", "content": "what is postgresql indexing"}])
        self.assertEqual(res, "B-Tree indexes speed up lookups.")
        self.assertEqual(brain.last_reply.provider, "booster_cache")


if __name__ == '__main__':
    unittest.main()
