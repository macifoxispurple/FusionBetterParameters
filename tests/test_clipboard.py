"""
test_clipboard.py — offline tests for _copy_to_clipboard, _clipboard_write_win32,
and _clipboard_write_macos.

These tests mock the OS-level clipboard APIs so they run cross-platform in CI
without actually writing to the system clipboard.
"""
import platform
import subprocess
import pytest
from unittest.mock import patch, MagicMock, call
import BetterParameters as BP


# ---------------------------------------------------------------------------
# _copy_to_clipboard — input validation
# ---------------------------------------------------------------------------

def test_empty_text_raises_validation_error():
    with pytest.raises(BP.BPValidationError):
        BP._copy_to_clipboard({"text": ""})


def test_none_text_raises_validation_error():
    with pytest.raises(BP.BPValidationError):
        BP._copy_to_clipboard({"text": None})


def test_missing_text_key_raises_validation_error():
    with pytest.raises(BP.BPValidationError):
        BP._copy_to_clipboard({})


# ---------------------------------------------------------------------------
# Windows path
# ---------------------------------------------------------------------------

def _make_win32_mocks(global_alloc_returns=1, global_lock_returns=1,
                      open_clipboard_returns=1, set_clipboard_data_returns=1):
    kernel32 = MagicMock()
    user32 = MagicMock()
    kernel32.GlobalAlloc.return_value = global_alloc_returns
    kernel32.GlobalLock.return_value = global_lock_returns
    user32.OpenClipboard.return_value = open_clipboard_returns
    user32.SetClipboardData.return_value = set_clipboard_data_returns
    return kernel32, user32


def _patch_win32(kernel32, user32):
    return patch.multiple(
        "ctypes",
        windll=MagicMock(kernel32=kernel32, user32=user32),
        memmove=MagicMock(),
    )


def test_win32_happy_path_calls_set_clipboard_data():
    kernel32, user32 = _make_win32_mocks()
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        result = BP._copy_to_clipboard({"text": "hello"})
    assert result["ok"] is True
    user32.SetClipboardData.assert_called_once()


def test_win32_global_alloc_fail_raises():
    kernel32, user32 = _make_win32_mocks(global_alloc_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


def test_win32_global_lock_fail_raises():
    kernel32, user32 = _make_win32_mocks(global_lock_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


def test_win32_open_clipboard_fail_raises():
    kernel32, user32 = _make_win32_mocks(open_clipboard_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


def test_win32_set_clipboard_data_fail_raises():
    kernel32, user32 = _make_win32_mocks(set_clipboard_data_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


def test_win32_free_called_on_set_clipboard_failure():
    """GlobalFree must be called when SetClipboardData fails (clipboard doesn't own h_mem)."""
    kernel32, user32 = _make_win32_mocks(set_clipboard_data_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError):
            BP._copy_to_clipboard({"text": "hello"})
    kernel32.GlobalFree.assert_called_once()


def test_win32_free_not_called_on_success():
    """GlobalFree must NOT be called on success (clipboard owns the memory)."""
    kernel32, user32 = _make_win32_mocks()
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        BP._copy_to_clipboard({"text": "hello"})
    kernel32.GlobalFree.assert_not_called()


def test_win32_close_clipboard_always_called():
    """CloseClipboard must be called whether SetClipboardData succeeds or fails."""
    kernel32, user32 = _make_win32_mocks(set_clipboard_data_returns=0)
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", MagicMock()):
        with pytest.raises(BP.BPError):
            BP._copy_to_clipboard({"text": "hello"})
    user32.CloseClipboard.assert_called_once()


def test_win32_unicode_text_encoded_utf16():
    """Text must be encoded as UTF-16-LE with null terminator."""
    kernel32, user32 = _make_win32_mocks()
    memmove_mock = MagicMock()
    with patch("platform.system", return_value="Windows"), \
         patch.object(BP.ctypes, "windll", MagicMock(kernel32=kernel32, user32=user32)), \
         patch.object(BP.ctypes, "memmove", memmove_mock):
        BP._copy_to_clipboard({"text": "hi"})
    # First positional arg to memmove is dst pointer; second is the encoded bytes.
    encoded_arg = memmove_mock.call_args[0][1]
    assert encoded_arg == ("hi\x00").encode("utf-16-le")


# ---------------------------------------------------------------------------
# macOS path
# ---------------------------------------------------------------------------

def test_macos_happy_path_calls_pbcopy():
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.run") as mock_run:
        result = BP._copy_to_clipboard({"text": "hello mac"})
    assert result["ok"] is True
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert args[0][0] == ["pbcopy"]
    assert args[1]["input"] == b"hello mac"


def test_macos_pbcopy_failure_raises_io_error():
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pbcopy")):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


def test_macos_pbcopy_timeout_raises_io_error():
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pbcopy", 3)):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


# ---------------------------------------------------------------------------
# Unsupported platform
# ---------------------------------------------------------------------------

def test_unsupported_platform_raises_io_error():
    with patch("platform.system", return_value="Linux"):
        with pytest.raises(BP.BPError) as exc_info:
            BP._copy_to_clipboard({"text": "hello"})
    assert exc_info.value.bp_code == BP.ERROR_IO


# ---------------------------------------------------------------------------
# Contract: action classification
# ---------------------------------------------------------------------------

def test_copy_to_clipboard_is_read_only_action():
    assert "copyToClipboard" in BP._READ_ONLY_ACTIONS


def test_copy_to_clipboard_not_in_mutating_actions():
    assert "copyToClipboard" not in BP._MUTATING_ACTIONS
