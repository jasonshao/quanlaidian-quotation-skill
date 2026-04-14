import os
import unittest
from unittest.mock import patch

from scripts.feishu_file_delivery import FeishuClient, FeishuDeliveryError, should_send_to_feishu


class FeishuFileDeliveryTests(unittest.TestCase):
    def test_from_env_prefers_explicit_receive_id(self):
        with patch.dict(
            os.environ,
            {
                "FEISHU_APP_ID": "cli_test_app",
                "FEISHU_APP_SECRET": "cli_test_secret",
                "FEISHU_RECEIVE_ID": "",
                "FEISHU_RECEIVE_ID_TYPE": "chat_id",
            },
            clear=False,
        ):
            client = FeishuClient.from_env(receive_id="oc_test_chat", receive_id_type="chat_id")
            self.assertEqual(client.receive_id, "oc_test_chat")
            self.assertEqual(client.receive_id_type, "chat_id")

    def test_from_env_requires_receive_target(self):
        with patch.dict(
            os.environ,
            {
                "FEISHU_APP_ID": "cli_test_app",
                "FEISHU_APP_SECRET": "cli_test_secret",
                "FEISHU_RECEIVE_ID": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(FeishuDeliveryError, "缺少接收目标"):
                FeishuClient.from_env()

    def test_should_send_to_feishu_with_receive_id(self):
        with patch.dict(
            os.environ,
            {
                "FEISHU_SEND_FILES": "",
                "FEISHU_RECEIVE_ID": "",
            },
            clear=False,
        ):
            self.assertTrue(should_send_to_feishu(explicit_flag=False, receive_id="oc_test_chat"))


if __name__ == "__main__":
    unittest.main()
