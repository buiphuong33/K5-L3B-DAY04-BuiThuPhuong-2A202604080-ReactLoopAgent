"""Tests cho các cải tiến tự thêm vào agent.py (không gọi LLM API)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import run_agent
from bonus.tools import BonusTools
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


def bonus_call(call_id, name, args):
    return tool_call(call_id, name, json.dumps(args))


class UnfollowedLinkTests(unittest.TestCase):
    def test_linked_incident_triggers_one_reminder(self):
        args = '{"provider":"github","incident_id":"h02n9572mx9y"}'
        fake = FakeProvider([tool_call('1', 'get_incident_details', args),
                             final('Chưa đọc incident liên quan https://stspg.io/7pwv28hvkmz8'),
                             tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
                             final('Đã đọc cả hai https://stspg.io/7pwv28hvkmz8')])
        result = run_agent('Điều tra h02n9572mx9y', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        events = [x for x in result['trace'] if x['event'] == 'validation_unfollowed_link']
        self.assertEqual(len(events), 1)
        self.assertIn('github:xr3myzj7ms51', events[0]['pending'])

    def test_reminder_is_not_repeated(self):
        args = '{"provider":"github","incident_id":"h02n9572mx9y"}'
        fake = FakeProvider([tool_call('1', 'get_incident_details', args),
                             final('Lần 1 https://stspg.io/7pwv28hvkmz8'),
                             final('Lần 2 vẫn không đọc https://stspg.io/7pwv28hvkmz8')])
        result = run_agent('x', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(sum(x['event'] == 'validation_unfollowed_link' for x in result['trace']), 1)


class RateLimitTests(unittest.TestCase):
    def test_fourth_call_after_three_429_is_blocked(self):
        calls = [bonus_call(c, 'get_vercel_status', {}) for c in 'abcd']
        fake = FakeProvider(calls + [final('Không xác định được trạng thái Vercel.')])
        result = run_agent('x', fake, BonusTools(scenario='rate_limit_always'), max_steps=8)
        self.assertEqual(result['status'], 'completed')
        executed = [x for x in result['trace'] if x['event'] == 'tool']
        self.assertEqual(len(executed), 3)
        self.assertEqual(sum(x['event'] == 'tool_blocked' for x in result['trace']), 1)
        self.assertEqual(json.loads(fake.histories[4][-1]['content'])['error'], 'RETRY_BUDGET_EXHAUSTED')

    def test_stopping_after_one_429_gets_retry_reminder(self):
        fake = FakeProvider([bonus_call('a', 'get_vercel_status', {}), final('Vercel bị rate limit.'),
                             bonus_call('b', 'get_vercel_status', {}), final('Vercel: none')])
        result = run_agent('x', fake, BonusTools(scenario='rate_limit_once'), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(sum(x['event'] == 'validation_unretried_rate_limit' for x in result['trace']), 1)
        self.assertEqual(sum(x['event'] == 'tool' for x in result['trace']), 2)

    def test_429_note_says_not_outage(self):
        fake = FakeProvider([bonus_call('a', 'get_vercel_status', {}), final()])
        run_agent('x', fake, BonusTools(scenario='rate_limit_once'))
        sent = json.loads(fake.histories[1][-1]['content'])
        self.assertEqual(sent['error'], 'RATE_LIMITED')
        self.assertIn('không phải outage', sent['agent_note'])


class ContextTests(unittest.TestCase):
    def test_long_noise_list_is_compacted_for_model_but_kept_in_trace(self):
        fake = FakeProvider([bonus_call('a', 'get_vercel_status', {}), final()])
        result = run_agent('x', fake, BonusTools(scenario='noisy'))
        sent = json.loads(fake.histories[1][-1]['content'])
        full = next(x for x in result['trace'] if x['event'] == 'tool')['result']
        self.assertEqual(len(full['distractors']), 160)
        self.assertLess(len(sent['distractors']), 10)
        self.assertEqual(sent['distractors'][-1]['_omitted_items'], 155)
        self.assertEqual(sent['incidents'], full['incidents'])

    def test_bonus_prompt_keeps_tool_prompt_and_adds_rules(self):
        fake = FakeProvider([final()])
        run_agent('x', fake, BonusTools())
        system = fake.histories[0][0]['content']
        self.assertIn('DigitalOcean', system)
        self.assertIn('RATE_LIMITED', system)


if __name__ == '__main__':
    unittest.main()
