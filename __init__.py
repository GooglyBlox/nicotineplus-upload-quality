import aifc
import gc
import os
import types
import wave
from collections import OrderedDict

from pynicotine.events import events
from pynicotine.gtkgui.application import Application
from pynicotine.gtkgui.mainwindow import MainWindow
from pynicotine.pluginsystem import BasePlugin

try:
    from gi.repository import Gtk
except Exception:  # pragma: no cover - plugin host provides GTK
    Gtk = None

try:
    from mutagen import File as MutagenFile
except Exception:  # Optional dependency
    MutagenFile = None

try:
    from pynicotine.external.tinytag import TinyTag
except Exception:  # pragma: no cover - Nicotine+ bundles TinyTag
    TinyTag = None


SUPPORTED_EXTENSIONS = {
    ".aif",
    ".aifc",
    ".aiff",
    ".flac",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
    ".m4a",
    ".aac",
    ".alac",
}

class Plugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._quality_by_real_path = {}
        self._quality_by_virtual_path = {}
        self._install_attempts = 0
        self._install_scheduled = False
        self._periodic_check_started = False
        self._tree_view = None
        self._widget = None
        self._refresh_scheduled = False

    def loaded_notification(self):
        self._schedule_ui_install()
        if not self._periodic_check_started:
            self._periodic_check_started = True
            events.schedule(delay=2, callback=self._schedule_ui_install, repeat=True)

    def unloaded_notification(self):
        self._reset_runtime_refs()

    def upload_queued_notification(self, user, virtual_path, real_path):
        self._cache_quality(virtual_path, real_path)
        self._schedule_ui_install()
        self._schedule_redraw()

    def upload_started_notification(self, user, virtual_path, real_path):
        self._cache_quality(virtual_path, real_path)
        self._schedule_ui_install()
        self._schedule_redraw()

    def upload_finished_notification(self, user, virtual_path, real_path):
        self._cache_quality(virtual_path, real_path)
        self._schedule_redraw()

    def disable(self):
        self._reset_runtime_refs()

    def _schedule_ui_install(self):
        if self._install_scheduled:
            return

        self._install_scheduled = True
        events.invoke_main_thread(self._install_column)

    def _schedule_redraw(self):
        events.invoke_main_thread(self._redraw_tree)

    def _schedule_refresh_values(self):
        if self._refresh_scheduled:
            return

        self._refresh_scheduled = True
        events.invoke_main_thread(self._refresh_quality_values)

    def _find_main_window(self):
        for obj in gc.get_objects():
            if isinstance(obj, Application):
                try:
                    if obj.window is not None:
                        return obj.window
                except Exception:
                    pass

        visible_windows = []
        fallback_windows = []

        for obj in gc.get_objects():
            if isinstance(obj, MainWindow):
                try:
                    if obj.widget is not None and obj.widget.get_visible():
                        visible_windows.append(obj)
                    else:
                        fallback_windows.append(obj)
                except Exception:
                    fallback_windows.append(obj)

        if visible_windows:
            return visible_windows[-1]

        if fallback_windows:
            return fallback_windows[-1]

        return None

    def _install_column(self):
        self._install_scheduled = False

        if Gtk is None:
            return

        window = self._find_main_window()
        if window is None:
            self._retry_install()
            return

        try:
            tree_view = window.uploads.tree_view
            uploads_view = window.uploads
            widget = tree_view.widget
        except Exception as exc:
            self._retry_install()
            return

        if widget is None:
            self._retry_install()
            return

        try:
            if not widget.get_visible():
                self._retry_install()
                return
        except Exception:
            pass

        existing_titles = self._get_column_titles(widget)

        if "Quality" in existing_titles:
            self._tree_view = tree_view
            self._widget = widget
            self._refresh_quality_values()
            return

        if self._widget is not None and self._widget != widget:
            self._tree_view = None
            self._widget = None

        self._patch_treeview_wrapper(uploads_view, tree_view)
        self._tree_view = tree_view
        self._widget = widget
        self._install_attempts = 0
        self._refresh_quality_values()

    def _retry_install(self):
        self._install_attempts += 1
        if self._install_attempts <= 60:
            events.schedule(delay=0.5, callback=self._schedule_ui_install)

    def _redraw_tree(self):
        if self._tree_view is None:
            return

        try:
            self._tree_view.redraw()
            self._tree_view.widget.queue_draw()
        except Exception:
            pass

    def _get_column_titles(self, widget):
        titles = []
        try:
            for column in widget.get_columns():
                titles.append(column.get_title() or "<empty>")
        except Exception:
            return ["<unavailable>"]
        return titles

    def _patch_treeview_wrapper(self, uploads_view, tree_view):
        self._patch_add_row(tree_view)

        columns = tree_view._columns
        if "quality" not in columns:
            new_columns = OrderedDict()
            for column_id, column_data in columns.items():
                if column_id == "status":
                    new_columns["quality"] = {
                        "column_type": "text",
                        "title": "Quality",
                        "width": 130,
                    }
                new_columns[column_id] = column_data
            tree_view._columns = new_columns

        try:
            if tree_view._columns_changed_handler is not None:
                tree_view.widget.disconnect(tree_view._columns_changed_handler)
        except Exception:
            pass

        for column in list(tree_view.widget.get_columns()):
            try:
                tree_view.widget.remove_column(column)
            except Exception:
                pass

        tree_view._column_ids = {}
        tree_view._column_offsets = {}
        tree_view._column_gvalues = {}
        tree_view._column_gesture_controllers = []
        tree_view._column_numbers = None
        tree_view._default_sort_column = None
        tree_view._sort_column = None
        tree_view._sort_type = None

        tree_view._initialise_columns(tree_view._columns)
        uploads_view.clear_model()
        uploads_view.update_model()

    def _patch_add_row(self, tree_view):
        if getattr(tree_view, "_upload_quality_add_row_patched", False):
            return

        original_add_row = tree_view.add_row
        plugin = self

        def patched_add_row(self_tree_view, values, select_row=True, parent_iterator=None):
            adjusted_values = values

            try:
                if (
                    "quality" in self_tree_view._columns
                    and "quality" in self_tree_view._column_ids
                    and len(values) == (len(self_tree_view._columns) - 1)
                ):
                    adjusted_values = list(values)
                    quality_index = list(self_tree_view._columns.keys()).index("quality")
                    adjusted_values.insert(quality_index, "")
            except Exception:
                adjusted_values = values

            result = original_add_row(adjusted_values, select_row=select_row, parent_iterator=parent_iterator)
            plugin._schedule_refresh_values()
            return result

        tree_view.add_row = types.MethodType(patched_add_row, tree_view)
        tree_view._upload_quality_add_row_patched = True

    def _refresh_quality_values(self):
        self._refresh_scheduled = False

        if self._tree_view is None:
            return

        try:
            if "quality" not in self._tree_view._column_ids:
                return
        except Exception:
            return

        for iterator in self._tree_view.iterators.values():
            try:
                transfer = self._tree_view.get_row_value(iterator, "transfer_data")
                quality_text = self._quality_from_transfer(transfer)
                self._tree_view.set_row_value(iterator, "quality", quality_text)
            except Exception:
                continue

        self._redraw_tree()

    def _reset_runtime_refs(self):
        self._tree_view = None
        self._widget = None
        self._refresh_scheduled = False

    def _quality_from_transfer(self, transfer):
        if transfer is None:
            return ""

        virtual_path = getattr(transfer, "virtual_path", None)
        if not virtual_path:
            return ""

        quality = self._quality_from_file_attributes(getattr(transfer, "file_attributes", None))
        if quality:
            self._quality_by_virtual_path[virtual_path] = quality
            return quality

        real_path = self._real_path_from_transfer(transfer)

        if real_path and real_path in self._quality_by_real_path:
            return self._quality_by_real_path[real_path]

        if virtual_path in self._quality_by_virtual_path:
            return self._quality_by_virtual_path[virtual_path]

        if real_path:
            quality = self._compute_quality(real_path, transfer.file_attributes)
            if quality:
                self._quality_by_real_path[real_path] = quality
                self._quality_by_virtual_path[virtual_path] = quality
                return quality

        estimated_quality = self._estimated_quality_from_transfer(transfer)
        if estimated_quality:
            return estimated_quality

        return ""


    def _real_path_from_transfer(self, transfer):
        real_path = None
        folder_path = getattr(transfer, "folder_path", None)
        virtual_path = getattr(transfer, "virtual_path", None)

        if folder_path and virtual_path:
            basename = virtual_path.rpartition("\\")[-1]
            if basename:
                candidate = os.path.join(folder_path, basename)
                if os.path.isfile(candidate):
                    return candidate

        try:
            real_path = self.core.shares.virtual2real(
                virtual_path,
                revert_backslash=getattr(transfer, "is_backslash_path", False),
                is_lowercase_path=getattr(transfer, "is_lowercase_path", False),
            )
        except Exception:
            real_path = None

        return real_path

    def _cache_quality(self, virtual_path, real_path):
        quality = self._compute_quality(real_path)
        if quality:
            self._quality_by_real_path[real_path] = quality
            self._quality_by_virtual_path[virtual_path] = quality

    def _compute_quality(self, real_path, file_attributes=None):
        if not real_path or not os.path.isfile(real_path):
            return ""

        if not self._is_supported_media_path(real_path):
            return ""

        quality = self._quality_from_file_attributes(file_attributes)
        if quality:
            return quality

        quality = self._quality_from_tinytag(real_path)
        if quality:
            return quality

        quality = self._quality_from_mutagen(real_path)
        if quality:
            return quality

        return self._quality_from_builtin_parser(real_path)

    def _is_supported_media_path(self, path):
        return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS

    def _quality_from_file_attributes(self, file_attributes):
        if file_attributes is None:
            return ""

        sample_rate = getattr(file_attributes, "sample_rate", None)
        bit_depth = getattr(file_attributes, "bit_depth", None)
        bitrate = getattr(file_attributes, "bitrate", None)
        vbr = getattr(file_attributes, "vbr", None)

        if sample_rate and bit_depth:
            return self._format_lossless(sample_rate, bit_depth)

        if bitrate:
            suffix = " (vbr)" if vbr == 1 else ""
            return f"{bitrate} kbps{suffix}"

        return ""

    def _estimated_quality_from_transfer(self, transfer):
        file_attributes = getattr(transfer, "file_attributes", None)
        length = getattr(file_attributes, "length", None) if file_attributes is not None else None
        size = getattr(transfer, "size", None)

        if not length or not size or length <= 0:
            return ""

        # Approximate average bitrate from bytes and duration.
        bitrate_kbps = int(round((size * 8) / max(1, length) / 1000.0))
        if bitrate_kbps <= 0:
            return ""

        # Round to common lossy bitrates for cleaner display.
        common_bitrates = [64, 96, 112, 128, 160, 192, 224, 256, 320]
        rounded = min(common_bitrates, key=lambda item: abs(item - bitrate_kbps))

        if abs(rounded - bitrate_kbps) <= 12:
            bitrate_kbps = rounded

        return f"{bitrate_kbps} kbps"

    def _quality_from_tinytag(self, real_path):
        if TinyTag is None:
            return ""

        try:
            tag = TinyTag.get(real_path)
        except Exception:
            return ""

        sample_rate = getattr(tag, "samplerate", None)
        bit_depth = getattr(tag, "bitdepth", None)
        bitrate = getattr(tag, "bitrate", None)
        is_vbr = getattr(tag, "is_vbr", None)

        if sample_rate and bit_depth:
            return self._format_lossless(sample_rate, bit_depth)

        if bitrate:
            bitrate_kbps = int(round(float(bitrate)))
            suffix = " (vbr)" if is_vbr else ""
            return f"{bitrate_kbps} kbps{suffix}"

        return ""

    def _quality_from_mutagen(self, real_path):
        if MutagenFile is None:
            return ""

        try:
            audio = MutagenFile(real_path)
        except Exception:
            return ""

        if audio is None or not hasattr(audio, "info"):
            return ""

        info = audio.info
        sample_rate = getattr(info, "sample_rate", None)
        bit_depth = getattr(info, "bits_per_sample", None)

        if sample_rate and bit_depth:
            return self._format_lossless(sample_rate, bit_depth)

        bitrate = getattr(info, "bitrate", None)
        if bitrate:
            return f"{int(round(bitrate / 1000.0))} kbps"

        return ""

    def _quality_from_builtin_parser(self, real_path):
        ext = os.path.splitext(real_path)[1].lower()

        try:
            if ext == ".flac":
                return self._parse_flac(real_path)

            if ext == ".wav":
                return self._parse_wave(real_path)

            if ext in {".aif", ".aiff", ".aifc"}:
                return self._parse_aiff(real_path)
        except Exception:
            return ""

        return ""

    def _parse_wave(self, real_path):
        with wave.open(real_path, "rb") as wav_file:
            return self._format_lossless(wav_file.getframerate(), wav_file.getsampwidth() * 8)

    def _parse_aiff(self, real_path):
        with aifc.open(real_path, "rb") as aiff_file:
            return self._format_lossless(int(aiff_file.getframerate()), aiff_file.getsampwidth() * 8)

    def _parse_flac(self, real_path):
        with open(real_path, "rb") as handle:
            if handle.read(4) != b"fLaC":
                return ""

            is_last = False
            while not is_last:
                header = handle.read(4)
                if len(header) != 4:
                    return ""

                header_byte = header[0]
                is_last = bool(header_byte & 0x80)
                block_type = header_byte & 0x7F
                length = int.from_bytes(header[1:], "big")

                if block_type != 0:
                    handle.seek(length, os.SEEK_CUR)
                    continue

                streaminfo = handle.read(length)
                if len(streaminfo) != length or length < 18:
                    return ""

                packed = int.from_bytes(streaminfo[10:18], "big")
                sample_rate = (packed >> 44) & 0xFFFFF
                bit_depth = ((packed >> 36) & 0x1F) + 1

                if sample_rate and bit_depth:
                    return self._format_lossless(sample_rate, bit_depth)

                return ""

        return ""

    def _format_lossless(self, sample_rate, bit_depth):
        khz = sample_rate / 1000.0
        return f"{khz:.3g} kHz / {bit_depth} bit"
