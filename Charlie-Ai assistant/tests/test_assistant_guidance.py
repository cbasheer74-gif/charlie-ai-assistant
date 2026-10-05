import unittest
from unittest.mock import patch
from core.assistant_guidance import conversation_guidance
from engine.pro_chat import ProChatAssistant


class GuidanceTests(unittest.TestCase):
    def test_shared_standards_and_mode_delivery(self):
        for mode in ('text', 'voice'):
            prompt = conversation_guidance(mode)
            for requirement in ('sample data', 'live-exam', 'self-harm',
                                'unverified', 'untrusted', 'humour', 'grade',
                                'Meeting summarization', 'Email & corporate communication',
                                'Code & bug auditing', 'Voice workflow execution',
                                'Factual sexual health', 'Relationship communication',
                                'Camera object scanning', 'Defensive cyber-security',
                                'Financial intelligence', 'Viva & job interview simulation',
                                'Smart-home & IoT', 'Database & SQL optimization',
                                'Cloud architecture & DevOps', 'Data science & machine learning',
                                'API design & microservices', 'System administration & OS',
                                'Web frontend & UI', 'Mobile application development',
                                'Mathematical & statistical', 'Legal & contract comprehension',
                                'Fitness, ergonomics & wellness', 'Creative writing & public speaking',
                                'Project management & Agile'):
                self.assertIn(requirement, prompt)
        self.assertIn('short natural turns', conversation_guidance('voice'))
        self.assertIn('written explanations', conversation_guidance('text'))

    def test_actual_chat_receives_standards(self):
        captured = []
        chat = ProChatAssistant(lambda system, messages: captured.append(system) or 'draft')
        chat.respond('Help with my school science project')
        self.assertIn(conversation_guidance('text'), captured[0])

    def test_failed_turn_does_not_corrupt_context(self):
        chat = ProChatAssistant(lambda *_: 'helpful answer')
        chat.respond('I need project help')
        before = chat.history
        def unavailable(*_):
            raise RuntimeError('offline')
        chat._generate = unavailable
        with self.assertRaises(RuntimeError):
            chat.respond('Continue')
        self.assertEqual(chat.history, before)

    def test_provider_errors_do_not_expose_secrets(self):
        with patch('core.gemini.chat_text', side_effect=RuntimeError('secret-token-123')), \
             patch('core.llm_client.call_llm', side_effect=RuntimeError('private-server')):
            with self.assertRaises(RuntimeError) as error:
                ProChatAssistant._generate_default('system', [{'role': 'user', 'content': 'hi'}])
        self.assertNotIn('secret-token', str(error.exception))
        self.assertNotIn('private-server', str(error.exception))


if __name__ == '__main__':
    unittest.main()
