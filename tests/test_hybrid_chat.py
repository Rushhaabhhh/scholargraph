"""Hybrid chat falls back without corrupting a streamed answer."""
import unittest
from unittest.mock import patch

from hiresense.assistant.errors import BackendError
from hiresense.conversation.routes import ChatProvider


class HybridChatTests(unittest.TestCase):
    def setUp(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'SCHOLARGRAPH_CHAT_PROVIDER': 'auto'}, clear=True):
            self.provider = ChatProvider()

    def test_auto_uses_remote_and_falls_back_before_first_token(self):
        self.assertEqual(self.provider.kind, 'hybrid')
        with patch.object(self.provider.local, 'status', return_value={'available':True}), \
             patch.object(self.provider.remote, 'stream', side_effect=BackendError('model_rate_limited', 'limited', 429)), \
             patch.object(self.provider.local, 'stream', return_value=iter(['Local answer'])) as local:
            self.assertEqual(list(self.provider.stream([{'role':'user','content':'Hello'}])), ['Local answer'])
            local.assert_called_once()

    def test_partial_cloud_answer_is_not_joined_to_local_answer(self):
        def interrupted(_):
            yield 'Partial '
            raise BackendError('model_timeout', 'timed out', 504)
        with patch.object(self.provider.remote, 'stream', side_effect=interrupted), \
             patch.object(self.provider.local, 'stream') as local:
            stream = self.provider.stream([])
            self.assertEqual(next(stream), 'Partial ')
            with self.assertRaises(BackendError): next(stream)
            local.assert_not_called()

    def test_tool_selection_failure_does_not_block_local_generation(self):
        with patch.object(self.provider.remote, 'select_tools', side_effect=BackendError('model_unavailable','offline',503)):
            self.assertIsNone(self.provider.select_tools([]))

    def test_no_key_defaults_to_local(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(ChatProvider().kind, 'local')


if __name__ == '__main__': unittest.main()
