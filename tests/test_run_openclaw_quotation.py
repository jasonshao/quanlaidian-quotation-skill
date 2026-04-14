import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import scripts.run_openclaw_quotation as run_script
from scripts.feishu_file_delivery import FeishuDeliveryError


class RunOpenclawQuotationTests(unittest.TestCase):
    def _build_fake_files(self, base_dir: Path):
        form_path = base_dir / "form.json"
        form_path.write_text(
            json.dumps(
                {
                    "客户品牌名称": "海底捞火锅",
                    "餐饮类型": "正餐",
                    "门店数量": 30,
                    "门店套餐": "正餐连锁营销旗舰版",
                    "门店增值模块": ["供应链基础-门店点位", "电子发票接口"],
                    "总部模块": ["配送中心", "生产加工"],
                    "配送中心数量": 1,
                    "生产加工中心数量": 1,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        config_path = base_dir / "报价配置.json"
        config_path.write_text(json.dumps({"报价项目": []}, ensure_ascii=False), encoding="utf-8")
        pdf_path = base_dir / "报价单.pdf"
        pdf_path.write_bytes(b"pdf")
        xlsx_path = base_dir / "报价单.xlsx"
        xlsx_path.write_bytes(b"xlsx")
        return form_path, config_path, pdf_path, xlsx_path

    def test_feishu_mode_hides_local_paths_in_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            form_path, config_path, pdf_path, xlsx_path = self._build_fake_files(tmp_dir)

            with patch.object(
                run_script,
                "generate_outputs",
                return_value=(config_path, pdf_path, xlsx_path),
            ), patch.object(
                run_script,
                "should_send_to_feishu",
                return_value=True,
            ), patch.object(
                run_script,
                "deliver_files_to_feishu",
                return_value=[
                    {"file_name": "报价单.pdf", "message_id": "om_1"},
                    {"file_name": "报价单.xlsx", "message_id": "om_2"},
                    {"file_name": "报价配置.json", "message_id": "om_3"},
                ],
            ) as mocked_deliver:
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = run_script.main(
                        [
                            "--form",
                            str(form_path),
                            "--output-dir",
                            str(tmp_dir),
                            "--send-to-feishu",
                            "--feishu-chat-id",
                            "oc_test_chat",
                        ]
                    )

            self.assertEqual(rc, 0)
            stdout_text = output.getvalue()
            self.assertIn("报价文件已发送到飞书", stdout_text)
            self.assertNotIn("生成的文件（本地路径）", stdout_text)
            self.assertNotIn("/tmp/", stdout_text)
            mocked_deliver.assert_called_once()
            _, called_kwargs = mocked_deliver.call_args
            self.assertEqual(called_kwargs.get("receive_id"), "oc_test_chat")

    def test_local_mode_keeps_local_paths_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            form_path, config_path, pdf_path, xlsx_path = self._build_fake_files(tmp_dir)

            with patch.object(
                run_script,
                "generate_outputs",
                return_value=(config_path, pdf_path, xlsx_path),
            ), patch.object(
                run_script,
                "should_send_to_feishu",
                return_value=False,
            ), patch.object(run_script, "deliver_files_to_feishu") as mocked_deliver:
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = run_script.main(
                        [
                            "--form",
                            str(form_path),
                            "--output-dir",
                            str(tmp_dir),
                        ]
                    )

            self.assertEqual(rc, 0)
            stdout_text = output.getvalue()
            self.assertIn("生成的文件（本地路径）", stdout_text)
            self.assertIn(str(pdf_path), stdout_text)
            self.assertIn(str(xlsx_path), stdout_text)
            mocked_deliver.assert_not_called()

    def test_explicit_feishu_mode_returns_error_on_delivery_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            form_path, config_path, pdf_path, xlsx_path = self._build_fake_files(tmp_dir)

            with patch.object(
                run_script,
                "generate_outputs",
                return_value=(config_path, pdf_path, xlsx_path),
            ), patch.object(
                run_script,
                "should_send_to_feishu",
                return_value=True,
            ), patch.object(
                run_script,
                "deliver_files_to_feishu",
                side_effect=FeishuDeliveryError("upload fail"),
            ):
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = run_script.main(
                        [
                            "--form",
                            str(form_path),
                            "--output-dir",
                            str(tmp_dir),
                            "--send-to-feishu",
                        ]
                    )

            self.assertEqual(rc, 1)
            self.assertIn("飞书发送失败", output.getvalue())


if __name__ == "__main__":
    unittest.main()
