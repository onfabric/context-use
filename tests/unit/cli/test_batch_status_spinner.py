from __future__ import annotations

from unittest.mock import MagicMock, patch

from context_use.batch.states import (
    CompleteState,
    CreatedState,
    FailedState,
    SkippedState,
)
from context_use.cli.output import _STATUS_STYLES, BatchStatusSpinner


class TestBatchStatusSpinnerInit:
    def test_preserves_order(self) -> None:
        created = CreatedState()
        batches = [
            ("b1", "Batch 001", created, ""),
            ("b2", "Batch 002", created, ""),
            ("b3", "Batch 003", created, ""),
        ]
        spinner = BatchStatusSpinner(batches)
        assert spinner._order == ["b1", "b2", "b3"]

    def test_stores_state_and_detail(self) -> None:
        created = CreatedState()
        batches = [("b1", "Batch 001", created, "some detail")]
        spinner = BatchStatusSpinner(batches)
        row = spinner._rows["b1"]
        assert row.state == created
        assert row.detail == "some detail"
        assert row.label == "Batch 001"


class TestBatchStatusSpinnerUpdate:
    def test_update_changes_state_and_detail(self) -> None:
        created = CreatedState()
        batches = [("b1", "Batch 001", created, "")]
        spinner = BatchStatusSpinner(batches)

        complete = CompleteState()
        spinner.update("b1", complete, detail="done")

        row = spinner._rows["b1"]
        assert row.state == complete
        assert row.detail == "done"

    def test_update_skips_when_unchanged(self) -> None:
        created = CreatedState()
        batches = [("b1", "Batch 001", created, "")]
        spinner = BatchStatusSpinner(batches)
        spinner._refresh = MagicMock()  # type: ignore[method-assign]

        spinner.update("b1", created, detail="")
        spinner._refresh.assert_not_called()

    def test_update_ignores_unknown_batch_id(self) -> None:
        created = CreatedState()
        batches = [("b1", "Batch 001", created, "")]
        spinner = BatchStatusSpinner(batches)
        spinner._refresh = MagicMock()  # type: ignore[method-assign]

        spinner.update("unknown", CompleteState())
        spinner._refresh.assert_not_called()

    def test_update_calls_refresh_on_change(self) -> None:
        created = CreatedState()
        batches = [("b1", "Batch 001", created, "")]
        spinner = BatchStatusSpinner(batches)
        spinner._refresh = MagicMock()  # type: ignore[method-assign]

        spinner.update("b1", CompleteState(), detail="finished")
        spinner._refresh.assert_called_once()


class TestBatchStatusSpinnerRender:
    def test_render_returns_table_with_correct_row_count(self) -> None:
        created = CreatedState()
        batches = [
            ("b1", "Batch 001", created, ""),
            ("b2", "Batch 002", CompleteState(), "done"),
        ]
        spinner = BatchStatusSpinner(batches)
        table = spinner._render()
        assert table.row_count == 2

    def test_indicator_shows_checkmark_for_complete(self) -> None:
        complete = CompleteState()
        result = BatchStatusSpinner._indicator(complete, done=True)
        assert hasattr(result, "plain")
        assert result.plain == "✓"  # type: ignore[union-attr]

    def test_indicator_shows_x_for_failed(self) -> None:
        failed = FailedState(error_message="boom", previous_status="CREATED")
        result = BatchStatusSpinner._indicator(failed, done=True)
        assert hasattr(result, "plain")
        assert result.plain == "✗"  # type: ignore[union-attr]

    def test_indicator_shows_bang_for_skipped(self) -> None:
        skipped = SkippedState(reason="empty")
        result = BatchStatusSpinner._indicator(skipped, done=True)
        assert hasattr(result, "plain")
        assert result.plain == "!"  # type: ignore[union-attr]

    def test_indicator_returns_spinner_when_not_done(self) -> None:
        from rich.spinner import Spinner

        created = CreatedState()
        result = BatchStatusSpinner._indicator(created, done=False)
        assert isinstance(result, Spinner)

    def test_status_text_formats_correctly(self) -> None:
        text = BatchStatusSpinner._status_text("MEMORY_GENERATE_PENDING")
        assert text.plain == "Memory Generate Pending"

    def test_status_text_uses_correct_style(self) -> None:
        text = BatchStatusSpinner._status_text("FAILED")
        assert text.style == "red"

    def test_status_text_falls_back_for_unknown(self) -> None:
        text = BatchStatusSpinner._status_text("SOMETHING_ELSE")
        assert text.style == "bright_blue"


class TestBatchStatusSpinnerContextManager:
    @patch("context_use.cli.output.Live")
    @patch("context_use.cli.output.Console")
    def test_enter_and_exit(
        self, mock_console_cls: MagicMock, mock_live_cls: MagicMock
    ) -> None:
        mock_live = MagicMock()
        mock_live_cls.return_value = mock_live
        mock_live.__enter__ = MagicMock(return_value=mock_live)
        mock_live.__exit__ = MagicMock(return_value=None)

        created = CreatedState()
        batches = [("b1", "Batch 001", created, "")]
        spinner = BatchStatusSpinner(batches)

        result = spinner.__enter__()
        assert result is spinner
        assert spinner._live is not None

        spinner.__exit__(None, None, None)
        assert spinner._live is None


class TestStatusStyles:
    def test_all_memory_states_have_styles(self) -> None:
        expected = {
            "CREATED",
            "MEMORY_GENERATE_PENDING",
            "MEMORY_GENERATE_COMPLETE",
            "MEMORY_EMBED_PENDING",
            "MEMORY_EMBED_COMPLETE",
            "COMPLETE",
            "SKIPPED",
            "FAILED",
        }
        assert expected == set(_STATUS_STYLES.keys())
