import flet as ft
import yt_dlp
import asyncio
import os
import re
import sys
import subprocess
import warnings
import traceback
import platform
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings("ignore")
executor = ThreadPoolExecutor(max_workers=4)


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _search_sync(query, max_results=12):
    print(f"[SEARCH] query='{query}'")
    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
        "extract_flat": "in_playlist",
        "default_search": f"ytsearch{max_results}",
        "skip_download": True,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if not info:
                print("[SEARCH] info=None")
                return []
            entries = info.get("entries") or []
            print(f"[SEARCH] {len(entries)} resultados")
            results = []
            for e in entries:
                if not e:
                    continue
                vid_id = e.get("id", "")
                title  = e.get("title") or e.get("fulltitle") or "Sin titulo"
                ch     = (e.get("uploader") or e.get("channel")
                          or e.get("uploader_id") or "Desconocido")
                print(f"[SEARCH]   {title[:50]} | {vid_id}")
                results.append({
                    "title":     title,
                    "channel":   ch,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                    "url":       f"https://www.youtube.com/watch?v={vid_id}",
                })
            return results
    except Exception:
        traceback.print_exc()
        return []


def _download_sync(url, title, out_dir, progress_cb_sync):
    safe  = sanitize_filename(title)
    tmpl  = os.path.join(out_dir, f"{safe}.%(ext)s")

    def hook(d):
        if d["status"] == "downloading":
            dl    = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            pct   = dl / total * 100
            speed = d.get("_speed_str", "").strip()
            eta   = d.get("_eta_str", "").strip()
            progress_cb_sync(pct, f"Descargando {pct:.0f}%  {speed}  ETA {eta}")
        elif d["status"] == "finished":
            progress_cb_sync(100, "Convirtiendo a MP3...")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    # Android specific ffmpeg location
    if platform.system() == "Linux" and "ANDROID_ROOT" in os.environ:
        # Check if ffmpeg is in the expected place for Flet Android apps
        # Or if it's bundled in assets. This is a common path for some Flet templates.
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path
        else:
            # Fallback for common Flet/Kivy-like environments
            opts["ffmpeg_location"] = "/usr/bin/ffmpeg" 

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return os.path.join(out_dir, f"{safe}.mp3")


async def main(page: ft.Page):
    page.title      = "YT Music Downloader"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width      = 860
    page.window.height     = 700
    page.window.min_width  = 620
    page.window.min_height = 500
    page.padding           = 0
    page.bgcolor           = "#0d0d14"

    C_CARD    = "#17172b"
    C_HEADER  = "#12121f"
    C_ACCENT  = "#7c6ff7"
    C_TEXT    = "#e6e6f0"
    C_MUTED   = "#7777aa"
    C_SUCCESS = "#3dd68c"
    C_ERROR   = "#ff5c5c"
    C_BORDER  = "#252540"

    # Detectar directorio de musica en Android o PC
    if platform.system() == "Linux" and "ANDROID_ROOT" in os.environ:
        # Ruta tipica en Android
        default_dir = "/storage/emulated/0/Music"
    else:
        default_dir = str(Path.home() / "Musica")
        
    os.makedirs(default_dir, exist_ok=True)
    download_dir = {"path": default_dir}

    # ── Header ──────────────────────────────────────────────────────────────
    header = ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.HEADPHONES_ROUNDED, color="#ffffff", size=26),
                width=48, height=48, bgcolor=C_ACCENT, border_radius=14,
                alignment=ft.Alignment(0, 0),
            ),
            ft.Column([
                ft.Text("YT Music Downloader", size=22,
                        weight=ft.FontWeight.BOLD, color=C_TEXT),
                ft.Text("Descarga canciones en MP3 - 192 kbps", size=12, color=C_MUTED),
            ], spacing=2, expand=True),
        ], spacing=16),
        padding=ft.Padding.symmetric(horizontal=24, vertical=18),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1),
            colors=["#1a1a30", "#13132a"],
        ),
    )

    # ── Carpeta destino ──────────────────────────────────────────────────────
    dir_status = ft.Text("OK", size=11, color=C_SUCCESS)

    def on_dir_change(e):
        path = e.control.value.strip()
        if os.path.isdir(path):
            download_dir["path"] = path
            dir_status.value = "OK"
            dir_status.color = C_SUCCESS
        else:
            dir_status.value = "No existe"
            dir_status.color = C_ERROR
        page.update()

    def open_folder(_):
        try:
            if sys.platform == "win32":
                os.startfile(download_dir["path"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", download_dir["path"]])
            else:
                subprocess.Popen(["xdg-open", download_dir["path"]])
        except Exception:
            pass

    dir_field = ft.TextField(
        value=default_dir, expand=True, text_size=12, color=C_TEXT,
        fill_color=C_CARD, filled=True, border_color=C_BORDER,
        focused_border_color=C_ACCENT, border_radius=8,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        on_change=on_dir_change,
    )

    folder_row = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.FOLDER_ROUNDED, color=C_ACCENT, size=18),
            ft.Text("Guardar en:", size=12, color=C_MUTED),
            dir_field, dir_status,
            ft.IconButton(icon=ft.Icons.OPEN_IN_NEW_ROUNDED, icon_color=C_MUTED,
                          icon_size=16, tooltip="Abrir carpeta", on_click=open_folder),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=20, vertical=8),
        bgcolor=C_HEADER,
        border=ft.Border.only(bottom=ft.BorderSide(1, C_BORDER)),
    )

    # ── Busqueda ─────────────────────────────────────────────────────────────
    search_field = ft.TextField(
        hint_text="Buscar cancion, artista, album...",
        prefix_icon=ft.Icons.SEARCH_ROUNDED,
        border_radius=30, filled=True,
        fill_color=C_CARD, border_color=C_BORDER,
        focused_border_color=C_ACCENT, focused_border_width=2,
        color=C_TEXT, hint_style=ft.TextStyle(color=C_MUTED),
        expand=True, text_size=14, cursor_color=C_ACCENT,
        content_padding=ft.Padding.symmetric(horizontal=20, vertical=14),
    )

    # ── Estado ───────────────────────────────────────────────────────────────
    status_text  = ft.Text("Escribe algo y pulsa Buscar",
                           color=C_MUTED, size=14, text_align=ft.TextAlign.CENTER)
    loading_ring = ft.ProgressRing(color=C_ACCENT, width=36, height=36,
                                   stroke_width=3, visible=False)
    status_row   = ft.Row([loading_ring, status_text],
                          alignment=ft.MainAxisAlignment.CENTER,
                          vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # ── Lista resultados ──────────────────────────────────────────────────────
    results_list = ft.ListView(
        spacing=10,
        padding=ft.Padding.only(top=8, bottom=20),
        expand=True,
    )

    # ── Tarjeta ───────────────────────────────────────────────────────────────
    def make_card(item):
        title   = item["title"]
        channel = item["channel"]
        thumb   = item["thumbnail"]
        url     = item["url"]

        pbar       = ft.ProgressBar(value=0, color=C_ACCENT, bgcolor=C_BORDER,
                                    height=3, visible=False)
        clbl       = ft.Text("", size=11, color=C_MUTED, visible=False)
        btn_ref    = ft.Ref[ft.IconButton]()

        async def on_dl(_):
            if not os.path.isdir(download_dir["path"]):
                clbl.value = "Carpeta invalida"; clbl.color = C_ERROR
                clbl.visible = True; page.update(); return

            btn_ref.current.disabled = True
            pbar.value = 0; pbar.visible = True
            clbl.value = "Iniciando..."; clbl.color = C_MUTED
            clbl.visible = True; page.update()

            loop  = asyncio.get_event_loop()
            queue = asyncio.Queue()

            def sync_progress(pct, msg):
                loop.call_soon_threadsafe(queue.put_nowait, ("p", pct, msg))

            def run_dl():
                try:
                    path = _download_sync(url, title, download_dir["path"], sync_progress)
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", True, path))
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", False, str(exc)))

            import threading
            threading.Thread(target=run_dl, daemon=True).start()

            while True:
                msg = await queue.get()
                if msg[0] == "p":
                    pbar.value = msg[1] / 100
                    clbl.value = msg[2]; page.update()
                else:
                    btn_ref.current.disabled = False
                    pbar.visible = False
                    if msg[1]:
                        clbl.value = f"Listo: {os.path.basename(msg[2])}"
                        clbl.color = C_SUCCESS
                    else:
                        clbl.value = f"Error: {str(msg[2])[:80]}"
                        clbl.color = C_ERROR
                    page.update(); break

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Image(src=thumb, width=110, height=62,
                                         fit="cover",
                                         error_content=ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED,
                                                               color=C_MUTED, size=28)),
                        width=110, height=62, border_radius=8,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE, bgcolor=C_BORDER,
                    ),
                    ft.Column([
                        ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=C_TEXT,
                                max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Row([
                            ft.Icon(ft.Icons.PERSON_ROUNDED, size=13, color=C_MUTED),
                            ft.Text(channel, size=12, color=C_MUTED,
                                    expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                        ], spacing=4),
                    ], expand=True, spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    ft.IconButton(
                        ref=btn_ref,
                        icon=ft.Icons.DOWNLOAD_FOR_OFFLINE_ROUNDED,
                        icon_color=C_ACCENT, icon_size=32,
                        tooltip="Descargar MP3", on_click=on_dl,
                        style=ft.ButtonStyle(
                            shape=ft.CircleBorder(),
                            bgcolor={ft.ControlState.DEFAULT: "#22223a",
                                     ft.ControlState.HOVERED: "#2e2e50"},
                        ),
                    ),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Column([ft.Container(pbar, padding=ft.Padding.only(top=2)), clbl], spacing=2),
            ], spacing=4),
            bgcolor=C_CARD, border_radius=12,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border=ft.Border.all(1, C_BORDER),
        )

    # ── Logica de busqueda ────────────────────────────────────────────────────
    async def do_search(query):
        query = query.strip()
        if not query:
            return

        results_list.controls.clear()
        loading_ring.visible = True
        status_text.value    = "Buscando..."
        status_text.color    = C_MUTED
        page.update()

        try:
            loop  = asyncio.get_event_loop()
            items = await loop.run_in_executor(executor, _search_sync, query, 12)
            print(f"[UI] items recibidos: {len(items)}")

            loading_ring.visible = False

            if not items:
                status_text.value = "Sin resultados. Intenta otra busqueda."
                status_text.color = C_ERROR
                page.update()
                return

            status_text.value = f"{len(items)} resultados"
            status_text.color = C_MUTED
            for it in items:
                results_list.controls.append(make_card(it))
            page.update()

        except Exception:
            traceback.print_exc()
            loading_ring.visible = False
            status_text.value    = "Error al buscar. Ver consola."
            status_text.color    = C_ERROR
            page.update()

    async def on_submit(e):
        await do_search(e.control.value)

    async def on_btn(_):
        await do_search(search_field.value)

    search_field.on_submit = on_submit

    search_btn = ft.Button(
        "Buscar", icon=ft.Icons.SEARCH_ROUNDED, on_click=on_btn,
        style=ft.ButtonStyle(
            bgcolor=C_ACCENT, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=30),
            padding=ft.Padding.symmetric(horizontal=22, vertical=14),
            elevation=0,
        ),
    )

    search_bar = ft.Container(
        content=ft.Row([search_field, search_btn], spacing=10),
        padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        bgcolor=C_HEADER,
        border=ft.Border.only(bottom=ft.BorderSide(1, C_BORDER)),
    )

    page.add(
        ft.Column([
            header,
            search_bar,
            folder_row,
            ft.Container(content=status_row, padding=ft.Padding.symmetric(vertical=10)),
            ft.Container(content=results_list, expand=True,
                         padding=ft.Padding.symmetric(horizontal=20)),
        ], spacing=0, expand=True),
    )


if __name__ == "__main__":
    ft.run(main)