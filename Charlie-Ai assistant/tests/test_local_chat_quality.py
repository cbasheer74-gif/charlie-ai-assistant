import unittest
from unittest.mock import patch
from core.study_notes import study_reference, study_card
from engine.pro_chat import ProChatAssistant
from engine.hybrid_brain import HybridBrain, BrainInputError


class LocalQualityTests(unittest.TestCase):
    def test_authored_card_is_explicit_and_narrow(self):
        question = [{'role':'user','content':'Explain evaporation for a class 6 school project. Under 80 words, suggest one safe activity.'}]
        brain = HybridBrain('local_only', local=lambda *_: self.fail('model called'))
        answer = brain.generate('s',question)
        self.assertIn('boiling is not required',answer)
        self.assertIn('same place',answer)
        self.assertIn('built-in study card',answer)
        self.assertEqual(brain.last_reply.provider,'study_card')
        self.assertIsNone(study_card([{'role':'user','content':'Explain evaporation in Hindi'}]))
        self.assertIsNone(study_card([{'role':'user','content':'Explain evaporation versus boiling'}]))

    def test_compact_prompt_retains_safety_and_grammar(self):
        with patch('memory.config_manager.get_assistant_grammar_instruction', return_value='Use feminine grammar.'):
            prompt = ProChatAssistant._system_prompt(compact=True)
        self.assertLess(len(prompt), 2000)
        for rule in ('feminine', 'untrusted', 'uncertainty', 'distress', 'supervision', 'citations'):
            self.assertIn(rule, prompt)

    def test_grounding_is_scoped_and_not_external_citation(self):
        self.assertEqual(study_reference([{'role':'user','content':'Write a Python function'}]), '')
        self.assertEqual(study_reference([{'role':'assistant','content':'evaporation'}]), '')
        notes = study_reference([{'role':'user','content':'What is evaporation?'}])
        self.assertIn('boiling is not required', notes)
        self.assertIn('not measured data', notes)
        self.assertIn('not a verified textbook citation', notes)

    def test_local_context_keeps_current_request_and_pairs(self):
        history = [{'role':'user','content':'x'*6000}, {'role':'assistant','content':'y'*6000},
                   {'role':'user','content':'current question'}]
        with patch('core.llm_client.get_llm_settings', return_value=('http://localhost:11434','qwen3.5:2b')), \
             patch('core.llm_client.call_llm', return_value={'content':'answer'}) as call:
            HybridBrain._local_generate('system', history)
        sent = call.call_args.args[0]
        self.assertEqual(sent[-1]['content'], 'current question')
        self.assertEqual(sent[1]['role'], 'user')
        self.assertLess(sum(len(m['content']) for m in sent),10000)
        self.assertEqual(len(history), 3)

    def test_oversize_input_is_not_outage_or_cloud_fallback(self):
        def local(*_):
            raise BrainInputError('Use a shorter file excerpt')
        brain = HybridBrain('local_only', local=local, cloud=lambda *_: self.fail('cloud used'))
        with self.assertRaisesRegex(BrainInputError,'shorter file'):
            brain.generate('s',[{'role':'user','content':'question'}])
        self.assertEqual(brain._cooldown, {})


if __name__ == '__main__':
    unittest.main()
