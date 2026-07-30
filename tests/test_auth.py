"""Unit tests for auth module — credential persistence, browser extraction, QR flow."""

from __future__ import annotations

import json
import logging
import os
import time
from unittest.mock import MagicMock

import httpx
import pytest
import qrcode

from weibo_cli.auth import (
    Credential,
    QRExpiredError,
    _render_qr_half_blocks,
    clear_credential,
    extract_browser_credential,
    get_credential,
    load_credential,
    save_credential,
)


# ── Credential class ────────────────────────────────────────────────


class TestCredential:
    def test_valid_credential(self):
        cred = Credential(cookies={"SUB": "abc", "SUBP": "xyz"})
        assert cred.is_valid

    def test_empty_credential_invalid(self):
        cred = Credential(cookies={})
        assert not cred.is_valid

    def test_to_dict_includes_saved_at(self):
        cred = Credential(cookies={"SUB": "abc"})
        d = cred.to_dict()
        assert "cookies" in d
        assert "saved_at" in d
        assert isinstance(d["saved_at"], float)

    def test_from_dict(self):
        cred = Credential.from_dict({"cookies": {"SUB": "abc"}, "saved_at": 0})
        assert cred.cookies == {"SUB": "abc"}

    def test_from_dict_missing_cookies(self):
        cred = Credential.from_dict({})
        assert cred.cookies == {}
        assert not cred.is_valid

    def test_cookie_header_format(self):
        cred = Credential(cookies={"A": "1", "B": "2"})
        header = cred.as_cookie_header()
        assert "A=1" in header
        assert "B=2" in header
        assert "; " in header

    def test_roundtrip(self):
        original = Credential(cookies={"SUB": "abc", "SUBP": "xyz", "X-CSRF-TOKEN": "csrf"})
        d = original.to_dict()
        restored = Credential.from_dict(d)
        assert restored.cookies == original.cookies


# ── Credential persistence ──────────────────────────────────────────


class TestCredentialPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "credential.json")

        cred = Credential(cookies={"SUB": "test_sub"})
        save_credential(cred)

        loaded = load_credential()
        assert loaded is not None
        assert loaded.cookies == {"SUB": "test_sub"}

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "nonexistent.json")
        assert load_credential() is None

    def test_load_invalid_json(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "credential.json"
        cred_file.write_text("not valid json!!!")
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", cred_file)
        assert load_credential() is None

    def test_load_empty_cookies(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "credential.json"
        cred_file.write_text(json.dumps({"cookies": {}, "saved_at": time.time()}))
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", cred_file)
        assert load_credential() is None

    def test_clear_credential(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "credential.json"
        cred_file.write_text("{}")
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", cred_file)
        clear_credential()
        assert not cred_file.exists()

    def test_clear_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "nonexistent.json")
        # Should not raise
        clear_credential()

    def test_load_triggers_refresh_when_stale(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "credential.json"
        old_time = time.time() - (8 * 86400)  # 8 days ago
        cred_file.write_text(json.dumps({"cookies": {"SUB": "old"}, "saved_at": old_time}))
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", cred_file)

        fresh_cred = Credential(cookies={"SUB": "fresh"})
        monkeypatch.setattr("weibo_cli.auth.extract_browser_credential", lambda: fresh_cred)

        loaded = load_credential()
        assert loaded is not None
        assert loaded.cookies["SUB"] == "fresh"

    def test_load_uses_old_when_refresh_fails(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "credential.json"
        old_time = time.time() - (8 * 86400)
        cred_file.write_text(json.dumps({"cookies": {"SUB": "old"}, "saved_at": old_time}))
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", cred_file)
        monkeypatch.setattr("weibo_cli.auth.extract_browser_credential", lambda: None)

        loaded = load_credential()
        assert loaded is not None
        assert loaded.cookies["SUB"] == "old"

    def test_file_permissions(self, tmp_path, monkeypatch):
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "credential.json")

        save_credential(Credential(cookies={"SUB": "test"}))
        perms = (tmp_path / "credential.json").stat().st_mode & 0o777
        assert perms == 0o600


# ── Browser cookie extraction ───────────────────────────────────────


class TestBrowserExtraction:
    def test_extraction_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "credential.json")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"browser": "Chrome", "cookies": {"SUB": "extracted"}})

        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        cred = extract_browser_credential()
        assert cred is not None
        assert cred.cookies["SUB"] == "extracted"

    def test_extraction_no_cookies(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"error": "no_cookies"})

        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        assert extract_browser_credential() is None

    def test_extraction_not_installed(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"error": "not_installed"})

        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        assert extract_browser_credential() is None

    def test_extraction_subprocess_failure(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        assert extract_browser_credential() is None

    def test_extraction_timeout(self, monkeypatch):
        import subprocess
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 15)))
        assert extract_browser_credential() is None

    def test_extraction_invalid_json(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not json"

        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        assert extract_browser_credential() is None

    def test_extraction_with_cookie_source(self, monkeypatch, tmp_path):
        monkeypatch.setattr("weibo_cli.auth.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("weibo_cli.auth.CREDENTIAL_FILE", tmp_path / "credential.json")

        captured_cmd = {}

        def fake_run(cmd, **kw):
            captured_cmd["args"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"browser": "Firefox", "cookies": {"SUB": "fx"}})
            return result

        monkeypatch.setattr("subprocess.run", fake_run)
        cred = extract_browser_credential(cookie_source="Firefox")
        assert cred is not None
        assert "Firefox" in captured_cmd["args"]


# ── get_credential chain ────────────────────────────────────────────


class TestGetCredential:
    def test_returns_saved_first(self, monkeypatch):
        saved = Credential(cookies={"SUB": "saved"})
        monkeypatch.setattr("weibo_cli.auth.load_credential", lambda: saved)
        monkeypatch.setattr("weibo_cli.auth.extract_browser_credential", lambda: None)

        result = get_credential()
        assert result.cookies["SUB"] == "saved"

    def test_falls_back_to_browser(self, monkeypatch):
        browser_cred = Credential(cookies={"SUB": "browser"})
        monkeypatch.setattr("weibo_cli.auth.load_credential", lambda: None)
        monkeypatch.setattr("weibo_cli.auth.extract_browser_credential", lambda: browser_cred)

        result = get_credential()
        assert result.cookies["SUB"] == "browser"

    def test_returns_none_when_all_fail(self, monkeypatch):
        monkeypatch.setattr("weibo_cli.auth.load_credential", lambda: None)
        monkeypatch.setattr("weibo_cli.auth.extract_browser_credential", lambda: None)

        assert get_credential() is None


# ── QR rendering ────────────────────────────────────────────────────


def _mock_qr_login_http(monkeypatch, check_data):
    from weibo_cli.auth import QR_CHECK_URL, QR_IMAGE_URL, SSO_SIGNIN_URL

    class FakeResponse:
        def __init__(self, payload=None):
            self._payload = payload or {}

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.cookies = httpx.Cookies({"X-CSRF-TOKEN": "csrf-token"})
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            pass

        def get(self, url, params=None):
            logging.getLogger("httpx").info(
                "HTTP Request: GET %s params=%s",
                url,
                params,
            )
            if url == SSO_SIGNIN_URL:
                return FakeResponse()
            if url == QR_IMAGE_URL:
                return FakeResponse(
                    {
                        "retcode": 20000000,
                        "data": {
                            "qrid": "secret-qrid-value",
                            "image": (
                                "https://example.com/qr?"
                                "data=https%3A%2F%2Fpassport.weibo.cn%2Fsignin%2Fqrcode%2Fscan%3Fqr%3Dsecret-qrid-value"
                            ),
                        },
                    }
                )
            if url == QR_CHECK_URL:
                if isinstance(check_data, BaseException):
                    raise check_data
                return FakeResponse(check_data)
            raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr("weibo_cli.auth.httpx.Client", FakeClient)


class TestQRRendering:
    def test_save_qr_svg_writes_vector_image_with_private_permissions(self, tmp_path):
        from weibo_cli.auth import _save_qr_svg

        output_path = tmp_path / "weibo-login.svg"
        saved_path, is_temporary = _save_qr_svg(
            "https://passport.weibo.cn/signin/qrcode/scan?qr=test",
            output_path,
        )

        svg = saved_path.read_text()
        assert saved_path == output_path
        assert is_temporary is False
        assert "<svg" in svg
        assert "<path" in svg
        assert saved_path.stat().st_mode & 0o777 == 0o600

    def test_save_qr_svg_uses_secure_atomic_file_for_explicit_output(self, tmp_path, monkeypatch):
        from weibo_cli.auth import _save_qr_svg

        output_path = tmp_path / "weibo-login.svg"
        output_path.write_text("previous content")
        output_path.chmod(0o644)
        observed = {}

        class FailingImage:
            def save(self, target):
                observed["is_file_object"] = hasattr(target, "fileno")
                if observed["is_file_object"]:
                    observed["mode_while_writing"] = os.fstat(target.fileno()).st_mode & 0o777
                raise OSError("write failed")

        monkeypatch.setattr(
            qrcode.QRCode,
            "make_image",
            lambda self, image_factory: FailingImage(),
        )

        with pytest.raises(OSError):
            _save_qr_svg("https://example.com/scan", output_path)

        assert observed == {
            "is_file_object": True,
            "mode_while_writing": 0o600,
        }
        assert output_path.read_text() == "previous content"
        assert output_path.stat().st_mode & 0o777 == 0o644

    def test_present_qr_keeps_terminal_output_and_prints_svg_path(self, tmp_path, capsys):
        from weibo_cli.auth import _present_qr

        output_path = tmp_path / "weibo-login.svg"
        with _present_qr("https://example.com/scan", output_path) as presented_path:
            assert presented_path == output_path
            assert presented_path.exists()

        output = capsys.readouterr().out
        assert any(block in output for block in ("█", "▀", "▄"))
        assert str(output_path) in output
        assert output_path.exists()

    def test_present_qr_removes_temporary_svg_after_success(self):
        from weibo_cli.auth import _present_qr

        with _present_qr("https://example.com/scan") as presented_path:
            assert presented_path.exists()

        assert not presented_path.exists()

    def test_present_qr_cleanup_failure_does_not_override_success(self, monkeypatch, capsys):
        from pathlib import Path

        from weibo_cli.auth import _present_qr

        original_unlink = Path.unlink
        presented_path = None

        def fail_cleanup(path, *args, **kwargs):
            if path == presented_path:
                raise OSError("file is locked")
            return original_unlink(path, *args, **kwargs)

        try:
            with _present_qr("https://example.com/scan") as path:
                presented_path = path
                monkeypatch.setattr(Path, "unlink", fail_cleanup)
        finally:
            if presented_path is not None:
                original_unlink(presented_path, missing_ok=True)

        assert "无法删除临时二维码文件" in capsys.readouterr().out

    def test_present_qr_cleanup_failure_preserves_original_error(self, monkeypatch):
        from pathlib import Path

        from weibo_cli.auth import _present_qr

        original_unlink = Path.unlink
        presented_path = None

        def fail_cleanup(path, *args, **kwargs):
            if path == presented_path:
                raise OSError("file is locked")
            return original_unlink(path, *args, **kwargs)

        try:
            with pytest.raises(QRExpiredError):
                with _present_qr("https://example.com/scan") as path:
                    presented_path = path
                    monkeypatch.setattr(Path, "unlink", fail_cleanup)
                    raise QRExpiredError()
        finally:
            if presented_path is not None:
                original_unlink(presented_path, missing_ok=True)

    def test_present_qr_opens_svg_file_uri(self, tmp_path, monkeypatch):
        from weibo_cli.auth import _present_qr

        opened_uris = []
        monkeypatch.setattr("webbrowser.open", lambda uri: opened_uris.append(uri) or True)
        output_path = tmp_path / "weibo-login.svg"

        with _present_qr("https://example.com/scan", output_path, open_qrcode=True):
            pass

        assert opened_uris == [output_path.as_uri()]

    def test_present_qr_warns_when_browser_cannot_open(self, tmp_path, monkeypatch, capsys):
        from weibo_cli.auth import _present_qr

        monkeypatch.setattr("webbrowser.open", lambda uri: False)
        with _present_qr(
            "https://example.com/scan",
            tmp_path / "weibo-login.svg",
            open_qrcode=True,
        ):
            pass

        assert "无法自动打开二维码文件" in capsys.readouterr().out

    def test_present_qr_continues_when_browser_open_raises(self, tmp_path, monkeypatch, capsys):
        from weibo_cli.auth import _present_qr

        def fail_to_open(uri):
            raise RuntimeError("browser unavailable")

        monkeypatch.setattr("webbrowser.open", fail_to_open)
        with _present_qr(
            "https://example.com/scan",
            tmp_path / "weibo-login.svg",
            open_qrcode=True,
        ) as presented_path:
            assert presented_path.exists()

        assert "无法自动打开二维码文件" in capsys.readouterr().out

    def test_present_qr_continues_without_leaking_payload_when_svg_generation_fails(self, monkeypatch, capsys):
        from weibo_cli.auth import _present_qr

        def fail_to_save(data, output_path=None):
            raise RuntimeError("sensitive filesystem detail")

        monkeypatch.setattr("weibo_cli.auth._save_qr_svg", fail_to_save)
        payload = "sensitive-qr-payload"

        with _present_qr(payload) as presented_path:
            assert presented_path is None

        output = capsys.readouterr().out
        assert "无法生成高清二维码文件" in output
        assert payload not in output
        assert "sensitive filesystem detail" not in output

    def test_qr_login_uses_explicit_svg_without_leaking_login_tokens(self, tmp_path, monkeypatch, capsys, caplog):
        from weibo_cli.auth import qr_login

        _mock_qr_login_http(
            monkeypatch,
            {"retcode": 20000000, "data": {"url": "", "alt": ""}},
        )
        monkeypatch.setattr("weibo_cli.auth.save_credential", lambda credential: None)
        output_path = tmp_path / "weibo-login.svg"
        caplog.set_level(logging.INFO)

        credential = qr_login(qr_output=output_path)

        assert credential.is_valid
        assert output_path.exists()
        output = capsys.readouterr().out
        assert str(output_path) in output
        assert "secret-qrid-value" not in output
        assert "passport.weibo.cn/signin/qrcode/scan" not in output
        assert "secret-qrid-value" not in caplog.text
        assert "csrf-token" not in caplog.text

    def test_qr_login_sanitizes_token_bearing_http_errors(self, tmp_path, monkeypatch, capsys, caplog):
        from weibo_cli.auth import qr_login

        request = httpx.Request(
            "GET",
            "https://passport.weibo.com/check?qrid=secret-qrid-value",
        )
        response = httpx.Response(503, request=request)
        error = httpx.HTTPStatusError(
            f"Request failed: {request.url}",
            request=request,
            response=response,
        )
        _mock_qr_login_http(monkeypatch, error)
        caplog.set_level(logging.INFO)

        with pytest.raises(RuntimeError, match="Failed to check QR login status") as exc_info:
            qr_login(qr_output=tmp_path / "weibo-login.svg")

        output = capsys.readouterr().out
        combined = output + caplog.text + str(exc_info.value)
        assert "secret-qrid-value" not in combined
        assert "passport.weibo.com/check" not in combined
        assert "503" in caplog.text

    def test_qr_login_sanitizes_token_exchange_failures(self, tmp_path, monkeypatch, caplog):
        from weibo_cli.auth import qr_login

        _mock_qr_login_http(
            monkeypatch,
            {
                "retcode": 20000000,
                "data": {
                    "url": "https://login.example/cross?token=secret-cross-token",
                    "alt": "secret-alt-token",
                },
            },
        )
        monkeypatch.setattr("weibo_cli.auth.save_credential", lambda credential: None)
        caplog.set_level(logging.INFO)

        credential = qr_login(qr_output=tmp_path / "weibo-login.svg")

        assert credential.is_valid
        assert "secret-cross-token" not in caplog.text
        assert "secret-alt-token" not in caplog.text
        assert "login.example/cross" not in caplog.text

    def test_qr_login_removes_temporary_svg_after_success(self, tmp_path, monkeypatch):
        import tempfile

        from weibo_cli.auth import qr_login

        _mock_qr_login_http(
            monkeypatch,
            {"retcode": 20000000, "data": {"url": "", "alt": ""}},
        )
        monkeypatch.setattr("weibo_cli.auth.save_credential", lambda credential: None)
        real_mkstemp = tempfile.mkstemp
        monkeypatch.setattr(
            "weibo_cli.auth.tempfile.mkstemp",
            lambda **kwargs: real_mkstemp(dir=tmp_path, **kwargs),
        )

        qr_login()

        assert list(tmp_path.glob("weibo-login-*.svg")) == []

    @pytest.mark.parametrize(
        ("check_data", "expected_error"),
        [
            ({"retcode": -1, "msg": "二维码已过期"}, QRExpiredError),
            (KeyboardInterrupt(), KeyboardInterrupt),
        ],
    )
    def test_qr_login_removes_temporary_svg_after_error(
        self,
        check_data,
        expected_error,
        tmp_path,
        monkeypatch,
    ):
        import tempfile

        from weibo_cli.auth import qr_login

        _mock_qr_login_http(monkeypatch, check_data)
        real_mkstemp = tempfile.mkstemp
        monkeypatch.setattr(
            "weibo_cli.auth.tempfile.mkstemp",
            lambda **kwargs: real_mkstemp(dir=tmp_path, **kwargs),
        )

        with pytest.raises(expected_error):
            qr_login()

        assert list(tmp_path.glob("weibo-login-*.svg")) == []

    def test_render_empty_matrix(self):
        assert _render_qr_half_blocks([]) == ""

    def test_render_small_matrix(self):
        matrix = [
            [True, False],
            [False, True],
        ]
        result = _render_qr_half_blocks(matrix)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_all_true(self):
        # 4x4 matrix ensures full blocks survive the quiet zone padding
        matrix = [[True]*4 for _ in range(4)]
        result = _render_qr_half_blocks(matrix)
        assert "█" in result

    def test_render_all_false(self):
        matrix = [[False, False], [False, False]]
        result = _render_qr_half_blocks(matrix)
        # Should produce spaces (with quiet zone)
        assert isinstance(result, str)
