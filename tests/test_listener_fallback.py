import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import listen


def valid_report() -> str:
    return (
        "Ornek sembol icin teknik ve temel gorunumu aciklayan egitici rapor. "
        + ("Veriye dayali ihtimaller ve riskler ele alindi. " * 8)
        + "\nBu tabloyu ne bozar? Veri kalitesinin bozulmasi ana risktir.\n"
        + listen.REQUIRED_DISCLAIMER
    )


class ListenerFallbackTests(unittest.TestCase):
    def test_claude_success_does_not_call_codex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.txt"

            def fake_run(args, **kwargs):
                report_path.write_text(valid_report(), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with (
                patch.object(listen.shutil, "which", return_value="claude.exe") as which,
                patch.object(listen.subprocess, "run", side_effect=fake_run) as run,
                patch.object(listen, "log"),
            ):
                ok, text = listen.generate_report_with_fallback("prompt", report_path, "TEST")

            self.assertTrue(ok)
            self.assertEqual(text, valid_report())
            self.assertEqual(run.call_count, 1)
            which.assert_called_once_with("claude")

    def test_claude_limit_falls_back_to_read_only_codex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.txt"
            calls = []

            def fake_which(command):
                return {"claude": "claude.exe", "codex.cmd": "codex.cmd"}.get(command)

            def fake_run(args, **kwargs):
                calls.append(args)
                if args[0] == "claude.exe":
                    return subprocess.CompletedProcess(
                        args, 1, stdout="You've hit your session limit", stderr=""
                    )
                report_path.write_text(valid_report(), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout=valid_report(), stderr="")

            with (
                patch.object(listen.shutil, "which", side_effect=fake_which),
                patch.object(listen.subprocess, "run", side_effect=fake_run),
                patch.object(listen, "log"),
            ):
                ok, text = listen.generate_report_with_fallback("prompt", report_path, "TEST")

            self.assertTrue(ok)
            self.assertEqual(text, valid_report())
            self.assertEqual(len(calls), 2)
            self.assertIn("exec", calls[1])
            self.assertIn("read-only", calls[1])
            self.assertIn("--ephemeral", calls[1])
            self.assertIn("-o", calls[1])

    def test_invalid_claude_output_is_replaced_by_codex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.txt"
            call_count = 0

            def fake_which(command):
                return {"claude": "claude.exe", "codex.cmd": "codex.cmd"}.get(command)

            def fake_run(args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    report_path.write_text("yarim rapor", encoding="utf-8")
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                self.assertFalse(report_path.exists())
                report_path.write_text(valid_report(), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with (
                patch.object(listen.shutil, "which", side_effect=fake_which),
                patch.object(listen.subprocess, "run", side_effect=fake_run),
                patch.object(listen, "log"),
            ):
                ok, text = listen.generate_report_with_fallback("prompt", report_path, "TEST")

            self.assertTrue(ok)
            self.assertEqual(text, valid_report())

    def test_missing_both_engines_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.txt"
            with (
                patch.object(listen.shutil, "which", return_value=None),
                patch.object(listen, "log"),
            ):
                ok, text = listen.generate_report_with_fallback("prompt", report_path, "TEST")

            self.assertFalse(ok)
            self.assertIn("analiz motorlari kullanilamadi", text)


if __name__ == "__main__":
    unittest.main()
