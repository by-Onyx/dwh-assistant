import json
import unittest
from assistant import Agent
from dwh_tools import dispatch
from test_assistant import FakeClient

class GeneralTests(unittest.TestCase):
    def test_general_answer_keeps_prior_requirements(self):
        class Spy(FakeClient):
            def complete(self,messages,emit=None):
                self.context=messages
                return super().complete(messages,emit)
        client=Spy(['<answer>Как часто обновлять остатки?</answer>','<call>{"name":"rules","arguments":{"topic":"modeling"}}</call>','Черновик проекта.','Предлагаю факт снимков остатков.'])
        agent=Agent(client,'general')
        agent.ask('У нас сеть аптек; нужны партии и сроки годности.')
        result=agent.ask('Ежедневно. Теперь предложи проект.')
        data=json.loads(client.context[1]['content'])
        self.assertEqual(list(data)[-1],'question')
        self.assertIn('аптек',data['conversation'][0]['content'])
        self.assertEqual(data['question'],'Ежедневно. Теперь предложи проект.')
        self.assertEqual(result['calls'][0]['arguments'],{'topic':'modeling'})
        self.assertNotIn('proposal',data)
        self.assertTrue(all(m['role']=='user' for m in data['conversation']))
        self.assertEqual(agent.messages[-1]['content'],result['answer'])
    def test_general_rules_exist_and_unknown_stays_error(self):
        for topic in ['modeling','requirements','inventory','etl']:
            self.assertIn('rule',dispatch('rules',{'topic':topic}))
        self.assertIn('error',dispatch('rules',{'topic':'run_sql'}))
    def test_general_reset_removes_previous_domain(self):
        agent=Agent(FakeClient(['<answer>Ответ для аптеки</answer>']),'general')
        agent.ask('Аптека')
        agent.reset()
        self.assertEqual(len(agent.messages),agent.initial_length)
        self.assertFalse(any(m['content']=='Аптека' for m in agent.messages))

if __name__=='__main__':
    unittest.main()
